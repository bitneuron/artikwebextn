#!/bin/sh
# Selects web vs. worker CMD from the SAME image, per WORKER_ROLE (set by ECS task
# definitions — see infra/stacks/compute_stack.py). Empty/unset = web (FastAPI).
set -eu

if [ "${WORKER_ROLE:-}" = "run" ]; then
  exec python -m app.worker.main
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8420
fi
