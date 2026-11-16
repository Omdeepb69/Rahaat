# Resource budget

All figures measured on the target laptop (i3-1125G4, 8 GB RAM, Ubuntu 24.04)
on 2026-11-16, with the containerised stack from `compose.yaml` and
test-fixture data. Other desktop applications were running; about 2.5 GB of
memory was available to the system during the tests.

## Memory and CPU

| Container | Limit | Idle RSS | Peak RSS under load | Peak CPU under load |
|---|---|---|---|---|
| api | 512 MB | 97 MiB | 118 MiB | 115% (of one core) |
| db | 768 MB | 68 MiB | 124 MiB | 45% |
| worker | 384 MB | 65 MiB | 66 MiB | <1% (no audio in the load) |
| **Total** | 1.6 GB | **230 MiB** | **~310 MiB** | |

Load: 200 operator reports at concurrency 4, twice (400 incidents).
PostgreSQL is tuned for this host in `compose.yaml` (`shared_buffers=256MB`,
`max_connections=40`, `work_mem=8MB`). The API's connection pool is 5 + 5
overflow.

Not run on this machine: any local language model. A 30B model (Gnani Evon)
needs far more memory than the laptop has; translation and model extraction
are remote only.

## Latency (API, measured from the host, warm)

| Operation | p50 | p95 |
|---|---|---|
| Enter a report (full analysis: language, extraction, landmarks, duplicates, triage), 200 incidents in the operation | 275 ms | 384 ms |
| Same, 400 incidents | 363 ms | 482 ms |
| List 50 open incidents | 9.6 ms | 16.3 ms |
| Incident detail | 31 ms | 36 ms |
| Dispatch recommendation | 4.8 ms | 6.3 ms |
| Dispatch queue | 3.9 ms | 4.7 ms |
| System status | 9.0 ms | 10.7 ms |
| Health (readiness) | 21 ms | 27 ms |
| Change committed → delivered on an open event stream | under 1 s (measured 0.9 s before the per-notification wake-up fix) | |
| Voice note transcription (Gnani Prisma, 4–6 s clip) | 0.7–1.4 s | |

Intake throughput at concurrency 4: 11–15 reports/second. Before the duplicate
matching change (DECISIONS.md D17), report intake took 1.25 s at p50 with 200
incidents and grew with every incident.

The per-user limit (600 requests/minute) was reached by the load script in the
third batch and returned HTTP 429, as designed. Operators working normally
stay far below it.

## Storage

| Item | Size |
|---|---|
| Backend image | 460 MB |
| Database after ~420 reports, 457 landmark names, audit trail | 25 MB |
| Backup of that database (custom format, compressed) | 72 KB for a small operation; scales with reports |
| Web app bundle | 335 KB JS (105 KB gzip) initial; map 154 KB (45 KB gzip), loaded on first map view; fonts subset per script |

## Failure timing (browser)

| Event | Measured |
|---|---|
| API stopped → "Server unreachable" banner | 5.8 s |
| API restarted → "Live" again, missed changes replayed | 6.4 s |
| API shutdown with open event streams | 0.1 s (bounded at 5 s; previously did not finish) |
| Silent network loss (no TCP close) | detected by the 15 s readiness probe or the 40 s stream watchdog; not measured |

## Limits to watch

- **Disk**: the health check warns below 10% free. This laptop's data
  partition had 17% free during testing.
- **Memory**: the containers fit comfortably; the risk is other applications.
  The health check warns below 500 MB available.
- **Single API process**: rate limits and the event listener are per process,
  so the API deliberately runs one worker process. It handled the load above
  at roughly one core.
