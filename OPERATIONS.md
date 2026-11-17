# Operations

## Before a shift

1. `./scripts/health-check.sh https://<public-host>`: all lines OK.
2. In the web app, *System status*: core services operational; check which
   providers are configured (speech, translation, geocoder, routing, alerts).
3. Confirm the latest backup is less than an hour old during an active
   operation.
4. Laptop on mains power, suspend on lid close disabled.

## What operators see when something fails

| Failure | Interface | Data |
|---|---|---|
| Laptop off, asleep, tunnel down, network lost | Red banner "The RAAHAT server cannot be reached", time of last confirmed data and its age; header shows *Server unreachable*. Saving is refused with a clear message. | Data on screen stays visible and labelled with its age; it is not presented as current. |
| Database down, API up | Amber banner "server is not healthy" (readiness fails). | As above. |
| Live updates interrupted | Header shows *Reconnecting*. On reconnect, missed changes are replayed by sequence number; if the gap is too large, all views reload. | Polling every 60 s continues as a backstop. |
| Worker stopped | *System status*: worker unavailable with heartbeat age and number of waiting reports. Reports entered by operators are still analysed immediately; voice and SMS reports wait. | Queue is the database; nothing is lost. |
| Speech provider down or not configured | Report shows "Audio was not transcribed … Listen to the recording." Recording is playable. | The report still becomes an incident. |
| Translation/model provider down | Original text and rule-based facts are shown; no translation. The failure is recorded in the report's processing history. | |
| Geocoder or routing not configured | Lookup button reports it is not configured; distances are labelled straight-line. | |

## Monitoring

- `./scripts/health-check.sh` exits non-zero on any failure; run it from cron
  and alert yourself on failure, e.g.
  `*/5 * * * * cd /path/to/rahaat && ./scripts/health-check.sh > /dev/null || notify-send "RAAHAT health check failed"`.
- *System status* in the web app refreshes every 30 s.
- Logs are JSON lines, one per request (`raahat.access`) with request id,
  user id, path, status and duration: `docker compose logs -f api`.
  Docker rotates them at 10 MB × 5 files per container.

## Accounts

Staff sign in by choosing their **state**, then their **district** (or the
state control room), then the password issued to that control room. There is
one account per control room:

| Account | Sees | Role |
|---|---|---|
| National administration | Every operation in every state | Administrator: also issues passwords |
| State control room | Every operation in its state, all districts | Control room |
| District control room | Only operations in its district | Control room |

The server enforces this on every request and on the live event stream;
anything outside the account's area is answered as "not found".

- **Create every account at once** (prints passwords once, as CSV):
  `docker compose exec -T api raahat-entrypoint cli provision-accounts --all > secrets/control-room-passwords.csv`
  Keep that file private (`secrets/` is git-ignored, mode 600) and hand each
  control room only its own line. `--states 32,21` limits it to some states;
  `--reset` replaces existing passwords.
- **Replace one password**: national administration, *Control room accounts*
  page, *New password*. The old password stops working and its sessions end.
- **Suspend** a control room from the same page.
- Passwords are random (four groups of four characters), never derived from the
  state or district, and stored only as scrypt hashes.

## Public reporting site

- Requires `PUBLIC_INTAKE_ENABLED=true`.
- After deploying, synthesise the spoken questions once so callers never wait:
  `docker compose exec api raahat-entrypoint cli warm-voice-prompts`
  (82 clips through Gnani Timbre, cached under the audio volume).
- A call is routed by the state and district the caller chooses: to the newest
  active operation for that district, else the newest state-wide one, else a
  standing "<District>: public emergency reports" operation created on first
  use. Open a named operation for the district and new calls go there.
- A call the caller abandons is sent as a report by the worker three minutes
  after its last answer.

## Running an operation

1. *Operations setup*: open an operation with a map focus (landmark searches are
   limited to 75 km around it).
2. Import landmarks for the area (`cli import-landmarks`, ≤1 square degree per
   call; repeat for adjacent tiles).
3. Set `CAP_ALERT_FEED_URL` to the state's SACHET feed.
4. Register resources with capabilities and positions; keep positions current.
   Positions older than 2 hours are greyed on the map and flagged in
   recommendations.
5. When the response ends, close the operation (records are kept; new reports
   are refused).

## Data retention

RAAHAT keeps everything until removed. Caller names and phone numbers are in
`reports.caller_name`, `reports.caller_contact` and the original payload.
Agree a retention period with the responsible authority. Removing data is a
database operation outside the application; take a backup first and record
the decision.

## Removing the old stack

See DEPLOYMENT_LOCAL.md, "The previous stack".
