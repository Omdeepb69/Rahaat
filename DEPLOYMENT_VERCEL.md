# Deploying the web app

The web app (`web/`) is a static single-page application. It holds no secrets
and contains no server code: every request goes to the RAAHAT API on the
laptop, through the HTTPS address in `VITE_API_BASE_URL`.

## Vercel

1. Import the repository in Vercel and set **Root Directory** to `web`.
   `web/vercel.json` sets the framework (Vite), build command, output
   directory, SPA rewrites and security headers.
2. Environment variables (Production and Preview):

   | Name | Value |
   |---|---|
   | `VITE_API_BASE_URL` | Public API address, e.g. `https://raahat-laptop.tailnet-name.ts.net` (no trailing slash) |
   | `VITE_MAP_TILE_URL` | Optional. Tile URL template. The default is the OpenStreetMap standard tile server, which is for light use only. |
   | `VITE_MAP_ATTRIBUTION` | Optional. Attribution for the tile source. |

   Everything prefixed `VITE_` is compiled into the public bundle. Never put a
   key or password in one.
3. Deploy. Then add the deployment's exact origin (e.g.
   `https://raahat-ops.vercel.app`) to `CORS_ALLOWED_ORIGINS` in the laptop's
   `.env` and restart the API (`docker compose up -d api`). Preview
   deployments have their own origins; add them only if you need them to work.

The build fails if `VITE_API_BASE_URL` is unset, is not a URL, or uses
plain `http` for anything other than localhost, so a deployment cannot
silently point at the wrong or an unencrypted backend.

`vercel.json` also sends a Content-Security-Policy (scripts and fonts from the
site only, network requests to HTTPS origins, map tiles from HTTPS, no
framing), HSTS, `nosniff`, `no-referrer` and a restrictive
Permissions-Policy. The production build was served locally with these exact
headers (with `connect-src` widened only to reach the local test API): no
policy violations, all fonts and map tiles loaded.

## Any static host

```bash
cd web
npm ci
VITE_API_BASE_URL=https://<api-host> npm run build
# Serve web/dist with a fallback to index.html for unknown paths.
```

## Verifying a deployment

1. Open the site: the sign-in page loads. If the header shows
   "Server unreachable", the browser cannot reach `VITE_API_BASE_URL` (tunnel
   down, laptop off, or CORS: check the browser console).
2. Sign in, open *System status*: every core service should be operational.
3. Enter a report in a test operation and watch it appear on the board of a
   second signed-in browser without reloading.

## Status

The production build was tested locally with `vite preview` against the
containerised backend (full workflow passed). **Deployment to Vercel itself
was not performed**: it requires the project owner's Vercel account.
