# Raahat 2.0: Security Architecture & Threat Model

Security design principles, trust boundaries, and invariants for the Raahat Disaster Intelligence Platform (RAAHAT_SPEC §10).

---

## 1. Core Security Invariants

The Raahat architecture enforces non-negotiable security and safety invariants:

| Security Rule | Enforcement Mechanism | Failure Mode Containment |
| :--- | :--- | :--- |
| **Zero Autonomous Dispatch** | API and Domain validation requires `dispatcher_id` on all operational transitions | Algorithmic proposals are held in `PROPOSED` status until an authenticated operator explicitly approves deployment |
| **Tamper-Evident Audit Trail** | Cryptographic SHA-256 hash chaining across operational events | Modifying, omitting, or reordering historical records invalidates `verify_entity_chain()` |
| **Non-Root Execution** | Docker containers execute under dedicated unprivileged user `raahat` (`uid 10001`) | Eliminates host privilege escalation in the event of container process compromise |
| **Database Port Isolation** | PostGIS database port `5432` has zero host port mappings | Database is strictly reachable via internal Docker bridge network (`raahat-net`) |
| **Sensitive PII Masking** | Recursive `sanitize_payload()` masking on SSE streams and loggers | Distressed citizen phone numbers are masked (`+9198*****210`) in live dispatcher broadcasts |

---

## 2. Trust Boundaries & Network Segmentation

```
[ UNTRUSTED ZONE ]
 - Public Internet / Caller telephony (IVR SIP webhooks)
 - Citizen web SOS forms & SMS gateways
 - Field volunteer mobile devices (Offline SQLite sync)
                     │
                     ▼
          [ GATEWAY PERIMETER ]
       Nginx Reverse Proxy (:8080)
       - Rate limiting & request size limits (25MB max)
       - HTTP Security Headers (nosniff, SAMEORIGIN, XSS protection)
       - Unbuffered SSE proxying
                     │
                     ▼
          [ APPLICATION BOUNDARY ]
         FastAPI Ingestion & Operations (:8000)
         - Dispatcher header validation (`X-Dispatcher-Id`)
         - Input schema validation via Pydantic extra="forbid"
         - Multi-source evidence resolution & candidate ranking
                     │
                     ▼
          [ SECURE DATA BOUNDARY ]
       PostgreSQL 16 + PostGIS (Port 5432 - NO PUBLIC EXPOSURE)
       - Authenticated connections
       - Row-level outbox leasing with fencing tokens
       - Append-only audit log tables
```

---

## 3. Threat Modeling & Mitigations

### Threat 1: Malicious Distressed Report Spoofing (Sybil Attack)
- **Attack Vector**: Adversary submits automated false flood reports to divert emergency rescue resources from real disaster zones.
- **Mitigations**:
  1. Multi-source evidence corroboration: Single-source reports remain `UNVERIFIED` until corroborating evidence from trusted volunteers, satellite GIS, or official radio dispatch is registered.
  2. Geographic consistency filtering: Reports with coordinates outside declared disaster zones are flagged for manual operator review.
  3. Strict Human-in-the-Loop approval: Automated pipelines **cannot** authorize boat or helicopter dispatch without human operational sign-off.

### Threat 2: Split-Brain Zombie Worker Writes
- **Attack Vector**: Worker node hangs due to high ASR CPU load, losing its outbox lease. A second worker reclaims and completes the job. The hung worker unfreezes and attempts to overwrite the job result.
- **Mitigations**:
  - Monotonic `lease_token` (fencing token): Every claim generates a fresh UUID token. The update statement enforces `WHERE id = :id AND lease_token = :token`. Stale writes from zombie workers fail silently or log a warning without corrupting database state.

### Threat 3: Offline Sync Device Impersonation
- **Attack Vector**: Tampered field client attempts to overwrite report sequence numbers or inject reports under another volunteer's `device_id`.
- **Mitigations**:
  - `DeviceSyncService` validates that the authenticated `device_id` matches the batch payload.
  - Monotonic sequence checks detect sequence gaps and duplicate submissions idempotently.

---

## 4. Cryptographic Audit Log Verification

All state-mutating actions (incident verification, merge reviews, unmerge operations, assignment proposals, approvals, cancellations) append to `audit_events`.

### Hash Chaining Formula
$$\text{Hash}_i = \text{SHA-256}(\text{Hash}_{i-1} \parallel \text{Timestamp} \parallel \text{ActorID} \parallel \text{Action} \parallel \text{EntityType} \parallel \text{EntityID} \parallel \text{PayloadHash})$$

Where Genesis Hash ($i=0$) is a deterministic SHA-256 anchor.

To verify audit integrity:
```bash
docker compose exec api python -c "
from raahat.infrastructure.database.session import get_sync_sessionmaker
from raahat.infrastructure.database.repositories.audit import PostgresAuditRepository
from raahat.infrastructure.audit.verifier import AuditVerifier

repo = PostgresAuditRepository(session_factory=get_sync_sessionmaker())
verifier = AuditVerifier(repository=repo)
summary = verifier.verify_all_chains()
assert summary.is_valid, 'Cryptographic audit verification failed!'
print('Verification successful:', summary.chains_verified, 'chains verified.')
"
```
