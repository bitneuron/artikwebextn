#!/usr/bin/env bash
# Launch artik_broker on port 8100
cd "$(dirname "$0")"
exec ../artikAPIs/venv/bin/python -m uvicorn app:app --reload --port 8100
