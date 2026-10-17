"""03 — nutrition + social layer: NFHS (4/5/6), Census-2011 PCA, state population projections,
PDS rice/wheat, climate-vulnerability index, natural-farming registrations.

Outputs (idempotent):
  artifacts/social_district.parquet
  artifacts/timeseries_social/{lgd}.json
  artifacts/reports/03_social_report.md
"""
from __future__ import annotations
import json, re, shutil, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import districts, read_idp, RAW, ART, save_json

POP = RAW / "09_population_malnutrition"
M = districts()
LG = set(M.lgd)
R: list[str] = []          # report lines
def rep(s=""): R.append(s)

def pct(a, b): return f"{a}/{b} ({100*a/b:.1f}%)"

# ═══ 1. NFHS ═══════════════════════════════════════════════════════════════════
nf = read_idp(POP / "idp_nfhs_poshan" / "District_Level_NFHS.csv")
nf_raw_n = len(nf)
nf = nf[nf.lgd.notna()]
assert not nf.duplicated(["year", "lgd"]).any()
CORE = {"stunting": "under5_stunted", "wasting": "under5_wasted", "severe_wasting": "under5_severely_wasted",
        "underweight": "under5_underweight", "child_anaemia": "children_6_59m_anaemic",
        "women_anaemia": "women_15_49_anaemic", "women_bmi_low": "women_bmi_under18_5"}
EXTRA = {"women_literate": "women_literate", "women_10plus_schooling": "women_10plus_schooling",
         "improved_sanitation": "population_improved_sanitation", "improved_water": "population_improved_water",
         "electricity": "population_electricity", "health_insurance": "households_health_insurance",
         "clean_cooking_fuel": "households_clean_cooking_fuel", "institutional_births": "institutional_births",
         "anc_4plus": "mothers_anc_4plus_visits", "fully_vaccinated_12_23m": "children_12_23m_fully_vaccinated",
         "adequate_diet_6_23m": "children_6_23m_adequate_diet", "exclusive_bf_u6m": "under6m_exclusive_breastfeeding",
         "women_bmi_25plus": "women_bmi_25plus", "pop_under5_pct": "population_under_5",
         "women_20_24_married_before18": "women_20_24_married_before18",
         "women_use_mobile_phone": "women_use_mobile_phone", "households_bank_account": "households_bank_account"}
ALL = {**CORE, **EXTRA}
ROUND = {"nfhs4": "2015-16", "nfhs5": "2019-21", "nfhs6": "2023-24"}

def row_dicts(df):
    """vectorised-ish: build per-row dict, NaN -> None, rounded to 1 dp."""
    vals = df[list(ALL.values())].astype(float).round(1)
    out = []
    for yr, rec in zip(df["year"], vals.to_dict("records")):
        d = {"year": yr}
        for k, c in ALL.items():
            v = rec[c]; d[k] = None if pd.isna(v) else float(v)
        out.append(d)
    return out

nfhs_by_round: dict[str, pd.Series] = {}
nfhs_flat = {}
for key, yr in ROUND.items():
    sub = nf[nf.year == yr].set_index("lgd")
    s = pd.Series(row_dicts(sub), index=sub.index.astype(int))
    nfhs_by_round[key] = s
    for short, c in (("stunting", "under5_stunted"), ("wasting", "under5_wasted"), ("underweight", "under5_underweight"),
                     ("child_anaemia", "children_6_59m_anaemic"), ("women_anaemia", "women_15_49_anaemic")):
        nfhs_flat[f"{short}_{key}"] = pd.Series(sub[c].astype(float).values, index=sub.index.astype(int))

# ═══ 2. Census PCA ════════════════════════════════════════════════════════════
cn = pd.read_csv(POP / "idp_census_pca" / "Census_PCA_Demography_Districts.csv", low_memory=False)
cn_rows = len(cn)
cn["lgd"] = pd.to_numeric(cn.district_code, errors="coerce")
# Unmapped (district_code NaN) rows: Kolkata (WB) and Greater Mumbai (MH) — recover by state + known totals.
unm = cn.lgd.isna()
wb = unm & (cn.state_name == "West Bengal"); mh = unm & (cn.state_name == "Maharashtra")
cn.loc[wb, "lgd"] = 315                                    # Kolkata
mumbai_ward_total = cn[mh & (cn.level == "Ward") & (cn.gender == "Total") & (cn.literacy == "Total")].population.sum()
cn.loc[mh & (cn.level == "Town"), ["lgd", "level"]] = [483, "Ward"]   # Mumbai Suburban (Town-level total = 9,356,962 = true district)
cn_unmapped_left = int(cn.lgd.isna().sum())               # Maharashtra Ward-level combined rows (used only for Mumbai pop)
# Urban = "Ward" level. "Town" excludes municipal-corporation cities (e.g. Delhi, Bengaluru Urban) so Ward >= Town;
# for ordinary districts Ward == Town. Relabelled "Town" below (= urban).
c = cn[cn.lgd.notna() & cn.level.isin(["Village", "Ward"])].copy()
c["level"] = c.level.replace({"Ward": "Town"})
c["lgd"] = c.lgd.astype(int)
assert not c.duplicated(["lgd", "level", "gender", "age", "social_group", "literacy", "working_status", "worker_type", "occupation"]).any()

def agg(mask):
    return c[mask].groupby(["lgd", "level"]).population.sum().unstack("level").reindex(columns=["Village", "Town"]).fillna(0)

gT = c.gender == "Total"
pop = agg(gT & (c.literacy == "Total"))
tot = pop.sum(axis=1)
S = pd.DataFrame({"population_2011": tot})
S["rural_share"] = pop["Village"] / tot
sg = lambda g: agg(gT & (c.social_group == g)).sum(axis=1)
S["sc_share"] = sg("Sc") / sg("Total"); S["st_share"] = sg("St") / sg("Total")
S["sc_st_share"] = S.sc_share + S.st_share
wk = lambda occ: agg(gT & (c.working_status == "Worker") & (c.worker_type == "Total") & (c.occupation == occ)).sum(axis=1)
w_tot = wk("Total")
S["agri_workers_share"] = (wk("Cultivator") + wk("Agricultural_Labourers")) / w_tot
S["cultivator_share_workers"] = wk("Cultivator") / w_tot
S["agri_labour_share_workers"] = wk("Agricultural_Labourers") / w_tot
S["worker_participation"] = w_tot / tot
S["pop_0_6_share"] = agg(gT & c.age.notna()).sum(axis=1) / tot
S["literacy_rate_2011"] = agg(gT & (c.literacy == "Literate")).sum(axis=1) / tot
fem = c.gender == "Female"
S["female_literacy_2011"] = agg(fem & (c.literacy == "Literate")).sum(axis=1) / agg(fem & (c.literacy == "Total")).sum(axis=1)
S.loc[S.population_2011 <= 0] = np.nan
S.loc[w_tot.reindex(S.index) <= 0, ["agri_workers_share", "cultivator_share_workers", "agri_labour_share_workers"]] = np.nan
# Greater Mumbai (482): population only
S.loc[482, ["population_2011", "rural_share"]] = [mumbai_ward_total - S.loc[483, "population_2011"], 0.0]

# ═══ 3. Population projection (state factors, NCP/MoHFW July 2020, Table 8, 1 March, '000, Persons) ═══
# Parsed from the PDF (pdftotext -layout, Table 8) and hard-coded for reproducibility.
PROJ = {  # state: (2011, 2026)
 "Jammu & Kashmir": (12267, 13896), "Himachal Pradesh": (6865, 7579), "Punjab": (27743, 31318), "Haryana": (25351, 31299),
 "Delhi": (16788, 22540), "Rajasthan": (68548, 83642), "Uttar Pradesh": (199812, 242859), "Bihar": (104099, 132265),
 "Assam": (31206, 36717), "West Bengal": (91276, 100522), "Jharkhand": (32988, 40958), "Odisha": (41974, 44677),
 "Chhattisgarh": (25545, 31211), "Madhya Pradesh": (72627, 89673), "Gujarat": (60440, 74086),
 "Maharashtra": (112374, 129308), "Andhra Pradesh": (49577, 53709), "Karnataka": (61095, 68962), "Kerala": (33406, 36207),
 "Tamil Nadu": (72147, 77546), "Chandigarh": (1055, 1267), "Uttarakhand": (10086, 11993), "Sikkim": (611, 708),
 "Arunachal Pradesh": (1384, 1604), "Nagaland": (1979, 2294), "Manipur": (2856, 3311), "Mizoram": (1097, 1272),
 "Tripura": (3674, 4260), "Meghalaya": (2967, 3440), "Goa": (1459, 1599),
 "Lakshadweep": (64, 70), "Puducherry": (1248, 1757), "Andaman & Nicobar": (381, 406),
 "Telangana": (35004, 38636), "Ladakh": (274, 305),
 "Dadra,Nagar Haveli,Daman & Diu": (243 + 344, 705 + 836),   # Daman & Diu + Dadra & Nagar Haveli
}
INDIA_PROJ = (1210855, 1423435)
pf = pd.DataFrame(PROJ, index=["p2011", "p2026"]).T
pf["factor"] = pf.p2026 / pf.p2011
assert set(M.state) <= set(pf.index), set(M.state) - set(pf.index)
S = M[["lgd", "state"]].merge(S, left_on="lgd", right_index=True, how="left").set_index("lgd")
S["state_pop_factor"] = S.state.map(pf.factor)
S["population_2026"] = (S.population_2011 * S.state_pop_factor).round()
S["pop_projection_flag"] = np.where(S.state_pop_factor > 1.5, "state_factor_outlier_gt1.5", None)

# children under 5: share chain NFHS-6 pop_under5 -> NFHS-5 -> census 0-6 share scaled -> state median
sh6 = pd.Series({k: v["pop_under5_pct"] for k, v in nfhs_by_round["nfhs6"].items()}, dtype=float) / 100
sh5 = pd.Series({k: v["pop_under5_pct"] for k, v in nfhs_by_round["nfhs5"].items()}, dtype=float) / 100
both = pd.concat([sh6.rename("n6"), (S.pop_0_6_share).rename("c06")], axis=1).dropna()
ratio_c06 = float((both.n6 / both.c06).median())      # empirical u5(2023-24) / census 0-6(2011)
S["u5_share"] = sh6.reindex(S.index)
S["u5_method"] = np.where(S.u5_share.notna(), "nfhs6_pop_under5", None)
m5 = S.u5_share.isna() & sh5.reindex(S.index).notna()
S.loc[m5, "u5_share"] = sh5.reindex(S.index)[m5]; S.loc[m5, "u5_method"] = "nfhs5_pop_under5"
mc = S.u5_share.isna() & S.pop_0_6_share.notna()
S.loc[mc, "u5_share"] = S.pop_0_6_share[mc] * ratio_c06; S.loc[mc, "u5_method"] = "census_0_6_x_ratio"
ms = S.u5_share.isna() & S.population_2011.notna()
stmed = S.groupby("state").u5_share.transform("median")
S.loc[ms & stmed.notna(), "u5_share"] = stmed[ms & stmed.notna()]; S.loc[ms & stmed.notna(), "u5_method"] = "state_median"
mg = S.u5_share.isna() & S.population_2011.notna()
S.loc[mg, "u5_share"] = float(S.u5_share.median()); S.loc[mg, "u5_method"] = "national_median"
S["children_u5_est"] = (S.population_2026 * S.u5_share).round()

# ═══ 4. NFHS attach ═══════════════════════════════════════════════════════════
for key in ROUND:
    S[f"{key}_json"] = nfhs_by_round[key].reindex(S.index).map(lambda d: json.dumps(d) if isinstance(d, dict) else None)
for k, s in nfhs_flat.items():
    S[k] = s.reindex(S.index)

# ═══ 5. PDS ═══════════════════════════════════════════════════════════════════
pds = read_idp(RAW / "09_population_malnutrition" / "idp_rural_infra_pds" / "PDS_District_Wise_Monthly_Wheat_and_Rice.csv")
pds = pds[pds.lgd.notna()].copy()
pds["lgd"] = pds.lgd.astype(int)
pds["month"] = pd.to_datetime(pds.date).dt.to_period("M")
assert not pds.duplicated(["lgd", "month"]).any()
pds["dist_t"] = pds.total_rice_distributed.fillna(0) + pds.total_wheat_distributed.fillna(0)
months = sorted(pds.month.unique())
mset = set(months)
def last_full_end(before=None):
    for e in reversed(months):
        if before is not None and e > before: continue
        if all((e - i) in mset for i in range(12)): return e
end12 = last_full_end(); prev_end = end12 - 12
assert prev_end in mset
def window(end, min_months=10):
    w = pds[(pds.month > end - 12) & (pds.month <= end)]
    g = w.groupby("lgd").agg(n=("month", "nunique"), t=("dist_t", "sum"), rice=("total_rice_distributed", "sum"), wheat=("total_wheat_distributed", "sum"))
    g = g[g.n >= min_months]
    scale = 12 / g.n
    out = pd.DataFrame({"t": g.t * scale, "rice": g.rice * scale, "wheat": g.wheat * scale, "n": g.n})
    out.loc[out.t <= 0, ["t", "rice", "wheat"]] = np.nan
    return out
w_now, w_prev = window(end12), window(prev_end)
S["pds_rice_wheat_t_latest12m"] = w_now.t.reindex(S.index).round(1)
S["pds_rice_t_latest12m"] = w_now.rice.reindex(S.index).round(1)
S["pds_wheat_t_latest12m"] = w_now.wheat.reindex(S.index).round(1)
S["pds_months_present"] = w_now.n.reindex(S.index)
S["pds_latest_period"] = np.where(S.pds_rice_wheat_t_latest12m.notna(), f"{end12 - 11}..{end12}", None)
S["pds_rice_wheat_t_prev12m"] = w_prev.t.reindex(S.index).round(1)
S["pds_prev_period"] = np.where(S.pds_rice_wheat_t_prev12m.notna(), f"{prev_end - 11}..{prev_end}", None)
pds_last = max(months)

# ═══ 6. Climate vulnerability ═════════════════════════════════════════════════
cv = read_idp(RAW / "05_weather_drought_imd" / "idp_climate" / "Climate_Vulnerability_Indicators_District_Wise.csv")
cv = cv[cv.lgd.notna()].copy(); cv["lgd"] = cv.lgd.astype(int)
cv_n_raw, cv_dups = len(cv), int(cv.duplicated("lgd").sum())
cv = cv.sort_values(["lgd", "climate_vul_in"], na_position="last").drop_duplicates("lgd").set_index("lgd")
comp_cols = [x for x in cv.columns if x not in ("id", "year", "state_code", "state_name", "district_name", "district_code", "climate_vul_in")]
S["clim_vuln_index"] = cv.climate_vul_in.reindex(S.index)
cvc = cv.reindex(S.index)[comp_cols]
S["clim_vuln_components_json"] = [json.dumps({k: round(float(v), 4) for k, v in r.items() if pd.notna(v)}) or None
                                   for r in cvc.to_dict("records")]
S.loc[S.clim_vuln_components_json == "{}", "clim_vuln_components_json"] = None

# ═══ 7. Natural farming (name match, state-aware) ═════════════════════════════
nfm = pd.read_csv(RAW / "08_natural_farming" / "districtwise_farmer_count_all_years.csv")
nfm = nfm[nfm.fin_year == "All"].copy()
def norm(x): return re.sub(r"[^a-z0-9]", "", str(x).lower().replace("&", "and"))
M2 = M.assign(dk=M.district.map(norm), sk=M.state.map(norm).str[:4])
nfm["dk"] = nfm.district_name.map(norm); nfm["sk"] = nfm.state_name.map(norm).str[:4]
mm = nfm.merge(M2[["lgd", "dk", "sk"]], on=["dk", "sk"], how="left")
nf_match = int(mm.lgd.notna().sum()); nf_total = len(mm)
mm = mm[mm.lgd.notna()].drop_duplicates("lgd")
S["natural_farming_farmers"] = mm.set_index(mm.lgd.astype(int)).no_of_farmers.reindex(S.index)
S["natural_farming_area_acre"] = mm.set_index(mm.lgd.astype(int)).area_covered_acre.reindex(S.index)

# ═══ 8. write parquet ═════════════════════════════════════════════════════════
S = S.drop(columns=["state"]).reset_index().sort_values("lgd").reset_index(drop=True)
for col in S.select_dtypes("float").columns:
    if col in ("population_2011", "population_2026", "children_u5_est"):
        S[col] = S[col].astype("Int64")
S.to_parquet(ART / "social_district.parquet", index=False)

# ═══ 9. timeseries json ═══════════════════════════════════════════════════════
ts_dir = ART / "timeseries_social"
if ts_dir.exists(): shutil.rmtree(ts_dir)
ts_dir.mkdir(parents=True)
nfhs_ts: dict[int, list] = {}
for key in ("nfhs4", "nfhs5", "nfhs6"):
    for l, d in nfhs_by_round[key].items():
        nfhs_ts.setdefault(int(l), []).append({k: d[k] for k in ("year", "stunting", "wasting", "severe_wasting", "underweight", "child_anaemia", "women_anaemia", "women_bmi_low")})
cut = pds_last - 35
pm = pds[(pds.month >= cut)].sort_values(["lgd", "month"])
pds_ts: dict[int, list] = {}
for l, mth, r, w, ra, wa in zip(pm.lgd, pm.month, pm.total_rice_distributed, pm.total_wheat_distributed,
                                  pm.total_rice_allocated, pm.total_wheat_allocated):
    f = lambda v: None if pd.isna(v) else round(float(v), 2)
    pds_ts.setdefault(int(l), []).append({"date": f"{mth}-01", "rice_t": f(r), "wheat_t": f(w), "rice_alloc_t": f(ra), "wheat_alloc_t": f(wa)})
n_ts = 0
for l in M.lgd:
    l = int(l)
    if l in nfhs_ts or l in pds_ts:
        save_json({"nfhs": nfhs_ts.get(l, []), "pds_monthly": pds_ts.get(l, [])}, ts_dir / f"{l}.json"); n_ts += 1

# ═══ 10. report ═══════════════════════════════════════════════════════════════
N = len(M)
rep("# 03 — Nutrition & social layer: QA report\n")
rep(f"Master: {N} districts (`districts()`). Output rows: {len(S)} in `social_district.parquet`; timeseries_social files: {n_ts}.\n")
rep("## Match rates vs master\n")
rep("| Source | Rows (non-null code) | Distinct LGD | Matched to master | Master covered |\n|---|---|---|---|---|")
for key, yr in ROUND.items():
    ids = set(nfhs_by_round[key].index)
    rep(f"| NFHS {yr} ({key}) | {int((nf.year==yr).sum())} | {len(ids)} | {len(ids & LG)} | {pct(len(ids & LG), N)} |")
cids = set(c.lgd)
rep(f"| Census PCA 2011 | {cn_rows} rows ({len(cids)} districts after recovering Kolkata/Mumbai Suburban) | {len(cids)} | {len(cids & LG)} | {pct(len(cids & LG)+1, N)} (incl. Greater Mumbai pop only) |")
pids = set(pds.lgd)
rep(f"| PDS monthly | {len(pds)} | {len(pids)} | {len(pids & LG)} | {pct(len(pids & LG), N)} |")
rep(f"| Climate vulnerability | {cv_n_raw} ({cv_dups} duplicate codes dropped) | {cv.shape[0]} | {len(set(cv.index) & LG)} | {pct(len(set(cv.index) & LG), N)}; index non-null for {pct(int(S.clim_vuln_index.notna().sum()), N)} |")
rep(f"| Natural farming (name match, fin_year=All) | {nf_total} | - | {nf_match} | {pct(int(S.natural_farming_farmers.notna().sum()), N)} |")
rep(f"\nNFHS rows dropped for null district_code: {nf_raw_n - len(nf)} (Shahdara, Mahe, Yanam). Master districts with no census 2011 row (post-2011 new districts): {int(S.population_2011.isna().sum())}.\n")
rep("## Population sanity\n")
p11 = S.population_2011.astype(float).sum(); p26 = S.population_2026.astype(float).sum()
rep(f"- Sum of master-matched census 2011 population: **{p11/1e6:,.1f} M** (target ~1,210.9 M). Excluding recovered Greater Mumbai: {tot.sum()/1e6:,.1f} M. Remaining shortfall vs 1,210.9 M = post-2011 districts without census rows (Mahe, Yanam, etc.) and Pok.")
rep(f"- Sum of population_2026: **{p26/1e6:,.1f} M** (NCP India 1 Mar 2026 = {INDIA_PROJ[1]/1e3:,.1f} M; sum of state projections = {sum(v[1] for v in PROJ.values())/1e3:,.1f} M). Note: master drops Pok polygons (LGD 0), and districts missing census data have null population.")
rep(f"- Spot checks: Patan(455) = {int(S.set_index('lgd').loc[455,'population_2011']):,} (published 1,343,734); Nandurbar(486) = {int(S.set_index('lgd').loc[486,'population_2011']):,} (published 1,648,295); Kolkata(315) = {int(S.set_index('lgd').loc[315,'population_2011']):,} (4,496,694); Mumbai(482) = {int(S.set_index('lgd').loc[482,'population_2011']):,} (3,085,411); Mumbai Suburban(483) = {int(S.set_index('lgd').loc[483,'population_2011']):,} (9,356,962).")
rep(f"- children_u5_est total: {S.children_u5_est.astype(float).sum()/1e6:,.1f} M ({S.children_u5_est.astype(float).sum()/p26*100:.2f}% of population_2026). Method counts: {S.u5_method.value_counts().to_dict()}. Empirical NFHS-6 u5 share / census 0-6 share median ratio = {ratio_c06:.3f}.")
rep("\n## Projection method & caveats\n")
rep("- State growth factor = NCP/MoHFW (July 2020) Table 8, persons as on 1 March, 2026 / 2011; parsed from the PDF via `pdftotext -layout` and hard-coded in the script (no PDF dependency at run time). District 2026 = district 2011 x state factor (assumes uniform growth within a state; ignores intra-state migration/urbanisation differences).")
rep("- Districts split after 2011: master polygons are post-split but census rows are 2011 boundaries, so parents hold the full pre-split population and new child districts are null (not 0). State totals are therefore preserved but district values for split parents are overstated relative to current boundaries.")
out = S[S.pop_projection_flag.notna()]
rep(f"- Outlier state factors flagged in `pop_projection_flag` ({len(out)} districts): the source projects Dadra, Nagar Haveli, Daman & Diu to 2.6x 2011 (1.54 M in 2026, driven by assumed in-migration) - treat those 3 districts (and Delhi 1.34x, Puducherry 1.41x) with caution.")
rep("- Greater Mumbai(482): only population_2011 and rural_share derived (census rows for the Mumbai pair arrive unmapped with a combined Ward-level total); other census indicators are null. Mumbai Suburban(483) took Town-level rows.")
rep("\n## NFHS coverage & distributions\n")
rep("| Round | districts in master | stunting | wasting | child anaemia | women anaemia | women BMI<18.5 |\n|---|---|---|---|---|---|---|")
for key, yr in ROUND.items():
    ser = nfhs_by_round[key].reindex(S.lgd)
    cnt = lambda f: int(ser.map(lambda d: isinstance(d, dict) and d[f] is not None).sum())
    rep(f"| {yr} | {int(ser.map(lambda d: isinstance(d, dict)).sum())} | {cnt('stunting')} | {cnt('wasting')} | {cnt('child_anaemia')} | {cnt('women_anaemia')} | {cnt('women_bmi_low')} |")
rep("\nNFHS-6 (2023-24) district fact-sheets in this file carry no anaemia indicators (null), no sanitation, no women_literate; those fields are null, not 0.\n")
rep("Stunting (% under-5) distribution:\n\n| Round | n | min | p10 | p25 | median | p75 | p90 | max | mean |\n|---|---|---|---|---|---|---|---|---|---|")
for key, yr in ROUND.items():
    x = S[f"stunting_{key}"].dropna()
    q = x.quantile([.1, .25, .5, .75, .9])
    rep(f"| {yr} | {len(x)} | {x.min():.1f} | {q[.1]:.1f} | {q[.25]:.1f} | {q[.5]:.1f} | {q[.75]:.1f} | {q[.9]:.1f} | {x.max():.1f} | {x.mean():.1f} |")
rep(f"\nNFHS-5 -> NFHS-6 stunting change (districts with both): median {((S.stunting_nfhs6 - S.stunting_nfhs5).dropna()).median():+.1f} pp, n={int((S.stunting_nfhs6 - S.stunting_nfhs5).notna().sum())}. "
    "Caution: some district estimates are noisy (e.g. Patan 50.5 -> 38.0 between rounds); district-level NFHS has wide CIs.")
rep("\n## Census-derived indicators (master-matched)\n")
d = S[["rural_share", "sc_st_share", "agri_workers_share", "pop_0_6_share", "literacy_rate_2011"]].describe().loc[["count", "min", "50%", "mean", "max"]].round(3)
rep(d.to_markdown() if hasattr(d, "to_markdown") else d.to_string())
rep("\n- Total population: row with gender=Total & literacy=Total, levels Village + urban. Urban = `Ward` level: `Town` level omits municipal-corporation cities (Delhi, Bengaluru Urban, Indore ... would lose 40-90% of urban pop) while Ward == Town for ordinary districts; Ward level is therefore used.")
rep("- agri_workers_share = (cultivators + agricultural labourers) / total workers (main + marginal). sc_st_share = (SC + ST) / population.")
rep("\n## PDS\n")
rep(f"- Units: `total_*_allocated/distributed` are **tonnes per month** (e.g. Kozhikode ~6.1 kt rice + ~1.5 kt wheat per month for ~3 M people = ~2.5 kg/person/month, plausible for NFSA's 5 kg/beneficiary on ~50-65% coverage; kg or quintals would be off by 1000x/10x; median district 60 kt/yr over ~1.9 M people also fits tonnes). Source series spans {months[0]} to {pds_last} with a gap Jan-Aug 2021 for all districts.")
rep(f"- Latest complete 12 consecutive calendar months with data: **{end12-11}..{end12}**; districts need >=10 of 12 months present (annualised x12/n); `pds_months_present` records n. Previous window {prev_end-11}..{prev_end} stored in `pds_rice_wheat_t_prev12m`.")
ratio = (S.pds_rice_wheat_t_latest12m / S.pds_rice_wheat_t_prev12m).dropna()
rep(f"- Caveat: Apr-Nov 2020 includes PMGKAY (COVID free extra 5 kg/person/month), so the latest window may be inflated (observed median latest/previous = {ratio.median():.2f}x (n={len(ratio)}) - small at the median, larger in individual districts). For normal-year dependency use `pds_rice_wheat_t_prev12m`. Latest window is also stale (data ends 2021-11) - a documented limitation.")
rep(f"- Coverage: latest12m non-null {pct(int(S.pds_rice_wheat_t_latest12m.notna().sum()), N)}; prev12m non-null {pct(int(S.pds_rice_wheat_t_prev12m.notna().sum()), N)}. PDS source covers fewer than all districts (not all states report).")
rep(f"- Median latest12m distributed (rice+wheat): {S.pds_rice_wheat_t_latest12m.median():,.0f} t/district/yr.")
rep("\n## Climate vulnerability\n")
x = S.clim_vuln_index.dropna()
rep(f"- `climate_vul_in` range {x.min():.3f}-{x.max():.3f} (mean {x.mean():.3f}); it is a 0-1 composite but empirically compressed (not rescaled). Components kept where non-null (many sparse): median {int(pd.Series([len(json.loads(j)) for j in S.clim_vuln_components_json.dropna()]).median())} components per district.")
rep("\n## Skipped / not done\n")
rep("- PLFS and District_Level_Infrastructure: PLFS is state-level only (no district_code); Mission Antyodaya infrastructure is village-sample counts for 2020 - not used.")
rep(f"- Natural farming matched by normalised name + first 4 letters of state: {nf_match}/{nf_total} source rows matched; unmatched rows (renamed/new districts) are dropped.")
rep("- NFHS-4 uses 2015-16 district boundaries: only districts with an LGD code are matched.")
Path(ART / "reports").mkdir(exist_ok=True)
(ART / "reports" / "03_social_report.md").write_text("\n".join(R) + "\n")
print("done", len(S), n_ts)
