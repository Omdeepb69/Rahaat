# Raahat 2.0 (राहत)

**Uncertainty-Aware, Offline-Resilient Disaster Intelligence & Emergency Triage Engine**

Built for coordinated flood and emergency crisis response across India, powered by Gnani.ai's Indic speech & reasoning models.

[![Tests](https://img.shields.io/badge/tests-457%20passing-brightgreen)](#testing--verification)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Database](https://img.shields.io/badge/database-PostgreSQL%2016%20%2B%20PostGIS-blue)](https://postgis.net/)
[![Gnani Speech](https://img.shields.io/badge/Gnani.ai-Prisma%20v3.0%20%7C%20Timbre-orange)](https://gnani.ai/)
[![Gnani Reasoning](https://img.shields.io/badge/Gnani.ai-Evon%20v3.3%2030B-purple)](https://huggingface.co/gnani)

---

## Overview

During major flood disasters (such as the 2018 Kerala floods or urban inundations), emergency helplines and 1077 control rooms are overwhelmed with thousands of simultaneous distress calls. Conventional systems fail because:
1. **Dialect and acoustic noise**: Callers speak regional languages (Malayalam, Marathi, Hindi) mixed with English (Hinglish) under severe emotional stress and heavy rain/water noise.
2. **Ambiguous vernacular locations**: Victims report colloquial landmarks ("near St. Thomas church, ward 4", "near Chalakudy bridge") rather than GPS coordinates.
3. **Black-box AI risks**: Autonomous generative models can hallucinate victim counts or fabricate coordinates, creating fatal rescue failures.
4. **Network collapse**: Cellular infrastructure fails during severe floods, cutting off cloud-only platforms.

**Raahat 2.0** solves these challenges with an unbreachable architectural boundary:
- **Sensory Perception**: Fast, multilingual Indic speech transcription via **Gnani Prisma v3.0** (`indic-auto`), natural regional voice synthesis via **Gnani Timbre** (`Shivani` neural voice), and zero-shot disaster fact extraction via **Gnani Evon v3.3** (`gnani/gnani-evon-v3.3-30B-A3B`).
- **Deterministic Decision Policy**: Spatial landmark grounding with PostGIS trigram matching (`similarity >= 0.25`) and uncertainty radius circles ($\pm150\text{m}$), conservative multi-source incident deduplication, rule-based P0–P3 triage explainability, and strictly **1-click human commander authorization**.

---

## Architectural Principle: Perception vs. Policy

```
[ Citizen Voice SOS / IVR Call 1077 / SMS / Radio / Field App ]
                           │
                           ▼
             SENSORY PERCEPTION (Probabilistic)
     ┌─────────────────────────────────────────────────┐
     │  Gnani Prisma v3.0 STT (10 Indian Languages)    │
     │  Gnani Timbre v3.0 TTS (Neural Voice Guidance)  │
     │  Gnani Evon v3.3 (30B Indic Disaster Schema LLM)│
     │  Energy-based VAD (Silence / Boundary Detect)   │
     │  Whisper Recognizer (Local Offline Fallback)    │
     └─────────────────────────────────────────────────┘
                           │
                 Transcribed Text & Extracted Entities
                           │
                           ▼
          DETERMINISTIC SAFETY POLICY (Zero Hallucination)
     ┌─────────────────────────────────────────────────┐
     │  PostGIS Spatial Grounding (Trigram + Bounding) │
     │  NLP Centroid District Fallback (Zero Dropouts) │
     │  Conservative Entity Deduplication (Incident)   │
     │  Safety-First Triage Rules (P0 to P3)           │
     │  "Unknown never lowers priority" invariant      │
     └─────────────────────────────────────────────────┘
                           │
                           ▼
               HUMAN COMMANDER INTERFACE
     ┌─────────────────────────────────────────────────┐
     │  Operator Console & Tactical Triage Dashboard   │
     │  1-Click Dispatch Authorization & Unit Assign   │
     │  Tamper-Evident SHA-256 Chained Audit Trail     │
     └─────────────────────────────────────────────────┘
```

> **Safety Invariant**: Generative models never make autonomous triage or dispatch decisions. Stochastic models are strictly confined to understanding speech waveforms into structured text schema. All life-critical operational actions require authenticated human approval.

---

## Key Capabilities

- **Multilingual Emergency Helpline (`/sos/call.html`)**: Real-time interactive in-browser voice helpline powered by **Gnani Prisma v3.0 STT** and **Gnani Timbre TTS**. Follows an explainable dialog state machine with dynamic fact extraction powered by **Gnani Evon v3.3**.
- **Tactical Command Dashboard (`/dashboard/`)**: Modern React + TypeScript situational awareness HUD featuring live incident heatmaps, P0–P3 priority queues, rescue fleet deployment, and real-time SSE updates.
- **Citizen SOS Web Portal (`/sos/`)**: Mobile-first bilingual (Hindi/English) single-tap voice note recorder (`MediaRecorder`) and 1-click GPS location sharing.
- **Live Rescue Ticket Tracker (`/sos/track.html`)**: Real-time 4-stage status stepper (`received` → `processing` → `triaged` → `dispatched`) polling every 3 seconds.
- **PostGIS Spatial Landmark Gazetteer**: Resolves vernacular landmarks to geographic candidate points with explicit uncertainty circles rather than fabricated precision.
- **Explainable Triage Engine**: Assigns P0 (Critical/Life-Threatening) through P3 (Informational/Low) based on deterministic safety rules. Preserves unknown fields so missing data never lowers rescue priority.
- **Tamper-Evident Audit Trail**: Every status transition, incident merge, and dispatch authorization writes an immutable, SHA-256 hash-chained `AuditEvent`.
- **Offline-First Field Client (`field_app/`)**: Local SQLite-backed sync client for rescue volunteers operating in zero-connectivity zones.

---

## Repository Structure

```
.
├── src/raahat/               # Core Python package
│   ├── domain/               # Pure domain models (reports, triage, incidents, geospatial)
│   ├── application/          # Application orchestrators (ingestion, resolution, workflow)
│   ├── infrastructure/       # PostgreSQL/PostGIS, outbox, audit, speech (Prisma, Timbre, Evon)
│   ├── adapters/             # Channel adapters (IVR call agent, SMS, web, volunteer sync)
│   ├── api/                  # FastAPI routes, middleware, dependencies
│   └── workers/              # Transactional outbox runner, background audio processor
├── dashboard/                # Modern React + Vite Tactical Commander HUD (/dashboard/)
├── citizen_portal/           # Mobile web SOS and interactive voice helpline (/sos/)
├── operator_console/         # Lightweight emergency dispatcher console (/console/)
├── field_app/                # Offline field worker SQLite client
├── scripts/                  # Data seeders and scenario runners
├── deployment/               # Nginx reverse proxy configuration
└── tests/                    # 457 unit, integration, concurrency, and chaos tests
```

---

## Quick Start

### 1. Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/Omdeepb69/Rahaat.git
cd Rahaat

# Configure environment
cp .env.example .env

# Start all services (PostgreSQL, PostGIS, FastAPI, Nginx Proxy, Worker)
docker compose up -d

# Verify health
curl -s http://localhost:8080/healthz

# Seed demonstration scenario (Thrissur / Chalakudy floods, landmarks, rescue units)
docker exec raahat-api python -m scripts.seed_demo_data
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
PYTHONPATH=src python3 -m scripts.seed_demo_data

# Start development server
PYTHONPATH=src uvicorn raahat.api.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## Application Interfaces

| Interface | URL (Docker) | Description |
|---|---|---|
| **Tactical Dashboard** | `http://localhost:8080/dashboard/` | Command HUD, P0 triage queue & resource map |
| **Interactive Helpline** | `http://localhost:8080/sos/call.html` | Live browser mic 1077 emergency voice call |
| **Citizen SOS Form** | `http://localhost:8080/sos/` | 1-tap voice note & GPS submission |
| **Ticket Tracker** | `http://localhost:8080/sos/track.html` | Citizen rescue request status |
| **Operator Console** | `http://localhost:8080/console/` | Dispatcher inbox & live situation map |
| **API Documentation** | `http://localhost:8080/docs` | Interactive OpenAPI Swagger UI |

### Demonstration Credentials
- **Role**: Duty Officer - Thrissur DEOC
- **Username**: `KeralaThrissur2026#`
- **Password**: `KeralaThrissur2026#`

---

## Testing & Verification

The codebase maintains strict typing (`mypy`), linting (`ruff`), and comprehensive automated test coverage:

```bash
# Run unit and integration tests (457 tests)
PYTHONPATH=src pytest -q

# Run type checker
mypy src/raahat

# Run linter
ruff check .
```

---

## License

This project is licensed under the Apache 2.0 License.
