# Running the backend on the laptop

Target host: HP 15s-fr2xxx, Ubuntu 24.04, Intel i3-1125G4 (4 cores / 8 threads),
8 GB RAM, no discrete GPU. Everything below was run on this machine.

## Components

| Container | Image | Purpose | Exposure | Memory limit |
|---|---|---|---|---|
| `db` | postgis/postgis:16-3.4 | Database (data volume `raahat_pgdata`) | none (internal network only) | 768 MB |
| `api` | `raahat-backend:local` | HTTP API, event stream, migrations on start | `127.0.0.1:8000` | 512 MB |
| `worker` | `raahat-backend:local` | Voice transcription, channel report analysis, enrichment, alert polling | none | 384 MB |

Recorded audio is kept in the `raahat_audio` volume.

## Prerequisites

- Docker Engine with the compose plugin (tested: Docker 29.8, Compose 5.5).
- About 1 GB of disk for images, plus database growth (see RESOURCE_BUDGET.md).

## First start

```bash
cp .env.example .env
chmod 600 .env
# Edit .env:
#   POSTGRES_PASSWORD   python3 -c 'import secrets; print(secrets.token_urlsafe(24))'
#   RAAHAT_SECRET_KEY   python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
#   CORS_ALLOWED_ORIGINS  exact frontend origin(s), e.g. https://raahat-ops.vercel.app
./scripts/dev-up.sh
docker compose exec api raahat-entrypoint cli create-admin --username <name> --full-name "<Full Name>"
```

`dev-up.sh` refuses to start without the three required values, builds the
image, starts the containers, waits until they report healthy, and prints the
next steps. The API runs `alembic upgrade head` before it serves, so the schema
always matches the code.

Check the configuration without printing secrets:

```bash
docker compose exec api raahat-entrypoint cli check-config
```

## Everyday commands

| Task | Command |
|---|---|
| Start | `./scripts/dev-up.sh` (`--no-build` to skip the image build) |
| Stop (keep data) | `./scripts/dev-down.sh` |
| Stop and remove containers | `./scripts/dev-down.sh --remove` (volumes kept) |
| Health | `./scripts/health-check.sh` (add the public URL to check the tunnel too) |
| Logs | `docker compose logs -f --tail=100 api worker` |
| Migrations only | `docker compose run --rm api migrate` |
| Back up | `./scripts/backup.sh` |
| Restore | `./scripts/restore.sh backups/<file>.dump --yes` |
| Import landmarks | `docker compose exec api raahat-entrypoint cli import-landmarks --bbox 10.07,76.31,10.15,76.39` |
| Reset a user's password | `docker compose exec api raahat-entrypoint cli reset-password --username <name>` |

## Start on boot

All services use `restart: unless-stopped`, so they come back after a reboot
once Docker starts. Enable Docker at boot with `sudo systemctl enable docker`.

## Sleep and lid

A sleeping laptop serves nothing. While RAAHAT is in use, disable suspend on
lid close (`HandleLidSwitch=ignore` in `/etc/systemd/logind.conf`) and on
idle. The web app tells operators within seconds when the server stops
answering; see OPERATIONS.md.

## Running without Docker (development)

```bash
uv sync --extra dev
export DATABASE_URL=postgresql://<user>:<pass>@localhost:<port>/<db>
export ENVIRONMENT=development CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173
alembic upgrade head
python -m raahat.cli create-admin --username admin --full-name "Admin"
python -m raahat.serve           # API on 127.0.0.1:8000
python -m raahat.workers.main    # worker
```

In development an unset `RAAHAT_SECRET_KEY` is replaced by a random one per
process (sessions end on restart); in production the API refuses to start.

## The previous stack

The pre-redesign stack (compose project `raahat-platform`: containers
`raahat-db`, `raahat-api`, `raahat-worker`, `raahat-proxy`, `raahat-grafana`,
`raahat-prometheus`) may still be running on ports 8080, 3000 and 9090. It is
independent of this one: different project, network and volumes. Its data
(`raahat_postgres_data`) was left untouched.

- Stop it: `docker compose -p raahat-platform stop`
- Its database holds a seeded demo scenario. If you want to carry it over, the
  migrations upgrade it in place without data loss (tested on a copy):
  dump it with `pg_dump -Fc`, restore into the new stack with
  `scripts/restore.sh`, and the API applies the migrations on start.
