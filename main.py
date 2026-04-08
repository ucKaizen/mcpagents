"""
Single-process entry point for deployment (Railway, Render, Fly.io, etc.).

Runs the MCP server in-process and the web agent on a single port.
No need for two separate servers — fastmcp Client connects directly
to the MCP server object in memory.
"""

import sys, os, pathlib

# Make server/ importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "server"))

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8001"))
    print(f"Starting AGF Media Measurement Agent on port {port}")
    print(f"Open http://localhost:{port} in your browser\n")
    uvicorn.run(
        "agent.dynamic_gpt_mcp_bridge:app",
        host="0.0.0.0",
        port=port,
    )
