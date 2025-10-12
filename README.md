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
export API_TOKEN=devtoken123
uvicorn server.app:app --reload
