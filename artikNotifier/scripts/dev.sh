#!/usr/bin/env bash
# Run the backend (8080) and frontend (5173) for local development.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"

# backend
cd "$HERE/backend"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
( uvicorn app.main:app --reload --port 8080 ) &
BACK=$!

# frontend
cd "$HERE/frontend"
[ -d node_modules ] || npm install
( npm run dev ) &
FRONT=$!

echo "▶ backend  → http://localhost:8080  (docs: /docs)"
echo "▶ frontend → http://localhost:5173"
trap "kill $BACK $FRONT 2>/dev/null" EXIT
wait
