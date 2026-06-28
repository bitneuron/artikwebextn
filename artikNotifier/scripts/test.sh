#!/usr/bin/env bash
# Run backend tests + frontend type-check/build.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"

echo "── backend tests ──"
cd "$HERE/backend"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
python -m pytest

echo "── frontend build/typecheck ──"
cd "$HERE/frontend"
[ -d node_modules ] || npm install
npm run build
echo "✅ all checks passed"
