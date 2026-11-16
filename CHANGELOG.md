# Changelog

## 0.3.1 — 2026-11-17

Frontend redesign.

- Design tokens rebuilt in OKLCH with a separately tuned dark theme and a per-browser theme switch.
- Self-hosted variable fonts: Public Sans, JetBrains Mono, Noto Sans Malayalam and Devanagari.
- Operations board: situation strip with live counts as filters, queue with severity rail, keyboard navigation (`j`/`k`, `/`, `Esc`), sticky incident header.
- Facts shown as tiles that distinguish unknown, extracted and operator-confirmed values.
- Native `<dialog>` overlays, skeleton loading states, delayed spinners, inverse toasts.
- New sign-in screen; consistent single-card layout for password change and public reporting.
- Accessibility: correct heading structure on every screen, required-field markers, forced-colours support; axe clean.
- Deployment: build refuses a missing or non-HTTPS API address; CSP and HSTS headers in `vercel.json`; fonts never inlined.
- Fixed: Leaflet layers covering the incident drawer on small screens; the logo on dark backgrounds; "Verify" offered on incidents with a committed resource.

## 0.3.0 — 2026-11-16

A redesign of the whole system. See ARCHITECTURE.md for the audit that
motivated it and DECISIONS.md for the reasons behind each change.

### Security
- All API routes require authentication; per-route role permissions.
- Real user accounts (scrypt), lockout, token revocation, forced password change for new users.
- Removed: formula-derived passwords and the endpoint publishing the formula, client-supplied dispatcher identity, hardcoded JWT secret, wildcard CORS.
- Caller details hidden from roles without permission.
- Rate limits and body-size limits; production refuses weak configuration.

### Added
- Operator web app (`web/`) replacing three frontends.
- Incident lifecycle with validated transitions, human-readable references, corrections with provenance.
- Location hypotheses with sources; landmark gazetteer import from OpenStreetMap; optional Nominatim lookups.
- Resource register, explainable recommendations, human dispatch decisions with recorded rationale.
- Hash-chained event log streamed over SSE with replay.
- Official alerts from NDMA SACHET (CAP 1.2).
- Real health checks and integration status.
- Rule-based multilingual extraction; model extraction grounded in source quotes.
- Backup, restore, health-check, start/stop and tunnel scripts.

### Changed
- Duplicate matches always require review; matching bounded in SQL (4× faster intake).
- Unresolved locations stay unresolved (previously a fixed coordinate in Pune was returned).
- Provider failures are reported instead of replaced by mock output.
- Compose stack reduced to database, API and worker with memory limits; API on loopback only.

### Removed
- Demo scenario route, seed scripts, simulation modules, mock speech, stub telephony, browser voice-call agent, text-to-speech, device sync endpoint, Prometheus, Grafana, nginx, `dashboard/`, `operator_console/`, `citizen_portal/`.

### Migrations
- `8c1d0a000001`, `8c1d0a000002`: data-preserving, reversible.
