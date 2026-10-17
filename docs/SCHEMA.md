# Data contract — `artifacts/districts.json`

Array of objects, one per district polygon in `INDIA_DISTRICTS.geojson`, keyed by **`lgd`** (= `Dist_LGD`). Missing → `null`, never 0.

```jsonc
{
  "lgd": 486, "district": "Nandurbar", "state": "Maharashtra", "census11": "497",
  "centroid": [74.24, 21.37],
  "population_2011": 1648295, "population_2026": 1910000,
  "children_u5_est": 190000,
  "crops": {                                   // latest year with full coverage (APY 2022‑23 or UPAG)
    "year": "2022-23",
    "gross_cropped_area_ha": 512000,
    "top": [{"crop":"Jowar","share":0.22,"yield_t_ha":0.9}, ...],    // top 5 by area
    "groups": {"cereals":{"area_ha":..., "prod_t":...}, "pulses":{...}, "oilseeds":{...}, "millets":{...}, "cash":{...}},
    "foodgrain_prod_t": 310000,
    "simpson_div": 0.71, "top_crop_share": 0.22, "kharif_rabi_ratio": 2.1,
    "yield_cv10": 0.31,
    "irrigated_share": 0.14, "rainfed_share": 0.86,
    "small_marginal_share": 0.62
  },
  "food_balance": {
    "requirement_t": 341000,                   // pop_2026 × 180 kg cereal‑equivalent/yr (ICMR‑NIN)
    "edible_prod_t": 271000,                   // foodgrain × 0.875
    "self_sufficiency": 0.79,
    "pds_dependency": 0.41                     // PDS rice+wheat distributed (annual, latest) / requirement
  },
  "nutrition": {                               // NFHS, percentages
    "nfhs5": {"year":"2019-21","stunting":...,"wasting":...,"underweight":...,"child_anaemia":...,"women_anaemia":...,"women_bmi_low":...},
    "nfhs6": {"year":"2023-24", ...}           // null if missing
  },
  "climate": {
    "jjas_normal_mm": 820,
    "jjas_anomaly_pct": {"2014":-18,"2015":-27,"2023":-9, ...},   // 2000‑2025 (IMD)
    "elnino_mean_anomaly_pct": -16, "neutral_mean_anomaly_pct": 2, "lanina_mean_anomaly_pct": 9,
    "tmax_anomaly_c": {"2015":0.8, ...},
    "clim_vuln_index": 0.61,                   // IDP/DST composite 0‑1 if present
    "live": {"ndvi_anom": -0.08, "chirps_30d_anom_pct": -22, "wn_10d_rain_mm": 14, "as_of":"2026-10-17"}   // optional
  },
  "yield_sensitivity": {                       // deviation from trend, El Niño‑deficit years vs neutral
    "foodgrain_elnino_pct": -14, "n_elnino_years": 5,
    "by_group": {"cereals":-12,"pulses":-21,"oilseeds":-18,"millets":-6}
  },
  "risk": {
    "neutral":  {"score":31,"band":"low","exposure":0.2,"sensitivity":0.6,"capacity":0.4,"expected_yield_shock_pct":-2,"drivers":[{"name":"rainfed_share","contrib":0.18}, ...]},
    "elnino":   {"score":78,"band":"high", ...},
    "elnino_strong": {...}
  },
  "hindcast": {"2015": {"predicted_score":74, "actual_foodgrain_yield_dev_pct":-23}, "2014":{...}, "2023":{...}}
}
```

`artifacts/kpis.json`: `{ "as_of", "enso": {"state":"El Niño","nino34":2.1,"p_historic_ond":0.83,"source":"NOAA CPC 2026-10-08"}, "central_pool": {"date","rice_lmt","wheat_lmt","total_lmt","norm_lmt","months_of_offtake"}, "scenario_counts": {"elnino":{"high":..,"medium":..,"low":..}}, "people_in_high_risk": ..., "children_u5_in_high_risk": .. }`

`artifacts/timeseries/{lgd}.json`: `{ "yield": {"foodgrain_t_ha": {"2000":..}, "by_group": {...}}, "rain_jjas_mm": {...}, "oni_phase": {"2000":"La Niña", ...}, "nfhs": [...], "pds_monthly": [{"date","rice_t","wheat_t"}] }`

Scenario definitions: `neutral` = climatology; `elnino` = district El Niño‑year mean anomaly, weighted by CPC probabilities; `elnino_strong` = mean of 2002/2009/2015 analogs.
Risk bands: score ≥ 67 high, 34‑66 medium, < 34 low (tertiles of elnino scenario fixed as thresholds so scenarios are comparable).

## Addendum A — actions (pre‑positioning planner)
Each `risk.{scenario}` object also carries an `actions` block (computed deterministically in 04_risk.py; null where inputs missing):
```jsonc
"actions": {
  "grain_preposition_t": 41000,        // max(0, deficit_t_scn − deficit_t_neutral): extra rice/wheat/millet to pre‑position via PDS/OMSS
  "pulses_preposition_t": 3100,        // pulses_prod × |pulses shock| × 0.875
  "anganwadi_children": 91000,         // children_u5_est × stunting% (NFHS‑6 else 5) — supplementary‑nutrition top‑up target
  "women_anaemia_target": 310000,      // women 15‑49 ≈ pop_2026 × 0.26 × women_anaemia%
  "seed_bank_ha": 88000,               // 0.2 × rainfed_share × gross_cropped_area_ha, only if band ≠ low — short‑duration/millet seed
  "mgnrega_persondays": 4100000,       // agri_workers_est × 50 × rainfed_share, only if band == high (agri_workers_est = pop_2026 × agri_workers_share × 0.4 workforce)
  "pmfby_gap_farmers": 120000,         // max(0, holdings_est − pmfby_farmers) if both known
  "fodder_flag": true,                 // band high and millets/cash share > 0.3
  "lead": {"rabi_2026_27": "by 2026-11-15", "kharif_2027": "by 2027-05-15"},
  "priority_rank_state": 3, "priority_rank_national": 41
}
```
`artifacts/actions_{scenario}.csv` — flat table (state, district, lgd, score, band, the fields above) for download.
`artifacts/kpis.json` adds `actions_total` per scenario (sums of the above) and `top_states` (sum grain_preposition_t by state, top 10).

## Addendum B — API additions
- `GET /api/actions?scenario=&state=&band=&format=json|csv` → ranked rows (from actions_{scenario}.csv) and `kpis.actions_total`.
- `POST /api/state_brief` {state, scenario} → Gemini markdown: state‑level pre‑positioning plan (top districts, quantities, timeline, who does what: Food & Civil Supplies, WCD/ICDS, Agriculture, Rural Development/MGNREGA, Health).
- `POST /api/advisory/{lgd}/audio` {language, scenario} → audio/wav (or mp3) of the farmer advisory, generated with Gemini TTS (`gemini-2.5-flash-preview-tts`, `response_modalities=["AUDIO"]`, voice e.g. "Kore"; PCM 24 kHz → wrap as WAV). Cache to artifacts/_audio_cache/{lgd}_{lang}_{scenario}.wav. 503 if no key; with MOCK_LLM=1 return a 1‑second silent WAV.

## Addendum C — personalised advisories
`POST /api/advisory/{lgd}` body gains optional fields (all strings; defaults in brackets):
```jsonc
{
  "audience": "farmer" | "official",
  "language": "en|hi|mr|te|bn|ta|kn|gu|or",
  "scenario": "neutral|elnino|elnino_strong",
  // farmer profile (audience=farmer)
  "profile": {
    "holding": "marginal" | "small" | "medium_large",        // <1 ha, 1-2 ha, >2 ha  [small]
    "water":   "rainfed" | "partial" | "irrigated",          // [rainfed]
    "crop":    "<one of district top crops or 'other'>",     // main kharif/rabi crop  [district top crop]
    "livestock": true | false,                               // [false]
    "tenant":  true | false                                  // sharecropper/tenant → insurance & credit caveats [false]
  },
  // official role (audience=official)
  "department": "collector" | "food_civil_supplies" | "agriculture" | "wcd_icds" | "rural_development" | "health" | "animal_husbandry"   // [collector]
}
```
Response unchanged (`{markdown, model, grounding, cached}`); grounding gains `profile`/`department`. Cache key includes them. `/api/advisory/{lgd}/audio` accepts the same `profile` + `language`.

Department focus (prompt must tailor sections + the 5 actions to the mandate; cite the same evidence):
| department | lens | action menu |
|---|---|---|
| collector | whole picture, coordination, timeline | all, prioritised |
| food_civil_supplies | PDS allocation/offtake, pds_dependency, grain_preposition_t, OMSS, storage | advance lifting, FPS stock checks, inter-district movement, price monitoring |
| agriculture | crop mix, rainfed share, β, seed_bank_ha, PMFBY gap, contingency plan | seed banks, short-duration varieties, sowing advisories, PMFBY drive, KVK demos |
| wcd_icds | stunting/wasting/underweight, anganwadi_children, THR, growth monitoring | THR front-loading, SAM screening, hot-cooked meals, VHSND |
| rural_development | mgnrega_persondays, water conservation, migration risk | work-demand surge, farm ponds/bunds, drought-proofing, wage timeliness |
| health | child + women anaemia, low BMI, diarrhoea/heat season | IFA/deworming camps, SAM referral, heat/water advisories |
| animal_husbandry | fodder_flag, millet/cash share, livestock density if known | fodder banks, cattle camps, silage, vaccination |

Farmer profile effects: marginal + rainfed → zero-cost practices, PDS/MGNREGA linkages, intercropping; medium_large + irrigated → protective-irrigation scheduling, crop diversification, water budgeting; livestock → fodder/pasture + dual-purpose crops (jowar/bajra); tenant → PMFBY needs land record/consent, note alternatives; crop → specific substitution/variety advice for that crop (e.g. paddy→short-duration varieties or shift to millets; cotton→intercrop pulses; soybean→moong/urad in delay).

## Addendum D — extra sources (artifacts/extra_district.parquet, keyed by lgd)
- `price_volatility_idx` (0-1 rank), `price_elnino_spike_pct` (ICRISAT farm-harvest prices: mean % change in El Niño years vs trend for the district's main foodgrain), `price_series_json`
- `poshan_underweight_pct`, `poshan_stunted_pct`, `poshan_wasted_pct`, `poshan_as_of` (latest month, Poshan Tracker) — live malnutrition
- `gw_premonsoon_depth_m`, `gw_decline_10y_m_per_yr`, `gw_stress_idx` (0-1 rank) — groundwater resilience
- `coc_json`: state×crop cost of cultivation + value for the district's top crops (for farmer economics in Gemini)
Risk model: add `price_spike_risk` (weight 0.10 inside exposure, renormalise), `groundwater_stress` (0.10 inside sensitivity), prefer Poshan live underweight as an extra capacity term (0.10) when present. Drivers get labels. Export into SCHEMA blocks: `markets`, `groundwater`, `nutrition.poshan_live`, `crops.economics`.

## Addendum E — model ensemble block (per district)
```jsonc
"models": {
  "expected_shock_source": "ensemble",            // what risk.*.expected_yield_shock_pct now uses
  "by_scenario": {"elnino": {"analog": -2.8, "lgbm": -6.5, "ensemble": -4.7, "spread": 5.1}, "neutral": {...}, "elnino_strong": {...}},
  "weights": {"analog": 0.48, "lgbm": 0.52},
  "skill": {"lgbm_rho_loyo": 0.31, "analog_rho_loyo": 0.08, "lgbm_mae": 16.1, "analog_mae": 17.7, "zero_mae": 17.0},
  "timesfm": {"jjas2027_anom_pct": -7.8, "p10": -20.1, "p90": 3.2, "variant": "TimesFM 3.0 + ONI covariate", "district_skill": "none (ρ≈0 vs history); national signal only"}
}
```
`hindcast[year]` gains `predicted_shock_lgbm_oos_pct` (leave-year-out LightGBM prediction for that district-year) and `kpis.hindcast[year]` gains `rho_lgbm_oos`, `rho_analog_oos`, `gap_lgbm_oos`; existing `spearman_rho` is relabelled in UI as "in-sample analog".
`kpis.models` = the skill table + weights + TimesFM national summary.

## Addendum F — seasons & outlook (every year, every season)
The product is a standing early-warning system. Each run is stamped with an `outlook` and scores **two seasons**:
```jsonc
"kpis.outlook": {
  "as_of": "2026-10-17",
  "seasons": [
    {"id": "rabi_2026_27", "label": "Rabi 2026-27", "sowing": "2026-10-15..2026-12-15", "harvest": "2027-03..2027-04", "status": "sowing_now"},
    {"id": "kharif_2027", "label": "Kharif 2027", "sowing": "2027-06..2027-07", "harvest": "2027-10..2027-11", "status": "upcoming"}
  ],
  "enso": {"state": "El Niño", "nino34": 2.1, "source": "NOAA CPC 2026-10-08",
           "p_by_season": {"rabi_2026_27": {"elnino": 1.0, "neutral": 0.0, "lanina": 0.0}, "kharif_2027": {"elnino": 0.61, "neutral": 0.33, "lanina": 0.06}}},
  "default_scenario": {"rabi_2026_27": "elnino", "kharif_2027": "elnino"},
  "refresh": {"enso": "monthly (pipeline/08_enso_status.py)", "live_layers": "daily (05_gee_live.py)", "crops": "annual (DES/UPAG release)", "nutrition": "NFHS round / Poshan monthly"}
}
```
Scenario ids are now `season × phase`: `rabi_2026_27:{lanina,neutral,elnino,elnino_strong}` and `kharif_2027:{lanina,neutral,elnino,elnino_strong}`; plus `current` = probability-weighted mix per season. `risk` object keys use `"<season>:<phase>"`, and for backward compatibility the old keys `neutral|elnino|elnino_strong` remain as aliases of `kharif_2027:*`.

Season physics:
| season | exposure drivers | analog β target | LightGBM target |
|---|---|---|---|
| kharif | JJAS anomaly, dry spells, onset, JJAS tmax | kharif-season foodgrain yield deviation (season column in APY/UPAG) | same |
| rabi | OND anomaly (residual soil moisture), Feb–Mar tmax anomaly (terminal heat), groundwater stress, previous kharif deviation (income/seed carry-over) | rabi-season foodgrain yield deviation (wheat, gram, rabi rice, mustard, barley) | same features |

ENSO phase analogs (monsoon-year): El Niño 2002/04/06/09/15/18/23; La Niña 2000/07/10/11/20/21/22; strong El Niño 2002/09/15. La Niña for kharif = excess-rain/flood exposure where the district's La Niña anomaly is > +15 % **and** yield β in La Niña years is negative (flood-prone districts); otherwise benign.
Rabi El Niño effect = warm, dry winter: use El Niño-year OND anomaly and Feb–Mar tmax anomaly; β from rabi yields in those years.

Actions per season: rabi → timely sowing before 15 Nov, heat-tolerant/early wheat varieties, 1–2 protective irrigations at crown-root/grain-filling, groundwater budgeting, PDS wheat lifting; kharif → existing menu (seed banks, onset, millets/pulses, MGNREGA, fodder). `actions` now carries `season` and the `lead` dates per season.

`kpis` gains `by_season_scenario[season][phase]` (counts, people, children, shock) and keeps `by_scenario` as the kharif alias.
UI: top bar gets a **Season** selector (Rabi 2026-27 · Kharif 2027) and a Scenario selector with four phases + "Current outlook (ENSO-weighted)"; the ENSO chip shows phase probabilities for the selected season; copy says "early warning for the coming season" with the El Niño headline as this season's situation.

## Addendum G — imputation flags
Every numeric field that was imputed is accompanied by a sibling in `data_quality.imputed` map: `{"<dotted.path>": "<source>"}` e.g. `{"nutrition.nfhs6.stunting": "state_median", "markets.price_volatility_idx": "neighbours_knn", "population_2026": "ee_worldpop", "risk.rabi_2026_27:elnino": "neighbours_exposure"}`. `data_quality.imputed_count` = number of entries. The `risk.*.band` for a district whose exposure was imputed is still a real band, with `risk.*.imputed = true`. Districts that still cannot be estimated keep band `no_data`.

## Addendum H — history mode
`GET /api/history` → `{"years": [2003..2024], "enso": {year: {"phase": "El Niño", "oni_jja_son": 1.2, "all_india_jjas_anom_pct": -12.7, "headline": "Deficit monsoon (−12 %) under El Niño; foodgrain yields −6 % vs trend"}}}`
`GET /api/history/{year}` → `{"year": 2015, "enso": {...}, "districts": {lgd: {"rain_anom_pct": -17.2, "ond_anom_pct": ..., "yield_dev_pct": -26.6, "tool_score": 77.6, "tool_band": "high", "lgbm_oos_shock_pct": -11.9, "warned": true, "nfhs_round": "NFHS-4 (2015-16)", "stunting": 45.8}}}`
- `tool_score`/`tool_band`: the hindcast score (same formula as today, that year's actual rainfall as the scenario; structural terms as of today — stated). Available for 2003–2024 (extend 04_risk hindcast loop to all years; cheap).
- `lgbm_oos_shock_pct`: leave‑one‑year‑out LightGBM prediction (artifacts/_ml_loyo_preds.parquet).
- `warned`: tool_band in (medium, high) and yield_dev_pct ≤ −5.
- Files: `artifacts/history/index.json`, `artifacts/history/{year}.json` (≤ 150 KB each). 
UI (History mode in the header, next to Season): year slider + play; layer picks: *What happened: monsoon* · *What happened: harvest* · *What the tool would have said* · *Hit / miss* (green = warned & loss, red = missed loss, grey = no loss); ENSO phase + headline for the year; click district → Trends tab with that year highlighted. Farmer view: "In past El Niño years here…" sentence from the same data.
