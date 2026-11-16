# RAAHAT

Emergency intake, incident intelligence and rescue-resource coordination for
disaster control rooms (floods, landslides, cyclones). Built for Kerala and Goa
operations; Malayalam, English, Hindi and Konkani reports.

RAAHAT is **decision support**. It records reports, organises them into
incidents, shows where they are and what is known, and recommends which
resource to send. A person approves every dispatch. RAAHAT does not contact
emergency services or field teams, and it is not a certified replacement for an
emergency-services system.

## What it does

| Area | What happens |
|---|---|
| Intake | Operators type reports in the caller's words and language. Channel gateways (SMS, radio) and an optional public web form submit through the API. Voice notes are transcribed by Gnani Prisma when configured. The original text is never altered. |
| Understanding | Language identified from script and vocabulary; rule-based extraction of people, trapped, medical need, water level and depth, hazards, needs and place mentions, each with the words it came from. With a model configured (Gnani Evon or Gemini), translation to English and model extraction; model output is kept only when its supporting quote is found in the report. |
| Incidents | Every report becomes or joins an incident, starting **unverified**. Lifecycle: unverified → under review → verified → assigned → response active → resolved → closed (or duplicate). Transitions are validated. Operators correct facts; corrections are stored beside the extracted values with name and time. |
| Priority | Deterministic triage rules (critical / urgent / standard / low; "not assessed" ranks above standard). An explicit priority score orders verified incidents awaiting a resource. |
| Duplicates | Candidates found from phone, distance, people named, shared facts and contradictions. Never merged automatically. Operators merge, reject or relate; merges are reversible. |
| Location | Candidates from the caller's device, operator entry, landmark gazetteer (OpenStreetMap import) and geocoder (Nominatim, on request). Each is labelled with its source and uncertainty. Nothing becomes the position until confirmed, and no coordinates are invented. |
| Dispatch | Resources with capabilities, capacity and timestamped positions. Recommendations rank feasible resources on capability, distance (road distance with OSRM, otherwise labelled straight-line), capacity and position age, with every factor shown. Approval records what was recommended and why a different choice was made. |
| Live operation | Every change is an audited, hash-chained event, streamed to browsers (SSE) and replayed after reconnect. Official CAP alerts (NDMA SACHET) are imported for reference. |
| Honesty | System status reflects real checks. The interface says when the server is unreachable and how old the data on screen is. |

## Repository

```
src/raahat/          Python package (FastAPI API, worker, domain, providers)
  api/               routes, auth dependencies, app factory
  application/       intake, incidents, location, dispatch, alerts, system status, identity
  domain/            triage facts, evidence, lifecycle, enums
  policies/          deterministic triage rules
  infrastructure/    database models and migrations, provider adapters, audit chain
  workers/           background worker
web/                 operator web app (Vite, React, TypeScript)
tests/               backend tests (pytest, real PostGIS)
evaluation/          synthetic benchmark harness (generated data, see TESTING.md)
scripts/             dev-up, dev-down, health-check, backup, restore, tunnel-up
compose.yaml         database, API, worker for one host
```

## Quick start (local)

```bash
cp .env.example .env            # fill in POSTGRES_PASSWORD, RAAHAT_SECRET_KEY, CORS_ALLOWED_ORIGINS
./scripts/dev-up.sh             # builds, starts, migrates, waits for health
docker compose exec api raahat-entrypoint cli create-admin --username <you> --full-name "<Your Name>"

cd web && cp .env.example .env.local   # VITE_API_BASE_URL=http://127.0.0.1:8000
npm ci && npm run dev                  # http://127.0.0.1:5173 (add it to CORS_ALLOWED_ORIGINS)
```

There are no default accounts and no sample data. Open an operation, register
resources and enter reports.

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Audit of the original code and the architecture now in place |
| [DECISIONS.md](DECISIONS.md) | Design and engineering decisions with reasons |
| [DATA_PROVIDERS.md](DATA_PROVIDERS.md) | External data sources assessed for Kerala and Goa |
| [DEPLOYMENT_LOCAL.md](DEPLOYMENT_LOCAL.md) | Running the backend on the laptop |
| [DEPLOYMENT_VERCEL.md](DEPLOYMENT_VERCEL.md) | Deploying the web app |
| [NETWORK_CONNECTIVITY.md](NETWORK_CONNECTIVITY.md) | HTTPS tunnel, CORS, exposure |
| [OPERATIONS.md](OPERATIONS.md) | Day-to-day running, monitoring, failure handling |
| [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md) | Backups, restore, recovery drills |
| [RESOURCE_BUDGET.md](RESOURCE_BUDGET.md) | Measured memory, CPU, latency and limits |
| [TESTING.md](TESTING.md) | Test suites, how to run them, what is and is not verified |
| [TASKS.md](TASKS.md) | Status of every work item, including open ones |
| [CHANGELOG.md](CHANGELOG.md) | Changes by version |

## Licence

Apache 2.0. Landmark data imported from OpenStreetMap is © OpenStreetMap
contributors under the ODbL; NDMA SACHET alerts are published as public domain.
