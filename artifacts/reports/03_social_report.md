# 03 — Nutrition & social layer: QA report

Master: 753 districts (`districts()`). Output rows: 753 in `social_district.parquet`; timeseries_social files: 729.

## Match rates vs master

| Source | Rows (non-null code) | Distinct LGD | Matched to master | Master covered |
|---|---|---|---|---|
| NFHS 2015-16 (nfhs4) | 573 | 573 | 573 | 573/753 (76.1%) |
| NFHS 2019-21 (nfhs5) | 704 | 704 | 704 | 704/753 (93.5%) |
| NFHS 2023-24 (nfhs6) | 710 | 710 | 710 | 710/753 (94.3%) |
| Census PCA 2011 | 188910 rows (730 districts after recovering Kolkata/Mumbai Suburban) | 730 | 730 | 731/753 (97.1%) (incl. Greater Mumbai pop only) |
| PDS monthly | 28338 | 717 | 717 | 717/753 (95.2%) |
| Climate vulnerability | 699 (5 duplicate codes dropped) | 694 | 694 | 694/753 (92.2%); index non-null for 633/753 (84.1%) |
| Natural farming (name match, fin_year=All) | 672 | - | 586 | 586/753 (77.8%) |

NFHS rows dropped for null district_code: 8 (Shahdara, Mahe, Yanam). Master districts with no census 2011 row (post-2011 new districts): 22.

## Population sanity

- Sum of master-matched census 2011 population: **1,207.3 M** (target ~1,210.9 M). Excluding recovered Greater Mumbai: 1,204.3 M. Remaining shortfall vs 1,210.9 M = post-2011 districts without census rows (Mahe, Yanam, etc.) and Pok.
- Sum of population_2026: **1,419.1 M** (NCP India 1 Mar 2026 = 1,423.4 M; sum of state projections = 1,423.4 M). Note: master drops Pok polygons (LGD 0), and districts missing census data have null population.
- Spot checks: Patan(455) = 1,343,995 (published 1,343,734); Nandurbar(486) = 1,648,295 (published 1,648,295); Kolkata(315) = 4,496,694 (4,496,694); Mumbai(482) = 3,085,411 (3,085,411); Mumbai Suburban(483) = 9,356,962 (9,356,962).
- children_u5_est total: 112.8 M (7.95% of population_2026). Method counts: {'nfhs6_pop_under5': 710, 'census_0_6_x_ratio': 22}. Empirical NFHS-6 u5 share / census 0-6 share median ratio = 0.566.

## Projection method & caveats

- State growth factor = NCP/MoHFW (July 2020) Table 8, persons as on 1 March, 2026 / 2011; parsed from the PDF via `pdftotext -layout` and hard-coded in the script (no PDF dependency at run time). District 2026 = district 2011 x state factor (assumes uniform growth within a state; ignores intra-state migration/urbanisation differences).
- Districts split after 2011: master polygons are post-split but census rows are 2011 boundaries, so parents hold the full pre-split population and new child districts are null (not 0). State totals are therefore preserved but district values for split parents are overstated relative to current boundaries.
- Outlier state factors flagged in `pop_projection_flag` (3 districts): the source projects Dadra, Nagar Haveli, Daman & Diu to 2.6x 2011 (1.54 M in 2026, driven by assumed in-migration) - treat those 3 districts (and Delhi 1.34x, Puducherry 1.41x) with caution.
- Greater Mumbai(482): only population_2011 and rural_share derived (census rows for the Mumbai pair arrive unmapped with a combined Ward-level total); other census indicators are null. Mumbai Suburban(483) took Town-level rows.

## NFHS coverage & distributions

| Round | districts in master | stunting | wasting | child anaemia | women anaemia | women BMI<18.5 |
|---|---|---|---|---|---|---|
| 2015-16 | 573 | 573 | 573 | 573 | 573 | 573 |
| 2019-21 | 704 | 704 | 704 | 704 | 704 | 704 |
| 2023-24 | 710 | 710 | 710 | 0 | 0 | 710 |

NFHS-6 (2023-24) district fact-sheets in this file carry no anaemia indicators (null), no sanitation, no women_literate; those fields are null, not 0.

Stunting (% under-5) distribution:

| Round | n | min | p10 | p25 | median | p75 | p90 | max | mean |
|---|---|---|---|---|---|---|---|---|---|
| 2015-16 | 573 | 12.4 | 22.6 | 28.3 | 36.3 | 43.9 | 49.1 | 65.1 | 36.1 |
| 2019-21 | 704 | 13.2 | 23.0 | 27.3 | 32.8 | 39.2 | 45.1 | 60.6 | 33.5 |
| 2023-24 | 710 | 8.8 | 17.5 | 21.9 | 27.4 | 33.4 | 38.9 | 51.5 | 28.0 |

NFHS-5 -> NFHS-6 stunting change (districts with both): median -5.5 pp, n=693. Caution: some district estimates are noisy (e.g. Patan 50.5 -> 38.0 between rounds); district-level NFHS has wide CIs.

## Census-derived indicators (master-matched)

|       |   rural_share |   sc_st_share |   agri_workers_share |   pop_0_6_share |   literacy_rate_2011 |
|:------|--------------:|--------------:|---------------------:|----------------:|---------------------:|
| count |       731     |       730     |              730     |         730     |              730     |
| min   |         0     |         0.007 |                0     |           0.075 |                0.288 |
| 50%   |         0.806 |         0.263 |                0.631 |           0.137 |                0.618 |
| mean  |         0.747 |         0.341 |                0.577 |           0.139 |                0.62  |
| max   |         1     |         0.988 |                0.9   |           0.243 |                0.887 |

- Total population: row with gender=Total & literacy=Total, levels Village + urban. Urban = `Ward` level: `Town` level omits municipal-corporation cities (Delhi, Bengaluru Urban, Indore ... would lose 40-90% of urban pop) while Ward == Town for ordinary districts; Ward level is therefore used.
- agri_workers_share = (cultivators + agricultural labourers) / total workers (main + marginal). sc_st_share = (SC + ST) / population.

## PDS

- Units: `total_*_allocated/distributed` are **tonnes per month** (e.g. Kozhikode ~6.1 kt rice + ~1.5 kt wheat per month for ~3 M people = ~2.5 kg/person/month, plausible for NFSA's 5 kg/beneficiary on ~50-65% coverage; kg or quintals would be off by 1000x/10x; median district 60 kt/yr over ~1.9 M people also fits tonnes). Source series spans 2017-01 to 2021-11 with a gap Jan-Aug 2021 for all districts.
- Latest complete 12 consecutive calendar months with data: **2020-01..2020-12**; districts need >=10 of 12 months present (annualised x12/n); `pds_months_present` records n. Previous window 2019-01..2019-12 stored in `pds_rice_wheat_t_prev12m`.
- Caveat: Apr-Nov 2020 includes PMGKAY (COVID free extra 5 kg/person/month), so the latest window may be inflated (observed median latest/previous = 1.03x (n=654) - small at the median, larger in individual districts). For normal-year dependency use `pds_rice_wheat_t_prev12m`. Latest window is also stale (data ends 2021-11) - a documented limitation.
- Coverage: latest12m non-null 672/753 (89.2%); prev12m non-null 658/753 (87.4%). PDS source covers fewer than all districts (not all states report).
- Median latest12m distributed (rice+wheat): 60,164 t/district/yr.

## Climate vulnerability

- `climate_vul_in` range 0.069-0.753 (mean 0.561); it is a 0-1 composite but empirically compressed (not rescaled). Components kept where non-null (many sparse): median 13 components per district.

## Skipped / not done

- PLFS and District_Level_Infrastructure: PLFS is state-level only (no district_code); Mission Antyodaya infrastructure is village-sample counts for 2020 - not used.
- Natural farming matched by normalised name + first 4 letters of state: 586/672 source rows matched; unmatched rows (renamed/new districts) are dropped.
- NFHS-4 uses 2015-16 district boundaries: only districts with an LGD code are matched.
