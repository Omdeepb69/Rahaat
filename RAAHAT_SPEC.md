Raahat: an AI control room where no distress call ever gets a busy tone

When a flood hits, the phone line is the main lifeline, and it jams. In the 2018 Kerala floods, most government helpline numbers were busy, thousands of SOS requests arrived, and duplicates were rampant, since victims, relatives and friends all sent the same request. A volunteer team’s fix was a missed-call line so helplines wouldn’t stay busy, and they handled over 200 requests simultaneously. Another volunteer centre fielded over 25,000 calls in its first five days. Every one of those calls needed a human to work out who the person was, where they were and how urgent it was. A helicopter team’s advice was to ask callers for more visible landmarks.

Raahat does that work at scale. It answers every call at once, in the caller’s language, calls back dropped lines, builds a live map, and hands human dispatchers a ranked, evidence-backed rescue queue.

Why it passes your three tests

Emotionally obvious. “A thousand people are calling, and nobody gets a busy tone.” The demo: a counter of live calls on one side, and on the other a flood map lighting up with clusters of trapped households, each with a shrinking uncertainty circle.

Technically hard. This isn’t speech to LLM to answer:

Active location inference under uncertainty. Indians describe places by landmark: “Shiv Mandir ke paas, school ke peeche.” The system keeps a probability distribution over candidate places (OpenStreetMap points of interest plus fuzzy matching of spoken, transliterated names), then chooses the next question that most reduces the uncertainty (“mandir ke samne ya peeche?”). It reads the location back to the caller to verify. When a caller shares a WhatsApp location pin, that becomes a high-confidence signal.
Fusing evidence across calls. Neighbours mention the same landmark, and that tightens everyone’s location.
Entity resolution. The same household may call three times, and relatives abroad call too. Merge conservatively, because wrongly merging two separate families is worse than a duplicate, and send uncertain merges to a human.
Triage under uncertainty. Urgency scoring (elderly, children, medical need, rising water, floor level) shows “unknown” instead of guessing, and every field links back to the transcript span that supports it.
Real-time systems. Dozens of concurrent streams, graceful degradation when the LLM is slow, and callbacks for dropped calls. Stretch goal: assign scarce boats and teams to clusters with an optimizer, with a human approving each dispatch.

Gnani must matter. The product breaks if the speech layer garbles the place name. Panicked Malayalam, Tamil or Hindi speech over rain, wind and bad phone lines, mixed with English words like “school” and “bus stand,” is exactly where generic models fail. And a wrong landmark means a wrong location. So the proof isn’t WER, it’s place-name accuracy and resulting location error, compared between Prisma and an open-source baseline like Whisper.

Who would use it

State and district disaster control rooms (Kerala’s statewide flood lines used 1077 and 1070), 112 emergency centres, municipal helplines during urban flooding, and volunteer networks. It also has an everyday mode: overflow handling for civic complaint lines like waterlogging and power outages. That’s Gnani’s government vertical.

Honest risks
Safety. AI answering distress calls is sensitive. Humans make every dispatch decision. The agent speaks only vetted, scripted safety messages and never improvises medical advice. Say this up front. Call it decision support and overflow handling, not a replacement.
Synthetic data only. There are no real distress-call recordings to train or test on, so don’t claim real-world accuracy or that it saves lives.
Language coverage. Pick a language Prisma handles well and check Malayalam or Tamil quality before committing.
Map data. OpenStreetMap can be sparse in rural areas, so choose a district with rich data and report location error honestly.
Credits. Real streaming for hundreds of calls will blow your 5,000 credits. Use real Prisma streams for a small set and replay cached transcripts for the surge, and label which is which.
Scope. This is the biggest of the ideas. For a solo 5-week MVP: one flood scenario, one or two languages, about 100 synthetic calls, 20-30 live streams, and the location inference, dedup, triage and map. The optimizer and photo input are stretch goals.
What I rejected
A live phone interpreter and a call relay for deaf users: too plain.
A crop-photo helpline for farmers: any multimodal model can do it, and only the speech part is special.
Mental-health helplines: too risky to build solo.

If this one lands, I’ll sketch the architecture and the location-inference loop. If not, tell me which of your three criteria it misses.

Building an IVR system with phone call automation and testing.

60 tests pass. Re-running the real-audio calls with the new robustness features (keypad fallback after a failed answer, number read-back, turn cap).

Continue

Re-running the baseline simulation to check under-triage.

62 tests pass. Re-running the baseline surge to see what the floor/hazard questions and the “unverified never lowers priority” rule did to the under-triage rate.

Continue

Continue

are you close to finishing ?? give me a percentage of you being done and current progress , quickly and brief without wasting much tokens

About 85% done.

Finished and tested (about 80 tests passing):

The call agent runs on real local models: Silero voice detection, Whisper-base speech recognition, and Hindi Piper text-to-speech.
It locates callers from landmarks, falls back to the keypad when speech recognition fails, and confirms unreliable numbers by reading them back.
Duplicate calls are merged into one incident, triaged conservatively, and held for a human to approve before any dispatch.
The API, an audit log that can’t be quietly edited, and recovery of incidents and promised callbacks after a restart are done.
The operator console works against the live server in a simulated browser.
The surge and outage simulation replays real recorded Whisper output.

Left (about 15%):

Dockerfile, compose, Kubernetes manifests, monitoring dashboards and alerts, and chaos experiments.
Docs: README, architecture notes, a guide to swapping in Prisma/Timbre/Evon, a runbook, and an evaluation report.
A final run of all tests and simulations, then packaging.

What will still be unfinished, and the docs will say so:

Only one API instance can run, so the autoscaling in the simulation is a capacity-planning model, not something the deployment does yet.
Docker and Kubernetes files have never been run; this sandbox has neither.
The language-model extraction path has never run against a real model (no weights are reachable here).
The Prisma and Timbre adapters are stubs.
Outbound callback dialing isn’t connected to a telephony provider.
Everything was tested with synthetic callers, not real people.

Whisper-base is weak on short Hindi answers, so I expect a stronger recogniser to be needed before real use.

proceed do it properly and deliver fast but with the best quality please

Going straight to the deployment layer. Dropping the services that the code doesn’t actually use (NATS/Postgres/LiveKit) so nothing in the deployment is decorative.

Manifests parse. A schema check against real Kubernetes API definitions is cheap and catches typos YAML parsing can’t, so I’m running it.

YES. And honestly, you've just identified one of the biggest architectural weaknesses in Raahat.

During major floods, cyclones and landslides, we cannot assume that victims have:

- A working smartphone.
- Mobile data.
- Reliable cellular coverage.
- Battery power.
- The ability to speak.
- Enough signal to maintain a continuous call.

A system that depends on victims continuously calling an AI could fail precisely when it is needed most.

But there's an important distinction: communication failure is not necessarily total communication failure.

A phone call may fail while an SMS gets through. A mobile network may be available in one village but not another. A tower may be working while its backhaul is disrupted.

We need to design around these realities, not assume universal connectivity.

## 1. What actually happened during Kerala floods?

The historical evidence is quite revealing.

[Assam Floods – Update IV | WWF India](https://images.openai.com/static-rsc-4/RRlqOzStdscNuYtTnlPwblndVFUyeUfugTv5Lf-toGVV_EbawZMLQ5W_OMoVcM0NmqUvw_jIhbObpoSmf-_R0j-oML3heQVI8Vb1ZZX8HD5-scLk7LpB-JxZ0d-_xVnU6_wKhtkO10mT4mWlBIoRjcZzeh0MQPv_zFmO7-C8-80?purpose=inline)

Mobile network outages

During the 2018 floods, power failures and inaccessible tower sites disrupted mobile connectivity. Operators struggled to refuel generators and repair towers.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://timesofindia.indiatimes.com\&sz=32)

Thiruvananthapuram News - Times of India



[Times of India](https://images.openai.com/static-rsc-4/dynLr9KR3xkh6bSGYVXSzYY0L3L0FOzi41Y-bSwZYsJxPFqXEfyfVVCSGDcvIXNr3-HOjZdmrpDnRdbUU4D-em7NtYqjmixDrEEQkPxbk5LfSDSzux4dzBLDBw3o4gSUThPBPkw6bZatJOJd5cQMmXigoAHZAU57UBssEAxMlH0?purpose=inline)

Ham radio became important

Amateur radio operators helped relay rescue information when most telecommunications services were down.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.arrl.org\&sz=32)

arrl.org



[Times of India](https://images.openai.com/static-rsc-4/bsHjdC4nuTM8gXaDXpdxdeTMcJBqeSQ4SzVi7xmUbATr8-trZPnqP0JpwAXIlJMj0ibADilkshuGHeWeS7vAslG4sDFyNLDLW653U_Zu5y_2csOtXbAIH4mSdXf4xCH_LolzjKZwgBkFGRDKUK-aELLkbHP9VDZyYIiEFqJPYKY?purpose=inline)

Indirect communication worked

Some people couldn't make calls but could occasionally access the internet. Relatives, journalists and volunteers relayed SOS messages through WhatsApp and social media.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://sdma.kerala.gov.in\&sz=32)

Kerala Disaster Management



The NDRF's own account describes areas where no communication system was functional.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://ndrf.mha.gov.in\&sz=32)

NDRF - National Disaster Response Force



So yes, your concern is absolutely legitimate.

## 2. This changes Raahat's architecture

I would introduce a completely new principle:

Raahat must not depend on the victim having connectivity.

Instead, it should collect information from wherever connectivity or communication survives.

## Raahat: resilient information architecture

DISTRESSED PERSON / AFFECTED HOUSEHOLD

May have no phone, battery or network

Direct channels

Calls, SMS, internet, SOS

Indirect channels

Relatives, neighbours, volunteers, shelters

Emergency networks

HAM, VHF, responder radio

Field infrastructure

Satellite terminals, mobile control units

RAAHAT INGESTION + EVIDENCE ENGINE

Normalize, timestamp, geolocate, corroborate and deduplicate reports

HUMAN DISASTER CONTROL ROOM

Verified incidents, uncertainty, rescue queue and operational tracking

## 3. Five features I would add

| Feature                      | What it does                                                   |
| ---------------------------- | -------------------------------------------------------------- |
| Indirect SOS ingestion       | Relatives and neighbours can report people who cannot call     |
| Offline-first field app      | Volunteers record reports without internet and sync later      |
| Radio-to-Raahat gateway      | Operators enter or relay information received over radio       |
| Connectivity-aware operation | Tracks which communication channels are available in each area |
| Evidence freshness           | Identifies reports that haven't been reconfirmed               |

One important distinction: SMS is not a guaranteed fallback when cellular infrastructure is down. Neither is a phone-based mesh network. We should treat both as conditional channels, not lifelines.

Kerala's own disaster-management communication architecture already recognizes the need for redundancy: satellite phones, VSAT, police wireless, HAM radio, landlines and internet are among its listed systems.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://sdma.kerala.gov.in\&sz=32)

Kerala State Disaster Management Authority+1



## 4. An even more interesting feature: connectivity-aware rescue intelligence

Imagine the following situation:

- Village A has no cellular coverage.
- Village B has intermittent internet.
- Village C has working calls but congested networks.
- A relief camp has internet.
- A volunteer team has a satellite terminal.

Raahat should understand this.

It should show responders where information can still enter the system, where information is stale, and where the absence of reports might simply mean communications are unavailable.

[ArcGIS Dashboards | Esri Australia](https://images.openai.com/static-rsc-4/q--iPRJE5r_Yv7nsi4LzWQ5Bgm2oxStBqy7XGJtcjxW6YN3AYvTyJea4w-PrzMT3Zoun4ztEE5v3sdF2gFaEYUHyW-XaMI3FfCwGPdrvZGSCqvokdDN_cROiXSKs33rJevFhrpmZ1eKkbqC78kXkIZup2i56X7z4yPpf3KtSQh0?purpose=inline)

[esriaustralia.com.au](https://esriaustralia.com.au/arcgis-dashboards?utm_source=chatgpt.com)

This last point is especially important: no reports from an area must never be interpreted as no people needing rescue.

## 5. My revised verdict

I would change the project's central promise.

Old:

> Every distress call gets answered.

New:

> Even when communication infrastructure fails, rescue information must keep moving.

That is a much more robust disaster-management problem.

And it creates a better reason for Raahat to exist alongside 112 rather than competing with it.

My recommendation: keep the IVR system, but demote it to one component. Make the actual product a resilient, multi-channel disaster intelligence platform.

One question that could fundamentally change our design:

Are you willing to make Raahat useful even when the affected person has absolutely no working phone or network, by designing around volunteers, responders, shelters and offline field reporting? I strongly recommend that direction.

# RAAHAT 2.0 — Final Project Specification



Project direction finalized

Product + Research



# Raahat: Resilient Disaster Intelligence & Rescue Coordination

Core proposition: A disaster-response intelligence platform that transforms fragmented, unreliable and multilingual distress information into evidence-backed incidents, verified locations and coordinated rescue operations—even when affected communities have little or no connectivity.

This is the specification I would use as the source of truth for development, demonstrations, research and eventual deployment discussions.

We're retaining the existing IVR implementation, but changing its role. It becomes one communication channel within a larger resilient system.

## 1. Product definition

### The problem

During disasters, information comes from multiple disconnected sources:

- Victims who can make calls.
- Relatives reporting on behalf of victims.
- Neighbours and local residents.
- Volunteers and relief organisations.
- Emergency responders.
- Radio operators.
- Shelters and temporary relief centres.

These reports can be duplicated, contradictory, outdated, incomplete or geographically ambiguous.

The disaster control room must determine:

1. Who needs help?
2. Where are they?
3. How many people are affected?
4. What is their current situation?
5. How reliable is the information?
6. Which incidents require attention first?
7. Which resources have been assigned?
8. Has the rescue actually happened?

Raahat's job is to maintain a continuously updated, auditable operational picture.

### Product boundaries

| Raahat does                          | Raahat does not                        |
| ------------------------------------ | -------------------------------------- |
| Collect distress reports             | Replace emergency numbers              |
| Transcribe multilingual calls        | Diagnose medical conditions            |
| Infer and verify locations           | Pretend uncertain locations are exact  |
| Detect possible duplicate reports    | Aggressively merge households          |
| Maintain incident intelligence       | Invent missing information             |
| Recommend operational priority       | Autonomously dispatch rescue teams     |
| Coordinate human-approved operations | Replace disaster authorities           |
| Work offline in field environments   | Promise connectivity where none exists |

Primary users: District disaster control rooms, emergency coordinators, volunteer organisations, relief camp operators and field rescue teams.

Initial scenario: Flood response in one district, using synthetic incidents and simulated communications.

Research objective: Evaluate whether evidence-aware, uncertainty-aware information fusion improves incident resolution and geospatial accuracy compared with conventional approaches.

## 2. Evidence supporting the product direction

This architecture isn't based on hypothetical disaster scenarios alone.

Three institutional findings shape the design:

India's existing ERSS-112 is already multi-channel. The Ministry of Home Affairs describes voice, SMS, SOS, email, web requests, chatbots, WhatsApp and external signals entering a common emergency response system. Raahat must complement that infrastructure rather than recreate it.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.mha.gov.in\&sz=32)

Ministry of Home Affairs



Communication redundancy is an established requirement. Kerala State Disaster Management Authority lists dedicated phones, landlines, VSAT, satellite phones, police wireless, WhatsApp, HAM radio and other communication systems for emergency coordination.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://sdma.kerala.gov.in\&sz=32)

Kerala State Disaster Management Authority



Crowdsourced reports have a verification problem. The 2020 Kerala flood deployment study specifically identifies inaccurate, incomplete and unverifiable submissions as limitations of crowdsourced disaster-relief systems.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.sciencedirect.com\&sz=32)

ScienceDirect



These findings give us three architectural requirements:

1. Multi-channel ingestion.
2. Connectivity-independent field reporting.
3. Evidence provenance and conservative information fusion.

# 3. Revised system architecture

## High-level architecture

INPUT CHANNELS

IVR · SMS · Web SOS · Volunteer App · Shelters · Radio Operator · Responders

INGESTION GATEWAY

Authentication · Source identity · Idempotency · Validation · Timestamping

EVIDENCE PROCESSING PIPELINE

Speech

VAD · ASR · Language detection

Extraction

Structured facts · Validation

Geospatial

Landmark candidates · Uncertainty

Entity resolution

Households · Incidents · Corroboration

INCIDENT INTELLIGENCE CORE

Evidence graph · Conflict detection · Risk policy · Human verification

OPERATIONS CONTROL ROOM

Live GIS · Ranked review queue · Resource assignments · Rescue tracking

AUDIT, ANALYTICS & EVALUATION

Immutable decision history · Metrics · Replay · Research benchmarks

### Architecture decisions

| Component         | Final choice                           | Reason                                            |
| ----------------- | -------------------------------------- | ------------------------------------------------- |
| Backend           | FastAPI modular monolith               | Existing implementation and manageable complexity |
| Primary database  | PostgreSQL                             | Transactional source of truth                     |
| Geospatial        | PostGIS                                | Spatial queries, indexing and geometry            |
| Map               | MapLibre + OSM                         | Open geospatial visualization                     |
| Event durability  | PostgreSQL transactional outbox        | No external broker dependency initially           |
| Background work   | Separate Python workers                | Isolate slow ASR and inference                    |
| Field persistence | SQLite on-device                       | Offline report capture                            |
| Live updates      | SSE initially, WebSockets where needed | Operator updates                                  |
| Voice activity    | Silero VAD                             | Existing implementation                           |
| ASR               | Whisper baseline, Gnani Prisma adapter | Comparative speech evaluation                     |
| TTS               | Existing Piper adapter                 | Controlled IVR responses                          |
| Observability     | Prometheus + Grafana                   | Latency, queues and failures                      |
| Deployment        | Docker Compose                         | Reproducible initial deployment                   |

Important: PostgreSQL is authoritative. Redis can be introduced for ephemeral caching or rate limiting, but not as the authoritative incident store. No Kafka, NATS, Kubernetes or microservices are required for the MVP.

### Connectivity architecture

This is a first-class subsystem, not an afterthought.

Offline field reporting lifecycle

1. Volunteer records a report on the field device.
2. Report is persisted locally in SQLite, including a globally unique event ID.
3. Device queues the event in an outbound sync table.
4. When connectivity returns, it submits events to the ingestion gateway.
5. Server applies idempotency and records server receipt time separately from device event time.
6. Server acknowledges the event and the device marks it synchronized.

We will use an append-only submission model, not attempt to implement a complicated distributed CRDT system.

Every report retains:

- `client_created_at`
- `server_received_at`
- `device_sequence`
- `source_event_id`
- `sync_status`
- `source_type`
- `source_identity`

The radio integration will initially be a human-operated gateway: a radio operator receives a message and records it into Raahat. We will not claim that a normal mobile application can directly receive HAM or VHF transmissions.

# 4. Database architecture and schema

This is probably the most important architectural change.

The old conceptual model of one call becoming one incident is insufficient.

We need to distinguish:

Report

A piece of information received from a particular source.

Evidence

The individual claims and observations supported by that report.

Household / Person

The people potentially affected, with identity uncertainty preserved.

Incident

The real-world situation inferred from multiple reports.

Rescue operation

The human-authorized operational response.

A report can support multiple incidents. An incident can have multiple reports. One household can be associated with several reports. Never make these relationships artificially one-to-one.

## 4.1 Core entities

| Table                 | Responsibility                                            |
| --------------------- | --------------------------------------------------------- |
| `organizations`       | Disaster authorities, NGOs and volunteer organisations    |
| `users`               | Authenticated users                                       |
| `teams`               | Field teams and operational units                         |
| `devices`             | Registered field devices                                  |
| `disasters`           | Disaster events and operational boundaries                |
| `reports`             | Every incoming report                                     |
| `evidence_items`      | Individual extracted or manually recorded claims          |
| `evidence_spans`      | Transcript or message spans supporting claims             |
| `households`          | Household records                                         |
| `persons`             | Optional individual records                               |
| `report_subjects`     | Relationship between reports and affected entities        |
| `incidents`           | Canonical operational incidents                           |
| `incident_reports`    | Many-to-many report/incident relationship                 |
| `incident_links`      | Possible duplicate, related or conflicting incident links |
| `location_hypotheses` | Candidate locations and their confidence                  |
| `landmarks`           | Geographic reference entities                             |
| `incident_locations`  | Location history for incidents                            |
| `resources`           | Boats, vehicles, medical teams and shelters               |
| `assignments`         | Resource-to-incident assignment                           |
| `operation_events`    | Acknowledgement, arrival, rescue and resolution           |
| `callback_jobs`       | Callback scheduling and provider state                    |
| `outbox_events`       | Durable background events                                 |
| `audit_events`        | Append-only decision and action history                   |
| `sync_cursors`        | Device synchronization state                              |

## 4.2 Important PostgreSQL schema

The following is the proposed logical schema, not a claim that these tables already exist in the current repository.

```

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE disasters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    disaster_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    boundary GEOMETRY(MultiPolygon, 4326),
    started_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disaster_id UUID NOT NULL REFERENCES disasters(id),
    source_type TEXT NOT NULL,
    source_event_id TEXT,
    source_identity TEXT,
    device_id UUID,
    channel_reference TEXT,
    raw_payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    client_created_at TIMESTAMPTZ,
    language_code TEXT,
    processing_status TEXT NOT NULL DEFAULT 'pending',
    idempotency_key TEXT NOT NULL,
    UNIQUE (disaster_id, idempotency_key)
);

CREATE TABLE households (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disaster_id UUID NOT NULL REFERENCES disasters(id),
    display_label TEXT,
    identity_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID REFERENCES households(id),
    display_label TEXT,
    vulnerability_attributes JSONB NOT NULL DEFAULT '{}',
    identity_status TEXT NOT NULL DEFAULT 'unverified'
);

CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disaster_id UUID NOT NULL REFERENCES disasters(id),
    status TEXT NOT NULL DEFAULT 'unverified',
    operational_priority TEXT NOT NULL DEFAULT 'unassessed',
    severity_facts JSONB NOT NULL DEFAULT '{}',
    last_confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidence_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES reports(id),
    subject_type TEXT NOT NULL,
    subject_id UUID,
    attribute TEXT NOT NULL,
    value JSONB NOT NULL,
    confidence DOUBLE PRECISION,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    observed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidence_spans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID NOT NULL REFERENCES evidence_items(id),
    source_start_ms INTEGER,
    source_end_ms INTEGER,
    source_text TEXT,
    source_reference JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE incident_reports (
    incident_id UUID NOT NULL REFERENCES incidents(id),
    report_id UUID NOT NULL REFERENCES reports(id),
    relationship TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    reviewed_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (incident_id, report_id)
);

CREATE TABLE location_hypotheses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id),
    location GEOGRAPHY(Point, 4326) NOT NULL,
    candidate_label TEXT,
    source_evidence_id UUID REFERENCES evidence_items(id),
    probability DOUBLE PRECISION,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disaster_id UUID NOT NULL REFERENCES disasters(id),
    resource_type TEXT NOT NULL,
    name TEXT NOT NULL,
    capacity INTEGER,
    availability_status TEXT NOT NULL,
    location GEOGRAPHY(Point, 4326)
);

CREATE TABLE assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id),
    resource_id UUID NOT NULL REFERENCES resources(id),
    assigned_by UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX reports_disaster_received_idx
    ON reports(disaster_id, received_at DESC);

CREATE INDEX evidence_report_idx
    ON evidence_items(report_id);

CREATE INDEX location_hypotheses_geo_idx
    ON location_hypotheses USING GIST(location);

CREATE INDEX resources_geo_idx
    ON resources USING GIST(location);

```

### Additional database rules

This SQL is the core starting point, not the entire migration.

We must also enforce:

- Probability values within `[0,1]`.
- Valid status values through enums or check constraints.
- No cross-disaster incident/report association.
- No assignment without an authenticated human actor.
- No silent overwriting of historical evidence.
- No hard deletion of audit events.
- Explicit retention and access policies for sensitive caller data.

For entity merges, use a separate `entity_merge_events` table with source entity, destination entity, reviewer, reason and reversible status. Never delete the original identity records.

For location changes, preserve every hypothesis. A verified location is a decision about the current best evidence, not permission to erase earlier possibilities.

One further design correction: a database-level `confidence` field is not automatically a statistically calibrated probability. It must be calibrated and evaluated before being presented as one.

# 5. Module boundaries and code organization

We will keep a modular monolith with separate API and worker processes.

No god modules. No business logic inside API route handlers. No model-specific logic inside incident management.

The proposed target repository structure:

```

raahat/
├── pyproject.toml
├── README.md
├── .env.example
├── docker-compose.yml
├── Dockerfile
│
├── src/
│   └── raahat/
│       ├── main.py
│       ├── config.py
│       │
│       ├── api/
│       │   ├── dependencies.py
│       │   ├── middleware.py
│       │   └── routes/
│       │       ├── reports.py
│       │       ├── incidents.py
│       │       ├── locations.py
│       │       ├── operations.py
│       │       ├── resources.py
│       │       ├── devices.py
│       │       └── health.py
│       │
│       ├── domain/
│       │   ├── reports/
│       │   ├── incidents/
│       │   ├── households/
│       │   ├── evidence/
│       │   ├── geospatial/
│       │   ├── triage/
│       │   ├── operations/
│       │   ├── resources/
│       │   └── shared/
│       │
│       ├── application/
│       │   ├── ingestion/
│       │   ├── processing/
│       │   ├── incident_resolution/
│       │   ├── location_verification/
│       │   ├── prioritization/
│       │   └── dispatch/
│       │
│       ├── infrastructure/
│       │   ├── database/
│       │   │   ├── models/
│       │   │   ├── repositories/
│       │   │   └── migrations/
│       │   ├── messaging/
│       │   ├── storage/
│       │   ├── telephony/
│       │   ├── speech/
│       │   ├── geocoding/
│       │   └── observability/
│       │
│       ├── adapters/
│       │   ├── channels/
│       │   │   ├── ivr/
│       │   │   ├── sms/
│       │   │   ├── web/
│       │   │   ├── volunteer/
│       │   │   └── radio_console/
│       │   ├── speech/
│       │   │   ├── whisper.py
│       │   │   ├── prisma.py
│       │   │   └── piper.py
│       │   └── maps/
│       │       └── osm.py
│       │
│       ├── workers/
│       │   ├── runner.py
│       │   ├── report_processor.py
│       │   ├── callback_worker.py
│       │   └── sync_worker.py
│       │
│       └── policies/
│           ├── triage.py
│           └── assignment.py
│
├── field_app/
│   ├── src/
│   ├── database/
│   └── sync/
│
├── operator_console/
│   ├── src/
│   └── public/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── concurrency/
│   ├── fault_injection/
│   ├── evaluation/
│   └── end_to_end/
│
├── evaluation/
│   ├── datasets/
│   ├── scenarios/
│   ├── baselines/
│   ├── metrics/
│   └── reports/
│
├── deployment/
│   ├── prometheus/
│   ├── grafana/
│   └── scripts/
│
└── docs/
    ├── architecture.md
    ├── data_model.md
    ├── security.md
    ├── operations_runbook.md
    ├── evaluation_protocol.md
    └── limitations.md

```

This is the target organization. Existing files should be mapped into these boundaries, not blindly moved into this tree.

## 5.1 Responsibility contracts

| Module                | Owns                                      | Must not own                |
| --------------------- | ----------------------------------------- | --------------------------- |
| `ingestion`           | Normalize incoming channels               | Triage decisions            |
| `reports`             | Report lifecycle                          | Incident identity           |
| `evidence`            | Claims, provenance, verification          | Dispatch                    |
| `geospatial`          | Candidate matching and spatial operations | Caller identity             |
| `incident_resolution` | Report-to-incident relationships          | Speech inference            |
| `households`          | Household identity and membership         | Location probability        |
| `prioritization`      | Deterministic safety policy               | Autonomous actions          |
| `operations`          | Rescue workflow and statuses              | AI-generated dispatch       |
| `resources`           | Resource availability                     | Incident inference          |
| `speech`              | Audio adapters and transcription          | Incident database mutations |
| `messaging`           | Durable event publication                 | Business rules              |
| `audit`               | Decision and action history               | Modifying historical events |

### Critical domain interfaces

The domain must not depend on Whisper, Prisma, PostGIS repositories or any specific provider.

For example:

```
class SpeechRecognizer(Protocol):    async def transcribe(        self,        audio: AudioInput,        language_hint: str | None = None,    ) -> Transcript:        ...class LocationResolver(Protocol):    async def resolve(        self,        observation: LocationObservation,    ) -> LocationResolution:        ...class IncidentMatcher(Protocol):    async def match(        self,        report: NormalizedReport,    ) -> list[IncidentCandidate]:        ...
```

These are proposed contracts; actual types should follow the existing implementation's conventions.

The important design principle is dependency inversion: core incident logic must not know which speech model generated a transcript.

# 6. Exact changes to the existing Raahat codebase

This is the migration plan based on the implementation history.

First, the existing work is not being discarded.

Preserve these working subsystems

Silero VAD + Whisper-base

Retain

Hindi Piper TTS

Retain

Keypad fallback and number read-back

Retain

Conservative triage and human approval

Retain

Audit log and restart recovery

Retain

Operator console

Extend

Duplicate detection

Redesign

Location inference

Redesign

The implementation history also identifies important unfinished work: the Prisma/Timbre adapters were stubs, outbound callback dialing was not connected to a provider, Docker/Kubernetes had not been executed, and testing used synthetic callers only. The previously reported test count was approximately 80, not a verified current run.&#x20;

## 6.1 Migration-by-migration plan

| Existing subsystem  | Exact change                                             | Expected result                              |
| ------------------- | -------------------------------------------------------- | -------------------------------------------- |
| Call ingestion      | Introduce common report ingestion contract               | Calls and non-call sources share a pipeline  |
| Call session        | Preserve session, link it to report                      | Multiple reports can arise from one session  |
| Incident creation   | Stop assuming one call equals one incident               | Multiple sources can support one incident    |
| Duplicate detection | Replace destructive merging with candidate relationships | Reversible entity resolution                 |
| Landmark resolver   | Return ranked candidates and uncertainty                 | Evidence-aware geolocation                   |
| Triage              | Extract facts separately from priority policy            | Deterministic, explainable priority          |
| Audit log           | Extend with evidence and merge-decision events           | Full decision provenance                     |
| Callback scheduler  | Retain scheduling, add provider adapter boundary         | Real dialing only after provider integration |
| Operator console    | Add report inbox, evidence and incident views            | Unified operations workflow                  |
| API                 | Add reports, devices, resources and operations routes    | Full platform API                            |
| Worker              | Add durable report-processing jobs                       | Slow inference doesn't block requests        |
| Deployment          | Run and verify Compose stack                             | Reproducible environment                     |

## 6.2 Changes to specific existing components

A. IVR pipeline

Keep:

```
Call
  → Silero VAD
  → Whisper
  → Structured response extraction
  → Keypad fallback
  → Read-back
```

Change the output from an incident mutation to a `ReportSubmitted` event.

The call agent must never directly merge incidents or assign resources.

B. Entity resolution

Replace this conceptual operation:

```
merge_incidents(report, matched_incident)
```

With:

```
candidates = matcher.find_candidates(report)decision = resolver.evaluate(    report=report,    candidates=candidates,)if decision.requires_review:    await review_queue.create(decision)else:    await incident_linker.attach_evidence(        report=report,        incident=decision.incident,    )
```

Even a high-confidence automated association should retain the source report and be reversible. Ambiguous household identity merges require human approval.

C. Location resolver

Current output should evolve from one chosen coordinate to:

```
{
  "status": "ambiguous",
  "candidates": [
    {
      "landmark_id": "osm-123",
      "latitude": 15.40,
      "longitude": 73.95,
      "probability": null
    },
    {
      "landmark_id": "osm-456",
      "latitude": 15.41,
      "longitude": 73.96,
      "probability": null
    }
  ],
  "next_question": "Is the temple opposite or behind the school?",
  "human_verification_required": true
}
```

Here `probability: null` is intentional. Do not manufacture calibrated probabilities before the model is evaluated.

D. Triage engine

Split it into two components:

- `fact_extractor`: extracts observations.
- `priority_policy`: calculates operational recommendations using explicit rules.

Example:

```
PriorityAssessment(    priority="critical_review",    reasons=[        "water_entering_occupied_floor",        "medical_need_reported",    ],    unknown_fields=[        "exact_people_count",        "last_contact_time",    ],    requires_human_review=True,)
```

Unknown information remains unknown. It is never converted into a negative observation.

E. Worker architecture

Introduce a durable processing lifecycle:

```
PENDING
   ↓
CLAIMED
   ↓
PROCESSING
   ├── SUCCEEDED
   ├── RETRYABLE_FAILURE
   └── DEAD_LETTER
```

Use database-backed leases and fencing tokens so a worker that loses its lease cannot commit stale processing results.

Keep transactions short. Never hold a PostgreSQL transaction open while Whisper or an LLM is processing audio.

## 6.3 API contract

The following are the new target endpoints:

| Method | Endpoint                                 | Purpose                       |
| ------ | ---------------------------------------- | ----------------------------- |
| POST   | `/api/v1/reports`                        | Submit report                 |
| GET    | `/api/v1/reports`                        | Search reports                |
| GET    | `/api/v1/reports/{id}`                   | View evidence and source      |
| POST   | `/api/v1/reports/{id}/process`           | Request processing            |
| GET    | `/api/v1/incidents`                      | Incident queue                |
| GET    | `/api/v1/incidents/{id}`                 | Incident detail               |
| POST   | `/api/v1/incidents/{id}/verify`          | Human verification            |
| POST   | `/api/v1/incidents/{id}/links`           | Review incident relationships |
| POST   | `/api/v1/incidents/{id}/location/verify` | Confirm location              |
| POST   | `/api/v1/incidents/{id}/assignments`     | Propose or approve assignment |
| POST   | `/api/v1/devices/sync`                   | Synchronize offline events    |
| GET    | `/api/v1/resources`                      | Resource availability         |
| POST   | `/api/v1/operations/{id}/events`         | Record rescue operation event |
| GET    | `/api/v1/events/stream`                  | Live operator updates         |

All mutating endpoints need authenticated authorization, idempotency where appropriate, and audit events.

These are a target API contract, not existing endpoints verified against the repository.

# 7. Operator console redesign

The existing operator console should evolve rather than be replaced.

I would use four primary workspaces.

[Emergency Response System for Smart Dispatch & GIS Command | Sharp Innvotech | Sharp Innovation](https://images.openai.com/static-rsc-4/Kkix-y7dnSZWqx0lDgO501acuvmXKKpvq5d5ghPjFIpovvMpkWzpb1e7rtrDItHkSShs-vHBXWu8CDd6pqua9z-FKunBj1azSbcF79e5GxEvXyD0vXgJw5DO0RU6mXyiT5SqdEFnWJpNuCIeDXlESkpN6Y6OJP7UQ5fW9sQfB9k?purpose=inline)

01\. Incoming reports

Live feed across all channels, processing status, language, source reliability and possible duplicate relationships.

[ArcGIS Enhances UDEM’s Situational Awareness | Case Study](https://images.openai.com/static-rsc-4/5KJprw5Of0CZWUzAUmUL8izQ4nTA5reEvg4DztM-bZHopoXuAQnSljAg_ZB1eqbNCyKzbaBxaMq1Z7ciV0N97ZVWAEbBvsSaJ2zF-_lcUXuUlhmwGAnhkPjHOzixf6ZSbfgjmrInvm0xLLgWVBeI6IhLVo1B3Yu2sOczUZ3Ro3M?purpose=inline)

02\. Situation map

Incident clusters, candidate locations, uncertainty radii, stale observations, shelters and resource positions.

[OSIRT iii – Digital Investigation & Evidence Capture Platform | OSINT Tool](https://images.openai.com/static-rsc-4/MuV5y11j5jYYAFZW1QrZNvLtzxHxG6YHgg2yQKQAPmrdc7qcV6JQMd961Y8H3tO4t98R_ZRaEr0WfR06TaK2tPQWPCSigt1XoTbNMAhFa7lrfqNSr8eqf2mrCn8zLXXPurOy3fLdIhWo2o0M7InO0tkS_Keq2KPaZoCb2CaUXHs?purpose=inline)

03\. Incident investigation

Transcripts, evidence spans, contradictions, household relationships, location hypotheses and verification history.

[Integrated Communication and Dispatch in Emergency Management: Systems, Technologies, Protocols, and Future Trends-Becke Telcom](https://images.openai.com/static-rsc-4/Aco6z3-cY4ZdIGj50BUPDkbXCF7XYqkOhXO_ZEYZ9qnB61oBv6qFBL8LvAQl7aD2PAaJ0SZzo_GSsNSocVTNA6LgOYrDWCfCD3WUq_RSodHK4Lux3vjFVPCJtryfbFx9OCv5fYw_haiuwO-bvGI5e_CP1cdGBayNLsNPxjGdRtw?purpose=inline)

04\. Operations

Resource availability, proposed assignments, human approval, acknowledgement, arrival and rescue completion.

### A critical UI rule

Every map marker must communicate its evidence status.

Use distinct visual representations for:

- Confirmed location.
- Candidate location.
- Approximate area.
- Stale location.
- Contradictory location.

A dispatcher should never mistake a low-confidence candidate for a verified rescue coordinate.

# 8. Five-week implementation roadmap

This is the recommended solo development schedule. The first deliverable is a working flood-response MVP, not a collection of disconnected infrastructure demonstrations.

# Development roadmap

1. Week 1 — Domain and data foundation

   Highest priority
   - Audit the current repository and freeze working interfaces.
   - Introduce disaster, report, evidence and incident separation.
   - PostgreSQL/PostGIS migrations.
   - Report ingestion API.
   - Transactional outbox and worker.
   - Preserve existing IVR compatibility.
   Deliverable: Multiple channels can create durable reports without creating duplicate incidents automatically.
2. Week 2 — Geospatial and offline intelligence
   - OSM landmark indexing.
   - Candidate location resolution.
   - Active clarification questions.
   - Location read-back and verification.
   - Offline SQLite field-reporting prototype.
   - Idempotent synchronization.
   Deliverable: Reports can be collected offline and locations can be represented with explicit uncertainty.
3. Week 3 — Evidence graph and triage
   - Household/person/report relationships.
   - Conservative incident matching.
   - Contradiction detection.
   - Evidence provenance.
   - Explainable prioritization.
   - Human merge and verification workflow.
   Deliverable: A dispatcher can inspect why multiple reports belong to one incident and which facts remain unverified.
4. Week 4 — Full operations workflow
   - Expand operator console.
   - Resource registry.
   - Assignment approvals.
   - Operation lifecycle.
   - Working speech adapter abstraction.
   - Real Prisma adapter if provider access is available.
   - Callback provider integration if credentials and sandbox access are available.
   Deliverable: A complete simulated rescue operation from initial report through human-approved assignment and resolution.
5. Week 5 — Research, resilience and deployment
   - Generate and freeze evaluation datasets.
   - Run baseline and ablation studies.
   - Concurrency and fault injection.
   - Docker Compose build and runtime validation.
   - Monitoring dashboards.
   - Architecture documentation and evaluation report.
   Deliverable: Reproducible, benchmarked Raahat MVP with honest limitations.

### What is explicitly out of scope for the five-week MVP?

- Real government 112 integration.
- Real emergency dispatch.
- Satellite infrastructure deployment.
- Direct HAM/VHF hardware integration.
- Satellite imagery analysis.
- Flood forecasting.
- Autonomous boat allocation.
- Kubernetes-based production scaling.
- Real victim recordings or real-world accuracy claims.

These can become future research or integration milestones.

# 9. Research and evaluation protocol

This is the part that determines whether Raahat becomes a serious research-engineering project or just an impressive demonstration.

I recommend a dedicated benchmark:

# RaahatBench

Multichannel Disaster Incident Intelligence Benchmark

Its purpose is to evaluate how reliably a system transforms incomplete disaster reports into actionable incidents.

## 9.1 Dataset design

Proposed benchmark

Create 1,000 synthetic reports across approximately 100 ground-truth incidents.

| Dataset dimension                | Proposed coverage |
| -------------------------------- | ----------------- |
| Total reports                    | 1,000             |
| Ground-truth incidents           | 100               |
| Direct victim reports            | 35%               |
| Relative/third-party reports     | 25%               |
| Volunteer reports                | 20%               |
| Shelter/responder reports        | 20%               |
| Duplicate or overlapping reports | 25–35%            |
| Contradictory reports            | 10–15%            |
| Ambiguous locations              | 20–30%            |
| Missing critical fields          | 20–30%            |

These percentages are dataset-generation targets, not estimates of actual disaster-report distributions.

Include:

- Hindi and English code-switching.
- A selected regional language, preferably Malayalam or Konkani depending on available speech support.
- Noisy and clipped audio.
- Incorrect landmark names.
- Multiple landmarks with similar names.
- People reporting on behalf of others.
- Multiple families in one building.
- Changed household locations.
- Stale and conflicting reports.
- Malicious or deliberately misleading submissions.
- Offline device synchronization and replay.

Every generated report must retain a known ground-truth incident, household, source and location.

Do not use generated data to claim real-world disaster performance.

## 9.2 Baseline comparisons

We need to prove the value of each technical contribution.

| Experiment        | Baseline              | Raahat improvement                     |
| ----------------- | --------------------- | -------------------------------------- |
| Speech            | Whisper-base          | Prisma versus Whisper                  |
| Geolocation       | Nearest landmark      | Candidate ranking + active questioning |
| Entity resolution | Exact/fuzzy matching  | Evidence-aware probabilistic matching  |
| Deduplication     | Aggressive threshold  | Conservative matching + review         |
| Triage            | Simple weighted score | Explicit uncertainty-aware policy      |
| Connectivity      | Online-only ingestion | Offline durable synchronization        |

### Key metrics

Geospatial intelligence

# Top-1

Candidate accuracy

# Top-3

Candidate recall

# MAE

Geographic error in metres

# ECE

Confidence calibration

Entity resolution

- B-cubed precision, recall and F1.
- False merge rate.
- Missed duplicate rate.
- Human review rate.

  Safety and triage
- High-severity recall.
- Under-triage rate.
- False escalation rate.
- Unknown-field preservation.

  Systems performance
- Report ingestion throughput.
- p50/p95/p99 processing latency.
- Worker queue wait.
- Restart recovery time.
- Offline synchronization success.
- Duplicate submission suppression.

## 9.3 Proposed engineering acceptance gates

These are initial targets for the controlled benchmark, not established results.

| Test                                              | Initial target           |
| ------------------------------------------------- | ------------------------ |
| High-severity incident recall                     | ≥99%                     |
| False household/incident merges                   | ≤1%                      |
| Location candidate recall at top 3                | ≥90%                     |
| Evidence provenance coverage                      | 100%                     |
| Idempotent duplicate submissions                  | 100%                     |
| Offline synchronization after reconnection        | 100% in tested scenarios |
| Unauthorized dispatch actions                     | 0                        |
| Audit history alteration through application APIs | 0                        |

We should report confidence intervals, dataset size and failure examples alongside every result.

A 99% recall figure on a small synthetic dataset is not a 99% real-world safety guarantee.

## 9.4 Ablation study

Run these configurations on identical frozen test sets:

## Research experiment matrix

A

Conventional baseline

ASR + simple extraction + nearest landmark

B

Geospatial upgrade

Candidate ranking and active clarification

C

Evidence graph

Source provenance and conservative resolution

D

Safety policy

Unknown-aware deterministic prioritization

E

Full Raahat

All components combined, including offline ingestion

This tells us whether the proposed novelty actually improves the system.

### Three research questions

RQ1: Does active clarification improve location accuracy compared with nearest-landmark matching?

RQ2: Does evidence-aware entity resolution reduce false incident merges while maintaining duplicate detection performance?

RQ3: Does explicit uncertainty preservation reduce under-triage compared with conventional weighted urgency scoring?

I would make RQ1 and RQ2 the primary paper contributions. RQ3 is a supporting safety evaluation.

### Gnani-specific experiment

This should be an independent experiment.

Use the exact same audio clips for both recognizers:

- Whisper-base baseline.
- Gnani Prisma.
- Identical audio preprocessing.
- Identical ground-truth transcripts.
- Identical landmark evaluation set.

Measure:

1. Overall WER.
2. Landmark-name transcription accuracy.
3. Named entity error rate.
4. Correct top-1 location.
5. Geographic distance from ground truth.
6. Clarification questions required.

The primary result should be location error after speech processing, not merely which recognizer has lower WER.

Also report language, noise and code-switching breakdowns.

# 10. Reliability, security and disaster safety

Raahat deals with highly sensitive information. The system must be designed accordingly.

## 10.1 Safety rules

| Rule                                          | Enforcement                          |
| --------------------------------------------- | ------------------------------------ |
| No AI-authorized rescue                       | Human permission required            |
| No fabricated medical guidance                | Scripted, vetted messages only       |
| Unknown never means safe                      | Missing fields remain unknown        |
| No destructive deduplication                  | Reversible relationships             |
| No unverified map pins presented as confirmed | Explicit location status             |
| No silent priority downgrades                 | Audited policy transitions           |
| No automatic callback loops                   | Consent and retry controls           |
| No unverified volunteer access                | Authentication and role-based access |

## 10.2 Security architecture

Implement:

- Role-based access control.
- Organisation and disaster-level data isolation.
- Encrypted transport.
- Encrypted storage and backups.
- Minimal collection of personally identifiable information.
- Secure token storage on field devices.
- Device revocation.
- Signed and idempotent synchronization requests.
- Rate limits and abuse detection.
- Retention and deletion policies for recordings.
- Audit records for sensitive data access.

A particularly important distinction: append-only audit history is not automatically tamper-proof. Use restricted database roles, external backup protection and, for stronger tamper evidence, cryptographic hash chaining or independently retained audit exports.

## 10.3 Fault injection scenarios

| Failure                       | Expected behaviour                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------------------- |
| Whisper process crashes       | Report remains persisted and retries                                                                    |
| LLM unavailable               | Rule-based extraction/review fallback                                                                   |
| PostgreSQL unavailable        | Ingestion rejected safely or retained in a local durable channel; never acknowledge unpersisted reports |
| Internet disappears           | Field device queues reports locally                                                                     |
| Worker crashes                | Expired lease allows recovery                                                                           |
| Duplicate sync request        | Idempotency prevents duplicate report creation                                                          |
| Operator disconnects          | State remains persisted                                                                                 |
| Callback provider unavailable | Job remains retryable; no false success                                                                 |
| GPS unavailable               | Landmark/manual location workflow continues                                                             |
| Incorrect entity merge        | Authorized reviewer can reverse it                                                                      |

One important implementation detail: an offline field device must be able to accept a report without waiting for server acknowledgement. The user interface must clearly distinguish locally saved from server synchronized.

# 11. Deployment architecture

The first deployable version should be simple.

Docker Compose deployment

Nginx

Reverse proxy / TLS / rate limits

API

FastAPI / REST / SSE

Worker

ASR / processing / sync

PostgreSQL + PostGIS

Reports / incidents / evidence / outbox / audit

Prometheus

Metrics

Grafana

Dashboards

For the initial deployment:

- One API process or a small number of API workers.
- One or more independently configurable processing workers.
- One PostgreSQL primary.
- Persistent database volumes.
- Separate resource limits for ASR and general processing.
- Backups and tested restoration.
- Health checks and readiness checks.

Horizontal scaling is a later validation step. Multiple API instances must share authoritative state, and workers must use database leases with fencing. Merely increasing a Compose replica count does not prove safe scaling.

### Deployment acceptance checklist

- Clean Docker image build.
- Compose startup from a fresh environment.
- PostgreSQL migrations execute.
- Application health checks work.
- Worker recovery tested.
- Persistent data survives restart.
- Backup restoration tested.
- Prometheus scrapes metrics.
- Grafana dashboards load.
- No secrets in the repository.
- No unnecessary public database ports.
- All documented commands verified.

Kubernetes manifests are not an MVP requirement. Keep them only if we actually validate them on a cluster.

# 12. Exact implementation order and change-control rules

Before modifying the existing repository, we need a controlled migration.

I would use these gates:

| Gate | Requirement before proceeding                         |
| ---- | ----------------------------------------------------- |
| G0   | Existing tests and API contracts documented           |
| G1   | New report model works without breaking IVR           |
| G2   | Evidence and incident relationships persist correctly |
| G3   | Location uncertainty and offline sync work            |
| G4   | Incident resolution and triage pass safety tests      |
| G5   | Human-controlled rescue workflow works end-to-end     |
| G6   | Deployment, evaluation and documentation verified     |

### Repository migration rules

1. Tag the current working implementation as a baseline.
2. Save the current test results and simulation outputs.
3. Add database migrations rather than replacing existing tables.
4. Keep the existing IVR API compatible during the transition.
5. Add new functionality behind interfaces.
6. Migrate existing call records into the new report model.
7. Run regression tests after each migration.
8. Remove old incident-creation behaviour only after all callers have migrated.

One important limitation: I have the implementation history, but the actual Raahat source tree has not been provided or found in the accessible Library. Therefore, the file tree above is the proposed target structure, and the migration instructions are exact at the subsystem and interface level, not verified file-by-file edits. I won't invent existing filenames or claim to have inspected code I haven't seen.

The first coding task must be a repository audit that maps the existing files and tests to this specification.

# 13. Research and institutional positioning

The following references should form the foundation of the project proposal.

| Reference                                                                                                                                                                                | What it establishes                                      |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| [MHA — Emergency Response Support System](https://www.mha.gov.in/emergency-response-support-system-erss?utm_source=chatgpt.com)                                                          | Existing national multi-channel emergency infrastructure |
| [Kerala SDMA — Communication](https://sdma.kerala.gov.in/communication/?utm_source=chatgpt.com)                                                                                          | Real disaster communication redundancy                   |
| [Kerala Floods: Lessons from Crowdsourced Technology (2020)](https://www.sciencedirect.com/science/article/pii/S1877050920313077?utm_source=chatgpt.com)                                 | Reliability and verification issues in disaster reports  |
| [CAG — Punjab ERSS Audit](https://www.cag.gov.in/en/audit-report/details/124583?utm_source=chatgpt.com)                                                                                  | Documented implementation and operational issues         |
| [National Disaster Management Plan](https://www.mha.gov.in/sites/default/files/2022-08/National%2520Disaster%2520Management%2520Plan%2520May%25202016%5B1%5D.pdf?utm_source=chatgpt.com) | Communication contingency and interoperability           |
| [National Disaster Management Plan — MHA](https://www.mha.gov.in/documents/national-disaster-management-plan?utm_source=chatgpt.com)                                                     | National disaster management framework                   |

A qualification on the CAG source: its ERSS audit is specifically about Punjab. It is evidence of problems identified in that implementation, not proof that every state's ERSS has the same deficiencies.

### How I would position Raahat academically

Proposed paper title:

Raahat: Uncertainty-Aware Multichannel Incident Intelligence for Resilient Disaster Response

Potential contributions:

1. An evidence-preserving architecture for heterogeneous disaster reports.
2. Active landmark disambiguation under geographic uncertainty.
3. Conservative multi-source entity and incident resolution.
4. An offline-first ingestion and synchronization mechanism.
5. A reproducible benchmark for evaluating incident intelligence under noisy, incomplete and conflicting reports.

Do not claim that the entire architecture is novel simply because it combines existing technologies. The research contribution needs to be demonstrated through the algorithms, experiments and comparative results.

# 14. Final project acceptance criteria

Raahat 2.0 is complete when all of these are satisfied.

Project completion checklist

# 0/25

Core platform

Multiple report sources use one ingestion contract

Reports and incidents are separate entities

Evidence retains source and provenance

PostgreSQL/PostGIS migrations work

Durable worker processing and recovery work

Intelligence

Location candidates and uncertainty are represented

Active clarification is evaluated

Conservative incident resolution works

Contradictory evidence is preserved

Explainable triage preserves unknown fields

Resilience

Offline reports persist locally

Synchronization is idempotent

Radio reports can be manually ingested

Network and worker failures are tested

Stale and unverified information is visible

Operations

Operator can verify incidents

Resource assignment requires human approval

Rescue lifecycle is tracked

All sensitive decisions are audited

Live GIS reflects evidence status

Research and deployment

Baseline and ablation experiments run

RaahatBench ground truth is frozen

Metrics and failure cases are published

Docker Compose is actually tested

Limitations and deployment runbook are documented

Your manual project acceptance tracker

Reset

# 15. The final strategic decision

Final specification

# Raahat 2.0

Resilient Disaster Intelligence & Rescue Coordination

When communication fails, rescue information must keep moving.

Primary system

Multichannel report ingestion + evidence graph + geospatial intelligence + human-controlled operations.

Primary research contribution

Uncertainty-aware geospatial incident resolution and conservative multi-source evidence fusion.

Primary AI contribution

Multilingual speech intelligence, structured evidence extraction and active location clarification.

Primary systems contribution

Offline-first ingestion, durable event processing, idempotent synchronization and fault recovery.

Primary demonstration

A simulated flood scenario in which disconnected reports from victims, relatives, volunteers and radio operators become verified incidents and human-approved rescue operations.

## What I want us to do first

I would not immediately start adding more AI models or deployment infrastructure.

I would execute these three steps in order:

1. Repository audit: identify the real files, existing APIs, models, database and test coverage.
2. Domain migration: introduce Report, Evidence, Incident and Household as distinct entities while preserving the working IVR.
3. First end-to-end scenario: simulate a village with no connectivity, receive reports through an offline volunteer device and a radio operator, synchronize them later, resolve duplicates and produce a verified rescue queue.

That third demonstration is the defining moment of Raahat 2.0.

My recommendation is to freeze this specification as `RAAHAT_SPEC.md` and treat it as the project's architectural contract. Every subsequent feature should justify itself against it.

I can take the next step by auditing the actual repository and producing a file-by-file migration plan, including which existing code to preserve, modify, replace and test.