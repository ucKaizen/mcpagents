#!/usr/bin/env bash
set -euo pipefail
[ -d ".venv" ] && source .venv/bin/activate
[ -f ".env" ] && export $(grep -v '^#' .env | xargs)

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY in your environment or .env}"
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"
# If your MCP server mounts on /mcp, set MCP_URL=http://127.0.0.1:8000/mcp
export MCP_URL="${MCP_URL:-http://127.0.0.1:8000}"

echo "🔗 Dynamic GPT↔MCP Bridge"
echo "   MCP_URL=$MCP_URL"
echo "   MODEL=$OPENAI_MODEL"
python agent/dynamic_gpt_mcp_bridge.py
