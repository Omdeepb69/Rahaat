# RAAHAT — Task tracker

Legend: `[x]` done and verified · `[~]` implemented, not fully verified ·
`[ ]` not started · `[!]` blocked (reason given)

## Stage 0 — Reconnaissance
- [x] Repository audit (`ARCHITECTURE.md` Part A)
- [x] Run existing stack, capture UI, record console errors
- [x] Test baseline (471 passed / 4 failed on the original code)

## Stage 1 — Foundations
- [x] Typed settings with production safety checks
- [x] Migrations: users, event log, heartbeats, processing runs, integration checks, external observations
- [x] scrypt passwords, JWT, permissions, rate limiter, lockout
- [x] Authentication and authorization on every route
- [x] App hardening: CORS, size limits, request ids, structured logs, real health checks
- [x] CLI: create-admin, reset-password, import-landmarks, check-config
- [x] Simulation, demo, mock and stub code removed

## Stage 2 — Domain
- [x] Incident model and lifecycle state machine
- [x] Location hypotheses with provenance; no fabricated fallback
- [x] Operator intake with idempotency; channel intake via worker
- [x] Corrections with history; manual priority with required note
- [x] Duplicate review with signals; reversible merge
- [x] Candidate prefilter for matching (performance)

## Stage 3 — Resources and dispatch
- [x] Resource register, availability, timestamped positions, retirement
- [x] Explicit priority score and queue
- [x] Recommendation engine with factors and limitations; road distance when OSRM configured
- [x] Human approval, override reason, decline, progress, cancellation; one active assignment per resource
- [~] Multi-incident plan (greedy by priority): constraints tested; not compared with baselines on real outcomes (no data)

## Stage 4 — Realtime and health
- [x] Persisted, hash-chained event log with NOTIFY
- [x] SSE with Last-Event-ID replay and resync; browser reconnect verified
- [x] System status with real probes; worker heartbeat

## Stage 5 — AI and external data
- [x] Provider adapters that raise instead of inventing output
- [x] Processing-run records
- [x] Gnani Prisma transcription: verified live with synthetic audio
- [!] Translation and model extraction: Gemini key in `.env` rejected (401); no Evon endpoint
- [~] Nominatim geocoding and OSRM routing: adapters tested with recorded responses; not configured
- [x] OSM landmark import (live Overpass import verified)
- [x] NDMA SACHET CAP alerts (live import verified)
- [x] Provider assessment (`DATA_PROVIDERS.md`)
- [ ] IMD API (needs IP whitelisting), CWC data (needs official access)

## Stage 6 — Frontend
- [x] Design system (tokens, light and dark, components)
- [x] API client, auth with refresh, realtime, connection monitor
- [x] Shell, navigation, offline banner
- [x] All screens connected to the API
- [x] Loading, empty, error and offline states; layouts at 1440/1280/834/390 px
- [~] Accessibility: semantics, labels, focus, keyboard and reduced motion done; no screen-reader session

## Stage 7 — Deployment
- [x] compose.yaml, Dockerfile (locked dependencies), entrypoint
- [x] Scripts: dev-up, dev-down, health-check, backup, restore, tunnel-up
- [x] Backup/restore and restart persistence tested
- [x] Vercel configuration
- [!] Tailscale Funnel: Tailscale is logged out on the host; exposing the API needs the owner
- [!] Vercel deployment: needs the owner's account

## Stage 8 — Verification
- [x] Backend tests, lint
- [x] Frontend type check, lint, tests, production build
- [x] Browser end-to-end on dev and containerised stacks
- [x] Resource and latency measurements

## Open items
- [ ] Valid Gemini key or an Evon endpoint, then measure translation/extraction quality on labelled real reports
- [ ] Labelled evaluation set from real (consented, anonymised) reports for extraction, language id and duplicates
- [ ] Self-hosted OSRM with a Kerala/Goa extract if road distances are wanted
- [ ] Retention policy for caller data, agreed with the responsible authority
- [ ] Decide whether to stop and remove the pre-redesign stack and its volume
