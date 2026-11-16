# Network connectivity

```
Browser ──HTTPS──> Vercel (static files only)
Browser ──HTTPS──> https://<machine>.<tailnet>.ts.net  (Tailscale Funnel)
                        │  TLS terminated by tailscaled on the laptop
                        ▼
                   127.0.0.1:8000  raahat api container
                        │  internal Docker network
                        ▼
                   db (no host port)      worker
```

## Why Tailscale Funnel

Compared with Cloudflare Tunnel (DECISIONS.md D12): Funnel gives a stable
`*.ts.net` HTTPS name without owning a domain, is already installed on this
laptop (version 1.104.7), supports long-lived SSE connections, and costs
nothing on the free plan. Cloudflare's free quick tunnels have random
hostnames and do not support SSE; a named tunnel requires a domain on
Cloudflare.

## Setting it up

```bash
sudo tailscale up                 # once: log in (opens a browser)
# In the Tailscale admin console: enable HTTPS certificates and allow Funnel
# for this device (Access controls -> "funnel" node attribute).
./scripts/tunnel-up.sh            # publishes 127.0.0.1:$API_PORT on :443
./scripts/health-check.sh https://<machine>.<tailnet>.ts.net
```

Stop publishing with `./scripts/tunnel-up.sh --off`. Funnel configuration
persists across reboots while tailscaled runs.

**Status:** Tailscale is installed but **logged out** on this laptop, so the
Funnel has not been started or tested. Starting it exposes the API to the
internet, which needs the owner's decision and login.

## What protects the API

The tunnel only carries traffic. Protection is in the API:

| Control | Setting |
|---|---|
| Authentication | Bearer access tokens (30 min, refreshed while active; 12 h maximum session). Every route except health, sign-in and optional public intake requires one. |
| Authorization | Role permissions checked per route on the server. |
| CORS | Exact origins from `CORS_ALLOWED_ORIGINS`; `*` is rejected at startup. No cookies are used. |
| Rate limits | Sign-in 10/min per address; 600 requests/min per user; public intake 10/min per address. Repeated failed sign-ins lock the account for 15 minutes. |
| Client address | With `TRUST_FORWARDED_HEADERS=true`, `X-Forwarded-For` is honoured only from a loopback peer (the local tunnel agent). |
| Request size | 1 MB JSON bodies; 15 MB voice uploads. |
| Errors | Uniform JSON with a request id; no stack traces. API docs disabled in production. |
| Event stream | Same bearer token as every request; origin restricted by CORS. |

Exposure check on this laptop: the new stack publishes only
`127.0.0.1:8000` (verified with `ss -ltn`). PostgreSQL has no published
port. The old stack still publishes 8080, 3000 and 9090 on all interfaces
until it is stopped (DEPLOYMENT_LOCAL.md).

## Frontend configuration

The web app reads exactly one backend address, `VITE_API_BASE_URL`, in
`web/src/lib/config.ts`. Nothing else builds backend URLs.
