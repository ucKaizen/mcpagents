# agent/dynamic_gpt_mcp_bridge.py
"""
Web-enabled OpenAI ↔ MCP bridge.

Serves a web UI and exposes a WebSocket endpoint for real-time chat.
On each user message the agent discovers MCP tools, lets the LLM decide
which to call, executes them, and streams structured events back to the
browser (assistant text, tool calls, tool results).
"""

import os, json, asyncio, re, pathlib
from typing import Dict, Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

from openai import OpenAI
from fastmcp import Client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8001"))

# In-process MCP: if server/ is on sys.path we can skip HTTP entirely
_mcp_server = None
try:
    from app_mcp import mcp as _mcp_server
except ImportError:
    pass

SYSTEM_TEMPLATE = (
    "You are a media analytics expert with access to AGF Germany TV audience "
    "measurement data. You can query reach, market share, and cross-media "
    "metrics at program, channel, and genre level, all with demographic "
    "breakdowns by age group (3-13, 14-29, 30-49, 50-64, 65+) and gender "
    "(Male, Female).\n\n"
    "Use the available tools to answer questions. Chain multiple tool calls "
    "when needed — for example, first list programs to find names, then query "
    "detailed metrics. Always call tools rather than guessing numbers.\n\n"
    "Present data clearly with numbers. When comparing, use tables. "
    "Provide context (e.g. 'this is high/low for this demographic')."
)

WEB_DIR = pathlib.Path(__file__).resolve().parent.parent / "web"

# ---------------------------------------------------------------------------
# Schema normalization (unchanged from original)
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


def mcp_tools_to_openai_tools(mcp_tools: List[Any]) -> List[Dict[str, Any]]:
    tools = []
    for t in mcp_tools:
        raw_name = getattr(t, "name", None) or getattr(t, "tool_name", None)
        if not raw_name or not _VALID_TOOL_NAME.match(raw_name):
            continue
        desc = getattr(t, "description", "") or "MCP tool"
        schema = getattr(t, "input_schema", None) or getattr(t, "schema", None) or {}
        tools.append({
            "type": "function",
            "function": {
                "name": raw_name,
                "description": desc,
                "parameters": normalize_json_schema(schema),
            }
        })
    return tools


def _mcp_target():
    """Return in-process MCP server if available, else HTTP URL."""
    if _mcp_server is not None:
        return _mcp_server
    return MCP_URL


async def call_mcp_tool(mcp_client: Client, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    res = await mcp_client.call_tool(name, args or {})
    for c in getattr(res, "content", []):
        if getattr(c, "type", "") == "json" and getattr(c, "json", None) is not None:
            return c.json
    texts = [getattr(c, "text", "") for c in getattr(res, "content", [])
             if getattr(c, "type", "") == "text"]
    # Try parsing text as JSON
    for text in texts:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
    return {"content": texts}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="AGF Media Measurement Agent")


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_path = WEB_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Per-connection message history
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_TEMPLATE},
    ]

    try:
        while True:
            # Wait for user message
            data = await ws.receive_text()
            user_msg = json.loads(data).get("message", "").strip()
            if not user_msg:
                continue

            messages.append({"role": "user", "content": user_msg})

            # Send acknowledgment
            await ws.send_text(json.dumps({"type": "status", "content": "Thinking..."}))

            async with Client(_mcp_target()) as mcp:
                discovered = await mcp.list_tools()
                openai_tools = mcp_tools_to_openai_tools(discovered)

                if not openai_tools:
                    await ws.send_text(json.dumps({
                        "type": "assistant",
                        "content": "No tools discovered on MCP server. Is the server running?"
                    }))
                    continue

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
                        # Final answer
                        answer = msg.content or ""
                        messages.append({"role": "assistant", "content": answer})
                        await ws.send_text(json.dumps({
                            "type": "assistant",
                            "content": answer,
                        }))
                        break

                    # Append assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": tool_calls,
                    })

                    # Execute each tool call
                    for tc in tool_calls:
                        fname = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except Exception:
                            args = {}

                        # Send tool call event to UI
                        await ws.send_text(json.dumps({
                            "type": "tool_call",
                            "name": fname,
                            "args": args,
                        }))

                        try:
                            result = await call_mcp_tool(mcp, fname, args)
                        except Exception as e:
                            result = {"error": str(e)}

                        # Send tool result event to UI
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
        pass


# ---------------------------------------------------------------------------
# CLI fallback (still works without the web UI)
# ---------------------------------------------------------------------------
async def cli_mode():
    if not OPENAI_API_KEY:
        raise RuntimeError("Set OPENAI_API_KEY to use this bridge.")
    client = OpenAI(api_key=OPENAI_API_KEY)

    print(f"Connected target MCP URL: {MCP_URL}")
    print("Type a prompt. Ctrl+C or 'exit' to quit.\n")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_TEMPLATE},
    ]

    while True:
        user = input("You: ").strip()
        if user.lower() in {"exit", "quit"}:
            break

        messages.append({"role": "user", "content": user})

        async with Client(_mcp_target()) as mcp:
            discovered = await mcp.list_tools()
            openai_tools = mcp_tools_to_openai_tools(discovered)

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
                    print(f"\nAssistant:\n{answer}\n")
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
                    print(f"  [Tool Call] {fname}({json.dumps(args)})")
                    try:
                        result = await call_mcp_tool(mcp, fname, args)
                    except Exception as e:
                        result = {"error": str(e)}
                    print(f"  [Tool Result] {json.dumps(result)[:200]}...")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fname,
                        "content": json.dumps(result),
                    })
            else:
                print("\nAssistant:\nReached tool-call limit.\n")


if __name__ == "__main__":
    import sys

    if "--cli" in sys.argv:
        asyncio.run(cli_mode())
    else:
        if not OPENAI_API_KEY:
            print("ERROR: Set OPENAI_API_KEY environment variable.")
            sys.exit(1)
        print(f"MCP target: {MCP_URL}")
        print(f"Starting web agent on http://localhost:{AGENT_PORT}")
        print(f"Open http://localhost:{AGENT_PORT} in your browser.\n")
        uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
