# agent/dynamic_gpt_mcp_bridge.py
import os, json, asyncio
from typing import Dict, Any, List

from openai import OpenAI
from fastmcp import Client  # MCP client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000")  # use /mcp if your server mounts there
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_TEMPLATE = (
    "You are a helpful assistant with access to {n} tools provided by an MCP server. "
    "Prefer calling tools when they match the user's request. Be concise and show final results clearly."
)

def normalize_json_schema(s: Dict[str, Any]) -> Dict[str, Any]:
    """
    Try to coerce an MCP tool's input schema into something OpenAI 'tools' will accept.
    We expect an object schema with 'properties' and optional 'required'.
    If the schema is missing, fall back to a permissive object schema.
    """
    if not isinstance(s, dict):
        return {"type": "object", "properties": {}}

    t = s.get("type")
    if t != "object":
        # Some servers wrap with {"anyOf":[...]}, etc. Make a permissive object if unclear.
        return {"type": "object", "properties": {}}

    props = s.get("properties")
    if not isinstance(props, dict):
        props = {}

    # Keep only JSON-serializable bits OpenAI expects
    out = {"type": "object", "properties": {}}
    for k, v in props.items():
        if not isinstance(v, dict):
            continue
        vt = v.get("type")
        # Only pass through basic scalar types; fallback to string
        if vt not in {"string", "number", "integer", "boolean", "array", "object"}:
            vt = "string"
        clean = {"type": vt}
        # Optional description
        if isinstance(v.get("description"), str):
            clean["description"] = v["description"]
        # If array/object, keep minimal structure
        if vt == "array" and isinstance(v.get("items"), dict):
            clean["items"] = {"type": v["items"].get("type", "string")}
        if vt == "object" and isinstance(v.get("properties"), dict):
            clean["properties"] = {pk: {"type": pv.get("type", "string")}
                                   for pk, pv in v["properties"].items()}
        out["properties"][k] = clean

    if isinstance(s.get("required"), list):
        out["required"] = [r for r in s["required"] if isinstance(r, str)]

    return out

def mcp_tools_to_openai_tools(mcp_tools: List[Any]) -> List[Dict[str, Any]]:
    """
    Convert MCP tool descriptors -> OpenAI 'tools' array.
    We expect each MCP tool to have .name, .description, .input_schema (jsonschema or None).
    """
    tools = []
    for t in mcp_tools:
        name = getattr(t, "name", None) or getattr(t, "tool_name", None)
        desc = getattr(t, "description", "") or "MCP tool"
        schema = getattr(t, "input_schema", None) or getattr(t, "schema", None) or {}
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": normalize_json_schema(schema),
            }
        })
    return tools

async def call_mcp_tool(mcp_client: Client, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    # Invoke and normalize result content to plain JSON/text for the model
    res = await mcp_client.call_tool(name, args or {})
    # Prefer JSON content parts if present
    for c in getattr(res, "content", []):
        if getattr(c, "type", "") == "json" and getattr(c, "json", None) is not None:
            return c.json
    # Fallback: collect text content
    texts = [getattr(c, "text", "") for c in getattr(res, "content", []) if getattr(c, "type", "") == "text"]
    return {"content": texts}

async def main():
    if not OPENAI_API_KEY:
        raise RuntimeError("Set OPENAI_API_KEY to use this bridge.")

    # 1) Connect to MCP & discover tools dynamically
    async with Client(MCP_URL) as mcp:
        discovered = await mcp.list_tools()
        if not discovered:
            print("No tools discovered on MCP server. Is it running and exposing tools?")
            return
        openai_tools = mcp_tools_to_openai_tools(discovered)

        client = OpenAI(api_key=OPENAI_API_KEY)
        system_msg = SYSTEM_TEMPLATE.format(n=len(openai_tools))

        print("Connected to MCP:", MCP_URL)
        print("Discovered tools:", [getattr(t, "name", None) for t in discovered])
        print("\nType a prompt. The model will decide if/which tool to call.")
        print("Ctrl+C or 'exit' to quit.")

        while True:
            user = input("\nYou: ").strip()
            if user.lower() in {"exit", "quit"}:
                break

            # 2) Ask model with dynamically built OpenAI tools array
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role":"system","content":system_msg},
                          {"role":"user","content":user}],
                tools=openai_tools,
            )
            msg = resp.choices[0].message

            # 3) If model asks to call a tool, route it to MCP by name (generic)
            if msg.tool_calls:
                msgs = [
                    {"role":"system","content":system_msg},
                    {"role":"user","content":user},
                    {"role":"assistant","content":None,"tool_calls":msg.tool_calls},
                ]
                tool_msgs = []
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}
                    try:
                        result = await call_mcp_tool(mcp, name, args)
                        tool_msgs.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": name,
                            "content": json.dumps(result),
                        })
                    except Exception as e:
                        tool_msgs.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": name,
                            "content": json.dumps({"error": str(e)}),
                        })

                follow = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=msgs + tool_msgs,
                )
                print("\nAssistant:\n" + (follow.choices[0].message.content or ""))
            else:
                print("\nAssistant:\n" + (msg.content or ""))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye")
