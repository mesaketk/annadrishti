# 04b ML ensemble report - RABI

Target `ydev_pct`: **rabi-season foodgrain yield deviation** (%) from a Theil-Sen trend on the prior 10 crop years (>= 6 obs), clipped +/-100; crop year Y = rabi sown Oct Y, harvested Mar Y+1; rabi yield = rabi_fg_yield_t_ha (01_crops: cereals + millets + pulses with season label Rabi, >= 500 ha). Panel: **10,606 district-years** (602 districts, 2003-2024). Features (14): ond_anomaly_pct, tmax_febmar_anom, jjas_anomaly_pct, oni_ndj, prev_kharif_dev, prev_rabi_dev, irrigated_share, gw_stress_idx, small_marginal_share, top_crop_share, rabi_share, state, lat, lon. Climate alignment: OND and JJAS anomalies of year Y, Feb-Mar tmax anomaly of Y+1, ONI NDJ of year Y.

Caveat: season labels in APY/UPAG are unreliable in Bihar, Odisha, West Bengal, Assam and Jharkhand (see 01_crops report) - rabi deviations there include label-switch jumps.

## Harness

Leave-one-year-out 2003-2024 exactly as kharif (the following year is dropped from training because its `prev_rabi_dev` contains the held-out target). `analog` = phase beta: held-out El Nino year -> beta(El Nino) (mean rabi deviation in El Nino years minus neutral years, recomputed without the held-out year, clipped, state/national-median imputed), La Nina year -> beta(La Nina), neutral year -> 0; no irrigation buffer (terminal heat hits irrigated wheat). `lgbm` = LightGBM huber, 3-seed mean. TabFM not used. Not a forecasting backtest.

## Pooled results (10,606 held-out district-years)

| model | MAE (pp) | pooled rho | mean within-year rho | mean per-year MAE |
|---|---|---|---|---|
| analog | 19.73 | -0.012 | -0.015 | 19.76 |
| lgbm | 17.43 | 0.317 | 0.317 | 17.47 |
| ensemble | 17.95 | 0.248 | 0.259 | 18.00 |
| (predict 0) | 18.63 | - | - | - |

Ensemble weights (1/MAE): analog 0.469, lgbm 0.531.

## Hindcast crop years

| crop year | phase | n | analog MAE / rho / gap | lgbm MAE / rho / gap | ensemble MAE / rho / gap |
|---|---|---|---|---|---|
| 2009-10 | El Niño | 408 | 17.31 / 0.039 / -0.49 | 15.92 / 0.136 / -4.90 | 15.99 / 0.129 / -5.70 |
| 2015-16 | El Niño | 490 | 20.40 / -0.143 / 8.02 | 15.01 / 0.388 / -15.67 | 16.84 / 0.174 / -6.96 |
| 2021-22 | La Niña | 539 | 16.22 / 0.106 / -5.72 | 13.73 / 0.387 / -18.73 | 14.03 / 0.361 / -18.33 |
| 2022-23 | La Niña | 578 | 20.50 / -0.049 / 6.47 | 17.94 / 0.241 / -17.30 | 18.28 / 0.146 / -6.41 |

## Per-year rho

| crop year | phase | n | analog | lgbm | ensemble |
|---|---|---|---|---|---|
| 2003 | Neutral | 364 | - | 0.270 | 0.270 |
| 2004 | El Niño | 411 | -0.202 | 0.539 | 0.242 |
| 2005 | Neutral | 411 | - | 0.352 | 0.352 |
| 2006 | El Niño | 443 | 0.043 | 0.295 | 0.281 |
| 2007 | La Niña | 444 | 0.029 | 0.415 | 0.304 |
| 2008 | Neutral | 444 | - | 0.409 | 0.409 |
| 2009 | El Niño | 408 | 0.039 | 0.136 | 0.129 |
| 2010 | La Niña | 457 | 0.202 | 0.176 | 0.254 |
| 2011 | La Niña | 461 | -0.183 | 0.305 | -0.002 |
| 2012 | Neutral | 461 | - | 0.482 | 0.482 |
| 2013 | Neutral | 468 | - | 0.175 | 0.175 |
| 2014 | Neutral | 476 | - | 0.399 | 0.399 |
| 2015 | El Niño | 490 | -0.143 | 0.388 | 0.174 |
| 2016 | Neutral | 495 | - | 0.255 | 0.255 |
| 2017 | Neutral | 507 | - | 0.393 | 0.393 |
| 2018 | El Niño | 528 | -0.087 | 0.382 | 0.180 |
| 2019 | Neutral | 531 | - | 0.159 | 0.159 |
| 2020 | La Niña | 542 | 0.143 | 0.287 | 0.302 |
| 2021 | La Niña | 539 | 0.106 | 0.387 | 0.361 |
| 2022 | La Niña | 578 | -0.049 | 0.241 | 0.146 |
| 2023 | El Niño | 582 | -0.080 | 0.277 | 0.187 |
| 2024 | Neutral | 566 | - | 0.258 | 0.258 |

## LightGBM feature importance (gain %)

| feature | gain % |
|---|---|
| prev_rabi_dev | 31.7 |
| state | 18.1 |
| oni_ndj | 11.5 |
| prev_kharif_dev | 10.0 |
| tmax_febmar_anom | 8.5 |
| jjas_anomaly_pct | 5.6 |
| ond_anomaly_pct | 3.6 |
| lat | 2.9 |
| lon | 1.9 |
| irrigated_share | 1.6 |
| small_marginal_share | 1.5 |
| rabi_share | 1.3 |
| top_crop_share | 1.0 |
| gw_stress_idx | 0.8 |

## Scenario predictions (547 rabi-eligible scored districts)

| scenario | analog | lgbm (vs neutral) | lgbm raw | ensemble | spread | ONI NDJ | phase years |
|---|---|---|---|---|---|---|---|
| neutral | 0.00 | 0.00 | 3.35 | 0.00 | 0.00 | -0.16 | [2001, 2003, 2005, 2008, 2012, 2013, 2014, 2016, 2017, 2019, 2024] |
| lanina | -0.75 | 3.23 | 6.58 | 1.36 | 7.57 | -1.07 | [2000, 2007, 2010, 2011, 2020, 2021, 2022] |
| elnino | -3.44 | 0.50 | 3.85 | -1.35 | 6.87 | 1.40 | [2002, 2004, 2006, 2009, 2015, 2018, 2023] |
| elnino_strong | -5.66 | -1.39 | 1.96 | -3.39 | 7.65 | 1.72 | [2002, 2009, 2015] |

LightGBM scenario shocks are **relative to the same district's neutral-winter prediction** (the raw prediction is the deviation from a lagged trailing trend, mean about +5 pp, dominated by the carried-over 2024 deviation; subtracting the neutral row removes that level and the persistence term so the shock is the climate / ENSO-attributable part, neutral = 0 as for the analog). Pooled mean of the leave-one-year-out LightGBM predictions (the level used to de-bias the 04_risk rabi hindcast): +3.54 pp.

## Honest conclusion

- Pooled MAE: lgbm 17.43 pp, analog 19.73 pp, predict-0 18.63 pp; within-year rank skill rho: lgbm 0.317, analog -0.015.
- Scenario rows are phase-year means of the climate features, so they shrink towards the mean; the ONI NDJ of the 2026-27 event (about +2.5) is outside the training range of any winter, and the strong scenario mainly differs through the analog beta.
- `prev_kharif_dev` / `prev_rabi_dev` in the scenario rows are the last observed (crop year 2024) deviations, not the unobserved 2026 values.
