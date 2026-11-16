#!/usr/bin/env bash
# Restore a RAAHAT backup. This REPLACES the current database contents.
#
#   ./scripts/restore.sh backups/raahat-<timestamp>.dump --yes
#
# Steps: verify checksum, stop API and worker, take a safety backup of the
# current database, restore, run migrations, start API and worker.
source "$(dirname "$0")/lib.sh"
require_env_file

dump="${1:-}"
[[ -n "$dump" && -f "$dump" ]] || die "usage: $0 <backup.dump> --yes"
[[ "${2:-}" == "--yes" ]] || die "Restoring replaces all current data. Re-run with --yes to confirm."

if [[ -f "$dump.sha256" ]]; then
  (cd "$(dirname "$dump")" && sha256sum -c "$(basename "$dump").sha256" >/dev/null) || die "checksum mismatch for $dump"
  ok "checksum verified"
else
  warn "no checksum file next to $dump"
fi
compose exec -T db pg_restore --list < "$dump" > /dev/null || die "$dump is not a readable PostgreSQL archive"

say "Safety backup of the current database"
KEEP=1000 "$ROOT/scripts/backup.sh" > /dev/null
ok "written to backups/ before restoring"

say "Stopping API and worker"
compose stop -t 20 worker api

say "Restoring $(basename "$dump")"
compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --force --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' < "$dump"
ok "database restored"

audio="${dump%.dump}.audio.tar.gz"
if [[ -f "$audio" ]]; then
  compose run --rm -T --no-deps --entrypoint sh api -c 'rm -rf /data/audio/* && tar -xzf - -C /data' < "$audio"
  ok "audio restored"
fi

say "Starting API (runs migrations) and worker"
compose up -d --wait api worker
ok "restore complete"
sleep 6  # let the worker write a fresh heartbeat before checking
"$ROOT/scripts/health-check.sh" || true
