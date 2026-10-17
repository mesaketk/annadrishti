# 04b ML ensemble report

Target `ydev_pct`: foodgrain yield deviation (%) from a Theil-Sen trend fitted on the prior 10 crop years (>= 6 obs), clipped +/-100 -- identical to the 04_risk hindcast `actual_dev`. Panel: **13,306 district-years** (689 districts, 2003-2024; no target before 2003 because the trend needs 6 prior years from 1997, so the 2002 fold is empty). Features (18): jjas_anomaly_pct, ond_anomaly_pct, main_anom_pct, dry_spells, onset_day, tmax_jjas_anom, tmax_febmar_anom, oni_jja_son, prev_year_ydev, irrigated_share, simpson_div, top_crop_share, small_marginal_share, gw_stress_idx, state, main_season_ond, lat, lon (`main_anom_pct` = the district's main-season anomaly, OND for TN/Puducherry/Nellore/Chittoor/Prakasam, added so the ML models see the same driver as the analog).

## Harness

Leave-one-year-out over 2003-2024 (held-out year predicted by a model trained on all other years, except Y+1 which is dropped because its `prev_year_ydev` feature contains Y's target). This is **not** a forecasting backtest: training includes future years, which is the right design for 'does the model generalise to an unseen monsoon' but flatters models that learn secular structure. `analog` = 04_risk formula `clip(beta x f x (0.4+0.6 rainfed))` with beta, El Nino/neutral anomaly means recomputed excluding the held-out year (from this same ydev panel, so betas are noisier than the shipped ones: ydev starts 2003 -> El Nino years 2004/06/09/15/18/23). `analog_shipped` uses the shipped `beta_used_pct` (computed on all years incl. the held-out one: **optimistic/leaky**, reference only). `lgbm` = LightGBM huber, 3-seed mean, early stopping on 1/6 of training years held out. `tabfm` = TabFM zero-shot regression -- **NOT AVAILABLE**: disabled via --no-tabfm

Sign conventions: rho = Spearman(predicted shock, actual deviation), **positive = good**; tercile gap = mean actual dev of worst-predicted tercile minus best-predicted tercile, **negative = good** (same sign as 04_risk's top-minus-bottom).

## Pooled results (13,267 held-out district-years from 22 folds (2003-2024) where every member has a prediction)

| model | MAE (pp) | pooled rho | mean within-year rho | mean per-year MAE |
|---|---|---|---|---|
| analog | 17.71 | 0.077 | 0.060 | 17.87 |
| analog_shipped | 17.43 | 0.136 | 0.103 | 17.60 |
| lgbm | 16.07 | 0.305 | 0.286 | 16.28 |
| ensemble | 16.31 | 0.280 | 0.258 | 16.54 |
| (predict 0) | 16.96 | - | - | - |
| (predict global mean) | 17.14 | - | - | - |

All 13,306 rows / 23 folds, models without the TabFM CPU restriction:

| model | MAE (pp) | pooled rho | mean within-year rho |
|---|---|---|---|
| analog | 17.71 | 0.077 | 0.060 |
| analog_shipped | 17.43 | 0.136 | 0.103 |
| lgbm | 16.14 | 0.303 | 0.286 |
| ensemble | 16.38 | 0.277 | 0.258 |
| (predict 0) | 17.02 | - | - |

## Hindcast years (the 4 years 04_risk reports)

| year | phase | n | analog MAE / rho / gap | lgbm MAE / rho / gap | tabfm MAE / rho / gap | ensemble MAE / rho / gap |
|---|---|---|---|---|---|---|
| 2009 | El Niño | 577 | 16.46 / 0.183 / -9.70 | 15.89 / 0.281 / -16.25 | - | 15.47 / 0.335 / -18.40 |
| 2014 | Neutral | 613 | 19.71 / 0.258 / -14.76 | 18.17 / 0.461 / -25.02 | - | 18.24 / 0.475 / -25.10 |
| 2015 | El Niño | 620 | 16.58 / 0.304 / -14.26 | 16.53 / 0.334 / -12.14 | - | 16.18 / 0.404 / -18.27 |
| 2023 | El Niño | 685 | 14.61 / 0.086 / -0.53 | 13.57 / 0.239 / -11.28 | - | 13.64 / 0.216 / -9.77 |

## Per-year rho (all folds)

| year | phase | n | analog | analog_shipped | lgbm | tabfm | ensemble |
|---|---|---|---|---|---|---|---|
| 2003 | Neutral | 474 | -0.038 | -0.099 | 0.296 | - | 0.218 |
| 2004 | El Niño | 533 | -0.049 | 0.148 | 0.199 | - | 0.171 |
| 2005 | Neutral | 557 | 0.185 | 0.107 | 0.430 | - | 0.398 |
| 2006 | El Niño | 560 | 0.001 | 0.060 | 0.245 | - | 0.140 |
| 2007 | La Niña | 560 | 0.112 | 0.123 | 0.460 | - | 0.410 |
| 2008 | Neutral | 561 | 0.134 | 0.089 | 0.285 | - | 0.334 |
| 2009 | El Niño | 577 | 0.183 | 0.375 | 0.281 | - | 0.335 |
| 2010 | La Niña | 583 | 0.077 | 0.068 | 0.238 | - | 0.200 |
| 2011 | La Niña | 590 | 0.058 | 0.113 | 0.380 | - | 0.340 |
| 2012 | Neutral | 595 | -0.061 | 0.058 | 0.469 | - | 0.358 |
| 2013 | Neutral | 603 | -0.012 | -0.106 | 0.157 | - | 0.165 |
| 2014 | Neutral | 613 | 0.258 | 0.269 | 0.461 | - | 0.475 |
| 2015 | El Niño | 620 | 0.304 | 0.511 | 0.334 | - | 0.404 |
| 2016 | Neutral | 621 | 0.006 | -0.065 | 0.317 | - | 0.216 |
| 2017 | Neutral | 631 | 0.087 | 0.007 | 0.286 | - | 0.286 |
| 2018 | El Niño | 640 | 0.027 | 0.206 | 0.257 | - | 0.225 |
| 2019 | Neutral | 646 | -0.102 | -0.117 | 0.091 | - | 0.033 |
| 2020 | La Niña | 652 | -0.133 | -0.146 | 0.177 | - | 0.066 |
| 2021 | La Niña | 656 | 0.028 | 0.126 | 0.394 | - | 0.363 |
| 2022 | La Niña | 683 | 0.088 | 0.122 | 0.160 | - | 0.170 |
| 2023 | El Niño | 685 | 0.086 | 0.408 | 0.239 | - | 0.216 |
| 2024 | Neutral | 666 | 0.091 | 0.009 | 0.141 | - | 0.152 |

## Per-year MAE

| year | analog | lgbm | tabfm | ensemble |
|---|---|---|---|---|
| 2003 | 23.03 | 21.65 | - | 22.10 |
| 2004 | 20.00 | 18.06 | - | 18.31 |
| 2005 | 16.80 | 15.27 | - | 15.54 |
| 2006 | 19.83 | 18.01 | - | 18.53 |
| 2007 | 17.59 | 14.47 | - | 15.55 |
| 2008 | 17.65 | 16.73 | - | 16.80 |
| 2009 | 16.46 | 15.89 | - | 15.47 |
| 2010 | 19.72 | 17.14 | - | 18.02 |
| 2011 | 22.77 | 19.18 | - | 20.40 |
| 2012 | 22.60 | 18.83 | - | 20.21 |
| 2013 | 18.40 | 16.14 | - | 16.57 |
| 2014 | 19.71 | 18.17 | - | 18.24 |
| 2015 | 16.58 | 16.53 | - | 16.18 |
| 2016 | 22.64 | 20.83 | - | 21.55 |
| 2017 | 15.72 | 14.07 | - | 14.07 |
| 2018 | 15.11 | 13.90 | - | 13.68 |
| 2019 | 15.60 | 14.59 | - | 14.83 |
| 2020 | 16.71 | 14.28 | - | 15.12 |
| 2021 | 13.88 | 14.17 | - | 12.97 |
| 2022 | 15.32 | 14.83 | - | 14.27 |
| 2023 | 14.61 | 13.57 | - | 13.64 |
| 2024 | 12.38 | 11.85 | - | 11.76 |

## LightGBM feature importance (gain %, final model on all years, 3-seed sum)

| feature | gain % |
|---|---|
| prev_year_ydev | 28.2 |
| state | 21.1 |
| oni_jja_son | 12.8 |
| main_anom_pct | 7.8 |
| tmax_jjas_anom | 6.0 |
| tmax_febmar_anom | 5.9 |
| ond_anomaly_pct | 5.4 |
| lat | 2.6 |
| jjas_anomaly_pct | 2.1 |
| onset_day | 1.7 |
| irrigated_share | 1.3 |
| lon | 1.0 |
| simpson_div | 1.0 |
| top_crop_share | 1.0 |
| gw_stress_idx | 1.0 |
| small_marginal_share | 0.6 |
| dry_spells | 0.4 |
| main_season_ond | 0.0 |

## Ensemble weights

| member | weight (proportional to 1/pooled MAE) |
|---|---|
| analog | 0.476 |
| lgbm | 0.524 |
| tabfm | null (unavailable) |

## Scenario predictions (today)

753 scored districts x 4 scenarios (v4: analog member = pure phases, El Nino p = 1; `lanina` follows the flood rule: analog = beta_LaNina only where La Nina-year rain > +15 % and beta_LaNina < 0, ensemble gated the same way - 60 flood-flagged districts). Mean shock % and member spread:

| scenario | analog | lgbm | tabfm | ensemble | spread |
|---|---|---|---|---|---|
| neutral | 0.00 | -0.23 | - | -0.09 | 2.90 |
| elnino | -4.46 | -6.28 | - | -5.38 | 4.57 |
| elnino_strong | -6.42 | -8.60 | - | -7.53 | 5.82 |
| lanina | -0.49 | 5.04 | - | -0.06 | 5.96 |

Rank correlation of analog with other members across districts: {"elnino": {"shock_lgbm_pct": 0.608}, "elnino_strong": {"shock_lgbm_pct": 0.664}, "lanina": {"shock_lgbm_pct": -0.121}, "neutral": {"shock_lgbm_pct": 0.0}}

## Honest conclusion

- Pooled MAE: best = **lgbm** (16.07 pp) vs analog 17.71 pp, predict-0 16.96 pp. Within-year ranking (what the risk score needs): best mean rho = **lgbm** (0.286) vs analog 0.060.
- ML members see year-specific weather (dry spells, onset, heat, previous-year yield) and the district's static structure, so they can rank districts within a year; the analog uses one anomaly and a fixed per-district beta and is blind to everything else. The ML advantage is largest where the analog's beta is noisy (few El Nino years, 6 in the ydev panel).
- Caveats: (1) LOYO trains on future years (not a true forecast skill estimate); (2) yield deviation is noisy and partially reporting-error driven (clip +/-100), so absolute MAE floors are high; (3) scenario rows are synthetic composites (El Nino-year mean dry spells/onset/tmax, ONI +1.5/+2.2) that average out year-specific extremes, so ML scenario shocks are shrunk towards the mean vs. any real year; (4) the ML models extrapolate `oni_jja_son`=2.2 using only 2015/2023 (~1.0-2.0) so strong scenario is mostly the rainfall-anomaly channel; (5) the analog n=719 scored districts, ML trained on all districts with a target; (6) trailing Theil-Sen detrending means a target year following a drop has an inflated deviation (mean reversion) which prev_year_ydev partly exploits -- it is a legitimate predictor but not climate-driven.
- Sample sizes: 13,306 train rows overall, ~578 per held-out year, hindcast years n = 577, 613, 620, 685.
- TabFM: unavailable (disabled via --no-tabfm); `tabfm` slot is null and ensemble = analog + lgbm.
