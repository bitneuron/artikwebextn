#!/bin/sh
# Boot wrapper: restore the SQLite DB from S3 (if a replica exists), then run the app
# under Litestream so all writes are streamed back to S3. If LITESTREAM_BUCKET is unset
# (e.g. local Docker), run plainly with an ephemeral SQLite file.
set -e

export LITESTREAM_DB="${LITESTREAM_DB:-/data/artik_notifier.db}"
START="uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"

if [ -n "$LITESTREAM_BUCKET" ]; then
  echo "[entrypoint] Litestream enabled → s3://${LITESTREAM_BUCKET} (db=${LITESTREAM_DB})"
  if [ ! -f "$LITESTREAM_DB" ]; then
    echo "[entrypoint] restoring DB from S3 (if a replica exists)…"
    litestream restore -if-replica-exists -o "$LITESTREAM_DB" "$LITESTREAM_DB" \
      && echo "[entrypoint] restore complete" \
      || echo "[entrypoint] no existing replica — starting with a fresh DB"
  else
    echo "[entrypoint] local DB already present — skipping restore"
  fi
  # replicate keeps streaming WAL → S3; on shutdown it does a final sync, then exits.
  exec litestream replicate -exec "$START"
else
  echo "[entrypoint] Litestream disabled (no LITESTREAM_BUCKET) — ephemeral SQLite"
  exec $START
fi
