# AnnaDrishti BigQuery warehouse + TimesFM forecasts

Project `aibuildercup-511905`, dataset `annadrishti`, location **asia-south1** (AI.FORECAST with TimesFM 2.5 and 3.0 verified there; US also works).
Everything is built by `pipeline/07_bigquery.py` (idempotent; all loads WRITE_TRUNCATE; `lgd` is INT64 and the join key everywhere).

## Layout
| group | tables |
|---|---|
| dimensions / features | `districts`, `crops_district_year`, `crops_latest`, `climate_district`, `social_district`, `extra_district`, `yield_sensitivity`, `risk_district` (flattened districts.json: 3 scenarios x score/band/shock/exposure/sensitivity/capacity, food balance, NFHS-5/6, Poshan), `actions_elnino` |
| monthly series | `district_month_rain` (lgd, month, rain_mm; IMD 2000-01..2025-12), `district_month_oni` (month, oni, source = observed or assumed), `district_month_poshan` (underweight_pct, `_filled`, `is_interpolated`), `district_month_pds` (rice_t, wheat_t, alloc; ends 2021-11) |
| forecasts | `forecast_rain_timesfm` (variant = `timesfm2.5_univariate` or `timesfm3.0_oni_covariate`; lgd, series, cutoff, horizon_month, forecast, p10, p90), `forecast_poshan_timesfm`, `backtest_rain_timesfm` (hindcasts for JJAS 2009/2015/2023/2025), `timesfm_summary` (per-lgd JJAS-2027 anomaly, p10/p90, Poshan 6m, PDS null) |
| not built | `forecast_pds_timesfm`: PDS series is 59 months stale, skipped (`bq/04_pds.sql` template kept) |

Local mirrors: `artifacts/timesfm_forecasts.parquet`, `artifacts/timesfm_summary.parquet`, `artifacts/_district_month_rain.parquet` (cache), `artifacts/_bq_jobstats.json`.
Report with row counts, sanity and hindcasts: `artifacts/reports/07_bigquery_report.md`.

## SQL (bq/)
`01_rain_univariate.sql` (TimesFM 2.5), `02_rain_covariate.sql` (TimesFM 3.0, `target_cols`, `future_covariate_cols => ['oni']`), `03_poshan.sql`, `04_pds.sql`. `${...}` placeholders are filled by the script. AI.FORECAST requires `horizon` and `confidence_level` to be literals.

## Re-run
```bash
export GOOGLE_APPLICATION_CREDENTIALS=$PWD/aibuildercup-511905-0689c9d7ac44.json   # key is git-ignored; never commit/print it
python3 pipeline/07_bigquery.py               # full: load tables, run AI.FORECAST (~10 min, 11 jobs), summary, sanity, GCS, report
python3 pipeline/07_bigquery.py --analysis-only   # reuse existing forecast tables; rebuild summary/sanity/GCS/report (~30 s)
python3 pipeline/07_bigquery.py --skip-gcs
```

## Cost
All 11 AI.FORECAST jobs together: ~56.5 MB processed, ~1.87M slot-ms (`artifacts/_bq_jobstats.json`). Negligible on-demand (<$0.01 at $6.25/TiB for bytes; AI.FORECAST bills at the BigQuery ML prediction rate). TimesFM 3.0 is Preview; token-based billing starts 2026-12-01.

## Known limits
- Project has **no billing account**: BigQuery runs in sandbox mode, tables auto-expire after 60 days (first: 2026-12-16), and GCS bucket creation fails with 403. Enable billing, then re-run `--analysis-only` (creates `gs://aibuildercup-511905-annadrishti/artifacts/v1/` with districts.json, kpis.json, timeseries/*.json; uniform bucket-level access, public access prevention enforced) and use `ARTIFACTS_GCS_URI=gs://aibuildercup-511905-annadrishti/artifacts/v1`.
- ONI after JAS-2026 is an assumed IRI-style decay (see report). TimesFM has no real skill on district JJAS rainfall (hindcast corr -0.06..+0.26, no better than climatology RMSE) and median-of-month forecasts are biased low. Treat as a pattern signal, not a risk input.
