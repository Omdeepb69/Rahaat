# Raahat 2.0: System Limitations & Explicit Boundaries

Honest, unhedged disclosure of technical boundaries, scientific assumptions, and operational constraints for the Raahat platform (RAAHAT_SPEC §11, §15).

---

## 1. Synthetic Benchmark Evaluation vs. Real-World Efficacy

- **Synthetic Nature of RaahatBench**: The RaahatBench benchmark suite (1,000 synthetic reports across 100 ground-truth incidents) was constructed to evaluate algorithmic failure modes (ambiguous landmarks, code-switching, missing facts, contradictory accounts, and offline replay) under controlled conditions.
- **No Direct Real-World Safety Claim**: Achieving ≥99% high-severity recall and ≤1% false merge rates on synthetic benchmarks demonstrates that the safety triage rules and probabilistic spatial candidate ranking algorithms behave as mathematically intended. It **does not** prove that the system will achieve identical safety figures during an unconstrained real-world disaster.
- **Acoustic Profiling**: Simulated audio metadata (SNR 4–22 dB, amplitude clipping, background motor/rain noise) approximates typical distress acoustic environments but cannot reproduce the hyper-local acoustic dynamics, panic-induced vocal deformation, or microphone degradation experienced during catastrophic floods.

---

## 2. Speech Recognition & Dialect Boundaries

- **Whisper-Base Baseline Limitations**: The local Whisper-base speech recognizer is resource-efficient and runs on standard CPU containers, but exhibits known degradation on short monosyllabic responses, code-switched Indic phrases, and rapid regional speech (e.g., colloquial Malayalam or rural Hindi).
- **Vendor Adapter Boundary**: The Gnani Prisma and local Piper TTS adapters are engineered behind abstract protocols (`SpeechRecognizer`, `TTSSynthesizer`). While interfaces and segment-level confidence parsing are implemented, production deployment in specific disaster zones requires provisioning authenticated cloud API keys or downloading regional acoustic model checkpoints.
- **Keypad Fallback Requirement**: The automated IVR agent incorporates a mandatory keypad DTMF fallback after two consecutive low-confidence speech turns. In areas with high background noise, operators must expect a subset of callers to transition to numeric keypad entry.

---

## 3. Deployment & Scaling Boundaries

- **Single-Node PostgreSQL / PostGIS Primary**: The MVP deployment utilizes a single PostgreSQL 16 primary container with PostGIS extensions. While sufficient for handling hundreds of incoming reports per minute, massive regional disasters generating tens of thousands of concurrent reports per minute will bottleneck database connection pools and row-level `FOR UPDATE SKIP LOCKED` lease contention.
- **Horizontal Scaling Post-MVP**: Multiple FastAPI replicas can safely share state because PostgreSQL is the single source of truth and outbox leasing uses fencing tokens. However, multi-region active-active database clustering and distributed message brokers (e.g., Apache Kafka) are post-MVP enhancements.
- **In-Memory SSE Pub/Sub**: The real-time Server-Sent Events (SSE) broadcaster currently operates in-process within each FastAPI instance. If multiple API instances are deployed behind a load balancer, dispatcher consoles must be sticky-session routed, or an external pub/sub backbone (such as Redis or PostgreSQL `LISTEN`/`NOTIFY`) must be enabled for cross-worker event fanout.

---

## 4. Hardware & Emergency Dispatch Boundaries

- **Decision-Support Only (Zero Autonomous Dispatch)**: Raahat **never** automatically deploys rescue boats, medical teams, or evacuation vehicles. Every rescue assignment is created in `PROPOSED` status and strictly requires an authenticated human dispatcher to review evidence and sign off (`APPROVED`).
- **No Direct Radio (HAM/VHF) Hardware Demodulation**: The radio channel is an adapter layer that ingests transcribed spot reports from radio operators or automated audio capture gateways; software-defined radio (SDR) hardware and RF demodulation are outside the application boundary.
- **No Real Government 112 API Integration**: The platform provides standard REST ingestion and webhooks suitable for emergency operations centers (EOCs). Direct integration into government 112 emergency routing backbones requires state-level memorandums of understanding, security vetting, and dedicated leased lines.
