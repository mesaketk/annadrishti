# AnnaDrishti — climate‑informed food‑security early warning for India's districts

> **A season‑by‑season food‑security early‑warning system for India's 753 districts, run every year.** Before each sowing window (Rabi in October–November, Kharif in May–June) it tells every district **how exposed its food system is, who will be hurt first, how much buffer the state has, and what farmers should plant differently** — built on Google Earth Engine, BigQuery + TimesFM, WeatherNext and Gemini.
>
> **This season's situation:** a record El Niño is forming (NOAA CPC, 8 Oct 2026: Niño‑3.4 +2.1 °C). Rabi 2026‑27 is sowing now under an El Niño winter; Kharif 2027 carries a 61 % El Niño probability.

Entry for the **Google Cloud AI Builder Cup 2026 · Sustainability & Social Impact** — **Team Sangam**: Arulsrinivaasan, Nymisha Herrera Nimmagadda, Saket Kumar.

**Live demo:** https://annadrishti-801618653701.asia-south1.run.app (Cloud Run, asia-south1) · **Code:** https://github.com/mesaketk/annadrishti

## What it does
* **Three entry points**: *Farmer* (phone‑first, 9 Indian languages, voice), *District officer* (department‑specific briefing and actions), *State planner* (map + pre‑positioning table). Built on Google **Material Design 3** with Roboto Flex and Material Symbols.
* **Map of 753 districts** with a traffic‑light risk (Low · Watch · Act now) for the **selected season (Rabi 2026‑27 · Kharif 2027)** under ENSO scenarios: *Current outlook (probability‑weighted)*, *La Niña*, *Neutral*, *El Niño*, *Strong El Niño (2015‑like)*. The ENSO outlook refreshes monthly from NOAA CPC / IRI; crop, nutrition and live layers refresh on their own cadences. Gaps are filled from neighbouring districts, Census parents or Earth Engine (WorldPop, CHIRPS, MODIS) and shown as "estimated".
* **District view in plain language**: Overview (people, children, expected harvest, grain in stock, live signals) · Why (top drivers as sentences; full breakdown one tap deeper) · Trends (yield 2000‑2024 with El Niño years shaded, monsoon anomalies, NFHS‑4→5→6, Poshan Tracker monthly, PDS offtake, prices) · Actions (season‑specific quantities with lead dates and responsible departments; Gemini briefing per department).
* **History mode**: year slider 2003‑2024 — what the monsoon did, what the harvest did, what the tool would have said, and hit/miss.
* **Pre‑positioning planner**: ranked districts with quantities (grain and pulses, anganwadi targets, seed‑bank hectares, MGNREGA person‑days, insurance gaps), CSV export, Gemini state brief.
* **Gemini as the analyst**: grounded briefing per department (7 lenses), farmer advisory personalised by holding, water, crop, livestock and tenancy with a spoken version (Gemini TTS), and an "ask a question" chat with function calling over the data.

## Data (all public)
IMD 0.25° gridded daily rainfall 2000‑2025 · DES/UPAG crop area‑production‑yield 1997‑2025 · NFHS‑4/5/6 district fact sheets · Census 2011 + NCP projections to 2026 · PDS district monthly offtake · FCI/DFPD central pool stocks · ICRISAT district database · NOAA ONI + IRI ENSO plume · DST climate‑vulnerability index · Earth Engine: CHIRPS, MODIS NDVI, ERA5‑Land, **WeatherNext 2** (64‑member ensemble).

## Method in one paragraph
Per district we compute the historical rainfall response to ENSO phase (El Niño vs neutral years, IMD 0.25° gridded) and the empirical yield deviation from trend in El Niño / deficit years (analog β). A LightGBM model trained on ~13k district‑years (rainfall anomaly, dry spells, onset, heat, ONI, irrigation, crop diversity, groundwater stress, state) is validated leave‑one‑year‑out (ρ 0.31 vs 0.08 for the analog; MAE 16.1 vs 17.7 pp). The **expected yield shock is a skill‑weighted ensemble** of both. Exposure (shock, deficit probability, antecedent dryness, live NDVI, El Niño price‑spike risk), sensitivity (rainfed share, crop concentration, yield CV, smallholder share, self‑sufficiency, groundwater stress) and adaptive‑capacity deficit (NFHS stunting/wasting/anaemia, Poshan Tracker live underweight, PDS dependency, climate‑vulnerability index) are rank‑normalised and weighted 0.45 / 0.30 / 0.25. Google **TimesFM 3.0** (BigQuery `AI.FORECAST`, ONI covariate) provides a secondary 2027 monsoon view, shown but not scored because it has no district‑level skill; **TabFM** was evaluated and found CPU‑infeasible in the time available. Forecasts are **ENSO‑conditioned scenarios with uncertainty, not deterministic predictions**. Full spec: [docs/RISK_MODEL.md](docs/RISK_MODEL.md); contract: [docs/SCHEMA.md](docs/SCHEMA.md); reports: `artifacts/reports/`.

## Repository layout
```
pipeline/   00_boundaries 01_crops 02_climate 03_nutrition_social 03b_extra_sources 04b_ml_ensemble 04_risk 05_gee_live 06_export 07_bigquery
bq/         BigQuery SQL (TimesFM AI.FORECAST) + README
artifacts/  districts.json kpis.json timeseries/ actions_*.csv reports/   (pipeline outputs served by the API)
api/        FastAPI: /api/districts /api/kpis /api/timeseries/{lgd} /api/actions /api/advisory /api/chat /api/state_brief
web/        React + Vite + MapLibre + Recharts
deploy/     Dockerfile, cloudbuild.yaml, deploy.sh, README_GCP.md
docs/       CONCEPT, PLAN, SCHEMA, RISK_MODEL, PITCH
```

## Run locally
```bash
# 1. data → artifacts (needs the raw bundle in data/raw/datasets; Earth Engine step needs `earthengine authenticate`)
python3 pipeline/00_boundaries.py && python3 pipeline/01_crops.py && python3 pipeline/02_climate.py \
  && python3 pipeline/03_nutrition_social.py && python3 pipeline/05_gee_live.py && python3 pipeline/04_risk.py && python3 pipeline/06_export.py
# 2. web
cd web && npm i && npm run build && cd ..
# 3. api (serves web/dist + /api)
export GEMINI_API_KEY=...        # or MOCK_LLM=1 for canned text
uvicorn api.main:app --port 8080
```
Open http://localhost:8080.

## Deploy to Google Cloud Run
See [deploy/README_GCP.md](deploy/README_GCP.md). Short version: `GEMINI_API_KEY=... PROJECT_ID=... bash deploy/deploy.sh`.

## Google Cloud / Google AI used
Earth Engine (CHIRPS, MODIS, ERA5‑Land, WeatherNext 2) · BigQuery warehouse (17 tables) + BigQuery ML `AI.FORECAST` with TimesFM 2.5 / 3.0 · Gemini 2.5 Flash (grounded generation, function calling, personalised by farmer profile and department) · Gemini TTS · Cloud Run · Cloud Build · Artifact Registry · Secret Manager · Cloud Storage.

## Caveats (we say them in the app too)
District‑level consumption is normative (ICMR‑NIN norm × projected population), buffer stock is national (central pool), NFHS rounds are not annual, WeatherNext covers 10‑15 days (in‑season layer, not the annual outlook), hindcast skill is modest (LightGBM out‑of‑sample ρ 0.24–0.46 by year; analog in‑sample score ρ −0.1 to −0.5), and TimesFM has no district‑level skill (display only).

## License
Code: MIT. Data: respective government / open licences (see `artifacts/reports/` and `data/raw/datasets/MANIFEST.md`).
