# Testing

## Suites

| Suite | Location | Count | Needs |
|---|---|---|---|
| Backend unit and integration | `tests/` | 324 | PostgreSQL + PostGIS (migrated automatically) |
| Frontend unit and component | `web/src/test/` | 11 | Node |
| Browser end-to-end | not in the repository; scripts run during this work are described below | — | running stack, Chrome |

### Backend

```bash
docker run -d --name raahat-pg-test --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=raahat_test -p 127.0.0.1:54330:5432 postgis/postgis:16-3.4
uv sync --extra dev
uv run pytest            # DATABASE_URL defaults to the container above
uv run ruff check src tests
```

If a ROS installation is on your Python path, its pytest plugin breaks
collection; run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -p pytest_asyncio.plugin -p pytest_timeout`.

API tests truncate and reuse the test database. **Never point
`DATABASE_URL` at operational data when running tests.**

Covered: authentication, lockout, token revocation, role permissions, PII
redaction, CORS, body limits; report intake, idempotency, language
identification, rule extraction (en/hi/ml/kok, negation, units), original text
immutability; incident lifecycle; corrections and priority override;
landmark candidates, confirm/reject, operator positions; duplicate signals,
merge, reject, unmerge, the candidate prefilter; resources and positions;
recommendation feasibility, ranking, routes, limitations; approval, override
reason, double-commit prevention, progress and cancellation; dispatch queue
and plan; event persistence, replay and resync; system status; audit chain
verification and tamper detection; public intake; worker processing, missing
speech provider, crash recovery; provider adapters (recorded HTTP responses,
including errors, missing configuration, key-in-header); CAP parsing;
migrations; deployment definition (no database port, loopback API, memory
limits, bounded shutdown, env template completeness).

Results on 2026-11-16: **324 passed** (backend), **11 passed** (frontend),
ruff clean, TypeScript `tsc -b` clean, oxlint clean, production build OK.

### Frontend

```bash
cd web
npm ci
npm run typecheck && npm run lint && npm test && npm run build
```

## End-to-end runs performed

Playwright driving Chrome against real services:

1. **Dev stack** (API on host, Vite dev server): sign-in errors and success;
   empty state; open operation; register resources and report a position;
   three reports (English with a real OSM landmark, Malayalam repeat call,
   Hindi medical); landmark candidate confirmed; verify; recommendation;
   approve; progress; incidents table; incident page; duplicate merge;
   reports, dispatch, activity, system, users pages; audit verification; a
   report made by another session appearing without reload. Console: no
   errors other than the deliberate failed sign-in.
2. **Production build** (`vite preview`) against the **containerised stack**:
   the same flow, passed.
3. **Failure**: API stopped while signed in → banner after 5.8 s, data kept and
   labelled; API restarted → live again after 6.4 s.
4. **Layouts**: 1440×900, 1280×720, 834×1112, 390×844 and dark mode: no
   horizontal overflow; screenshots reviewed.
5. **Keyboard**: tab order on sign-in; dialogs trap focus and close on Escape;
   tabs use arrow keys.

## Not verified

| Item | Why |
|---|---|
| Vercel deployment, public HTTPS via Tailscale Funnel | Need the owner's accounts and login |
| Translation and model extraction against a live model | Gemini key rejected; no Evon endpoint |
| Speech recognition accuracy | Only synthetic espeak audio was available; connectivity verified, accuracy not measured |
| Geocoding and routing against live services | Not configured; adapters tested with recorded responses |
| Screen-reader walkthrough | Semantics and labels tested; no assistive-technology session run |

## Model and algorithm evaluation

No accuracy figures are claimed.

- `evaluation/` contains a **synthetic** benchmark generator and metrics
  (precision/recall for duplicate resolution, triage, spatial error). Its
  dataset is generated from templates with a fixed seed; results on it say
  nothing about real reports and are not reported as such.
- The rule extractor, language identifier, duplicate matcher and
  recommendation engine have behavioural tests, not accuracy measurements. A
  labelled set of real (consented, anonymised) reports from Kerala/Goa
  control rooms is needed to measure them.
- The dispatch plan has not been compared with FIFO or nearest-available
  baselines on real outcomes; no such data exists here. Its constraint
  behaviour (feasibility, no double allocation, priority order) is tested.
