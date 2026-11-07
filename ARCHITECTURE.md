# Architecture

Stable architectural decisions for Raahat. Unlike `PROJECT_PLAN.md`
(which tracks progress and changes constantly), this file changes rarely —
only when an architectural decision is actually made or revised. Treat
entries here as load-bearing: other tasks and modules assume they hold.

## System Overview

Raahat 2.0 is an uncertainty-aware, offline-resilient disaster intelligence
and rescue coordination platform. It ingests distress reports from multiple
heterogeneous channels (IVR calls, SMS, Web SOS, offline field volunteer
devices, and radio operator consoles), separates incoming reports from canonical
incidents, builds an evidence graph with source provenance, disambiguates
locations using landmark reasoning with explicit uncertainty, applies
conservative entity resolution and explainable deterministic triage, and
maintains a human-in-the-loop operational rescue queue.

## Module Map

Target repository layout:

```
src/raahat/
├── domain/                  — Pure domain models, value objects, and protocols.
│                              Zero external framework or vendor imports.
│   ├── reports/             — Report entity, source metadata, channel types.
│   ├── evidence/            — EvidenceItem, EvidenceSpan, provenance, conflict detection.
│   ├── households/          — Household and Person entities, identity uncertainty.
│   ├── incidents/           — Canonical Incident aggregate, operational status.
│   ├── geospatial/          — Coordinate representations, landmark models, spatial queries.
│   ├── triage/              — Priority assessment, safety policy rules, unknown preservation.
│   ├── operations/          — Rescue operation aggregate, assignments, lifecycle events.
│   ├── resources/           — Rescue resources (boats, medical, vehicles, shelters).
│   └── shared/              — Identifiers, timestamps, pagination, audit event schemas.
│
├── application/             — Application services orchestrating domain logic.
│   ├── ingestion/           — ReportIngestionService (idempotency, source validation).
│   ├── incident_resolution/ — Multi-source matching, candidate evaluation, review queue.
│   ├── location/            — Location disambiguation and active clarification engine.
│   ├── triage/              — Fact extraction and priority evaluation orchestrator.
│   └── dispatch/            — Resource assignment and rescue operation workflows.
│
├── infrastructure/          — Concrete implementations of external systems and storage.
│   ├── database/            — PostgreSQL + PostGIS models, repositories, and migrations.
│   ├── outbox/              — Transactional outbox event writer and leasing worker.
│   ├── audit/               — Append-only tamper-evident audit store.
│   ├── speech/              — SpeechRecognizer adapters (Whisper, Gnani Prisma, Piper TTS).
│   └── observability/       — Prometheus metrics collector, health/readiness probes.
│
├── adapters/                — Input channel gateways and external interfaces.
│   ├── channels/
│   │   ├── ivr/             — Voice call session adapter (Silero VAD + ASR -> Report).
│   │   ├── sms/             — SMS ingestion webhook/adapter.
│   │   ├── web/             — Web SOS submission adapter.
│   │   ├── volunteer/       — Field device synchronization receiver (idempotent sync).
│   │   └── radio_console/   — Human-operated radio gateway adapter.
│   └── maps/                — OpenStreetMap / PostGIS gazetteer indexer.
│
├── api/                     — FastAPI modular presentation layer.
│   ├── routes/              — REST endpoints (reports, incidents, locations, operations, etc.).
│   ├── middleware/          — Auth, request tracing, rate limiting, error handling.
│   └── dependencies.py      — Dependency injection wiring.
│
└── workers/                 — Background process execution.
    ├── runner.py            — Database-backed leasing and fencing worker loop.
    ├── report_processor.py  — Background speech/text extraction worker.
    ├── sync_worker.py       — Device synchronization processing.
    └── callback_worker.py   — Scheduled phone callback dialing worker.

field_app/                   — Offline-first field client (SQLite storage + sync queue).
operator_console/            — Dispatcher UI (Reports inbox, Situation map, Investigation, Ops).
tests/                       — Unit, integration, concurrency, fault injection, and evaluation tests.
evaluation/                  — RaahatBench datasets, baselines, ablation runner, and reports.
deployment/                  — Docker Compose, Prometheus, Grafana configs, and runbooks.
```

## Interfaces / Contracts

### `SpeechRecognizer` (Protocol)
- `async def transcribe(audio: AudioInput, language_hint: str | None = None) -> Transcript`
- Guarantees: Takes raw or segmented audio, returns timestamped transcript with confidence.
- Consumed by: `ivr` adapter and `report_processor` worker.
- Implemented by: `WhisperRecognizer` (local baseline), `PrismaRecognizer` (Gnani adapter), `MockSpeechRecognizer`.
- Core domain logic never imports Whisper or Prisma directly.

### `LocationResolver` (Protocol)
- `async def resolve(observation: LocationObservation) -> LocationResolution`
- Guarantees: Evaluates landmark mentions, returns candidate hypotheses with uncertainty bounding and active clarification questions. Never fabricates calibrated probabilities without an evaluated statistical model.
- Consumed by: `location` application service.
- Implemented by: `PostGISGazetteerResolver`.

### `IncidentMatcher` (Protocol)
- `async def match(report: Report) -> list[IncidentCandidate]`
- Guarantees: Finds candidate incidents based on spatial proximity, phone numbers, and household attributes. Evaluates merge safety and tags ambiguous merges for human review.
- Consumed by: `incident_resolution` application service.
- Implemented by: `ConservativeIncidentMatcher`.

### `PriorityPolicy` (Protocol)
- `def assess(facts: SeverityFacts) -> PriorityAssessment`
- Guarantees: Evaluates operational urgency deterministically based on explicit policy rules. Preserves unknown fields; unverified information never lowers priority.
- Consumed by: `triage` application service.
- Implemented by: `DeterministicSafetyPriorityPolicy`.

### `ReportIngestionService` (Protocol)
- `async def ingest(submission: ReportSubmission) -> IngestionResult`
- Guarantees: Enforces idempotency via `(disaster_id, idempotency_key)`, persists raw report, writes outbox event in same transaction, returns durable report ID.

### `EventOutbox` (Protocol)
- `async def publish(event: DomainEvent, connection: DatabaseConnection) -> None`
- Guarantees: Appends event to `outbox_events` atomically with aggregate state changes.

## Boundaries and Rules

1. **Separation of Reports and Incidents**:
   - A `Report` is an immutable record of an incoming message from a source.
   - An `Incident` is an evolving, verified operational situation.
   - Reports and Incidents have a many-to-many relationship (`incident_reports`). A call, SMS, or volunteer submission must NEVER automatically overwrite or replace an incident.

2. **Human-in-the-Loop Authority**:
   - AI and automated workers propose associations, candidate locations, and urgency rankings.
   - No rescue operation or resource assignment may be initiated without explicit human approval.
   - Ambiguous incident merges require dispatcher review. Entity merges must be reversible through `entity_merge_events`; original records are never deleted.

3. **Dependency Inversion**:
   - `domain/` must have zero dependencies on web frameworks (FastAPI), database engines (SQLAlchemy, asyncpg, psycopg), or ML backends (Whisper, PyTorch, Transformers).
   - Core domain models use standard library and pure dataclasses/Pydantic.
   - All external integrations (Speech, SMS, GIS, Database) sit behind protocols.

4. **Transactional Safety & Worker Isolation**:
   - PostgreSQL is the sole authoritative transactional store for the MVP.
   - Heavy inference (ASR, LLM extraction) must run in separate worker processes, NEVER in API request handlers.
   - Database transactions must remain brief: NEVER hold an open transaction while waiting on speech recognition or external API calls.
   - Background workers use database-backed leases with fencing tokens to guarantee that a worker that lost its lease cannot commit stale processing results.

5. **Explicit Uncertainty**:
   - Unknown information remains `unknown` — missing fields must never be default-coerced into negative observations (e.g. "no medical need").
   - Location candidates must carry uncertainty bounding or candidate radii; uncalibrated confidence scores must not be displayed as probabilities.
   - The UI and API must explicitly distinguish confirmed, candidate, approximate, and stale locations.

6. **Durable Ingestion & Offline Sync**:
   - Field devices store reports locally in SQLite with a UUID and monotonic device sequence.
   - Sync submissions are idempotent; server receipt timestamps are tracked independently of client creation timestamps.
   - Ingestion endpoints must acknowledge reports only after durable persistence in PostgreSQL.

7. **Immutable & Tamper-Evident Auditability**:
   - All status transitions, human approvals, dispatch assignments, and merge decisions must produce an append-only `AuditEvent`.
   - Audit records cannot be modified or deleted via application APIs.
   - Cryptographic hash chaining ensures detection of any direct database tampering.

## Decisions Log

### 2026-11-07 — Architecture alignment with RAAHAT_SPEC.md (Raahat 2.0)
- **Context**: Transition from IVR-centric prototype (slice 1) to full resilient multichannel disaster intelligence platform.
- **Decision**: Adopt a modular monolith architecture with FastAPI, PostgreSQL + PostGIS as the authoritative source of truth, transactional outbox for worker dispatch, and SQLite on offline field clients.
- **Reasoning**: Floods disrupt cellular communications; relying on callers maintaining active phone connections creates catastrophic failure modes. Raahat must ingest from volunteers, radio operators, SMS, and web in addition to IVR.
- **Alternatives considered**:
  - *Microservices with Kafka/NATS*: Rejected for MVP. Adds distributed system failure modes and deployment complexity without operational benefit for the single-district scenario.
  - *Direct LLM-to-incident dispatch*: Rejected. Autonomous AI dispatch in disaster environments is unsafe; human dispatchers must verify and approve every operational action.
