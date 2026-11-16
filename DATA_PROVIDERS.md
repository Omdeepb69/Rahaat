# External data providers

Assessment of sources for Kerala and Goa operations, carried out 2026-11-16.
"Verified" means a request was made from this deployment and the response
inspected; everything else is from published documentation and is marked as
such.

## Integrated

| Provider | Data | Access | Verified | Status in RAAHAT |
|---|---|---|---|---|
| **NDMA SACHET** (Integrated Alert System, C-DOT) | Official CAP 1.2 warnings issued by IMD, CWC, SDMAs | Public RSS index per state, linking to CAP XML. No key. Feed marked "public domain". | Yes. `rss_kerala.xml` (10 items), `rss_goa.xml` (HTTP 200), `rss_india.xml` (98 items). Kerala messages parsed: sender, severity, urgency, certainty, effective/expiry, area, English and Malayalam headlines. | Imported every 5 minutes when `CAP_ALERT_FEED_URL` is set. Shown on *Official alerts* with issuer, issue and expiry time and fetch time. Reference only: alerts never create incidents. Polygon geometry is linked in the message but not imported. |
| **OpenStreetMap via Overpass API** | Named landmarks: places of worship, schools, hospitals, bridges, stations, bus stands, localities | Public; fair-use limits; the main server returned HTTP 502 "at capacity" on first attempt and succeeded on retry. ODbL. | Yes. 418 features (457 names incl. Malayalam/Hindi names) for 10.07–10.15 N, 76.31–76.39 E (Aluva). | `python -m raahat.cli import-landmarks --bbox S,W,N,E` (≤1 square degree per call). Stored with OSM id, tags and licence. |
| **Nominatim** (OSM geocoder) | Place search | Public instance: 1 request/second, identified client, no bulk use. Self-hosting possible. | Adapter tested with recorded responses; live public instance **not** called. | Optional (`GEOCODER_PROVIDER=nominatim`). Called only when an operator requests a lookup; results become candidates. |
| **OSRM** | Road distance and duration | Needs a server. The public demo server is not for operational use. | Adapter tested with recorded responses only. | Optional. Without it, distances are labelled straight-line. Knows nothing about flooded or closed roads. |
| **Gnani Prisma** (api.vachana.ai) | Speech-to-text, Indian languages | API key (`X-API-Key-ID`) | Yes, with the key in this project's `.env`: two synthetic espeak clips returned transcripts in ~1.3 s with detected language (en-IN, hi-IN). Accuracy on real calls not measured. | Worker transcribes uploaded voice reports. No confidence value is returned by the provider, so none is shown. |
| **Gemini** | Translation and extraction | API key | **Failed**: the key in `.env` is rejected (HTTP 401) by both the Gemini API and Vertex AI. | Blocked on a valid key. |
| **Gnani Evon** | Translation and extraction | OpenAI-compatible endpoint (self-hosted or gateway) | No endpoint configured. | Blocked on an endpoint. A 30B model cannot run on the 8 GB host. |

## Assessed, not integrated

| Provider | Data | Findings | Recommendation |
|---|---|---|---|
| **IMD API** (api.imd.gov.in, mausam.imd.gov.in) | Observations, district-wise warnings, nowcasts | Documented API set including district warnings; access requires registering a **single public IP for whitelisting** with IMD and approval by their nodal officer. A laptop on a residential connection usually has no stable public IP. | Pursue through the State EOC, which may already be whitelisted. Most IMD district warnings already reach SACHET as CAP messages, which RAAHAT imports. |
| **CWC flood forecasting** (ffs.india-water.gov.in, aff.india-water.gov.in) | River level forecasts and observations | No public API documentation found. CWC material refers to API-based sharing arranged through state nodal officers. The forecast site was reported inaccessible for over a week at the start of the 2026 monsoon (SANDRP). | Request access through KSDMA/GSDMA. Do not scrape. CWC flood warnings also reach SACHET. |
| **Kerala SDMA** (sdma.kerala.gov.in) | Orders, alerts, camp information | Publishes via website and SACHET; no documented API found. | Covered via SACHET. |
| **Open-Meteo** | Model rainfall forecasts | Free, no key, non-commercial terms. Model output, not observations or official warnings. | Not integrated. If added, it must be labelled as model forecast and never shown as an official warning. |
| **Road closures** | Closures and damaged roads | No authoritative machine-readable source found for Kerala or Goa. PWD and police notices are published as text. | Operators record closures as incident hazards; routing remains labelled as unaware of closures. |
| **Bhuvan (ISRO)** | Flood inundation layers, boundaries | Map services exist; terms of use and API access need a request. | Assess for post-event inundation maps. |

## Rules applied

- An alert is labelled *official* only when it comes from `sachet.ndma.gov.in`;
  any other CAP feed is labelled *source not verified as official*.
- Every external record stores provider, external id, issue time, fetch time
  and the original link.
- Provider failures are recorded in system status; nothing is substituted.
