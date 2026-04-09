#!/usr/bin/env bash
set -euo pipefail

# Activate venv if present
[ -d ".venv" ] && source .venv/bin/activate
# Load .env if present
[ -f ".env" ] && export $(grep -v '^#' .env | xargs)

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY in your environment or .env}"

echo "Starting AGF Media Measurement Gateway on http://127.0.0.1:8000"
python3 gateway/app.py
