#!/usr/bin/env bash
set -euo pipefail

# Activate venv if present
[ -d ".venv" ] && source .venv/bin/activate
# Load .env if present
[ -f ".env" ] && export $(grep -v '^#' .env | xargs)

echo "Starting AGF Media Measurement MCP server on http://127.0.0.1:8000/mcp"
cd server && python app_mcp.py
