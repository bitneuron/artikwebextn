#!/usr/bin/env bash
# Launch artik_broker on port 8100
cd "$(dirname "$0")"
PY=../artikAPIs/venv/bin/python
# Ensure the shared scoring engine (artik-engine) is installed in the venv.
"$PY" -c "import artik_engine" 2>/dev/null || \
  "$PY" -m pip install -e ../artikagents/agents/stock_broker_agent -q
exec "$PY" -m uvicorn app:app --reload --port 8100
