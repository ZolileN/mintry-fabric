#!/bin/sh
set -eu

PYTHON_API_HOST="${PYTHON_API_HOST:-127.0.0.1}"
PYTHON_API_PORT="${PYTHON_API_PORT:-8000}"
MINTRY_DB_PATH="${MINTRY_DB_PATH:-/root/.mintry/vouchers.db}"

mkdir -p "$(dirname "$MINTRY_DB_PATH")"

mintry dashboard \
  --db "$MINTRY_DB_PATH" \
  --host "$PYTHON_API_HOST" \
  --port "$PYTHON_API_PORT" &

cd /app/dashboard
exec /usr/local/bin/node server.js
