# RAAHAT

Emergency reporting, incident intelligence and rescue-resource coordination for
India's disaster control rooms (floods, landslides, cyclones).

- **For the public:** a reporting site where anyone can report an emergency
  **by voice, in their own language**. An assistant asks a few short spoken
  questions, understands the answers and sends the report straight to the
  control room for the caller's district.
- **For control rooms:** a live operations dashboard. Each state and district
  control room signs in with **State → District → Password** and sees only
  its own area.

RAAHAT is **decision support**. It records reports, organises them into
incidents, shows where they are and what is known, and recommends which
resource to send. A person approves every dispatch. RAAHAT does not contact
emergency services or field teams, and it does not replace 112.

---

## Contents

1. [What it does](#what-it-does)
2. [Public reporting site and voice calls](#public-reporting-site-and-voice-calls)
3. [Jurisdictions, accounts and isolation](#jurisdictions-accounts-and-isolation)
4. [Architecture](#architecture)
5. [Repository layout](#repository-layout)
6. [Quick start](#quick-start)
7. [Configuration](#configuration)
8. [Running on the laptop (Docker)](#running-on-the-laptop-docker)
9. [Public access: HTTPS tunnel](#public-access-https-tunnel)
10. [Deploying the web app (Vercel)](#deploying-the-web-app-vercel)
11. [Day-to-day operation](#day-to-day-operation)
12. [Backup and recovery](#backup-and-recovery)
13. [Security](#security)
14. [Testing](#testing)
15. [Measured performance](#measured-performance)
16. [Design decisions](#design-decisions)
17. [Known limits](#known-limits)
18. [Licence and data sources](#licence-and-data-sources)

---

## What it does

| Area | What happens |
|---|---|
| Public reporting | A landing page (`/`) and a guided voice call (`/report`). Questions are spoken by Gnani Timbre in 10 languages; answers are transcribed by Gnani Prisma with automatic language detection. Typing works at every step. The caller gets a ticket and a status page. |
| Operator intake | Operators type reports in the caller's words and language. SMS and radio gateways submit through the API. Voice notes are transcribed when speech is configured. The original text is never altered. |
| Understanding | Language identified from script and vocabulary. Rule-based extraction of people, trapped, medical need, water level and depth, hazards, needs and place mentions, each with the words it came from. With a model configured (Gnani Evon or Gemini), translation to English and model extraction; model output is kept only when its supporting quote is found in the report. |
| Incidents | Every report becomes or joins an incident, starting **unverified**. Lifecycle: unverified → under review → verified → assigned → response active → resolved → closed (or duplicate). Transitions are validated; operator corrections are stored beside extracted values with name and time. |
| Priority | Deterministic triage (critical / urgent / standard / low; "not assessed" ranks above standard) and an explicit priority score for verified incidents awaiting a resource. |
| Duplicates | Candidates from phone, distance, people named, shared facts and contradictions. Never merged automatically; merges are reviewed and reversible. |
| Location | Candidates from the caller's device GPS, operator entry, an OpenStreetMap landmark gazetteer and a geocoder (Nominatim, on request), each labelled with source and uncertainty. Nothing becomes the position until confirmed; no coordinates are invented. |
| Dispatch | Resources with capabilities, capacity and timestamped positions. Recommendations rank feasible resources on capability, distance (road distance with OSRM, otherwise labelled straight-line), capacity and position age, showing every factor. Approval records what was recommended and why a different choice was made. |
| Live operation | Every change is an audited, hash-chained event, streamed to browsers (SSE) and replayed after reconnect. Official CAP alerts (NDMA SACHET) are imported for reference. |
| Honesty | System status reflects real checks. The interface says when the server is unreachable and how old the data on screen is. |

---

## Public reporting site and voice calls

### Pages

| Path | Page |
|---|---|
| `/` | Landing page: what the service does, the languages, what happens to a report, FAQ, "Report an emergency" and "Authority login" |
| `/report` | The guided voice call |
| `/report/status/:ticket` | Status of a submitted report (coarse stages only; nothing about other reports or responders) |
| `/login` | Authority sign-in |
| `/control/...` | Control room dashboard (not indexed by search engines) |

### How a call works

1. The caller chooses their **state and district** (this decides which control
   room receives the report) and may share their phone's location.
2. The assistant speaks an opening in Hindi and English inviting the caller to
   speak in any language, then asks what happened.
3. The browser records the answer as 16 kHz WAV and detects the end of speech
   automatically (the caller can also press "I've finished speaking").
4. **Gnani Prisma** transcribes it with automatic language identification.
   From then on every question is asked in that language. If the language is
   not recognised, the call continues in **Hindi**. The caller can pick a
   language at any time.
5. The same deterministic rules used on every report pick facts out of each
   answer, so questions already answered are skipped. Example: "five of us are
   trapped on the roof" fills both *people* and *danger*.
6. Questions: what happened → where exactly → how many people → anyone hurt,
   trapped or in danger → callback number → name (optional).
7. When the interview ends (or the caller presses "Send report now", or leaves
   the page), the call becomes **one report** containing:
   - every answer in the caller's own words, with the questions asked;
   - the recordings joined into one audio file;
   - GPS position if shared;
   - structured fields: place, people count, phone, name.
8. The worker analyses it like any other report. It appears **live** on the
   board of that district's control room (and its state and national views),
   with the full question-and-answer transcript and playable recording.

A call the caller abandons part-way is sent automatically by the worker three
minutes after the last answer. A call with nothing said is discarded.

### Routing

A call for a district goes to:

1. the newest **active operation for that district**; otherwise
2. the newest active **state-wide** operation; otherwise
3. a **standing operation** "‹District›: public emergency reports", created
   on first use.

Open a named operation for the district (for example "Periyar flood response")
and new calls go there.

### Languages

Hindi, English, Bengali, Marathi, Telugu, Tamil, Gujarati, Kannada, Malayalam,
Punjabi. Prompts are fixed sentences, synthesised once by Gnani Timbre and
cached on disk; pre-generate them after deployment:

```bash
docker compose exec api raahat-entrypoint cli warm-voice-prompts   # 82 clips
```

---

## Jurisdictions, accounts and isolation

States and districts come from the Government of India's **Local Government
Directory** (LGD codes; 36 states and union territories, 790 districts), bundled
in `src/raahat/data/jurisdictions.json`.

| Account | Signs in with | Sees | Can |
|---|---|---|---|
| National administration | "National administration" + password | Every operation in every state | Everything, including issuing control room passwords |
| State control room | State + "state control room" + password | Every operation in its state | Run the response in its state; open operations for the state or any of its districts |
| District control room | State + district + password | Only operations in its district | Run the response in its district |

**Isolation is enforced by the server**, not the interface:

- every operation carries a state and district;
- every route that reads or changes an incident, report, resource, assignment
  or operation checks it against the caller's jurisdiction and answers
  **404 Not found** outside it (so existence is not revealed);
- list endpoints require an operation for non-national accounts;
- the activity log and the live event stream are filtered to visible
  operations.

An Odisha account asking for a Kerala incident by its reference gets "not
found"; this is covered by tests and was checked on the running system.

### Passwords

Passwords are **random per account** (four groups of four characters, about
91 bits), never derived from the state or district, stored only as scrypt
hashes.

```bash
# Create national, every state and every district account; passwords printed once as CSV
docker compose exec -T api raahat-entrypoint cli provision-accounts --all > secrets/control-room-passwords.csv
chmod 600 secrets/control-room-passwords.csv

# Only some states (LGD codes, e.g. 32 Kerala, 21 Odisha), state accounts only, or re-key
docker compose exec -T api raahat-entrypoint cli provision-accounts --states 32,21
docker compose exec -T api raahat-entrypoint cli provision-accounts --states 32 --no-districts
docker compose exec -T api raahat-entrypoint cli provision-accounts --states 32 --reset
```

`secrets/` is git-ignored. Hand each control room only its own line through a
trusted channel. The national administration can issue a new password for any
control room, or suspend one, on the **Control room accounts** page. Issuing a
new password signs out everyone using the old one.

### Permissions

| Role | Permissions |
|---|---|
| National administration (`admin`) | All |
| Control room (`control_room`) | All except managing accounts and system settings |
| Operator / dispatcher / resource coordinator / observer | Individual roles kept for future per-person accounts |

Caller names and numbers are visible only to roles with `pii:read`; for other
roles they are redacted, including the phone and name answers in a call
transcript.

---

## Architecture

A modular monolith: one Python package, one PostgreSQL/PostGIS database, two
process types and a static web app.

```
Browser ─ static SPA (web/, Vercel) ─┐
                                     │ HTTPS, Authorization: Bearer
                                     ▼
                Tailscale Funnel (TLS) → 127.0.0.1:8000
                                     │
        raahat api  (python -m raahat.serve, 1 process)
          REST /api/v1 · SSE /api/v1/events/stream · /health/*
          event listener thread: LISTEN raahat_events
                                     │                    Gnani Prisma (speech-to-text)
        PostgreSQL 16 + PostGIS 3.4  (no published port)  Gnani Timbre (text-to-speech)
          audit_events = hash-chained event log            Nominatim · OSRM · Overpass
          reports table = work queue (SKIP LOCKED)          NDMA SACHET CAP feed
                                     ▲
        raahat worker (python -m raahat.workers.main, 1 process)
          transcription · report analysis · enrichment · CAP polling
          abandoned voice calls · heartbeat
```

No Redis, broker or reverse proxy: PostgreSQL is the queue, the event log and
the notifier.

### Modules

| Module | Responsibility |
|---|---|
| `raahat.config` | Typed settings; refuses a production start with a weak secret or wildcard CORS |
| `raahat.security` | scrypt passwords, JWT access tokens, roles and permissions, jurisdictions (LGD), rate limiter |
| `raahat.api` | App factory (request id, size limits, access log, error shape, CORS), `current_user`/`require()`, jurisdiction enforcement (`api/scope.py`), routers |
| `raahat.application.identity` | Accounts, lockout, password changes, jurisdiction account provisioning |
| `raahat.application.voicecall` | Call script in 10 languages, interview logic, call sessions, routing, report creation |
| `raahat.application.intake` | Operator and channel report creation; analysis pipeline (transcribe → analyse → enrich) |
| `raahat.application.ai` | Language identification, rule extraction, model translation/extraction with quote grounding |
| `raahat.application.incident_resolution` | Duplicate scoring (SQL-prefiltered), reviewed merge/reject/relate/unmerge |
| `raahat.application.incidents` | Read models, fact provenance, lifecycle changes, corrections |
| `raahat.application.location` | Landmark search, location hypotheses with provenance, confirmation |
| `raahat.application.triage` | Facts from evidence, overrides, deterministic policy |
| `raahat.application.resources` / `dispatch` | Resource register and positions; priority score, recommendations, plan, decisions, progress |
| `raahat.application.events` | Event hub (LISTEN) and SSE subscription with replay and jurisdiction filtering |
| `raahat.application.alerts` / `system` | CAP import; health probes and integration status |
| `raahat.infrastructure` | SQLAlchemy models, Alembic migrations, audit chain and verifier, provider adapters |
| `raahat.workers` | Worker loop with heartbeat, crash recovery, bounded batches |
| `raahat.cli` | `provision-accounts`, `warm-voice-prompts`, `create-admin`, `reset-password`, `import-landmarks`, `check-config` |

### Transactions and events

One session per request. A command changes state and appends audit records in
the same transaction, then commits once. Audit appends take a transaction-scoped
advisory lock, so sequence order equals commit order; an `AFTER INSERT` trigger
issues `NOTIFY raahat_events`. The SSE endpoint sends `ready` (current sequence
and a `resync` flag), then every change after the client's `Last-Event-ID` (up
to 500, beyond that a resync), then live changes, with a heartbeat every 15 s.

### Main tables

| Table | Notes |
|---|---|
| `users` | role, jurisdiction (`state_code`, `district_code`), `token_version` for revocation, lockout fields |
| `disasters` | an "operation": status, map focus, jurisdiction, `is_standing` |
| `voice_calls` | public call sessions: hashed token, district, language and how it was set, answers, position, resulting report |
| `reports` | immutable `original_text`, language and its source, translation, caller fields, processing status |
| `processing_runs`, `evidence_items`, `evidence_spans` | each stage and extracted fact with provider and source quote |
| `incidents` | reference (INC-000001), lifecycle status, priority, extracted facts, operator overrides, triage, best position with source |
| `location_hypotheses`, `incident_links`, `entity_merge_events` | position candidates; duplicate candidates; reversible merges |
| `resources`, `assignments`, `dispatch_decisions` | register; at most one approved assignment per resource; decisions with snapshot and reason |
| `audit_events` | hash chain per entity, global `seq`, incident and operation keys |
| `landmarks`, `external_observations`, `worker_heartbeats`, `integration_checks` | gazetteer, CAP alerts, liveness, provider outcomes |

### Frontend

`web/`: Vite 8, React 19, TypeScript (strict), React Router 7, TanStack Query 5,
Leaflet (lazy-loaded), lucide icons.

- Design system in `styles/tokens.css`: OKLCH colour tokens with a separately
  tuned dark theme and a per-browser theme switch, self-hosted variable fonts
  (Public Sans, JetBrains Mono, Noto Sans for 8 Indic scripts).
- `lib/api.ts` is the only HTTP client (base URL from `VITE_API_BASE_URL`).
- `lib/realtime.ts`: fetch-based SSE with `Last-Event-ID` replay and watchdog.
- `features/public/`: landing, call and ticket pages; `voice/` holds the
  browser audio engine (AudioWorklet capture, end-of-speech detection, WAV
  encoding, prompt playback).

---

## Repository layout

```
src/raahat/          Python package (API, worker, domain, providers)
  api/               routes, auth and jurisdiction dependencies, app factory
  application/       intake, voicecall, incidents, location, dispatch, alerts, identity, system
  data/              jurisdictions.json (LGD states and districts)
  domain/ policies/  lifecycle, evidence, triage rules
  infrastructure/    database models and migrations, provider adapters, audit chain
  workers/           background worker
web/                 web app (Vite, React, TypeScript)
tests/               backend tests (pytest, real PostGIS)
evaluation/          synthetic benchmark harness (generated data only)
scripts/             dev-up, dev-down, health-check, backup, restore, tunnel-up
compose.yaml         database, API, worker for one host
```

---

## Quick start

```bash
cp .env.example .env && chmod 600 .env
#   POSTGRES_PASSWORD     python3 -c 'import secrets; print(secrets.token_urlsafe(24))'
#   RAAHAT_SECRET_KEY     python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
#   CORS_ALLOWED_ORIGINS  exact web origin(s), e.g. http://127.0.0.1:4173
#   GNANI_API_KEY_TTS_STT speech key (for voice calls and voice notes)
#   PUBLIC_INTAKE_ENABLED=true   to open the public reporting site
./scripts/dev-up.sh                     # builds, starts, migrates, waits for health

mkdir -p secrets && chmod 700 secrets
docker compose exec -T api raahat-entrypoint cli provision-accounts --all > secrets/control-room-passwords.csv
docker compose exec api raahat-entrypoint cli warm-voice-prompts

cd web
VITE_API_BASE_URL=http://127.0.0.1:8000 npm ci
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run build
npx vite preview --host 127.0.0.1 --port 4173     # http://127.0.0.1:4173
```

For development use `npm run dev` (port 5173) with `web/.env.local` containing
`VITE_API_BASE_URL=http://127.0.0.1:8000`, and add that origin to
`CORS_ALLOWED_ORIGINS`.

There is no sample data. Sign in, open an operation (or let the first public
call create a standing one), register resources and take reports.

---

## Configuration

All settings are environment variables; `.env.example` documents every one.
The most important:

| Setting | Purpose |
|---|---|
| `POSTGRES_PASSWORD`, `RAAHAT_SECRET_KEY` | Required. The API refuses to start in production without a strong secret. |
| `CORS_ALLOWED_ORIGINS` | Exact web origins; `*` is rejected. |
| `PUBLIC_INTAKE_ENABLED` | Opens `/api/v1/public` (voice calls, ticket status). Off by default. |
| `GNANI_API_KEY_TTS_STT` | Gnani key for Prisma (speech-to-text) and Timbre (text-to-speech). Without it audio is stored and flagged as untranscribed; nothing is invented. |
| `TIMBRE_MODEL`, `TIMBRE_VOICE` | Voice for the call (default `timbre-v3.0`, `Shivani`). |
| `VOICE_CALL_RATE_PER_MINUTE` | Requests per minute per address during a call (default 90). |
| `LLM_PROVIDER` | `none`, `evon` or `gemini` for translation and model extraction. |
| `GEOCODER_PROVIDER`, `ROUTING_PROVIDER`, `OSRM_BASE_URL` | Optional Nominatim geocoding and OSRM road routing. |
| `CAP_ALERT_FEED_URL` | Official alert feed, e.g. NDMA SACHET RSS for a state. |
| `TRUST_FORWARDED_HEADERS` | Honour `X-Forwarded-For` from the local tunnel agent only. |

Check without printing secrets: `docker compose exec api raahat-entrypoint cli check-config`.

Web build: `VITE_API_BASE_URL` (required, HTTPS except for localhost; the build
fails otherwise), optional `VITE_MAP_TILE_URL` and `VITE_MAP_ATTRIBUTION`.
Everything prefixed `VITE_` is public; never put a key in one.

---

## Running on the laptop (Docker)

Target host: Intel i3-1125G4, 8 GB RAM, Ubuntu 24.04, no GPU.

| Container | Purpose | Exposure | Memory limit |
|---|---|---|---|
| `db` (postgis/postgis:16-3.4) | Database, volume `raahat_pgdata` | none (internal network) | 768 MB |
| `api` | HTTP API, event stream, migrations on start | `127.0.0.1:8000` | 512 MB |
| `worker` | Transcription, analysis, enrichment, alerts, abandoned calls | none | 384 MB |

Recordings and cached prompts live in the `raahat_audio` volume.

| Task | Command |
|---|---|
| Start | `./scripts/dev-up.sh` (`--no-build` to skip the build) |
| Stop (keep data) | `./scripts/dev-down.sh` (`--remove` to remove containers; volumes kept) |
| Health | `./scripts/health-check.sh [https://public-url]` |
| Logs | `docker compose logs -f --tail=100 api worker` |
| Migrations only | `docker compose run --rm api migrate` |
| Import landmarks | `docker compose exec api raahat-entrypoint cli import-landmarks --bbox SOUTH,WEST,NORTH,EAST` |

Containers use `restart: unless-stopped`; enable Docker at boot
(`sudo systemctl enable docker`). A sleeping laptop serves nothing: disable
suspend on lid close (`HandleLidSwitch=ignore` in `/etc/systemd/logind.conf`)
while RAAHAT is in use.

Without Docker (development):

```bash
uv sync --extra dev
export DATABASE_URL=postgresql://<user>:<pass>@localhost:<port>/<db> ENVIRONMENT=development
alembic upgrade head
python -m raahat.serve           # API on 127.0.0.1:8000
python -m raahat.workers.main    # worker
```

---

## Public access: HTTPS tunnel

```
Browser ──HTTPS──> Vercel (static files only)
Browser ──HTTPS──> https://<machine>.<tailnet>.ts.net  (Tailscale Funnel, TLS on the laptop)
                        ▼
                   127.0.0.1:8000 api ── internal network ── db, worker
```

Tailscale Funnel gives a stable `*.ts.net` HTTPS name without owning a domain
and supports long-lived SSE connections; Cloudflare quick tunnels have random
names and do not support SSE.

```bash
sudo tailscale up                 # once: log in
# Tailscale admin console: enable HTTPS certificates and allow Funnel for this device
./scripts/tunnel-up.sh            # publish 127.0.0.1:8000 on :443  (--off to stop)
./scripts/health-check.sh https://<machine>.<tailnet>.ts.net
```

Only `127.0.0.1:8000` is published on the host; PostgreSQL has no published
port. Starting the tunnel exposes the API to the internet; protection is in the
API (see [Security](#security)).

---

## Deploying the web app (Vercel)

1. Import the repository in Vercel; set **Root Directory** to `web`.
   `web/vercel.json` sets the framework, SPA rewrites and security headers.
2. Environment variable `VITE_API_BASE_URL` = the tunnel's HTTPS address (no
   trailing slash).
3. Deploy, then add the deployment's exact origin to `CORS_ALLOWED_ORIGINS` on
   the laptop and restart the API (`docker compose up -d api`).

Headers from `vercel.json`: a Content-Security-Policy (scripts and fonts from
the site only, network requests to HTTPS origins, no framing), HSTS, `nosniff`,
`no-referrer`, and a Permissions-Policy that allows the **microphone and
geolocation for the site itself only** (needed for voice calls). `/control`
and `/login` are sent with `X-Robots-Tag: noindex`.

Any static host works: `VITE_API_BASE_URL=https://<api> npm run build`, then
serve `web/dist` with a fallback to `index.html`.

---

## Day-to-day operation

**Before a shift:** `./scripts/health-check.sh`, then *System status* in the
dashboard: database, worker, event stream, speech and alert feed should be
operational.

**When something fails**, the dashboard says so: "Server unreachable" banner
within about 6 s, data-age labels on stale lists, a warning when the worker
heartbeat stops, and per-integration status (last real outcome, not a guess).
Missed changes are replayed on reconnect.

**Running an operation:**

- open an operation for a district or state (*Operations setup*); public calls
  for that district then go to it;
- verify incidents, confirm locations, review duplicates;
- dispatch only verified incidents; approval records the recommendation and
  any reason for a different choice;
- close the operation when finished. Records are kept; it stops accepting
  reports.

**Monitoring:** `docker stats`, `docker compose logs`, the health check (warns
below 10% free disk and 500 MB free memory) and *Activity log → Verify
integrity* for the audit chain.

---

## Backup and recovery

| Data | Where | How |
|---|---|---|
| Database (reports, incidents, audit trail, accounts, resources, calls, landmarks, alerts) | volume `raahat_pgdata` | `pg_dump --format=custom` while running |
| Recordings and prompt cache | volume `raahat_audio` | tar.gz |
| `.env` and `secrets/` | host | **not** backed up by the script; keep them in a password manager |

```bash
./scripts/backup.sh                    # backups/raahat-<UTC>.dump (+ .sha256, .audio.tar.gz); KEEP=30 for retention
./scripts/restore.sh backups/raahat-<UTC>.dump --yes
```

Restore verifies the checksum and archive, takes a safety backup, stops API and
worker, restores, applies newer migrations and runs the health check; without
`--yes` it refuses. Connected browsers receive a *resync* and reload.

Backups contain callers' names and numbers: `backups/` is mode 700 and
git-ignored; copy them only to encrypted storage. Schedule hourly during an
operation:

```
0 * * * * cd /path/to/rahaat && ./scripts/backup.sh >> backups/backup.log 2>&1
```

| Situation | Action |
|---|---|
| Laptop rebooted | Containers restart; interrupted reports return to the worker queue. |
| API or worker crashed | Docker restarts it; check the logs. |
| Database or disk lost | Restore the latest backup on a working machine. |
| Disk full | Free space; PostgreSQL stops accepting writes when full. |
| Audit integrity alarm | Back up the database as found before investigating. |

Tested: stop/start keeps data; backup → change → restore returns to the backup
with a valid audit chain (restore took 15 s).

---

## Security

| Control | Setting |
|---|---|
| Authentication | Bearer access tokens (30 min, refreshed while active; 12 h maximum session), re-validated against the account on every request; revoked on password change or suspension. |
| Authorization | Permissions per route, plus jurisdiction checks on every operational route and the event stream. |
| Passwords | Random per account, scrypt hashes, lockout after 5 failures for 15 minutes. No default accounts. |
| Public endpoints | Rate limited per address; a call is bound to a secret token (stored as a hash); uploads limited to 3 MB per answer. |
| CORS | Exact origins only; no cookies are used. |
| Rate limits | Sign-in 10/min per address; 600 requests/min per user; public 10/min per address; voice calls 90/min per address. |
| Request size | 1 MB JSON; 15 MB voice notes; 3 MB per call answer. |
| Errors | Uniform JSON with a request id; no stack traces; API docs disabled in production. |
| Secrets | Only in the host `.env` and `secrets/`, both git-ignored. |

---

## Testing

| Suite | Location | Count |
|---|---|---|
| Backend unit and integration | `tests/` | 345 |
| Frontend unit | `web/src/test/` | 11 |

```bash
docker run -d --name raahat-pg-test --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=raahat_test -p 127.0.0.1:54330:5432 postgis/postgis:16-3.4
uv sync --extra dev
uv run pytest                    # DATABASE_URL defaults to the container above
uv run ruff check src tests
cd web && npm test && npx tsc --noEmit -p . && npx oxlint src
```

API tests truncate the test database: **never point `DATABASE_URL` at
operational data when running tests.** If a ROS installation is on your Python
path, run pytest with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -p pytest_asyncio.plugin -p pytest_timeout`.

Covered: authentication, lockout, revocation, permissions, PII redaction, CORS,
size limits; jurisdiction sign-in and isolation (Odisha cannot see Kerala; a
district cannot see another district; operations open only inside the creator's
area; only national issues passwords); voice calls (language detection, Hindi
fallback, skipping answered questions, silence and failed transcription,
chosen language, early send, abandoned and empty calls, routing to an existing
or standing operation, prompt audio); intake, extraction, lifecycle, location,
duplicates, resources, recommendations, dispatch, events and replay, audit
chain, worker recovery, provider adapters, migrations and deployment
definition.

Checked in a real browser (Chrome) on the running stack:

- a full voice call with live Gnani: a spoken Malayalam answer was
  transcribed, the language was detected, and the assistant switched to
  Malayalam and skipped answered questions;
- the incident appeared live on the Ernakulam board, with the transcript;
- Thrissur and Odisha accounts got "not found";
- axe accessibility checks are clean on every page, in light and dark;
- no horizontal overflow from 360 to 1920 px;
- keyboard path and reduced motion work.

Not verified: a physical phone with a real voice, a screen reader, Lighthouse,
and the live Vercel and Tailscale deployment.

---

## Measured performance

On the target laptop with the containerised stack:

| Measure | Result |
|---|---|
| Memory, idle / under load | ~230 MiB / ~310 MiB for all three containers |
| Enter a report (full analysis), 400 incidents in the operation | p50 363 ms, p95 482 ms |
| Incident list / detail / recommendation | ~10 ms / ~31 ms / ~5 ms |
| Change → delivered on an open event stream | under 1 s |
| Gnani Prisma transcription of a 4–6 s answer | 0.4–1.4 s |
| Gnani Timbre synthesis of a prompt (first time; cached after) | 1.4–2.1 s |
| Provisioning 827 accounts | 78 s |
| Server unreachable → banner / back → live | 5.8 s / 6.4 s |
| Web bundle | 109 KB gzip initial; map 45 KB and public pages 4–8 KB loaded on demand |

The API runs as a single process on purpose: rate limits and the event listener
are per process.

---

## Design decisions

- **Modular monolith on PostgreSQL** as queue, event log and notifier: one
  dependency to run and back up on an 8 GB laptop.
- **Audit-first:** every change is an appended, hash-chained event in the same
  transaction as the change; the live stream is read from it, so the screen and
  the record cannot disagree.
- **Unknown is a value:** missing facts are shown as unknown and rank above
  standard priority; nothing is defaulted or guessed.
- **Provenance everywhere:** every fact and position shows where it came from;
  model output is kept only with a quote found in the report.
- **Human approval for dispatch:** recommendations explain themselves; the
  system never commits a resource on its own.
- **Jurisdiction accounts with server-side isolation:** routing and visibility
  follow LGD state and district codes; out-of-area records are "not found".
  Shared accounts per control room mean the audit log records the control room,
  not the individual; per-person accounts can be added under the same model.
- **Own voice agent on Gnani Prisma and Timbre:** runs in any phone browser
  using only the provisioned speech key, keeps every answer verbatim, and needs
  no language model to conduct the interview.
- **Tailscale Funnel** for public access (stable HTTPS name, SSE support, no
  domain needed); **Vercel** for the static web app.

---

## Known limits

- Fact extraction rules are strongest in English, Hindi and Malayalam; in
  other languages questions may be asked even when already answered.
- Call prompt translations need review by native speakers.
- Konkani has no Prisma model and is usually identified as Hindi or Marathi;
  callers can type.
- The voice call runs in the browser; a dial-in phone number would need
  Gnani's hosted voice-agent service or a telephony provider.
- A local language model does not fit on the laptop; translation and model
  extraction are remote and optional.

---

## Licence and data sources

Apache 2.0.

- States and districts: Local Government Directory (lgdirectory.gov.in),
  Ministry of Panchayati Raj, Government Open Data License – India.
- Landmarks imported from OpenStreetMap: © OpenStreetMap contributors, ODbL.
- NDMA SACHET alerts are published as public domain.
- Speech: Gnani Prisma and Timbre via api.vachana.ai, under the operator's own
  account.
