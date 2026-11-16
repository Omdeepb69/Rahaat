# RAAHAT — Architecture

This document has two parts: the audit of the repository as it was found on
2026-11-16 (Part A), and the architecture as built (Part B).
Part B describes the system as built on 2026-11-16. Open items are in `TASKS.md`.

---

## Part A — Audit of the repository as found

### A.1 What is in the repository

| Area | Location | Stack | Size |
|---|---|---|---|
| Backend API + workers | `src/raahat/` | Python 3.11, FastAPI, SQLAlchemy 2 (sync), Alembic, PostGIS 16-3.4 | ~19,500 lines, 3 migrations |
| React dashboard | `dashboard/` | Vite 8, React 19, TypeScript, react-router 7, Leaflet | ~6,700 lines |
| Legacy operator console | `operator_console/` | Vanilla JS + Leaflet from unpkg | ~2,700 lines |
| Citizen SOS portal | `citizen_portal/` | Static HTML/JS (voice note, GPS, in-browser "call") | ~2,300 lines |
| Offline field client | `field_app/` | Python + SQLite sync queue | ~500 lines |
| Synthetic benchmark | `evaluation/` | Seeded generator + metrics | 1,000 generated reports |
| Deployment | `compose.yaml`, `Dockerfile`, `deployment/` | db, api, worker, nginx, Prometheus, Grafana | 6 containers |
| Tests | `tests/` | pytest | 475 tests |

The backend follows a layered layout (`domain/`, `application/`, `infrastructure/`,
`adapters/`, `api/`, `workers/`, `policies/`).

### A.2 What works (retained)

- **Report ingestion** (`application/ingestion`): idempotent on
  `(disaster_id, idempotency_key)`, writes the report and an outbox row in one
  transaction, handles the unique-violation race.
- **Deterministic triage policy** (`policies/triage.py`): explicit rules, no
  weights, "unknown never lowers priority", returns the reasons that fired.
- **Evidence extraction and contradiction detection** (`domain/evidence`).
- **Duplicate matching** (`application/incident_resolution`): signal-based
  candidate matching, links held for review, reversible merge/unmerge with a
  merge-event record.
- **Landmark gazetteer** (`infrastructure/database/repositories/landmark.py`):
  PostGIS `geography` points, GiST index, `pg_trgm` fuzzy name search.
- **Audit trail** (`infrastructure/audit`): per-entity SHA-256 hash chain with a
  verifier.
- **Transactional outbox** with leases, fencing tokens, retry and dead-lettering.
- **Schema**: sensible constraints, GiST indexes on every spatial column.

### A.3 What is broken or unsafe

| # | Finding | Evidence |
|---|---|---|
| 1 | **The API is unauthenticated.** No route except `/auth/me` checks the JWT. `GET /api/v1/incidents` and `/reports` return caller data to anyone. | `curl` without credentials returns 200 |
| 2 | **Identity is a client-supplied header.** Mutating routes accept any UUID in `X-Dispatcher-Id` as the actor, and every login is issued the same dispatcher id `…0001`. Audit records therefore cannot identify a person. | `api/dependencies.py`, `api/routes/auth.py` |
| 3 | **Passwords are derived from a public formula** (`{State}{District}{YEAR}#`) and the formula is served by `GET /auth/credential-format`. Anyone can log in as any district. | Logged in with `KeralaSEOC2026#` |
| 4 | **JWT secret has a hardcoded default** used when `RAAHAT_JWT_SECRET` is unset, which it is in `.env`. | `auth.py` |
| 5 | **CORS is `*` with credentials allowed.** | `api/app.py` |
| 6 | **Health check is a constant.** `/healthz`, `/health/live` and `/health/ready` all return `{"status":"ok"}` without touching the database. | `api/app.py` |
| 7 | **Realtime does not work across processes.** The SSE broadcaster is an in-process set of queues; the API runs two uvicorn workers and events are produced in a third process (the worker). The stream also returns 401 to the dashboard, which silently falls back to a "POLLING" badge. No replay on reconnect. | `application/events/broadcaster.py`, browser console |
| 8 | **The location resolver invents coordinates.** When nothing matches it returns a hypothesis at a hardcoded point in Pune (18.5204, 73.8567), or the centre of a bounding box, labelled as an estimate. | `application/location/resolver.py::_handle_unresolved` |
| 9 | **Providers fail silently into fabricated output.** Timbre TTS returns `[TIMBRE_MOCK:…]` bytes as audio when no key is set; the LLM clients fall back to a rule engine while reporting as the LLM; Prisma returns an empty transcript on error. | `infrastructure/speech/timbre.py`, `infrastructure/llm/*.py` |
| 10 | **Telephony is a stub that pretends to dial.** The worker runs a callback scheduler against `StubTelephonyProvider`. | `infrastructure/telephony`, `workers/main.py` |
| 11 | **State change and audit are not atomic.** Services open their own sessions; `audit_repo.record_event` commits separately from the change it describes. | `application/dispatch/service.py` and others |
| 12 | **Dashboard deep links 404.** Only `/dashboard/` is served; `/dashboard/map`, `/dashboard/login` etc. return raw JSON `{"detail":"Not Found"}` on load or refresh. | Headless Chrome capture |
| 13 | **Dashboard layout overflows at 1440px**, uses emoji as icons, and shows "Location Pending Disambiguation" for every incident. | Screenshot |
| 14 | **N+1 data loading.** The dashboard fetches every incident's detail individually to get coordinates, then filters by jurisdiction in the browser. | `dashboard/src/services/raahatService.ts` |
| 15 | **Legacy console's map is blocked** by a wrong SRI hash on the Leaflet script. | Browser console |

### A.4 What is simulation or demonstration

- `api/routes/demo.py`, `scripts/seed_demo_data.py`, `scripts/demo_run.py`,
  `scripts/generate_contest_audio.py`, `demo/scenario.json`: scenario runner and
  seeded disaster, hand-typed landmark coordinates and invented rescue units.
- `domain/geospatial/simulate.py`, `asr_sim.py`: simulated caller dialogues.
- `infrastructure/speech/mock.py`: mock recognizer wired as a runtime fallback.
- `DEMO_MODE` branch in `require_dispatcher_id`.
- The live database volume holds one seeded disaster ("Kerala Floods 2018 —
  Raahat Demo") with 16 reports, 9 incidents and 10 invented resources.
- `evaluation/`: a seeded synthetic benchmark. Legitimate as an evaluation
  fixture, but the README presents the platform's test count and capabilities
  without stating that the data is generated.

### A.5 What is duplicated or unnecessarily complicated

- Two operator frontends (`operator_console/`, `dashboard/`) implement the same
  screens against the same API.
- Most services carry two code paths, in-memory and PostgreSQL, selected by
  whether a session factory was passed. The in-memory path exists only for
  unit tests and doubles the surface to maintain.
- `application/workflow/audio_triage.py` (1,075 lines) does transcription,
  regex fact extraction, location resolution, persistence, deduplication,
  triage, dispatch proposal and broadcasting in one class.
- Prometheus and Grafana run by default (≈80 MB RSS) on an 8 GB host for a
  metrics page nobody reads during operations.
- nginx sits in front of a single upstream only to proxy it.

### A.6 Test baseline

On a fresh PostGIS database migrated to head, with the shell's stray ROS pytest
plugin disabled: **471 passed, 4 failed**. The README's "457 passing" badge does
not match. The four failures: two need demo audio that is not in the repository,
one asserts that certain documentation files exist, one asserts a jurisdiction
list shape. There is no `conftest.py`; each test file hardcodes a database URL.

---

## Part B — Architecture as built

### B.1 Shape

A modular monolith: one Python package, one PostgreSQL/PostGIS database, two
process types, and a static web app.

```
Browser ─ static SPA (web/, Vercel) ─┐
                                     │ HTTPS, Authorization: Bearer
                                     ▼
                Tailscale Funnel (TLS) → 127.0.0.1:8000
                                     │
        raahat api  (python -m raahat.serve, 1 process)
          REST /api/v1 · SSE /api/v1/events/stream · /health/*
          event listener thread: LISTEN raahat_events
                                     │
        PostgreSQL 16 + PostGIS 3.4  (no published port)
          audit_events = hash-chained event log (BIGSERIAL seq, NOTIFY trigger)
          reports table = work queue (FOR UPDATE SKIP LOCKED)
                                     ▲
        raahat worker (python -m raahat.workers.main, 1 process)
          transcription · channel-report analysis · enrichment · CAP alert polling
          heartbeat row each tick
```

No Redis, broker or reverse proxy. PostgreSQL is the queue, the event log and
the notifier.

### B.2 Modules

| Module | Responsibility |
|---|---|
| `raahat.config` | Typed settings; refuses production start with a weak secret or wildcard CORS |
| `raahat.security` | scrypt passwords, JWT access tokens, role→permission map, sliding-window rate limiter |
| `raahat.api` | App factory (request id, size limits, access log, error shape, CORS), `current_user`/`require()`, routers: auth, users, disasters, reports, public, incidents, resources, dispatch, events, alerts, audit, system |
| `raahat.application.identity` | Accounts, lockout, password changes, last-admin protection |
| `raahat.application.intake` | Operator and channel report creation; the analysis pipeline (transcribe → analyse → enrich) recording a processing run per stage |
| `raahat.application.ai` | Language identification, rule extraction, model translation/extraction with quote grounding, provider construction |
| `raahat.application.incident_resolution` | Duplicate candidate scoring (SQL-prefiltered), resolution decisions, reviewed merge/reject/relate/unmerge |
| `raahat.application.incidents` | Incident read models (single-query lists), fact provenance sheet, lifecycle changes, corrections |
| `raahat.application.location` | Landmark gazetteer search, location hypotheses with provenance, confirmation, best-position rule |
| `raahat.application.triage` | Facts from evidence, operator overrides, deterministic policy, triage record |
| `raahat.application.resources` | Resource register, availability, timestamped positions |
| `raahat.application.dispatch` | Priority score, recommendation engine, multi-incident plan, decisions, assignment progress |
| `raahat.application.events` | Event hub (LISTEN), SSE subscription with replay |
| `raahat.application.alerts` | CAP feed import and listing |
| `raahat.application.system` | Health probes, integration status |
| `raahat.domain` | Lifecycle state machine, triage facts, evidence model and contradiction detection, enums |
| `raahat.policies` | Deterministic triage rules (retained from the original code) |
| `raahat.infrastructure` | SQLAlchemy models, Alembic migrations, audit chain and verifier, provider adapters (Gnani Prisma, OpenAI-compatible/Evon, Gemini, Nominatim, OSRM, Overpass, CAP) |
| `raahat.workers` | Worker loop with heartbeat, crash recovery, bounded batches |
| `raahat.cli` | `create-admin`, `reset-password`, `import-landmarks`, `check-config` |

### B.3 Transactions and events

One session per request. A command changes state and appends audit records in
the same transaction (`append_audit`), then the route commits once. Audit
appends take a transaction-scoped advisory lock, so sequence order equals
commit order; an `AFTER INSERT` trigger issues `NOTIFY raahat_events`.

The SSE endpoint sends `ready` (with the current sequence and a `resync` flag),
then every committed change after the client's `Last-Event-ID` (up to 500;
beyond that the client is told to resync), then live changes, with a heartbeat
every 15 s. Subscribers wake on notification and re-check every 5 s regardless,
so a lost notification costs latency, not data.

### B.4 Data model (main tables)

| Table | Notes |
|---|---|
| `users` | role check constraint, `token_version` for revocation, lockout fields |
| `disasters` | an "operation"; status, map focus |
| `reports` | immutable `original_text`, `original_language` + source, `translated_text` + provider, caller fields, processing status/error |
| `processing_runs` | provider, model, stage, outcome, duration per report |
| `evidence_items` / `evidence_spans` | each extracted fact with extractor, model and source quote |
| `incidents` | `reference` (INC-000001), lifecycle status (check constraint), category, priority, `severity_facts` (extracted), `fact_overrides` (operator), `triage` record, denormalised best position with source/status/uncertainty, merge pointer |
| `location_hypotheses` | every position candidate with `source` (caller_gps/operator/geocoder/landmark), detail, score, radius, confirmation |
| `incident_links` | duplicate candidates with signals and review record |
| `entity_merge_events` | reversible merges |
| `resources` | callsign (unique per operation), capabilities, status, position + source + timestamp (constraint: no position without time) |
| `assignments` | at most one approved assignment per resource (partial unique index); stage |
| `dispatch_decisions` | approved/rejected, chosen vs recommended, full recommendation snapshot, reason |
| `audit_events` | hash chain per entity, global `seq`, incident and operation keys |
| `landmarks` | name trigram index, source/external id (OSM) |
| `external_observations` | CAP alerts with provenance |
| `worker_heartbeats`, `integration_checks` | liveness and last real provider outcome |

Migrations: `8c1d0a000001` (identity, event log, bookkeeping) and
`8c1d0a000002` (domain model). Both upgrade existing data in place and
downgrade cleanly; tested on a copy of the original demo database.

### B.5 Security

See NETWORK_CONNECTIVITY.md. Summary: bearer tokens re-validated against the
user row on every request; per-route permissions; caller details redacted for
roles without `pii:read`; exact-origin CORS; rate limits; size limits; no
default accounts; secrets only in the host `.env`.

### B.6 Frontend

`web/`: Vite, React 19, TypeScript (strict), React Router, TanStack Query,
Leaflet (lazy-loaded), lucide icons, self-hosted IBM Plex and Noto fonts.

- `lib/api.ts` is the only HTTP client: base URL from `VITE_API_BASE_URL`,
  timeouts, GET-only retries, typed errors, connection reporting.
- `lib/realtime.ts`: fetch-based SSE (header auth), `Last-Event-ID` replay,
  resync, watchdog; `lib/live.tsx` turns changes into coalesced query
  invalidations.
- `lib/connection.ts`: readiness probe and request outcomes drive the
  offline banner and data-age labels.
- Features: operations board, intake, incidents, incident page, reports,
  dispatch, resources, official alerts, activity log, system status, users,
  operations setup, public report and ticket pages.
- Design system: `styles/tokens.css` (light and dark), `components/ui.tsx`
  (buttons, fields, badges, panels, dialogs, toasts, tabs, states).
