# AnnaDrishti — Climate‑informed food‑security early warning for India's districts

*Working name: AnnaDrishti (अन्न = grain, दृष्टि = foresight). Alternative: "Harvest Horizon".*
*Theme: Sustainability & Social Impact — Google Cloud AI Builder Cup 2026.*

## One‑line pitch
A standing, season‑by‑season early‑warning system: every Rabi and every Kharif, for every district, it links the climate outlook to yields, food availability, nutrition and buffer stocks, and turns that into department‑ and farmer‑specific actions. **This season's situation:** a historic El Niño is forming right now (CPC, 8 Oct 2026: Niño‑3.4 +2.1 °C, 83 % chance of a record event by Oct–Dec).
AnnaDrishti tells every Indian district **how exposed its food system is, who will be hurt first, how much buffer the
state has, and what farmers should plant differently** — using Earth Engine, Google's WeatherNext forecasts and Gemini.

## Why this wins (mapped to judging weights)
| Criterion | Weight | What we show |
|---|---|---|
| Gen‑AI technical merit | 40 % | Gemini grounded on per‑district structured evidence (climate analogs, yield sensitivity, NFHS, ICAR contingency plans) → explainable risk narrative, farmer crop‑switch advisory in local language, "ask the map" chat with function‑calling over the data. Earth Engine + WeatherNext as live signals. |
| Problem alignment & impact | 25 % | El Niño → monsoon deficit → yield shock → price + availability shock → malnutrition in already‑vulnerable districts. 2026‑27 is the live case. Tool targets state food/agri/WCD departments + farmers. |
| Innovation | 25 % | First tool that chains climate → crop → nutrition → buffer stock → farmer action at district scale, with hindcast proof (2014/2015/2023 El Niño years) and honest probability bands. |
| UX | 10 % | One map, three questions: *Where? Why? What to do?* KPI tiles, scenario toggle, district drawer with driver waterfall, farmer mode. |

## What the user sees
1. **KPI strip**: districts at high risk, people exposed, children under‑5 in high‑risk districts, central‑pool stock vs buffer norm (months of PDS cover), ENSO state.
2. **India district map** (755 polygons, LGD codes). Layers: Food‑security risk (default) · Yield shock expected · Production vs requirement gap · Malnutrition (NFHS‑5/6 stunting, wasting, anaemia) · Rainfall anomaly (live, IMD/CHIRPS) · NDVI anomaly (live, GEE) · 10‑day rain (WeatherNext).
3. **Season + scenario selectors**: Season = *Rabi 2026‑27 (sowing now)* · *Kharif 2027 (upcoming)*; Scenario = *Current outlook (ENSO‑weighted)* · *La Niña* · *Neutral* · *El Niño* · *Strong El Niño (2015‑like)*. The same screens run next year with next year's outlook — nothing is hard‑wired to 2026.
4. **District drawer** (click): risk score 0‑100 + driver breakdown (exposure / sensitivity / adaptive‑capacity), yield history with El Niño years highlighted, crop mix, NFHS trend, PDS dependency, Gemini‑written "why this is red" + "what to do" (for officials) and a **farmer card** (crop switch, short‑duration varieties, sowing window; Hindi/Marathi/Telugu toggle).
5. **Ask the map**: Gemini chat with tools (`get_district`, `rank_districts`, `compare_scenarios`) — e.g. "Which Maharashtra districts should pre‑position pulses stock?"

## Science (kept honest)
- **Exposure**: per district, JJAS rainfall anomaly distribution conditioned on ENSO phase (IMD 0.25° gridded 2000‑2025 + ICRISAT/TerraClimate 1966‑2017 + ONI). El Niño years are historical analogs, not a deterministic forecast.
- **Yield sensitivity**: per district × crop group, yield deviation from trend in El Niño‑deficit years vs neutral years (empirical elasticity); LightGBM yield‑anomaly model on rainfall anomaly, SPI‑3, tmax anomaly, NDVI anomaly, irrigation share, trend — leave‑years‑out CV; abstain where skill is poor.
- **Food balance**: production (edible, minus 12.5 % seed/feed/waste) vs requirement (population projected to 2026 × ICMR‑NIN cereal norm) → self‑sufficiency ratio. Explicitly *availability*, not access.
- **Sensitivity / adaptive capacity**: rainfed share, crop concentration (Simpson), small/marginal holdings, yield CV, PDS dependency, NFHS stunting/wasting/underweight/anaemia, climate‑vulnerability index (IDP/DST).
- **Risk score** = exposure × sensitivity × (1 − adaptive capacity), rank‑normalised; drivers reported as contributions.
- **Buffer side**: central pool stock vs buffer norm (DFPD/FCI), months of NFSA offtake covered; district PDS allocation/offtake 2017+.
- **Hindcast**: show 2014, 2015, 2023 — predicted risk vs actual yield drop, so judges see the tool would have warned.

## Google tech used
Earth Engine (CHIRPS, ERA5‑Land, MODIS NDVI, WeatherNext Gen/Graph) · Gemini 2.5/3 (grounded generation, function calling, multilingual) · Cloud Run (API + web) · Cloud Storage (artifacts) · Cloud Build + Artifact Registry · Secret Manager · optional BigQuery + Vertex AI for the yield model.

## What we cut (and say so)
No district‑level consumption survey (NSS HCES unit data needs login) → requirement is normative. No seasonal climate model run by us → ENSO analogs + CPC probabilities (C3S seasonal is a follow‑up, cdsapi key exists). WeatherNext gives 10‑15 days, not a year — it is the *in‑season nowcast* layer, not the annual forecast.
