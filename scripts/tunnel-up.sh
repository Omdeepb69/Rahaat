#!/usr/bin/env bash
# Publish the local API over HTTPS with Tailscale Funnel.
#
#   ./scripts/tunnel-up.sh          expose 127.0.0.1:$API_PORT at https://<machine>.<tailnet>.ts.net
#   ./scripts/tunnel-up.sh --off    stop publishing
#
# This makes the API reachable from the internet. Authentication, CORS and
# rate limits in the API are what protect it; the tunnel only carries traffic.
# See NETWORK_CONNECTIVITY.md before running this.
source "$(dirname "$0")/lib.sh"
require_env_file
command -v tailscale >/dev/null || die "tailscale is not installed: https://tailscale.com/download/linux"

port="$(api_port)"
if [[ "${1:-}" == "--off" ]]; then
  tailscale funnel --https=443 off
  ok "Funnel stopped"
  exit 0
fi

backend_state="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState",""))' 2>/dev/null || true)"
[[ "$backend_state" == "Running" ]] || die "Tailscale is not logged in (state: ${backend_state:-unknown}). Run: sudo tailscale up"
curl -fsS --max-time 5 "http://127.0.0.1:$port/health/ready" >/dev/null || die "API is not running on 127.0.0.1:$port. Run ./scripts/dev-up.sh first."

[[ "$(env_value ENVIRONMENT)" == "production" ]] || warn "ENVIRONMENT is not 'production': API docs are exposed and a weak secret would be accepted."
[[ -n "$(env_value CORS_ALLOWED_ORIGINS)" ]] || die "CORS_ALLOWED_ORIGINS is empty; the frontend could not call the API."

say "Starting Funnel to 127.0.0.1:$port"
tailscale funnel --bg --https=443 "http://127.0.0.1:$port"
host="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
ok "Public URL: https://$host"
echo "Set VITE_API_BASE_URL=https://$host in the Vercel project, then check:"
echo "  ./scripts/health-check.sh https://$host"
