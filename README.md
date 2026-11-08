# Raahat 2.0 (राहत)

**Uncertainty-Aware, Offline-Resilient Disaster Intelligence & Rescue Coordination Platform**

Built for rapid, coordinated flood and disaster emergency response in India.

[![Tests](https://img.shields.io/badge/tests-457%20passing-brightgreen)](#testing--verification)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Database](https://img.shields.io/badge/database-PostgreSQL%2016%20%2B%20PostGIS-blue)](https://postgis.net/)
[![Gnani AI](https://img.shields.io/badge/Gnani.ai-Prisma%20v3.0%20%7C%20Timbre-orange)](https://gnani.ai/)

---

## Overview

During major flood disasters (such as the 2018 Kerala floods or Pune urban inundations), emergency helplines and dispatch centers are overwhelmed with thousands of simultaneous distress calls. Existing systems fail because:
1. **Dialect and code-mixing**: Callers speak regional languages (Malayalam, Marathi, Hindi) mixed with English (Hinglish) under severe stress and noisy acoustic conditions.
2. **Ambiguous locations**: Victims report relative landmarks ("near Alappuzha canal", "near Shaniwar Wada bridge") rather than GPS coordinates.
3. **Black-box AI risks**: Autonomous LLMs can hallucinate headcounts or dispatch units to wrong addresses, creating life-safety hazards.
4. **Network collapse**: Cellular networks fail during floods, cutting off cloud-only platforms.

**Raahat 2.0** solves these challenges with a clear architectural separation:
- **Sensory Perception**: Fast, multilingual Indian speech transcription via **Gnani Prisma v3.0** (`indic-auto`), natural Indic voice synthesis via **Gnani Timbre** (`Shivani` voice), and acoustic voice-activity detection (VAD).
- **Deterministic Decision Policy**: Spatial landmark disambiguation with PostGIS uncertainty bounding, conservative multi-source incident deduplication, rule-based P0–P3 triage explainability, and strictly **human-authorized dispatch**.

---

## Architectural Principle: Perception vs. Policy

```
[ Citizen Voice SOS / IVR Call / SMS / Radio / Field App ]
                           │
                           ▼
             SENSORY PERCEPTION (Probabilistic)
     ┌─────────────────────────────────────────────────┐
     │  Gnani Prisma v3.0 STT (10 Indian Languages)    │
     │  Gnani Timbre v3.0 TTS (Neural Voice Guidance)  │
     │  Energy-based VAD (Silence / Boundary Detect)   │
     │  Whisper Recognizer (Local Offline Fallback)    │
     └─────────────────────────────────────────────────┘
                           │
                 Transcribed Text & Audio Spans
                           │
                           ▼
          DETERMINISTIC SAFETY POLICY (Zero Hallucination)
     ┌─────────────────────────────────────────────────┐
     │  Regex & Keyword Fact Extraction                │
     │  PostGIS Spatial Disambiguation (Bounding Radii)│
     │  Conservative Entity Deduplication (Incident)   │
     │  Safety-First Triage Rules (P0 to P3)           │
     │  "Unknown never lowers priority" invariant      │
     └─────────────────────────────────────────────────┘
                           │
                           ▼
               HUMAN DISPATCHER INTERFACE
     ┌─────────────────────────────────────────────────┐
     │  Operator Console (Reports Inbox, Leaflet Map)  │
     │  1-Click Dispatch Authorization & Unit Assign   │
     │  Tamper-Evident SHA-256 Chained Audit Trail     │
     └─────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Safety Guarantee**: In Raahat, generative models never make autonomous triage or dispatch decisions. Stochastic models are strictly confined to transcribing speech waveforms into text. All life-critical operational actions require authenticated human approval.

---

## Key Features

- **Multilingual Emergency Helpline (`/sos/call.html`)**: Real-time interactive in-browser voice helpline powered by Gnani Prisma v3.0 STT and Gnani Timbre TTS. Follows an explainable 4-stage dialog state machine with automatic number read-back and DTMF keypad fallback.
- **Citizen SOS Web Portal (`/sos/`)**: Mobile-first bilingual (Hindi/English) single-tap voice note recorder (`MediaRecorder`) and 1-click GPS location sharing.
- **Live Rescue Ticket Tracker (`/sos/track.html`)**: Real-time 4-stage status stepper (`received` → `processing` → `triaged` → `dispatched`) polling every 3 seconds.
- **PostGIS Spatial Landmark Gazetteer**: Resolves vernacular landmarks to geographic candidate points with explicit uncertainty circles rather than fabricated precision.
- **Explainable Triage Engine**: Assigns P0 (Critical/Life-Threatening) through P3 (Informational/Low) based on deterministic safety rules. Preserves unknown fields so missing data never lowers rescue priority.
- **Dispatcher Operations Console (`/console/`)**: Live situation map (Leaflet.js) with real-time SSE updates, reports inbox, incident investigation pane, and audit log inspector.
- **Tamper-Evident Audit Trail**: Every status transition, incident merge, and dispatch authorization writes an immutable, SHA-256 hash-chained `AuditEvent`.
- **Offline-First Field Client (`field_app/`)**: Local SQLite-backed sync client for rescue volunteers operating in zero-connectivity zones.

---

## Repository Structure

```
.
├── src/raahat/               # Core Python package
│   ├── domain/               # Pure domain models (reports, triage, incidents, geospatial)
│   ├── application/          # Application orchestrators (ingestion, resolution, workflow)
│   ├── infrastructure/       # PostgreSQL/PostGIS, outbox, audit, speech (Prisma, Timbre, Whisper)
│   ├── adapters/             # Channel adapters (IVR call agent, SMS, web, volunteer sync)
│   ├── api/                  # FastAPI routes, middleware, dependencies
│   └── workers/              # Transactional outbox runner, background audio processor
├── citizen_portal/           # Mobile web SOS and interactive voice helpline (/sos/)
│   ├── public/               # index.html (SOS form), call.html (Helpline), track.html (Tracker)
│   └── src/                  # Audio recorder, geolocation, and Web Audio call orchestration
├── operator_console/         # Dispatcher web dashboard (/console/)
├── field_app/                # Offline field worker SQLite client
├── demo/                     # Scenario runner, audio samples (Kerala 2018 archival & contest)
├── docs/                     # Runbooks, model card, limitations, operations, security
├── scripts/                  # Data seeders, contest audio generators, terminal demo runner
└── tests/                    # 457 unit, integration, concurrency, and evaluation tests
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose **OR** Python 3.10+ with PostgreSQL 16 + PostGIS
- (Optional) Gnani.ai API Key (`GNANI_API_KEY_TTS_STT`) for live cloud STT/TTS

### 1. Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-org/raahat.git
cd raahat

# Configure environment (optional: add Gnani API key for live voice)
cp .env.example .env

# Start all services (PostgreSQL, PostGIS, API, Citizen Portal, Operator Console)
docker compose up -d

# Verify health
curl -s http://localhost:8080/health | python3 -m json.tool

# Seed demo disaster data (Kerala Floods 2018 landmarks & resources)
PYTHONPATH=src python3 scripts/seed_demo_data.py
```

### 2. Local Python Development Setup

```bash
# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Ensure local PostgreSQL + PostGIS is running and apply migrations
alembic upgrade head

# Seed initial scenario data
PYTHONPATH=src python3 scripts/seed_demo_data.py

# Start development server
PYTHONPATH=src uvicorn raahat.api.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## Application URLs

| Interface | URL (Docker) | URL (Local Dev) | Description |
|---|---|---|---|
| **Citizen SOS Form** | `http://localhost:8080/sos/` | `http://localhost:8000/sos/` | 1-tap voice note & GPS submission |
| **Interactive Helpline** | `http://localhost:8080/sos/call.html` | `http://localhost:8000/sos/call.html` | Live browser mic emergency voice call |
| **Ticket Tracker** | `http://localhost:8080/sos/track.html` | `http://localhost:8000/sos/track.html` | Citizen rescue request status |
| **Operator Console** | `http://localhost:8080/console/` | `http://localhost:8000/console/` | Dispatcher inbox & live situation map |
| **API Documentation** | `http://localhost:8080/docs` | `http://localhost:8000/docs` | Interactive OpenAPI Swagger UI |

---

## Live Demo & Evaluation

For full click-by-click instructions, video script, and evaluation steps, see the **[Demo Runbook](docs/demo_runbook.md)** and **[System Model Card](docs/model_card.md)**.

### Run Automated Scenario
```bash
# Ingests Kerala 2018 audio clips, transcribes, triages, and prepares dispatch
PYTHONPATH=src python3 demo/run_scenario.py --disaster "Kerala Floods 2018 — Raahat Demo"
```

### Run 8-Milestone Presentation Terminal Runner
```bash
# Interactive terminal walkthrough demonstrating all platform capabilities
PYTHONPATH=src python3 scripts/demo_run.py --dry-run
```

### Generate Contest Audio Suite
```bash
# Synthesizes 4 target audio clips (Hinglish, Hindi, Malayalam, Marathi)
PYTHONPATH=src python3 scripts/generate_contest_audio.py
```

---

## Testing & Verification

The codebase maintains strict typing (`mypy`), linting (`ruff`), and comprehensive automated test coverage:

```bash
# Run all unit and integration tests (457 tests)
PYTHONPATH=src pytest -p no:launch_testing_ros_pytest_entrypoint -q

# Run type checker
mypy src/raahat field_app evaluation tests scripts

# Run linter
ruff check .
```

---

## Architectural Documentation

- **[System Model Card](docs/model_card.md)**: Specifications for Gnani Prisma v3.0, Timbre TTS, VAD, triage safety policies, and model limitations.
- **[Demo Presentation Runbook](docs/demo_runbook.md)**: 60-second video recording script, 8-milestone live presentation walkthrough, and credit budget guidelines.
- **[Architecture & Decision Log](ARCHITECTURE.md)**: Module boundaries, architectural invariants, and historical decisions.
- **[Operations Runbook](docs/operations_runbook.md)**: Deployment, scaling, monitoring, and backup procedures.
- **[Security Policy](docs/security.md)**: Threat model, authentication, cryptographic audit hashing, and data protection.
- **[System Limitations](docs/limitations.md)**: Documented failure modes, operational constraints, and edge cases.

---

## License

This project is licensed under the Apache 2.0 License.
