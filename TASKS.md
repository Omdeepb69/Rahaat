# RAAHAT — Task tracker

Legend: `[x]` done and verified · `[~]` implemented, not fully verified ·
`[ ]` not started · `[!]` blocked (reason given)

## Stage 0 — Reconnaissance
- [x] Repository audit (`ARCHITECTURE.md` Part A)
- [x] Run existing stack, capture UI, record console errors
- [x] Establish test baseline (471 passed / 4 failed)
- [x] Target architecture and decisions recorded

## Stage 1 — Foundations
- [ ] Typed settings
- [ ] Migration: users, event log, heartbeats, processing runs, integration checks
- [ ] Password hashing, tokens, permissions, rate limiter
- [ ] Authentication and authorization on every route
- [ ] App factory hardening and real health checks
- [ ] CLI (create-admin)
- [ ] Remove simulation and demo code

## Stage 2 — Domain corrections
- [ ] Migration: incident model, report text, provenance columns
- [ ] Incident lifecycle state machine
- [ ] Location resolver without fabricated fallback
- [ ] Operator intake service
- [ ] Corrections with history
- [ ] Duplicate review API with signals

## Stage 3 — Resources and dispatch
- [ ] Resource registry
- [ ] Priority ordering
- [ ] Recommendation engine and baselines
- [ ] Human decision workflow

## Stage 4 — Realtime and health
- [ ] Event log writer
- [ ] SSE with replay
- [ ] System status with real probes

## Stage 5 — AI and external data
- [ ] Provider ports and adapters
- [ ] Processing-run records
- [ ] Geocoder, routing, landmark import
- [ ] External data provider research and adapters

## Stage 6 — Frontend
- [ ] Design system
- [ ] API client, auth, realtime
- [ ] Shell
- [ ] Screens
- [ ] States and responsive passes

## Stage 7 — Deployment
- [ ] Compose, Dockerfile
- [ ] Scripts
- [ ] Vercel configuration
- [ ] Documents

## Stage 8 — Verification
- [ ] Backend tests
- [ ] Frontend checks
- [ ] End-to-end browser run
- [ ] Measurements
