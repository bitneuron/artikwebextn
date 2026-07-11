#!/usr/bin/env bash
# Launch artikBroker on port 8100
cd "$(dirname "$0")"
# Load local secrets (gitignored) so providers like Finnhub / IBKR / admin work in dev.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
  echo "run.sh: loaded .env (FINNHUB=$([ -n "$FINNHUB_API_KEY" ] && echo set || echo unset), IBKR=$([ -n "$IBKR_BASE_URL" ] && echo set || echo unset))"
fi
PY=../artikAPIs/venv/bin/python
# Ensure the shared scoring engine (artik-engine) is installed in the venv.
"$PY" -c "import artik_engine" 2>/dev/null || \
  "$PY" -m pip install -e ../artikAgents/agents/stock_broker_agent -q
exec "$PY" -m uvicorn app:app --reload --port 8100
