#!/usr/bin/env bash
set -euo pipefail

# Activate venv if present
[ -d ".venv" ] && source .venv/bin/activate
# Load .env if present
[ -f ".env" ] && export $(grep -v '^#' .env | xargs)

echo "🚀 Starting REAL MCP server (hello-mcp) on http://127.0.0.1:8000"
python server/app_mcp.py
