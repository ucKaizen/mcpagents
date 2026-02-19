# MCP Analytics Tools (Text Example)

This repo contains a minimal text-only **MCP-style** setup:

- A FastAPI server exposing analytics tools:
  - `compute_sales_lift`
  - `compute_reach`
  - `get_known_dimensions`
- A console "agent" for manual testing.
- Sample CSV data for `sales` and `impressions`.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Start server
➜ /workspaces/mcpagents (main) $ ./start_server.sh 
...
...
🚀 Starting REAL MCP server (hello-mcp) on http://127.0.0.1:8000
# start chatbot (in another terminal)
➜ /workspaces/mcpagents (main) $ export OPENAI_API_KEY=
➜ /workspaces/mcpagents (main) $ ./start_agent.sh 
