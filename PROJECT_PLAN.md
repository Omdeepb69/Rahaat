# Project Plan

This file is the persistent source of truth for project progress. It
survives across conversations and context resets. Conversation history is
not a record of project state — this file is. Update it after every
completed task, not at the end of a session.

## Goal

Build Raahat 2.0: an uncertainty-aware, offline-resilient multichannel disaster
intelligence and rescue coordination platform. "Done" means satisfying all 25
acceptance criteria in `RAAHAT_SPEC.md` §14:
1. Multichannel report ingestion (IVR, SMS, Web SOS, offline volunteer app, radio console gateway) behind a unified contract.
2. Distinct Report, Evidence, Household, Person, and Incident entities with PostGIS persistence and transactional outbox.
3. Active landmark disambiguation under geographic uncertainty.
4. Conservative, reversible entity resolution and conflict-aware evidence graph.
5. Deterministic, explainable safety triage preserving unknown fields.
6. Human-authorized rescue dispatch workflow with immutable audit logging.
7. Reproducible evaluation on RaahatBench benchmark and Docker Compose deployment stack.

## Current Phase

Phase 3 — Evidence Graph, Entity Resolution & Safety Triage

## Status

- [x] Phase 1 — Repository Baseline, Core Domain Models & Ingestion Pipeline
  - [x] 1.1 Repository & Workspace Foundation
  - [x] 1.2 Database Schema & Migration Foundation (PostgreSQL + PostGIS)
  - [x] 1.3 Core Domain Entities & Value Objects
  - [x] 1.4 Transactional Outbox & Background Worker Runtime
  - [x] 1.5 Ingestion Gateway & Multi-Channel Ingestion Adapters
  - [x] 1.6 IVR Pipeline Adapter Integration
- [x] Phase 2 — Geospatial Intelligence & Offline Field Resilience
  - [x] 2.1 PostGIS Landmark Index & Candidate Matcher
  - [x] 2.2 Active Clarification & Question Selection Engine
  - [x] 2.3 Location Verification API & Hypotheses History
  - [x] 2.4 Offline Field Client Storage & Protocol (SQLite)
  - [x] 2.5 Idempotent Synchronization Endpoint & Sync Worker
- [ ] Phase 3 — Evidence Graph, Entity Resolution & Safety Triage
  - [x] 3.1 Evidence Provenance Graph & Contradiction Detection
  - [x] 3.2 Conservative Entity Resolution & Incident Matcher
  - [ ] 3.3 Human Verification & Reversible Incident Linking Workflow
  - [ ] 3.4 Fact Extraction & Deterministic Safety Triage Policy
- [ ] Phase 4 — Operations Control Room, Resource Dispatch & Telephony
  - [ ] 4.1 Resource Registry & Availability Management
  - [ ] 4.2 Human-Approved Rescue Assignment & Operation Lifecycle
  - [ ] 4.3 Tamper-Evident Append-Only Audit Logging
  - [ ] 4.4 Live Event Streaming (SSE / WebSocket)
  - [ ] 4.5 Speech Recognizer & Telephony Callback Boundaries
  - [ ] 4.6 Operator Console Web Application
- [ ] Phase 5 — Resilience, RaahatBench Evaluation & Deployment
  - [ ] 5.1 Fault Injection & Chaos Recovery Scenarios
  - [ ] 5.2 RaahatBench Benchmark Dataset & Ground Truth Generator
  - [ ] 5.3 Ablation Studies & Research Evaluation Runner
  - [ ] 5.4 Docker Compose Stack & Infrastructure Scaffolding
  - [ ] 5.5 Observability Dashboards, Runbook & Limitations Documentation

---

## Phase 1 — Repository Baseline, Core Domain Models & Ingestion Pipeline

### 1.1 Repository & Workspace Foundation
- Objective: Initialize `src/raahat` layout, configure `pyproject.toml` (FastAPI, Pydantic, SQLAlchemy, psycopg, pytest, ruff, mypy), audit and import slice-1 location math & synthetic gazetteer from `/mnt/data/projects/raahat-repo` into `src/raahat/domain/geospatial/`, and verify 13 unit tests pass in new layout.
- Inputs: `/mnt/data/projects/raahat-repo`, `RAAHAT_SPEC.md`.
- Output: Standardized Python package structure, passing geospatial unit tests, linters and typecheckers configured.
- Depends on: None.

### 1.2 Database Schema & Migration Foundation (PostgreSQL + PostGIS)
- Objective: Create PostgreSQL/PostGIS database models and initial Alembic migrations for core tables (`disasters`, `reports`, `households`, `persons`, `incidents`, `evidence_items`, `evidence_spans`, `incident_reports`, `location_hypotheses`, `resources`, `assignments`, `operation_events`, `outbox_events`, `audit_events`, `sync_cursors`, `entity_merge_events`).
- Inputs: Schema definitions from `RAAHAT_SPEC.md` §4.
- Output: Working Alembic migration scripts, SQLAlchemy declarative models, test database setup.
- Constraints: PostGIS spatial indexes (`GIST`), check constraints for probabilities `[0,1]`, UUID primary keys.
- Depends on: 1.1.

### 1.3 Core Domain Entities & Value Objects
- Objective: Implement immutable domain entities, value objects, and status enums for `Report`, `EvidenceItem`, `EvidenceSpan`, `Household`, `Person`, `Incident`, `LocationHypothesis`, and `PriorityAssessment` in pure Python.
- Inputs: Entity contracts from `RAAHAT_SPEC.md` §4 and `ARCHITECTURE.md`.
- Output: Pure domain classes in `src/raahat/domain/` with zero database or web framework dependencies.
- Constraints: Immutability for event records; strict validation; no external vendor imports.
- Depends on: 1.1.

### 1.4 Transactional Outbox & Background Worker Runtime
- Objective: Implement the transactional outbox pattern and a database-backed worker runner with row-level leasing (`FOR UPDATE SKIP LOCKED`), fencing tokens, and job lifecycle (`PENDING -> CLAIMED -> PROCESSING -> SUCCEEDED / RETRYABLE_FAILURE / DEAD_LETTER`).
- Inputs: Outbox table schema from 1.2, domain events from 1.3.
- Output: Outbox publisher protocol and DB-backed background worker loop in `src/raahat/workers/runner.py`.
- Constraints: Short transactions; no open DB transactions during long-running tasks; worker lease expiration recovery.
- Depends on: 1.2, 1.3.

### 1.5 Ingestion Gateway & Multi-Channel Ingestion Adapters
- Objective: Build `ReportIngestionService` and REST endpoints `POST /api/v1/reports`, enforcing idempotency `(disaster_id, idempotency_key)`, atomic outbox publishing, and channel adapters for Web SOS, SMS, and Radio Console manual submissions.
- Inputs: Outbox service from 1.4, report models from 1.3.
- Output: Ingestion application service, API routes, and channel payload adapters.
- Constraints: Ingestion must acknowledge only after durable PostgreSQL persistence; never directly mutate incidents from ingestion.
- Depends on: 1.2, 1.3, 1.4.

### 1.6 IVR Pipeline Adapter Integration
- Objective: Adapt the voice call session (Silero VAD, speech transcription, keypad fallback, number read-back) to emit structured `ReportSubmission` records into `ReportIngestionService` rather than mutating incidents directly.
- Inputs: Ingestion gateway from 1.5, speech contracts from `ARCHITECTURE.md`.
- Output: IVR channel adapter in `src/raahat/adapters/channels/ivr/`.
- Constraints: Preserve call session state and keypad/read-back fallbacks; call agent must never directly assign resources or merge incidents.
- Depends on: 1.5.

---

## Phase 2 — Geospatial Intelligence & Offline Field Resilience

### 2.1 PostGIS Landmark Index & Candidate Matcher
- Objective: Implement PostGIS-backed landmark repository with spatial queries, trigram fuzzy matching (`pg_trgm`), and candidate location retrieval based on spoken/textual landmark descriptions.
- Inputs: PostGIS gazetteer schema from 1.2.
- Output: PostGIS landmark repository and candidate spatial query engine.
- Constraints: Transliteration-tolerant fuzzy lookup; spatial bounding to disaster zone.
- Depends on: 1.2, 1.3.

### 2.2 Active Clarification & Question Selection Engine
- Objective: Port and adapt the expected-confidence utility and belief distribution engine to select optimal follow-up disambiguation questions ("mandir ke samne ya peeche?") and produce candidate hypotheses with explicit uncertainty bounding.
- Inputs: Geospatial math from 1.1, candidate matcher from 2.1.
- Output: `LocationResolver` protocol implementation in `src/raahat/application/location/`.
- Constraints: Explicitly set `probability: null` prior to model calibration; do not fabricate confidence; return clear candidate bounding.
- Depends on: 1.1, 2.1.

### 2.3 Location Verification API & Hypotheses History
- Objective: Implement `POST /api/v1/incidents/{id}/location/verify` endpoint, preserving all historical candidate hypotheses while recording dispatcher confirmation decisions and generating audit events.
- Inputs: Location engine from 2.2, API framework from 1.5.
- Output: Location verification route and hypothesis history repository.
- Constraints: Never erase earlier location hypotheses upon verification; require authenticated dispatcher identity.
- Depends on: 2.2, 1.5.

### 2.4 Offline Field Client Storage & Protocol (SQLite)
- Objective: Implement the offline field app data layer (`field_app/`) with SQLite storage, monotonic device sequence numbering, UUID event IDs, `client_created_at`, and an outbound sync queue.
- Inputs: Domain report models from 1.3.
- Output: SQLite database schema and sync client queue in `field_app/`.
- Constraints: Zero internet dependency for report entry; local atomic persistence; clean separation of `locally_saved` vs `server_synchronized` statuses.
- Depends on: 1.3.

### 2.5 Idempotent Synchronization Endpoint & Sync Worker
- Objective: Build `POST /api/v1/devices/sync` endpoint and server-side sync processor to ingest batches of offline reports with device authentication, sequence tracking in `sync_cursors`, and duplicate suppression.
- Inputs: Field app sync format from 2.4, Ingestion gateway from 1.5.
- Output: Device sync API endpoint and background sync worker in `src/raahat/workers/sync_worker.py`.
- Constraints: 100% idempotent handling of retransmitted batches; server receipt timestamps recorded distinctly from client event timestamps.
- Depends on: 1.5, 2.4.

---

## Phase 3 — Evidence Graph, Entity Resolution & Safety Triage

### 3.1 Evidence Provenance Graph & Contradiction Detection
- Objective: Implement domain services and repositories to decompose reports into `EvidenceItem` and `EvidenceSpan` records, track source provenance, and detect contradictory claims (e.g. water level rising vs receded, varying headcounts).
- Inputs: Report models from 1.3, DB tables from 1.2.
- Output: Evidence graph service and conflict detection module in `src/raahat/domain/evidence/`.
- Constraints: Every evidence item must link back to its report and source text/audio span; contradictions must be flagged, never silently resolved.
- Depends on: 1.3, 1.5.

### 3.2 Conservative Entity Resolution & Incident Matcher
- Objective: Implement `IncidentMatcher` evaluating candidate incidents for incoming reports based on spatial distance, household members, and contact numbers, using conservative thresholds that flag ambiguous merges for human review.
- Inputs: Evidence graph from 3.1, candidate matcher from 2.1.
- Output: Conservative incident matcher service in `src/raahat/application/incident_resolution/`.
- Constraints: Conservative matching: false merges are worse than duplicates. Ambiguous merges must be sent to review queue; automated links must remain reversible.
- Depends on: 2.1, 3.1.

### 3.3 Human Verification & Reversible Incident Linking Workflow
- Objective: Build `POST /api/v1/incidents/{id}/links` and `POST /api/v1/incidents/{id}/verify` endpoints, recording dispatcher merge approvals/rejections in `entity_merge_events` and supporting reversibility without data loss.
- Inputs: Incident matcher from 3.2, API framework from 1.5.
- Output: Incident verification routes and merge review service.
- Constraints: Original household and report records are never deleted; every merge action records reviewer ID, timestamp, and justification; full unmerge capability.
- Depends on: 3.2.

### 3.4 Fact Extraction & Deterministic Safety Triage Policy
- Objective: Implement decoupled fact extraction (`fact_extractor`) and deterministic safety triage policy (`priority_policy`) calculating priority (`critical_review`, `urgent`, `standard`, `low`) based on explicit rules while strictly preserving `unknown` fields.
- Inputs: Evidence graph from 3.1.
- Output: Pure policy module in `src/raahat/policies/triage.py` and triage application service.
- Constraints: "Unknown never lowers priority" rule; missing fields remain explicitly `unknown`; no floating point arbitrary weights; full decision explanation list.
- Depends on: 3.1.

---

## Phase 4 — Operations Control Room, Resource Dispatch & Telephony

### 4.1 Resource Registry & Availability Management
- Objective: Implement domain models, PostGIS repositories, and API endpoints (`GET /api/v1/resources`, `POST /api/v1/resources`) for rescue assets (boats, medical teams, vehicles, shelters) with status tracking (`available`, `assigned`, `maintenance`, `offline`).
- Inputs: Database models from 1.2, domain entities from 1.3.
- Output: Resource management service and API routes.
- Constraints: Spatial indexing for resource coordinates; authenticated management.
- Depends on: 1.2, 1.3.

### 4.2 Human-Approved Rescue Assignment & Operation Lifecycle
- Objective: Implement rescue assignment and operation tracking (`POST /api/v1/incidents/{id}/assignments`, `POST /api/v1/operations/{id}/events`), enforcing human dispatcher approval and state transitions (`proposed -> approved -> acknowledged -> en_route -> on_scene -> rescued -> closed`).
- Inputs: Resource registry from 4.1, triage assessments from 3.4.
- Output: Operations application service and assignment API routes.
- Constraints: Strict zero autonomous dispatch rule: assignment fails without valid dispatcher authentication; audit event emitted on every transition.
- Depends on: 4.1, 3.4.

### 4.3 Tamper-Evident Append-Only Audit Logging
- Objective: Implement audit service writing to `audit_events` with SHA-256 cryptographic hash chaining (`prev_hash || event_payload -> current_hash`), tamper verification routine, and read-only inspection API.
- Inputs: Database schema from 1.2.
- Output: Audit repository and hash chain verification service in `src/raahat/infrastructure/audit/`.
- Constraints: Append-only; no UPDATE or DELETE queries permitted on table; hash chain verification detects modified or omitted records.
- Depends on: 1.2, 1.3.

### 4.4 Live Event Streaming (SSE / WebSocket)
- Objective: Implement `GET /api/v1/events/stream` providing real-time Server-Sent Events (SSE) to dispatcher consoles, streaming sanitized incident updates, new reports, and operational status changes published by the outbox.
- Inputs: Outbox engine from 1.4, operations events from 4.2.
- Output: Real-time event streaming route in `src/raahat/api/routes/events.py`.
- Constraints: Non-blocking asynchronous streaming; connection disconnect handling; event filtering by disaster ID.
- Depends on: 1.4, 4.2.

### 4.5 Speech Recognizer & Telephony Callback Boundaries
- Objective: Implement `SpeechRecognizer` protocol with Whisper-base local adapter, Gnani Prisma client adapter stub, Piper TTS adapter, and outbound callback scheduler behind a telephony provider interface.
- Inputs: IVR requirements from 1.6, domain contracts from `ARCHITECTURE.md`.
- Output: Speech and telephony infrastructure adapters in `src/raahat/infrastructure/speech/` and `src/raahat/infrastructure/telephony/`.
- Constraints: Core logic isolated from provider SDKs; retry limits and consent checks on automated callbacks; no infinite redial loops.
- Depends on: 1.3.

### 4.6 Operator Console Web Application
- Objective: Build the operator console frontend with four distinct workspaces: 1. Incoming Reports Feed, 2. Situation Map (MapLibre + OSM with distinct visual encoding for confirmed, candidate, approximate, stale, and contradictory locations), 3. Incident Investigation (transcripts, evidence spans, merge review), 4. Operations (resources, assignments, approvals).
- Inputs: API routes from 1.5, 3.3, 4.2, and streaming from 4.4.
- Output: Single-page web console in `operator_console/`.
- Constraints: Critical UI safety rule: map markers must never display unverified candidate locations as confirmed rescue pins; explicit display of unknown fields and evidence provenance.
- Depends on: 4.2, 4.4.

---

## Phase 5 — Resilience, RaahatBench Evaluation & Deployment

### 5.1 Fault Injection & Chaos Recovery Scenarios
- Objective: Implement automated fault injection test suite verifying system behavior during speech worker crashes, database disconnections, LLM unavailability, worker lease timeouts, duplicate sync attempts, and operator disconnects.
- Inputs: Ingestion from 1.5, outbox worker from 1.4, sync worker from 2.5.
- Output: Chaos test suite in `tests/fault_injection/`.
- Constraints: Failures must be diagnosable; zero lost reports; expired leases must safely recover without duplicate processing.
- Depends on: 1.4, 2.5, 4.2.

### 5.2 RaahatBench Benchmark Dataset & Ground Truth Generator
- Objective: Implement `evaluation/` generator creating the frozen 1,000 synthetic reports across 100 ground-truth incidents with specified distributions (direct, third-party, volunteer, radio; code-switching, noisy audio, ambiguous landmarks, contradictions).
- Inputs: Benchmark specification from `RAAHAT_SPEC.md` §9.1.
- Output: Deterministic dataset generator and frozen dataset files in `evaluation/datasets/`.
- Constraints: Fully deterministic generation via seeds; immutable ground-truth references for each incident, household, and coordinate.
- Depends on: 1.3, 3.1.

### 5.3 Ablation Studies & Research Evaluation Runner
- Objective: Implement benchmark runner executing Configurations A (conventional baseline) through E (Full Raahat) against frozen RaahatBench; calculate Top-1/Top-3 candidate accuracy, MAE (m), B-cubed F1, false merge rate, high-severity recall, and under-triage rate.
- Inputs: Benchmark dataset from 5.2, baseline and upgraded pipelines.
- Output: Evaluation runner and automated report generator in `evaluation/runner.py`.
- Constraints: Paired bootstrap 95% confidence intervals; honest reporting of limitations and failures.
- Depends on: 5.2, 2.2, 3.2, 3.4.

### 5.4 Docker Compose Stack & Infrastructure Scaffolding
- Objective: Create production-grade Docker Compose environment (`compose.yaml`, `Dockerfile`) deploying Nginx reverse proxy, FastAPI API service, Background Worker service, PostgreSQL 16 + PostGIS, Prometheus, and Grafana with volume persistence and health checks.
- Inputs: API service, worker runner, database migrations, console frontend.
- Output: Validated Compose stack and build files in project root and `deployment/`.
- Constraints: Non-root container execution; health and readiness checks; persistent volume survival across restarts; no exposed internal database ports.
- Depends on: 1.2, 1.4, 1.5, 4.6.

### 5.5 Observability Dashboards, Runbook & Limitations Documentation
- Objective: Configure Prometheus scraping and Grafana dashboards for report throughput, processing latencies, worker queue lag, and sync metrics; author operational runbook, security documentation, and explicit limitations report.
- Inputs: Prometheus metrics from services, deployment stack from 5.4.
- Output: Dashboard configs, operational runbook, security architecture doc, and `docs/limitations.md`.
- Constraints: Honest documentation of limitations (synthetic dataset, single-instance scaling boundaries, speech recognizer requirements).
- Depends on: 5.4, 5.3.

---

## Current Task

**Task ID:** 3.3 — Human Verification & Reversible Incident Linking Workflow

**Goal:** Build `POST /api/v1/incidents/{id}/links` and `POST /api/v1/incidents/{id}/verify` endpoints, recording dispatcher merge approvals/rejections in `entity_merge_events` and supporting reversibility without data loss.

**Inputs:** Incident matcher from 3.2, API framework from 1.5.

**Output:** Incident verification routes and merge review service in `src/raahat/application/incident_resolution/` and `src/raahat/api/routes/incidents.py`.

**Constraints:** Original household and report records are never deleted; every merge action records reviewer ID, timestamp, and justification; full unmerge capability.

**Verification:** Unit and integration tests verifying merge approval, unmerge rollback, `entity_merge_events` logging, audit event generation, and REST endpoint authorization; `mypy` and `ruff` clean.

**Depends on:** 3.2.

---

## Next Task

**Task ID:** 3.4 — Fact Extraction & Deterministic Safety Triage Policy.

---

## Constraints

- Target language: Python 3.10+.
- Authoritative transactional store: PostgreSQL + PostGIS. No Kafka, NATS, Kubernetes, or microservices for MVP.
- All AI/automated operations are decision-support only; dispatch and resource allocation strictly require authenticated human approval.
- Speech and geocoding implementations must sit behind abstract protocols (`SpeechRecognizer`, `LocationResolver`).
- Explicit uncertainty preservation: unverified information remains `unknown`, candidate locations carry uncertainty bounds, and probabilities are never manufactured without statistical calibration.
- All mutating actions produce append-only, tamper-evident audit logs.

---

## Log

### 2026-11-07 — Task 3.2 complete
- Changed: Implemented conservative entity resolution and incident matching engine. Defined domain repository protocol `IncidentRepository` and `InMemoryIncidentRepository` in `src/raahat/domain/incidents/repository.py`; defined application models (`ResolutionDecisionType`, `MatchSignal`, `IncidentCandidate`, `ResolutionDecision`, `ResolutionResult`, `IncidentSnapshot`) in `src/raahat/application/incident_resolution/models.py`; defined `IncidentMatcher` and `IncidentResolver` protocols in `src/raahat/application/incident_resolution/protocol.py`; implemented `ConservativeIncidentMatcher` evaluating phone normalization, spatial distance falloff (`distance_to`), name/household matching, and cross-report contradiction detection with score capping (<=0.50); implemented `ConservativeIncidentResolver` enforcing conservative auto-link thresholds (0.80), distance limits (<=150m), candidate margin requirements (>=0.15), and zero-tolerance contradiction routing to human review; implemented `IncidentResolutionService` orchestrating report resolution, duplicate report linking, and `pending_review` incident linking in `src/raahat/application/incident_resolution/service.py`; wired `get_incident_resolution_service` dependency in `src/raahat/api/dependencies.py`.
- Files: `src/raahat/domain/incidents/repository.py`, `src/raahat/domain/incidents/__init__.py`, `src/raahat/application/incident_resolution/models.py`, `src/raahat/application/incident_resolution/protocol.py`, `src/raahat/application/incident_resolution/matcher.py`, `src/raahat/application/incident_resolution/resolver.py`, `src/raahat/application/incident_resolution/service.py`, `src/raahat/application/incident_resolution/__init__.py`, `src/raahat/api/dependencies.py`, `tests/unit/application/test_incident_matcher.py`, `tests/unit/application/test_incident_resolver.py`, `tests/unit/application/test_incident_resolution_service.py`, `tests/integration/test_incident_resolution.py`, `LESSONS.md`.
- Verified: 9 unit tests in `test_incident_matcher.py` (phone normalization, feature extraction, distance scoring, contradiction capping, resolved incident exclusion); 7 unit tests in `test_incident_resolver.py` (auto-link, distance safety, contradiction override, ambiguous score, margin safety); 3 unit tests in `test_incident_resolution_service.py` with `InMemoryIncidentRepository` (auto-link duplicate, ambiguous review link, independent creation); 5 integration tests in `test_incident_resolution.py` against PostgreSQL + PostGIS container (candidate querying, auto-link duplicate insertion, ambiguous link pending_review insertion, conflicting link insertion, and automatic `LocationHypothesisModel` creation); full test suite passes (259 passed, up from 235); `mypy src/raahat field_app tests` clean across 160 source files; `ruff check .` clean.
- Limitations: Human review endpoints `POST /api/v1/incidents/{id}/links` and merge/unmerge workflow will be implemented in Task 3.3.

### 2026-11-07 — Task 3.1 complete
- Changed: Implemented evidence decomposition, source provenance tracking, and rule-based contradiction detection. Defined domain entities and value objects (`EvidenceSpan` with ID, `EvidenceItem`, `Contradiction`, `Corroboration`, `EvidenceProvenance`, `EvidenceGraph`) in `src/raahat/domain/evidence/evidence.py`; implemented `StructuredEvidenceExtractor` in `src/raahat/domain/evidence/extractor.py` decomposing structured and audio-turn payloads with Hindi/English concept keyword matching and trend normalization; implemented `RuleBasedContradictionDetector` in `src/raahat/domain/evidence/detector.py` flagging water level trend conflicts, headcount divergence, boolean status mismatches, numeric water depth discrepancies (>=50cm), and landmark divergence, plus corroboration detection; defined `EvidenceRepository` protocol and `InMemoryEvidenceRepository` in `src/raahat/domain/evidence/repository.py`; implemented `PostgresEvidenceRepository` in `src/raahat/infrastructure/database/repositories/evidence.py`; implemented `EvidenceGraphService` in `src/raahat/domain/evidence/service.py` coordinating decomposition, persistence, provenance tracing, and graph synthesis; added `get_evidence_graph_service` dependency provider in `src/raahat/api/dependencies.py`.
- Files: `src/raahat/domain/evidence/evidence.py`, `src/raahat/domain/evidence/extractor.py`, `src/raahat/domain/evidence/detector.py`, `src/raahat/domain/evidence/repository.py`, `src/raahat/domain/evidence/service.py`, `src/raahat/domain/evidence/__init__.py`, `src/raahat/infrastructure/database/repositories/evidence.py`, `src/raahat/infrastructure/database/repositories/__init__.py`, `src/raahat/api/dependencies.py`, `tests/unit/domain/test_evidence_extractor.py`, `tests/unit/domain/test_contradiction_detector.py`, `tests/unit/domain/test_evidence_service.py`, `tests/integration/test_evidence_graph.py`, `LESSONS.md`.
- Verified: 5 unit tests in `test_evidence_extractor.py`; 24 unit tests in `test_contradiction_detector.py`; 11 unit tests in `test_evidence_service.py`; 6 integration tests in `test_evidence_graph.py` against live PostgreSQL container (verifying report decomposition persistence, foreign key relationships, multi-report provenance, graph extraction, and contradiction detection); full test suite passes (235 passed, up from 189); `mypy src/raahat field_app tests` clean across 150 source files; `ruff check .` clean.
- Limitations: Conservative incident matcher consuming evidence items will be implemented in Task 3.2.

### 2026-11-07 — Task 2.5 complete
- Changed: Implemented idempotent device synchronization endpoint and background sync monitor worker. Built `VolunteerSyncAdapter` in `src/raahat/adapters/channels/volunteer/adapter.py` mapping `SyncReportItem` wire objects into `ReportSubmission` domain items with separate `client_created_at` and `received_at` timestamps; built `DeviceSyncService` in `src/raahat/adapters/channels/volunteer/service.py` coordinating batch report ingestion, atomic `sync_cursors` sequence advancement, and transactional outbox event publishing (`raahat.device.synced`); built REST endpoints `POST /api/v1/devices/sync` and `GET /api/v1/devices/{device_id}/cursor` with `require_device_id` header authentication (`X-Device-Id`); implemented `SyncWorker` in `src/raahat/workers/sync_worker.py` monitoring device connectivity, staleness thresholds, and sequence continuity gap detection.
- Files: `src/raahat/adapters/channels/volunteer/adapter.py`, `src/raahat/adapters/channels/volunteer/service.py`, `src/raahat/adapters/channels/volunteer/__init__.py`, `src/raahat/api/routes/devices.py`, `src/raahat/api/routes/__init__.py`, `src/raahat/api/app.py`, `src/raahat/api/dependencies.py`, `src/raahat/workers/sync_worker.py`, `src/raahat/workers/__init__.py`, `tests/unit/adapters/test_volunteer_adapter.py`, `tests/unit/workers/test_sync_worker.py`, `tests/integration/test_device_sync_api.py`, `LESSONS.md`.
- Verified: 1 unit test in `test_volunteer_adapter.py` verifying model conversion and channel reference format; 2 unit tests in `test_sync_worker.py` verifying stale device identification and sequence gap detection; 7 integration tests in `test_device_sync_api.py` against PostgreSQL and FastAPI `TestClient` (happy-path batch ingestion, duplicate retransmission idempotency, partial sequence overlap, authentication failures 401/400/403, 404 disaster not found, device cursor retrieval, and end-to-end roundtrip from SQLite `field_app.OfflineSyncQueue` to PostgreSQL and back); full test suite passes (189 tests); `mypy src/raahat field_app tests` clean across 141 files; `ruff check .` clean.
- Limitations: Evidence graph decomposition and contradiction detection will consume incoming reports in Task 3.1.

### 2026-11-07 — Task 2.4 complete
- Changed: Implemented offline field client data layer and sync queue in `field_app/`. Defined domain models and sync protocols `SyncStatus` (`locally_saved`, `syncing`, `server_synchronized`, `failed`), `OfflineReportDraft`, `OfflineReport`, `SyncReportItem`, `SyncBatch`, and `SyncAck` in `field_app/models.py`; implemented SQLite database connection and schema manager in `field_app/database/` supporting WAL mode, atomic transactions (`BEGIN IMMEDIATE`), schema version tracking, and thread-safe serialized execution; implemented `OfflineSyncQueue` in `field_app/sync/queue.py` providing strictly monotonic device sequence numbering, event UUID generation, local atomic persistence, outbound batch creation, acknowledgement processing, and failure/retry recovery with zero internet dependency.
- Files: `field_app/__init__.py`, `field_app/models.py`, `field_app/database/__init__.py`, `field_app/database/schema.py`, `field_app/database/connection.py`, `field_app/sync/__init__.py`, `field_app/sync/queue.py`, `pyproject.toml`, `tests/unit/field_app/test_database.py`, `tests/unit/field_app/test_offline_queue.py`, `LESSONS.md`.
- Verified: 9 unit tests in `tests/unit/field_app/` (in-memory schema initialization, atomic transactions commit/rollback, file-based persistence, monotonic sequence assignment, batch status transitions, acknowledgement to `server_synchronized`, failure handling, empty queue, and concurrent multi-threaded drafting sequence integrity); full test suite passes (179 tests); `mypy src/raahat field_app tests` clean across 134 source files; `ruff check .` clean.
- Limitations: Server-side synchronization endpoint `POST /api/v1/devices/sync` and background sync worker will be implemented in Task 2.5.

### 2026-11-07 — Task 2.3 complete
- Changed: Implemented location verification API and historical hypothesis tracking. Implemented `AuditRepository` and `PostgresAuditRepository` with cryptographic SHA-256 hash chaining; implemented `LocationHypothesisRepository`, `PostgresLocationHypothesisRepository`, and `InMemoryLocationHypothesisRepository` with pure-Python EWKB Point parser (`parse_wkb_point`); implemented `LocationVerificationService` enforcing authenticated dispatcher confirmation, updating incident `last_confirmed_at` and `status`, recording audit events, and preserving earlier hypotheses without deletion; implemented REST endpoints `POST /api/v1/incidents/{incident_id}/location/verify` and `GET /api/v1/incidents/{incident_id}/location/hypotheses` with `require_dispatcher_id` authentication.
- Files: `src/raahat/infrastructure/database/repositories/audit.py`, `src/raahat/infrastructure/database/repositories/location_hypothesis.py`, `src/raahat/infrastructure/database/repositories/__init__.py`, `src/raahat/application/location/verification.py`, `src/raahat/application/location/__init__.py`, `src/raahat/api/routes/locations.py`, `src/raahat/api/routes/__init__.py`, `src/raahat/api/app.py`, `src/raahat/api/dependencies.py`, `tests/unit/application/test_location_verification_service.py`, `tests/unit/api/test_location_verification_api.py`, `tests/integration/test_location_verification_api.py`, `LESSONS.md`.
- Verified: 3 unit tests in `test_location_verification_service.py` (existing hypothesis confirmation, new coordinates confirmation, error cases); 6 unit tests in `test_location_verification_api.py` (dispatcher header requirement 401/400, validation 422, incident 404, successful verify 200, hypotheses history 200); 3 integration tests in `test_location_verification_api.py` against live PostgreSQL+PostGIS (verifying hypothesis update, non-deletion of prior hypotheses, incident confirmation timestamp, and tamper-evident audit hash chaining); full test suite passes (170 tests); `mypy src/raahat tests` clean across 125 files; `ruff check .` clean.
- Limitations: Offline field client data layer and sync queue will be implemented in Task 2.4.

### 2026-11-07 — Task 2.2 complete
- Changed: Implemented active clarification and question selection engine. Defined domain models `ClarificationAnswer`, `ClarificationQuestion`, `LocationObservation`, and `LocationResolution` in `src/raahat/application/location/models.py`; defined `LocationResolver` protocol in `src/raahat/application/location/protocol.py`; implemented `PostGISGazetteerResolver` in `src/raahat/application/location/resolver.py` supporting direct GPS pins, fuzzy landmark text matching via `LandmarkRepository`, Expected Information Gain (EIG) calculation for spatial ambiguity, adaptive question selection ("mandir ke samne ya peeche?" vs landmark disambiguation), ward filtering, prior answer evaluation, and explicit uncertainty bounding (`probability=None` strictly enforced per specification).
- Files: `src/raahat/application/location/models.py`, `src/raahat/application/location/protocol.py`, `src/raahat/application/location/resolver.py`, `src/raahat/application/location/__init__.py`, `tests/unit/application/test_location_resolver.py`, `tests/integration/test_location_resolver_integration.py`.
- Verified: 8 unit tests in `tests/unit/application/test_location_resolver.py` (protocol conformance, GPS resolution, single landmark relative direction question, answer processing, multiple landmark EIG disambiguation, ward filtering, no-match fallback); 3 integration tests in `tests/integration/test_location_resolver_integration.py` against live PostGIS (direct coordinates finding nearby landmark, fuzzy text matching, multi-turn disambiguation flow); full test suite passes (158 passed); `mypy src/raahat tests` clean across 118 files; `ruff check .` clean.
- Limitations: Location verification API endpoint and historical candidate hypothesis tracking will be implemented in Task 2.3.

### 2026-11-07 — Task 2.1 complete
- Changed: Implemented PostGIS-backed landmark repository and candidate matcher. Added Alembic migration `41e7e411f7ee` creating `pg_trgm` extension and GIN trigram index `landmarks_name_trgm_idx` on `landmarks.name`; defined domain value objects `BoundingBox`, `Landmark`, and `LandmarkCandidate` in `src/raahat/domain/geospatial/landmark.py`; created transliteration normalization and synonym expansion helpers in `src/raahat/adapters/maps/transliteration.py`; implemented `LandmarkRepository` protocol, `PostgresLandmarkRepository`, `InMemoryLandmarkRepository`, and `trigram_similarity` in `src/raahat/infrastructure/database/repositories/landmark.py`; implemented `LandmarkIndexer` in `src/raahat/adapters/maps/indexer.py` seeding synthetic `City` POIs into PostgreSQL/PostGIS.
- Files: `src/raahat/domain/geospatial/landmark.py`, `src/raahat/domain/geospatial/__init__.py`, `src/raahat/infrastructure/database/models/location.py`, `src/raahat/infrastructure/database/migrations/versions/41e7e411f7ee_add_pg_trgm_and_landmark_trgm_index.py`, `src/raahat/infrastructure/database/repositories/landmark.py`, `src/raahat/infrastructure/database/repositories/__init__.py`, `src/raahat/adapters/maps/transliteration.py`, `src/raahat/adapters/maps/indexer.py`, `src/raahat/adapters/maps/__init__.py`, `tests/unit/geospatial/test_landmark.py`, `tests/integration/test_landmark_repository.py`.
- Verified: 8 unit tests in `tests/unit/geospatial/test_landmark.py` (bounding box containment/validation, transliteration normalization, synonym expansion, trigram similarity, in-memory repository text search & radius queries); 9 integration tests in `tests/integration/test_landmark_repository.py` against PostgreSQL+PostGIS (exact text search, fuzzy trigram query, transliteration variant query, spatial bounding box filter, similarity threshold enforcement, radius search with distance sorting, kind filtering, synthetic City indexer seeding); all 147 test suite tests pass; `mypy src/raahat tests` clean across 113 source files; `ruff check .` clean.
- Limitations: Active clarification and question selection engine will consume `LandmarkRepository` in Task 2.2.

### 2026-11-07 — Task 1.6 complete
- Changed: Implemented IVR voice call pipeline adapter in `src/raahat/adapters/channels/ivr/`. Built `IVRCallSession` tracking multi-turn dialog state and turn cap (`max_turns`); built `IVRCallAgent` managing state machine transitions (`AWAITING_LOCATION`, `AWAITING_LOCATION_KEYPAD`, `AWAITING_PEOPLE_COUNT`, `AWAITING_PEOPLE_COUNT_READBACK`, `AWAITING_NEEDS`, `COMPLETED`); implemented speech recognition protocol & mock in `src/raahat/infrastructure/speech/`, VAD detection (`EnergyVADDetector` and `SileroVADDetector`), number read-back generator and confirmation evaluator (`evaluate_readback_confirmation`), keypad fallback on repeated recognition failures, and structured `ReportSubmission` generation into `ReportIngestionService`.
- Files: `src/raahat/infrastructure/speech/protocol.py`, `src/raahat/infrastructure/speech/mock.py`, `src/raahat/infrastructure/speech/__init__.py`, `src/raahat/adapters/channels/ivr/session.py`, `src/raahat/adapters/channels/ivr/vad.py`, `src/raahat/adapters/channels/ivr/readback.py`, `src/raahat/adapters/channels/ivr/agent.py`, `src/raahat/adapters/channels/ivr/__init__.py`, `src/raahat/adapters/channels/__init__.py`, `tests/unit/adapters/test_ivr_adapter.py`, `LESSONS.md`.
- Verified: 12 unit tests in `tests/unit/adapters/test_ivr_adapter.py` verifying full conversational turn flow, keypad fallback after repeated low confidence / silence, direct DTMF headcount entry, number read-back rejection and correction, and turn cap enforcement; all 130 test suite tests pass; `mypy src/raahat tests` clean across 105 files; `ruff check .` clean.
- Limitations: Live telephony provider SIP/Twilio trunking callback scheduler will be connected in Task 4.5.

### 2026-11-07 — Task 1.5 complete
- Changed: Implemented `ReportIngestionService` enforcing `(disaster_id, idempotency_key)` uniqueness and atomic outbox event publishing (`raahat.report.received`) in the same database transaction; built channel payload adapters for Web SOS (`WebSOSAdapter`), SMS (`SMSAdapter`), and Radio Console (`RadioConsoleAdapter`); built FastAPI application (`create_app`) with REST endpoints `POST /api/v1/reports`, channel-specific routes (`POST /api/v1/reports/channels/{web|sms|radio}`), and report query endpoints (`GET /api/v1/reports/{id}`, `GET /api/v1/reports`).
- Files: `pyproject.toml`, `src/raahat/adapters/channels/web/adapter.py`, `src/raahat/adapters/channels/sms/adapter.py`, `src/raahat/adapters/channels/radio_console/adapter.py`, `src/raahat/adapters/channels/__init__.py`, `src/raahat/application/ingestion/service.py`, `src/raahat/application/ingestion/__init__.py`, `src/raahat/api/app.py`, `src/raahat/api/dependencies.py`, `src/raahat/api/routes/reports.py`, `src/raahat/api/routes/__init__.py`, `src/raahat/api/__init__.py`, `tests/unit/adapters/test_channel_adapters.py`, `tests/unit/application/test_ingestion_service.py`, `tests/integration/test_ingestion_api.py`.
- Verified: 10 unit tests (channel adapter payload conversions and validation, ingestion service idempotency and race condition recovery); 9 integration tests against PostgreSQL and FastAPI `TestClient` (generic submission, duplicate suppression returning 200, atomic outbox creation, Web SOS / SMS / Radio routes, 404 on missing disaster or report, list filtering); all 118 test suite tests pass; `mypy src/raahat tests` clean (98 files); `ruff check .` clean.
- Limitations: Live telephony / Twilio voice call webhook and speech recognizer integration is handled in Task 1.6.

### 2026-11-07 — Task 1.4 complete
- Changed: Implemented transactional outbox pattern and database-backed worker runtime. Added `DomainEvent` value object, `OutboxJobStatus` enum, `EventOutbox` protocol with `PostgresEventOutbox` publisher in `src/raahat/infrastructure/outbox/`; implemented `PostgresOutboxRepository` using `SELECT … FOR UPDATE SKIP LOCKED` with row-level leasing, fencing tokens, and configurable retry/dead-letter settling; implemented `OutboxWorker` in `src/raahat/workers/runner.py` executing handlers outside open DB transactions.
- Files: `src/raahat/infrastructure/outbox/events.py`, `src/raahat/infrastructure/outbox/publisher.py`, `src/raahat/infrastructure/outbox/repository.py`, `src/raahat/infrastructure/outbox/__init__.py`, `src/raahat/workers/runner.py`, `src/raahat/workers/__init__.py`, `tests/unit/workers/test_outbox_worker.py`, `tests/integration/test_outbox.py`, `LESSONS.md`.
- Verified: 10 unit tests in `tests/unit/workers/test_outbox_worker.py` verifying lease claiming, fencing token rejection on stale settle, retry increment, dead-letter promotion, and expired lease recovery with pure-Python fake repository; 5 integration tests in `tests/integration/test_outbox.py` validating real PostgreSQL operations with `FOR UPDATE SKIP LOCKED`; full test suite passes (99 tests); `mypy src/raahat tests` clean across 88 source files; `ruff check .` clean.
- Limitations: Ingestion API routes and background worker process CLI entrypoint will be wired in Tasks 1.5 and Phase 5.

### 2026-11-07 — Task 1.3 complete
- Changed: Implemented all core domain entities and value objects as frozen Pydantic v2 models with zero database/framework dependencies: `PointCoordinates` (with Haversine `distance_to`, WKT round-trip), `Report`/`ReportSubmission` (with idempotency key derivation), `EvidenceItem`/`EvidenceSpan`, `Household`/`Person`, `Incident`/`IncidentLink`/`IncidentReportLink`, `LocationHypothesis`, `PriorityAssessment`, and `Resource`/`Assignment`/`OperationEvent` in `src/raahat/domain/operations/`.
- Files: `src/raahat/domain/shared/enums.py`, `src/raahat/domain/shared/coordinates.py`, `src/raahat/domain/shared/__init__.py`, `src/raahat/domain/reports/report.py`, `src/raahat/domain/reports/__init__.py`, `src/raahat/domain/evidence/evidence.py`, `src/raahat/domain/evidence/__init__.py`, `src/raahat/domain/households/household.py`, `src/raahat/domain/households/__init__.py`, `src/raahat/domain/incidents/incident.py`, `src/raahat/domain/incidents/__init__.py`, `src/raahat/domain/geospatial/location_hypothesis.py`, `src/raahat/domain/geospatial/__init__.py`, `src/raahat/domain/triage/assessment.py`, `src/raahat/domain/triage/__init__.py`, `src/raahat/domain/operations/operation.py`, `src/raahat/domain/operations/__init__.py`, `tests/unit/domain/test_entities.py`.
- Verified: 77 unit tests pass (`PYTHONPATH="" pytest tests/unit/`; 64 new domain entity tests + 13 prior geospatial tests); `mypy src/raahat tests` — 0 errors across 82 source files; `ruff check .` — 0 errors.
- Limitations: `src/raahat/domain/resources/__init__.py` is an empty stub (resource domain is covered by `operations/`); can be removed or consolidated in a future cleanup task.

### 2026-11-07 — Task 1.2 complete
- Changed: Implemented complete SQLAlchemy 2.0 declarative models and Alembic migrations for all 17 core Raahat 2.0 tables with PostGIS geography/geometry types, GIST indexes, and check constraints (`[0, 1]` ranges for probability and confidence, unique idempotency keys per disaster); set up engine/session factory in `src/raahat/infrastructure/database/session.py`; created integration test suite `tests/integration/test_migrations.py`.
- Files: `alembic.ini`, `src/raahat/infrastructure/database/base.py`, `src/raahat/infrastructure/database/session.py`, `src/raahat/infrastructure/database/models/*`, `src/raahat/infrastructure/database/migrations/*`, `tests/integration/test_migrations.py`, `pyproject.toml`, `LESSONS.md`.
- Verified: Tested Alembic migration upgrade and downgrade against live PostgreSQL 17 + PostGIS 3.7 container; ran `PYTHONPATH="" pytest tests` with 20 passing tests (7 integration + 13 geospatial); `ruff check .` passed with 0 errors; `mypy src/raahat tests` passed with 0 errors across 72 source files.
- Limitations: PostgreSQL test container runs on localhost:54329; production compose stack will wrap this in Phase 5.

### 2026-11-07 — Task 1.1 complete
- Changed: Initialized git repository, configured `pyproject.toml` with packaging, test, ruff, and mypy settings; established full `src/raahat/` and `tests/` directory tree; migrated slice-1 location math and synthetic gazetteer from `raahat-repo` into `src/raahat/domain/geospatial/`; created `tests/unit/geospatial/test_core.py`.
- Files: `pyproject.toml`, `.gitignore`, `src/raahat/domain/geospatial/*`, `tests/unit/geospatial/test_core.py`, `LESSONS.md`.
- Verified: All 13 unit tests passed in pytest (`PYTHONPATH="" pytest tests/unit/geospatial`), `ruff check .` passed with 0 errors, `mypy src/raahat tests/unit/geospatial` passed cleanly across 45 source files.
- Limitations: Slice-1 gazetteer is currently synthetic grid-based; real PostGIS landmark indexing comes in Phase 2.
