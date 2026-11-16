#!/usr/bin/env bash
# Stop the RAAHAT backend. Data in the raahat_pgdata and raahat_audio volumes is kept.
#
#   ./scripts/dev-down.sh            stop containers
#   ./scripts/dev-down.sh --remove   stop and remove containers (volumes are still kept)
source "$(dirname "$0")/lib.sh"
require_env_file

say "Stopping RAAHAT backend (worker, then API, then database)"
compose stop -t 20 worker
compose stop -t 10 api
compose stop -t 30 db
if [[ "${1:-}" == "--remove" ]]; then
  compose down
fi
ok "Stopped. Data volumes are untouched."
