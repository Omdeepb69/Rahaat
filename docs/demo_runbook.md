# Raahat 2.0 — Demo Runbook

**Contest**: Gnani.ai Great Indian AI Internship Challenge (deadline: November 10, 2026)  
**Target presentation**: 60-second public demo video + live interactive showcase

---

## Pre-Demo Checklist

Run these commands before recording or presenting. All commands run from the project root.

```bash
# 1. Start the full stack (PostgreSQL + PostGIS + API server)
docker compose up -d

# 2. Wait for the API server to be healthy
curl -s http://localhost:8080/health | python3 -m json.tool

# 3. Seed the Kerala Floods 2018 disaster and demo data
PYTHONPATH=src python3 scripts/seed_demo_data.py

# 4. (Optional) Run the automated scenario to pre-populate incidents on the map
PYTHONPATH=src python3 demo/run_scenario.py --disaster "Kerala Floods 2018 — Raahat Demo"

# 5. Verify test suite is green before you go on camera
PYTHONPATH=src pytest -p no:launch_testing_ros_pytest_entrypoint -q --tb=short
```

> [!IMPORTANT]
> The API key `GNANI_API_KEY_TTS_STT` must be set in `.env` **before** starting the stack
> for real Prisma v3.0 STT and Timbre TTS to activate. Without a key both adapters
> fall back to silent mode (empty transcript / silent audio) so the IVR still runs.

```bash
# Confirm key is loaded (should print the key prefix, not empty)
grep GNANI_API_KEY_TTS_STT .env | head -c 60
```

**Local dev alternative (no Docker)**:

```bash
# Start local server directly
PYTHONPATH=src uvicorn raahat.api.app:app --port 8000 --reload
# Then use http://localhost:8000 for all URLs below
```

---

## Endpoints Reference

| Component | URL |
|---|---|
| Citizen SOS portal | `http://localhost:8080/sos/` |
| Interactive voice helpline | `http://localhost:8080/sos/call.html` |
| Operator console | `http://localhost:8080/console/` |
| Situation map | `http://localhost:8080/console/#map` |
| REST API root | `http://localhost:8080/api/v1/` |
| OpenAPI docs | `http://localhost:8080/docs` |

---

## 60-Second Demo Video Script

> This script is word-for-word for a screen-recorded video. Record at 1920×1080. Use a phone camera or microphone for the voice segments.

---

**[0:00–0:08] Hook — the problem**

> *Show a photo of flooded streets (Kerala 2018, credited).*

Narrator (voice over):
> "In a disaster, thousands call for help simultaneously. Dispatchers are overwhelmed. Every second of delay costs lives. Meet Raahat — an AI-powered rescue coordination platform built for India."

---

**[0:08–0:18] Live Voice Call — Citizen SOS**

> *Open `http://localhost:8080/sos/call.html` in browser. Click "Start Call".*

Narrator:
> "A citizen trapped in Alappuzha opens the web SOS page and speaks in Malayalam."

> *Click the microphone button. Speak (or play back pre-recorded audio `demo/audio/contest_showcase/03_malayalam_alappuzha_boat.wav`)*:

**Sample distress phrase (Malayalam)**:
> "Ente veetil vellam keri. Randu per kuttiyum oru athiyayum undu. Boat venam."

Narrator:
> "Prisma v3.0 — Gnani's multilingual STT — transcribes Malayalam in real time, even over noisy telephony audio."

> *Point camera at the transcript that appears in the chat bubble.*

---

**[0:18–0:30] AI Helpline Conversation**

> *The agent voice (Timbre TTS — Gnani) responds in Hindi:*

Agent response (Timbre voice):
> "Namaste. Mujhe aapki baat sun rahi hoon. Kitne log hain aapke saath?"

Narrator:
> "The IVR agent confirms the location, counts the people trapped, asks for their immediate needs — all in Hinglish. The state machine is fully deterministic. No LLM hallucination risk."

> *Demonstrate one more turn — speak headcount in Hindi: "Teen log hain, ek burai ho rahi hai".*

---

**[0:30–0:40] Automatic Triage on the Operator Console**

> *Switch to `http://localhost:8080/console/`.*

Narrator:
> "The call completes. Raahat creates a report, extracts location and medical facts, and runs the safety policy triage engine."

> *Point to a P0 incident card appearing in the inbox.*

Narrator:
> "Three people, medical emergency, water rising — that's a P0 — Priority Zero — the highest severity. Completely rule-based. Explainable. Auditable."

---

**[0:40–0:50] Spatial Disambiguation on Live Map**

> *Click on the incident to open the investigation pane. Click over to the Situation Map tab.*

Narrator:
> "PostGIS resolves the landmark 'Alappuzha canal' with a 500-metre uncertainty bounding circle. The dispatcher sees exactly where confidence ends — no fabricated GPS precision."

> *Point to the circle on the Leaflet map.*

---

**[0:50–0:58] 1-Click Dispatch & Audit**

> *Click "Authorize Dispatch". A toast notification confirms the assignment.*

Narrator:
> "The dispatcher clicks Authorize. NDRF Boat Unit 3 is assigned. A cryptographic audit trail records who approved it and when — immutable, tamper-evident."

---

**[0:58–1:00] Close**

Narrator:
> "Raahat 2.0. Prisma v3.0. Timbre. Built for India. Built for real disasters. Built to save lives."

> *Fade to Raahat logo or project title card.*

---

## Live Interactive Demo — Click-by-Click Walkthrough (8 Milestones)

For a live conference or evaluator walkthrough, follow these eight milestones in order. Budget approximately 5–7 minutes.

### Milestone 1 — Citizen SOS Form (`/sos/`)

1. Open `http://localhost:8080/sos/`.
2. Grant location permission when the browser prompts.
3. Click the red microphone button. Record 10–15 seconds of distress in Hindi or Hinglish.
4. Fill in distress type checkboxes: `Water Rising`, `Medical Emergency`.
5. Click **Submit SOS**.
6. The browser redirects to the ticket tracker (`/sos/track.html?id=<report_id>`).
7. Watch the stepper advance: `Received → Processing → Triaged`.

**What to say on camera**: "Citizens anywhere with a smartphone can submit a voice SOS — no app install needed. The portal works in Hindi and English. Location is shared with one click."

---

### Milestone 2 — Interactive Voice Helpline (`/sos/call.html`)

1. Open `http://localhost:8080/sos/call.html` in a fresh tab.
2. Select language: `Hinglish / Auto`.
3. Click **Start Call**. The page connects to `POST /api/v1/ivr/calls/start`.
4. The agent (Timbre TTS) plays its opening greeting as audio.
5. Click the microphone button and speak your location.
6. Click **Stop** — the recording is sent to `POST /api/v1/ivr/calls/{call_sid}/turn`.
7. Prisma v3.0 transcribes. The agent responds in Timbre voice.
8. Continue through 4 turns: location → people count → readback confirm → needs.
9. On completion, a dispatch card appears with Incident ID, Priority, and assigned unit.

**What to say on camera**: "This is an actual AI-powered emergency helpline in a web browser. The microphone audio goes to Gnani Prisma v3.0, transcript comes back, the IVR state machine decides what to ask next, Timbre synthesizes the response, and it plays back — end to end, in real time."

> [!NOTE]
> If the API key is not set, the agent still runs — the transcript will be empty and
> the TTS audio will be silent. Use the **Text fallback** input to simulate a full
> conversation without consuming credits.

---

### Milestone 3 — Reports Inbox (Operator Console)

1. Open `http://localhost:8080/console/`.
2. Navigate to the **Reports** tab.
3. The IVR-completed call appears as a new unverified report.
4. Click the report to open the investigation pane.
5. The transcript, acoustic features, extracted entities, and triage facts are visible.

---

### Milestone 4 — Evidence Graph & Location Hypothesis

1. Inside the report investigation pane, click **Location Hypotheses**.
2. Each candidate location shows: landmark name, distance, uncertainty radius, and evidence span.
3. The PostGIS spatial index resolved the spoken landmark to a coordinate with an explicit confidence bound — not a hallucinated GPS coordinate.

---

### Milestone 5 — Priority Triage Explanation

1. In the same pane, click **Triage Assessment**.
2. The P0–P3 breakdown shows exactly which rule fired:
   - Medical emergency keyword → `severity_medical = True`
   - People count ≥ 2 → `household_at_risk = True`
   - Unknown water depth → uncertainty preserved, NOT coerced to low-risk
3. The final priority is `P0` — computed deterministically, no neural network involved.

**What to say on camera**: "Every priority decision is explainable. I can point to exactly which rule produced this P0. That matters when you're sending rescue boats to real people."

---

### Milestone 6 — Situation Map (Live Leaflet)

1. Click **Situation Map** tab in the console.
2. Each incident appears as a marker: color-coded by priority (P0 = red, P1 = orange, P2 = yellow, P3 = green).
3. Click a marker — a popup shows: incident ID, priority, people count, location hypothesis, assigned unit.
4. The map updates in real time via SSE when new incidents are created.

---

### Milestone 7 — 1-Click Dispatch Authorization

1. Back in the investigation pane, click **Authorize Dispatch**.
2. A modal confirms the nearest capable rescue unit (NDRF Boat Unit / Medical team).
3. Confirm — the assignment is committed.
4. The incident transitions to `in_progress` on the map.
5. An audit event is written — immutable, cryptographically chained.

---

### Milestone 8 — Audit Trail Verification

1. Navigate to `GET /api/v1/incidents/{incident_id}/audit-trail` in the OpenAPI explorer.
2. The response shows the full chain: report created → triage completed → dispatch authorized.
3. Each event carries a SHA-256 hash of the previous event — tamper detection built in.

**What to say on camera**: "Every action is logged and chained. If anyone disputes what happened during a rescue operation, we can cryptographically prove the exact sequence of decisions."

---

## Credit Budget Guide (Gnani API — 5,000 credits)

> [!IMPORTANT]
> Run all development and integration tests using the `text_override` parameter
> (no Prisma/Timbre API calls). Reserve credits for the actual demo recording only.

### Cost per Interactive IVR Call (Estimated)

The Gnani docs do not publish per-credit rates publicly. This table is based on
typical telephony STT/TTS pricing patterns. **Verify in the Gnani console dashboard.**

| Component | Per call estimate |
|---|---|
| Prisma v3.0 STT — 4 turns × ~8s audio each | ~32 seconds of audio |
| Timbre TTS — 4 agent responses × ~40 chars each | ~160 characters |
| **Full interactive call** | Verify exact rate in console |

### Conservative Credit Allocation

| Activity | Calls | Estimated credits |
|---|---|---|
| Contest demo recording (5 takes max) | 5 | ~400 |
| Evaluator live demo (3 sessions) | 3 | ~240 |
| Contest audio generation (`--use-timbre`, 4 clips) | — | ~100 |
| **Safety reserve** | — | remaining |

**Strategy**: Use `text_override` for all development. Only switch to live STT/TTS when recording the demo video.

```bash
# Dev / test: NO credit consumption — use text override
curl -X POST http://localhost:8080/api/v1/ivr/calls/start
curl -X POST http://localhost:8080/api/v1/ivr/calls/{call_sid}/turn \
  -F "text_override=Alappuzha, panchayat ward 7"

# Production demo: upload real microphone WAV
curl -X POST http://localhost:8080/api/v1/ivr/calls/{call_sid}/turn \
  -F "audio_file=@recording.wav"
```

---

## Generating Real Contest Audio Clips

When you are ready to use the Timbre API for real speech synthesis:

```bash
PYTHONPATH=src python3 scripts/generate_contest_audio.py --use-timbre
```

Output files in `demo/audio/contest_showcase/`:

| File | Language | Scenario |
|---|---|---|
| `01_hinglish_noisy_flood.wav` | Hinglish + brown noise | Flood + pump background |
| `02_hindi_medical_p0.wav` | Hindi | Diabetic elderly, needs insulin |
| `03_malayalam_alappuzha_boat.wav` | Malayalam | Boat rescue, Alappuzha canal |
| `04_marathi_shaniwar_wada.wav` | Marathi | 6 persons trapped, Pune Shaniwar Wada |

> [!NOTE]
> Without `--use-timbre`, the script generates acoustic simulations (synthetic signal +
> noise envelope) — suitable for testing the STT pipeline but NOT for a speech quality
> demo. Record real audio on a phone if Timbre credits are unavailable.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent greeting is silent | No `GNANI_API_KEY_TTS_STT` in `.env` | Set the key and restart; or use Text input |
| Transcript is empty | Prisma key missing or audio too short | Use text_override for dev; check `.env` |
| Map shows no markers | No incidents in DB | Run `seed_demo_data.py` and the scenario runner |
| `GET /sos/call.html` 404 | Citizen portal not mounted | Confirm `app.py` mounts `citizen_portal/public` |
| IVR session not found (404) | Server restarted — in-memory sessions lost | Restart call from `/sos/call.html` |
| Prisma HTTP 401 | API key invalid or header wrong | Key must go in `X-API-Key-ID`, not `Authorization` |

---

## Contest Submission Checklist

- [ ] Demo video recorded (60 seconds minimum), uploaded to LinkedIn and/or X
- [ ] Post tags: `@GnaniAI`, `#GnaniAI`, `#GreatIndianAIInternshipChallenge`
- [ ] Project description submitted in participant workspace
- [ ] Models/APIs listed: `Gnani Prisma v3.0 (STT)`, `Gnani Timbre (TTS)`
- [ ] GitHub or demo link included
- [ ] LinkedIn post link submitted
- [ ] Submission deadline: **November 10, 2026** (no extensions)

