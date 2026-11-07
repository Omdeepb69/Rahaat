#!/usr/bin/env bash
set -e

echo "[raahat-entrypoint] Running as user: $(id -un) (uid=$(id -u), gid=$(id -g))"

case "$1" in
  api)
    echo "[raahat-entrypoint] Running database schema migrations via Alembic..."
    alembic upgrade head

    echo "[raahat-entrypoint] Starting Raahat FastAPI application server on port ${PORT:-8000}..."
    exec uvicorn raahat.api.app:app \
      --host "${HOST:-0.0.0.0}" \
      --port "${PORT:-8000}" \
      --workers "${WEB_CONCURRENCY:-2}" \
      --log-level "${LOG_LEVEL:-info}"
    ;;

  worker)
    echo "[raahat-entrypoint] Starting Raahat Background Worker service..."
    exec python -m raahat.workers.main
    ;;

  *)
    exec "$@"
    ;;
esac
