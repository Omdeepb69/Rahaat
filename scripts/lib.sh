#!/usr/bin/env bash
# Shared helpers for RAAHAT operations scripts. Sourced, not executed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${RAAHAT_ENV_FILE:-$ROOT/.env}"

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32mOK\033[0m    %s\n' "$*"; }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

require_env_file() {
  [[ -f "$ENV_FILE" ]] || die "No environment file at $ENV_FILE. Copy .env.example to .env and fill it in."
}

env_value() {
  # Read KEY from the env file without sourcing it (values may contain shell syntax).
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-
}

compose() {
  docker compose --project-directory "$ROOT" -f "$ROOT/compose.yaml" --env-file "$ENV_FILE" "$@"
}

api_port() {
  local port
  port="$(env_value API_PORT)"
  echo "${port:-8000}"
}
