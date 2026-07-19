#!/usr/bin/env bash
# ArtikResearch Assistant — dev launcher.
#   ./run.sh          → backend (uvicorn :8410) + Vite dev server (:5173, proxies /api)
#   ./run.sh build    → build the frontend into frontend/dist (served by the backend at :8410)
#   ./run.sh api      → backend only
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="${ARTIKRESEARCH_VENV:-$HERE/../artikAPIs/venv}"   # reuse the shared venv by default
PY="$VENV/bin/python"

if [ "${1:-}" = "build" ]; then
  echo "▶ Building frontend…"
  (cd "$HERE/frontend" && npm install --no-fund --no-audit && npm run build)
  echo "✅ Built frontend/dist — now run: ./run.sh api  (open http://localhost:8410)"
  exit 0
fi

echo "▶ Backend → http://localhost:8410  (docs at /docs)"
(cd "$HERE/backend" && "$PY" -m uvicorn app.main:app --reload --port 8410) &
BACK=$!
trap 'kill $BACK 2>/dev/null || true' EXIT

if [ "${1:-}" = "api" ]; then wait $BACK; fi

echo "▶ Frontend dev → http://localhost:5173"
(cd "$HERE/frontend" && npm install --no-fund --no-audit >/dev/null 2>&1 && npm run dev)
