# 05_gee_live report

Generated 2026-10-17T16:20:10 - as_of 2026-10-17 - runtime of this invocation 13s (cache hit). Full uncached run: 549s (ndvi 36s, chirps 32s, soilm 29s, WeatherNext 2 with all 64 members 439s). Note: the next uncached run overwrites this line with its own runtime.

## Coverage and India-wide (unweighted district) stats
| field | non-null | mean | median | min | max |
|---|---|---|---|---|---|
| ndvi_anom | 753/753 | 0.089 | 0.086 | -0.205 | 0.435 |
| chirps_30d_mm | 753/753 | 197.937 | 183.100 | 11.000 | 542.900 |
| chirps_30d_anom_pct | 753/753 | -4.607 | -11.300 | -84.500 | 188.100 |
| soilm_anom | 752/753 | -0.019 | -0.007 | -0.191 | 0.065 |
| wn_10d_rain_mm | 753/753 | 16.487 | 1.700 | 0.000 | 168.400 |
| wn_10d_tmax_c | 753/753 | 29.460 | 30.800 | -4.500 | 36.700 |
| wn_init | 753/753 | - | - | - | - |

## WeatherNext
{
  "dataset": "projects/gcp-public-data-weathernext/assets/weathernext_2_0_0",
  "model": "WeatherNext 2",
  "asset": "projects/gcp-public-data-weathernext/assets/weathernext_2_0_0",
  "init": "2026-10-17T00:00:00Z",
  "lead_hours": [
    6,
    240
  ],
  "members_used": 64,
  "aggregation": "mean over members of per-member (sum of precip leads<=240h; max of 6h-instantaneous 2m T)"
}

## Other sources
```
{
  "ndvi_anom": {
    "dataset": "MODIS/061/MOD13Q1 NDVI",
    "units": "fraction vs mean",
    "latest_composite": "2026-09-14",
    "window": [
      "2026-08-14",
      "2026-09-14"
    ],
    "clim_years": "2015-2024",
    "note": "(latest 32-day mean - same-window mean 2015-2024)/same-window mean; 1 km reduce"
  },
  "chirps_30d": {
    "dataset": "UCSB-CHG/CHIRPS/DAILY precipitation",
    "window": [
      "2026-09-01",
      "2026-09-30"
    ],
    "clim_years": "2001-2024",
    "note": "30-day sum (mm) and % anomaly vs same window mean 2001-2024; anom null where climatology < 5 mm"
  },
  "soilm_anom": {
    "dataset": "ECMWF/ERA5_LAND/MONTHLY_AGGR volumetric_soil_water_layer_1",
    "month": "2026-09",
    "clim_years": "2001-2024",
    "units": "m3/m3 (absolute anomaly)",
    "note": "SMAP SPL4SMGP/007 deprecated/empty; ERA5-Land used instead"
  }
}
```

## Sample districts
| lgd | district | ndvi_anom | chirps_30d_mm | chirps_30d_anom_pct | soilm_anom | wn_10d_rain_mm | wn_10d_tmax_c |
|---|---|---|---|---|---|---|---|
| 486 | Nandurbar (Maharashtra) | 0.0306 | 123.4 | -41.2 | -0.0278 | 1.9 | 33.1 |
| 673 | Morbi (Gujarat) | 0.0697 | 121.1 | -2.9 | -0.0261 | 0.0 | 35.8 |
| 191 | Begusarai (Bihar) | 0.0188 | 151.5 | -31.3 | 0.0151 | 1.6 | 30.7 |
| 502 | Anantpur (Andhra Pradesh) | -0.0014 | 120.8 | -4.8 | -0.1244 | 25.1 | 32.2 |
| 441 | Banas Kantha (Gujarat) | 0.0968 | 131.4 | -11.6 | -0.0294 | 0.1 | 34.7 |
