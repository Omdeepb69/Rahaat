# Raahat 2.0 — System Model Card

**Version**: 2.0.0-rc1  
**Date**: November 2026  
**Maintainer**: Raahat project team  
**Repository**: `/mnt/data/projects/rahaat`

---

## 1. What Raahat Is

Raahat is a **disaster intelligence and rescue coordination platform** designed for Indian flood-response operations. It ingests distress reports from multiple channels — interactive voice (IVR), web SOS form, SMS, radio operator consoles, and offline field devices — and maintains a shared operational picture for human rescue dispatchers.

**Primary users**: Trained human disaster response dispatchers (NDRF, SDRF, municipal emergency centres)  
**Primary failure mode it guards against**: Dispatcher cognitive overload when thousands of simultaneous distress calls arrive  
**What it does NOT do**: Autonomously dispatch rescue units. Every operational action requires human authorization.

---

## 2. Architecture Principle: Perception vs. Policy

> [!IMPORTANT]
> This boundary is load-bearing. It is not a marketing claim; it is an architectural invariant
> enforced in code (see `ARCHITECTURE.md` §Decisions Log — 2026-11-08).

| Layer | Technology | Role | Stochastic? |
|---|---|---|---|
| **Speech perception** | Gnani Prisma v3.0 (STT) | Audio waveform → text transcript | Yes — probabilistic ASR |
| **Speech perception** | Acoustic energy VAD | Silence detection, segment boundary | Yes — energy threshold |
| **Speech synthesis** | Gnani Timbre v3.0 (TTS) | Text → agent voice audio | Yes — neural synthesis |
| **Fact extraction** | Deterministic regex + keyword rules | Transcript → structured facts (location, count, needs) | **No** |
| **Location disambiguation** | PostGIS spatial index + haversine | Landmark candidates + uncertainty bounds | **No** |
| **Triage** | Explicit safety policy (P0–P3 rules) | Priority assignment | **No** |
| **Incident matching** | Conservative entity resolution rules | Report → incident deduplication | **No** |
| **Dispatch** | Human dispatcher + audit logger | Resource assignment | **No — requires human** |

**Why this division matters**: Stochastic generative models can produce confident-sounding incorrect outputs. In disaster operations, a hallucinated GPS location or a fabricated headcount can send a rescue boat to the wrong street. The Raahat architecture confines probabilistic models to transcribing speech sounds into words, and applies only deterministic, human-readable rules to those words for every safety-critical decision.

---

## 3. Speech Perception — Gnani Prisma v3.0 (STT)

**Adapter**: [`src/raahat/infrastructure/speech/prisma.py`](../src/raahat/infrastructure/speech/prisma.py)  
**API endpoint**: `POST https://api.vachana.ai/stt/v3`  
**Model**: `prisma-v3.0`

### Capabilities

- Languages: 10 Indian languages + Hinglish/code-mixed
- Language detection: `indic-auto` (automatic, no manual selection required)
- Format: `transcribe` — Inverse Text Normalization enabled (numbers → digits, currency → ₹)
- Context boosting: `keyterms` JSON array (up to 200 terms) — Raahat seeds emergency vocabulary
- Topic hint: `"Disaster emergency distress call, flood rescue, trapped people"`
- Max audio per request: 30 seconds (REST endpoint)

### Emergency Keyterms Seeded

```
नाव, boat, NDRF, Shaniwar Wada, Bund Garden, Alappuzha, Ernakulam,
paani, vellam, trapped, madat, rescue, hospital, oxygen, first floor, chhat
```

### Supported Language Codes

| Spoken | Code |
|---|---|
| Hindi | `hi-IN` |
| English (Indian) | `en-IN` |
| Malayalam | `ml-IN` |
| Marathi | `mr-IN` |
| Tamil | `ta-IN` |
| Telugu | `te-IN` |
| Kannada | `kn-IN` |
| Bengali | `bn-IN` |
| Gujarati | `gu-IN` |
| Punjabi | `pa-IN` |
| Hinglish / auto | `indic-auto` |

### Fallback Behaviour

When no API key is present (`GNANI_API_KEY_TTS_STT` unset), `PrismaRecognizer.transcribe()` returns an empty `Transcript` with zero segments. The IVR state machine then uses the low-confidence fallback path (keypad input) rather than crashing.

### Known Limitations

- Maximum 30 seconds audio per request (REST). Longer audio must be chunked or use the streaming WebSocket endpoint (not currently wired).
- Accuracy degrades on very high background noise (>30 dB SNR degradation).
- Language detection `indic-auto` may misclassify very short utterances (< 2 seconds).
- Transcripts carry no word-level timestamps in the current API version.

---

## 4. Speech Synthesis — Gnani Timbre v3.0 (TTS)

**Adapter**: [`src/raahat/infrastructure/speech/timbre.py`](../src/raahat/infrastructure/speech/timbre.py)  
**API endpoint**: `POST https://api.vachana.ai/api/v1/tts/inference`  
**Model**: `timbre-v3.0`  
**Default voice**: `Shivani`  
**Available voices**: `Shivani` (female, Hindi-accented), `Avinash` (male), `Lakshmi` (female, South Indian accent)  
**Output**: Raw WAV bytes, 16000 Hz, mono

### Supported Languages

All 10 Indian languages above, plus `hi-en` (Hinglish) and `auto` (automatic).

### Usage in IVR

Agent prompts are synthesized on every turn and returned as base64-encoded WAV in the API response. The browser decodes and plays them via the Web Audio API.

### Fallback Behaviour

When no API key is present, `GnaniTimbreTTS.synthesize()` returns 44 bytes of valid WAV header with no audio content (silent). The IVR continues; the browser plays silence. The dispatcher or demo operator can still use the text fallback.

---

## 5. Local Speech Fallback — Whisper (Offline)

**Adapter**: [`src/raahat/infrastructure/speech/whisper_recognizer.py`](../src/raahat/infrastructure/speech/whisper_recognizer.py)  
**Model**: OpenAI Whisper (local, CPU/GPU)

Used as a fallback recognizer in the background audio processing worker (`report_processor.py`) when Prisma is unavailable. Whisper produces an uncalibrated confidence score; Raahat tags these transcripts with `provenance=whisper_fallback` and sets `confidence_calibrated=False` to prevent their scores from being displayed as probabilities.

---

## 6. Voice Activity Detection (VAD)

**Implementation**: [`src/raahat/infrastructure/speech/vad.py`](../src/raahat/infrastructure/speech/vad.py)  
**Method**: Energy-based threshold (`EnergyVADDetector`)

The VAD gate determines whether an incoming audio buffer contains speech before invoking the more expensive Prisma API. If VAD detects only silence:
- The system does not make an API call.
- The IVR agent is informed of a silence turn.
- After 2 consecutive silence turns, the agent offers the DTMF keypad fallback.

This is an intentional credit conservation mechanism, not a Silero model (which was considered but not installed — see `ARCHITECTURE.md`).

---

## 7. IVR State Machine — Interactive Voice Helpline

**Implementation**: [`src/raahat/adapters/channels/ivr/agent.py`](../src/raahat/adapters/channels/ivr/agent.py)  
**API routes**: [`src/raahat/api/routes/ivr.py`](../src/raahat/api/routes/ivr.py)  
**Web UI**: [`citizen_portal/public/call.html`](../citizen_portal/public/call.html)

### State Machine

```
INIT
  └─► AWAITING_LOCATION
        ├─► (confidence ok) AWAITING_PEOPLE_COUNT
        │     ├─► (spoken count parsed) AWAITING_PEOPLE_COUNT_READBACK
        │     │     ├─► (confirmed) AWAITING_NEEDS
        │     │     │     └─► COMPLETED
        │     │     └─► (rejected) AWAITING_PEOPLE_COUNT
        │     └─► (VAD silence) AWAITING_PEOPLE_COUNT
        └─► (2× low-conf) AWAITING_LOCATION_KEYPAD
              └─► AWAITING_PEOPLE_COUNT
```

### Session Storage

Sessions are stored in-memory (`dict[str, IVRCallSession]`). They do not survive a server restart. For the demo this is acceptable. A production deployment would use Redis or database-backed sessions.

### Maximum Turns

Default: 10 turns. If the caller exceeds the maximum without completing the flow, the session is force-completed with whatever information has been collected.

### On Completion

1. The collected `IVRSubmission` (location text, people count, needs) is passed to `ReportIngestionService.ingest()`.
2. The returned `report_id` is passed to `AutomatedAudioTriageWorkflow.run_for_report()`.
3. The workflow extracts facts, resolves location, runs triage, assigns nearest unit.
4. The API response includes `incident_id`, `priority` (P0–P3), `proposed_resource_name`.

---

## 8. Fact Extraction

**Implementation**: [`src/raahat/application/triage/`](../src/raahat/application/triage/)

Fact extraction uses deterministic keyword and regex rules applied to the Prisma transcript. No LLM is involved.

Extracted fields:
- `location_text` — raw spoken location string
- `people_count` — integer parsed from spoken headcount (Hindi numerals supported)
- `has_medical_emergency` — bool (keyword detection: hospital, oxygen, diabetes, insulin, etc.)
- `has_children` — bool
- `water_level_text` — raw descriptor (waist-high, roof, etc.)
- `needs` — list of detected need types (boat, food, medicine, shelter)

**Unknown preservation invariant**: If a field is not mentioned in the transcript, it remains `None` — not defaulted to `False`. A missing medical mention does NOT mean no medical need. The triage rule engine treats unknown fields conservatively (they never lower the priority).

---

## 9. Priority Triage — P0 to P3

**Implementation**: [`src/raahat/domain/triage/`](../src/raahat/domain/triage/)

Priority is assigned by a strict rule tree:

| Priority | Rule |
|---|---|
| **P0** | Medical emergency AND/OR 3+ persons AND/OR structural collapse |
| **P1** | Multiple persons trapped, no confirmed medical emergency |
| **P2** | Single person, non-critical, no children |
| **P3** | Resource request, no persons confirmed trapped |

**Unknown never lowers priority**: Missing fields default to the most conservative (highest) priority applicable.

The P0–P3 scheme is designed to satisfy the safety policy that it is always better to dispatch unnecessarily than to fail to dispatch.

---

## 10. Location Disambiguation

**Implementation**: [`src/raahat/application/location/`](../src/raahat/application/location/)  
**Data**: PostGIS spatial index of disaster-specific landmark gazetteer

Location disambiguation:
1. Extracts candidate landmark mentions from the transcript.
2. Queries the PostGIS gazetteer for fuzzy landmark matches within the disaster's operational bounding box.
3. Returns up to 3 candidate hypotheses, each with: landmark name, centroid coordinate, uncertainty radius (metres), and evidence span (the exact substring that produced the match).
4. The UI displays uncertainty circles — not false-precision point markers.

**When no match is found**: The system records `location_text` as the raw string and flags `location_resolved = False`. The dispatcher is shown a clarification prompt. The system never fabricates a coordinate.

---

## 11. Entity Resolution — Incident Deduplication

**Implementation**: [`src/raahat/application/incident_resolution/`](../src/raahat/application/incident_resolution/)

Multiple reports about the same household are merged into a single canonical `Incident`. The matcher uses conservative rules:
- Geographic proximity (< configurable radius, default 100m)
- Matching disaster ID
- Time window (< 2 hours)
- No merge unless spatial hypothesis centroids overlap

The matcher does not use embedding similarity or LLM judgment. When uncertain, it creates a new candidate incident for human review rather than merging incorrectly.

---

## 12. Dispatch & Human-in-the-Loop

**Implementation**: [`src/raahat/application/dispatch/`](../src/raahat/application/dispatch/)

Resource assignment is suggested by the system (nearest capable unit within the disaster's resource inventory), but **every assignment requires explicit human dispatcher authorization** via:
- Operator console button "Authorize Dispatch"
- API: `POST /api/v1/incidents/{id}/authorize-dispatch`

Raahat never autonomously commits a dispatch action. The rationale: incorrect autonomous dispatch in a disaster can send the only available boat to the wrong location, causing preventable deaths. Human oversight is not a limitation — it is the system's explicit safety contract.

---

## 13. Audit Trail

**Implementation**: [`src/raahat/infrastructure/audit/`](../src/raahat/infrastructure/audit/)

Every state transition is recorded as an immutable `AuditEvent` with:
- Event type, actor (dispatcher ID or system), timestamp
- SHA-256 hash of the previous event (cryptographic chain)
- Incident ID, report ID, resource ID as applicable

Audit records cannot be modified or deleted via the application API. Direct database tampering breaks the hash chain and is detectable.

---

## 14. Offline Resilience

The platform is designed with the assumption that flood events disrupt cellular and internet infrastructure.

| Component | Offline capability |
|---|---|
| Field volunteer app | SQLite-backed, full offline operation with sync queue |
| Citizen SOS portal | Requires connectivity (web app) |
| IVR helpline | Requires connectivity to API server |
| Operator console | Requires connectivity to API server |
| Local Whisper fallback | Runs on-device, no API calls needed |
| PostGIS gazetteer | Local database, no external map API |

---

## 15. Known Limitations

| Limitation | Detail |
|---|---|
| IVR session persistence | In-memory only — sessions lost on server restart |
| Max Prisma audio per request | 30 seconds (REST endpoint) |
| Fact extraction language scope | Keyword rules tuned for Hindi, Hinglish, Malayalam, Marathi; other languages produce lower extraction recall |
| Map coordinates | Incidents without resolved PostGIS matches render at a fallback position |
| No real-time telephony | The helpline is browser-microphone only (no Twilio/SIP/PSTN integration) |
| Whisper model | Not pre-loaded in Docker image by default — must be downloaded on first run |
| TTS credits | Timbre TTS consumes Gnani API credits; each IVR turn synthesizes one prompt |
| Concurrency | The in-memory session store is not thread-safe for multi-process deployments |

---

## 16. What This System Is NOT

- **Not an autonomous AI dispatcher**: Every rescue assignment requires human approval.
- **Not an LLM-powered chatbot**: The IVR agent is a deterministic state machine. It does not "understand" language generatively — it transcribes speech via Prisma and applies keyword rules.
- **Not a production telephony system**: The IVR operates over WebRTC-style browser microphone, not a PSTN phone line.
- **Not a real-time GPS tracker**: Location estimates carry explicit uncertainty bounds, not precision coordinates.
- **Not a certified disaster management system**: Raahat is a research and demonstration platform. It has not undergone operational certification for deployment in live emergency management operations.

---

## 17. Contest-Specific Capabilities (Gnani AI Internship Challenge)

| Prize category | Raahat capability |
|---|---|
| Regional language support | Prisma v3.0 `indic-auto` — Malayalam, Marathi, Hindi, Hinglish, 7 others |
| Hinglish / code-mixed audio | Native `hi-en` language code; `codemix` output format available |
| Noisy telephonic audio | Emergency keyterm boosting; topic hint; `format=transcribe` ITN |
| Real-world impact | Disaster rescue coordination for 2018-pattern Kerala flood events |
| Best 60-second demo | Full voice→triage→dispatch→audit pipeline demonstrable in < 60 seconds |

---

## 18. Credits & Attributions

- **Gnani Prisma v3.0** — STT model and API by [Gnani.ai](https://gnani.ai)
- **Gnani Timbre v3.0** — TTS model and API by [Gnani.ai](https://gnani.ai)
- **OpenAI Whisper** — Local fallback ASR (MIT License)
- **PostGIS** — Spatial database extension (GPLv2)
- **Leaflet.js** — Map rendering (BSD 2-Clause)
- **FastAPI** — Web framework (MIT License)
- **Kerala Floods 2018 reference audio** — Archival oral history recordings, Christ College Irinjalakuda DSpace repository (oral history interviews — not victim calls; used only for acoustic reference, not as training data)

