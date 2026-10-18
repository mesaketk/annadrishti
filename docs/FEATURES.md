# AnnaDrishti — key features & tools (Team Sangam)

**Live:** https://annadrishti-801618653701.asia-south1.run.app · **Code:** https://github.com/mesaketk/annadrishti

## What it is
A season‑by‑season food‑security early‑warning system for all 753 districts of India. Before every Rabi and Kharif it links the climate outlook → expected harvest → food availability → child nutrition → government grain buffer → **actions**, for three audiences: farmers, district officers, state planners. This season's situation: a record El Niño (NOAA CPC, Oct 2026).

## Key features
1. **Three role‑based entry points** — Farmer (phone‑first, 9 Indian languages, voice), District officer (department‑specific briefing + actions), State planner (map + pre‑positioning table).
2. **Season × scenario engine** — Rabi 2026‑27 / Kharif 2027 × La Niña / Neutral / El Niño / Strong El Niño / "Current outlook" (ENSO‑probability‑weighted). ENSO outlook auto‑refreshes monthly from NOAA CPC / IRI.
3. **District risk traffic light (Low · Watch · Act now)** with driver attribution: exposure (rain deficit risk, expected yield loss, antecedent dryness, live NDVI, price‑spike risk) × sensitivity (rainfed share, crop concentration, yield variability, smallholders, self‑sufficiency, groundwater stress) × adaptive‑capacity deficit (NFHS stunting/wasting/anaemia, Poshan Tracker live underweight, PDS dependency, climate‑vulnerability index).
4. **Yield‑shock ensemble** — ENSO‑analog β + LightGBM, validated leave‑one‑year‑out on ~13k district‑years (LightGBM ρ 0.31 vs analog 0.08); "model agreement" shown per district.
5. **Would it have warned? / History mode** — in‑app hindcast for 2009/2014/2015/2023 and a 2003‑2024 year slider: what the monsoon did, what the harvest did, what the tool would have said, hit/miss.
6. **Pre‑positioning planner** — ranked districts with quantities (grain & pulses to move, anganwadi top‑up targets, seed‑bank hectares, MGNREGA person‑days, PMFBY coverage gaps), lead dates, responsible departments, CSV export, Gemini state brief.
7. **Gemini as the analyst** — grounded on each district's evidence JSON (cites numbers, states uncertainty, never invents): department briefings (Collector, Food & Civil Supplies, Agriculture, WCD/ICDS, Rural Development, Health, Animal Husbandry) with named units and lead times; farmer advisories personalised by holding size, water source, main crop, livestock, tenancy; spoken version via Gemini TTS; "Ask a question" chat with function calling over the data.
8. **Plain‑language district view** — Overview · Why · Trends (yield 2000‑2024 with El Niño years shaded, monsoon anomalies, NFHS‑4→5→6, Poshan monthly, PDS offtake, prices) · Actions.
9. **Live satellite signals** — NDVI anomaly, 30‑day rain anomaly, soil moisture, and Google WeatherNext 2 10‑day rain per district.
10. **Complete coverage** — missing values filled from neighbouring districts, Census parents or Earth Engine (WorldPop, CHIRPS, MODIS) and flagged "estimated".
11. **Production hardening** — per‑IP rate limits, daily AI budget breaker, payload caps, CSP/security headers, Cloud Run instance cap, secrets in Secret Manager.

## Google tools used
| Tool | Use |
|---|---|
| **Gemini 3.8 Flash** (Gemini API) | grounded briefings, farmer advisories, function‑calling chat, state briefs |
| **Gemini TTS** | spoken farmer advisories in Indian languages |
| **Google Earth Engine** | CHIRPS rainfall, MODIS NDVI, ERA5‑Land soil moisture, WorldPop, **WeatherNext 2** 10‑day ensemble forecasts |
| **BigQuery + BigQuery ML `AI.FORECAST`** | 17‑table warehouse; **TimesFM 2.5 / 3.0** forecasts (rainfall with ONI covariate, Poshan trend) — shown as a secondary view |
| **TabFM** | evaluated for zero‑shot yield regression (CPU‑infeasible in time; documented) |
| **Cloud Run** (asia‑south1) | API + web, min 0 / max 5 instances |
| **Artifact Registry, Secret Manager, Cloud Storage, Cloud Build** | image, Gemini key, artifact sync, builds |
| **Material Design 3**, Roboto Flex, Material Symbols, Google Fonts (Noto Indic scripts) | UI |

## Other tech
FastAPI · React + Vite + TypeScript · MapLibre GL (CARTO basemap) · Recharts · Tailwind · LightGBM · pandas/xarray/imdlib · Docker.

## Data sources (public)
IMD 0.25° gridded rainfall & temperature 2000‑25 · DES/UPAG crop area‑production‑yield 1997‑2025 · NFHS‑4/5/6 district fact sheets · Census 2011 + NCP projections · PDS district monthly offtake · FCI/DFPD central pool stocks · ICRISAT district database (prices, inputs) · Poshan Tracker · CGWB groundwater · Cost of Cultivation · PMFBY · DST climate‑vulnerability index · NOAA ONI + CPC/IRI ENSO outlooks.
