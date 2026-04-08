#!/usr/bin/env bash
set -euo pipefail
[ -d ".venv" ] && source .venv/bin/activate
[ -f ".env" ] && export $(grep -v '^#' .env | xargs)

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY in your environment or .env}"
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"
# If your MCP server mounts on /mcp, set MCP_URL=http://127.0.0.1:8000/mcp
export MCP_URL="${MCP_URL:-http://127.0.0.1:8000/mcp}"

echo "Starting AGF Media Measurement Web Agent"
echo "  MCP_URL=$MCP_URL"
echo "  MODEL=$OPENAI_MODEL"
echo "  Web UI: http://localhost:${AGENT_PORT:-8001}"
echo ""
echo "  Use --cli flag for terminal mode"
python agent/dynamic_gpt_mcp_bridge.py "$@"
