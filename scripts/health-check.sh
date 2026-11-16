#!/usr/bin/env bash
# Check the RAAHAT backend and the host it runs on. Exit status is non-zero if
# anything required is failing.
#
#   ./scripts/health-check.sh                     local checks
#   ./scripts/health-check.sh https://host.ts.net also check the public URL
source "$(dirname "$0")/lib.sh"
require_env_file
status=0
port="$(api_port)"

say "Containers"
for service in db api worker; do
  state="$(compose ps --format '{{.State}} {{.Health}}' "$service" 2>/dev/null | head -1)"
  case "$state" in
    "running healthy"|"running ") ok "$service: $state" ;;
    "") fail "$service: not running"; status=1 ;;
    *) fail "$service: $state"; status=1 ;;
  esac
done

say "API"
if body="$(curl -fsS --max-time 5 "http://127.0.0.1:$port/health/ready")"; then
  ok "ready: $body"
else
  fail "http://127.0.0.1:$port/health/ready did not answer"; status=1
fi

say "Database"
db_query() { compose exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"$1\"" 2>/dev/null; }
if size="$(db_query "SELECT pg_size_pretty(pg_database_size(current_database()))")"; then
  ok "size $size, schema $(db_query 'SELECT version_num FROM alembic_version')"
  beat="$(db_query "SELECT EXTRACT(EPOCH FROM now() - max(last_beat_at))::int FROM worker_heartbeats")"
  if [[ -z "$beat" ]]; then fail "worker has never reported a heartbeat"; status=1
  elif (( beat > 30 )); then fail "worker heartbeat is ${beat}s old"; status=1
  else ok "worker heartbeat ${beat}s ago"; fi
  waiting="$(db_query "SELECT count(*) FROM reports WHERE processing_status IN ('pending','pending_enrichment','claimed')")"
  ok "reports waiting for the worker: $waiting"
else
  fail "cannot query the database"; status=1
fi

say "Host"
disk_free_pct="$(df -P "$ROOT" | awk 'NR==2 {print 100 - $5}' | tr -d '%')"
if (( disk_free_pct < 10 )); then fail "disk ${disk_free_pct}% free"; status=1; else ok "disk ${disk_free_pct}% free"; fi
mem_avail_mb="$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)"
if (( mem_avail_mb < 500 )); then warn "memory available ${mem_avail_mb} MB"; else ok "memory available ${mem_avail_mb} MB"; fi
ok "load $(cut -d' ' -f1-3 /proc/loadavg) on $(nproc) cores"
compose_stats="$(docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' $(compose ps -q) 2>/dev/null || true)"
[[ -n "$compose_stats" ]] && echo "$compose_stats" | sed 's/^/        /'

say "Backups"
latest="$(ls -1t "$ROOT"/backups/raahat-*.dump 2>/dev/null | head -1 || true)"
if [[ -z "$latest" ]]; then warn "no backup found in backups/ (run ./scripts/backup.sh)"
else
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$latest") ) / 3600 ))
  if (( age_h > 24 )); then warn "latest backup is ${age_h} h old: $(basename "$latest")"; else ok "latest backup ${age_h} h old: $(basename "$latest")"; fi
fi

if [[ -n "${1:-}" ]]; then
  say "Public endpoint"
  if body="$(curl -fsS --max-time 10 "${1%/}/health/ready")"; then ok "$1 reachable: $body"; else fail "$1 not reachable"; status=1; fi
fi

exit "$status"
