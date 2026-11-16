#!/usr/bin/env bash
# Back up the RAAHAT database and stored audio.
#
#   ./scripts/backup.sh               write backups/raahat-<timestamp>.dump (+ .audio.tar.gz)
#   KEEP=14 ./scripts/backup.sh       keep the 14 most recent backups (default 14)
#
# The dump is PostgreSQL custom format (compressed, restorable with
# scripts/restore.sh). It is taken from a consistent snapshot while the system
# keeps running. Backups contain caller details: store them as you would the
# database itself.
source "$(dirname "$0")/lib.sh"
require_env_file

keep="${KEEP:-14}"
dir="$ROOT/backups"
mkdir -p "$dir"
chmod 700 "$dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump="$dir/raahat-$stamp.dump"
audio="$dir/raahat-$stamp.audio.tar.gz"

say "Database backup"
compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --no-owner' > "$dump.partial"
# Prove the file is a readable archive before keeping it.
compose exec -T db pg_restore --list < "$dump.partial" > /dev/null || { rm -f "$dump.partial"; die "dump is not readable"; }
mv "$dump.partial" "$dump"
chmod 600 "$dump"
sha256sum "$dump" > "$dump.sha256"
ok "$(basename "$dump") ($(du -h "$dump" | cut -f1))"

say "Audio backup"
if compose ps -q api >/dev/null 2>&1 && [[ -n "$(compose ps -q api)" ]]; then
  compose exec -T api tar -czf - -C /data audio > "$audio.partial"
  mv "$audio.partial" "$audio"
  chmod 600 "$audio"
  ok "$(basename "$audio") ($(du -h "$audio" | cut -f1))"
else
  warn "api container not running; audio not backed up"
fi

say "Retention (keep $keep)"
ls -1t "$dir"/raahat-*.dump 2>/dev/null | tail -n +"$((keep + 1))" | while read -r old; do
  base="${old%.dump}"
  rm -f -- "$old" "$old.sha256" "$base.audio.tar.gz"
  ok "removed $(basename "$old")"
done
