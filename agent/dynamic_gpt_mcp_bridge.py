import os, json, asyncio, re
from typing import Dict, Any, List

from openai import OpenAI
from fastmcp import Client  # MCP client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_TEMPLATE = (
    "You are a strategic analytics agent with access to multiple tools. "
    "For complex queries, reason step by step, plan which tools to call, "
    "use multiple tool calls if needed, and synthesize a clear final answer."
)

_VALID_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

def _valid_json_type(t: str) -> str:
    return t if t in {"string","number","integer","boolean","array","object"} else "string"

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
            clean = {"type": vt}
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
                    clean["properties"] = {pk: {"type": _valid_json_type(pv.get("type","string"))}
                                           for pk, pv in subp.items() if isinstance(pv, dict)}
            out_props[k] = clean
    out = {"type": "object", "properties": out_props}
    req = s.get("required")
    if isinstance(req, list):
        out["required"] = [r for r in req if isinstance(r, str) and r in out_props]
    return out

def mcp_tools_to_openai_tools(mcp_tools: List[Any]) -> List[Dict[str, Any]]:
    tools = []
    for t in mcp_tools:
        raw_name = getattr(t, "name", None) or getattr(t, "tool_name", None)
        if not raw_name or not _VALID_TOOL_NAME.match(raw_name):
            # skip invalid names
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

async def call_mcp_tool(mcp_client: Client, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    res = await mcp_client.call_tool(name, args or {})
    for c in getattr(res, "content", []):
        if getattr(c, "type", "") == "json" and getattr(c, "json", None) is not None:
            return c.json
    texts = [getattr(c, "text", "") for c in getattr(res, "content", []) if getattr(c, "type", "") == "text"]
    return {"content": texts}

async def run_turn(client: OpenAI, user: str):
    async with Client(MCP_URL) as mcp:
        discovered = await mcp.list_tools()
        if not discovered:
            print("No tools discovered on MCP server.")
            return
        openai_tools = mcp_tools_to_openai_tools(discovered)
        system_msg = SYSTEM_TEMPLATE  # no unused .format()

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user},
        ]

        # loop to allow multiple tool hops (cap at 4)
        for _ in range(4):
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=openai_tools,
                # tool_choice="auto",  # optional; default is auto
            )
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)

            if not tool_calls:
                # final answer
                print("\nAssistant:\n" + (msg.content or ""))
                return

            # append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls,
            })

            # execute tools and append tool results
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                try:
                    result = await call_mcp_tool(mcp, name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,  # optional
                        "content": json.dumps(result),
                    })
                except Exception as e:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps({"error": str(e)}),
                    })

        # safety: if the model keeps asking for tools
        print("\nAssistant:\nReached tool-call limit without a final answer.")

async def main():
    if not OPENAI_API_KEY:
        raise RuntimeError("Set OPENAI_API_KEY to use this bridge.")
    client = OpenAI(api_key=OPENAI_API_KEY)

    print(f"Connected target MCP URL: {MCP_URL}")
    print("Type a prompt. The bridge will discover tools fresh on each turn.")
    print("Ctrl+C or 'exit' to quit.")

    while True:
        user = input("\nYou: ").strip()
        if user.lower() in {"exit", "quit"}:
            break
        await run_turn(client, user)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye")
