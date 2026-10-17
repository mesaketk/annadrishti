# 02_climate report

Grid: rain 0.25 deg (IMD), tmax 1 deg (IMD). Years 2000-2025; normal = 2000-2024 mean. ENSO years (El Nino n=7): [2002, 2004, 2006, 2009, 2015, 2018, 2023]; Neutral n=12; La Nina n=7.

## All-India JJAS anomaly (area-weighted district means) vs IMD reference

| Year | ENSO | All-India JJAS (mm) | Anom vs 2000-24 mean (%) | Anom vs IMD LPA 868.6mm (%) | IMD reference (%) |
|---|---|---|---|---|---|
| 2000 | La Niña | 768 | -8.8 | -11.6 |  |
| 2001 | Neutral | 791 | -6.1 | -9.0 |  |
| 2002 | El Niño | 678 | -19.4 | -21.9 | -19 |
| 2003 | Neutral | 878 | +4.4 | +1.1 |  |
| 2004 | El Niño | 751 | -10.8 | -13.6 |  |
| 2005 | Neutral | 865 | +2.8 | -0.4 |  |
| 2006 | El Niño | 878 | +4.3 | +1.1 |  |
| 2007 | La Niña | 920 | +9.3 | +5.9 |  |
| 2008 | Neutral | 883 | +4.9 | +1.6 |  |
| 2009 | El Niño | 709 | -15.8 | -18.4 | -22 |
| 2010 | La Niña | 903 | +7.2 | +3.9 |  |
| 2011 | La Niña | 918 | +9.1 | +5.7 |  |
| 2012 | Neutral | 824 | -2.1 | -5.2 |  |
| 2013 | Neutral | 919 | +9.2 | +5.8 |  |
| 2014 | Neutral | 754 | -10.4 | -13.2 | -12 |
| 2015 | El Niño | 753 | -10.5 | -13.3 | -14 |
| 2016 | Neutral | 849 | +0.9 | -2.2 |  |
| 2017 | Neutral | 829 | -1.4 | -4.5 |  |
| 2018 | El Niño | 789 | -6.2 | -9.2 |  |
| 2019 | Neutral | 949 | +12.8 | +9.3 | 10 |
| 2020 | La Niña | 935 | +11.1 | +7.6 |  |
| 2021 | La Niña | 858 | +2.0 | -1.2 |  |
| 2022 | La Niña | 914 | +8.6 | +5.2 |  |
| 2023 | El Niño | 794 | -5.6 | -8.6 | -6 |
| 2024 | Neutral | 930 | +10.6 | +7.1 |  |
| 2025 | Neutral | 916 | +8.8 | +5.4 |  |

Note: IMD all-India anomalies are relative to the 1971-2020 LPA (868.6 mm); ours are relative to the 2000-2024 mean (shown also vs LPA). Rain-gauge-gridded data are IMD's own, so agreement is expected within a few points.

## Districts without in-polygon cells (nearest valid cell fallback)

Rain grid: 32 districts used fallback; tmax grid (1 deg): 505 districts.
Districts with null rainfall (nearest cell beyond 0.75 deg): 4; null tmax (beyond 1.5 deg): 3.

Null-rain districts: Lakshadweep (Lakshadweep, lgd 553), South Andaman (Andaman & Nicobar, lgd 602), Nicobars (Andaman & Nicobar, lgd 603), North  & Middle Andaman (Andaman & Nicobar, lgd 632)

Rain fallback districts (first 40, by distance):

| lgd | district | state | dist deg |
|---|---|---|---|
| 603 | Nicobars | Andaman & Nicobar | 14.48 |
| 602 | South Andaman | Andaman & Nicobar | 11.19 |
| 632 | North  & Middle Andaman | Andaman & Nicobar | 8.77 |
| 553 | Lakshadweep | Lakshadweep | 1.78 |
| 618 | Kamrup Metropolitan | Assam | 0.17 |
| 483 | Mumbai Suburban | Maharashtra | 0.16 |
| 568 | Chennai | Tamil Nadu | 0.15 |
| 30 | Fatehgarh Sahib | Punjab | 0.15 |
| 79 | New Delhi | Delhi | 0.14 |
| 85 | West | Delhi | 0.14 |
| 78 | East | Delhi | 0.14 |
| 60 | Faridabad | Haryana | 0.13 |
| 227 | South District | Sikkim | 0.13 |
| 256 | Imphal West | Manipur | 0.13 |
| 13 | Srinagar | Jammu & Kashmir | 0.12 |
| 713 | Jiribam | Manipur | 0.12 |
| 315 | Kolkata | West Bengal | 0.12 |
| 259 | Thoubal | Manipur | 0.12 |
| 463 | Daman | Dadra,Nagar Haveli,Daman & Diu | 0.12 |
| 507 | Hyderabad | Telangana | 0.12 |
| 707 | South Salmara Mancachar | Assam | 0.11 |
| 80 | North | Delhi | 0.10 |
| 608 | Sahibzada Ajit Singh Nag* | Punjab | 0.10 |
| 728 | Khawzawl | Mizoram | 0.09 |
| 84 | South West | Delhi | 0.09 |
| 671 | Shahdara | Delhi | 0.09 |
| 482 | Mumbai | Maharashtra | 0.08 |
| 77 | Central | Delhi | 0.08 |
| 464 | Diu | Dadra,Nagar Haveli,Daman & Diu | 0.07 |
| 599 | Mahe | Puducherry | 0.06 |
| 83 | South | Delhi | 0.05 |
| 601 | Yanam | Puducherry | 0.05 |

## Distribution of elnino_mean_anomaly_pct

```
count    749.00
mean      -9.53
std       10.40
min      -44.40
5%       -26.76
25%      -16.60
50%       -8.50
75%       -2.70
95%        5.36
max       28.30
```

Share of districts with El Nino mean anomaly < -10%: 43.7%; < 0: 82.3%. Mean elnino_deficit_prob: 0.52.

## Sample districts

| lgd | district | JJAS normal mm | El Nino % | Neutral % | La Nina % | Strong El Nino % | P(deficit) | latest anom % |
|---|---|---|---|---|---|---|---|---|
| 486 | Nandurbar (Maharashtra) | 763.5 | -1.9 | 2.1 | -0.9 | -16.8 | 0.7 | 5.1 (2025) |
| 673 | Morbi (Gujarat) | 717.4 | -28.0 | -3.8 | 33.6 | -35.1 | 0.9 | -6.2 (2025) |
| 191 | Begusarai (Bihar) | 874.1 | -4.9 | -0.0 | 9.3 | 0.0 | 0.6 | 30.6 (2025) |
| 502 | Anantpur (Andhra Pradesh) | 368.3 | -26.8 | -0.7 | 28.3 | -21.8 | 0.7 | 2.9 (2025) |
| 481 | Latur (Maharashtra) | 698.7 | -17.7 | 2.9 | 19.1 | -30.3 | 0.7 | 44.7 (2025) |

## Runtime

47 s (with cache). Normal from 2000-2024 IMD (TerraClimate 1958-2017 normal not used).
