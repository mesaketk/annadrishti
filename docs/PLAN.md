# Build plan — 24 h MVP, then roadmap

Deadline: prototype submission **18 Oct 2026**. Deliverables: deployed URL (Cloud Run), <3 min video, public GitHub repo, deck.
Models: Fable 5.1 plans/reviews, Sonnet 5.5 executes.

## Repo layout
```
annadrishti/
  data/raw/datasets/...        # extracted bundle (gitignored)
  pipeline/                    # python, builds artifacts/
    00_boundaries.py           # simplify INDIA_DISTRICTS.geojson → web/public/districts.json (LGD key)
    01_crops.py                # APY+UPAG → district_year_crop parquet, crop groups, trend, El Niño deltas
    02_climate.py              # IMD gridded → district JJAS/annual rain, tmax anomalies 2000‑2025; ONI phases
    03_nutrition_social.py     # NFHS 15‑16/19‑21/23‑24, census pop, PDS, clim‑vuln, resilience, agcensus
    04_risk.py                 # exposure/sensitivity/capacity → risk score + drivers per scenario; hindcast
    05_gee_live.py             # NDVI anomaly, CHIRPS anomaly, WeatherNext 10‑day rain per district (optional)
    06_export.py               # artifacts/districts.json, artifacts/kpis.json, artifacts/timeseries/{lgd}.json
  api/                         # FastAPI: serves artifacts + Gemini endpoints, serves built web/
  web/                         # React + Vite + MapLibre/deck.gl
  deploy/                      # Dockerfile, cloudbuild.yaml, deploy.sh, README_GCP.md
  docs/                        # CONCEPT, PLAN, SCHEMA, pitch outline
```

## Phase A (hours 0‑6) — data to artifacts  [agents: data‑crops, data‑climate, data‑social]
Exit: `artifacts/districts.json` populated for ≥ 700 LGD districts with the SCHEMA.md fields; sanity report.

## Phase B (hours 0‑6, parallel) — app skeleton  [agents: web, api]
Exit: map renders from `districts.json` (mock until Phase A lands), KPI tiles, drawer, scenario toggle; API serves artifacts; Gemini endpoints stubbed behind `GEMINI_API_KEY`.

## Phase C (hours 6‑12) — risk model + hindcast + Gemini grounding  [agents: risk, gemini]
Exit: risk score + drivers for 3 scenarios; hindcast panel for 2015; advisory + chat produce grounded answers.

## Phase D (hours 12‑18) — GEE live layers + polish + deploy
Exit: NDVI/CHIRPS/WeatherNext layers; Cloud Run URL live; README; video script; deck outline.

## Phase E (post‑deadline roadmap)
LightGBM yield model with proper CV · C3S seasonal ensembles · FCI state stocks scraper · ICAR contingency‑plan RAG (Vertex AI Search) · BigQuery warehouse · farmer SMS/WhatsApp via Gemini · Android field app.

## Needs from Saket
1. Gemini API key (AI Studio) **or** enable Vertex AI on a GCP project.
2. Confirm team is registered for AI Builder Cup 2026 (registration closed 11 Oct) and the 18 Oct deadline.
3. GCP project id for Cloud Run deploy (ee‑chvi works for Earth Engine with your user OAuth; the service account lacks `serviceusage.serviceUsageConsumer`).
4. Public GitHub repo name/org.

## GCP access (project aibuildercup-511905)
Service account `builder-cup-bigquery-manager@...` key in project root (ignored). Roles granted/needed: serviceusage.serviceUsageConsumer, bigquery.admin, storage.admin, earthengine.writer, aiplatform.user, run.admin, cloudbuild.builds.editor, artifactregistry.admin, secretmanager.admin, iam.serviceAccountUser, cloudscheduler.admin, logging.viewer. APIs must be enabled in console once.
