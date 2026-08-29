#!/usr/bin/env bash
# artikAgentFactory — dev launcher.
#   ./run.sh          -> backend (uvicorn :8420) + Vite dev server (:5173, proxies /api)
#   ./run.sh build    -> build the frontend into frontend/dist (served by the backend at :8420)
#   ./run.sh api      -> backend only
#   ./run.sh seed     -> create example agent configs (no live API calls)
#   ./run.sh seed --with-runs -> also execute a real live run on each (costs API calls, ~10 min)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="${ARTIKAGENTFACTORY_VENV:-$HERE/../artikAPIs/venv}"   # reuse the shared venv by default
PY="$VENV/bin/python"

if [ "${1:-}" = "build" ]; then
  echo "Building frontend..."
  (cd "$HERE/frontend" && npm install --no-fund --no-audit && npm run build)
  echo "Built frontend/dist -- now run: ./run.sh api  (open http://localhost:8420)"
  exit 0
fi

if [ "${1:-}" = "seed" ]; then
  (cd "$HERE/backend" && "$PY" -m app.seed "${2:-}")
  exit 0
fi

"$PY" -m pip install -q -r "$HERE/backend/requirements.txt"

echo "Backend -> http://localhost:8420  (docs at /docs)"
(cd "$HERE/backend" && "$PY" -m uvicorn app.main:app --reload --port 8420) &
BACK=$!
trap 'kill $BACK 2>/dev/null || true' EXIT

if [ "${1:-}" = "api" ]; then wait $BACK; fi

echo "Frontend dev -> http://localhost:5173"
(cd "$HERE/frontend" && npm install --no-fund --no-audit >/dev/null 2>&1 && npm run dev)
