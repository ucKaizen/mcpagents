#!/usr/bin/env bash
set -euo pipefail
[ -d ".venv" ] && source .venv/bin/activate
[ -f ".env" ] && export $(grep -v '^#' .env | xargs)

echo "Starting toolsets..."
echo "  Use Ctrl+C to stop"
echo ""

case "${1:-all}" in
  basic)
    echo "Starting Basic Metrics toolset on :8002"
    python3 toolsets/basic_metrics.py
    ;;
  advanced)
    echo "Starting Advanced Analytics toolset on :8003"
    python3 toolsets/advanced_analytics.py
    ;;
  all)
    echo "Starting both toolsets..."
    python3 toolsets/basic_metrics.py &
    python3 toolsets/advanced_analytics.py &
    wait
    ;;
  *)
    echo "Usage: $0 [basic|advanced|all]"
    exit 1
    ;;
esac
