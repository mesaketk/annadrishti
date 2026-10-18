# AnnaDrishti API

FastAPI service: serves the pipeline artifacts, Gemini-grounded advisories, a function-calling "ask the map" chat,
and the built frontend (`web/dist`) with SPA fallback.

## Run locally (from the project root)

```bash
pip install -r api/requirements-dev.txt
# no key needed, canned LLM responses:
MOCK_LLM=1 uvicorn api.main:app --reload --port 8080
# real Gemini (AI Studio key):
GEMINI_API_KEY=... uvicorn api.main:app --reload --port 8080
# real Gemini via Vertex AI (uses gcloud application-default credentials):
USE_VERTEX=1 GOOGLE_CLOUD_PROJECT=my-proj uvicorn api.main:app --port 8080
# tests
python3 -m pytest api/tests -q
```

Frontend dev: `cd web && pnpm dev` (port 5173; CORS is open for it).

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | status, data mode, LLM backend, plus `llm_calls_today`, `tts_calls_today`, `caps` (per-instance AI budget counters). Cheap; not an LLM route |
| GET | `/robots.txt` | `User-agent: *` / `Disallow: /api/` |
| GET | `/api/districts` | `artifacts/districts.json`, reloaded when mtime changes |
| GET | `/api/kpis` | `artifacts/kpis.json` |
| GET | `/api/timeseries/{lgd}` | 404 if missing |
| POST | `/api/advisory/{lgd}` | `{audience: official\|farmer, language: en\|hi\|mr\|te\|bn\|ta\|kn\|gu\|or, scenario: <season-scenario key>, profile?, department?}` → `{markdown, model, grounding:{lgd, district, fields_used, scenario, profile, department}, cached}`. See *Personalised advisories* below |
| POST | `/api/chat` | `{messages:[{role,content}], scenario, lgd?, role?: farmer\|officer\|planner, language?}` → `{reply, citations:[lgd], model}`; Gemini tools: `get_district`, `rank_districts`, `compare_scenarios`, `national_summary`, `farmer_advice` (max 4 tool rounds). `lgd` (404 if unknown) puts `SELECTED DISTRICT: <name> (<lgd>)` in the system prompt and is the default district; `role: farmer` = ≤120 words, plain words, no scores unless asked; `language` = reply language. Farmer questions (what to sow, variety, insurance, schemes) are in scope: answered via `farmer_advice`; with no selected/named district the model asks "Which district are you in?" instead of refusing |
| GET | `/api/actions` | `?scenario=<season-scenario key>&state=&band=low\|medium\|high&format=json\|csv`. Reads `artifacts/actions_<season>_<phase>.csv` (e.g. `actions_rabi_2026_27_elnino.csv`; legacy keys keep `actions_elnino.csv`); if absent, derives rows from `districts.json` `risk[key].actions` (alias-resolved); no data gives `rows: []`. JSON: `{scenario, n, actions_total, rows}` (ranked by score; `actions_total` from `kpis.actions_total[scenario]` when unfiltered, else summed). CSV: `Content-Disposition: attachment` |
| POST | `/api/state_brief` | `{state (required), scenario}` → **422** `{error:"state is required: ..."}` if `state` is missing/blank; Gemini markdown state pre-positioning plan grounded on the state's action rows (top 10 by score, state totals, rabi 2026-27 / kharif 2027 timeline, per-department asks). Cached like advisories. 404 if the state has no rows. Totals use the label "NREGA person-days" |
| POST | `/api/advisory/{lgd}/audio` | `{language, scenario, profile?}` (same `profile` as the advisory) → `audio/wav` narration of the cached farmer advisory for that profile (markdown stripped) via Gemini TTS (`GEMINI_TTS_MODEL`, default `gemini-2.5-flash-preview-tts`; voice `TTS_VOICE`, default `Kore`; 24 kHz 16-bit mono PCM wrapped with `wave`). Cached in `ARTIFACTS_DIR/_audio_cache/{lgd}_{lang}_{scenario}[_{profile-hash}].wav` (no `profile` keeps the legacy file name). `MOCK_LLM=1` returns 1 s of silence (never cached). 503 without credentials |
| GET | `/*` | `web/dist` static files, falls back to `index.html` |

Every `/api` response carries `X-Data-Mode: mock|real`. If `artifacts/districts.json` is missing the API falls back to
`web/public/mock/*.json`, then to 3 built-in demo districts (mock mode).

Without Gemini credentials the two LLM endpoints return `503 {"error": "GEMINI_API_KEY not set"}`.
Advisories are cached in memory and in `ARTIFACTS_DIR/_advisory_cache.json` (key: lgd, audience, language, scenario, profile-or-department variant, model;
mock responses are never persisted).

## Personalised advisories (`docs/SCHEMA.md` Addendum C)

Both fields are optional; old request bodies keep working. Bad enum values return `422`.

- `profile` (used when `audience=farmer`): `holding` = `marginal` (<1 ha) \| `small` (1-2 ha, default) \| `medium_large` (>2 ha);
  `water` = `rainfed` (default) \| `partial` \| `irrigated`; `crop` = a district top crop or `other` (default: the
  district's `crops.top[0].crop`; matched case-insensitively and canonicalised; max 40 chars, letters/digits/space/`()/&.,'-`);
  `livestock` bool (false); `tenant` bool (false).
- `department` (used when `audience=official`): `collector` (default) \| `food_civil_supplies` \| `agriculture` \|
  `wcd_icds` \| `rural_development` \| `health` \| `animal_husbandry`.
- Only the field that applies to the audience takes part in the cache key, prompt and `grounding`
  (`grounding.profile` is the resolved profile for farmers, `grounding.department` for officials; the other is `null`).
- Prompts: farmer = PROFILE block (deterministic profile rules, crop playbook, crop economics when `crops.economics`
  exists), 220-word limit, title names the farmer type. Official = DEPARTMENT block (lens, named responsible units, action
  menu with lead times); the five actions come from that menu; extra sections `What to tell the public` (all) and a
  cross-department timeline table (collector). `markets`, `groundwater`, `nutrition.poshan_live`, `crops.economics` are used
  only when present in the district JSON. Code: `api/personalize.py` (catalogue/rules) and `api/llm.py` (prompts, MOCK_LLM).
- `MOCK_LLM=1` output differs per department and per holding/water/livestock/tenant/crop (Hindi mock for `language=hi`).

```bash
# farmer: marginal, rainfed paddy grower with cattle, tenant, in Hindi
curl -s localhost:8080/api/advisory/486 -H 'content-type: application/json' -d '{
  "audience":"farmer","language":"hi","scenario":"elnino",
  "profile":{"holding":"marginal","water":"rainfed","crop":"Paddy","livestock":true,"tenant":true}}'

# official: Food & Civil Supplies lens
curl -s localhost:8080/api/advisory/486 -H 'content-type: application/json' -d '{
  "audience":"official","language":"en","scenario":"elnino","department":"food_civil_supplies"}'

# audio narration for the same farmer profile
curl -s localhost:8080/api/advisory/486/audio -H 'content-type: application/json' -o advice.wav -d '{
  "language":"hi","scenario":"elnino",
  "profile":{"holding":"marginal","water":"rainfed","crop":"Paddy","livestock":true,"tenant":true}}'
```

## Seasons and scenario keys (`docs/SCHEMA.md` Addendum F)

Every endpoint taking `scenario` (`/api/advisory`, `/audio`, `/chat`, `/state_brief`, `/api/actions`) accepts
either form; anything else is `422`:

- legacy `neutral | elnino | elnino_strong` (aliases of the default kharif season),
- `"<season>:<phase>"` matching `^(kharif|rabi)_\d{4}(_\d{2})?:(lanina|neutral|elnino|elnino_strong|current)$`,
  e.g. `kharif_2027:elnino`, `rabi_2026_27:current` (`current` = ENSO-probability-weighted mix).

Resolution (`api/seasons.py`, `resolve_risk`): exact `district.risk[key]`; else for `current` the outlook's
`default_scenario[season]` phase; else the legacy alias of the phase (`rabi_2026_27:elnino` -> `risk.elnino`); a legacy
key on season-only data -> `<default kharif season>:<key>`. The prompt then carries a `DATA CAVEAT` that the numbers come
from an alias. If none exists the advisory/audio endpoints return `404 {"error": "... no risk entry ..."}`. The advisory
`grounding` gains `resolved_scenario` and `season`; `/api/actions` and `/state_brief` return `season`.

- **Season context in prompts** (`seasons.season_block`): season label, sowing/harvest window, status (sowing now /
  upcoming) and ENSO phase probabilities from `kpis.outlook` (built-in Rabi 2026-27 / Kharif 2027 defaults when absent),
  plus the phase framing: La Niña = excess rain/flood, neutral = climatology (structural vulnerability), El Niño =
  deficit/heat; rabi framing adds residual moisture, terminal heat and groundwater. Cache keys, audio files
  (`{lgd}_{lang}_{season}_{phase}[_hash].wav`) and `Content-Disposition` names are per scenario key.
- **Farmer playbook** (`personalize.crop_playbook(crop, season_kind, phase)`): rabi wheat (sow by 15 Nov, heat-tolerant/
  early varieties, irrigation at crown-root + grain filling), gram and mustard (early sowing, moisture conservation),
  rabi rice (groundwater budgeting); kharif La Niña paddy (drainage, Swarna-Sub1, delayed sowing after floods,
  short-duration pulses on residual moisture) and a generic kharif La Niña row. Old one-argument calls are unchanged.
- **Official menus**: rabi variants for Food & Civil Supplies (wheat procurement/lifting), Agriculture (timely-sowing
  campaign, heat-tolerant wheat seed), Rural Development (irrigation works) and Animal Husbandry (fodder from rabi
  straw); other departments reuse the base menu. La Niña/neutral add a phase-adaptation note to the department block.
- **Chat tools**: `rank_districts(metric, scenario)`, `get_district(name, scenario?)` and `compare_scenarios(lgd)` take
  any key; `compare_scenarios` returns `scenarios` (flat) and `by_season` (season -> phases + El Niño-minus-neutral
  delta); `national_summary` adds `outlook` and `kpis.by_season_scenario` when present and bands for every risk key.
- `MOCK_LLM=1` output names the season (label, status, sowing window).

## Environment

| Var | Default | |
|---|---|---|
| `GEMINI_API_KEY` | - | Gemini Developer API key (takes precedence) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | any Gemini model id, e.g. a Gemini 3 id |
| `USE_VERTEX` / `GOOGLE_CLOUD_PROJECT` / `VERTEX_LOCATION` | `0` / - / `asia-south1` | Vertex AI when no API key |
| `MOCK_LLM` | `0` | `1` = canned markdown / rule-based chat, no credentials |
| `PORT` | `8080` | used by `python -m api.main` and the Docker CMD |
| `ARTIFACTS_DIR` | `<root>/artifacts` | |
| `ARTIFACTS_GCS_URI` | - | `gs://bucket/prefix`; `*.json` (incl. `timeseries/`) downloaded at startup |
| `WEB_DIST_DIR`, `WEB_MOCK_DIR` | `web/dist`, `web/public/mock` | |
| `LLM_DAILY_CAP` | `1500` | max text-LLM calls (advisory / brief / chat cache misses) per instance per UTC day; `0` blocks all |
| `TTS_DAILY_CAP` | `150` | max audio syntheses per instance per UTC day |
| `LLM_PER_MIN_CAP` | `30` | max text-LLM calls per instance per rolling minute |
| `RATE_LIMIT_BYPASS_TOKEN` | - | requests with header `X-Admin-Token: <token>` skip the per-IP limits (global caps still apply). Secret Manager secret of the same name is wired in by `deploy/` when it exists. Never logged |
| `XFF_POSITION` | `first` | which `X-Forwarded-For` entry is the client IP: `first` (default) or `last` (see caveat below) |

## Abuse protection (`api/ratelimit.py`)

In-memory and dependency-free, so **every limit is per Cloud Run instance** (up to 5 instances: worst case x5 across the
service; counters also reset when an instance restarts). Cache hits are never charged: an advisory/brief limit token and
budget unit are taken only on a cache miss, right before the Gemini call. Chat is never cached, so it always counts.

| Scope | Limit (per IP unless noted) | Applies to |
|---|---|---|
| General | 120 req/min sustained, burst 40 (token bucket) | every `/api/*` request (incl. `/api/health`) |
| LLM text | 10/min and 60/hour | cache-miss `POST /api/advisory/{lgd}`, `POST /api/state_brief`, every `POST /api/chat` |
| Audio | 3/min and 20/hour | audio-file cache miss on `POST /api/advisory/{lgd}/audio` (a missing farmer advisory also takes an LLM token) |
| Global budget (instance) | `LLM_DAILY_CAP`/day, `TTS_DAILY_CAP`/day, `LLM_PER_MIN_CAP`/min | same cache-miss points; UTC-midnight reset |
| Request body | 64 KB | all POST/PUT/PATCH (413 `payload_too_large`, also for chunked bodies) |
| Chat | <= 12 messages, <= 2,000 chars each, <= 12,000 total | `POST /api/chat` (413) |

Responses: per-IP limit -> `429 {"error":"rate_limited","retry_after_s":N}` + `Retry-After`. Budget exhausted (and no cached
copy) -> `503 {"error":"budget_reached","message":"Daily AI budget reached; cached advisories still available."}` (the per-minute
cap uses the same code with a "busy, retry shortly" message); both carry `Retry-After`.

Every response also gets `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy: geolocation=(self)` and a CSP (self; inline styles; Google Fonts css/fonts; CARTO basemap
`basemaps.cartocdn.com`/`*.basemaps.cartocdn.com`; `data:`/`blob:` images, `blob:` audio and workers). Verified against the built
frontend (map, fonts, audio blob) with zero CSP violations; if you add a new external origin to the UI, extend `CSP` in `ratelimit.py`.

IP caveat: the client IP is read from `X-Forwarded-For` (first entry by default). On Cloud Run the front end appends the
real peer, so a client can prepend fake entries to dodge per-IP limits; `XFF_POSITION=last` closes that (rightmost
entry is the one Google added) at the cost of being wrong if another proxy sits in front. The global budget caps are
the backstop either way. Stale limiter entries are pruned every 60 s and each store is capped at 50k keys.

Pre-warming: `X-Admin-Token` skips only the per-IP limits; pace calls (~2 s) to stay under `LLM_PER_MIN_CAP`.

## Feedback round 2 (chat scope, season-aware advisory)
- **`farmer_advice` chat tool**: `farmer_advice(lgd, season_scenario, holding?, water?, crop?, livestock?, tenant?, language?)`
  returns `{lgd, district, state, scenario, season, language, profile, advisory_markdown, model}` from the same cached
  builder as `POST /api/advisory/{lgd}` (audience `farmer`; same cache key, so a chat call and the advisory panel share
  entries). Defaults are filled from the chat request (`lgd`, `scenario`, `language`). A cache miss costs one extra LLM
  unit against the caller's rate limit/budget. `main.py` registers the builder with `tools.set_advisory_provider`
  (avoids a circular import). Bad enum values are ignored with a `notes` entry.
- **Season-aware farmer prompt** (reads Addendum I fields, falls back when absent): crop choices come from
  `crops.by_season[<kharif|rabi>].top` (else `crops.top`); `crops.top` in the evidence JSON is that season list
  (`crops.top_is_for_season`); default crop = the season's top crop. Economics = at most one figure-free sentence.
  The "why" is climate only (nutrition / food-balance fields are dropped from the farmer evidence). Climate wording is
  `season_outlook[season][phase].plain`, else "very likely / likely / possible" built from the ENSO phase probability
  (`seasons.plain_outlook`); no "El Niño (100 %)" phrasing.
- **Officer prompt**: `SEASON OUTLOOK` block (kharif: Jun-Sep rain, onset, heat; rabi: Oct-Dec rain, Feb-Mar heat).
  For rabi the JJAS-only `climate` fields are removed from the evidence when an outlook exists; when it is absent the
  prompt says the winter outlook is not available.
- **Cache invalidation**: `personalize.PROMPT_VERSION` (`p2`) is part of every advisory/audio variant key and the state
  brief key, so cached output from the old prompts is not reused.
- **Text**: "MGNREGA" is now "NREGA" in prompts, menus, mocks and the `/api/actions?format=csv` header
  (`nrega_persondays`); JSON keys keep `mgnrega_persondays` (the CSV reader accepts either header).
