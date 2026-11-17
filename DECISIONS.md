# RAAHAT — Decision record

Each entry states the decision, why, and what was rejected. Newest last.

## D1 — Targeted refactor of the backend, not a rewrite

The domain logic (triage rules, evidence extraction, duplicate matching,
gazetteer, audit chain, outbox) is sound and covered by tests. The defects are
at the edges: no authentication, no cross-process realtime, non-atomic audit,
fabricated fallbacks. Those are replaced; the core is kept.

Rejected: rewriting in another framework (no benefit), splitting into services
(one host with 8 GB RAM, one team).

## D2 — One operator frontend; `operator_console/` and `dashboard/` are replaced by `web/`

Two frontends implemented the same screens. `dashboard/` was the more complete
but nearly every file needed rewriting (data layer, routing, layout, styling),
so the new app lives in a new directory with an accurate name and the two old
ones are deleted. The stack is unchanged: Vite, React, TypeScript, react-router,
Leaflet.

Rejected: migrating to Next.js. The app is an authenticated SPA with no SEO or
server-rendering need, and the mission forbids backend logic in the frontend
host. A static build deploys to Vercel as-is. The API base URL variable is
therefore `VITE_API_BASE_URL` rather than `NEXT_PUBLIC_API_BASE_URL`.

## D3 — Real user accounts; formula passwords removed

Jurisdiction-derived passwords are public knowledge. Replaced with a `users`
table, scrypt hashes (stdlib `hashlib.scrypt`, N=2¹⁵, r=8, p=1), one role per
user, and an administrator-only user management API. No account is created by
migrations or at startup; `python -m raahat.cli create-admin` creates the first
one on the host.

Rejected: argon2 (adds a compiled dependency for no practical gain at this
scale); a default admin password (would be a shipped credential).

## D4 — Bearer tokens in the Authorization header, not cookies

The frontend (Vercel) and backend (tunnel hostname) are different sites.
Cross-site cookies need `SameSite=None` and are blocked by default in Safari and
increasingly elsewhere. A bearer token held in memory and `sessionStorage`
works on every browser and removes CSRF from the threat model. Tokens are
short-lived; a refresh endpoint re-issues while the session is active.

Consequence: the browser `EventSource` API cannot send headers, so the SSE
client is implemented on `fetch` with a streaming reader.

## D5 — PostgreSQL is the queue, the event log and the notifier; no Redis

Outbox polling with `SKIP LOCKED` already existed. `LISTEN/NOTIFY` gives
push-style wake-ups for SSE without another process. On an 8 GB laptop every
avoided service matters.

## D6 — Persisted event log with sequence-based replay

Realtime that depends on being connected at the moment of the event is not
safe for operations. Every operational event is a row; the stream is a view of
that table. A reconnecting client replays from its last sequence.

## D7 — The recommendation engine never writes an assignment

Recommendations are computed on request and returned with their factors. An
assignment exists only after a user with the `dispatch:decide` permission
approves one, and the decision record stores the recommendation it was shown,
whether the operator followed or overrode it, and the stated reason.

Previously the intake pipeline auto-created `proposed` assignments under a
fixed system id.

## D8 — Unresolved locations stay unresolved

The resolver returned a hardcoded coordinate when nothing matched. It now
returns no candidates. An incident without an established position appears in
the queue with "Location not established" and is absent from the map.

## D9 — No silent provider fallbacks

A provider that is not configured or fails raises a typed error that is
recorded on the processing run and surfaced in system status. Rule-based
extraction still runs — it is a real deterministic algorithm — but its output
is labelled `rules`, never attributed to a model.

## D10 — Simulation code is removed from the product

Demo route, seed scripts, scenario file, simulated-caller modules, mock
recognizer fallback and stub telephony are deleted. The synthetic benchmark in
`evaluation/` is kept as an evaluation fixture and labelled synthetic wherever
it is referenced.

## D11 — The existing database volume is left untouched

`raahat_postgres_data` holds seeded demo records. Deleting user data requires
confirmation, so the new stack uses a new compose project and volume and starts
empty. The old volume remains until the owner removes it.

## D12 — Tailscale Funnel for public access

Compared against Cloudflare Tunnel:

| | Tailscale Funnel | Cloudflare Tunnel |
|---|---|---|
| Stable hostname without owning a domain | Yes (`*.ts.net`) | No (quick tunnels are random and do not support SSE) |
| TLS | Automatic | Automatic |
| Cost | Free tier | Free with own domain |
| Installed on the host | Yes (logged out) | No |
| SSE | Supported | Supported on named tunnels only |

Funnel is chosen. A tunnel is transport, not authentication: the backend
enforces auth, CORS and rate limits regardless.

## D13 — Design direction: light-first, ink on paper, with provenance as a visual language

**Why light.** District control rooms are lit offices with ordinary monitors,
not dim rooms with video walls. Dark text on a light ground is more legible in
ambient light and on low-contrast panels, and the map — the central surface —
is a light raster. A dark shell around a light map produces the harshest
contrast exactly where the eye works. A dark theme is provided through the same
tokens for night shifts.

**Colour.** Colour is reserved for meaning. The severity ramp owns red, orange
and amber; operational health owns green. The interface chrome is neutral
slate, primary actions are ink (near-black), and one accent — a petrol blue —
marks selection, focus and links, chosen because it is the only hue family not
otherwise carrying status. Violet marks machine-derived content.

**Provenance marking.** The product's central promise is that it does not
confuse a guess with a fact, so the interface shows the difference everywhere:
machine-extracted values carry a violet "AI" or "Rules" tag and a dashed
underline until an operator confirms them; operator-confirmed values are solid
with a check; unknown values render as an explicit "Unknown", never blank and
never zero. Location candidates draw their uncertainty radius.

**Never colour alone.** Severity is text + icon + shape. Map markers differ by
shape and carry a letter.

**Typography** (revised in 0.3.1). Public Sans, a variable face designed for
clear public-service interfaces, for all UI text; JetBrains Mono for incident
references, coordinates and identifiers; variable Noto Sans Malayalam and
Devanagari for report text. All self-hosted (no third-party font requests;
fonts are never inlined, so the CSP stays strict). Tabular figures wherever
numbers align. Base size 15px, inputs 16px on touch devices.

**Colour system** (revised in 0.3.1). Tokens are defined in OKLCH with
neutrals tinted toward one petrol-teal hue, so equal lightness steps look
equal. Severity text colours were chosen against their tints for 4.5:1; axe
reports no contrast failures in light or dark. Dark mode is a separate palette
(lower chroma, lighter raised surfaces), selectable per browser
(system/light/dark) for night shifts.

**Geometry and depth.** Panels separate by surface tone and a soft tinted
shadow rather than borders; borders remain where they carry structure
(tables, inputs, dividers). Radii 4/7/12/16px by level.

**Motion.** Gated by frequency: queue navigation and shortcuts are instant;
hover and press feedback ≤150ms; dialogs, drawers and toasts 200–260ms with
ease-out curves; the sign-in screen has the only entrance animation. Under
`prefers-reduced-motion` movement is removed but colour and opacity feedback
remain.

**Layout.** The operations board has one job, working the next incident: a
situation strip (live counts that double as filters), the priority queue with
a severity rail, the map, and a sticky incident header holding the status
actions. Keyboard: `j`/`k` or arrows move through the queue, `/` searches,
`Esc` closes.

Rejected: the existing dark glassmorphism (low contrast, decorative blur,
gradients), card-grid KPI dashboards (the previous four KPI tiles summed
unverified data into headline numbers).

## D14 — Conversational phone agent, text-to-speech and device sync removed

The browser "voice call" agent, Timbre/Piper text-to-speech, local Whisper and
the offline field-app sync endpoint were removed. The call agent depended on
mock recognisers and invented fallback replies; the sync endpoint accepted
unauthenticated writes. Voice reports remain: a recording is stored, transcribed
by Gnani Prisma when configured, and playable by authorised users. Outbound
calls and SMS are not sent by RAAHAT.

## D15 — Rule-based extraction always runs; models add, never replace

Rule extraction (keywords and patterns in English, Hindi, Malayalam, Konkani)
needs no provider, so the system works with none configured. It asserts
presence only: a negated phrase leaves a fact unknown, because a mis-parsed
negation must not lower priority. Model extraction, when configured, adds
evidence only when its supporting quote is found verbatim in the report. No
confidence numbers are shown for either, because neither is calibrated.

## D16 — Location candidates, one best position by an explicit rule

Every position is a hypothesis with a source. The incident's displayed position
is: the latest operator-confirmed one; otherwise the best candidate by source
(device > operator > geocoder > landmark), then score; otherwise none. Landmark
candidates carry an *assumed* radius (150–400 m by relation word) and say so.

## D17 — Duplicate matching bounded in SQL

The original matcher loaded every open incident with its reports and evidence
for each new report (about 900 queries at 300 incidents). Candidates are now
limited in SQL to incidents sharing the phone number, within 2 km, or among the
50 most recent in 12 hours, and loaded in four queries. Intake p50 fell from
1.25 s to 0.28 s at 200 incidents. Automatic linking is disabled by default
(`DEDUP_AUTO_LINK_THRESHOLD=1.01`): every match goes to an operator.

## D18 — Server entry point with bounded shutdown

`python -m raahat.serve` is the only way the API is started (container and
development). It fixes one process, loopback binding by default, and a 5 s
graceful-shutdown limit. Without the limit, uvicorn waited indefinitely for
open event streams and the API never stopped on SIGTERM (measured: ~98 s until
killed; now 0.1 s).

## D19 — Official alerts from NDMA SACHET

SACHET publishes CAP 1.2 warnings from IMD and SDMAs per state as a public
RSS index (verified for Kerala and Goa). It is the only authoritative,
machine-readable, keyless source found (DATA_PROVIDERS.md). Alerts are
displayed for reference with full provenance and never change incidents. IMD's
own API needs IP whitelisting and CWC offers no public API; both are reached
indirectly through SACHET.

## D20 — Public intake off by default, inside the same web app

A citizen form at `/report` posts to rate-limited `/api/v1/public` endpoints
that exist only when `PUBLIC_INTAKE_ENABLED=true`. It can attach the
reporter's device position with consent; the ticket page shows only a coarse
stage, never report content or responder details.

## D21 — Accessibility choices

Severity is conveyed by text, icon and marker shape, never colour alone.
Required fields set `aria-required`; errors are linked with
`aria-describedby` and announced once. Dialogs trap focus and restore it.
New incidents are announced through a polite live region. Submit buttons stay
enabled and validate on press rather than being silently disabled. All motion
stops under `prefers-reduced-motion`.

## D22 — Jurisdiction accounts and server-side isolation

**Decision.** Sign-in is by state, district and password; one account per
national, state and district control room (LGD codes, bundled from the Local
Government Directory: 36 states and union territories, 790 districts). Every
operation carries a state and district; every authenticated route checks the
operation it touches against the caller's jurisdiction, list endpoints require
an operation for non-national accounts, and the event stream is filtered by a
subquery of visible operations.

**Why.** Reports from one state must never reach another state's staff, and
hiding things in the interface is not enforcement. Passwords are generated per
account rather than derived from the place, because a formula anyone can read
would let anyone sign in anywhere.

**Trade-off.** Shared accounts per control room mean the audit log records the
control room, not the individual. Individual accounts can be added later
under the same jurisdiction model.

## D23 — Guided voice call built on Gnani Prisma and Timbre

**Decision.** The public site runs its own short interview in the browser:
Gnani Timbre speaks fixed questions (cached), the browser records each answer
as 16 kHz WAV with simple end-of-speech detection, Gnani Prisma transcribes
with automatic language identification, and the deterministic extraction rules
decide which questions are already answered. Unrecognised languages fall back
to Hindi. Typing works at every step.

**Why.** It needs only the speech keys already provisioned, works on any phone
browser, and every answer stays in the caller's own words. No language model
is required to run the interview.

**Limits.** Extraction rules cover English, Hindi and Malayalam best; in other
languages questions are asked even when already answered. Prompt translations
need review by native speakers. Konkani has no Prisma model and is usually
identified as Hindi or Marathi.
