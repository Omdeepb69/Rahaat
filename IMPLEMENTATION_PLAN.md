# RAAHAT — Implementation plan

Order is chosen so that each stage leaves a running, testable system. Status of
individual items is tracked in `TASKS.md`.

**Status (2026-11-16):** stages 1–8 implemented. Deviations from this plan:
the event log is the audit table itself rather than a separate `event_log`
table (one write, one ordering); IMD and CWC were not integrated (no public
API, see DATA_PROVIDERS.md) and NDMA SACHET alerts were integrated instead;
Observability containers were removed rather than moved behind a profile.

## Stage 1 — Foundations (backend)

1. `raahat.config`: typed settings; fail fast on missing secret in production.
2. Migration `a1_identity_and_events`: `users`, `event_log` (+ NOTIFY trigger),
   `worker_heartbeats`, `processing_runs`, `integration_checks`.
3. `raahat.security`: scrypt hashing, JWT issue/verify, permission map,
   in-process token-bucket rate limiter.
4. API dependencies `current_user` / `require(permission)`; apply to every
   router. Replace `X-Dispatcher-Id` with the authenticated user id.
5. App factory: exact-origin CORS, body-size limit, request id, structured
   logs, uniform error body, real `/health/live` and `/health/ready`.
6. CLI: `create-admin`, `import-landmarks`.
7. Remove demo route, seed/demo scripts, simulation modules, mock fallbacks,
   stub telephony.

## Stage 2 — Domain corrections

1. Migration `a2_incident_model`: incident reference sequence, category,
   summary, location description, verification fields, expanded status set with
   a check constraint; report original/translated text and language; location
   hypothesis `source`; incident link `signals`; resource capabilities, status
   detail, contact, position source and timestamp; dispatch decision table.
2. Incident lifecycle state machine with validated transitions.
3. Location resolver: remove fabricated fallback; add provenance; geocoder port.
4. Intake service: operator-entered report → extraction → evidence → incident
   resolution → triage, one transaction, events emitted.
5. Corrections API with field-level history.
6. Duplicate review API exposing the signals behind each candidate.

## Stage 3 — Resources and dispatch

1. Resource registry CRUD, availability changes, position updates; all audited.
2. Priority ordering of open incidents (explicit formula).
3. Recommendation engine: feasibility filter, scored ranking, factor
   breakdown; multi-incident plan; FIFO and nearest-available baselines.
4. Decision endpoint: approve / reject / override with reason; assignment
   lifecycle; resource state follows assignment state.

## Stage 4 — Realtime and health

1. Event log writer used by every command handler.
2. SSE endpoint with `Last-Event-ID` replay and LISTEN/NOTIFY fan-out.
3. Worker heartbeat rows; system status endpoint with real probes.

## Stage 5 — AI and external data

1. Ports and adapters: speech-to-text (Gnani Prisma), extraction and
   translation (Gnani Evon via OpenAI-compatible endpoint, Gemini), language
   identification (provider result for audio, script analysis for text).
2. Processing-run records with provider, model, duration, error.
3. Geocoder adapter (Nominatim), routing adapter (OSRM), landmark import
   (Overpass).
4. External data: provider research document; adapters for the sources that
   are genuinely reachable.

## Stage 6 — Frontend (`web/`)

1. Tooling, tokens, base styles, primitives.
2. API client, auth, SSE client, query layer.
3. Shell and navigation; connection and freshness indicators.
4. Screens: sign-in, operations (queue + map + detail), incidents, incident
   detail, intake, reports, resources, dispatch, activity, system status,
   administration.
5. Loading, empty, error and offline states for each.
6. Responsive passes at 1440, 1024, 768 and 390 px; keyboard and screen-reader
   pass.

## Stage 7 — Deployment

1. Compose reduced to db, api, worker; observability behind a profile.
2. Scripts: `dev-up`, `dev-down`, `health-check`, `backup`, `restore`,
   `tunnel-up`.
3. `web/vercel.json`; `.env.example` files.
4. Deployment, connectivity, operations, backup and resource-budget documents.

## Stage 8 — Verification

1. Backend tests updated and extended; migration up/down check.
2. Frontend type check, lint, unit tests, production build.
3. Browser end-to-end run against a real backend and database.
4. Measurements: memory, CPU, latency.
5. Final documentation pass; handoff report.
