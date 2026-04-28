#!/bin/sh
set -e
cd /app
if echo "${DATABASE_URL:-}" | grep -q '^postgresql'; then
  alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
