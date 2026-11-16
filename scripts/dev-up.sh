#!/usr/bin/env bash
# Start the RAAHAT backend (database, API, worker) and wait until it is healthy.
#
#   ./scripts/dev-up.sh            build if needed and start
#   ./scripts/dev-up.sh --no-build start the existing image
source "$(dirname "$0")/lib.sh"

require_env_file
for key in POSTGRES_PASSWORD RAAHAT_SECRET_KEY CORS_ALLOWED_ORIGINS; do
  [[ -n "$(env_value "$key")" ]] || die "$key is empty in $ENV_FILE"
done
command -v docker >/dev/null || die "docker is not installed"

build=(--build)
[[ "${1:-}" == "--no-build" ]] && build=()

say "Starting RAAHAT backend"
compose up -d "${build[@]}" --wait --wait-timeout 180 || {
  compose ps
  die "Services did not become healthy. Inspect: docker compose logs --tail=100 api"
}
compose ps --format 'table {{.Service}}\t{{.Status}}'

port="$(api_port)"
ready="$(curl -fsS "http://127.0.0.1:$port/health/ready")" || die "API is not answering on 127.0.0.1:$port"
ok "API ready on http://127.0.0.1:$port  $ready"

users="$(compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM users"' 2>/dev/null || echo "?")"
if [[ "$users" == "0" ]]; then
  warn "No user accounts exist yet. Create the first administrator:"
  echo "      docker compose exec api raahat-entrypoint cli create-admin --username <name> --full-name \"<Full Name>\""
fi
echo "Next: ./scripts/health-check.sh   ·   public access: see NETWORK_CONNECTIVITY.md"
