"""
Gateway Service — MCP server + tool registry + web agent + UI.

Toolsets register themselves via REST API. When the LLM calls a tool,
the gateway proxies the invocation to the owning toolset's callback URL.
"""

import os, json, re, time, pathlib, asyncio
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
import uvicorn

from openai import OpenAI

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PORT = int(os.getenv("PORT", "8000"))

WEB_DIR = pathlib.Path(__file__).resolve().parent.parent / "web"

SYSTEM_TEMPLATE = (
    "You are a media analytics assistant for AGF Germany TV audience measurement. "
    "You ONLY answer questions about German TV audience data — reach, market share, "
    "cross-media metrics, demographics, programs, channels, and genres.\n\n"
    "CRITICAL RULES:\n"
    "- You have ONLY the tools listed below. No other tools exist. Do NOT hallucinate, "
    "invent, or reference tools that are not explicitly listed.\n"
    "- When asked what tools you have, list ONLY the tools provided to you in this "
    "conversation — nothing else.\n"
    "- NEVER make up or estimate numbers. Always call a tool to get data.\n"
    "- If you don't have a tool to answer the question, say clearly: "
    "'I don't currently have a tool for that. The [capability] toolset may not be online.'\n"
    "- If the user asks about anything unrelated to media measurement, politely decline.\n"
    "- Chain multiple tool calls when needed.\n"
    "- Present data clearly with numbers. Use tables when comparing.\n"
)

# ---------------------------------------------------------------------------
# Tool Registry — toolsets register/deregister via REST
# ---------------------------------------------------------------------------

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]

class ToolsetRegistration(BaseModel):
    toolset_name: str
    callback_url: str  # POST to this URL to invoke a tool
    tools: List[ToolDefinition]

class ToolsetRecord:
    def __init__(self, name: str, callback_url: str, tools: List[ToolDefinition]):
        self.name = name
        self.callback_url = callback_url
        self.tools = {t.name: t for t in tools}
        self.registered_at = time.time()

# Global registry
_registry: Dict[str, ToolsetRecord] = {}

HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "15"))  # seconds


# ---------------------------------------------------------------------------
# Heartbeat — periodically check if toolsets are still alive
# ---------------------------------------------------------------------------

_heartbeat_failures: Dict[str, int] = {}
HEARTBEAT_MAX_FAILURES = 3  # remove after 3 consecutive failures

async def _heartbeat_loop():
    """Ping each registered toolset's health endpoint. Remove dead ones."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        if not _registry:
            continue

        dead = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, record in list(_registry.items()):
                health_url = record.callback_url.rsplit("/", 1)[0] + "/health"
                try:
                    resp = await client.get(health_url)
                    resp.raise_for_status()
                    # Reset failure count on success
                    _heartbeat_failures.pop(name, None)
                except Exception as e:
                    count = _heartbeat_failures.get(name, 0) + 1
                    _heartbeat_failures[name] = count
                    print(f"[Heartbeat] '{name}' check failed ({count}/{HEARTBEAT_MAX_FAILURES}): {health_url} — {type(e).__name__}: {e}", flush=True)
                    if count >= HEARTBEAT_MAX_FAILURES:
                        dead.append(name)
                        print(f"[Heartbeat] Removing '{name}' after {HEARTBEAT_MAX_FAILURES} consecutive failures", flush=True)

        for name in dead:
            if name in _registry:
                del _registry[name]
                _heartbeat_failures.pop(name, None)

        if dead:
            await broadcast_registry_update()


# ---------------------------------------------------------------------------
# Schema normalization for OpenAI
# ---------------------------------------------------------------------------
_VALID_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

def _valid_json_type(t: str) -> str:
    return t if t in {"string", "number", "integer", "boolean", "array", "object"} else "string"

def normalize_json_schema(s: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(s, dict):
        return {"type": "object", "properties": {}}
    t = s.get("type") or "object"
    if t != "object":
        return {"type": "object", "properties": {}}
    props_in = s.get("properties") or {}
    out_props: Dict[str, Any] = {}
    if isinstance(props_in, dict):
        for k, v in props_in.items():
            if not isinstance(v, dict):
                continue
            vt = _valid_json_type(v.get("type", "string"))
            clean: Dict[str, Any] = {"type": vt}
            desc = v.get("description")
            if isinstance(desc, str):
                clean["description"] = desc
            if vt == "array":
                items = v.get("items") or {}
                it = _valid_json_type(items.get("type", "string")) if isinstance(items, dict) else "string"
                clean["items"] = {"type": it}
            if vt == "object":
                subp = v.get("properties") or {}
                if isinstance(subp, dict):
                    clean["properties"] = {
                        pk: {"type": _valid_json_type(pv.get("type", "string"))}
                        for pk, pv in subp.items() if isinstance(pv, dict)
                    }
            out_props[k] = clean
    out: Dict[str, Any] = {"type": "object", "properties": out_props}
    req = s.get("required")
    if isinstance(req, list):
        out["required"] = [r for r in req if isinstance(r, str) and r in out_props]
    return out


def get_openai_tools() -> List[Dict[str, Any]]:
    """Build OpenAI tool definitions from currently registered toolsets."""
    tools = []
    for record in _registry.values():
        for tdef in record.tools.values():
            if not _VALID_TOOL_NAME.match(tdef.name):
                continue
            tools.append({
                "type": "function",
                "function": {
                    "name": tdef.name,
                    "description": tdef.description,
                    "parameters": normalize_json_schema(tdef.parameters),
                }
            })
    return tools


def find_tool_owner(tool_name: str) -> Optional[ToolsetRecord]:
    """Find which toolset owns a given tool."""
    for record in _registry.values():
        if tool_name in record.tools:
            return record
    return None


async def invoke_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Proxy a tool call to the owning toolset's callback URL."""
    owner = find_tool_owner(tool_name)
    if not owner:
        return {"error": f"Tool '{tool_name}' not found in any registered toolset"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            owner.callback_url,
            json={"tool_name": tool_name, "arguments": args},
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_heartbeat_loop())
    yield
    task.cancel()

app = FastAPI(title="AGF Media Measurement Gateway", lifespan=lifespan)


# --- Registry API ---

@app.post("/api/register")
async def register_toolset(reg: ToolsetRegistration):
    """Register a toolset with the gateway."""
    _registry[reg.toolset_name] = ToolsetRecord(
        name=reg.toolset_name,
        callback_url=reg.callback_url,
        tools=reg.tools,
    )
    tool_names = [t.name for t in reg.tools]
    print(f"[Registry] Registered toolset '{reg.toolset_name}' with tools: {tool_names}")
    # Notify connected WebSocket clients
    await broadcast_registry_update()
    return {"status": "registered", "toolset": reg.toolset_name, "tools": tool_names}


@app.post("/api/deregister/{toolset_name}")
async def deregister_toolset(toolset_name: str):
    """Deregister a toolset from the gateway."""
    if toolset_name in _registry:
        del _registry[toolset_name]
        print(f"[Registry] Deregistered toolset '{toolset_name}'")
        await broadcast_registry_update()
        return {"status": "deregistered", "toolset": toolset_name}
    return {"status": "not_found", "toolset": toolset_name}


@app.get("/api/toolsets")
async def list_toolsets():
    """List all registered toolsets and their tools."""
    result = {}
    for name, record in _registry.items():
        result[name] = {
            "callback_url": record.callback_url,
            "tools": [t.name for t in record.tools.values()],
            "registered_at": record.registered_at,
        }
    return {"toolsets": result, "total_tools": sum(len(r.tools) for r in _registry.values())}


@app.get("/api/health")
async def health():
    return {"ok": True, "toolsets": len(_registry)}


# --- Web UI ---

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_path = WEB_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# --- WebSocket chat + registry notifications ---

_ws_clients: List[WebSocket] = []


async def broadcast_registry_update():
    """Notify all connected WebSocket clients about registry changes."""
    toolsets_info = {}
    for name, record in _registry.items():
        toolsets_info[name] = [t.name for t in record.tools.values()]

    msg = json.dumps({
        "type": "registry_update",
        "toolsets": toolsets_info,
        "total_tools": sum(len(tools) for tools in toolsets_info.values()),
    })
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)

    # Send initial registry state
    await broadcast_registry_update()

    client = OpenAI(api_key=OPENAI_API_KEY)
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_TEMPLATE},
    ]

    try:
        while True:
            data = await ws.receive_text()
            user_msg = json.loads(data).get("message", "").strip()
            if not user_msg:
                continue

            messages.append({"role": "user", "content": user_msg})
            await ws.send_text(json.dumps({"type": "status", "content": "Thinking..."}))

            # Discover currently registered tools
            openai_tools = get_openai_tools()

            if not openai_tools:
                messages.append({"role": "assistant", "content": "No measurement tools are currently available. No toolsets have registered with the gateway yet."})
                await ws.send_text(json.dumps({
                    "type": "assistant",
                    "content": "No measurement tools are currently available. No toolsets have registered with the gateway yet. Please start a toolset service.",
                }))
                continue

            # Inject available tools into system context
            tool_names = [t["function"]["name"] for t in openai_tools]
            tool_list = "\n".join(f"  - {name}" for name in tool_names)
            dynamic_system = (
                SYSTEM_TEMPLATE +
                f"\nYou have EXACTLY {len(tool_names)} tools available right now:\n{tool_list}\n"
                "These are the ONLY tools you can use. There are no others."
            )
            messages[0] = {"role": "system", "content": dynamic_system}

            # Multi-turn tool loop (max 6 hops)
            for _ in range(6):
                resp = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    tools=openai_tools,
                )
                msg = resp.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None)

                if not tool_calls:
                    answer = msg.content or ""
                    messages.append({"role": "assistant", "content": answer})
                    await ws.send_text(json.dumps({"type": "assistant", "content": answer}))
                    break

                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": tool_calls,
                })

                for tc in tool_calls:
                    fname = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}

                    await ws.send_text(json.dumps({
                        "type": "tool_call",
                        "name": fname,
                        "args": args,
                    }))

                    try:
                        result = await invoke_tool(fname, args)
                    except Exception as e:
                        result = {"error": str(e)}

                    await ws.send_text(json.dumps({
                        "type": "tool_result",
                        "name": fname,
                        "result": result,
                    }))

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fname,
                        "content": json.dumps(result),
                    })
            else:
                await ws.send_text(json.dumps({
                    "type": "assistant",
                    "content": "Reached tool-call limit. Please try a more specific question.",
                }))

    except WebSocketDisconnect:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("ERROR: Set OPENAI_API_KEY environment variable.")
        import sys; sys.exit(1)
    print(f"Starting AGF Media Measurement Gateway on port {PORT}")
    print(f"Open http://localhost:{PORT} in your browser")
    print(f"Registry API: http://localhost:{PORT}/api/toolsets\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
