#!/bin/sh
# Boot wrapper: restore the SQLite users DB from S3 (if a replica exists), then run the
# app under Litestream so account changes are streamed back to S3. If LITESTREAM_BUCKET
# is unset (e.g. local Docker), run plainly with an ephemeral users DB.
set -e

export LITESTREAM_DB="${LITESTREAM_DB:-/data/users.db}"
START="uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"

if [ -n "$LITESTREAM_BUCKET" ]; then
  echo "[entrypoint] Litestream enabled → s3://${LITESTREAM_BUCKET} (db=${LITESTREAM_DB})"
  if [ ! -f "$LITESTREAM_DB" ]; then
    echo "[entrypoint] restoring users DB from S3 (if a replica exists)…"
    litestream restore -if-replica-exists -o "$LITESTREAM_DB" "$LITESTREAM_DB" \
      && echo "[entrypoint] restore complete — existing accounts preserved" \
      || echo "[entrypoint] no replica yet — fresh DB (admin will bootstrap)"
  else
    echo "[entrypoint] local users DB already present — skipping restore"
  fi
  exec litestream replicate -exec "$START"
else
  echo "[entrypoint] Litestream disabled (no LITESTREAM_BUCKET) — ephemeral users DB"
  exec $START
fi
