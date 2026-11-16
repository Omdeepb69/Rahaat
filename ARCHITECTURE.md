# RAAHAT — Architecture

This document has two parts: the audit of the repository as it was found on
2026-11-16 (Part A), and the architecture the codebase is being moved to (Part B).
Part B is updated as the implementation lands; anything not yet built is tracked
in `TASKS.md`, not described here as if it existed.

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

## Part B — Target architecture

### B.1 Shape

A modular monolith. One Python package, one database, two process types.

```
Browser (static SPA on Vercel)
   │  HTTPS, Authorization: Bearer <access token>
   ▼
Public HTTPS endpoint (Tailscale Funnel)  ── terminates TLS, forwards to 127.0.0.1:8000
   ▼
raahat-api      FastAPI / uvicorn, bound to loopback
   │                REST under /api/v1, SSE at /api/v1/events/stream
   │                LISTEN on the `raahat_events` channel
   ▼
PostgreSQL 16 + PostGIS 3.4   (not published to any host port)
   ▲
raahat-worker   outbox processing, audio transcription, external-data polling,
                heartbeat row every tick
```

No Redis, no message broker, no reverse proxy container. PostgreSQL provides
the queue (outbox with `FOR UPDATE SKIP LOCKED`), the event log, and the
wake-up signal (`LISTEN/NOTIFY`).

### B.2 Backend modules

| Module | Responsibility |
|---|---|
| `raahat.config` | Typed settings read once from the environment; refuses to start in production with a missing or default secret |
| `raahat.security` | Password hashing, token issue/verify, role → permission map, rate limiter |
| `raahat.api` | App factory, middleware, dependencies (`current_user`, `require(permission)`), routers, request/response schemas |
| `raahat.application.intake` | Operator and channel intake; orchestrates text processing → evidence → incident resolution → triage in one transaction |
| `raahat.application.ai` | Provider-independent ports: speech-to-text, language identification, translation, extraction; processing-run records |
| `raahat.application.incidents` | Incident lifecycle state machine, corrections with field-level history |
| `raahat.application.incident_resolution` | Duplicate candidate scoring and reviewed merge/unmerge (retained) |
| `raahat.application.location` | Landmark resolution, geocoder port, candidate ranking, confirmation (retained, fabrication removed) |
| `raahat.application.resources` | Resource registry, availability, position with source and timestamp |
| `raahat.application.dispatch` | Priority ordering, recommendation engine, human decision recording, assignment lifecycle |
| `raahat.application.events` | Persisted event log, SSE stream with replay |
| `raahat.application.system` | Health probes and integration status |
| `raahat.infrastructure` | Database models and migrations, provider adapters (Gnani, Gemini, Nominatim, OSRM, alert feeds), audit chain, outbox |
| `raahat.policies` | Deterministic triage rules (retained) |
| `raahat.workers` | Bounded background loops |

### B.3 Request and transaction model

One SQLAlchemy session per request. A command handler changes state, appends
audit records and appends event-log rows through that same session, and commits
once. An `AFTER INSERT` trigger on the event log issues `pg_notify`, so
subscribers are woken only after the transaction is durable.

### B.4 Realtime

`event_log` has a `BIGSERIAL` sequence. The SSE endpoint sends each row with
`id: <seq>`. A reconnecting client sends `Last-Event-ID`; the server replays
every row after that sequence (bounded) before tailing. If the gap exceeds the
replay bound the server sends a `resync` event and the client refetches its
queries. Each API process holds one `LISTEN` connection and fans out to its
subscribers through bounded queues; a slow subscriber is disconnected and
recovers through replay rather than dropping events silently.

### B.5 Security model

- Users are rows with a scrypt password hash and one role. There are no default
  accounts; the first administrator is created from the CLI on the host.
- Roles: `admin`, `operator`, `dispatcher`, `resource_coordinator`, `observer`.
  Permissions are checked in the backend per route.
- Access tokens are short-lived signed JWTs sent in the `Authorization` header.
  The frontend is cross-origin, so cookies are not used.
- CORS allows exactly the configured frontend origins.
- Public surface is limited to health, login and the citizen intake endpoints,
  each rate-limited and size-limited.

### B.6 Frontend

A single SPA in `web/` (Vite, React, TypeScript) replacing both `dashboard/` and
`operator_console/`. It talks only to the backend API through one typed client
whose base URL comes from `VITE_API_BASE_URL`. Server state is held in TanStack
Query; the SSE stream invalidates queries. See `DECISIONS.md` for the design
system.

### B.7 Data provenance

Every location candidate, extracted fact and external observation carries its
source (`caller`, `operator`, `gps`, `geocoder`, `landmark`, `ai`, `rules`,
`external`), the time it was recorded, and a confidence or verification status
where one exists. Original report text is immutable; corrections are new
records that reference the actor.
