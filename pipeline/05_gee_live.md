# 05_gee_live - Earth Engine live signals

`python3 pipeline/05_gee_live.py` writes `artifacts/gee_live.json` (753 districts keyed by LGD code, null where unavailable) and `artifacts/reports/05_gee_report.md`.

Auth: user OAuth credentials (`~/.config/earthengine/credentials`), `ee.Initialize(project='ee-chvi')`.

## Fields (per district, spatial mean over the district polygon)

| field | meaning | source / method |
|---|---|---|
| `ndvi_anom` | Fractional NDVI anomaly: (current - normal) / normal. Negative = browner than normal. | MODIS MOD13Q1 v061 NDVI. Current = mean of composites in the 32 days ending at the latest composite; normal = mean of the same calendar window 2015-2024. 1 km reduce. Null if normal NDVI < 0.05. |
| `chirps_30d_mm` | Rain (mm) in the last 30 days ending at the latest CHIRPS day. | UCSB-CHG CHIRPS daily, 5566 m reduce. CHIRPS lags real time by ~2 weeks. |
| `chirps_30d_anom_pct` | % departure of that 30-day total from the 2001-2024 mean of the same window. | Null where the normal is < 5 mm (a % is meaningless). |
| `soilm_anom` | Absolute anomaly (m3/m3) of top-layer (0-7 cm) volumetric soil water for the latest month vs the 2001-2024 mean for that calendar month. | ERA5-Land monthly aggregates (SMAP SPL4SMGP/007 is deprecated/empty). Monthly, so it lags by up to ~6 weeks. |
| `wn_10d_rain_mm` | Forecast accumulated rain (mm) over the next 10 days (leads 6-240 h). | Google WeatherNext 2, ensemble mean of per-member totals. Source precip is in metres, converted to mm. |
| `wn_10d_tmax_c` | Forecast highest 2 m temperature (deg C) in the next 10 days. | Ensemble mean of per-member maxima. Based on 6-hourly instantaneous values, so it can understate the true daily maximum by 1-3 C. |
| `wn_init` | Forecast initialisation time (UTC) used. | Latest init with a complete run (all leads to 240 h). |

`sources` in the JSON records the exact windows, dates, asset id, and number of ensemble members used.

## WeatherNext asset choice
`weathernext_2_0_0` is used first. The older Gen (`126478713_1_0`) and Graph (`59572747_4_0`) assets are deprecated and stop at 2026-07-29, so they only act as fallbacks when WeatherNext 2 has no complete recent init.

## Refresh
Daily cron (e.g. 07:00 IST; WeatherNext inits at 00/06/12/18 UTC):
```
0 7 * * * cd /path/to/project && python3 pipeline/05_gee_live.py >> artifacts/_gee_cache/cron.log 2>&1
```
Layer results are cached as `artifacts/_gee_cache/{layer}_{YYYY-MM-DD}.json`; a rerun on the same day is instant. Force recompute with `--refresh`. Use `--wn-members N` to use only N evenly-spread ensemble members (default: all).
Old cache files are not pruned automatically.
