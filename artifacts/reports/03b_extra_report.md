# 03b extra sources report

## 1. ICRISAT farm-harvest prices

- File rows 18,662; 536 census-coded ICRISAT districts + 66 districts with code -1 (name match only). ICRISAT years 1990-2020.
- Master match: census code 536, state+name fallback 47, unmatched 170 (of 753).
- price series (>=8 valid yrs): 511 / 753; elnino spike: 474; volatility idx: 469
- price_crop counts: {'Paddy': 179, 'Wheat': 136, 'Rice': 84, 'Maize': 34, 'Chickpea': 22, 'Pearl Millet': 21, 'Sorghum': 18, 'Pigeonpea': 8, 'Finger Millet': 7, 'Barley': 2}
- price_elnino_spike_pct (pp): n=474 min=-67.33 p10=-16.32 p25=-9.87 med=-4.25 p75=0.79 p90=6.50 max=66.34 mean=-4.06
- price_volatility_idx: n=469 min=0.00 p10=0.10 p25=0.25 med=0.50 p75=0.75 p90=0.90 max=1.00 mean=0.50
- El Nino years used [2002, 2004, 2006, 2009, 2015]; neutral years from ONI helper (kharif-season mean ONI). Spike = mean % deviation from log-linear trend (El Nino) minus same (neutral); needs >=2 El Nino and >=3 neutral obs. Volatility = std of detrended log price (~CV of price around trend), 2000-2017, >=8 yrs, rank-normalised across districts.
- Chosen crop uses first of the district's top-5 APY crops that has an ICRISAT price series with >=8 yrs, else RICE then WHEAT.

## 2. Poshan Tracker

- Columns `severely_moderately_underweight`, `severely_or_moderately_stunted`, `wasting_sam_or_mam` are already percentages of children measured (0-100, mostly integer-rounded), NOT counts; used as-is. SAM is not published separately (only SAM+MAM combined) -> `poshan_sam_pct` all null, `poshan_wasted_pct` = SAM+MAM.
- Rows with usable lgd: 25,964 after filters (children_measured_0_5_years >= 500, underweight>0 and stunted>0 as 0 = unreported). Months 2023-04 to 2026-02.
- Master coverage: 748 / 753; wasted non-null 682; series non-null 748
- as_of distribution: {'2025-05-01': 1, '2025-06-01': 1, '2025-08-01': 1, '2025-09-01': 1, '2025-11-01': 1, '2026-02-01': 740} (older months = district stopped reporting >=500 valid)
- poshan_underweight_pct: n=748 min=1.00 p10=3.00 p25=6.00 med=10.00 p75=16.00 p90=20.00 max=44.00 mean=11.30
- poshan_stunted_pct: n=748 min=2.00 p10=9.00 p25=16.00 med=28.00 p75=37.00 p90=42.00 max=64.00 mean=26.89
- poshan_wasted_pct: n=682 min=1.00 p10=1.00 p25=2.00 med=3.00 p75=5.00 p90=8.00 max=15.00 mean=3.94
- poshan_measured: n=748 min=507.00 p10=11384.20 p25=35174.00 med=69025.00 p75=113055.25 p90=191521.10 max=751009.00 mean=87469.17
- vs NFHS-6 underweight: n=707 Pearson r=0.613, Spearman=0.608; mean Poshan 11.6 vs NFHS-6 29.5 (diff -17.9 pp)

## 3. Groundwater

- Depth = `currentlevel` (m below ground), pre-monsoon = Apr-Jun readings (median per station-year, then district median per year, need >=5 wells/yr); readings >300 m dropped as implausible. Latest year with >=5 wells used; trend = OLS slope over the last <=10 such years (need >=5). CGWB used where it yields a valid depth, else State Boards file.
- Coverage: depth 505 / 753 (CGWB 504, state boards 1); decline 483; stress idx (needs both) 483
- latest year distribution: {2013.0: 1, 2014.0: 1, 2015.0: 3, 2016.0: 4, 2017.0: 3, 2018.0: 11, 2019.0: 482}
- gw_premonsoon_depth_m: n=505 min=0.50 p10=4.29 p25=6.02 med=7.93 p75=10.42 p90=14.54 max=93.10 mean=9.51
- gw_decline_10y_m_per_yr (+ = deepening): n=483 min=-3.01 p10=-0.26 p25=-0.07 med=0.09 p75=0.30 p90=0.50 max=2.94 mean=0.12
- gw_stress_idx: n=483 min=0.00 p10=0.10 p25=0.25 med=0.50 p75=0.75 p90=0.90 max=1.00 mean=0.50 (depth winsorised p99, decline winsorised p1/p99 before z-scoring; rank-normalised 0-1)

## 4. Cost of cultivation

- State x crop rows 225 (latest year per pair, >= 2014); all CoC states match master state names.
- coc_json non-null 616 / 753; crops matched per district: {1: 9, 2: 34, 3: 81, 4: 207, 5: 285}
- coc_drought_tolerant_json non-null 506 / 753 (Horse Gram and Castor are not in the CoC file; Bajra/Jowar/Ragi/Moong only where the state surveyed them).
- margin = main_product_value - cul_cost_c2 (Rs/ha, nominal, excludes by-product value and uses full C2 cost incl. imputed family labour/land rent so it is a conservative economic margin); yield_q_ha = derived_yield (quintal/ha; sugarcane/tubers on fresh-weight basis).

## Coverage summary (non-null of 753)

```
price_crop                    511
price_n_years                 511
price_match                   753
price_elnino_spike_pct        474
price_volatility_idx          469
price_series_json             511
poshan_underweight_pct        748
poshan_stunted_pct            748
poshan_wasted_pct             682
poshan_sam_pct                  0
poshan_as_of                  748
poshan_measured               748
poshan_series_json            748
gw_premonsoon_depth_m         505
gw_decline_10y_m_per_yr       483
gw_stress_idx                 483
gw_latest_year                505
gw_n_wells                    505
gw_n_years_trend              483
gw_source                     505
coc_json                      616
coc_drought_tolerant_json     506
```

## Sample districts

### 486 Nandurbar, Maharashtra
- price_crop: Maize
- price_n_years: 13
- price_match: census_code
- price_elnino_spike_pct: -5.48
- price_volatility_idx: 0.9209
- price_series_json: {"2000":560.0,"2001":546.0,"2002":559.0,"2003":545.0,"2005":560.0,"2006":500.0,"2007":495.0,"2008":779.0,"2009":890.0,"2015":2000.0,"2016":2011.0,"2019":3000.0,"2020":3500.0}
- poshan_underweight_pct: 42.0
- poshan_stunted_pct: 62.0
- poshan_wasted_pct: 7.0
- poshan_sam_pct: None
- poshan_as_of: 2026-02-01
- poshan_measured: 117411
- poshan_series_json: {"2024-03":44.0,"2024-04":45.0,"2024-05":45.0,"2024-06":48.0,"2024-07":49.0,"2024-08":49.0,"2024-09":48.0,"2024-10":47.0,"2024-11":46.0,"2024-12":44.0,"2025-01":42.0,"2025-02":42.0,"2025-03":43.0,"2025-04":46.0,"2025-05":48.0,"2025-06":49.0,"2025-07":48.0,"2025-08":47.0,"2025-09":46.0,"2025-10":45.0,"2025-11":44.0,"2025-12":42.0,"2026-01":42.0,"2026-02":42.0}
- gw_premonsoon_depth_m: 10.99
- gw_decline_10y_m_per_yr: 0.445
- gw_stress_idx: 0.861
- gw_latest_year: 2019
- gw_n_wells: 27
- gw_n_years_trend: 7
- gw_source: CGWB
- coc_json: [{"crop":"Cotton","year":"2021-22","cost_c2_per_ha":94710,"value_per_ha":86267,"margin_per_ha":-8443,"yield_q_ha":12.7},{"crop":"Maize","year":"2021-22","cost_c2_per_ha":92343,"value_per_ha":100572,"margin_per_ha":8229,"yield_q_ha":57.0},{"crop":"Soybean","year":"2021-22","cost_c2_per_ha":69905,"value_per_ha":80453,"margin_per_ha":10547,"yield_q_ha":16.1},{"crop":"Jowar","year":"2021-22","cost_c2_...
- coc_drought_tolerant_json: [{"crop":"Bajra","year":"2021-22","cost_c2_per_ha":72926,"value_per_ha":52842,"margin_per_ha":-20084,"yield_q_ha":26.3},{"crop":"Jowar","year":"2021-22","cost_c2_per_ha":51537,"value_per_ha":30440,"margin_per_ha":-21097,"yield_q_ha":10.8},{"crop":"Ragi","year":"2019-20","cost_c2_per_ha":67389,"value_per_ha":30295,"margin_per_ha":-37095,"yield_q_ha":10.4},{"crop":"Moong","year":"2021-22","cost_c2_p...

### 358 Kalahandi, Odisha
- price_crop: Paddy
- price_n_years: 30
- price_match: census_code
- price_elnino_spike_pct: -5.72
- price_volatility_idx: 0.562
- price_series_json: {"1990":161.0,"1991":173.0,"1992":175.0,"1993":200.0,"1994":310.0,"1995":352.0,"1996":353.0,"1997":413.0,"1998":397.0,"1999":363.0,"2000":422.0,"2001":407.0,"2002":381.0,"2003":409.0,"2004":421.0,"2005":458.0,"2006":466.0,"2007":684.0,"2008":857.0,"2009":927.0,"2010":906.0,"2011":1002.0,"2012":1103.0,"2014":1307.0,"2015":1435.0,"2016":1444.0,"2017":1570.0,"2018":1453.0,"2019":1679.0,"2020":1510.0}
- poshan_underweight_pct: 12.0
- poshan_stunted_pct: 31.0
- poshan_wasted_pct: 3.0
- poshan_sam_pct: None
- poshan_as_of: 2026-02-01
- poshan_measured: 114829
- poshan_series_json: {"2024-03":18.0,"2024-04":19.0,"2024-05":18.0,"2024-06":15.0,"2024-07":14.0,"2024-08":15.0,"2024-09":16.0,"2024-10":15.0,"2024-11":14.0,"2024-12":14.0,"2025-01":14.0,"2025-02":13.0,"2025-03":13.0,"2025-04":12.0,"2025-05":12.0,"2025-06":13.0,"2025-07":12.0,"2025-08":12.0,"2025-09":12.0,"2025-10":12.0,"2025-11":12.0,"2025-12":12.0,"2026-01":13.0,"2026-02":12.0}
- gw_premonsoon_depth_m: 4.74
- gw_decline_10y_m_per_yr: -0.015
- gw_stress_idx: 0.1909
- gw_latest_year: 2019
- gw_n_wells: 30
- gw_n_years_trend: 7
- gw_source: CGWB
- coc_json: [{"crop":"Rice","year":"2021-22","cost_c2_per_ha":71291,"value_per_ha":57561,"margin_per_ha":-13730,"yield_q_ha":40.5},{"crop":"Moong","year":"2021-22","cost_c2_per_ha":25403,"value_per_ha":29620,"margin_per_ha":4217,"yield_q_ha":4.1},{"crop":"Urad","year":"2021-22","cost_c2_per_ha":24660,"value_per_ha":25792,"margin_per_ha":1133,"yield_q_ha":3.5},{"crop":"Groundnut","year":"2021-22","cost_c2_per_...
- coc_drought_tolerant_json: [{"crop":"Ragi","year":"2021-22","cost_c2_per_ha":41293,"value_per_ha":26510,"margin_per_ha":-14783,"yield_q_ha":8.7},{"crop":"Moong","year":"2021-22","cost_c2_per_ha":25403,"value_per_ha":29620,"margin_per_ha":4217,"yield_q_ha":4.1}]

### 191 Begusarai, Bihar
- price_crop: Maize
- price_n_years: 30
- price_match: census_code
- price_elnino_spike_pct: -9.42
- price_volatility_idx: 0.5534
- price_series_json: {"1990":269.0,"1991":264.0,"1992":289.0,"1993":313.0,"1994":335.0,"1995":322.0,"1996":358.0,"1997":395.0,"1998":398.0,"1999":457.0,"2000":356.0,"2001":395.0,"2002":493.0,"2003":403.0,"2004":475.0,"2006":514.0,"2007":575.0,"2008":616.0,"2009":700.0,"2010":950.0,"2011":904.0,"2012":1185.0,"2013":1109.0,"2014":1009.0,"2015":1044.0,"2016":1141.0,"2017":1118.5,"2018":1161.7,"2019":1290.3,"2020":1363.7}
- poshan_underweight_pct: 18.0
- poshan_stunted_pct: 42.0
- poshan_wasted_pct: 7.0
- poshan_sam_pct: None
- poshan_as_of: 2026-02-01
- poshan_measured: 241098
- poshan_series_json: {"2024-03":18.0,"2024-04":18.0,"2024-05":18.0,"2024-06":19.0,"2024-07":20.0,"2024-08":20.0,"2024-09":21.0,"2024-10":21.0,"2024-11":20.0,"2024-12":21.0,"2025-01":21.0,"2025-02":21.0,"2025-03":21.0,"2025-04":21.0,"2025-05":22.0,"2025-06":22.0,"2025-07":22.0,"2025-08":22.0,"2025-09":22.0,"2025-10":22.0,"2025-11":22.0,"2025-12":22.0,"2026-01":20.0,"2026-02":18.0}
- gw_premonsoon_depth_m: 7.32
- gw_decline_10y_m_per_yr: -0.117
- gw_stress_idx: 0.2469
- gw_latest_year: 2019
- gw_n_wells: 24
- gw_n_years_trend: 7
- gw_source: CGWB
- coc_json: [{"crop":"Maize","year":"2021-22","cost_c2_per_ha":64075,"value_per_ha":79757,"margin_per_ha":15682,"yield_q_ha":46.1},{"crop":"Wheat","year":"2021-22","cost_c2_per_ha":61056,"value_per_ha":55759,"margin_per_ha":-5297,"yield_q_ha":29.3},{"crop":"Rice","year":"2021-22","cost_c2_per_ha":54311,"value_per_ha":39683,"margin_per_ha":-14628,"yield_q_ha":28.6},{"crop":"Rapeseed & Mustard","year":"2021-22"...
- coc_drought_tolerant_json: [{"crop":"Moong","year":"2019-20","cost_c2_per_ha":23991,"value_per_ha":47942,"margin_per_ha":23951,"yield_q_ha":8.0}]

### 673 Morbi, Gujarat
- price_crop: None
- price_n_years: None
- price_match: name
- price_elnino_spike_pct: None
- price_volatility_idx: None
- price_series_json: None
- poshan_underweight_pct: 10.0
- poshan_stunted_pct: 22.0
- poshan_wasted_pct: 3.0
- poshan_sam_pct: None
- poshan_as_of: 2026-02-01
- poshan_measured: 50045
- poshan_series_json: {"2024-02":11.0,"2024-04":11.0,"2024-05":11.0,"2024-06":12.0,"2024-07":12.0,"2024-08":13.0,"2024-09":13.0,"2024-10":12.0,"2024-11":14.0,"2024-12":14.0,"2025-01":14.0,"2025-02":14.0,"2025-03":14.0,"2025-04":14.0,"2025-05":14.0,"2025-06":15.0,"2025-07":16.0,"2025-08":16.0,"2025-09":16.0,"2025-10":16.0,"2025-11":14.0,"2025-12":12.0,"2026-01":10.0,"2026-02":10.0}
- gw_premonsoon_depth_m: None
- gw_decline_10y_m_per_yr: None
- gw_stress_idx: None
- gw_latest_year: None
- gw_n_wells: None
- gw_n_years_trend: None
- gw_source: None
- coc_json: [{"crop":"Cotton","year":"2021-22","cost_c2_per_ha":90293,"value_per_ha":116910,"margin_per_ha":26616,"yield_q_ha":14.8},{"crop":"Groundnut","year":"2021-22","cost_c2_per_ha":91647,"value_per_ha":89787,"margin_per_ha":-1860,"yield_q_ha":16.5},{"crop":"Wheat","year":"2021-22","cost_c2_per_ha":55176,"value_per_ha":73117,"margin_per_ha":17940,"yield_q_ha":32.5},{"crop":"Sesamum","year":"2021-22","cos...
- coc_drought_tolerant_json: [{"crop":"Bajra","year":"2021-22","cost_c2_per_ha":68296,"value_per_ha":57562,"margin_per_ha":-10735,"yield_q_ha":27.7},{"crop":"Moong","year":"2021-22","cost_c2_per_ha":40381,"value_per_ha":42693,"margin_per_ha":2312,"yield_q_ha":6.6}]

### 502 Anantpur, Andhra Pradesh
- price_crop: Pigeonpea
- price_n_years: 31
- price_match: census_code
- price_elnino_spike_pct: 20.45
- price_volatility_idx: 0.8868
- price_series_json: {"1990":689.0,"1991":805.0,"1992":806.0,"1993":805.0,"1994":1100.0,"1995":1274.0,"1996":1325.0,"1997":1312.0,"1998":1117.0,"1999":1253.0,"2000":1160.0,"2001":1235.0,"2002":1508.0,"2003":1650.0,"2004":1458.0,"2005":1383.0,"2006":1889.0,"2007":2024.0,"2008":2468.0,"2009":3417.0,"2010":3040.0,"2011":2886.0,"2012":3199.0,"2013":3170.0,"2014":4530.0,"2015":7503.0,"2016":4069.0,"2017":4145.0,"2018":4340...
- poshan_underweight_pct: 4.0
- poshan_stunted_pct: 7.0
- poshan_wasted_pct: 2.0
- poshan_sam_pct: None
- poshan_as_of: 2026-02-01
- poshan_measured: 116578
- poshan_series_json: {"2024-03":11.0,"2024-04":11.0,"2024-05":12.0,"2024-06":12.0,"2024-07":12.0,"2024-08":12.0,"2024-09":12.0,"2024-10":12.0,"2024-11":12.0,"2024-12":12.0,"2025-01":10.0,"2025-02":8.0,"2025-03":8.0,"2025-04":8.0,"2025-05":8.0,"2025-06":8.0,"2025-07":8.0,"2025-08":8.0,"2025-09":8.0,"2025-10":5.0,"2025-11":4.0,"2025-12":5.0,"2026-01":4.0,"2026-02":4.0}
- gw_premonsoon_depth_m: 12.26
- gw_decline_10y_m_per_yr: 0.372
- gw_stress_idx: 0.8714
- gw_latest_year: 2019
- gw_n_wells: 47
- gw_n_years_trend: 7
- gw_source: CGWB
- coc_json: [{"crop":"Groundnut","year":"2021-22","cost_c2_per_ha":83444,"value_per_ha":51903,"margin_per_ha":-31541,"yield_q_ha":9.8},{"crop":"Tur","year":"2021-22","cost_c2_per_ha":42564,"value_per_ha":41549,"margin_per_ha":-1015,"yield_q_ha":6.4},{"crop":"Gram","year":"2021-22","cost_c2_per_ha":66887,"value_per_ha":92467,"margin_per_ha":25580,"yield_q_ha":16.2},{"crop":"Cotton","year":"2021-22","cost_c2_pe...
- coc_drought_tolerant_json: [{"crop":"Jowar","year":"2021-22","cost_c2_per_ha":98399,"value_per_ha":138415,"margin_per_ha":40016,"yield_q_ha":47.3},{"crop":"Moong","year":"2021-22","cost_c2_per_ha":41854,"value_per_ha":44158,"margin_per_ha":2305,"yield_q_ha":7.0}]

## Caveats

- ICRISAT (unapportioned, ~537 districts) ends 2020 and predates new districts; new/split districts only match by name, others stay null (no parent inheritance). Prices are nominal; the log-linear trend absorbs inflation. Price crop varies by district, so volatility ranks are across mixed crops.
- Poshan percentages are integer-rounded administrative (AWC-measured) values; self-reported coverage varies, and Poshan reads lower than NFHS survey. Use as a trend/live signal, not level-comparable to NFHS. SAM alone is unavailable.
- Groundwater: CGWB coverage collapses after 2020, so many districts' 'latest' year is 2019-21; district median over a changing well panel can alias composition change into the trend; state-board wells may use different datum conventions.
- CoC is state-level (not district), latest year 2021-22 at best, nominal Rs; use as relative economics, not district-specific truth.