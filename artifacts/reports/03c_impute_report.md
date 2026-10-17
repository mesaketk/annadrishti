# 03c impute report

Run 2026-10-17 | 417 of 753 districts have at least one imputed field; 2552 (district, field) entries; Earth Engine used.

Observed values are never overwritten: `04_risk.py` / `06_export.py` fill only where the source layer is null. Every entry is flagged in `data_quality.imputed` (SCHEMA Addendum G).

## Imputed entries by field and source

| field (schema path) | imputed | sources |
|---|---|---|
| `markets.price_volatility_idx` | 284 | neighbours_knn 177, national_median 84, parent_inherit 17, neighbours_2hop 6 |
| `markets.price_elnino_spike_pct` | 279 | neighbours_knn 174, national_median 87, parent_inherit 17, neighbours_2hop 1 |
| `groundwater.decline_m_per_yr` | 270 | national_median 124, neighbours_knn 114, parent_inherit 16, neighbours_2hop 12, state_median 4 |
| `groundwater.stress_idx` | 270 | national_median 124, neighbours_knn 114, parent_inherit 16, neighbours_2hop 12, state_median 4 |
| `groundwater.premonsoon_depth_m` | 248 | national_median 124, neighbours_knn 93, parent_inherit 16, neighbours_2hop 11, state_median 4 |
| `climate.clim_vuln_index` | 120 | neighbours_knn 90, parent_inherit 16, national_median 7, neighbours_2hop 7 |
| `crops.small_marginal_share` | 89 | neighbours_knn 63, parent_inherit 26 |
| `food_balance.pds_dependency` | 81 | neighbours_knn 46, parent_inherit 22, national_median 13 |
| `nutrition.poshan_live.wasted_pct` | 71 | neighbours_knn 58, neighbours_2hop 8, national_median 2, parent_inherit 2, state_median 1 |
| `nutrition.nfhs5.stunting` | 49 | parent_inherit 25, state_ratio_nfhs6 17, neighbours_knn 6, national_median 1 |
| `nutrition.nfhs5.wasting` | 49 | parent_inherit 25, state_ratio_nfhs6 17, neighbours_knn 6, national_median 1 |
| `nutrition.nfhs5.underweight` | 49 | parent_inherit 25, state_ratio_nfhs6 17, neighbours_knn 6, national_median 1 |
| `nutrition.nfhs5.child_anaemia` | 49 | parent_inherit 26, neighbours_knn 22, national_median 1 |
| `nutrition.nfhs5.women_anaemia` | 49 | parent_inherit 26, neighbours_knn 22, national_median 1 |
| `nutrition.nfhs5.women_bmi_low` | 49 | parent_inherit 25, state_ratio_nfhs6 17, neighbours_knn 6, national_median 1 |
| `nutrition.nfhs5.severe_wasting` | 49 | parent_inherit 25, state_ratio_nfhs6 17, neighbours_knn 6, national_median 1 |
| `nutrition.nfhs6.stunting` | 43 | parent_inherit 18, state_ratio_nfhs5 17, neighbours_knn 8 |
| `nutrition.nfhs6.wasting` | 43 | parent_inherit 18, state_ratio_nfhs5 17, neighbours_knn 8 |
| `nutrition.nfhs6.underweight` | 43 | parent_inherit 18, state_ratio_nfhs5 17, neighbours_knn 8 |
| `nutrition.nfhs6.women_bmi_low` | 43 | parent_inherit 18, state_ratio_nfhs5 17, neighbours_knn 8 |
| `nutrition.nfhs6.severe_wasting` | 43 | parent_inherit 18, state_ratio_nfhs5 17, neighbours_knn 8 |
| `crops.yield_cv10` | 36 | parent_inherit 26, neighbours_knn 10 |
| `season_context.rabi.foodgrain_prod_t` | 23 | ee_rabi_ndvi 14, parent_split_area_share 9 |
| `season_context.rabi.share_of_foodgrain_prod` | 23 | ee_rabi_ndvi 14, parent_split_area_share 9 |
| `population_2011` | 22 | ee_worldpop 22 |
| `population_2026` | 22 | ee_worldpop 22 |
| `children_u5_est` | 22 | ee_worldpop 22 |
| `crops.rainfed_share` | 13 | parent_inherit 10, neighbours_knn 3 |
| `crops.irrigated_share` | 13 | parent_inherit 10, neighbours_knn 3 |
| `crops.simpson_div` | 9 | parent_inherit 9 |
| `crops.top_crop_share` | 9 | parent_inherit 9 |
| `crops.foodgrain_prod_t` | 9 | parent_split_area_share 9 |
| `crops.gross_cropped_area_ha` | 9 | parent_split_area_share 9 |
| `crops.foodgrain_yield_t_ha` | 9 | parent_inherit 9 |
| `crops` | 9 | parent_split_area_share 9 |
| `nutrition.poshan_live.underweight_pct` | 5 | neighbours_knn 5 |
| `nutrition.poshan_live.stunted_pct` | 5 | neighbours_knn 5 |
| `climate.jjas_normal_mm` | 4 | ee_chirps 4 |
| `climate.elnino_mean_anomaly_pct` | 4 | ee_chirps 4 |
| `climate.neutral_mean_anomaly_pct` | 4 | ee_chirps 4 |
| `climate.lanina_mean_anomaly_pct` | 4 | ee_chirps 4 |
| `climate.strong_elnino_anomaly_pct` | 4 | ee_chirps 4 |
| `climate.elnino_deficit_prob` | 4 | ee_chirps 4 |
| `climate.jjas_anomaly_pct` | 4 | ee_chirps 4 |
| `climate.ond_anomaly_pct` | 4 | ee_chirps 4 |
| `climate.latest_year_anomaly_pct` | 4 | ee_chirps 4 |
| `climate.latest_year` | 4 | ee_chirps 4 |
| `climate` | 4 | ee_chirps 4 |

## Methods and validation

### 1. Neighbour method (adjacency: polygons touching within 500 m, `artifacts/_adjacency.json`)

Donors are districts with an OBSERVED value; median weighted by shared border length (simple mean when <= 2 donors); order: touching same state -> touching any state -> 2-hop same state -> state median (>= 3 donors) -> national median. Mean 5.5 touching districts; no touching donors (island): Lakshadweep, Nicobars.

Leave-one-out check (each observed district masked in turn and re-estimated from its neighbours; `pct_knn` = share estimated from touching districts). MAE of the neighbour estimate vs the state-median and national-median baselines:

| field | n | Spearman rho | MAE neighbours | MAE state median | MAE national median | pct touching |
|---|---|---|---|---|---|---|
| stunting_nfhs5 | 450 | 0.67 | 5.25 | 5.57 | 7.12 | 100% |
| wasting_nfhs5 | 450 | 0.54 | 4.38 | 3.98 | 4.91 | 100% |
| underweight_nfhs5 | 450 | 0.78 | 4.59 | 5.15 | 7.73 | 100% |
| child_anaemia_nfhs5 | 450 | 0.62 | 6.22 | 7.08 | 9.1 | 100% |
| stunting_nfhs6 | 450 | 0.73 | 4.4 | 5.33 | 6.52 | 100% |
| women_bmi_low_nfhs6 | 450 | 0.89 | 2.87 | 3.66 | 6.76 | 100% |
| rainfed_share | 450 | 0.83 | 0.118 | 0.137 | 0.261 | 100% |
| small_marginal_share | 450 | 0.90 | 0.0499 | 0.0682 | 0.131 | 99% |
| yield_cv10 | 450 | 0.76 | 0.0509 | 0.0565 | 0.082 | 100% |
| top_crop_share | 450 | 0.76 | 0.0971 | 0.123 | 0.172 | 100% |
| simpson_div | 450 | 0.77 | 0.0994 | 0.128 | 0.173 | 100% |
| price_volatility_idx | 450 | 0.51 | 0.206 | 0.203 | 0.252 | 99% |
| price_elnino_spike_pct | 450 | 0.51 | 7.65 | 6.56 | 7.9 | 99% |
| gw_premonsoon_depth_m | 450 | 0.67 | 2.86 | 3.34 | 3.85 | 99% |
| gw_decline_10y_m_per_yr | 450 | 0.38 | 0.295 | 0.285 | 0.288 | 99% |
| gw_stress_idx | 450 | 0.49 | 0.196 | 0.215 | 0.253 | 99% |
| poshan_underweight_pct | 450 | 0.83 | 2.92 | 3.09 | 5.71 | 100% |
| clim_vuln_index | 450 | 0.71 | 0.0372 | 0.0386 | 0.0581 | 100% |
| pds_per_person_t | 450 | 0.64 | 0.00755 | 0.00722 | 0.0091 | 100% |

Read: rho well above 0 and MAE below the baselines = neighbours carry information (nutrition, rainfed share, groundwater); rho near 0 / no gain over the state median = the layer is spatially noisy (price indices, yield CV, top-crop share) - those imputations are close to a regional median and should be read as 'typical for the area', not as local estimates.

### 2. Population: WorldPop 2020 (Earth Engine `WorldPop/GP/100m/pop`, sum per polygon)

Cross-check on 702 districts (not split parents/children; census 2011 x state factor^(9/15) = census-based 2020): Pearson r = 0.982 (log-log 0.986); vs census-based 2026 (WorldPop x state factor^(6/15)): log-log r = 0.986; median ratio WorldPop-2020 / census-2020 = 0.900 (p10 0.80, p90 1.03); median ratio WorldPop-2026 / census-2026 = 0.900. All-India WorldPop sum 1210.9 M (polygons incl. split children; PoK excluded).

22 districts had no census population (22 post-2011 districts): population_2011 = WorldPop / g^(9/15), population_2026 = WorldPop x g^(6/15) with g = state 2026/2011 factor. WorldPop is scaled by the state median census/WorldPop ratio (national 1.111 where a state has < 5 comparable districts) before use: median WorldPop/census after calibration 1.000. Columns `worldpop_2020` (raw) and `worldpop_2020_calibrated` are in `imputed_district.parquet` for ALL districts.

Validation of the parent area-share split (method 2) against WorldPop for the split children (parent census 2026 x area share vs WorldPop 2026):

| district | parent | WorldPop 2026 | parent x area share | census 2026 (if any) | area-share / WorldPop |
|---|---|---|---|---|---|
| Kakching | Thoubal | 186,711 | 135,244 | 147,465 | 0.72 |
| Jiribam | Imphal East | 52,142 | 187,287 | 50,822 | 3.59 |
| Noney | Tamenglong | 56,768 | 26,794 | 48,982 | 0.47 |
| Pherzawl | Churachandpur | 57,113 | 125,470 | 46,825 | 2.20 |
| Tengnoupal | Chandel | 78,956 | 37,781 | 68,794 | 0.48 |
| Kamjong | Ukhrul | 65,995 | 76,000 | 53,619 | 1.15 |
| Mayiladuthurai | Nagapattinam | 994,446 | 795,063 |  | 0.80 |
| Noklak | Tuensang | 68,628 | 105,894 |  | 1.54 |
| Malerkotla | Sangrur | 491,812 | 353,306 |  | 0.72 |
| Vijayanagar | Ballari | 1,229,969 | 1,542,817 |  | 1.25 |
| Bajali | Barpeta | 242,218 | 310,353 |  | 1.28 |
| Eastern West Khasi Hills | West Khasi Hills | 157,689 | 108,928 |  | 0.69 |
| Parvathipuram Manyam | Vizianagaram | 998,110 | 1,208,982 |  | 1.21 |
| Anakapalli | Visakhapatnam | 2,113,880 | 1,026,221 |  | 0.49 |
| Alluri Sitharama Raju | Visakhapatnam | 1,003,636 | 3,226,364 |  | 3.21 |
| Kakinada | East Godavari | 2,145,461 | 2,172,429 |  | 1.01 |
| Konaseema | East Godavari | 1,805,873 | 1,699,908 |  | 0.94 |
| Eluru | West Godavari | 2,078,768 | 3,270,311 |  | 1.57 |
| NTR | Krishna | 2,235,642 | 2,257,896 |  | 1.01 |
| Bapatla | Guntur | 1,639,694 | 1,509,735 |  | 0.92 |
| Palnadu | Guntur | 2,307,241 | 2,835,497 |  | 1.23 |
| Tirupati | Chittoor | 2,412,275 | 2,524,147 |  | 1.05 |
| Annamayya | Y.S.R. | 1,833,565 | 1,462,308 |  | 0.80 |
| Sri Sathya sai | Anantpur | 2,041,303 | 2,070,880 |  | 1.01 |
| Nandyal | Kurnool | 1,979,445 | 2,411,626 |  | 1.22 |

Median area-share / WorldPop = 1.01 (spread p10-p90 0.57-1.95): area share is a poor proxy for population share (hill vs plain split), which is why WorldPop is preferred for population and the area-share rule is used only for crop quantities.

### 3. Rabi cropping intensity (MODIS MOD13Q1 NDVI x WorldCover v200 cropland)

Index = mean over winters 2021-22..2024-25 of [Dec-Feb mean NDVI - Sep-Oct minimum NDVI], cropland-fraction weighted per district, rescaled to 0-1 between the 2nd and 98th percentile (`rabi_ndvi_intensity`, all districts). Linear map `rabi area share = 0.265 + 0.392 x intensity` fitted on 547 districts with trustworthy APY rabi shares (= the rabi-eligible set): **R2 = 0.24** (5-fold CV R2 0.23, RMSE 0.191, Spearman 0.52); winter-mean-only index R2 0.19 (CV 0.18).

Imputed rabi structure: 14 season-label-gap districts get max(APY share, NDVI estimate) (APY under-reports rabi where the season labels are missing); the 159 negligible-rabi districts keep their small but measured APY rabi area (an R2 of 0.24 cannot overrule it; the map's intercept alone gives 27%); their NDVI intensity is stored for reference. Rabi production share is set equal to the area share (rabi/kharif yields are not separable for these districts).

Season-label-gap districts:

| district | state | APY rabi share | NDVI intensity | imputed share | method |
|---|---|---|---|---|---|
| Anugul | Odisha | 0.09 | 0.19 | 0.34 | ee_rabi_ndvi |
| Balangir | Odisha | 0.09 | 0.18 | 0.33 | ee_rabi_ndvi |
| Baudh | Odisha | 0.07 | 0.04 | 0.28 | ee_rabi_ndvi |
| Dhenkanal | Odisha | 0.06 | 0.10 | 0.30 | ee_rabi_ndvi |
| Jharsuguda | Odisha | 0.06 | 0.15 | 0.32 | ee_rabi_ndvi |
| Kalahandi | Odisha | 0.11 | 0.11 | 0.31 | ee_rabi_ndvi |
| Kendujhar | Odisha | 0.06 | 0.09 | 0.30 | ee_rabi_ndvi |
| Koraput | Odisha | 0.08 | 0.29 | 0.38 | ee_rabi_ndvi |
| Nuapada | Odisha | 0.09 | 0.12 | 0.31 | ee_rabi_ndvi |
| Rayagada | Odisha | 0.05 | 0.15 | 0.33 | ee_rabi_ndvi |
| Dadra & Nagar Haveli | Dadra,Nagar Haveli,Daman & Diu | 0.18 | 0.30 | 0.38 | ee_rabi_ndvi |
| Alappuzha | Kerala | 0.34 | 0.98 | 0.65 | ee_rabi_ndvi |
| Kottayam | Kerala | 0.44 | 0.88 | 0.61 | ee_rabi_ndvi |
| Thrissur | Kerala | 0.51 | 1.00 | 0.66 | ee_rabi_ndvi |

### 4. Island climate (CHIRPS v2 daily, JJAS and OND sums 2000-2025, polygons buffered 0.1 deg)

Districts without IMD cells: Lakshadweep, South Andaman, Nicobars, North  & Middle Andaman. CHIRPS normal = 2000-2024 mean, anomalies as in 02_climate; temperature layers stay null (rabi terminal-heat term dropped for them).

CHIRPS vs IMD, yearly JJAS anomaly over 40 sample districts: mean r = 0.58 (median 0.68), mean abs diff 17.7 pp (IMD vs CHIRPS differ most for the small-polygon / mountain districts).

### 5. Parent inheritance (post-2011 splits; polygons are post-split, parents shrank, nothing overlaps)

| child | parent | area share of pre-split territory |
|---|---|---|
| Kakching | Thoubal | 0.45 |
| Kangpokpi | Senapati | 0.50 |
| Jiribam | Imphal East | 0.41 |
| Noney | Tamenglong | 0.28 |
| Pherzawl | Churachandpur | 0.47 |
| Tengnoupal | Chandel | 0.38 |
| Kamjong | Ukhrul | 0.53 |
| Mayiladuthurai | Nagapattinam | 0.46 |
| Noklak | Tuensang | 0.47 |
| Malerkotla | Sangrur | 0.19 |
| Vijayanagar | Ballari | 0.50 |
| Bajali | Barpeta | 0.16 |
| Eastern West Khasi Hills | West Khasi Hills | 0.33 |
| Parvathipuram Manyam | Vizianagaram | 0.48 |
| Anakapalli | Visakhapatnam | 0.23 |
| Alluri Sitharama Raju | Visakhapatnam | 0.72 |
| Kakinada | East Godavari | 0.38 |
| Konaseema | East Godavari | 0.30 |
| Eluru | West Godavari | 0.76 |
| NTR | Krishna | 0.46 |
| Bapatla | Guntur | 0.29 |
| Palnadu | Guntur | 0.54 |
| Tirupati | Chittoor | 0.56 |
| Annamayya | Y.S.R. | 0.47 |
| Sri Sathya sai | Anantpur | 0.47 |
| Nandyal | Kurnool | 0.55 |

Ratio fields (NFHS, shares, prices, groundwater) are inherited; absolute fields (foodgrain production / area, gross cropped area, rabi structure) = parent x area share and only for the split children that have no crop data of their own. Parents are NOT reduced: their census population / crop totals remain the pre-split values (known caveat, unchanged).

### 6. Consumption side (declared here, scored in 04_risk.py)

24 districts: Central, Chandigarh, Chennai, East, Hyderabad, Kolkata, Lakshadweep, Mahe, Mumbai, Mumbai Suburban, New Delhi, Nicobars, North, North East, North West, Shahdara, South, South Andaman, South East, South West, Srinagar, The Nilgiris, West, Yanam. Crop-structure fields are NOT imputed for them (no cropping to describe); exposure comes from the surrounding districts, sensitivity from supply and PDS dependency only.

<!-- 06_export -->

## Result: nulls per field in districts.json, before -> after (753 districts)

`before` = the v4 export (pre-imputation); `after` = this run. A null that remains is a field with nothing to estimate from (e.g. crop structure of consumption-side districts, NFHS-6 anaemia which the round does not publish).

| field | null before | null after | filled |
|---|---|---|---|
| `population_2011` | 22 | 0 | 22 |
| `population_2026` | 22 | 0 | 22 |
| `children_u5_est` | 22 | 0 | 22 |
| `crops.foodgrain_prod_t` | 24 | 15 | 9 |
| `crops.gross_cropped_area_ha` | 24 | 15 | 9 |
| `crops.rainfed_share` | 31 | 18 | 13 |
| `crops.irrigated_share` | 31 | 18 | 13 |
| `crops.small_marginal_share` | 109 | 20 | 89 |
| `crops.yield_cv10` | 55 | 19 | 36 |
| `crops.simpson_div` | 24 | 15 | 9 |
| `crops.top_crop_share` | 24 | 15 | 9 |
| `food_balance.self_sufficiency` | 42 | 15 | 27 |
| `food_balance.pds_dependency` | 82 | 0 | 82 |
| `nutrition.nfhs5.stunting` | 49 | 0 | 49 |
| `nutrition.nfhs5.wasting` | 49 | 0 | 49 |
| `nutrition.nfhs5.child_anaemia` | 49 | 0 | 49 |
| `nutrition.nfhs6.stunting` | 43 | 0 | 43 |
| `nutrition.nfhs6.wasting` | 43 | 0 | 43 |
| `nutrition.nfhs6.underweight` | 43 | 0 | 43 |
| `nutrition.nfhs6.women_bmi_low` | 43 | 0 | 43 |
| `nutrition.poshan_live.underweight_pct` | 5 | 0 | 5 |
| `nutrition.poshan_live.wasted_pct` | 71 | 0 | 71 |
| `markets.price_volatility_idx` | 284 | 0 | 284 |
| `markets.price_elnino_spike_pct` | 279 | 0 | 279 |
| `groundwater.premonsoon_depth_m` | 248 | 0 | 248 |
| `groundwater.decline_m_per_yr` | 270 | 0 | 270 |
| `groundwater.stress_idx` | 270 | 0 | 270 |
| `climate.jjas_normal_mm` | 4 | 0 | 4 |
| `climate.elnino_mean_anomaly_pct` | 4 | 0 | 4 |
| `climate.clim_vuln_index` | 120 | 0 | 120 |
| `season_context.rabi.foodgrain_prod_t` | 62 | 42 | 20 |
| `risk.kharif_2027:elnino.score` | 34 | 0 | 34 |
| `risk.rabi_2026_27:elnino.score` | 206 | 18 | 188 |

**`no_data` bands (elnino): kharif 34 -> 0; rabi 206 -> 18.** Remaining rabi no_data = districts whose rabi foodgrain area is < 0.5 % of their foodgrain area (APY / imputed) (18 negligible_rabi_foodgrain).

| scenario | before (high/medium/low/no_data) | after |
|---|---|---|
| kharif_2027:neutral | 25/182/512/34 | 27/181/545/0 |
| kharif_2027:elnino | 240/239/240/34 | 242/247/264/0 |
| kharif_2027:current | 126/253/340/34 | 134/257/362/0 |
| rabi_2026_27:elnino | 135/196/216/206 | 190/248/297/18 |
| rabi_2026_27:current | 135/196/216/206 | 190/248/297/18 |
| rabi_2026_27:neutral | 20/194/333/206 | 35/235/465/18 |

## Imputed-count distribution (`data_quality.imputed_count` = entries incl. `risk.*`; `imputed_data_count` = data fields only)

| imputed entries | districts (imputed_count) | districts (data fields only) |
|---|---|---|
| 0 | 294 | 336 |
| 1-5 | 224 | 267 |
| 6-10 | 130 | 90 |
| 11-20 | 62 | 29 |
| 21-40 | 34 | 31 |
| 41+ | 9 | 0 |

Mean 5.3 / median 2 / max 47 entries per district; 417 districts have at least one imputed data field. Data-field entries by source: neighbours_knn 1069, national_median 573, parent_inherit 488, state_median 88, state_ratio_nfhs5 85, state_ratio_nfhs6 85, ee_worldpop 84, neighbours_2hop 57, parent_split_area_share 54, ee_chirps 44, ee_rabi_ndvi 28.

## Sanity: imputed districts vs their neighbours (elnino score; neighbours = border-weighted mean of touching districts whose score is not itself imputed; consumption side: its donor districts)

### Kharif - consumption side: n=24, mean diff -4.3, mean |diff| 6.9, Spearman 0.63, within 10 pts of neighbours 17/24

| district | state | imputed from | score | neighbour mean | diff | n neighbours | band |
|---|---|---|---|---|---|---|---|
| Hyderabad | Telangana | urban_consumption_side | 36.1 | 51.3 | -15.2 | 32 | low |
| South Andaman | Andaman & Nicobar | urban_consumption_side | 32.8 | 47.4 | -14.6 | 5 | low |
| Lakshadweep | Lakshadweep | urban_consumption_side | 59.5 | 47.3 | +12.2 | 5 | high |
| Kolkata | West Bengal | urban_consumption_side | 30.0 | 41.8 | -11.8 | 22 | low |
| Nicobars | Andaman & Nicobar | urban_consumption_side | 29.8 | 40.4 | -10.6 | 5 | low |
| Chennai | Tamil Nadu | urban_consumption_side | 32.8 | 43.2 | -10.4 | 36 | low |
| Srinagar | Jammu & Kashmir | urban_consumption_side | 30.6 | 40.9 | -10.3 | 19 | low |
| Mahe | Puducherry | urban_consumption_side | 38.2 | 47.6 | -9.4 | 8 | low |
| Chandigarh | Chandigarh | urban_consumption_side | 20.3 | 29.5 | -9.2 | 8 | low |
| North East | Delhi | urban_consumption_side | 53.7 | 45.3 | +8.4 | 5 | medium |
| Mumbai Suburban | Maharashtra | urban_consumption_side | 50.3 | 57.9 | -7.6 | 34 | medium |
| South West | Delhi | urban_consumption_side | 29.1 | 36.2 | -7.1 | 9 | low |
| East | Delhi | urban_consumption_side | 37.8 | 44.2 | -6.4 | 9 | low |
| Mumbai | Maharashtra | urban_consumption_side | 64.2 | 57.9 | +6.3 | 34 | high |
| North West | Delhi | urban_consumption_side | 32.1 | 36.6 | -4.5 | 11 | low |
| Central | Delhi | urban_consumption_side | 37.1 | 41.3 | -4.2 | 12 | low |
| New Delhi | Delhi | urban_consumption_side | 37.4 | 41.1 | -3.7 | 8 | low |
| South East | Delhi | urban_consumption_side | 40.2 | 43.9 | -3.7 | 8 | low |
| Yanam | Puducherry | urban_consumption_side | 48.7 | 45.3 | +3.4 | 8 | medium |
| The Nilgiris | Tamil Nadu | urban_consumption_side | 40.8 | 43.2 | -2.4 | 36 | low |
| Shahdara | Delhi | urban_consumption_side | 43.6 | 45.3 | -1.7 | 5 | low |
| South | Delhi | urban_consumption_side | 38.7 | 40.3 | -1.6 | 7 | low |
| North | Delhi | urban_consumption_side | 39.8 | 38.9 | +0.9 | 3 | low |
| West | Delhi | urban_consumption_side | 37.1 | 37.0 | +0.1 | 8 | low |

### Kharif - crop structure from the parent (split children): n=9, mean diff +3.0, mean |diff| 4.2, Spearman 0.13, within 10 pts of neighbours 8/9

| district | state | imputed from | score | neighbour mean | diff | n neighbours | band |
|---|---|---|---|---|---|---|---|
| Jiribam | Manipur | parent_split_area_share | 50.6 | 39.8 | +10.8 | 1 | medium |
| Pherzawl | Manipur | parent_split_area_share | 51.4 | 45.7 | +5.7 | 1 | medium |
| Tengnoupal | Manipur | parent_split_area_share | 46.2 | 40.7 | +5.5 | 2 | medium |
| Kamjong | Manipur | parent_split_area_share | 42.0 | 47.3 | -5.3 | 1 | low |
| Kangpokpi | Manipur | parent_split_area_share | 49.0 | 45.5 | +3.5 | 7 | medium |
| Kakching | Manipur | parent_split_area_share | 44.4 | 41.1 | +3.3 | 5 | low |
| Noney | Manipur | parent_split_area_share | 44.4 | 42.0 | +2.4 | 2 | low |
| Eastern West Khasi Hills | Meghalaya | parent_split_area_share | 44.0 | 42.9 | +1.1 | 4 | low |
| Bajali | Assam | parent_split_area_share | 53.7 | 54.1 | -0.4 | 3 | medium |

### Kharif - other imputed inputs, kharif (AP / other new districts, partial layers): n=23, mean diff -0.4, mean |diff| 3.7, Spearman 0.65, within 10 pts of neighbours 23/23

| district | state | imputed from | score | neighbour mean | diff | n neighbours | band |
|---|---|---|---|---|---|---|---|
| Anakapalli | Andhra Pradesh | imputed_inputs | 47.0 | 39.0 | +8.0 | 2 | medium |
| Hnahthial | Mizoram | imputed_inputs | 35.0 | 42.7 | -7.7 | 3 | low |
| Vijayanagar | Karnataka | imputed_inputs | 50.3 | 57.0 | -6.7 | 6 | medium |
| Palnadu | Andhra Pradesh | imputed_inputs | 55.0 | 48.5 | +6.5 | 2 | high |
| Alluri Sitharama Raju | Andhra Pradesh | imputed_inputs | 47.8 | 41.8 | +6.0 | 2 | medium |
| Malerkotla | Punjab | imputed_inputs | 23.1 | 29.0 | -5.9 | 5 | low |
| Niwari | Madhya Pradesh | imputed_inputs | 45.8 | 51.4 | -5.6 | 1 | medium |
| Noklak | Nagaland | imputed_inputs | 38.3 | 43.3 | -5.0 | 3 | low |
| Shi Yomi | Arunachal Pradesh | imputed_inputs | 33.0 | 37.4 | -4.4 | 4 | low |
| Senapati | Manipur | imputed_inputs | 41.3 | 45.7 | -4.4 | 2 | low |
| Bapatla | Andhra Pradesh | imputed_inputs | 51.3 | 47.6 | +3.7 | 3 | medium |
| Kakinada | Andhra Pradesh | imputed_inputs | 44.9 | 41.7 | +3.2 | 1 | low |
| Sri Sathya sai | Andhra Pradesh | imputed_inputs | 58.9 | 55.7 | +3.2 | 2 | high |
| Saitual | Mizoram | imputed_inputs | 42.0 | 44.5 | -2.5 | 3 | low |
| Nandyal | Andhra Pradesh | imputed_inputs | 53.2 | 55.5 | -2.3 | 4 | medium |
| Konaseema | Andhra Pradesh | imputed_inputs | 45.0 | 42.7 | +2.3 | 2 | medium |
| Annamayya | Andhra Pradesh | imputed_inputs | 50.4 | 48.5 | +1.9 | 3 | medium |
| Tirupati | Andhra Pradesh | imputed_inputs | 42.7 | 44.4 | -1.7 | 2 | low |
| Parvathipuram Manyam | Andhra Pradesh | imputed_inputs | 43.9 | 42.3 | +1.6 | 2 | low |
| NTR | Andhra Pradesh | imputed_inputs | 45.7 | 44.8 | +0.9 | 2 | medium |
| Mayiladuthurai | Tamil Nadu | imputed_inputs | 39.5 | 40.4 | -0.9 | 3 | low |
| Khawzawl | Mizoram | imputed_inputs | 42.5 | 43.3 | -0.8 | 2 | low |
| Eluru | Andhra Pradesh | imputed_inputs | 43.9 | 43.5 | +0.4 | 3 | low |

### Rabi - districts whose rabi shock is estimated from the touching districts' models: n=96, mean diff -0.2, mean |diff| 6.6, Spearman 0.76, within 10 pts of neighbours 75/96

Their own kharif elnino score (not imputed) vs their rabi score, and the neighbour mean rabi score, for the 15 largest differences:

| district | state | rabi score | neighbour mean (rabi) | diff | n neighbours | band |
|---|---|---|---|---|---|---|
| Lower Dibang Valley | Arunachal Pradesh | 22.0 | 42.3 | -20.3 | 1 | low |
| Lohit | Arunachal Pradesh | 22.9 | 42.3 | -19.4 | 1 | low |
| Kolasib | Mizoram | 46.0 | 64.7 | -18.7 | 1 | medium |
| Changlang | Arunachal Pradesh | 24.9 | 42.3 | -17.4 | 1 | low |
| East Siang | Arunachal Pradesh | 25.1 | 42.3 | -17.2 | 1 | low |
| Nabarangapur | Odisha | 65.0 | 48.2 | +16.8 | 1 | high |
| Gajapati | Odisha | 59.2 | 42.9 | +16.3 | 1 | high |
| Pakke Kessang | Arunachal Pradesh | 31.2 | 46.9 | -15.7 | 2 | low |
| West Kameng | Arunachal Pradesh | 31.1 | 46.8 | -15.7 | 1 | low |
| Namsai | Arunachal Pradesh | 27.4 | 42.3 | -14.9 | 1 | low |
| Mamit | Mizoram | 50.8 | 64.7 | -13.9 | 1 | medium |
| Charaideo | Assam | 61.2 | 47.7 | +13.5 | 1 | high |
| Dadra & Nagar Haveli | Dadra,Nagar Haveli,Daman & Diu | 71.7 | 59.1 | +12.6 | 1 | high |
| Papum Pare | Arunachal Pradesh | 29.5 | 42.1 | -12.6 | 2 | low |
| Tirap | Arunachal Pradesh | 30.1 | 42.3 | -12.2 | 1 | low |

