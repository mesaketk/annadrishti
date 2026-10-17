"""03b_extra_sources: ICRISAT prices, Poshan Tracker, groundwater (CGWB + state boards), cost of cultivation.
Output: artifacts/extra_district.parquet (one row per lgd) + artifacts/reports/03b_extra_report.md
Null never 0: anything not computable / not reported stays NaN/None.
"""
from __future__ import annotations
import json, re, sys, time
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import districts, RAW, ART, enso_phase_by_monsoon_year  # noqa: E402

T0 = time.time()
D = districts()
OUT = D[["lgd"]].copy()
REP: list[str] = ["# 03b extra sources report\n"]
crops = pd.read_parquet(ART / "crops_latest.parquet")[["lgd", "top_json"]].set_index("lgd")


def top_crops(lgd: int, n: int = 5) -> list[str]:
    try:
        tj = crops.at[lgd, "top_json"]
        return [c["crop"] for c in json.loads(tj)][:n] if isinstance(tj, str) else []
    except KeyError:
        return []


def rank01(s: pd.Series) -> pd.Series:
    r = s.rank(method="average")
    n = s.notna().sum()
    return (r - 1) / (n - 1) if n > 1 else r * np.nan


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", str(s).lower())


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def dist(s: pd.Series) -> str:
    s = s.dropna()
    if s.empty:
        return "n=0"
    q = s.quantile([0, .1, .25, .5, .75, .9, 1])
    return f"n={len(s)} min={q.iloc[0]:.2f} p10={q.iloc[1]:.2f} p25={q.iloc[2]:.2f} med={q.iloc[3]:.2f} p75={q.iloc[4]:.2f} p90={q.iloc[5]:.2f} max={q.iloc[6]:.2f} mean={s.mean():.2f}"


# ════════════════════════════ 1. ICRISAT prices ════════════════════════════
PF = RAW / "11_icrisat_district_level_db" / "unapportioned__prices__farm-harvest-prices.csv"
ic = pd.read_csv(PF)
KC = "Indian census District Code 2011"
PCOL = {  # ICRISAT short name -> column
    "RICE": "RICE HARVEST PRICE (Rs per Quintal)", "PADDY": "PADDY HARVEST PRICE (Rs per Quintal)",
    "WHEAT": "WHEAT HARVEST PRICE (Rs per Quintal)", "SORGHUM": "SORGHUM HARVEST PRICE (Rs per Quintal)",
    "PEARL MILLET": "PEARL MILLET HARVEST PRICE (Rs per Quintal)", "MAIZE": "MAIZE HARVEST PRICE (Rs per Quintal)",
    "FINGER MILLET": "FINGER MILLET HARVEST PRICE (Rs per Quintal)", "BARLEY": "BARLEY HARVEST PRICE (Rs per Quintal)",
    "CHICKPEA": "CHICKPEA HARVEST PRICE (Rs per Quintal)", "PIGEONPEA": "PIGEONPEA HARVEST PRICE (Rs per Quintal)",
}
CROP2IC = {  # APY crop -> ordered ICRISAT candidates
    "Rice": ["RICE", "PADDY"], "Paddy": ["RICE", "PADDY"], "Wheat": ["WHEAT"], "Jowar": ["SORGHUM"], "Sorghum": ["SORGHUM"],
    "Bajra": ["PEARL MILLET"], "Pearl Millet": ["PEARL MILLET"], "Maize": ["MAIZE"], "Ragi": ["FINGER MILLET"],
    "Finger Millet": ["FINGER MILLET"], "Gram": ["CHICKPEA"], "Arhar/Tur": ["PIGEONPEA"], "Tur": ["PIGEONPEA"],
    "Barley": ["BARLEY"],
}
for k, c in PCOL.items():
    ic[k] = pd.to_numeric(ic[c], errors="coerce").where(lambda s: s > 0)  # -1 / <=0 = missing
ic["state_n"] = ic["State Name"].replace({"Orissa": "Odisha"}).map(norm)
ic["name_n"] = ic["Dist Name"].map(norm)
ic["key"] = np.where(ic[KC] > 0, "c" + ic[KC].astype(str), "n" + ic.state_n + "|" + ic.name_n)
D2 = D.copy()
D2["census_i"] = pd.to_numeric(D2.census11, errors="coerce").fillna(0).astype(int)
D2["state_n"] = D2.state.map(norm)
D2["name_n"] = D2.district.map(norm)
icode = set(ic.loc[ic[KC] > 0, KC].unique())
nkeys = set(ic.loc[ic[KC] <= 0, "key"].unique())
nkey_all = {r.state_n + "|" + r.name_n: r.key for r in ic.drop_duplicates("key").itertuples()}
EN_YEARS = [2002, 2004, 2006, 2009, 2015]
PH = enso_phase_by_monsoon_year()
NEUTRAL = {y for y, p in PH.items() if p == "Neutral"}

rows = []; match_how = {"census_code": 0, "name": 0, "none": 0}
for r in D2.itertuples():
    if r.census_i in icode:
        key, how = f"c{r.census_i}", "census_code"
    elif ("n" + r.state_n + "|" + r.name_n) in nkeys:
        key, how = "n" + r.state_n + "|" + r.name_n, "name"
    elif (r.state_n + "|" + r.name_n) in nkey_all:
        key, how = nkey_all[r.state_n + "|" + r.name_n], "name"
    else:
        key, how = None, "none"
    match_how[how] += 1
    rec = dict(lgd=r.lgd, price_match=how, price_crop=None, price_n_years=np.nan, price_elnino_spike_pct=np.nan,
               price_volatility_idx=np.nan, price_series_json=None, _cv=np.nan)
    if key is not None:
        sub = ic[ic.key == key].sort_values("Year")
        cand: list[str] = []
        for cn in top_crops(r.lgd):
            cand += [c for c in CROP2IC.get(cn, []) if c not in cand]
        cand += [c for c in ("RICE", "WHEAT") if c not in cand]
        pick = None
        for c in cand:
            s = sub.set_index("Year")[c].dropna()
            if len(s) >= 8:
                pick = (c, s); break
        if pick:
            c, s = pick
            yrs = s.index.values.astype(float); ly = np.log(s.values)
            b = np.polyfit(yrs, ly, 1); res = ly - np.polyval(b, yrs)
            dev = pd.Series((np.exp(res) - 1) * 100, index=s.index)
            en = dev[dev.index.isin(EN_YEARS)]; ne = dev[dev.index.isin(NEUTRAL)]
            rec.update(price_crop=c.title(), price_n_years=len(s), price_series_json=dumps({int(y): round(float(v), 1) for y, v in s.items()}))
            if len(en) >= 2 and len(ne) >= 3:
                rec["price_elnino_spike_pct"] = round(float(en.mean() - ne.mean()), 2)
            m = (s.index >= 2000) & (s.index <= 2017)
            if m.sum() >= 8:
                rec["_cv"] = float(np.std(res[m], ddof=1))
    rows.append(rec)
P = pd.DataFrame(rows)
P["price_volatility_idx"] = rank01(P["_cv"]).round(4)
P = P.drop(columns="_cv")
OUT = OUT.merge(P, on="lgd", how="left")
n = len(OUT)
REP += ["## 1. ICRISAT farm-harvest prices\n",
        f"- File rows {len(ic):,}; {ic[KC][ic[KC] > 0].nunique()} census-coded ICRISAT districts + {ic.loc[ic[KC] <= 0, 'key'].nunique()} districts with code -1 (name match only). ICRISAT years {ic.Year.min()}-{ic.Year.max()}.",
        f"- Master match: census code {match_how['census_code']}, state+name fallback {match_how['name']}, unmatched {match_how['none']} (of {n}).",
        f"- price series (>=8 valid yrs): {OUT.price_series_json.notna().sum()} / {n}; elnino spike: {OUT.price_elnino_spike_pct.notna().sum()}; volatility idx: {OUT.price_volatility_idx.notna().sum()}",
        f"- price_crop counts: {OUT.price_crop.value_counts().to_dict()}",
        f"- price_elnino_spike_pct (pp): {dist(OUT.price_elnino_spike_pct)}",
        f"- price_volatility_idx: {dist(OUT.price_volatility_idx)}",
        f"- El Nino years used {EN_YEARS}; neutral years from ONI helper (kharif-season mean ONI). Spike = mean % deviation from log-linear trend (El Nino) minus same (neutral); needs >=2 El Nino and >=3 neutral obs. Volatility = std of detrended log price (~CV of price around trend), 2000-2017, >=8 yrs, rank-normalised across districts.",
        f"- Chosen crop uses first of the district's top-5 APY crops that has an ICRISAT price series with >=8 yrs, else RICE then WHEAT.\n"]
print("prices done", round(time.time() - T0, 1))

# ════════════════════════════ 2. Poshan Tracker ════════════════════════════
pp = pd.read_csv(RAW / "09_population_malnutrition" / "idp_nfhs_poshan" / "Poshan_Statistics.csv", low_memory=False,
                 usecols=["date", "district_code", "children_measured_0_5_years", "severely_moderately_underweight",
                          "severely_or_moderately_stunted", "wasting_sam_or_mam"])
pp["lgd"] = pd.to_numeric(pp.district_code, errors="coerce")
pp = pp[pp.lgd.notna()].copy(); pp["lgd"] = pp.lgd.astype(int)
pp["date"] = pd.to_datetime(pp.date)
pp = pp.rename(columns={"children_measured_0_5_years": "meas", "severely_moderately_underweight": "uw",
                        "severely_or_moderately_stunted": "st", "wasting_sam_or_mam": "wa"})
# The three indicator columns are ALREADY percentages (0-100) of children measured, not counts.
pp = pp[(pp.meas >= 500) & pp.uw.notna() & (pp.uw > 0) & pp.st.notna() & (pp.st > 0)]  # uw/st==0 at >=500 kids = unreported
pp = pp.drop_duplicates(["lgd", "date"], keep="last").sort_values(["lgd", "date"])
last = pp.groupby("lgd").tail(1).set_index("lgd")
PS = pd.DataFrame(index=last.index)
PS["poshan_underweight_pct"] = last.uw.round(2)
PS["poshan_stunted_pct"] = last.st.round(2)
PS["poshan_wasted_pct"] = last.wa.where(last.wa > 0).round(2)  # 0 indistinguishable from <0.5% rounding / unreported -> null
PS["poshan_sam_pct"] = np.nan  # not published separately: only combined SAM+MAM ("wasting_sam_or_mam")
PS["poshan_as_of"] = last.date.dt.strftime("%Y-%m-%d")
PS["poshan_measured"] = last.meas.astype(int)
ser = {}
for l, g in pp.groupby("lgd"):
    g = g.tail(24)
    ser[l] = dumps({d.strftime("%Y-%m"): float(v) for d, v in zip(g.date, g.uw)})
PS["poshan_series_json"] = pd.Series(ser)
OUT = OUT.merge(PS.reset_index().rename(columns={"index": "lgd"}), on="lgd", how="left")
soc = pd.read_parquet(ART / "social_district.parquet")[["lgd", "underweight_nfhs6"]]
cm = OUT[["lgd", "poshan_underweight_pct"]].merge(soc, on="lgd").dropna()
corr_p = cm.poshan_underweight_pct.corr(cm.underweight_nfhs6); corr_s = cm.poshan_underweight_pct.corr(cm.underweight_nfhs6, method="spearman")
REP += ["## 2. Poshan Tracker\n",
        "- Columns `severely_moderately_underweight`, `severely_or_moderately_stunted`, `wasting_sam_or_mam` are already percentages of children measured (0-100, mostly integer-rounded), NOT counts; used as-is. SAM is not published separately (only SAM+MAM combined) -> `poshan_sam_pct` all null, `poshan_wasted_pct` = SAM+MAM.",
        f"- Rows with usable lgd: {len(pp):,} after filters (children_measured_0_5_years >= 500, underweight>0 and stunted>0 as 0 = unreported). Months {pp.date.min():%Y-%m} to {pp.date.max():%Y-%m}.",
        f"- Master coverage: {OUT.poshan_underweight_pct.notna().sum()} / {n}; wasted non-null {OUT.poshan_wasted_pct.notna().sum()}; series non-null {OUT.poshan_series_json.notna().sum()}",
        f"- as_of distribution: {OUT.poshan_as_of.value_counts().sort_index().tail(6).to_dict()} (older months = district stopped reporting >=500 valid)",
        f"- poshan_underweight_pct: {dist(OUT.poshan_underweight_pct)}",
        f"- poshan_stunted_pct: {dist(OUT.poshan_stunted_pct)}",
        f"- poshan_wasted_pct: {dist(OUT.poshan_wasted_pct)}",
        f"- poshan_measured: {dist(OUT.poshan_measured)}",
        f"- vs NFHS-6 underweight: n={len(cm)} Pearson r={corr_p:.3f}, Spearman={corr_s:.3f}; mean Poshan {cm.poshan_underweight_pct.mean():.1f} vs NFHS-6 {cm.underweight_nfhs6.mean():.1f} (diff {cm.poshan_underweight_pct.mean() - cm.underweight_nfhs6.mean():+.1f} pp)\n"]
print("poshan done", round(time.time() - T0, 1))

# ════════════════════════════ 3. Groundwater ════════════════════════════
GWD = RAW / "05_weather_drought_imd" / "idp_groundwater"
PRE_MONTHS = (4, 5, 6)
MAXD = 300.0  # drop physically implausible depths (state-board file has values up to 11,553 m)


def gw_load(f: str) -> pd.DataFrame:
    g = pd.read_csv(GWD / f, usecols=["date", "district_code", "station_name", "currentlevel"])
    g["lgd"] = pd.to_numeric(g.district_code, errors="coerce")
    g = g[g.lgd.notna()].copy(); g["lgd"] = g.lgd.astype(int)
    g["date"] = pd.to_datetime(g.date, errors="coerce")
    g = g[g.date.dt.month.isin(PRE_MONTHS) & g.currentlevel.between(0, MAXD)]
    g["year"] = g.date.dt.year
    # one value per station-year (median of Apr-Jun readings)
    return g.groupby(["lgd", "station_name", "year"], as_index=False).currentlevel.median()


def gw_district(sy: pd.DataFrame) -> pd.DataFrame:
    a = sy.groupby(["lgd", "year"]).currentlevel.agg(med="median", wells="size").reset_index()
    a = a[a.wells >= 5]
    res = {}
    for l, g in a.groupby("lgd"):
        g = g.sort_values("year")
        rec = dict(depth=float(g.med.iloc[-1]), year=int(g.year.iloc[-1]), wells=int(g.wells.iloc[-1]), decl=np.nan, nyrs=0)
        gg = g.tail(10)
        rec["nyrs"] = len(gg)
        if len(gg) >= 5:
            rec["decl"] = float(np.polyfit(gg.year.values.astype(float), gg.med.values, 1)[0])
        res[l] = rec
    return pd.DataFrame.from_dict(res, orient="index")


cg = gw_district(gw_load("CGWB_Changes_in_Depth_to_Water_Level.csv"))
sb = gw_district(gw_load("State_Groundwater_Boards_Changes_in_Depth_to_Water_Level.csv"))
cg["src"] = "CGWB"; sb["src"] = "State board"
gwd = pd.concat([cg, sb[~sb.index.isin(cg.index)]])
G = pd.DataFrame(index=gwd.index)
G["gw_premonsoon_depth_m"] = gwd.depth.round(2)
G["gw_decline_10y_m_per_yr"] = gwd.decl.round(3)
G["gw_latest_year"] = gwd.year
G["gw_n_wells"] = gwd.wells
G["gw_n_years_trend"] = gwd.nyrs.where(gwd.nyrs >= 5)
G["gw_source"] = gwd.src
OUT = OUT.merge(G.reset_index().rename(columns={"index": "lgd"}), on="lgd", how="left")
declw = OUT.gw_decline_10y_m_per_yr.clip(OUT.gw_decline_10y_m_per_yr.quantile(.01), OUT.gw_decline_10y_m_per_yr.quantile(.99))
z = lambda s: (s - s.mean()) / s.std(ddof=0)
comb = 0.5 * z(OUT.gw_premonsoon_depth_m.clip(upper=OUT.gw_premonsoon_depth_m.quantile(.99))) + 0.5 * z(declw)
OUT["gw_stress_idx"] = rank01(comb).round(4)
REP += ["## 3. Groundwater\n",
        f"- Depth = `currentlevel` (m below ground), pre-monsoon = Apr-Jun readings (median per station-year, then district median per year, need >=5 wells/yr); readings >{MAXD:.0f} m dropped as implausible. Latest year with >=5 wells used; trend = OLS slope over the last <=10 such years (need >=5). CGWB used where it yields a valid depth, else State Boards file.",
        f"- Coverage: depth {OUT.gw_premonsoon_depth_m.notna().sum()} / {n} (CGWB {int((OUT.gw_source == 'CGWB').sum())}, state boards {int((OUT.gw_source == 'State board').sum())}); decline {OUT.gw_decline_10y_m_per_yr.notna().sum()}; stress idx (needs both) {OUT.gw_stress_idx.notna().sum()}",
        f"- latest year distribution: {OUT.gw_latest_year.value_counts().sort_index().to_dict()}",
        f"- gw_premonsoon_depth_m: {dist(OUT.gw_premonsoon_depth_m)}",
        f"- gw_decline_10y_m_per_yr (+ = deepening): {dist(OUT.gw_decline_10y_m_per_yr)}",
        f"- gw_stress_idx: {dist(OUT.gw_stress_idx)} (depth winsorised p99, decline winsorised p1/p99 before z-scoring; rank-normalised 0-1)\n"]
print("gw done", round(time.time() - T0, 1))

# ════════════════════════════ 4. Cost of cultivation ════════════════════════════
co = pd.read_csv(RAW / "01_crop_apy_des" / "idp_related_agri" / "Cost_of_Cultivation.csv",
                 usecols=["year", "state_name", "crop_name", "cul_cost_c2", "main_product_value", "derived_yield"])
co["yr"] = co.year.str[:4].astype(int)
co = co.groupby(["state_name", "crop_name", "yr", "year"], as_index=False)[["cul_cost_c2", "main_product_value", "derived_yield"]].mean()
MIN_YR = 2014  # CoC latest year is 2021-22; ignore older rows as stale (nominal Rs)
co = co[co.yr >= MIN_YR].sort_values("yr").groupby(["state_name", "crop_name"]).tail(1).set_index(["state_name", "crop_name"])
APY2COC = {"Rice": "Paddy", "Paddy": "Paddy", "Wheat": "Wheat", "Maize": "Maize", "Jowar": "Jowar", "Bajra": "Bajra", "Ragi": "Ragi",
           "Gram": "Gram", "Arhar/Tur": "Tur (Arhar)", "Tur": "Tur (Arhar)", "Urad": "Urad", "Moong(Green Gram)": "Moong", "Moong": "Moong",
           "Masoor": "Masur", "Lentil": "Lentil", "Groundnut": "Groundnut", "Rapeseed &Mustard": "Rapeseed & Mustard (Toria/Taramira)",
           "Rapeseed & Mustard": "Rapeseed & Mustard (Toria/Taramira)", "Soyabean": "Soyabean", "Soybean": "Soyabean", "Sunflower": "Sunflower",
           "Sesamum": "Sesamum (Til)", "Safflower": "Safflower", "Niger Seed": "Nigerseed", "Cotton(Lint)": "Cotton", "Cotton": "Cotton",
           "Sugarcane": "Sugarcane", "Jute": "Jute", "Barley": "Barley", "Potato": "Potato", "Onion": "Onion", "Tapioca": "Tapioca"}
DROUGHT = {"Bajra": "Bajra", "Jowar": "Jowar", "Ragi": "Ragi", "Moong": "Moong", "Horse Gram": "Horse Gram", "Castor": "Castor"}


def coc_rec(state: str, apy_name: str, coc_name: str):
    k = (state, coc_name)
    if k not in co.index:
        return None
    r = co.loc[k]
    if pd.isna(r.cul_cost_c2) or pd.isna(r.main_product_value):
        return None
    return dict(crop=apy_name, year=r.year, cost_c2_per_ha=round(float(r.cul_cost_c2)), value_per_ha=round(float(r.main_product_value)),
                margin_per_ha=round(float(r.main_product_value - r.cul_cost_c2)),
                yield_q_ha=None if pd.isna(r.derived_yield) else round(float(r.derived_yield), 1))


cj, dj = [], []
for r in D.itertuples():
    lst, seen = [], set()
    for cn in top_crops(r.lgd):
        cc = APY2COC.get(cn)
        if cc and cc not in seen:
            seen.add(cc)
            x = coc_rec(r.state, cn, cc)
            if x: lst.append(x)
    cj.append(dumps(lst) if lst else None)
    dl = [x for x in (coc_rec(r.state, nm, cn) for nm, cn in DROUGHT.items()) if x]
    dj.append(dumps(dl) if dl else None)
C = pd.DataFrame(dict(lgd=D.lgd.values, coc_json=cj, coc_drought_tolerant_json=dj))
OUT = OUT.merge(C, on="lgd", how="left")
ncrop = OUT.coc_json.dropna().map(lambda s: len(json.loads(s)))
REP += ["## 4. Cost of cultivation\n",
        f"- State x crop rows {len(co)} (latest year per pair, >= {MIN_YR}); all CoC states match master state names.",
        f"- coc_json non-null {OUT.coc_json.notna().sum()} / {n}; crops matched per district: {ncrop.value_counts().sort_index().to_dict()}",
        f"- coc_drought_tolerant_json non-null {OUT.coc_drought_tolerant_json.notna().sum()} / {n} (Horse Gram and Castor are not in the CoC file; Bajra/Jowar/Ragi/Moong only where the state surveyed them).",
        "- margin = main_product_value - cul_cost_c2 (Rs/ha, nominal, excludes by-product value and uses full C2 cost incl. imputed family labour/land rent so it is a conservative economic margin); yield_q_ha = derived_yield (quintal/ha; sugarcane/tubers on fresh-weight basis).\n"]

# ── write ────────────────────────────────────────────────────────────────────
ORDER = ["lgd", "price_crop", "price_n_years", "price_match", "price_elnino_spike_pct", "price_volatility_idx", "price_series_json",
         "poshan_underweight_pct", "poshan_stunted_pct", "poshan_wasted_pct", "poshan_sam_pct", "poshan_as_of", "poshan_measured", "poshan_series_json",
         "gw_premonsoon_depth_m", "gw_decline_10y_m_per_yr", "gw_stress_idx", "gw_latest_year", "gw_n_wells", "gw_n_years_trend", "gw_source",
         "coc_json", "coc_drought_tolerant_json"]
OUT = OUT[ORDER].sort_values("lgd").reset_index(drop=True)
assert len(OUT) == 753 and OUT.lgd.is_unique
for c in ("price_n_years", "poshan_measured", "gw_latest_year", "gw_n_wells", "gw_n_years_trend"):
    OUT[c] = OUT[c].astype("Int64")
OUT.to_parquet(ART / "extra_district.parquet", index=False)

REP += ["## Coverage summary (non-null of 753)\n", "```"] + [f"{c:28s} {OUT[c].notna().sum():4d}" for c in ORDER[1:]] + ["```\n", "## Sample districts\n"]
for l in (486, 358, 191, 673, 502):
    r = OUT[OUT.lgd == l].iloc[0]; nm = D[D.lgd == l].iloc[0]
    REP.append(f"### {l} {nm.district}, {nm.state}")
    for c in ORDER[1:]:
        v = r[c]
        if isinstance(v, str) and len(v) > 400: v = v[:400] + "..."
        REP.append(f"- {c}: {None if (not isinstance(v, str) and pd.isna(v)) else v}")
    REP.append("")
REP += ["## Caveats\n",
        "- ICRISAT (unapportioned, ~537 districts) ends 2020 and predates new districts; new/split districts only match by name, others stay null (no parent inheritance). Prices are nominal; the log-linear trend absorbs inflation. Price crop varies by district, so volatility ranks are across mixed crops.",
        "- Poshan percentages are integer-rounded administrative (AWC-measured) values; self-reported coverage varies, and Poshan reads lower than NFHS survey. Use as a trend/live signal, not level-comparable to NFHS. SAM alone is unavailable.",
        "- Groundwater: CGWB coverage collapses after 2020, so many districts' 'latest' year is 2019-21; district median over a changing well panel can alias composition change into the trend; state-board wells may use different datum conventions.",
        "- CoC is state-level (not district), latest year 2021-22 at best, nominal Rs; use as relative economics, not district-specific truth."]
(ART / "reports" / "03b_extra_report.md").write_text("\n".join(REP))
print("done", round(time.time() - T0, 1), "s")
