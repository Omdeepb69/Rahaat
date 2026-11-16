#!/bin/sh
# Container entry point for the RAAHAT image.
set -eu
case "${1:-api}" in
  api)
    # Migrations are idempotent; running them here keeps schema and code in step.
    alembic upgrade head
    exec python -m raahat.serve
    ;;
  worker)
    exec python -m raahat.workers.main
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  cli)
    shift
    exec python -m raahat.cli "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
