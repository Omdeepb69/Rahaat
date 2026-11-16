# Backup and recovery

## What is backed up

| Data | Where | How |
|---|---|---|
| Database (reports, incidents, audit trail, users, resources, landmarks, alerts) | volume `raahat_pgdata` | `pg_dump --format=custom` from a consistent snapshot while running |
| Voice recordings | volume `raahat_audio` | tar.gz of `/data/audio` |
| Configuration | `.env` | **Not** backed up by the script. Keep a copy in your password manager. |

Backups contain caller names and phone numbers. `backups/` is created with mode
700, files with mode 600, and the directory is git-ignored. Copy them only to
encrypted storage.

## Taking a backup

```bash
./scripts/backup.sh              # backups/raahat-<UTC timestamp>.dump, .dump.sha256, .audio.tar.gz
KEEP=30 ./scripts/backup.sh      # retention (default: keep 14)
```

The script checks the dump is a readable archive before keeping it and writes a
SHA-256 checksum.

Schedule it hourly during an active operation (crontab of the user who runs
Docker):

```
0 * * * * cd /path/to/rahaat && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Copy backups off the laptop: a laptop failure takes its disk with it. For
example, to an encrypted USB drive or another machine with `rsync -a backups/
<destination>`.

## Restoring

```bash
./scripts/restore.sh backups/raahat-<timestamp>.dump --yes
```

Steps the script performs: verify the checksum, verify the archive, take a
safety backup of the current database, stop API and worker, drop and recreate
the database, restore, restore audio if present, start the API (which applies
any newer migrations) and the worker, run the health check.

Without `--yes` it refuses to run.

After a restore, browsers that were connected receive a *resync* signal from
the event stream (their last event number is ahead of the restored database)
and reload their data.

## Tested

On 2026-11-16, on this laptop, with test-fixture data in a scratch database:

1. Created an operation and an incident; stopped and started the whole stack
   with `dev-down.sh` / `dev-up.sh`: the incident was still there.
2. Backed up, created a second incident, restored: one incident remained,
   matching the backup; the audit hash chain verified (8 events). Restore took
   15 seconds.
3. `restore.sh` without `--yes` refused to run.

## Recovery scenarios

| Situation | Action |
|---|---|
| Laptop rebooted | Containers restart automatically. Reports queued for the worker are resumed; any report interrupted mid-processing is returned to the queue on worker start. |
| API or worker crashed | Docker restarts it. Check `docker compose logs api worker`. |
| Database corrupted or disk failed | Restore the latest good backup on a working machine (DEPLOYMENT_LOCAL.md, then `restore.sh`). Data entered after that backup is lost; re-enter it from paper or call logs. |
| Disk full | The health check warns below 10% free. Free space (old backups, `docker system prune` of unused images); PostgreSQL stops accepting writes when the disk is full. |
| Audit integrity alarm | *Activity log → Verify integrity* reports a broken chain if stored records were changed outside the application. Preserve the database as found (`backup.sh`) before investigating. |
