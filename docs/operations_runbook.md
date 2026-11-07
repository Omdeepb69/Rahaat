# Raahat 2.0: Operations & Incident Response Runbook

Operational procedures, recovery protocols, and runbook for operating the Raahat Disaster Intelligence Platform under flood emergencies.

---

## 1. System Architecture & Startup Procedure

The Raahat production platform is orchestrated via Docker Compose (`compose.yaml`) with 6 interconnected services:

```
[ Internet / Field / Responders ]
               │
               ▼
       [ Nginx Gateway ] (:8080)
         │           │
         │           ▼
         │      [ Operator Console UI ] (/console/)
         ▼
     [ FastAPI ] (:8000)
    (Ingestion, Triage, SSE)
         │
         ├───► [ PostgreSQL 16 + PostGIS ] (Authoritative data store)
         │
     [ Background Worker ]
   (Outbox Leasing, Callbacks)
         ▲
         │ (Scraping)
   [ Prometheus ] (:9090) ───► [ Grafana Dashboards ] (:3000)
```

### Standard Startup Sequence

1. **Verify Environment Configuration**:
   ```bash
   cp .env.example .env
   # Ensure POSTGRES_PASSWORD and GRAFANA_ADMIN_PASSWORD are set
   ```

2. **Launch Compose Stack**:
   ```bash
   docker compose up -d
   ```

3. **Verify Service Health Status**:
   ```bash
   docker compose ps
   # Ensure db, api, worker, proxy, prometheus, grafana report "healthy"
   ```

4. **Verify Database Migrations**:
   The `api` container automatically executes `alembic upgrade head` on startup via `entrypoint.sh`. To verify migration head status manually:
   ```bash
   docker compose exec api alembic current
   ```

5. **Access Gateways**:
   - **Operator Console**: `http://localhost:8080/console/`
   - **API Health**: `http://localhost:8080/healthz`
   - **Prometheus Metrics**: `http://localhost:8080/metrics`
   - **Grafana Dashboards**: `http://localhost:3000` (Login: `admin` / `${GRAFANA_ADMIN_PASSWORD}`)

---

## 2. Emergency Incident Response & Failure Remediation

### Scenario A: Background Worker Crash / Unresponsiveness
- **Symptom**: `raahat_outbox_queue_pending_jobs` gauge rising above threshold (>50 jobs) or `/tmp/worker_heartbeat` age > 2 minutes.
- **Root Cause**: Worker node segmentation fault during ASR processing, hardware reboot, or unhandled exception.
- **Automated Recovery Invariant**:
  - Outbox jobs claimed by the crashed worker carry an explicit `lease_expires_at` deadline (default: 30 seconds).
  - When the lease expires, surviving or replacement workers automatically reclaim the jobs using `SELECT ... FOR UPDATE SKIP LOCKED`.
  - The monotonic `lease_token` (fencing token) ensures that if the frozen worker unfreezes later, any attempt to settle stale writes is rejected by the database.
- **Operator Action**:
  ```bash
  # Check worker container logs
  docker compose logs --tail 100 worker

  # Restart worker container
  docker compose restart worker
  ```

### Scenario B: Database Connection Partition or Failover
- **Symptom**: HTTP 503 / 500 errors on report ingestion, `OperationalError: could not connect to server`.
- **Safety Invariant**:
  - The ingestion gateway strictly rejects unpersisted submissions with HTTP 503/500 and **never returns a false positive acknowledgement** (`IngestionResult`).
  - Offline field volunteer clients buffer submissions in local SQLite storage with monotonic sequence numbers until the server confirms receipt.
- **Operator Action**:
  ```bash
  docker compose ps db
  docker compose logs --tail 50 db
  ```

### Scenario C: Telephony SIP Trunk / Carrier Outage
- **Symptom**: Scheduled callbacks report `502 Bad Gateway` from provider.
- **Automated Invariant**:
  - `CallbackScheduler` applies exponential backoff with jitter.
  - If errors persist, jobs transition to `EXHAUSTED` after 3 retries.
  - **Zero Infinite Redial Loops**: Callbacks never continuously dial distressed citizens without backoff.
- **Operator Action**:
  - Inspect provider credentials and trunk status.
  - Query exhausted callback jobs via API: `GET /api/v1/telephony/callbacks?status=exhausted`.

### Scenario D: Erroneous Incident Merge by Dispatcher
- **Symptom**: Two distinct households were erroneously merged into a single incident cluster by an operator.
- **Remediation Procedure**:
  - Execute a reversible unmerge via the Operator Console Investigation workspace or API:
    ```bash
    curl -X POST http://localhost:8080/api/v1/incidents/review-link \
      -H "Content-Type: application/json" \
      -H "X-Dispatcher-Id: <dispatcher-uuid>" \
      -d '{
        "source_incident_id": "<source-uuid>",
        "target_incident_id": "<target-uuid>",
        "action": "unmerge",
        "reason": "Mistaken merge: distinct households separated by canal",
        "merge_event_id": "<event-uuid>"
      }'
    ```
  - **Audit Invariant**: The source incident is reopened to `UNVERIFIED`, corroborating reports are cleanly detached, and an append-only `incident.unmerged` cryptographic audit entry is recorded.

---

## 3. Backup and Disaster Recovery

### Automated Database Backup
To perform an authoritative logical backup of PostGIS spatial tables and audit logs:
```bash
docker compose exec -T db pg_dump -U postgres -Fc raahat > backup_raahat_$(date +%Y%m%d_%H%M%S).dump
```

### Restoration Protocol
1. Stop API and Worker containers:
   ```bash
   docker compose stop api worker
   ```
2. Restore database:
   ```bash
   docker compose exec -T db dropdb -U postgres --if-exists raahat
   docker compose exec -T db createdb -U postgres raahat
   docker compose exec -T db pg_restore -U postgres -d raahat < backup_raahat_*.dump
   ```
3. Verify Audit Log Hash Chain Integrity:
   ```bash
   docker compose exec api python -c "
   from raahat.infrastructure.database.session import get_sync_sessionmaker
   from raahat.infrastructure.database.repositories.audit import PostgresAuditRepository
   from raahat.infrastructure.audit.verifier import AuditVerifier

   repo = PostgresAuditRepository(session_factory=get_sync_sessionmaker())
   verifier = AuditVerifier(repository=repo)
   result = verifier.verify_all_chains()
   print('Audit Chains Valid:', result.is_valid, 'Total Events:', result.total_events_checked)
   assert result.is_valid, 'AUDIT CHAIN CORRUPTED!'
   "
   ```
4. Restart services:
   ```bash
   docker compose start api worker
   ```
