#!/usr/bin/env bash
# Publish the local API (127.0.0.1:8000) on the account's free static ngrok
# domain. Requires `ngrok config add-authtoken <token>` once.
#   ./scripts/ngrok-up.sh          start (no-op if already running)
#   ./scripts/ngrok-up.sh --off    stop
set -euo pipefail
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/raahat"
PID_FILE="$STATE/ngrok.pid"
PORT="${API_PORT:-8000}"
mkdir -p "$STATE"

running() { [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; }

if [[ "${1:-}" == "--off" ]]; then
  if running; then kill "$(cat "$PID_FILE")" && rm -f "$PID_FILE" && echo "ngrok stopped"; else echo "ngrok is not running"; fi
  exit 0
fi

if ! running; then
  setsid nohup ngrok http "127.0.0.1:$PORT" ${NGROK_DOMAIN:+--url "$NGROK_DOMAIN"} \
    --log "$STATE/ngrok.log" --log-format json >/dev/null 2>&1 < /dev/null &
  echo $! > "$PID_FILE"
  sleep 4
fi
URL=$(curl -fsS http://127.0.0.1:4040/api/tunnels | python3 -c 'import json,sys; print(json.load(sys.stdin)["tunnels"][0]["public_url"])')
echo "API published at $URL"
echo "Web app build:  VITE_API_BASE_URL=$URL"
echo "API .env:       CORS_ALLOWED_ORIGINS must include the web app origin (e.g. https://omdeepb69.github.io)"
