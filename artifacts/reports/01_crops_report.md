# 01_crops report

## Rows in / out

- APY rows in: 455,359; 'Total'-season duplicate rows dropped: 48,044; rows used: 407,315 (303 in lgds not in master)
- UPAG rows in: 156,189; dropped for blank district_code: 54 (Mahe, Yanam); 808 more in lgds not in master
- Panel `crops_district_year`: 17,671 rows, 730 districts, crop years 1997-2024; source APY 16,241 / UPAG 1,430
- `crops_latest`: 753 rows (all master districts), `yield_sensitivity`: 753 rows, timeseries_crops: 753 json files

## Matching to district master (districts().lgd)

- Master polygons with LGD: 753; with any crop panel row: 730 (96.9%)
- APY lgds: 740 (11 not in master); UPAG lgds: 750 (22 not in master)
- Not in master (new districts created after the polygon file; dropped): 741: Pakyong (Sikkim); 742: Soreng (Sikkim); 757: Tseminyu (Nagaland); 758: Chumoukedima (Nagaland); 759: Khairagarh-Chhuikhadan-Gandai (Chhattisgarh); 760: Manendragarh-Chirmiri-Bharatpur(M C B) (Chhattisgarh); 761: Mohla-Manpur-Ambagarh Chouki (Chhattisgarh); 762: Sakti (Chhattisgarh); 763: Sarangarh-Bilaigarh (Chhattisgarh); 764: Niuland (Nagaland); 765: Shamator (Nagaland); 766: Mauganj (Madhya Pradesh); 767: Deeg (Rajasthan); 768: Didwana-Kuchaman (Rajasthan); 770: Khairthal-Tijara (Rajasthan); 772: Phalodi (Rajasthan); 774: Beawar (Rajasthan); 775: Balotra (Rajasthan); 777: Salumbar (Rajasthan); 782: Kotputli-Behror (Rajasthan); 784: Maihar (Madhya Pradesh); 785: Pandhurna (Madhya Pradesh)
- Master districts with NO crop data (23): Central (Delhi), East (Delhi), New Delhi (Delhi), North (Delhi), North East (Delhi), North West (Delhi), South (Delhi), South West (Delhi), West (Delhi), Kolkata (West Bengal), Lakshadweep (Lakshadweep), Mahe (Puducherry), Yanam (Puducherry), South East (Delhi), Shahdara (Delhi), Kakching (Manipur), Kangpokpi (Manipur), Jiribam (Manipur), Noney (Manipur), Pherzawl (Manipur), Tengnoupal (Manipur), Kamjong (Manipur), Bajali (Assam)

## Latest-year coverage

- Districts with a latest year (foodgrain production present): 729 / 753 (96.8%); flagged complete: 729
- Latest crop year distribution: 1997-98: 1, 1999-00: 1, 2016-17: 1, 2021-22: 19, 2022-23: 31, 2023-24: 676
- Source of latest row: UPAG: 676, APY: 53
- irrigated_share non-null: 723 / 753
- small_marginal_share non-null: 655 / 753
- yield_cv10 non-null: 698 / 753
- pmfby_farmers non-null: 528 / 753
- simpson_div non-null: 729 / 753
- Master districts without a latest snapshot: Central (Delhi), East (Delhi), New Delhi (Delhi), North (Delhi), North East (Delhi), North West (Delhi), South (Delhi), South West (Delhi), West (Delhi), Kolkata (West Bengal), Lakshadweep (Lakshadweep), Mahe (Puducherry), Yanam (Puducherry), South East (Delhi), Shahdara (Delhi), Kakching (Manipur), Kangpokpi (Manipur), Jiribam (Manipur), Noney (Manipur), Pherzawl (Manipur), Tengnoupal (Manipur), Kamjong (Manipur), Bajali (Assam), Eastern West Khasi Hills (Meghalaya)

## Year coverage histogram (districts with foodgrain_prod_t per crop year)

```
1997-98  498 #################################
1998-99  555 #####################################
1999-00  558 #####################################
2000-01  544 ####################################
2001-02  543 ####################################
2002-03  564 #####################################
2003-04  581 ######################################
2004-05  586 #######################################
2005-06  591 #######################################
2006-07  594 #######################################
2007-08  604 ########################################
2008-09  611 ########################################
2009-10  617 #########################################
2010-11  622 #########################################
2011-12  631 ##########################################
2012-13  640 ##########################################
2013-14  646 ###########################################
2014-15  655 ###########################################
2015-16  659 ###########################################
2016-17  685 #############################################
2017-18  685 #############################################
2018-19  689 #############################################
2019-20  698 ##############################################
2020-21  705 ###############################################
2021-22  709 ###############################################
2022-23  724 ################################################
2023-24  726 ################################################
2024-25  703 ##############################################
```

## Unit / harmonisation checks

- UPAG vs APY on 111,150 overlapping district-crop-season rows: area ratio 1.0103, production ratio 1.0016 => **UPAG is in ha / t / kg-per-ha, not '000** (applied factors: area x1, production x1). Yield kg/ha / 1000 -> t/ha.
- APY cotton production is in 170 kg bales, jute/mesta in 180 kg bales; converted x0.17 / x0.18. UPAG/APY production ratio after conversion: Cotton 1.000, Jute 1.000, Mesta 1.000
- foodgrain yields > 12 t/ha nulled: 0; max remaining foodgrain yield 10.92 t/ha

## Sample districts (latest snapshot)

| lgd | district | year | src | gross area ha | fg prod t | fg yield t/ha | cv10 | irrig | small+marg | top crops | elnino % | deficit % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 486 | Nandurbar (Maharashtra) | 2023-24 | UPAG | 350,775 | 214,684 | 1.30 | 0.19 | 0.42 | 0.68 | Cotton 37%, Maize 11%, Soybean 9% | -21.1 | -14.6 |
| 673 | Morbi (Gujarat) | 2023-24 | UPAG | 356,792 | 133,144 | 2.59 | 0.13 | 0.78 | 0.60 | Cotton 61%, Groundnut 16%, Wheat 9% | -10.0 | -0.6 |
| 191 | Begusarai (Bihar) | 2023-24 | UPAG | 188,184 | 610,338 | 3.90 | 0.24 | 0.66 | 0.98 | Maize 38%, Wheat 37%, Soybean 9% | -10.1 | -21.6 |
| 502 | Anantpur (Andhra Pradesh) | 2023-24 | UPAG | 359,194 | 277,860 | 1.52 | 0.34 | 0.41 | 0.72 | Groundnut 31%, Tur 17%, Gram 14% | -9.3 | -4.5 |
| 358 | Kalahandi (Odisha) | 2022-23 | APY | 274,033 | 760,960 | 2.83 | 0.21 | 0.56 | 0.87 | Rice 89%, Moong 5%, Urad 2% | -27.2 | -31.4 |

## Yield sensitivity (deviation from trend, El Nino years minus Neutral years, %)

- El Nino years used (ONI-derived, within 1997-2024): [2002, 2004, 2006, 2009, 2015, 2018, 2023]; Neutral: 11 years; La Nina: [1998, 1999, 2000, 2007, 2010, 2011, 2020, 2021, 2022]
- Deficit-year analogs: [2002, 2004, 2009, 2012, 2014, 2015, 2023]; baseline = all other years
- `foodgrain_elnino_pct`: n=657 non-null of 753; quantiles p0=-86.7, p5=-25.8, p10=-20.4, p25=-11.9, p50=-5.5, p75=-0.7, p90=2.7, p95=6.4, p100=37.9
- `foodgrain_deficit_year_pct`: n=653 non-null of 753; quantiles p0=-48.0, p5=-26.4, p10=-21.3, p25=-13.1, p50=-5.8, p75=-0.6, p90=3.6, p95=7.3, p100=30.9
- `cereals_elnino_pct`: n=654 non-null of 753; quantiles p0=-53.3, p5=-23.9, p10=-18.5, p25=-10.8, p50=-4.4, p75=-0.2, p90=3.4, p95=6.4, p100=28.9
- `millets_elnino_pct`: n=398 non-null of 753; quantiles p0=-57.3, p5=-32.1, p10=-24.6, p25=-16.7, p50=-5.6, p75=0.9, p90=6.3, p95=10.6, p100=37.4
- `pulses_elnino_pct`: n=575 non-null of 753; quantiles p0=-73.3, p5=-25.9, p10=-20.1, p25=-12.1, p50=-5.7, p75=-0.6, p90=5.6, p95=11.3, p100=44.7
- `oilseeds_elnino_pct`: n=562 non-null of 753; quantiles p0=-93.5, p5=-26.4, p10=-20.7, p25=-12.3, p50=-5.4, p75=0.5, p90=6.2, p95=11.9, p100=73.8
- share of districts with negative foodgrain_elnino_pct: 78.4%

## Season-split foodgrain columns (v4)

- `kharif_fg_*` / `rabi_fg_*` = foodgrain (cereals + millets + pulses) yield (t/ha), production (t), area (ha) by season label (kharif = Kharif + Autumn + Winter; rabi = Rabi; Summer and Whole Year in neither); `rabi_pulses_prod_t` = rabi pulses production. Used by 04b (--season rabi) and 04_risk (rabi scores).
- `kharif_fg_yield_t_ha` non-null rows: 17,493 of 17,671; districts with >= 1 year: 728; districts per crop year min / median / max: 493 / 620 / 726
- `rabi_fg_yield_t_ha` non-null rows: 15,979 of 17,671; districts with >= 1 year: 725; districts per crop year min / median / max: 443 / 566 / 688
- median rabi share of foodgrain production (district-years with both): 0.41

## Per-season top crops (v6, Addendum I)

- `kharif_top_json` / `rabi_top_json` (top-5 by area, share of the season's area on the same basis, yield t/ha) and `season_top_source` for the latest snapshot (same lgd x year x source as `top_json`). `apy_season_labels` = rows labelled Kharif / Autumn / Winter (kharif) or Rabi (Whole Year, Summer, Total ignored); `crop_calendar` = fallback for Bihar, Odisha, West Bengal, Assam, Jharkhand and for districts whose kharif+rabi labelled area is < 50 % of gross area (sowing-season crop list; sugarcane in both seasons; rice also in rabi where it is > 10 % of the rabi-labelled area).
- Districts with by-season tops: 729 / 753; source: apy_season_labels: 568, crop_calendar: 161
- Empty lists: kharif 2, rabi 17 (no crop of that season in the snapshot)
- Calendar fallback districts: 161 (of which in the five listed states: 147; by the < 50 % labelled-area rule: 14)

| lgd | district | source | labelled share | kharif top 3 | rabi top 3 |
|---|---|---|---|---|---|
| 486 | Nandurbar (Maharashtra) | apy_season_labels | 0.984 | Cotton 45%, Maize 11%, Soybean 11% | Wheat 38%, Gram 37%, Maize 13% |
| 358 | Kalahandi (Odisha) | crop_calendar | 0.802 | Rice 91%, Moong 5%, Urad 2% | Rapeseed & Mustard 91%, Sugarcane 9% |
| 673 | Morbi (Gujarat) | apy_season_labels | 0.953 | Cotton 76%, Groundnut 20%, Castorseed 3% | Wheat 63%, Gram 30%, Rapeseed & Mustard 7% |
| 191 | Begusarai (Bihar) | crop_calendar | 0.992 | Maize 67%, Soybean 16%, Rice 11% | Wheat 82%, Rapeseed & Mustard 12%, Sugarcane 5% |
| 502 | Anantpur (Andhra Pradesh) | apy_season_labels | 1.0 | Groundnut 36%, Tur 22%, Cotton 12% | Gram 60%, Groundnut 15%, Jowar 8% |

## Caveats

- UPAG file units are ha / t / kg-per-ha (identical to APY on the overlap), contrary to the '000-ha description; no x1000 conversion applied.
- APY and UPAG agree to <1 % on 2013-2022 foodgrain area/production for common crops, so the APY->UPAG switch (2023+) is smooth; APY coverage in 2020-22 is NOT partial in this extract (706-736 districts), so APY is kept there (UPAG used only where it has >5 % more foodgrain area).
- UPAG lists ~30 major crops only (no vegetables, fruit, spices, plantation). For UPAG-sourced years gross_cropped_area_ha, simpson_div, n_crops and top_crop_share are on a 'major crops' basis and are NOT comparable with APY-sourced rows; `gross_area_all_crops_ref_ha` gives the latest APY all-crop gross area.
- Gross cropped area = sum of all seasonal crop areas (incl. Whole Year perennials/plantations such as sugarcane, coconut, banana).
- Season labels are inconsistent across states/years (e.g. Bihar, Odisha, West Bengal, Assam, Jharkhand shift area between Kharif/Rabi/Autumn/Winter/Summer between 2022 and 2023; Odisha 2023 has no Rabi row). kharif_rabi_ratio (Kharif+Autumn+Winter over Rabi; Summer and Whole Year excluded) is unreliable for those states and for UPAG 2023+; treat as indicative only.
- SEASON-SPLIT COLUMNS (v4): the `season` label of APY/UPAG rows is unreliable in Bihar, Odisha, West Bengal, Assam and Jharkhand (area moves between Kharif / Autumn / Winter / Rabi / Summer between years; Odisha 2023 has no Rabi row; Summer/boro rice is in neither season column). `kharif_fg_*` and `rabi_fg_*` are therefore least reliable there and the season-split yield deviations built on them (04b --season rabi) inherit label-switch jumps; treat rabi results for those states as indicative. UPAG 2023+ covers major crops only, so season production is a lower bound in those years.
- PER-SEASON TOP CROPS (v6): season = label of the APY / UPAG row. Autumn and Winter (APY) count as kharif; Whole Year (sugarcane, plantation, banana), Summer (boro / summer rice, summer pulses) and APY 'Total' are ignored on the label basis, so sugarcane never appears in a label-based list. Fallback districts use a sowing-calendar crop list (CAL_KHARIF / CAL_RABI / sugarcane both) on the crop's all-season area: crops outside the list (vegetables, fruit, spices, plantation) are not listed, so the fallback share is of the classified area only; calendar assignment ignores rabi maize / rabi groundnut / summer crops. UPAG-sourced snapshots (676 districts, 2023-24) list ~30 major crops only. 'Other ...' aggregate rows (Other Pulses, Other Oilseeds, ...) are not listed. Yields from UPAG/APY production / area of rows reporting production; > 12 t/ha nulled.
- Production is summed over crops that report it; yield = production / area of crops with production, so missing production does not bias yield down but foodgrain_prod_t is a lower bound when fg_area_missing_prod_share > 0. Latest-year selection requires <= 15 % of foodgrain area lacking production.
- Latest year is capped at 2023-24: 2024-25 UPAG is provisional (kept in the panel and used in sensitivity). A district-year is 'complete' when <=15 % of foodgrain area lacks production, foodgrain area >= 30 % of the trailing-5-year median, and (only in state-years where new non-master districts report data: Rajasthan, MP, Chhattisgarh, Nagaland, Sikkim 2022+) >= 90 % of that median, so parents that lost area to child districts fall back to an earlier year. Real swings (e.g. 2023 drought-hit Nandurbar/Morbi) and long declines (Garhwal) are NOT rejected. The new districts themselves are not in the polygon master and are dropped (their area is therefore missing from 2023+ parents in split states where the 90 % test did not fire). `latest_stale` flags snapshots older than 2018 (urban districts with no real cropping: Mumbai, Hyderabad, ...).
- 'Other' crops (incl. fruit/veg) excluded from foodgrain. Millets group follows common.CROP_GROUPS ('Other Cereals' counted as millets). Classification fixes applied locally: Peas (Vegetable), Pear, Peach, Guar -> other; Korra/Samai/Varagu -> millets. Cash = sugarcane, cotton, jute, mesta, tobacco; cash yield is null because the group mixes cane tonnes and lint tonnes.
- Group yields from < 500 ha (rounding noise: APY reports in 100 ha steps) are excluded from sensitivity and time series. Deviations clipped to +/-100 %.
- 1997 (ONI El Nino) is excluded as an analog/baseline year (APY 1997-98 covers only ~500 districts; it is still used in detrending); analog years are therefore 2002, 2004, 2006, 2009, 2015, 2018, 2023. Yield sensitivity: per district/group linear trend over 1997-2024 (5-yr rolling median if < 12 obs, >= 6 obs required); trend fitted on all years including El Nino years (slightly biases the effect toward zero); effect = mean deviation in El Nino years minus mean in Neutral years (ONI-based, JJA-OND mean); requires >= 3 El Nino and >= 3 Neutral observations. These are historical analogs, not causal estimates; irrigated districts show weak signals and the deviation conflates rainfall with other shocks (e.g. 2018 and 2006 El Nino years were not monsoon deficits).
- deficit_year column uses non-deficit years (not Neutral ENSO years) as baseline; 2023 deficit-year data is UPAG (major crops only).
- irrigated_share = gross irrigated area / gross cropped area (both land-use statistics tables), latest year with valid data per district; zero numerators are treated as missing (tables report 0/NaN for non-reporting districts); share capped at 1. Coverage is patchy (2020-22 sparse; source-of-irrigation table is mostly empty for some districts, then the crop-wise irrigated table is used). Gross irrigated area can exceed net, so share is a cropping-intensity-weighted measure, not % of net sown area.
- small_marginal_share = (Marginal + Small, i.e. < 2 ha) / all operational holdings by count, latest Agriculture Census year per district (2015-16 where available, else 2010-11); districts created after 2011 may be missing.
- pmfby_farmers = PMFBY-scheme farmer_count summed over seasons and insurance-unit rows in the latest year (farmer-seasons, 2018-2022 only; loanee+non-loanee do not reconcile with farmer_count in source).
