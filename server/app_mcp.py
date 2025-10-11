# server/app_mcp.py
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("hello-mcp")

# NOTE: Depending on your fastmcp version, you may need @mcp.tool() instead of @mcp.tool
@mcp.tool
def calculate_magic_number(param: Optional[str] = None) -> dict:
    """
    Dummy MCP tool: returns a canned message and a 'magic' number.
    """
    magic = len(param) if param else 42
    return {
        "message": "This is dummy output",
        "echo_to": param or "world",
        "magic_number": magic,
    }


@mcp.tool
def calculate_brand_lift(param: Optional[str] = None) -> dict:
    """
    Dummy MCP tool: returns a canned message and a 'magic' number.
    """
    return {
        "message": "This is dummy output",
        "echo_to": param or "world",
        "brand_lift": 999,
    }

# ✅ Use a valid URI for resources (must include a scheme)
@mcp.resource("res://health")
def health() -> dict:
    return {"ok": True, "server": "hello-mcp"}

if __name__ == "__main__":
    # HTTP transport with explicit MCP path
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp")
