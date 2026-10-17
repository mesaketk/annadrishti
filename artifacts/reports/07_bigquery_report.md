# 07 - BigQuery warehouse + TimesFM forecasts

Project `aibuildercup-511905`, dataset `aibuildercup-511905.annadrishti`, **location `asia-south1`** (AI.FORECAST verified in asia-south1 and US). GCS: **not uploaded** (403 POST https://storage.googleapis.com/storage/v1/b?project=aibuildercup-511905&prettyPrint=false: The billing account for the owning project is disabled in state absent). Re-run `python3 pipeline/07_bigquery.py --analysis-only` once billing is enabled.

## Tables

| table | rows | bytes |
|---|---|---|
| `actions_elnino` | 719 | 109,577 |
| `backtest_rain_timesfm` | 71,904 | 6,003,984 |
| `climate_district` | 753 | 1,999,711 |
| `crops_district_year` | 17,671 | 3,878,721 |
| `crops_latest` | 753 | 700,136 |
| `district_month_oni` | 333 | 11,655 |
| `district_month_pds` | 19,003 | 912,144 |
| `district_month_poshan` | 18,018 | 593,258 |
| `district_month_rain` | 233,686 | 5,608,464 |
| `districts` | 753 | 44,900 |
| `extra_district` | 753 | 948,940 |
| `forecast_poshan_timesfm` | 4,440 | 430,680 |
| `forecast_rain_timesfm` | 31,458 | 2,626,743 |
| `risk_district` | 753 | 278,381 |
| `social_district` | 753 | 1,772,070 |
| `timesfm_summary` | 753 | 65,800 |
| `yield_sensitivity` | 753 | 179,399 |

## Models and syntax

- `AI.FORECAST` (BigQuery AI function, no model object to create). Univariate: `model => 'TimesFM 2.5'` (default, GA), `data_col`, `timestamp_col`, `id_cols => ['lgd']`, `horizon`, `confidence_level => 0.8`.
- Covariates: **supported only via TimesFM 3.0 (Preview) multivariate form**: `target_cols => ['rain_mm']`, `future_covariate_cols => ['oni']`, `model => 'TimesFM 3.0'`, `context_window => 320`; future target rows must be NULL and the covariate must span history + horizon. TimesFM 2.5 has no covariate support.
- Rain horizon is **21 months** (2026-01..2027-09) because IMD data in the cache ends 2025-12 (the brief said 15; 21 is what reaches 2027-09). 2026 is unobserved rainfall, forecast through.
- ONI covariate: observed NOAA CPC ONI through JAS-2026 (centre month 2026-08); later months are **assumptions** approximating the IRI/CPC plume of a strong event decaying: 2026-09 2.2, 2026-10 2.25, 2026-11 2.3, 2026-12 2.4, 2027-01 2.3, 2027-02 2.0, 2027-03 1.6, 2027-04 1.2, 2027-05 0.8, 2027-06 0.5, 2027-07 0.3, 2027-08 0.1, 2027-09 0.0. Season-to-month mapping uses the centre month (OND -> Nov).
- Primary summary columns (`jjas2027_*`) use the **ONI-covariate (TimesFM 3.0) variant**; `*_uni` columns hold the univariate TimesFM 2.5 result. Both variants are in `forecast_rain_timesfm` (column `variant`).
- JJAS p10/p90: the model gives 80% bounds per month; for the 4-month total we combine monthly sds assuming independent errors (approximation, likely too narrow if monthly errors correlate).

## Forecast sanity (JJAS 2027 anomaly vs 2000-24 normal)

**ONI-covariate (TimesFM 3.0, primary)** (n=749 districts)
- mean anomaly -9.14% (cropped-area-weighted -7.72%); share of districts with deficit 88%; share below -10%: 38%
- percentiles (0/5/10/25/50/75/90/95/100): -59.3, -27.7, -22.4, -13.5, -7.8, -3.8, +0.8, +5.5, +32.9
- median 80% interval width on the anomaly: 58.6 pp
- vs district analog El Nino mean anomaly (mean -9.5%): Pearson +0.01, Spearman -0.05
- vs strong-El Nino analog (2002/09/15; mean -15.5%): Pearson -0.11, Spearman -0.08

**Univariate (TimesFM 2.5)** (n=749 districts)
- mean anomaly -13.34% (cropped-area-weighted -11.79%); share of districts with deficit 82%; share below -10%: 59%
- percentiles (0/5/10/25/50/75/90/95/100): -67.7, -39.1, -31.6, -21.6, -13.5, -4.2, +5.0, +10.0, +40.1
- median 80% interval width on the anomaly: 69.6 pp
- vs district analog El Nino mean anomaly (mean -9.5%): Pearson -0.00, Spearman +0.00
- vs strong-El Nino analog (2002/09/15; mean -15.5%): Pearson -0.16, Spearman -0.14

Monthly table vs `climate_district.jjas_normal_mm`: max abs deviation 0.021% (consistency check).

### Hindcasts (history through Dec of year-1, 12 months ahead; ONI covariate uses ACTUAL ONI = perfect-ENSO-forecast upper bound)

| JJAS year | actual all-India mean anom % | uni fc mean % | uni corr | uni RMSE | ONI-cov fc mean % | cov corr | cov RMSE | climatology RMSE |
|---|---|---|---|---|---|---|---|---|
| 2009 | -15.3 | -20.9 | +0.23 | 29.5 | -10.2 | +0.17 | 27.6 | 29.5 |
| 2015 | -10.6 | -19.5 | -0.04 | 30.3 | -16.8 | +0.04 | 27.1 | 26.7 |
| 2023 | -4.3 | -14.1 | +0.07 | 28.3 | -11.6 | -0.06 | 26.9 | 23.6 |
| 2025 | +10.8 | -12.1 | +0.19 | 41.0 | -10.6 | +0.26 | 39.1 | 35.6 |

## Poshan / PDS

- Poshan underweight %: 740 districts with series ending 2026-02-01; 6-month horizon; internal gaps linearly interpolated (flag `is_interpolated`). Series are only ~24 monthly points and integer-rounded: treat as indicative.
- PDS: latest observation 2021-11-01 (59 months stale) -> forecast **skipped**; `pds_12m_forecast_t` is null. Template `bq/04_pds.sql` kept.
- Rows with non-empty `ai_forecast_status`: 0.

## Caveats

- **BigQuery sandbox**: project has no billing account (GCS bucket creation returns 403 'billing account ... disabled'). BigQuery works in sandbox mode but all tables auto-expire after 60 days (first expiry 2026-12-16; cannot be lifted without billing). Re-running this script refreshes them. Enable billing to lift the expiry and to create the GCS bucket.
- **Low-bias of median forecasts**: `forecast_value` is the 50% quantile. Monthly rainfall is right-skewed, so the sum of four monthly medians sits below the mean-based normal. Hindcasts show a persistent negative bias (all-India mean anomaly forecasts of -10..-20% even when actual was +11%). Read the absolute JJAS-2027 anomalies as biased low by roughly 5-10 pp; use them as a relative/ranking signal at most, and see the hindcast table for how little district-level skill there is.
- District-level skill is approximately nil: hindcast correlation of forecast vs actual JJAS anomaly across districts is between -0.06 and +0.26 and district RMSE is not better than forecasting 0% (climatology). The ONI covariate shifts the all-India mean towards deficit but does not add spatial skill. TimesFM output is a pattern forecast; it does not replace the ENSO-conditioned analog scenarios in 04_risk.py.
- TimesFM 3.0 multivariate is Preview (billing/feature changes possible; token billing from 2026-12-01).
- ONI beyond JAS-2026 is an assumption (see above), not an official forecast.

## Cost

Total bytes processed 56,543,712 (56.5 MB); total slot-ms 1,871,135. On-demand at ~$6.25/TiB that is far below one cent; AI.FORECAST bills at the BigQuery ML prediction rate (see pricing page; TimesFM 3.0 Preview token billing starts 2026-12-01).

| sql | dest | cutoff | bytes processed | slot ms | secs |
|---|---|---|---|---|---|
| 01_rain_univariate.sql | forecast_rain_timesfm | 2025-12-01 | 5,608,464 | 57,886 | 31.3 |
| 02_rain_covariate.sql | forecast_rain_timesfm | 2025-12-01 | 5,613,792 | 270,991 | 72.2 |
| 01_rain_univariate.sql | backtest_rain_timesfm | 2008-12-01 | 5,608,464 | 29,608 | 11.3 |
| 02_rain_covariate.sql | backtest_rain_timesfm | 2008-12-01 | 5,613,792 | 283,922 | 86.7 |
| 01_rain_univariate.sql | backtest_rain_timesfm | 2014-12-01 | 5,608,464 | 46,660 | 17.8 |
| 02_rain_covariate.sql | backtest_rain_timesfm | 2014-12-01 | 5,613,792 | 193,028 | 54.7 |
| 01_rain_univariate.sql | backtest_rain_timesfm | 2022-12-01 | 5,608,464 | 56,314 | 29.4 |
| 02_rain_covariate.sql | backtest_rain_timesfm | 2022-12-01 | 5,613,792 | 238,594 | 67.3 |
| 01_rain_univariate.sql | backtest_rain_timesfm | 2024-12-01 | 5,608,464 | 54,320 | 28.4 |
| 02_rain_covariate.sql | backtest_rain_timesfm | 2024-12-01 | 5,613,792 | 609,851 | 118.9 |
| 03_poshan.sql | forecast_poshan_timesfm | 2026-02-01 | 432,432 | 29,961 | 10.8 |
