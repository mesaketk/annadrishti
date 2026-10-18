# 04_risk report

Scored districts: **753 / 753** (719 on observed climate + crop data, 34 on imputed data, see the v5 section; unscored -> `band = no_data`, score null: 0). Observed-data screening (pre-v5): no climate: 4; no crops: 24; all-urban / negligible foodgrain area (rural share < 5 % or < 100 ha foodgrain): 7.

## Parameters

- El Nino years used (7): [2002, 2004, 2006, 2009, 2015, 2018, 2023]; neutral (12): [2001, 2003, 2005, 2008, 2012, 2013, 2014, 2016, 2017, 2019, 2024, 2025]; strong analogs: [2002, 2009, 2015].
- v4 scenarios (`<season>:<phase>`): phases are PURE (El Nino weight 1; the v3 `elnino` weighted the analog by p(El Nino) = 0.61); `current` = probability-weighted mix of the lanina / neutral / elnino phase shocks, p kharif kharif_2027 = El Nino 0.61 / neutral 0.33 / La Nina 0.06; p rabi rabi_2026_27 = 1.00 / 0.00 / 0.00 (IRI plume via 08_enso_status.py); the 45 OND-main districts use the rabi-season probabilities for their kharif `current` mix (their NE monsoon is this winter), as v3 did.
- Main rainy season: OND for Tamil Nadu + Puducherry and lgd [503, 515, 517] (Nellore, Chittoor, Prakasam); JJAS elsewhere. OND anomalies are clipped to +/-100 %.
- Beta (yield sensitivity). Spec beta = `foodgrain_elnino_pct`; **used as the mean of the El Nino-year effect and the rain-deficit-year effect (`foodgrain_deficit_year_pct`)** (see 'Investigation log'). Each clipped to (-40.0, 15.0); districts with n < 3 or null take the state median (>= 3 donors) else the national median (-5.63 %). Sources among scored districts: {'district': 652, 'state_median': 66, 'national_median': 1}.
- Shock = clip(beta x f x (0.4 + 0.6 x rainfed_share), -45, +10) with f = max(clip((a_scn - a_neutral) / min(a_elnino - a_neutral, -5), 0, 2), floor x w_el): the share of the district's historical El Nino rainfall departure that the scenario realises (w_el = El Nino weight of the scenario: 0 neutral, 1 for the El Nino phases; floor = 0.5 for JJAS districts, 0 for OND districts). This replaces the spec's `anomaly_scn / anomaly_elnino_hist`, which explodes or flips sign when the historical El Nino anomaly is near zero or wetter than neutral. NE-monsoon districts (OND): El Nino enhances rain -> f = 0 -> no shock -> low exposure, as intended. Neutral shock is 0 by construction. Only losses (shock < 0) raise exposure.
- Percentile normalisation: every scenario's exposure terms are normalised against the **elnino** scenario's distribution (not re-ranked per scenario), so neutral/strong scores genuinely move relative to the fixed band thresholds. S and C terms are rank-normalised over scored districts; missing terms are reweighted per district.
- Bands from tertiles of elnino scores: low < **45.0**, medium 45.0-55.0, high >= **55.0**, applied to all scenarios.
- **v3 override**: the analog shock above is computed, then replaced per district/scenario by the ML ensemble shock (`shock_ensemble_pct`, artifacts/ml_ensemble.parquet) where present; tables below from 'Expected foodgrain yield shock' onward use the ensemble. See the 'v3 - ensemble' section at the end.
- Live NDVI term **used**.

## Score distribution by scenario

| scenario | mean | sd | min | p10 | p25 | median | p75 | p90 | max | high | medium | low |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| neutral | 40.6 | 7.6 | 20.2 | 31.0 | 35.4 | 40.2 | 45.8 | 50.8 | 63.5 | 26 | 176 | 517 |
| elnino | 49.7 | 10.4 | 19.9 | 36.0 | 42.5 | 49.4 | 57.7 | 63.7 | 72.8 | 240 | 239 | 240 |
| elnino_strong | 51.8 | 10.8 | 22.2 | 36.9 | 43.3 | 52.7 | 59.7 | 66.1 | 76.7 | 303 | 210 | 206 |

Expected foodgrain yield shock (%), scored districts:

| scenario | mean | median | p10 | min | share of districts with loss > 5 % |
|---|---|---|---|---|---|
| neutral | -0.2 | -0.6 | -2.3 | -5.7 | 0% |
| elnino | -5.5 | -4.8 | -12.5 | -24.5 | 49% |
| elnino_strong | -7.7 | -6.6 | -18.2 | -32.6 | 58% |

## Top 25 districts, `elnino` scenario

| # | district | state | score | shock % | season | top 3 drivers |
|---|---|---|---|---|---|---|
| 1 | Bilaspur | Chhattisgarh | 72.8 | -15.4 | JJAS | Expected foodgrain yield loss 15.4% (ensemble of analog −12.4% and LightGBM −18.1%, spread 5.7 pp); 71% chance of a >10% JJAS rainfall deficit; 96% of cropped area is under a single crop (Rice) |
| 2 | Nandurbar | Maharashtra | 72.1 | -9.4 | JJAS | Expected foodgrain yield loss 9.4% (ensemble of analog −10.7% and LightGBM −8.2%, spread 2.4 pp); 71% chance of a >10% JJAS rainfall deficit; 37% of children under 5 are stunted (NFHS-6) |
| 3 | Balangir | Odisha | 72.0 | -15.9 | JJAS | Expected foodgrain yield loss 15.9% (ensemble of analog −26.9% and LightGBM −5.9%, spread 21.0 pp); 93% of cropped area is rainfed; Last JJAS season (2025) rainfall was -19% vs normal |
| 4 | Korba | Chhattisgarh | 71.1 | -19.1 | JJAS | Expected foodgrain yield loss 19.1% (ensemble of analog −19.8% and LightGBM −18.4%, spread 1.4 pp); 71% chance of a >10% JJAS rainfall deficit; 96% of cropped area is rainfed |
| 5 | Dindori | Madhya Pradesh | 71.0 | -14.0 | JJAS | Expected foodgrain yield loss 14.0% (ensemble of analog −15.4% and LightGBM −12.6%, spread 2.7 pp); 94% of cropped area is rainfed; 57% chance of a >10% JJAS rainfall deficit |
| 6 | Kendujhar | Odisha | 71.0 | -18.1 | JJAS | Expected foodgrain yield loss 18.1% (ensemble of analog −21.7% and LightGBM −14.9%, spread 6.8 pp); 90% of cropped area is rainfed; 57% chance of a >10% JJAS rainfall deficit |
| 7 | Palamu | Jharkhand | 70.7 | -20.5 | JJAS | Expected foodgrain yield loss 20.5% (ensemble of analog −19.1% and LightGBM −21.8%, spread 2.6 pp); 71% chance of a >10% JJAS rainfall deficit; 65% of cropped area is rainfed |
| 8 | Narayanpur | Chhattisgarh | 70.5 | -18.0 | JJAS | Expected foodgrain yield loss 18.0% (ensemble of analog −19.6% and LightGBM −16.6%, spread 3.0 pp); 99% of cropped area is rainfed; 57% chance of a >10% JJAS rainfall deficit |
| 9 | Devbhumi Dwarka | Gujarat | 70.4 | -11.3 | JJAS | Expected foodgrain yield loss 11.3% (ensemble of analog −10.8% and LightGBM −11.8%, spread 1.0 pp); 71% chance of a >10% JJAS rainfall deficit; Live vegetation (NDVI) anomaly -0.20 vs normal |
| 10 | Gaurela-Pendra-Marwahi | Chhattisgarh | 70.4 | -15.6 | JJAS | Expected foodgrain yield loss 15.6% (ensemble of analog −11.7% and LightGBM −19.2%, spread 7.5 pp); 71% chance of a >10% JJAS rainfall deficit; 91% of cropped area is rainfed |
| 11 | Mandla | Madhya Pradesh | 70.3 | -14.8 | JJAS | Expected foodgrain yield loss 14.8% (ensemble of analog −18.0% and LightGBM −12.0%, spread 6.0 pp); 71% chance of a >10% JJAS rainfall deficit; 77% of cropped area is rainfed |
| 12 | Saran | Bihar | 69.6 | -12.9 | JJAS | Expected foodgrain yield loss 12.9% (ensemble of analog −8.8% and LightGBM −16.5%, spread 7.7 pp); 71% chance of a >10% JJAS rainfall deficit; Last JJAS season (2025) rainfall was -27% vs normal |
| 13 | Kandhamal | Odisha | 69.0 | -15.2 | JJAS | Expected foodgrain yield loss 15.2% (ensemble of analog −16.6% and LightGBM −13.9%, spread 2.7 pp); 91% of cropped area is rainfed; 35% of children under 5 are stunted (NFHS-6) |
| 14 | Anugul | Odisha | 68.9 | -22.7 | JJAS | Expected foodgrain yield loss 22.7% (ensemble of analog −29.7% and LightGBM −16.4%, spread 13.3 pp); 90% of cropped area is rainfed; 57% chance of a >10% JJAS rainfall deficit |
| 15 | Barmer | Rajasthan | 68.9 | -15.2 | JJAS | Expected foodgrain yield loss 15.2% (ensemble of analog −31.7% and LightGBM −0.2%, spread 31.6 pp); 57% chance of a >10% JJAS rainfall deficit; 67% of cropped area is rainfed |
| 16 | Gumla | Jharkhand | 68.5 | -23.7 | JJAS | Expected foodgrain yield loss 23.7% (ensemble of analog −29.3% and LightGBM −18.7%, spread 10.6 pp); 92% of cropped area is rainfed; 42% of children under 5 are stunted (NFHS-6) |
| 17 | Giridih | Jharkhand | 68.5 | -12.4 | JJAS | Expected foodgrain yield loss 12.4% (ensemble of analog −9.3% and LightGBM −15.3%, spread 5.9 pp); 72% of cropped area is rainfed; 34% of children under 5 are stunted (NFHS-6) |
| 18 | Chitrakoot | Uttar Pradesh | 68.4 | -9.8 | JJAS | Expected foodgrain yield loss 9.8% (ensemble of analog −8.7% and LightGBM −10.9%, spread 2.2 pp); 86% chance of a >10% JJAS rainfall deficit; 37% of children under 5 are stunted (NFHS-6) |
| 19 | Sheohar | Bihar | 68.4 | -10.8 | JJAS | Expected foodgrain yield loss 10.8% (ensemble of analog −7.3% and LightGBM −14.0%, spread 6.8 pp); Last JJAS season (2025) rainfall was -45% vs normal; 57% chance of a >10% JJAS rainfall deficit |
| 20 | Nuapada | Odisha | 68.1 | -20.0 | JJAS | Expected foodgrain yield loss 20.0% (ensemble of analog −27.1% and LightGBM −13.6%, spread 13.5 pp); 81% of cropped area is rainfed; Last JJAS season (2025) rainfall was -22% vs normal |
| 21 | Saraikela-kharsawan | Jharkhand | 67.9 | -16.5 | JJAS | Expected foodgrain yield loss 16.5% (ensemble of analog −17.5% and LightGBM −15.5%, spread 2.0 pp); 99% of cropped area is rainfed; 57% chance of a >10% JJAS rainfall deficit |
| 22 | Simdega | Jharkhand | 67.8 | -16.0 | JJAS | Expected foodgrain yield loss 16.0% (ensemble of analog −15.3% and LightGBM −16.5%, spread 1.2 pp); 95% of cropped area is rainfed; Live vegetation (NDVI) anomaly -0.09 vs normal |
| 23 | Dumka | Jharkhand | 67.7 | -13.3 | JJAS | Expected foodgrain yield loss 13.3% (ensemble of analog −9.1% and LightGBM −17.1%, spread 7.9 pp); 89% of cropped area is rainfed; Last JJAS season (2025) rainfall was -9% vs normal |
| 24 | Arwal | Bihar | 67.6 | -10.1 | JJAS | Expected foodgrain yield loss 10.1% (ensemble of analog −5.9% and LightGBM −13.9%, spread 8.1 pp); 71% chance of a >10% JJAS rainfall deficit; 40% of children under 5 are stunted (NFHS-6) |
| 25 | Raigarh | Chhattisgarh | 67.6 | -14.4 | JJAS | Expected foodgrain yield loss 14.4% (ensemble of analog −14.9% and LightGBM −13.9%, spread 1.0 pp); 87% of cropped area is rainfed; 57% chance of a >10% JJAS rainfall deficit |

State mean elnino score (>= 5 scored districts), top 10:

| state | districts | mean score |
|---|---|---|
| Jharkhand | 24 | 64.8 |
| Bihar | 38 | 61.5 |
| Odisha | 30 | 61.5 |
| Chhattisgarh | 28 | 61.1 |
| Maharashtra | 34 | 57.9 |
| Karnataka | 31 | 54.0 |
| Madhya Pradesh | 52 | 53.4 |
| Rajasthan | 33 | 52.6 |
| Uttar Pradesh | 75 | 52.1 |
| Assam | 33 | 51.7 |

## Hindcast (does the model's ranking line up with what actually happened?)

Method: the *actual* main-season rainfall anomaly of year Y is the 'forecast' (same shock formula; El Nino/neutral deficit probability by that year's ENSO phase; antecedent = anomaly of Y-1). Sensitivity (beta, S) and capacity (C) are today's values, so this is **not** a clean out-of-sample test (beta is fitted on all years including Y; NFHS-6 is later than Y). Actual = % deviation of foodgrain yield from a Theil-Sen linear trend fitted on the 10 years before Y (>= 6 obs), clipped +/-100 %. A good model has **negative** rho (high predicted risk -> negative deviation). `rho_dryness` is the baseline using raw dryness (-anomaly) alone.

| year | ENSO | all-India anomaly % | n | rho (score) | rho (exposure only) | rho (dryness only) | top-tercile mean dev % | bottom-tercile mean dev % | gap (top - bottom) |
|---|---|---|---|---|---|---|---|---|---|
| 2009 | El Niño | -12.7 | 574 | -0.304 | -0.337 | -0.179 | -12.7 | 3.4 | -16.1 |
| 2014 | Neutral | -11.9 | 608 | -0.069 | -0.189 | -0.398 | -3.49 | 0.45 | -3.95 |
| 2015 | El Niño | -7.2 | 614 | -0.534 | -0.509 | -0.259 | -25.96 | 1.35 | -27.32 |
| 2023 | El Niño | -4.6 | 679 | -0.272 | -0.326 | -0.067 | -11.58 | -1.07 | -10.51 |

## Regional sanity check (elnino rank out of 719; 1 = highest risk)

| region | district | rank | percentile | score | band | shock % | beta | beta src | main driver |
|---|---|---|---|---|---|---|---|---|---|
| Marathwada (Beed spelled 'Bid') | Bid | 316 | 56% | 51.7 | medium | -10.6 | -6.8 | district | Expected foodgrain yield loss 10.6% (ensemble of analog −5.4% and LightGBM −15.3%, spread 9.9 pp) |
| Marathwada (Beed spelled 'Bid') | Latur | 147 | 80% | 59.3 | high | -17.8 | -26.8 | district | Expected foodgrain yield loss 17.8% (ensemble of analog −21.2% and LightGBM −14.8%, spread 6.4 pp) |
| Marathwada (Beed spelled 'Bid') | Osmanabad | 152 | 79% | 59.1 | high | -14.5 | -20.2 | district | Expected foodgrain yield loss 14.5% (ensemble of analog −16.3% and LightGBM −12.8%, spread 3.5 pp) |
| Marathwada (Beed spelled 'Bid') | Jalna | 87 | 88% | 63.2 | high | -14.4 | -20.4 | district | Expected foodgrain yield loss 14.4% (ensemble of analog −16.3% and LightGBM −12.6%, spread 3.6 pp) |
| Vidarbha | Yavatmal | 130 | 82% | 60.1 | high | -9.5 | -7.6 | district | Expected foodgrain yield loss 9.5% (ensemble of analog −6.1% and LightGBM −12.7%, spread 6.6 pp) |
| Vidarbha | Amravati | 60 | 92% | 64.9 | high | -9.3 | -4.6 | district | Expected foodgrain yield loss 9.3% (ensemble of analog −3.8% and LightGBM −14.2%, spread 10.4 pp) |
| Vidarbha | Akola | 111 | 85% | 61.5 | high | -9.7 | -9.2 | district | Expected foodgrain yield loss 9.7% (ensemble of analog −7.6% and LightGBM −11.6%, spread 4.1 pp) |
| Bundelkhand | Jhansi | 637 | 12% | 38.6 | low | -4.5 | -3.5 | district | Expected foodgrain yield loss 4.5% (ensemble of analog −2.3% and LightGBM −6.5%, spread 4.2 pp) |
| Bundelkhand | Lalitpur | 453 | 37% | 46.0 | medium | -7.4 | -6.0 | district | Expected foodgrain yield loss 7.4% (ensemble of analog −4.0% and LightGBM −10.5%, spread 6.5 pp) |
| Bundelkhand | Chhatarpur | 245 | 66% | 54.8 | medium | -8.9 | -11.2 | district | Expected foodgrain yield loss 8.9% (ensemble of analog −8.1% and LightGBM −9.6%, spread 1.5 pp) |
| Bundelkhand | Tikamgarh | 322 | 55% | 51.4 | medium | -6.8 | -13.1 | district | Expected foodgrain yield loss 6.8% (ensemble of analog −8.7% and LightGBM −5.1%, spread 3.6 pp) |
| Rayalaseema | Anantpur | 172 | 76% | 58.2 | high | -6.4 | -6.9 | district | Expected foodgrain yield loss 6.4% (ensemble of analog −5.2% and LightGBM −7.6%, spread 2.4 pp) |
| Rayalaseema | Kurnool | 117 | 84% | 60.9 | high | -8.8 | -14.0 | district | Expected foodgrain yield loss 8.8% (ensemble of analog −12.2% and LightGBM −5.7%, spread 6.5 pp) |
| KBK Odisha | Kalahandi | 153 | 79% | 59.1 | high | -11.3 | -29.3 | district | Expected foodgrain yield loss 11.3% (ensemble of analog −9.7% and LightGBM −12.8%, spread 3.0 pp) |
| KBK Odisha | Balangir | 3 | 100% | 72.0 | high | -15.9 | -28.1 | district | Expected foodgrain yield loss 15.9% (ensemble of analog −26.9% and LightGBM −5.9%, spread 21.0 pp) |
| KBK Odisha | Koraput | 114 | 84% | 61.2 | high | -9.3 | -17.3 | district | Expected foodgrain yield loss 9.3% (ensemble of analog −6.1% and LightGBM −12.3%, spread 6.2 pp) |
| South Rajasthan | Banswara | 194 | 73% | 56.9 | high | -7.3 | -13.9 | district | Expected foodgrain yield loss 7.3% (ensemble of analog −5.2% and LightGBM −9.2%, spread 4.0 pp) |
| South Rajasthan | Dungarpur | 163 | 77% | 58.5 | high | -5.6 | -14.6 | district | Expected foodgrain yield loss 5.6% (ensemble of analog −11.4% and LightGBM −0.4%, spread 11.0 pp) |
| South Rajasthan | Udaipur | 106 | 85% | 61.7 | high | -7.8 | -5.6 | district | Expected foodgrain yield loss 7.8% (ensemble of analog −4.2% and LightGBM −11.1%, spread 6.9 pp) |

Regional mean percentile (100 % = riskiest): Marathwada (Beed spelled 'Bid'): 76%; Vidarbha: 86%; Bundelkhand: 43%; Rayalaseema: 80%; KBK Odisha: 88%; South Rajasthan: 79%

## Investigation log (data checked before any weight change; component weights 0.45/0.30/0.25 and term weights are UNCHANGED from the spec)

1. First run (spec beta = El Nino-year effect only, no floor): Beed ('Bid', lgd 470) ranked ~596/726 and Banswara/Koraput were mid-table with shock 0. Data check: Beed's El Nino-year effect is **+4.7 %** because 2006 and 2018 (ONI El Nino years that were *not* monsoon-deficit years; yields 0.83 and 0.34 t/ha) offset the real droughts, while its rain-deficit-year effect (2002, 2004, 2009, 2012, 2014, 2015, 2023) is **-18.3 %**. Latur: -31.9 / -21.6. Jhansi: +1.0 / -8.0. Koraput and Banswara have El Nino-year JJAS rainfall *wetter* than neutral in this 7-year IMD sample (+2.0 vs -1.9; +2.4 vs +0.7) so a pure rainfall-gated shock is 0 even though yields fall in El Nino years. Both are small-sample (n = 7) artefacts, not weights. **Fix = estimator change, not weight change:** beta = mean(El Nino effect, deficit-year effect), and a JJAS floor of 0.5 on the realised share of the El Nino effect.
2. Top-5 included Mumbai (rank 3), Mumbai Suburban (65), Hyderabad (99): their latest 'crop' rows are 3 ha / 100 ha / 37 ha (1997-98, 2016-17, 1999-00). Districts with rural share < 5 % or < 100 ha foodgrain are now `no_data` (reason `negligible_agriculture`).
3. Alternatives tried (regional mean percentile, 100 % = riskiest; Marathwada / Vidarbha / Bundelkhand / Rayalaseema / KBK / S.Rajasthan): spec beta, no floor 64/58/45/83/74/74; spec beta, floor 0.5 62/51/43/82/81/84; blend, no floor 80/71/48/80/75/73; **blend, floor 0.5 (chosen) 79/69/46/78/87/82**. Hindcast rho improved or held in all four years in the chosen setting (spec-only: -0.25, +0.02, -0.50, -0.17). These comparisons pre-date the live-NDVI term (gee_live.json arrived later); the final percentile line below includes it and is the one to quote.
4. Bundelkhand remains mid-table: Jhansi and Lalitpur are canal-irrigated (Jhansi irrigated share 59 %, yields rising 1.2 -> 2.2 t/ha) with small El Nino/deficit effects (+1.0 / -8.0 %); the data do not support a high exposure there. Reported as a genuine divergence from the prior, not tuned away.

## Caveats

- Shocks use historical El Nino-minus-neutral yield deviations (analogs, not causal); irrigated districts show weak signals; beta is clipped and sometimes imputed (see `beta_source`).
- 'Exposure' for OND-main districts uses NE-monsoon rainfall; El Nino typically enhances it, so they score low on exposure. Their Kharif (JJAS) risk is not modelled separately.
- Hindcast is an in-sample sanity check, not skill validation.
- pmfby_gap_farmers: cultivators_est = pop_2026 x worker_participation x cultivator share of workers (Census 2011 ratios); PMFBY farmer_count is farmer-seasons so is halved to approximate unique farmers. Indicative only.
- women_anaemia_target uses NFHS-5 (NFHS-6 district fact sheets carry no anaemia); anganwadi_children uses NFHS-6 stunting else NFHS-5.
- fodder_flag = band high and (millets + cash-crop area) / gross cropped area > 0.3.
- Actions zero (not null) when not triggered by band (seed bank: low band; NREGA: not high); null when inputs are missing.
- UPAG-sourced latest years cover major crops only; gross_cropped_area_ha (and thus seed_bank_ha) is a lower bound there. Split-parent districts have overstated population.
- Consistency check vs climate parquet (JJAS districts): max |El Nino mean anomaly diff| 0.07 pp, max |deficit prob diff| 0.143.


---

## v2 — extra sources (price spike, groundwater, Poshan live)

Inputs: `artifacts/extra_district.parquet` (ICRISAT farm-harvest prices, CGWB/state-board groundwater, Poshan Tracker). Component weights 0.45/0.30/0.25 and all earlier term definitions, the beta estimator, the JJAS floor and the live-NDVI handling are UNCHANGED. Bands are re-derived from the new elnino tertiles; hindcast is recomputed with the new terms.

### New terms

- **price_spike_risk** (exposure): rank-normalise(0.5 x clip(price_elnino_spike_pct, 0, +40)/40 + 0.5 x price_volatility_idx), needs both inputs. Effective weight 0.10 inside exposure; the existing terms (incl. live NDVI) are scaled by 0.90 (raw weight 0.1278 against raw sum 1.15). Same value in every scenario (like S and C).
- **groundwater_stress** (sensitivity): `gw_stress_idx` (0-1 rank of depth + 10-yr deepening), effective weight 0.10; other S terms scaled by 0.90.
- **poshan_underweight_live** (capacity deficit): rank-normalised `poshan_underweight_pct` (Poshan Tracker, latest month), effective weight 0.10; other C terms scaled by 0.90. Poshan reads ~18 pp lower than NFHS-6 on average (administrative, integer-rounded) but ranks correlate (Spearman 0.61); only the rank enters the score.
- Missing term -> dropped and the rest of that component reweighted (never imputed as 0). Coverage among scored districts: price_spike_risk (E) 719/719; groundwater_stress (S) 719/719; poshan_underweight_live (C) 719/719.
- **Honest note on prices.** In this data the El Nino-year farm-harvest price effect is *negative on the median* (median spike -4.3 pp, 75th percentile +0.8 pp; farm-gate prices were below their log-linear trend in El Nino years, i.e. no widespread price spike). Only positive spikes count (clip at 0), so roughly three quarters of districts get zero from the spike half and the term is driven mostly by price volatility. It is a market-instability proxy for farm-gate price shocks, not a food-price inflation forecast, and it uses the district's main foodgrain only (ICRISAT ends 2020; 511/753 districts have a price series).

### Bands and score distribution

- Thresholds (elnino tertiles): v1 low < 44.69, high >= 55.75  ->  v2 low < **45.0**, high >= **55.0**.
- Band counts (scored districts), v1 -> v2: neutral: 16/181/522 -> 26/176/517 (high/medium/low); elnino: 240/239/240 -> 240/239/240 (high/medium/low); elnino_strong: 362/175/182 -> 303/210/206 (high/medium/low).
- Spearman correlation of elnino scores v1 vs v2: **0.923** (n = 719).
- Band moves elnino, v1 -> v2 (rows v1): high: 200 high, 37 medium, 3 low; medium: 40 high, 162 medium, 37 low; low: 0 high, 40 medium, 200 low.

### Hindcast rho (score vs actual yield deviation; more negative is better), v1 -> v2

| year | rho v1 | rho v2 | rho exposure-only v1 | v2 | top-bottom tercile gap v1 | v2 |
|---|---|---|---|---|---|---|
| 2009 | -0.302 | -0.304 | -0.29 | -0.337 | -16.19 | -16.1 |
| 2014 | -0.113 | -0.069 | -0.243 | -0.189 | -6.74 | -3.95 |
| 2015 | -0.511 | -0.534 | -0.445 | -0.509 | -27.06 | -27.32 |
| 2023 | -0.288 | -0.272 | -0.326 | -0.326 | -11.38 | -10.51 |

Caveat: the new terms are contemporary snapshots (prices fitted on 1990-2020 El Nino years that include 2009/2015; groundwater mostly 2019; Poshan 2023-26), so the hindcast is even less out-of-sample than before.

### Top 25 (elnino), before vs after — 17 of 25 unchanged

| v2 # | district | state | v2 score | v1 rank | v1 score | new-term contribution (pts) |
|---|---|---|---|---|---|---|
| 1 | Bilaspur | Chhattisgarh | 72.8 | 12 | 70.0 | 6.3 |
| 2 | Nandurbar | Maharashtra | 72.1 | 2 | 72.7 | 9.1 |
| 3 | Balangir | Odisha | 72.0 | 1 | 74.9 | 5.0 |
| 4 | Korba | Chhattisgarh | 71.1 | 3 | 72.6 | 2.7 |
| 5 | Dindori | Madhya Pradesh | 71.0 | 37 | 66.4 | 7.6 |
| 6 | Kendujhar | Odisha | 71.0 | 6 | 71.5 | 5.7 |
| 7 | Palamu | Jharkhand | 70.7 | 32 | 66.6 | 8.4 |
| 8 | Narayanpur | Chhattisgarh | 70.5 | 14 | 69.7 | 5.1 |
| 9 | Devbhumi Dwarka | Gujarat | 70.4 | 7 | 70.9 | 7.6 |
| 10 | Gaurela-Pendra-Marwahi | Chhattisgarh | 70.4 | 15 | 69.7 | 4.8 |
| 11 | Mandla | Madhya Pradesh | 70.3 | 16 | 69.4 | 6.2 |
| 12 | Saran | Bihar | 69.6 | 19 | 68.3 | 6.0 |
| 13 | Kandhamal | Odisha | 69.0 | 10 | 70.4 | 5.5 |
| 14 | Anugul | Odisha | 68.9 | 18 | 68.6 | 5.0 |
| 15 | Barmer | Rajasthan | 68.9 | 5 | 71.5 | 8.2 |
| 16 | Gumla | Jharkhand | 68.5 | 48 | 65.6 | 8.8 |
| 17 | Giridih | Jharkhand | 68.5 | 28 | 66.8 | 8.4 |
| 18 | Chitrakoot | Uttar Pradesh | 68.4 | 51 | 65.5 | 8.6 |
| 19 | Sheohar | Bihar | 68.4 | 13 | 69.8 | 5.2 |
| 20 | Nuapada | Odisha | 68.1 | 4 | 72.0 | 4.4 |
| 21 | Saraikela-kharsawan | Jharkhand | 67.9 | 11 | 70.1 | 3.6 |
| 22 | Simdega | Jharkhand | 67.8 | 78 | 63.4 | 8.4 |
| 23 | Dumka | Jharkhand | 67.7 | 17 | 68.6 | 7.2 |
| 24 | Arwal | Bihar | 67.6 | 27 | 66.9 | 4.6 |
| 25 | Raigarh | Chhattisgarh | 67.6 | 36 | 66.4 | 4.1 |

Dropped out of the v1 top 25: Baudh (Odisha, v1 #8 -> v2 #28), Kolar (Karnataka, v1 #9 -> v2 #40), Gopalganj (Bihar, v1 #20 -> v2 #37), Sahibganj (Jharkhand, v1 #21 -> v2 #39), Bhagalpur (Bihar, v1 #22 -> v2 #89), Mayurbhanj (Odisha, v1 #23 -> v2 #31), Udalguri (Assam, v1 #24 -> v2 #44), Deogarh (Odisha, v1 #25 -> v2 #57).

Biggest rank movers (elnino, v1 -> v2):

- up: Dhaulpur (Rajasthan) #644 -> #344; Patan (Gujarat) #499 -> #254; Puducherry (Puducherry) #594 -> #369; Aravalli (Gujarat) #614 -> #417; Amravati (Maharashtra) #256 -> #60; Tonk (Rajasthan) #414 -> #221; Raigarh (Maharashtra) #534 -> #351; Alwar (Rajasthan) #487 -> #307
- down: Salem (Tamil Nadu) #199 -> #577; Namakkal (Tamil Nadu) #217 -> #561; Konaseema (Andhra Pradesh) #154 -> #479; Champawat (Uttarakhand) #254 -> #571; Kakinada (Andhra Pradesh) #179 -> #481; Jalor (Rajasthan) #91 -> #357; Morigaon (Assam) #144 -> #400; Bongaigaon (Assam) #149 -> #402

Median absolute rank change: 44; 90th percentile: 129 (of 719).

### Regional mean percentile (elnino, 100 % = riskiest), v1 -> v2

| region | v1 | v2 | mean new-term contribution (pts) | all-district mean (pts) | drivers of the move |
|---|---|---|---|---|---|
| Marathwada (Beed spelled 'Bid') | 74% | 76% | 6.6 | 4.8 | mean rank-z: price 0.84, groundwater 0.66, poshan 0.35 (0.5 = average) |
| Vidarbha | 71% | 86% | 7.4 | 4.8 | mean rank-z: price 0.81, groundwater 0.83, poshan 0.48 (0.5 = average) |
| Bundelkhand | 42% | 44% | 4.1 | 4.8 | mean rank-z: price 0.14, groundwater 0.49, poshan 0.78 (0.5 = average) |
| Rayalaseema | 83% | 80% | 6.3 | 4.8 | mean rank-z: price 0.92, groundwater 0.64, poshan 0.08 (0.5 = average) |
| KBK Odisha | 84% | 88% | 5.2 | 4.8 | mean rank-z: price 0.60, groundwater 0.29, poshan 0.67 (0.5 = average) |
| South Rajasthan | 81% | 79% | 5.2 | 4.8 | mean rank-z: price 0.35, groundwater 0.49, poshan 0.86 (0.5 = average) |

### State-level shift (elnino score, mean v2 - v1, states with >= 5 scored districts)

| state | n | mean score change | median Poshan underweight % | mean Poshan rank-z | price coverage | groundwater coverage |
|---|---|---|---|---|---|---|
| Andhra Pradesh | 26 | -5.4 | 4 | 0.17 | 100% | 100% |
| Meghalaya | 11 | -4.9 | 4 | 0.17 | 100% | 100% |
| Uttarakhand | 13 | -4.7 | 6 | 0.25 | 100% | 100% |
| Manipur | 9 | -3.7 | 2 | 0.15 | 100% | 100% |
| Punjab | 23 | -3.6 | 4 | 0.18 | 100% | 100% |
| Tripura | 8 | +1.6 | 18 | 0.82 | 100% | 100% |
| Maharashtra | 34 | +1.6 | 8 | 0.46 | 100% | 100% |
| Madhya Pradesh | 52 | +2.1 | 22 | 0.88 | 100% | 100% |
| Nagaland | 12 | +2.4 | 6 | 0.31 | 100% | 100% |
| Rajasthan | 33 | +2.7 | 14 | 0.62 | 100% | 100% |

Reading the swings: the largest negative shift is Andhra Pradesh (most new AP districts - Annamayya, Sri Sathya Sai, Palnadu, Konaseema, Bapatla, Eluru, Kakinada - drop 100-300 ranks). The cause is the Poshan term, not a change in climate or crop exposure: AP districts report very low underweight on Poshan Tracker (median 4 % vs ~10 % nationally; NFHS-6 shows ~30 %), so their rank-z on this term is near the bottom and the capacity deficit falls; the split districts also have no price or groundwater series (name match only), so nothing offsets it. This is partly a state reporting-practice effect (Poshan is administrative and integer-rounded), i.e. a bias, not necessarily better nutrition. Not tuned away; if it matters for allocation, consider a within-state rank or an NFHS-calibrated adjustment for the Poshan term in a later version. As of this run, regions in the sanity check moved by <= 6 points of percentile (Vidarbha +6, Marathwada +3, Rayalaseema +2, Bundelkhand/KBK/South Rajasthan -1 to 0); none lost its prior ordering: Bundelkhand stays mid-table because its price term is low (rank-z 0.11) and its irrigated profile is unchanged.


---

## v3 - ensemble (analog + LightGBM expected yield shock)

Inputs: `artifacts/ml_ensemble.parquet` (04b: lgd x scenario predictions of the foodgrain yield deviation, `shock_analog_pct`, `shock_lgbm_pct`, `shock_ensemble_pct`, `spread_pct`) and `artifacts/_ml_loyo_preds.parquet` (leave-one-year-out predictions for the hindcast). `expected_yield_shock_pct` of every scenario is now the **ensemble** shock (weights analog 0.48 / LightGBM 0.52, inverse pooled out-of-sample MAE; TabFM not available) for 719/719 (neutral), 719/719 (elnino), 719/719 (elnino_strong) scored districts; the rest fall back to the analog formula. The analog value is kept as `expected_yield_shock_analog_pct`. Exposure percentiles are re-referenced to the new elnino shock distribution; component weights, S and C terms, the live-NDVI term and the in-sample hindcast formula are UNCHANGED; group shocks keep the analog group/foodgrain beta ratios (ratio 1 when |beta| < 2 pp, clipped +/-3) scaled to the new foodgrain shock.

### Expected yield shock (%), scored districts (v2 analog -> v3 ensemble)

| scenario | mean v2 | mean v3 | production-weighted national v2 | v3 | median v3 | share with loss > 5 % v2 -> v3 | mean analog-LightGBM spread (pp) |
|---|---|---|---|---|---|---|---|
| neutral | 0.00 | -0.19 | 0.00 | -0.31 | -0.56 | 0% -> 0% | 3.0 |
| elnino | -4.48 | -5.53 | -4.45 | -5.88 | -4.81 | 36% -> 49% | 4.8 |
| elnino_strong | -6.45 | -7.68 | -6.36 | -7.94 | -6.58 | 42% -> 58% | 6.1 |

Note: the neutral scenario is no longer exactly zero (LightGBM carries district-level structure such as the previous-year deviation and state effects; analog neutral stays 0 by construction).

### Bands and score distribution

- Thresholds (elnino tertiles): v2 low < 44.59, high >= 55.23  ->  v3 low < **45.0**, high >= **55.0**.
- Band counts (scored districts), v2 -> v3 (high/medium/low): neutral: 17/201/501 -> 26/176/517; elnino: 240/239/240 -> 240/239/240; elnino_strong: 366/174/179 -> 303/210/206.
- Spearman correlation of elnino scores v2 vs v3: **0.940** (n = 719).
- Band moves elnino, v2 -> v3 (rows v2): high: 204 high, 35 medium, 1 low; medium: 36 high, 171 medium, 32 low; low: 0 high, 33 medium, 207 low.

### Top 25 (elnino), v2 -> v3 - 21 of 25 unchanged

| v3 # | district | state | v3 score | v2 rank | v2 score | shock v3 % (analog / LightGBM) |
|---|---|---|---|---|---|---|
| 1 | Bilaspur | Chhattisgarh | 72.8 | 10 | 69.3 | -15.4 (-12.4 / -18.1) |
| 2 | Nandurbar | Maharashtra | 72.1 | 1 | 74.5 | -9.4 (-10.7 / -8.2) |
| 3 | Balangir | Odisha | 72.0 | 3 | 72.4 | -15.9 (-26.9 / -5.9) |
| 4 | Korba | Chhattisgarh | 71.1 | 18 | 68.1 | -19.1 (-19.8 / -18.4) |
| 5 | Dindori | Madhya Pradesh | 71.0 | 25 | 67.4 | -14.0 (-15.4 / -12.6) |
| 6 | Kendujhar | Odisha | 71.0 | 8 | 69.5 | -18.1 (-21.7 / -14.9) |
| 7 | Palamu | Jharkhand | 70.7 | 17 | 68.4 | -20.5 (-19.1 / -21.8) |
| 8 | Narayanpur | Chhattisgarh | 70.5 | 6 | 70.2 | -18.0 (-19.6 / -16.6) |
| 9 | Devbhumi Dwarka | Gujarat | 70.4 | 5 | 70.5 | -11.3 (-10.8 / -11.8) |
| 10 | Gaurela-Pendra-Marwahi | Chhattisgarh | 70.4 | 7 | 69.8 | -15.6 (-11.7 / -19.2) |
| 11 | Mandla | Madhya Pradesh | 70.3 | 9 | 69.5 | -14.8 (-18.0 / -12.0) |
| 12 | Saran | Bihar | 69.6 | 24 | 67.4 | -12.9 (-8.8 / -16.5) |
| 13 | Kandhamal | Odisha | 69.0 | 4 | 70.8 | -15.2 (-16.6 / -13.9) |
| 14 | Anugul | Odisha | 68.9 | 30 | 66.4 | -22.7 (-29.7 / -16.4) |
| 15 | Barmer | Rajasthan | 68.9 | 2 | 72.5 | -15.2 (-31.7 / -0.2) |
| 16 | Gumla | Jharkhand | 68.5 | 21 | 67.9 | -23.7 (-29.3 / -18.7) |
| 17 | Giridih | Jharkhand | 68.5 | 15 | 68.5 | -12.4 (-9.3 / -15.3) |
| 18 | Chitrakoot | Uttar Pradesh | 68.4 | 22 | 67.6 | -9.8 (-8.7 / -10.9) |
| 19 | Sheohar | Bihar | 68.4 | 12 | 69.1 | -10.8 (-7.3 / -14.0) |
| 20 | Nuapada | Odisha | 68.1 | 11 | 69.2 | -20.0 (-27.1 / -13.6) |
| 21 | Saraikela-kharsawan | Jharkhand | 67.9 | 14 | 68.9 | -16.5 (-17.5 / -15.5) |
| 22 | Simdega | Jharkhand | 67.8 | 35 | 65.5 | -16.0 (-15.3 / -16.5) |
| 23 | Dumka | Jharkhand | 67.7 | 13 | 69.0 | -13.3 (-9.1 / -17.1) |
| 24 | Arwal | Bihar | 67.6 | 50 | 64.6 | -10.1 (-5.9 / -13.9) |
| 25 | Raigarh | Chhattisgarh | 67.6 | 62 | 63.9 | -14.4 (-14.9 / -13.9) |

Dropped out of the v2 top 25: Kalaburagi (Karnataka, v2 #16 -> v3 #36), Kolar (Karnataka, v2 #19 -> v3 #40), Bhagalpur (Bihar, v2 #20 -> v3 #89), Kumuram Bheem Asifabad (Telangana, v2 #23 -> v3 #72).

Biggest rank movers (elnino, v2 -> v3):

- up: Dhaulpur (Rajasthan) #619 -> #344; Sri Sathya sai (Andhra Pradesh) #367 -> #153; Aravalli (Gujarat) #628 -> #417; Puducherry (Puducherry) #559 -> #369; Bametara (Chhattisgarh) #541 -> #352; Nandyal (Andhra Pradesh) #458 -> #280; Baloda Bazar (Chhattisgarh) #292 -> #119; Rohtas (Bihar) #374 -> #201
- down: Salem (Tamil Nadu) #214 -> #577; Champawat (Uttarakhand) #253 -> #571; Alluri Sitharama Raju (Andhra Pradesh) #75 -> #393; Namakkal (Tamil Nadu) #281 -> #561; Jalor (Rajasthan) #81 -> #357; Tumakuru (Karnataka) #150 -> #419; Morigaon (Assam) #179 -> #400; Bageshwar (Uttarakhand) #421 -> #630

Median absolute rank change: 37; 90th percentile: 112 (of 719).

### Regional mean percentile (elnino, 100 % = riskiest), v2 -> v3

| region | v2 | v3 | mean shock v2 analog % | mean shock v3 ensemble % |
|---|---|---|---|---|
| Marathwada (Beed spelled 'Bid') | 77% | 76% | -14.8 | -14.3 |
| Vidarbha | 78% | 86% | -5.8 | -9.5 |
| Bundelkhand | 41% | 44% | -5.8 | -6.9 |
| Rayalaseema | 85% | 80% | -8.7 | -7.6 |
| KBK Odisha | 84% | 88% | -14.2 | -12.2 |
| South Rajasthan | 81% | 79% | -6.9 | -6.9 |

State-level shift (elnino score, mean v3 - v2, states with >= 5 scored districts): largest falls Uttarakhand -4.7; Meghalaya -4.2; Punjab -3.5; Manipur -3.1; largest rises Chhattisgarh +2.2; Nagaland +2.2; Rajasthan +2.0; Madhya Pradesh +1.4.

### Hindcast: in-sample score vs out-of-sample shock models

Two different tests share these four years. **In-sample (04_risk)**: the risk *score* built from the *actual* rainfall anomaly of year Y with betas fitted on all years incl. Y -> rho = Spearman(score, actual deviation), **negative = good**. **Out-of-sample (04b leave-one-year-out)**: models that never saw year Y predict the foodgrain yield deviation -> rho = Spearman(predicted shock, actual deviation), **positive = good**; gap = mean actual deviation of the worst-predicted tercile minus the best-predicted tercile, **negative = good**. Not a forecasting backtest (training includes future years). Pooled over all 22 held-out years: LightGBM rho 0.305 / MAE 16.07 pp, analog rho 0.077 / MAE 17.71 pp, ensemble rho 0.280 / MAE 16.31 pp, predict-0 MAE 16.96 pp.

| year | ENSO | in-sample score rho v2 | v3 | in-sample gap v2 | v3 | OOS rho analog | OOS rho LightGBM | OOS rho ensemble | OOS gap analog | OOS gap LightGBM | OOS gap ensemble |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2009 | El Niño | -0.298 | -0.304 | -15.92 | -16.1 | 0.183 | 0.281 | 0.335 | -9.7 | -16.25 | -18.4 |
| 2014 | Neutral | -0.119 | -0.069 | -7.82 | -3.95 | 0.258 | 0.461 | 0.475 | -14.76 | -25.02 | -25.1 |
| 2015 | El Niño | -0.517 | -0.534 | -27.41 | -27.32 | 0.304 | 0.334 | 0.404 | -14.26 | -12.14 | -18.27 |
| 2023 | El Niño | -0.287 | -0.272 | -10.97 | -10.51 | 0.086 | 0.239 | 0.216 | -0.53 | -11.28 | -9.77 |

### Caveats (v3)

- LightGBM beats the analog out of sample (pooled rho 0.31 vs 0.08) but its skill comes largely from `prev_year_ydev` (persistence of the deviation), state effects and ONI; the scenario predictions hold the previous-year deviation at the actual 2024 value, so the three scenarios differ only through rainfall/heat/ONI features.
- LightGBM scenario predictions are not rank-identical to the analog (Spearman 0.60 elnino); the ensemble is the compromise, weights from pooled MAE, not tuned per district. Spread = max - min of members; large spread = low confidence.
- Out-of-sample rho is a ranking skill for the *foodgrain yield deviation*; it does not validate the 0-100 risk score, which also contains sensitivity and capacity terms.
- TimesFM rainfall/Poshan forecasts are display-only and do not enter the score (no district-level skill, hindcast rho ~0).


---

## v4 — seasons (every year, every season: rabi + kharif, five scenarios each)

Outlook as of 2026-10-18: seasons **rabi_2026_27** (sowing now) and **kharif_2027**; ENSO phase probabilities (IRI plume via `08_enso_status.py`): rabi_2026_27 El Nino 1.00 / neutral 0.00 / La Nina 0.00; kharif_2027 0.61 / 0.33 / 0.06.

### What changed

- **Scenario keys** `<season>:<phase>` for phase in lanina, neutral, elnino, elnino_strong, current (10 keys). The old keys `neutral | elnino | elnino_strong` are aliases of `kharif_2027:*` (same objects in `risk_district.json` / `districts.json`).
- **Phases are pure.** v3's `elnino` weighted the analog member by p(El Nino) = 0.61 (while LightGBM was already pure El Nino); the analog is now computed for the pure phase in 04b (El Nino weight 1) and the probability weighting lives only in `current`. Consequence (measured at the v3 -> v4 switch): kharif `elnino` analog shocks are larger (mean -4.48 % vs -2.75 %) and so is the ensemble (-5.52 % vs -4.70 %); `neutral` and `elnino_strong` are numerically unchanged (LightGBM members are bit-identical). Hindcast formula unchanged (its exposure percentiles are re-referenced to the new elnino distribution, so rho moved by <= 0.011).
- **`current`** = probability-weighted mix of the lanina / neutral / elnino phase **shocks** (`p_by_season`), then scored (not a mix of scores). Rabi `current` equals rabi `elnino` while p(El Nino) = 1.00 (the very-strong event is only represented in `elnino_strong`, a stress test of the 2002/2009/2015 analogs).
- **Kharif La Nina = flood scenario** (Addendum F): shock = beta of La Nina years (foodgrain deviation, La Nina-year minus neutral-year mean, clipped, imputed) only where the district's La Nina-year main-season rain anomaly is > +15 % **and** beta < 0; otherwise benign (0). Ensemble gated the same way (04b). Flood-flagged districts: **59**. The hazard term is the share of La Nina years with > +15 % rain (`rain_excess_risk`, flood-flagged districts only, 0 elsewhere), referenced to the El Nino deficit-probability distribution so the two hazards are on one scale.
- **Rabi** (rabi_2026_27; crop year Y = rabi sown Oct Y, harvested Mar Y+1): shock from `ml_ensemble_rabi.parquet` (04b --season rabi; analog phase-beta + LightGBM, weights analog 0.47 / LightGBM 0.53). Exposure = 0.5 x expected rabi yield loss (percentile vs the rabi El Nino distribution; zero loss -> 0) + 0.3 x terminal-heat hazard (share of the phase's winters with Feb-Mar tmax anomaly >= +0.5 C; percentile vs rabi El Nino) + 0.2 x weak previous kharif (rank of -(2024 kharif deviation), the latest observed; the unobserved 2026 kharif is not available) [+ live NDVI, price term as kharif]. OND rainfall anomaly is a LightGBM feature (residual soil moisture) but not a separate exposure term: OND % anomalies are unstable where normals are tiny (e.g. Nandurbar: most years below -80 %). Groundwater stress sits in the shared sensitivity component. S and C are shared with kharif.
- **Eligibility**: rabi score only where rabi foodgrain area >= 2,000 ha in >= 3 of the years 2018-2024, median >= 2,000 ha and >= 5 % of foodgrain area: **547 of 719** scored districts; negligible_rabi_foodgrain: 158, rabi_season_label_gap: 14 are `no_data` for rabi (`rabi_season_label_gap` = Odisha, Kerala, Dadra-Nagar Haveli: the APY/UPAG season labels carry no Rabi rows in most years).
- **Bands**: the same thresholds for every season and scenario = tertiles of `kharif_2027:elnino` (low < 45.0, high >= 55.0); exposure percentiles use each season's own El Nino distribution as reference, so rabi El Nino exposure is spread like kharif El Nino exposure and the seasons are comparable as *relative* vulnerability, not as absolute tonnes lost (rabi shocks are milder: mean rabi El Nino ensemble shock -1.35 % vs kharif -5.53 %).
- **Rabi LightGBM shocks are relative to the district's own neutral-winter prediction** (04b): the raw prediction is a deviation from a lagged trailing trend (mean +5 pp; `prev_rabi_dev` is the strongest feature), so the level is not a shock; neutral = 0 by construction.

### Band counts by scenario (scored districts; thresholds fixed from kharif elnino)

| scenario | high | medium | low | no_data | mean score | mean shock % |
|---|---|---|---|---|---|---|
| kharif_2027:lanina | 3 | 99 | 651 | 0 | 36.9 | -0.07 |
| kharif_2027:neutral | 27 | 181 | 545 | 0 | 40.5 | -0.19 |
| kharif_2027:elnino | 242 | 247 | 264 | 0 | 49.3 | -5.41 |
| kharif_2027:elnino_strong | 307 | 218 | 228 | 0 | 51.4 | -7.53 |
| kharif_2027:current | 134 | 257 | 362 | 0 | 45.9 | -3.41 |
| rabi_2026_27:lanina | 82 | 237 | 416 | 18 | 43.7 | 1.36 |
| rabi_2026_27:neutral | 35 | 235 | 465 | 18 | 42.2 | 0.00 |
| rabi_2026_27:elnino | 190 | 248 | 297 | 18 | 47.5 | -1.03 |
| rabi_2026_27:elnino_strong | 378 | 212 | 145 | 18 | 54.5 | -3.09 |
| rabi_2026_27:current | 190 | 248 | 297 | 18 | 47.5 | -1.03 |

### Kharif: v3 -> v4 (old keys neutral / elnino / elnino_strong)

- Thresholds (elnino tertiles): v3 low < 45.28, high >= 55.23 -> v4 low < **45.0**, high >= **55.0**.
- Band counts (high/medium/low), v3 -> v4: neutral: 34/182/503 -> 26/176/517; elnino: 240/239/240 -> 240/239/240; elnino_strong: 359/166/194 -> 303/210/206.
- Spearman of elnino scores v3 vs v4: **0.978**; top-25 overlap 21 of 25; median |rank change| 21 of 719. (The v2 -> v3 comparison earlier in this report is computed against the frozen v2 baseline and now includes this v4 change.)

### Kharif La Nina (flood scenario): 3 high, 96 medium, 620 low

Only flood-flagged districts carry a shock; the rest score on shared S and C. Top 10:

| # | district | state | score | shock % | La Nina flood-year share | flagged |
|---|---|---|---|---|---|---|
| 1 | Yadgir | Karnataka | 62.5 | -8.9 | 0.71 | True |
| 2 | Perambalur | Tamil Nadu | 57.9 | -6.2 | 0.43 | True |
| 3 | Kalaburagi | Karnataka | 55.9 | -1.2 | 0.71 | True |
| 4 | Balangir | Odisha | 52.5 | 0.0 | 0.00 | False |
| 5 | Dibrugarh | Assam | 52.0 | 0.0 | 0.29 | False |
| 6 | Bhagalpur | Bihar | 51.2 | 0.0 | 0.29 | False |
| 7 | Pakur | Jharkhand | 50.8 | 0.0 | 0.29 | False |
| 8 | Sri Sathya sai | Andhra Pradesh | 50.7 | 0.0 | 0.71 | True |
| 9 | Dadra & Nagar Haveli | Dadra,Nagar Haveli,Daman & Diu | 50.7 | 0.0 | 0.14 | False |
| 10 | Jamui | Bihar | 50.7 | 0.0 | 0.29 | False |

### Rabi El Nino (rabi_2026_27:elnino): top 15 of 547 rabi-scored districts

| # | district | state | score | kharif elnino score | rabi shock % (analog / LightGBM) | heat-winter share | irrigated share | rabi share of foodgrain prod | top drivers |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Kalaburagi | Karnataka | 76.2 | 66.5 | -16.1 (-20.0 / -12.6) | 0.57 | 0.17 | 0.16 | Expected rabi foodgrain yield loss 16.1% (ensemble of analog −20.0% and LightGBM −12.6%, spread 7.3 pp); 57% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); Last observed kharif (2024) foodgrain yield was -54% vs trend (income and seed carry-over into rabi) |
| 2 | Giridih | Jharkhand | 76.0 | 68.5 | -8.9 (-17.7 / -1.1) | 0.43 | 0.28 | 0.31 | Expected rabi foodgrain yield loss 8.9% (ensemble of analog −17.7% and LightGBM −1.1%, spread 16.6 pp); 43% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); Last observed kharif (2024) foodgrain yield was -25% vs trend (income and seed carry-over into rabi) |
| 3 | Gumla | Jharkhand | 74.1 | 68.5 | -7.8 (-15.0 / -1.5) | 0.29 | 0.08 | 0.08 | Expected rabi foodgrain yield loss 7.8% (ensemble of analog −15.0% and LightGBM −1.5%, spread 13.5 pp); 92% of cropped area is rainfed; Last observed kharif (2024) foodgrain yield was -25% vs trend (income and seed carry-over into rabi) |
| 4 | Purbi Singhbhum | Jharkhand | 73.8 | 65.4 | -5.0 (-9.8 / -0.8) | 0.43 | 0.02 | 0.06 | Expected rabi foodgrain yield loss 5.0% (ensemble of analog −9.8% and LightGBM −0.8%, spread 9.0 pp); 43% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); 98% of cropped area is rainfed |
| 5 | Simdega | Jharkhand | 72.5 | 67.8 | -8.8 (-16.7 / -1.9) | 0.29 | 0.05 | 0.28 | Expected rabi foodgrain yield loss 8.8% (ensemble of analog −16.7% and LightGBM −1.9%, spread 14.8 pp); 95% of cropped area is rainfed; Last observed kharif (2024) foodgrain yield was -39% vs trend (income and seed carry-over into rabi) |
| 6 | Jamtara | Jharkhand | 71.9 | 61.9 | -8.6 (-18.2 / -0.0) | 0.43 | 0.11 | 0.25 | Expected rabi foodgrain yield loss 8.6% (ensemble of analog −18.2% and LightGBM 0.0%, spread 18.2 pp); 43% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); 89% of cropped area is rainfed |
| 7 | Yadgir | Karnataka | 71.5 | 64.4 | -10.7 (-9.2 / -12.0) | 0.57 | 0.48 | 0.04 | Expected rabi foodgrain yield loss 10.7% (ensemble of analog −9.2% and LightGBM −12.0%, spread 2.8 pp); 57% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); 45% of children under 5 are stunted (NFHS-6) |
| 8 | Narayanpet | Telangana | 71.0 | 63.4 | -10.1 (-16.4 / -4.5) | 0.57 | 0.54 | 0.37 | Expected rabi foodgrain yield loss 10.1% (ensemble of analog −16.4% and LightGBM −4.5%, spread 11.9 pp); 57% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); Last observed kharif (2024) foodgrain yield was -15% vs trend (income and seed carry-over into rabi) |
| 9 | Pashchimi Singhbhum | Jharkhand | 70.6 | 64.5 | -7.9 (-15.6 / -1.1) | 0.29 | 0.01 | 0.09 | Expected rabi foodgrain yield loss 7.9% (ensemble of analog −15.6% and LightGBM −1.1%, spread 14.5 pp); 99% of cropped area is rainfed; 51% of children under 5 are stunted (NFHS-6) |
| 10 | Koppal | Karnataka | 70.3 | 62.1 | -9.7 (-12.0 / -7.7) | 0.57 | 0.40 | 0.17 | Expected rabi foodgrain yield loss 9.7% (ensemble of analog −12.0% and LightGBM −7.7%, spread 4.4 pp); 57% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); Last observed kharif (2024) foodgrain yield was -21% vs trend (income and seed carry-over into rabi) |
| 11 | Raichur | Karnataka | 69.4 | 55.3 | -9.3 (-11.5 / -7.3) | 0.57 | 0.50 | 0.18 | Expected rabi foodgrain yield loss 9.3% (ensemble of analog −11.5% and LightGBM −7.3%, spread 4.2 pp); 57% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); 46% of children under 5 are stunted (NFHS-6) |
| 12 | Deoghar | Jharkhand | 69.3 | 65.9 | -1.8 (-3.3 / -0.4) | 0.43 | 0.20 | 0.35 | Expected rabi foodgrain yield loss 1.8% (ensemble of analog −3.3% and LightGBM −0.4%, spread 2.9 pp); 43% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); Last observed kharif (2024) foodgrain yield was -31% vs trend (income and seed carry-over into rabi) |
| 13 | Kurnool | Andhra Pradesh | 69.3 | 60.9 | -20.4 (-33.7 / -8.6) | 0.57 | 0.21 | 0.60 | Expected rabi foodgrain yield loss 20.4% (ensemble of analog −33.7% and LightGBM −8.6%, spread 25.1 pp); 57% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); Last observed kharif (2024) foodgrain yield was -33% vs trend (income and seed carry-over into rabi) |
| 14 | Khunti | Jharkhand | 69.1 | 63.7 | -17.0 (-34.3 / -1.8) | 0.29 | 0.10 | 0.25 | Expected rabi foodgrain yield loss 17.0% (ensemble of analog −34.3% and LightGBM −1.8%, spread 32.5 pp); 90% of cropped area is rainfed; 36% of children under 5 are stunted (NFHS-6) |
| 15 | Bidar | Karnataka | 68.9 | 66.6 | -11.0 (-11.4 / -10.6) | 0.57 | 0.11 | 0.43 | Expected rabi foodgrain yield loss 11.0% (ensemble of analog −11.4% and LightGBM −10.6%, spread 0.7 pp); 57% of comparable winters had terminal heat (Feb-Mar max temperature >= +0.5 C above normal); 89% of cropped area is rainfed |

Rabi El Nino band counts: high 136, medium 193, low 218. States (>= 8 rabi-scored districts), mean scores and components:

| state | n | high (rabi) | mean rabi score | mean kharif score | mean exposure rabi / kharif | mean S | mean C | mean rabi shock % | mean analog shock % |
|---|---|---|---|---|---|---|---|---|---|
| Jharkhand | 24 | 21 | 65.1 | 64.8 | 0.64 / 0.63 | 0.63 | 0.71 | -5.96 | -11.31 |
| Karnataka | 24 | 17 | 59.3 | 55.0 | 0.68 / 0.58 | 0.50 | 0.55 | -6.77 | -6.73 |
| Telangana | 32 | 15 | 56.5 | 51.3 | 0.66 / 0.54 | 0.45 | 0.54 | -8.57 | -15.97 |
| Tamil Nadu | 31 | 17 | 55.2 | 42.6 | 0.69 / 0.41 | 0.54 | 0.31 | -2.92 | -1.92 |
| Andhra Pradesh | 26 | 11 | 53.1 | 47.4 | 0.66 / 0.53 | 0.51 | 0.32 | -6.36 | -7.41 |
| Jammu & Kashmir | 10 | 4 | 52.0 | 41.0 | 0.55 / 0.31 | 0.63 | 0.34 | -4.95 | -10.80 |
| Madhya Pradesh | 52 | 16 | 50.4 | 53.4 | 0.51 / 0.57 | 0.39 | 0.64 | -5.39 | -11.93 |
| Maharashtra | 33 | 11 | 49.7 | 58.0 | 0.44 / 0.62 | 0.56 | 0.53 | -1.50 | -5.08 |
| Gujarat | 33 | 10 | 49.3 | 51.4 | 0.49 / 0.54 | 0.40 | 0.60 | -2.54 | -4.45 |
| Bihar | 38 | 5 | 49.1 | 61.5 | 0.35 / 0.63 | 0.50 | 0.73 | 3.89 | 2.88 |
| Chhattisgarh | 11 | 2 | 48.8 | 55.9 | 0.44 / 0.60 | 0.54 | 0.50 | -0.85 | -3.79 |
| West Bengal | 15 | 1 | 46.7 | 41.5 | 0.43 / 0.31 | 0.50 | 0.50 | 0.32 | -2.73 |
| Assam | 19 | 2 | 46.2 | 50.3 | 0.24 / 0.33 | 0.62 | 0.66 | 5.54 | 5.33 |
| Uttar Pradesh | 75 | 4 | 45.2 | 52.1 | 0.41 / 0.56 | 0.41 | 0.58 | -0.85 | -2.33 |
| Rajasthan | 32 | 0 | 39.6 | 52.1 | 0.30 / 0.58 | 0.40 | 0.55 | 2.38 | 3.02 |
| Uttarakhand | 13 | 0 | 36.2 | 38.0 | 0.34 / 0.38 | 0.51 | 0.21 | 6.09 | 6.02 |
| Himachal Pradesh | 10 | 0 | 34.4 | 34.3 | 0.28 / 0.27 | 0.57 | 0.20 | 6.63 | 7.74 |
| Manipur | 9 | 0 | 34.2 | 43.9 | 0.18 / 0.39 | 0.62 | 0.30 | 3.33 | 3.50 |
| Haryana | 22 | 0 | 30.1 | 33.9 | 0.31 / 0.39 | 0.27 | 0.33 | 2.54 | 2.50 |
| Punjab | 23 | 0 | 29.2 | 29.2 | 0.33 / 0.33 | 0.23 | 0.30 | 1.54 | 1.40 |

Evidence on terminal heat (within-district OLS: change in rabi yield deviation, pp, per +1 C of Feb-Mar tmax anomaly; 2003-2024; states with >= 8 districts):

| state | districts | district-years | pp per +1 C |
|---|---|---|---|
| Karnataka | 30 | 587 | -18.5 |
| Tripura | 8 | 78 | -16.1 |
| Andhra Pradesh | 13 | 286 | -11.5 |
| Assam | 27 | 543 | -10.0 |
| Himachal Pradesh | 12 | 247 | -4.9 |
| West Bengal | 21 | 399 | -4.0 |
| Maharashtra | 34 | 721 | -4.0 |
| Uttarakhand | 13 | 283 | -3.8 |
| Bihar | 38 | 829 | -3.4 |
| Manipur | 9 | 72 | -2.7 |
| Telangana | 32 | 263 | -2.5 |
| Madhya Pradesh | 51 | 1012 | -2.4 |
| Gujarat | 33 | 556 | -1.1 |
| Rajasthan | 33 | 715 | -0.7 |
| Arunachal Pradesh | 8 | 61 | -0.5 |
| Jammu & Kashmir | 11 | 173 | -0.4 |
| Punjab | 22 | 426 | -0.3 |
| Haryana | 22 | 445 | -0.0 |
| Jharkhand | 24 | 359 | +0.4 |
| Uttar Pradesh | 75 | 1577 | +0.9 |
| Nagaland | 11 | 169 | +1.0 |
| Chhattisgarh | 25 | 377 | +4.4 |
| Tamil Nadu | 29 | 194 | +6.0 |

**Honest reading on the wheat belt.** The expectation that heat-sensitive irrigated wheat districts (Punjab / Haryana / UP / MP) would rise sharply in the rabi ranking is **not** borne out by the data: in the district panel the Feb-Mar tmax anomaly explains rabi yield deviations mainly in Karnataka, Andhra Pradesh, Assam, Maharashtra, Bihar and West Bengal (slopes above), and is flat in Punjab / Haryana / Uttar Pradesh / Rajasthan (irrigated, administratively smooth yields; March-2022 heat is not visible in district APY numbers), and El Nino winters were not systematically hotter or lower-yielding there (analog shocks near zero or positive). Those states also have low sensitivity and capacity-deficit components (high self-sufficiency, low malnutrition), so their scores stay low: mean rabi / kharif scores Haryana 30 / 34 (0 high of 22); Madhya Pradesh 50 / 53 (16 high of 52); Punjab 29 / 29 (0 high of 23); Rajasthan 40 / 52 (0 high of 32); Uttar Pradesh 45 / 52 (4 high of 75). The rabi high-risk set is led by Jharkhand, Karnataka, Telangana, Andhra Pradesh and tribal / peninsular Madhya Pradesh and Maharashtra, where heat sensitivity, rainfed share and malnutrition coincide. Rabi exposure of Punjab and Haryana is modestly higher than their kharif exposure (they gain a heat-hazard and a weak-carryover share), but not enough to move them out of the low band. Not tuned: reporting this as the data say.

### Rabi hindcast (leave-one-year-out ensemble shock -> score; crop year Y = rabi Y-(Y+1))

Method: for crop year Y the predicted shock is the leave-one-year-out ensemble prediction (04b rabi; the model never saw Y) minus the pooled mean of the LOYO LightGBM predictions (level de-bias), the heat hazard is the *observed* Feb-Mar tmax >= +0.5 C indicator of Y+1, the carry-over term is the same-year kharif deviation, S and C are today's values. rho = Spearman(score, actual rabi deviation), **negative = good**; `rho heat only` = Spearman(Feb-Mar tmax anomaly, actual deviation) as a naive baseline; OOS columns are Spearman(predicted shock, actual), positive = good. 2021-22 is the crop year of the March-2022 heatwave (the brief's '2022-23 (heat March 2022)' refers to the harvest year; both 2021-22 and 2022-23 are shown). Not a forecasting backtest.

| crop year | ENSO | n | mean all-India Feb-Mar tmax anom C | rho (score) | rho (exposure only) | rho heat only | top-bottom tercile gap pp | OOS rho analog | OOS rho LightGBM | OOS rho ensemble |
|---|---|---|---|---|---|---|---|---|---|---|
| 2009-10 | El Niño | 361 | 1.49 | -0.096 | -0.137 | -0.03 | -3.4 | 0.039 | 0.136 | 0.129 |
| 2015-16 | El Niño | 441 | 1.14 | -0.261 | -0.255 | -0.336 | -12.0 | -0.143 | 0.388 | 0.174 |
| 2021-22 | La Niña | 487 | 0.3 | -0.166 | -0.297 | -0.238 | -10.15 | 0.106 | 0.387 | 0.361 |
| 2022-23 | La Niña | 514 | 0.23 | -0.077 | -0.133 | -0.157 | -2.91 | -0.049 | 0.241 | 0.146 |

The score has the right sign in 4 of 4 winters (rho -0.26 to -0.08) but is weaker than kharif (-0.53 to -0.07); in 2009-10 (97% of districts), 2015-16 (96% of districts) nearly every district was a 'heat winter' (Feb-Mar tmax anomaly >= +0.5 C), so the heat term does not discriminate there; the discrimination comes from the LightGBM shock and S / C.

### Caveats (v4)

- Rabi skill is modest: pooled leave-one-year-out LightGBM rho 0.32 / MAE 17.4 pp vs predict-0 MAE 18.6 pp; the analog (ENSO phase beta) has **no** out-of-sample skill (rho -0.01, MAE 19.7 pp, worse than predict-0) but carries 0.47 of the ensemble weight (inverse-MAE, as kharif) - it is the interpretable ENSO signal, and its disagreement with LightGBM is the `spread` confidence flag.
- Rabi yields use the APY/UPAG `season` label; Bihar, Odisha, West Bengal, Assam and Jharkhand shift area between seasons across years (Odisha has no Rabi rows in most years -> `no_data`); their rabi deviations include label-switch jumps. UPAG 2023+ covers major crops only.
- Scenario rows use phase-year means of the climate features; the 2026-27 event (ONI NDJ about +2.5 expected) is outside any observed winter, so `elnino_strong` is an analog stress test, not a forecast of the realised event. `prev_kharif_dev` / `prev_rabi_dev` in the scenario rows are the 2024 values.
- Season probabilities beyond the IRI plume horizon are not available: kharif 2027 uses the MJJ-2027 plume (La Nina / neutral split from the previous release ratio); OND-main (Tamil Nadu etc.) districts use the rabi-season probabilities for their kharif `current` mix.
- The kharif ML target remains the all-season foodgrain deviation (kharif-dominated) - Addendum F's 'kharif-season foodgrain yield deviation' split is available (`kharif_fg_*` columns) but the kharif hindcast and models were deliberately left unchanged.
- La Nina rabi shocks are *gains* on average (mean ensemble +1.36 pp; analog -0.75); only losses raise exposure, so rabi La Nina scores reflect the heat-hazard / carry-over terms and S / C, not a crop loss.


---

## v5 — imputation (`pipeline/03c_impute.py`, SCHEMA Addendum G)

### What changed

- **Overlay, never overwrite.** Every layer is filled from `artifacts/imputed_district.parquet` only where it is null (60 columns touched; method tags and per-district map in `imputed_district.json`; details and validation in `reports/03c_impute_report.md`). Sources: neighbours (touching polygons, border-weighted median, same state first), state / national median as last resort, state NFHS-5 -> NFHS-6 ratio, parent district for post-2011 splits, Earth Engine (WorldPop population, CHIRPS island climate, MODIS-NDVI rabi share).
- **Existing districts are not re-ranked by imputed ones.** Percentile ranks use the *observed* population of each term (`elig_ref`: 719 districts, imputed entries of a term excluded from its reference) and the band thresholds are still the tertiles of the observed kharif elnino scores (low < **45.0**, high >= **55.0**; v4: low < 44.9, high >= 55.4 - the shift is the effect of newly filled price / groundwater / NFHS terms on the 719 observed districts).
- **Newly scored, regular model (10 districts):** split children / new districts whose crop structure is the parent's (area share), and island districts with CHIRPS climate. Their shock is the analog formula (no 04b model row) with state-median beta where needed.
- **Consumption side (24 districts: Delhi x11, Mumbai x2, Kolkata, Chennai, Hyderabad, Chandigarh, Srinagar, The Nilgiris, Mahe, Yanam, Lakshadweep, South Andaman, Nicobars):** exposure = mean exposure of the donor districts (same state if >= 3 scored, else the touching districts found by breadth-first search, topped up with the 5 nearest by centroid for islands), expected shock = donors' mean shock, sensitivity = low self-sufficiency of the donor pool x 0.5 + PDS dependency x 0.5 (no crop-structure terms), capacity as usual (NFHS, Poshan, climate vulnerability, PDS). Actions that need local production (grain pre-position, seed bank, NREGA, fodder, PMFBY) are null; child / women-anaemia targets are computed. `risk.*.imputed = true`, `imputed_from = urban_consumption_side`.
- **Rabi without a 04b model row (164 districts: negligible-rabi and season-label-gap, rabi share of foodgrain area >= 0.5%):** the rabi shock of every phase is the border-weighted median of the touching districts' model shocks (`expected_shock_source = neighbours`, `imputed_from = neighbours_exposure`); the heat-hazard term uses the district's own Feb-Mar temperature. Season-label-gap districts (Odisha, Kerala, DNH) also get their rabi foodgrain area / production from the NDVI estimate (`ee_rabi_ndvi`; map R2 is only ~0.24, see 03c report) instead of the under-reported APY rows. The 18 districts below the 0.5% rabi-share floor stay `no_data` for rabi (`negligible_rabi_foodgrain`).
- **Flags.** `risk.<key>.imputed = true` (+ `imputed_from`, `imputed_share`) when the exposure is imputed (consumption side / neighbour rabi shock / imputed climate / parent crop structure) or imputed inputs carry >= 25% of the score weight (`imputed_inputs`); `data_quality.imputed` {dotted path: source} and `imputed_count` list every imputed entry incl. `risk.<key>`.

### no_data and band counts, before -> after

| scenario | before (high/medium/low/no_data) | after |
|---|---|---|
| kharif_2027:neutral | 25/182/512/34 | 27/181/545/0 |
| kharif_2027:elnino | 240/239/240/34 | 242/247/264/0 |
| kharif_2027:current | 126/253/340/34 | 134/257/362/0 |
| rabi_2026_27:neutral | 20/194/333/206 | 35/235/465/18 |
| rabi_2026_27:elnino | 135/196/216/206 | 190/248/297/18 |
| rabi_2026_27:current | 135/196/216/206 | 190/248/297/18 |

Kharif elnino `no_data`: 34 -> 0; rabi elnino `no_data`: 206 -> 18 (negligible_rabi_foodgrain: 18).

### Stability of the districts that were already scored (elnino)

- **kharif**: n = 719, Spearman before vs after = **0.990**, mean |score change| 0.73 pts (max 13.1), 42 band moves (6 %), top-25 overlap 23 of 25. Band matrix (rows before, columns after; high/medium/low): high: 227/13/0; medium: 13/218/8; low: 0/8/232.
- **rabi**: n = 547, Spearman before vs after = **0.994**, mean |score change| 0.64 pts (max 13.6), 23 band moves (4 %), top-25 overlap 22 of 25. Band matrix (rows before, columns after; high/medium/low): high: 127/8/0; medium: 9/183/4; low: 0/2/214.

Largest kharif elnino score changes among observed districts (cause = terms that were missing and are now estimated, mostly price / groundwater / NFHS): Alluri Sitharama Raju (Andhra Pradesh) 60.9 -> 47.8; Sri Sathya sai (Andhra Pradesh) 48.3 -> 58.9; Nandyal (Andhra Pradesh) 44.1 -> 53.2; Tirupati (Andhra Pradesh) 35.9 -> 42.7; Annamayya (Andhra Pradesh) 44.3 -> 50.4; Chengalpattu (Tamil Nadu) 39.3 -> 45.1; Gariaband (Chhattisgarh) 65.4 -> 60.3; Pakke Kessang (Arunachal Pradesh) 44.3 -> 39.3.

### Consumption-side districts (kharif elnino): score vs the donors they inherit exposure from

| district | state | score | band | exposure | sensitivity | capacity | donors (n) | donor mean score | donor mean exposure |
|---|---|---|---|---|---|---|---|---|---|
| Srinagar | Jammu & Kashmir | 30.6 | low | 0.31 | 0.36 | 0.24 | 19 | 40.9 | 0.31 |
| Chandigarh | Chandigarh | 20.3 | low | 0.32 | 0.09 | 0.14 | 8 | 29.5 | 0.32 |
| Central | Delhi | 37.1 | low | 0.45 | 0.30 | 0.33 | 12 | 41.3 | 0.45 |
| East | Delhi | 37.8 | low | 0.45 | 0.33 | 0.30 | 9 | 44.2 | 0.45 |
| New Delhi | Delhi | 37.4 | low | 0.44 | 0.30 | 0.35 | 8 | 41.1 | 0.44 |
| North | Delhi | 39.8 | low | 0.43 | 0.33 | 0.43 | 3 | 38.9 | 0.43 |
| North East | Delhi | 53.7 | medium | 0.46 | 0.73 | 0.44 | 5 | 45.3 | 0.46 |
| North West | Delhi | 32.1 | low | 0.42 | 0.14 | 0.36 | 11 | 36.6 | 0.42 |
| South | Delhi | 38.7 | low | 0.43 | 0.35 | 0.36 | 7 | 40.3 | 0.43 |
| South West | Delhi | 29.1 | low | 0.41 | 0.09 | 0.31 | 9 | 36.2 | 0.41 |
| West | Delhi | 37.1 | low | 0.44 | 0.22 | 0.44 | 8 | 37.0 | 0.44 |
| Kolkata | West Bengal | 30.0 | low | 0.31 | 0.31 | 0.28 | 22 | 41.8 | 0.31 |
| Mumbai | Maharashtra | 64.2 | high | 0.62 | 0.84 | 0.45 | 34 | 57.9 | 0.62 |
| Mumbai Suburban | Maharashtra | 50.3 | medium | 0.62 | 0.39 | 0.43 | 34 | 57.9 | 0.62 |
| Hyderabad | Telangana | 36.1 | low | 0.54 | 0.10 | 0.34 | 32 | 51.3 | 0.54 |
| Lakshadweep | Lakshadweep | 59.5 | high | 0.42 | 0.99 | 0.44 | 5 | 47.3 | 0.42 |
| Chennai | Tamil Nadu | 32.8 | low | 0.41 | 0.33 | 0.18 | 36 | 43.2 | 0.41 |
| The Nilgiris | Tamil Nadu | 40.8 | low | 0.41 | 0.50 | 0.30 | 36 | 43.2 | 0.41 |
| Mahe | Puducherry | 38.2 | low | 0.42 | 0.52 | 0.15 | 8 | 47.6 | 0.42 |
| Yanam | Puducherry | 48.7 | medium | 0.46 | 0.55 | 0.45 | 8 | 45.3 | 0.46 |
| South Andaman | Andaman & Nicobar | 32.8 | low | 0.46 | 0.29 | 0.14 | 5 | 47.4 | 0.46 |
| Nicobars | Andaman & Nicobar | 29.8 | low | 0.32 | 0.23 | 0.34 | 5 | 40.4 | 0.32 |
| South East | Delhi | 40.2 | low | 0.46 | 0.32 | 0.39 | 8 | 43.9 | 0.46 |
| Shahdara | Delhi | 43.6 | low | 0.46 | 0.48 | 0.34 | 5 | 45.3 | 0.46 |

### Flags

- kharif elnino: 753 scored; flagged `imputed`: 57 (urban_consumption_side: 24, imputed_inputs: 23, parent_split_area_share: 9, ee_chirps: 1); the other 696 are scored on observed inputs (some single terms may still be estimated and carry the `(estimated)` tag in their driver label).
- rabi elnino: 735 scored; flagged `imputed`: 206 (neighbours_exposure: 154, urban_consumption_side: 24, imputed_inputs: 18, parent_split_area_share: 9, ee_chirps: 1); the other 529 are scored on observed inputs (some single terms may still be estimated and carry the `(estimated)` tag in their driver label).

### Caveats (v5)

- Imputed values are *typical for the area*, not local measurements: the leave-one-out table in the 03c report shows the neighbour method beats a state median clearly for nutrition, rainfed / small-holding shares and groundwater depth, and not at all for NFHS-5 wasting, the price indices, groundwater decline and PDS tonnes per person (spatially noisy). About 600 entries (mostly price / groundwater) fall back to the national median because whole states (NE hills, Himachal, Uttarakhand) have no data.
- Consumption-side scores are a *supply-chain exposure proxy*, not a crop-yield risk; Mumbai scores high because Maharashtra's donors are high, Delhi low-to-medium because Haryana / UP / Rajasthan districts are. Lakshadweep (donors = 5 nearest Kerala-coast districts, no touching land) and the Andamans are the least certain.
- Rabi band of the 154 neighbour-shock districts inherits the neighbours' *model* shock; for districts with almost no rabi cropping (Arunachal, Mizoram, Nagaland, Chhattisgarh Bastar) it is a notional exposure of a minor activity - read together with `season_context.rabi.share_of_foodgrain_prod`. The NDVI rabi-share map has R2 ~ 0.24, so imputed rabi production for the 14 season-label-gap districts is indicative.
- WorldPop population (calibrated to the census-based level by the state median ratio) fills the 22 post-2011 districts; split PARENTS still carry pre-split census populations and crop totals (unchanged known caveat), so a parent / child pair double counts a little in national totals.
- `districts.json` grew from 14.9 to ~16.9 MB (the 06_export size guard `MAX_MB` is raised from 15 to 17): 188 more districts have a rabi risk block.

---

## v6 — season outlook (`season_outlook`, SCHEMA Addendum I)

- `season_outlook[season][phase]` for 753 / 753 districts (every district with a climate record, observed or imputed), 5 phases x 2 seasons; `kpis.season_outlook_national` = cropped-area-weighted means (gross cropped area) of the same fields.
- Kharif: `rain_anom_pct` = the scenario anomaly used in the exposure terms (main-season: JJAS, or OND for the 45 OND-main districts - their rain_window is Oct–Dec and TimesFM JJAS fields are null); `p_deficit_gt10` = share of El Nino years with a > 10 % deficit (strong analog: mean of that and the strong-analog share, as in the exposure hazard; neutral: climatological share of all 2000-2025 years; La Nina: share of La Nina years > +15 % = the flood share, as the contract says; current: probability-weighted TRUE deficit share of the three phases); `tmax_anom_c` = JJAS tmax anomaly of the phase's years (neutral 0); `onset_delay_days` = phase-year mean onset day minus all-year mean (02_climate onset: first day after 1 Jun with 7-day rain >= 50 mm); TimesFM fields display-only.
- Rabi: `rain_anom_pct` = mean OND anomaly of the phase's crop years (the `rain_anomaly_pct` of the rabi scenario); `tmax_anom_c` = Feb\u2013Mar tmax anomaly of the FOLLOWING year (crop year Y -> Feb\u2013Mar Y+1) averaged over the phase's years (strong: 2002 / 2009 / 2015) - the same series as the rabi score's terminal-heat hazard (`risk.*.tmax_febmar_anomaly_c`); neutral 0; La Nina -0.3 C **assumption**, not data. NOTE: this differs from `climate.tmax_febmar_elnino_anomaly_c` (same calendar year, national El Nino mean +0.53 C vs -0.17 C here); per coordinator decision the outlook matches the score.
- `plain` sentence: probability word from `enso_status.p_by_season` of the phase (>= 0.8 very likely, 0.5–0.8 likely, 0.1–0.5 possible; **< 0.1 is written 'in <phase> years (unlikely this season)'**, an addition so a 0 % phase is not called possible; the strong El Nino analog carries no probability word); `current` uses the dominant phase's probability and the probability-weighted numbers. The head line follows the phrasing rule (El Nino kharif -> weak monsoon; La Nina -> heavy rain / flooding; neutral -> near-normal; El Nino rabi -> dry / warm winter) but only where the district's own record supports it (kharif El Nino: rain <= -5 % or deficit chance >= 50 %; La Nina: flood share >= 25 % or rain >= +5 %; rabi: dry <= -5 %, wet >= +5 %, warm >= +0.3 C, cool <= -0.3 C), otherwise a near-normal wording is used.

| season | phase | rain % | p deficit | tmax C | onset d | plain |
|---|---|---|---|---|---|---|
| kharif_2027 | lanina | 7.9 | 0.38 | -0.18 | -2.5 | Heavy rain / flooding possible in La Niña years here (unlikely this season): about 8 % more rain than normal, 4 in 10 La Niña years had flood-level excess rain |
| kharif_2027 | neutral | 4.4 | 0.39 | 0.0 | -0.3 | Near-normal season possible: rain close to normal on average, a serious deficit hits about 4 in 10 years |
| kharif_2027 | elnino | -12.3 | 0.57 | 0.23 | 3.2 | Weak monsoon likely: about 12 % less rain than normal, 6 in 10 chance of a serious deficit |
| kharif_2027 | elnino_strong | -19.2 | 0.63 | 0.66 | 6.9 | In a strong El Niño, weak monsoon: about 19 % less rain than normal, 6 in 10 chance of a serious deficit |
| kharif_2027 | current | -5.6 | 0.5 | 0.13 | 1.9 | Weak monsoon likely: about 6 % less rain than normal, 5 in 10 chance of a serious deficit |
| rabi_2026_27 | lanina | -17.5 |  | -0.3 |  | Dry, cool winter in La Niña years (unlikely this season): less Oct–Dec rain and cooler Feb–Mar |
| rabi_2026_27 | neutral | -9.4 |  | 0.0 |  | Dry winter in neutral years (unlikely this season): less Oct–Dec rain and Feb–Mar temperatures close to normal |
| rabi_2026_27 | elnino | -21.7 |  | -0.1 |  | Dry winter very likely: less Oct–Dec rain and Feb–Mar temperatures close to normal |
| rabi_2026_27 | elnino_strong | -20.4 |  | 0.67 |  | In a strong El Niño, dry, warm winter: less Oct–Dec rain and hotter Feb–Mar (about +0.7 °C) |
| rabi_2026_27 | current | -21.7 |  | -0.1 |  | Dry winter very likely: less Oct–Dec rain and Feb–Mar temperatures close to normal |

Labels: every user-facing 'MGNREGA' is now 'NREGA' (actions CSV header `nrega_persondays`, report text); JSON keys keep `mgnrega_persondays`.
