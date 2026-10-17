#!/usr/bin/env python3
"""01_crops.py -- crop area / production / yield panel, structural vulnerability covariates and
El Nino yield sensitivity for AnnaDrishti.

Outputs (all under artifacts/, rerunnable, outputs overwritten):
  crops_district_year.parquet   lgd x crop_year panel (kharif year int), harmonised ha / t / t-per-ha
  crops_latest.parquet          one row per master district: SCHEMA.md `crops` block (+ extra covariates)
  yield_sensitivity.parquet     one row per master district: yield deviation El Nino vs Neutral (and deficit years)
  timeseries_crops/{lgd}.json   yield / area / production time series per district
  reports/01_crops_report.md    QA report

Key data facts discovered while building this (see report for numbers):
  * UPAG file is in hectare / tonne / kg-per-ha (NOT '000) -- unit factor is auto-detected against APY overlap.
  * APY contains 'Total' season rows = sum of the other seasons of the same crop -> dropped (double counting).
  * APY cotton production is in 170 kg bales, jute/mesta in 180 kg bales (UPAG has tonnes) -> converted to tonnes.
  * UPAG only covers ~30 major crops; APY covers ~120 (horticulture, plantation) -> APY preferred for gross area.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ART, RAW, FOODGRAIN_GROUPS, crop_group, crop_year_to_int,  # noqa: E402
                    districts, enso_phase_by_monsoon_year, read_idp, save_json)

# --------------------------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------------------------
APY_CSV = RAW / "01_crop_apy_des" / "IDP_crop_wise_area_production_yield_district_1997-2023.csv"
UPAG_CSV = RAW / "01_crop_apy_des" / "IDP_cropwise_area_production_yield_UPAG.csv"
PMFBY_CSV = RAW / "01_crop_apy_des" / "idp_related_agri" / "_PMFBY_District_Level.csv"
LANDUSE = RAW / "10_cropping_pattern_resilience" / "idp_land_use_statistics"
AGCENSUS_CSV = RAW / "04_agri_census_farmers" / "idp_agricultural_census" / "District_level_AgCensus_Non_Crop.csv"

GROUPS = ["cereals", "millets", "pulses", "oilseeds", "cash"]          # reported groups
SENS_GROUPS = ["cereals", "millets", "pulses", "oilseeds"]            # sensitivity groups
LATEST_CAP = 2023            # 2024-25 UPAG is advance/provisional -> not used for the "latest" snapshot
COMPLETE_FLOOR = 0.30        # latest-year foodgrain area must be >= 30 % of trailing-5y median (truncated-data guard)
SPLIT_RATIO = 0.90           # ...and >= 90 % in state-years where new (non-master) districts appear (parent lost area to a split)
STALE_BEFORE = 2018          # latest_stale flag: snapshot older than this
FIRST_ANALOG_YEAR = 1998     # 1997-98 APY is thin (498 districts) -> in detrending, but not an El Nino/neutral/baseline year
MAX_MISSING_PROD_SHARE = 0.15
MIN_AREA_HA = 500            # group-year yields from < 500 ha are rounding noise (APY reports in 100 ha steps)
MIN_LIN_YEARS, MIN_ANY_YEARS = 12, 6
MIN_ANALOG, MIN_BASE = 3, 3
DEFICIT_YEARS = [2002, 2004, 2009, 2012, 2014, 2015, 2023]   # all-India monsoon deficit years (given)
DEV_CLIP = 100.0             # clip |% deviation| (guards against data glitches)

# APY crop names -> UPAG names so the two sources are comparable
NAME_MAP = {
    "Moong(Green Gram)": "Moong", "Arhar/Tur": "Tur", "Soyabean": "Soybean",
    "Rapeseed &Mustard": "Rapeseed & Mustard", "Cotton(Lint)": "Cotton", "Castor Seed": "Castorseed",
    "Niger Seed": "Nigerseed", "Guar Seed": "Guarseed", "Sannhamp": "Sannhemp", "Masoor": "Lentil",
    "Other Kharif Pulses": "Other Pulses", "Other Rabi Pulses": "Other Pulses",
    "Other Summer Pulses": "Other Pulses", "Other Misc. Pulses": "Other Pulses",
}
# APY production units that are not tonnes (verified on APY/UPAG overlap: ratio exactly 0.17 / 0.18)
BALE_TO_TONNE = {"Cotton(Lint)": 0.17, "Jute": 0.18, "Mesta": 0.18, "Jute & Mesta": 0.18}
# common.crop_group keyword fallback mis-classifies a few names -> explicit overrides
GROUP_OVERRIDE = {
    "Peas (Vegetable)": "other", "Pear": "other", "Peach": "other",        # 'pea' substring
    "Guarseed": "other", "Sannhemp": "other", "Perilla": "other",
    "Korra": "millets", "Samai": "millets", "Varagu": "millets",           # small millets
    "Kapas": "cash", "Jute & Mesta": "cash",
    "Ricebean (Nagadal)": "pulses", "Rajmash Kholar": "pulses", "Lab-Lab": "pulses",
}
SEASON_GRP = {"Kharif": "kharif", "Autumn": "kharif", "Winter": "kharif", "Rabi": "rabi",
              "Summer": "summer", "Whole Year": "whole"}


def group_of(name: str) -> str:
    return GROUP_OVERRIDE.get(name) or crop_group(name)


# --------------------------------------------------------------------------------------------
# 1. load + harmonise the two crop sources into one long table: cy, lgd, crop, grp, season, area_ha, prod_t
# --------------------------------------------------------------------------------------------
def _finish_long(df: pd.DataFrame, src: str) -> pd.DataFrame:
    df = df.copy()
    df["grp"] = df["crop"].map({c: group_of(c) for c in df["crop"].unique()})
    df["season_grp"] = df["season"].map(SEASON_GRP)
    df["src"] = src
    return df[["cy", "lgd", "state_code", "crop", "grp", "season", "season_grp", "area_ha", "prod_t", "src"]]


def load_apy(stats: dict) -> pd.DataFrame:
    a = read_idp(APY_CSV)
    stats["apy_rows_in"] = len(a)
    a["cy"] = a["year"].map(crop_year_to_int)
    # 'Total' season rows duplicate the sum of the other seasons -> keep only if a crop has no other season row
    key = ["cy", "lgd", "crop_name"]
    has_other = a[a.season != "Total"].groupby(key).size().rename("n_other").reset_index()
    a = a.merge(has_other, on=key, how="left")
    keep = (a.season != "Total") | a.n_other.isna()
    stats["apy_total_rows_dropped"] = int((~keep).sum())
    a = a[keep].copy()
    a = a.dropna(subset=["lgd"])
    # bale -> tonne
    fac = a["crop_name"].map(BALE_TO_TONNE).fillna(1.0)
    a["prod_t"] = a["production"] * fac
    a["area_ha"] = a["area"]            # APY already ha / t
    a["crop"] = a["crop_name"].replace(NAME_MAP)
    out = _finish_long(a, "APY")
    stats["apy_rows_used"] = len(out)
    return out


def load_upag(stats: dict) -> pd.DataFrame:
    u = read_idp(UPAG_CSV)
    stats["upag_rows_in"] = len(u)
    stats["upag_rows_no_lgd"] = int(u["lgd"].isna().sum())
    stats["upag_no_lgd_names"] = sorted(u.loc[u.lgd.isna(), "district_name"].dropna().unique().tolist())
    u = u.dropna(subset=["lgd"]).copy()
    u["cy"] = u["year"].map(crop_year_to_int)
    u["area_ha"], u["prod_t"] = u["area"], u["production"]   # factors fixed up after overlap check
    u["crop"] = u["crop_name"]
    return _finish_long(u, "UPAG")


def check_upag_units(apy: pd.DataFrame, upag: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """Compare UPAG vs APY on overlapping (year, lgd, crop, season) rows; auto-detect a x1000 unit issue."""
    k = ["cy", "lgd", "crop", "season"]
    a = apy.groupby(k)[["area_ha", "prod_t"]].sum(min_count=1)
    u = upag.groupby(k)[["area_ha", "prod_t"]].sum(min_count=1)
    j = a.join(u, lsuffix="_apy", rsuffix="_upag", how="inner")
    j = j[(j.area_ha_apy > 0) & (j.area_ha_upag > 0)]
    r_area = float(j.area_ha_upag.sum() / j.area_ha_apy.sum())
    # production ratio on crops with no unit conversion in APY
    jj = j.reset_index()
    jj = jj[~jj.crop.isin(["Cotton", "Jute", "Mesta"])]
    r_prod = float(jj.prod_t_upag.sum() / jj.prod_t_apy.sum())
    area_factor = 1000.0 if 500 < r_area < 2000 else (1.0 if 0.5 < r_area < 2.0 else np.nan)
    prod_factor = 1000.0 if 500 < r_prod < 2000 else (1.0 if 0.5 < r_prod < 2.0 else np.nan)
    if np.isnan(area_factor) or np.isnan(prod_factor):
        raise RuntimeError(f"UPAG/APY overlap ratios not interpretable: area {r_area}, prod {r_prod}")
    stats.update(upag_area_ratio=r_area, upag_prod_ratio=r_prod, upag_area_factor=area_factor,
                 upag_prod_factor=prod_factor, overlap_rows=len(j))
    # bale conversion sanity (APY raw cotton production vs UPAG tonnes)
    chk = {}
    for crop in ("Cotton", "Jute", "Mesta"):
        s = j.reset_index()
        s = s[s.crop == crop]
        chk[crop] = float(s.prod_t_upag.sum() / s.prod_t_apy.sum()) if len(s) else np.nan
    stats["bale_check_ratio_after_conversion"] = chk   # ~1.0 => conversion factor right
    upag = upag.copy()
    upag["area_ha"] *= area_factor
    upag["prod_t"] *= prod_factor
    return upag


# --------------------------------------------------------------------------------------------
# 2. aggregate long table -> crop-level and district-year panel
# --------------------------------------------------------------------------------------------
def crop_level(long: pd.DataFrame) -> pd.DataFrame:
    """Aggregate over seasons: one row per (src, cy, lgd, crop). area_wp = area on rows with production reported."""
    d = long.copy()
    d["area_wp"] = d["area_ha"].where(d["prod_t"].notna())
    c = (d.groupby(["src", "cy", "lgd", "crop", "grp"], as_index=False)
           .agg(area_ha=("area_ha", "sum"), prod_t=("prod_t", lambda s: s.sum(min_count=1)),
                area_wp=("area_wp", "sum")))
    return c


def district_panel(c: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    """Per (src, cy, lgd) summary from the crop-level table."""
    k = ["src", "cy", "lgd"]
    g = (c.groupby(k + ["grp"])
           .agg(area_ha=("area_ha", "sum"), prod_t=("prod_t", lambda s: s.sum(min_count=1)),
                area_wp=("area_wp", "sum")).reset_index())
    wide = g.pivot(index=k, columns="grp", values=["area_ha", "prod_t", "area_wp"])
    P = pd.DataFrame(index=wide.index)
    for grp in GROUPS + ["other"]:
        P[f"{grp}_area_ha"] = wide[("area_ha", grp)] if ("area_ha", grp) in wide else np.nan
        if grp == "other":
            continue
        P[f"{grp}_prod_t"] = wide[("prod_t", grp)] if ("prod_t", grp) in wide else np.nan
        awp = wide[("area_wp", grp)] if ("area_wp", grp) in wide else np.nan
        P[f"_{grp}_awp"] = awp
    # foodgrain = cereals + millets + pulses ('other' excluded)
    fg = list(FOODGRAIN_GROUPS)
    P["foodgrain_area_ha"] = P[[f"{x}_area_ha" for x in fg]].sum(axis=1, min_count=1)
    P["foodgrain_prod_t"] = P[[f"{x}_prod_t" for x in fg]].sum(axis=1, min_count=1)
    # zero production on a positive aggregated area is a reporting gap (not a crop failure) -> missing
    for col in ("foodgrain_prod_t", "cereals_prod_t"):
        P[col] = P[col].where(P[col] != 0)
    P["_fg_awp"] = P[[f"_{x}_awp" for x in fg]].sum(axis=1, min_count=1)
    P["fg_area_missing_prod_share"] = 1 - P["_fg_awp"] / P["foodgrain_area_ha"]
    # yields (t/ha) = production / area-with-production; cash is a mix of units (cane t, lint t, ...) -> null
    for grp in ["foodgrain"] + GROUPS:
        awp = P["_fg_awp"] if grp == "foodgrain" else P[f"_{grp}_awp"]
        y = P[f"{grp}_prod_t"] / awp.where(awp > 0)
        P[f"{grp}_yield_t_ha"] = np.nan if grp == "cash" else y
    # gross cropped area = all crops incl. 'other' (horticulture/plantation in APY)
    P["gross_cropped_area_ha"] = c.groupby(k).area_ha.sum()
    # crop diversity on crop-level areas (all crops, area>0)
    cc = c[c.area_ha > 0].copy()
    cc["share"] = cc.area_ha / cc.groupby(k).area_ha.transform("sum")
    P["simpson_div"] = 1 - (cc.share ** 2).groupby([cc.src, cc.cy, cc.lgd]).sum()
    P["n_crops"] = cc.groupby(k).size()
    top = cc.sort_values("area_ha", ascending=False).groupby(k).head(1).set_index(k)
    P["top_crop"] = top["crop"]
    P["top_crop_share"] = top["share"]
    # kharif : rabi area ratio (all crops, 'Whole Year' and 'Summer' excluded). Kharif = Kharif+Autumn+Winter.
    s = long.groupby(k + ["season_grp"]).area_ha.sum().unstack("season_grp")
    kr = s.get("kharif") / s.get("rabi").where(s.get("rabi") > 0)
    P["kharif_rabi_ratio"] = kr
    P = P.drop(columns=[x for x in P.columns if x.startswith("_")]).reset_index()
    return P


def combine_sources(pa: pd.DataFrame, pu: pd.DataFrame) -> pd.DataFrame:
    """APY preferred. From 2020 on, UPAG replaces APY where UPAG foodgrain area exceeds APY by >5 %
    (APY partial coverage per DES). UPAG-only years (2023+) use UPAG. UPAG foodgrain/gross are always kept in upag_* columns."""
    k = ["cy", "lgd"]
    a = pa.drop(columns="src").set_index(k)
    u = pu.drop(columns="src").set_index(k)
    idx = a.index.union(u.index)
    a, u = a.reindex(idx), u.reindex(idx)
    has_a = a["foodgrain_area_ha"].notna() | a["gross_cropped_area_ha"].notna()
    has_u = u["foodgrain_area_ha"].notna() | u["gross_cropped_area_ha"].notna()
    cy = idx.get_level_values("cy")
    use_u = (~has_a) | ((cy >= 2020) & has_u & (u["foodgrain_area_ha"] > 1.05 * a["foodgrain_area_ha"]))
    use_u = pd.Series(np.asarray(use_u), index=idx)
    P = a.where(~use_u, u)
    P["source"] = np.where(use_u, "UPAG", "APY")
    P["upag_foodgrain_area_ha"] = u["foodgrain_area_ha"]
    P["upag_foodgrain_prod_t"] = u["foodgrain_prod_t"]
    P["upag_gross_area_ha"] = u["gross_cropped_area_ha"]
    P = P[has_a | has_u].reset_index().rename(columns={"cy": "crop_year"})
    return P


def season_foodgrain(long: pd.DataFrame, src: str) -> pd.DataFrame:
    """v4 (seasons): season-split foodgrain (cereals + millets + pulses) per (cy, lgd) for one source.
    kharif = Kharif + Autumn + Winter season labels, rabi = Rabi; Summer / Whole Year are in neither.
    Yield = production / area of rows that report production (same convention as the all-season foodgrain yield);
    zero production on positive area is a reporting gap -> missing. Returns crop_year, lgd, source + extra columns."""
    d = long[long.grp.isin(FOODGRAIN_GROUPS) & long.season_grp.isin(["kharif", "rabi"])].copy()
    d["area_wp"] = d["area_ha"].where(d["prod_t"].notna())
    g = (d.groupby(["cy", "lgd", "season_grp"])
           .agg(area_ha=("area_ha", "sum"), prod_t=("prod_t", lambda s: s.sum(min_count=1)), area_wp=("area_wp", "sum"))
           .reset_index())
    g["prod_t"] = g["prod_t"].where(g["prod_t"] != 0)
    g["yield_t_ha"] = g["prod_t"] / g["area_wp"].where(g["area_wp"] > 0)
    w = g.pivot(index=["cy", "lgd"], columns="season_grp", values=["prod_t", "yield_t_ha", "area_ha"])
    out = pd.DataFrame(index=w.index)
    for sg in ("kharif", "rabi"):
        for col, name in (("yield_t_ha", f"{sg}_fg_yield_t_ha"), ("prod_t", f"{sg}_fg_prod_t"), ("area_ha", f"{sg}_fg_area_ha")):
            out[name] = w[(col, sg)] if (col, sg) in w.columns else np.nan
    # rabi pulses (gram, lentil, peas ...) production, used for the rabi pre-positioning quantity in 04_risk
    pl = long[(long.grp == "pulses") & (long.season_grp == "rabi")].groupby(["cy", "lgd"]).prod_t.sum(min_count=1)
    out["rabi_pulses_prod_t"] = pl.reindex(out.index)
    out = out.reset_index().rename(columns={"cy": "crop_year"})
    out["source"] = src
    return out


# --------------------------------------------------------------------------------------------
# 3. structural covariates: irrigation, small/marginal holdings, PMFBY
# --------------------------------------------------------------------------------------------
def irrigation_share(master_lgds) -> pd.DataFrame:
    """irrigated_share = gross irrigated area / gross cropped area (land-use statistics), latest valid year per district.
    Numerator: Sources_of_Irrigation 'Gross Irrigated Area' (sum of sources); fallback Crop_Wise_Irrigated_Area.
    Zero numerators are treated as missing (the table reports 0/NaN for non-reporting districts)."""
    k = ["cy", "lgd"]
    s = read_idp(LANDUSE / "Sources_of_Irrigation.csv")
    s = s[s.irrigated_area_type == "Gross Irrigated Area"].dropna(subset=["lgd"])
    s["cy"] = s.year.map(crop_year_to_int)
    num1 = s.groupby(k).irrigated_area.sum(min_count=1).rename("irr_src")
    i = read_idp(LANDUSE / "Crop_Wise_Irrigated_Area.csv").dropna(subset=["lgd"])
    i["cy"] = i.year.map(crop_year_to_int)
    num2 = i.groupby(k).area.sum(min_count=1).rename("irr_crop")
    a = read_idp(LANDUSE / "Area_Under_Crops.csv")
    a = a[a.area_category.isna()].dropna(subset=["lgd"])
    a["cy"] = a.year.map(crop_year_to_int)
    gca = a.groupby(k).area.sum(min_count=1).rename("gca")
    d = pd.concat([num1, num2, gca], axis=1).reset_index()
    d["irr"] = d.irr_src.where(d.irr_src > 0).fillna(d.irr_crop.where(d.irr_crop > 0))
    d["share"] = d.irr / d.gca.where(d.gca > 0)
    d = d[d.share.notna() & (d.share <= 1.05) & d.lgd.isin(master_lgds)]
    d["share"] = d.share.clip(upper=1.0)
    last = d.sort_values("cy").groupby("lgd").tail(1).set_index("lgd")
    return pd.DataFrame({"irrigated_share": last.share.round(4), "rainfed_share": (1 - last.share).round(4),
                         "irrigation_year": last.cy})


def small_marginal(master_lgds) -> pd.DataFrame:
    """Share of operational holdings (count) < 2 ha (Marginal + Small), latest census year per district.
    Social groups (SC/ST/Others/Institutional) are mutually exclusive -> summed for the total."""
    c = read_idp(AGCENSUS_CSV).dropna(subset=["lgd"])
    c["cy"] = c.year.map(crop_year_to_int)
    c["hol_no"] = pd.to_numeric(c.hol_no, errors="coerce")
    tot = c.groupby(["cy", "lgd"]).hol_no.sum(min_count=1)
    sm = c[c.farm_size_category.isin(["Marginal", "Small"])].groupby(["cy", "lgd"]).hol_no.sum(min_count=1)
    d = pd.concat([tot.rename("tot"), sm.rename("sm")], axis=1).reset_index()
    d["share"] = d.sm / d.tot.where(d.tot > 0)
    d = d[d.share.notna() & d.lgd.isin(master_lgds)]
    last = d.sort_values("cy").groupby("lgd").tail(1).set_index("lgd")
    return pd.DataFrame({"small_marginal_share": last.share.round(4), "small_marginal_year": last.cy})


def pmfby(master_lgds) -> pd.DataFrame:
    """Insured farmers (PMFBY scheme only), summed over seasons and insurance rows (= farmer-seasons) in the
    latest year with data per district."""
    p = read_idp(PMFBY_CSV).dropna(subset=["lgd"])
    p = p[p.scheme == "PMFBY"]
    p["cy"] = pd.to_numeric(p.year, errors="coerce")
    d = p.groupby(["cy", "lgd"]).farmer_count.sum(min_count=1).reset_index()
    d = d[(d.farmer_count > 0) & d.lgd.isin(master_lgds)]
    last = d.sort_values("cy").groupby("lgd").tail(1).set_index("lgd")
    return pd.DataFrame({"pmfby_farmers": last.farmer_count.round(0), "pmfby_year": last.cy})


# --------------------------------------------------------------------------------------------
# 4. latest-year snapshot
# --------------------------------------------------------------------------------------------
def pick_latest(P: pd.DataFrame, split_sy: set, state_of: dict) -> pd.DataFrame:
    """Latest crop year <= LATEST_CAP with foodgrain production present AND 'complete':
      * < 15 % of foodgrain area lacks a production figure;
      * foodgrain area >= 30 % of the trailing-5-year median (guards truncated/partial years);
      * in (state, year) pairs where new districts that are NOT in the polygon master report data (district splits:
        Rajasthan, MP, Chhattisgarh, Nagaland, Sikkim 2022+), foodgrain area >= 90 % of the trailing median, i.e. the parent
        polygon has not lost area to a child district.
    Real inter-annual swings and long declines (hill districts) are deliberately NOT rejected.
    Fallback: latest year with production (latest_complete=False)."""
    P = P.sort_values(["lgd", "crop_year"]).copy()
    ref = P.groupby("lgd").foodgrain_area_ha.transform(lambda s: s.shift(1).rolling(5, min_periods=3).median())
    P["fg_area_ratio_prior5"] = P.foodgrain_area_ha / ref
    r = P.fg_area_ratio_prior5
    split = pd.Series([(state_of.get(l), y) in split_sy for l, y in zip(P.lgd, P.crop_year)], index=P.index)
    ok_base = P.foodgrain_prod_t.notna() & (P.foodgrain_area_ha > 0) & (P.crop_year <= LATEST_CAP)
    P["complete"] = (ok_base & (r.isna() | (r >= COMPLETE_FLOOR)) & (~split | r.isna() | (r >= SPLIT_RATIO))
                     & (P.fg_area_missing_prod_share.fillna(0) <= MAX_MISSING_PROD_SHARE))
    comp = P[P.complete].groupby("lgd").tail(1)
    fb = P[ok_base & ~P.lgd.isin(comp.lgd)].groupby("lgd").tail(1)
    out = pd.concat([comp.assign(latest_complete=True), fb.assign(latest_complete=False)])
    return out.set_index("lgd")


def top_crops_json(c: pd.DataFrame, sel: pd.DataFrame) -> pd.Series:
    """Top-5 crops by area (share of gross cropped area, yield t/ha) for the chosen (lgd, year, source)."""
    s = sel.reset_index()[["lgd", "crop_year", "source", "gross_cropped_area_ha"]].rename(
        columns={"crop_year": "cy", "source": "src"})
    t = c.merge(s, on=["lgd", "cy", "src"])
    t = t[t.area_ha > 0].sort_values(["lgd", "area_ha"], ascending=[True, False]).groupby("lgd").head(5)
    t["share"] = (t.area_ha / t.gross_cropped_area_ha).round(4)
    t["yield_t_ha"] = (t.prod_t / t.area_wp.where(t.area_wp > 0)).round(3)

    def mk(g):
        return [{"crop": r.crop, "share": float(r.share),
                 "yield_t_ha": None if pd.isna(r.yield_t_ha) else float(r.yield_t_ha),
                 "area_ha": round(float(r.area_ha), 1)} for r in g.itertuples()]
    return t.groupby("lgd").apply(mk)


def yield_cv10(P: pd.DataFrame, sel: pd.DataFrame) -> pd.Series:
    """CV (std ddof=1 / mean) of foodgrain yield over the 10 crop years ending at each district's latest year; >=5 obs."""
    w = P.pivot(index="lgd", columns="crop_year", values="foodgrain_yield_t_ha")
    out = {}
    for lgd, yr in sel.crop_year.items():
        if lgd not in w.index:
            continue
        v = w.loc[lgd, [y for y in w.columns if yr - 9 <= y <= yr]].dropna()
        out[lgd] = float(v.std(ddof=1) / v.mean()) if len(v) >= 5 and v.mean() > 0 else np.nan
    return pd.Series(out, name="yield_cv10")


# --------------------------------------------------------------------------------------------
# 5. yield sensitivity to El Nino / monsoon deficit
# --------------------------------------------------------------------------------------------
def pct_dev_from_trend(Y: pd.DataFrame) -> np.ndarray:
    """% deviation of yield from a per-district trend: OLS linear in year if >= MIN_LIN_YEARS obs, else centred 5-year
    rolling median (>= MIN_ANY_YEARS obs required). Vectorised across districts. NaN where trend <= 0."""
    yrs = Y.columns.to_numpy(float) - 2010.0
    V = Y.to_numpy(float)
    M = ~np.isnan(V)
    n = M.sum(1).astype(float)
    V0, X = np.where(M, V, 0.0), np.where(M, yrs[None, :], 0.0)
    sx, sy, sxx, sxy = X.sum(1), V0.sum(1), (X * X).sum(1), (X * V0).sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        den = n * sxx - sx ** 2
        slope = (n * sxy - sx * sy) / den
        icpt = (sy - slope * sx) / n
        lin = icpt[:, None] + slope[:, None] * yrs[None, :]
        roll = Y.T.rolling(5, center=True, min_periods=3).median().T.to_numpy()
        trend = np.where((n >= MIN_LIN_YEARS)[:, None], lin, roll)
        trend = np.where((n >= MIN_ANY_YEARS)[:, None], trend, np.nan)
        trend = np.where(trend > 0, trend, np.nan)
        dev = (V - trend) / trend * 100.0
    return np.clip(dev, -DEV_CLIP, DEV_CLIP)


def analog_effect(D: np.ndarray, cols_a: np.ndarray, cols_b: np.ndarray):
    """mean(dev in analog years) - mean(dev in baseline years); NaN unless >= MIN_ANALOG analog and >= MIN_BASE baseline obs."""
    A, B = D[:, cols_a], D[:, cols_b]
    na, nb = (~np.isnan(A)).sum(1), (~np.isnan(B)).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ma, mb = np.nansum(A, 1) / na, np.nansum(B, 1) / nb
    eff = np.where((na >= MIN_ANALOG) & (nb >= MIN_BASE), ma - mb, np.nan)
    return eff, na


def sensitivity(P: pd.DataFrame, master_lgds, years, phases: dict) -> pd.DataFrame:
    yrs = np.array(years)
    inwin = yrs >= FIRST_ANALOG_YEAR
    el = np.array([phases.get(y) == "El Niño" for y in yrs]) & inwin
    ne = np.array([phases.get(y) == "Neutral" for y in yrs]) & inwin
    de = np.isin(yrs, DEFICIT_YEARS)
    nde = ~de & inwin

    def wide(col, area_col):
        w = P.pivot(index="lgd", columns="crop_year", values=col).reindex(index=master_lgds, columns=years)
        a = P.pivot(index="lgd", columns="crop_year", values=area_col).reindex(index=master_lgds, columns=years)
        w = w.where(a >= MIN_AREA_HA)
        # drop foodgrain years where >30 % of area lacks a production figure
        return w

    series = {"foodgrain": wide("foodgrain_yield_t_ha", "foodgrain_area_ha")}
    miss = P.pivot(index="lgd", columns="crop_year", values="fg_area_missing_prod_share") \
            .reindex(index=master_lgds, columns=years)
    series["foodgrain"] = series["foodgrain"].where(~(miss > 0.30))
    for g in SENS_GROUPS:
        series[g] = wide(f"{g}_yield_t_ha", f"{g}_area_ha")

    out = pd.DataFrame(index=pd.Index(master_lgds, name="lgd"))
    res = {}
    for name, Y in series.items():
        D = pct_dev_from_trend(Y)
        e1, n1 = analog_effect(D, np.where(el)[0], np.where(ne)[0])
        e2, n2 = analog_effect(D, np.where(de)[0], np.where(nde)[0])
        res[name] = (e1, n1, e2, n2)
    out["foodgrain_elnino_pct"] = res["foodgrain"][0]
    out["n_elnino_years"] = res["foodgrain"][1]
    out["foodgrain_deficit_year_pct"] = res["foodgrain"][2]
    out["n_deficit_years"] = res["foodgrain"][3]
    for g in SENS_GROUPS:
        out[f"{g}_elnino_pct"] = res[g][0]
        out[f"{g}_deficit_year_pct"] = res[g][2]
    out["n_neutral_years"] = int(ne.sum())
    # null the count where the effect itself is null? keep counts (diagnostic) but effect null per rule
    rnd = lambda v: None if pd.isna(v) else round(float(v), 2)  # noqa: E731
    out["by_group_json"] = [__import__("json").dumps({g: rnd(r[f"{g}_elnino_pct"]) for g in SENS_GROUPS})
                            for _, r in out.iterrows()]
    out["by_group_deficit_json"] = [__import__("json").dumps({g: rnd(r[f"{g}_deficit_year_pct"]) for g in SENS_GROUPS})
                                    for _, r in out.iterrows()]
    for c in [x for x in out.columns if x.endswith("_pct")]:
        out[c] = out[c].round(2)
    return out.reset_index()


# --------------------------------------------------------------------------------------------
# 6. main
# --------------------------------------------------------------------------------------------
def main():
    import json
    stats: dict = {}
    master = districts()
    mlgds = master.lgd.tolist()
    for p in (ART / "reports", ART / "timeseries_crops"):
        p.mkdir(parents=True, exist_ok=True)

    # ---- load, harmonise
    apy = load_apy(stats)
    upag = load_upag(stats)
    upag = check_upag_units(apy, upag, stats)

    # ---- master matching on raw rows
    for nm, df in (("apy", apy), ("upag", upag)):
        l = set(df.lgd.astype(int).unique())
        stats[f"{nm}_lgds"] = len(l)
        notin = sorted(l - set(mlgds))
        stats[f"{nm}_lgds_not_in_master"] = notin
        stats[f"{nm}_rows_not_in_master"] = int((~df.lgd.isin(mlgds)).sum())
    names = pd.concat([read_idp(UPAG_CSV)[["lgd", "district_name", "state_name"]],
                       read_idp(APY_CSV)[["lgd", "district_name", "state_name"]]]).drop_duplicates("lgd").set_index("lgd")
    stats["unmatched_names"] = {int(l): f"{names.loc[l, 'district_name']} ({names.loc[l, 'state_name']})"
                                for l in sorted(set(stats["apy_lgds_not_in_master"]) | set(stats["upag_lgds_not_in_master"]))
                                if l in names.index}
    # (state, year) pairs where new districts outside the polygon master report data -> parents may have lost area
    both = pd.concat([apy, upag])
    dropped = both[~both.lgd.isin(mlgds)]
    split_sy = set(zip(dropped.state_code.astype(int), dropped.cy.astype(int)))
    apy, upag = apy[apy.lgd.isin(mlgds)].copy(), upag[upag.lgd.isin(mlgds)].copy()
    apy["lgd"], upag["lgd"] = apy.lgd.astype(int), upag.lgd.astype(int)
    state_of = pd.concat([apy, upag]).drop_duplicates("lgd").set_index("lgd").state_code.astype(int).to_dict()

    # ---- aggregate
    c_apy, c_upag = crop_level(apy), crop_level(upag)
    c_all = pd.concat([c_apy, c_upag], ignore_index=True)
    pa = district_panel(c_apy, apy)
    pu = district_panel(c_upag, upag)
    P = combine_sources(pa, pu)
    P["lgd"] = P.lgd.astype(int)
    P["crop_year"] = P.crop_year.astype(int)

    # v4: season-split foodgrain (additive columns; each row takes the season split of the source chosen for that district-year)
    SF = pd.concat([season_foodgrain(apy, "APY"), season_foodgrain(upag, "UPAG")], ignore_index=True)
    SF["lgd"], SF["crop_year"] = SF.lgd.astype(int), SF.crop_year.astype(int)
    P = P.merge(SF, on=["crop_year", "lgd", "source"], how="left")
    for sg in ("kharif", "rabi"):       # same glitch guard as the all-season yield
        P.loc[P[f"{sg}_fg_yield_t_ha"] > 12, f"{sg}_fg_yield_t_ha"] = np.nan

    # implausible foodgrain yields -> null (data glitches); record how many
    bad = (P.foodgrain_yield_t_ha > 12)
    stats["foodgrain_yield_gt12_nulled"] = int(bad.sum())
    for col in ("foodgrain_yield_t_ha",):
        P.loc[bad, col] = np.nan
    stats["yield_max_before_clip"] = float(P.foodgrain_yield_t_ha.max())

    cols = (["lgd", "crop_year", "source", "gross_cropped_area_ha", "foodgrain_area_ha", "foodgrain_prod_t",
             "foodgrain_yield_t_ha", "fg_area_missing_prod_share"]
            + [f"{g}_{m}" for g in GROUPS for m in ("area_ha", "prod_t", "yield_t_ha")]
            + ["other_area_ha", "simpson_div", "top_crop", "top_crop_share", "n_crops", "kharif_rabi_ratio",
               "upag_foodgrain_area_ha", "upag_foodgrain_prod_t", "upag_gross_area_ha",
               # v4 additive season-split columns
               "kharif_fg_yield_t_ha", "rabi_fg_yield_t_ha", "kharif_fg_prod_t", "rabi_fg_prod_t",
               "kharif_fg_area_ha", "rabi_fg_area_ha", "rabi_pulses_prod_t"])
    P = P[cols].sort_values(["lgd", "crop_year"]).reset_index(drop=True)
    P.to_parquet(ART / "crops_district_year.parquet", index=False)
    stats["panel_rows"] = len(P)

    # ---- latest snapshot
    sel = pick_latest(P, split_sy, state_of)
    L = pd.DataFrame(index=pd.Index(mlgds, name="lgd"))
    L = L.join(master[["lgd", "district", "state"]].set_index("lgd"))
    s = sel.copy()
    s["year"] = s.crop_year.astype(str) + "-" + ((s.crop_year + 1) % 100).astype(str).str.zfill(2)
    L = L.join(s[["year", "crop_year", "source", "latest_complete", "gross_cropped_area_ha", "foodgrain_area_ha",
                  "foodgrain_prod_t", "foodgrain_yield_t_ha", "simpson_div", "top_crop", "top_crop_share", "n_crops",
                  "kharif_rabi_ratio", "fg_area_ratio_prior5"]])
    gj = {}
    for lgd, r in s.iterrows():
        gj[lgd] = json.dumps({g: {"area_ha": None if pd.isna(r[f"{g}_area_ha"]) else round(float(r[f"{g}_area_ha"]), 1),
                                  "prod_t": None if pd.isna(r[f"{g}_prod_t"]) else round(float(r[f"{g}_prod_t"]), 1),
                                  "yield_t_ha": None if pd.isna(r[f"{g}_yield_t_ha"]) else round(float(r[f"{g}_yield_t_ha"]), 4)}
                              for g in ["cereals", "pulses", "oilseeds", "millets", "cash"]})
    L["groups_json"] = pd.Series(gj)
    tj = top_crops_json(c_all, s)
    L["top_json"] = tj.map(json.dumps)
    L["yield_cv10"] = yield_cv10(P, s).round(4)
    # APY all-crop gross area reference (latest complete APY year <= 2022): comparable across districts even where
    # the snapshot year is UPAG-only (UPAG lists ~30 major crops, no horticulture/plantation)
    apy_ref = P[(P.source == "APY") & P.gross_cropped_area_ha.notna()].sort_values("crop_year").groupby("lgd").tail(1)
    L["gross_area_all_crops_ref_ha"] = apy_ref.set_index("lgd").gross_cropped_area_ha
    L["gross_area_ref_year"] = apy_ref.set_index("lgd").crop_year
    L = L.join(irrigation_share(mlgds)).join(small_marginal(mlgds)).join(pmfby(mlgds))
    L = L.rename(columns={"crop_year": "latest_crop_year"}).reset_index()
    L["latest_stale"] = (L.latest_crop_year < STALE_BEFORE).astype("boolean").where(L.latest_crop_year.notna())
    for c in ("gross_cropped_area_ha", "foodgrain_area_ha", "foodgrain_prod_t", "gross_area_all_crops_ref_ha"):
        L[c] = L[c].round(1)
    for c in ("foodgrain_yield_t_ha", "simpson_div", "top_crop_share", "kharif_rabi_ratio", "fg_area_ratio_prior5"):
        L[c] = L[c].round(4)
    L.to_parquet(ART / "crops_latest.parquet", index=False)

    # ---- sensitivity
    years = list(range(int(P.crop_year.min()), int(P.crop_year.max()) + 1))
    phases = enso_phase_by_monsoon_year()
    ya = [y for y in years if y >= FIRST_ANALOG_YEAR]
    stats["elnino_years_in_range"] = [y for y in ya if phases.get(y) == "El Niño"]
    stats["neutral_years_in_range"] = [y for y in ya if phases.get(y) == "Neutral"]
    stats["lanina_years_in_range"] = [y for y in ya if phases.get(y) == "La Niña"]
    S = sensitivity(P, mlgds, years, phases)
    S.to_parquet(ART / "yield_sensitivity.parquet", index=False)

    # ---- per-district time series json
    tsdir = ART / "timeseries_crops"
    for f in tsdir.glob("*.json"):
        f.unlink()
    ts_groups = ["cereals", "millets", "pulses", "oilseeds"]
    byl = {l: g for l, g in P.groupby("lgd")}

    def ser(g, col, nd, min_area_col=None):
        v = g[["crop_year", col]].copy()
        if min_area_col:
            v = v[g[min_area_col] >= MIN_AREA_HA]
        v = v.dropna()
        return {str(int(y)): round(float(x), nd) for y, x in zip(v.crop_year, v[col])}

    for lgd in mlgds:
        g = byl.get(lgd)
        if g is None:
            obj = {"foodgrain_t_ha": {}, "by_group": {k: {} for k in ts_groups}, "gross_area_ha": {}, "foodgrain_prod_t": {}}
        else:
            obj = {"foodgrain_t_ha": ser(g, "foodgrain_yield_t_ha", 4, "foodgrain_area_ha"),
                   "by_group": {k: ser(g, f"{k}_yield_t_ha", 4, f"{k}_area_ha") for k in ts_groups},
                   "gross_area_ha": ser(g, "gross_cropped_area_ha", 1),
                   "foodgrain_prod_t": ser(g, "foodgrain_prod_t", 1)}
        save_json(obj, tsdir / f"{lgd}.json")

    write_report(stats, master, P, L, S, c_all)


# --------------------------------------------------------------------------------------------
# 7. report
# --------------------------------------------------------------------------------------------
def write_report(stats, master, P, L, S, c_all):
    mset = set(master.lgd)
    out = []
    w = out.append
    w("# 01_crops report\n")
    w("## Rows in / out\n")
    w(f"- APY rows in: {stats['apy_rows_in']:,}; 'Total'-season duplicate rows dropped: {stats['apy_total_rows_dropped']:,}; "
      f"rows used: {stats['apy_rows_used']:,} ({stats['apy_rows_not_in_master']:,} in lgds not in master)")
    w(f"- UPAG rows in: {stats['upag_rows_in']:,}; dropped for blank district_code: {stats['upag_rows_no_lgd']} "
      f"({', '.join(stats['upag_no_lgd_names'])}); {stats['upag_rows_not_in_master']:,} more in lgds not in master")
    w(f"- Panel `crops_district_year`: {stats['panel_rows']:,} rows, {P.lgd.nunique()} districts, crop years "
      f"{P.crop_year.min()}-{P.crop_year.max()}; source APY {int((P.source == 'APY').sum()):,} / UPAG {int((P.source == 'UPAG').sum()):,}")
    w(f"- `crops_latest`: {len(L)} rows (all master districts), `yield_sensitivity`: {len(S)} rows, timeseries_crops: {len(master)} json files\n")
    w("## Matching to district master (districts().lgd)\n")
    w(f"- Master polygons with LGD: {len(mset)}; with any crop panel row: {P.lgd.nunique()} ({P.lgd.nunique() / len(mset):.1%})")
    w(f"- APY lgds: {stats['apy_lgds']} ({len(stats['apy_lgds_not_in_master'])} not in master); "
      f"UPAG lgds: {stats['upag_lgds']} ({len(stats['upag_lgds_not_in_master'])} not in master)")
    w("- Not in master (new districts created after the polygon file; dropped): "
      + "; ".join(f"{k}: {v}" for k, v in stats["unmatched_names"].items()))
    missing = master[~master.lgd.isin(P.lgd)]
    w(f"- Master districts with NO crop data ({len(missing)}): " + (", ".join(f"{r.district} ({r.state})" for r in missing.itertuples()) or "none") + "\n")
    w("## Latest-year coverage\n")
    ok = L.latest_crop_year.notna()
    w(f"- Districts with a latest year (foodgrain production present): {int(ok.sum())} / {len(L)} ({ok.mean():.1%}); "
      f"flagged complete: {int(L.latest_complete.fillna(False).sum())}")
    w("- Latest crop year distribution: " + ", ".join(f"{int(k)}-{str(int(k) + 1)[-2:]}: {v}" for k, v in
                                                       L.latest_crop_year.value_counts().sort_index().items()))
    w("- Source of latest row: " + ", ".join(f"{k}: {v}" for k, v in L.source.value_counts().items()))
    for col, lab in (("irrigated_share", "irrigated_share"), ("small_marginal_share", "small_marginal_share"),
                     ("yield_cv10", "yield_cv10"), ("pmfby_farmers", "pmfby_farmers"), ("simpson_div", "simpson_div")):
        w(f"- {lab} non-null: {int(L[col].notna().sum())} / {len(L)}")
    w("- Master districts without a latest snapshot: " + (", ".join(
        f"{r.district} ({r.state})" for r in L[~ok].itertuples()) or "none") + "\n")
    w("## Year coverage histogram (districts with foodgrain_prod_t per crop year)\n")
    w("```")
    cov = P[P.foodgrain_prod_t.notna()].groupby("crop_year").lgd.nunique()
    for y, n in cov.items():
        w(f"{y}-{str(y + 1)[-2:]} {n:4d} {'#' * int(n / 15)}")
    w("```\n")
    w("## Unit / harmonisation checks\n")
    w(f"- UPAG vs APY on {stats['overlap_rows']:,} overlapping district-crop-season rows: area ratio {stats['upag_area_ratio']:.4f}, "
      f"production ratio {stats['upag_prod_ratio']:.4f} => **UPAG is in ha / t / kg-per-ha, not '000** "
      f"(applied factors: area x{stats['upag_area_factor']:g}, production x{stats['upag_prod_factor']:g}). Yield kg/ha / 1000 -> t/ha.")
    w(f"- APY cotton production is in 170 kg bales, jute/mesta in 180 kg bales; converted x0.17 / x0.18. "
      f"UPAG/APY production ratio after conversion: " + ", ".join(f"{k} {v:.3f}" for k, v in stats["bale_check_ratio_after_conversion"].items()))
    w(f"- foodgrain yields > 12 t/ha nulled: {stats['foodgrain_yield_gt12_nulled']}; max remaining foodgrain yield {stats['yield_max_before_clip']:.2f} t/ha\n")
    w("## Sample districts (latest snapshot)\n")
    samples = [486, 673, 191, 502, 358]
    w("| lgd | district | year | src | gross area ha | fg prod t | fg yield t/ha | cv10 | irrig | small+marg | top crops | elnino % | deficit % |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    Si = S.set_index("lgd")
    for l in samples:
        r = L[L.lgd == l]
        if r.empty:
            continue
        r = r.iloc[0]
        top = ", ".join(f"{t['crop']} {t['share']:.0%}" for t in __import__("json").loads(r.top_json)[:3]) if isinstance(r.top_json, str) else ""
        f = lambda v, d=1: "n/a" if pd.isna(v) else f"{v:,.{d}f}"  # noqa: E731
        w(f"| {l} | {r.district} ({r.state}) | {r.year} | {r.source} | {f(r.gross_cropped_area_ha, 0)} | {f(r.foodgrain_prod_t, 0)} | "
          f"{f(r.foodgrain_yield_t_ha, 2)} | {f(r.yield_cv10, 2)} | {f(r.irrigated_share, 2)} | {f(r.small_marginal_share, 2)} | {top} | "
          f"{f(Si.loc[l, 'foodgrain_elnino_pct'])} | {f(Si.loc[l, 'foodgrain_deficit_year_pct'])} |")
    w("")
    w("## Yield sensitivity (deviation from trend, El Nino years minus Neutral years, %)\n")
    w(f"- El Nino years used (ONI-derived, within {P.crop_year.min()}-{P.crop_year.max()}): {stats['elnino_years_in_range']}; "
      f"Neutral: {len(stats['neutral_years_in_range'])} years; La Nina: {stats['lanina_years_in_range']}")
    w(f"- Deficit-year analogs: {DEFICIT_YEARS}; baseline = all other years")
    q = [0, .05, .1, .25, .5, .75, .9, .95, 1]
    for col in ("foodgrain_elnino_pct", "foodgrain_deficit_year_pct", "cereals_elnino_pct", "millets_elnino_pct",
                "pulses_elnino_pct", "oilseeds_elnino_pct"):
        v = S[col].dropna()
        w(f"- `{col}`: n={len(v)} non-null of {len(S)}; quantiles " + ", ".join(f"p{int(a * 100)}={v.quantile(a):.1f}" for a in q))
    w(f"- share of districts with negative foodgrain_elnino_pct: {(S.foodgrain_elnino_pct.dropna() < 0).mean():.1%}\n")
    w("## Season-split foodgrain columns (v4)\n")
    w("- `kharif_fg_*` / `rabi_fg_*` = foodgrain (cereals + millets + pulses) yield (t/ha), production (t), area (ha) by season label "
      "(kharif = Kharif + Autumn + Winter; rabi = Rabi; Summer and Whole Year in neither); `rabi_pulses_prod_t` = rabi pulses production. Used by 04b (--season rabi) and 04_risk (rabi scores).")
    for sg in ("kharif", "rabi"):
        v = P[f"{sg}_fg_yield_t_ha"]
        yc = P[v.notna()].groupby("crop_year").lgd.nunique()
        w(f"- `{sg}_fg_yield_t_ha` non-null rows: {int(v.notna().sum()):,} of {len(P):,}; districts with >= 1 year: {P[v.notna()].lgd.nunique()}; "
          f"districts per crop year min / median / max: {int(yc.min())} / {int(yc.median())} / {int(yc.max())}")
    both = P[P.kharif_fg_yield_t_ha.notna() & P.rabi_fg_yield_t_ha.notna()]
    w(f"- median rabi share of foodgrain production (district-years with both): {(both.rabi_fg_prod_t / (both.rabi_fg_prod_t + both.kharif_fg_prod_t)).median():.2f}\n")
    w("## Caveats\n")
    for t in CAVEATS:
        w(f"- {t}")
    txt = "\n".join(out) + "\n"
    (ART / "reports" / "01_crops_report.md").write_text(txt)
    print(txt)


CAVEATS = [
    "UPAG file units are ha / t / kg-per-ha (identical to APY on the overlap), contrary to the '000-ha description; no x1000 conversion applied.",
    "APY and UPAG agree to <1 % on 2013-2022 foodgrain area/production for common crops, so the APY->UPAG switch (2023+) is smooth; "
    "APY coverage in 2020-22 is NOT partial in this extract (706-736 districts), so APY is kept there (UPAG used only where it has >5 % more foodgrain area).",
    "UPAG lists ~30 major crops only (no vegetables, fruit, spices, plantation). For UPAG-sourced years gross_cropped_area_ha, simpson_div, n_crops and "
    "top_crop_share are on a 'major crops' basis and are NOT comparable with APY-sourced rows; `gross_area_all_crops_ref_ha` gives the latest APY all-crop gross area.",
    "Gross cropped area = sum of all seasonal crop areas (incl. Whole Year perennials/plantations such as sugarcane, coconut, banana).",
    "Season labels are inconsistent across states/years (e.g. Bihar, Odisha, West Bengal, Assam, Jharkhand shift area between Kharif/Rabi/Autumn/Winter/Summer "
    "between 2022 and 2023; Odisha 2023 has no Rabi row). kharif_rabi_ratio (Kharif+Autumn+Winter over Rabi; Summer and Whole Year excluded) is unreliable "
    "for those states and for UPAG 2023+; treat as indicative only.",
    "SEASON-SPLIT COLUMNS (v4): the `season` label of APY/UPAG rows is unreliable in Bihar, Odisha, West Bengal, Assam and Jharkhand (area moves between "
    "Kharif / Autumn / Winter / Rabi / Summer between years; Odisha 2023 has no Rabi row; Summer/boro rice is in neither season column). `kharif_fg_*` and `rabi_fg_*` "
    "are therefore least reliable there and the season-split yield deviations built on them (04b --season rabi) inherit label-switch jumps; treat rabi results for those "
    "states as indicative. UPAG 2023+ covers major crops only, so season production is a lower bound in those years.",
    "Production is summed over crops that report it; yield = production / area of crops with production, so missing production does not bias yield down "
    "but foodgrain_prod_t is a lower bound when fg_area_missing_prod_share > 0. Latest-year selection requires <= 15 % of foodgrain area lacking production.",
    "Latest year is capped at 2023-24: 2024-25 UPAG is provisional (kept in the panel and used in sensitivity). A district-year is 'complete' when <=15 % of foodgrain area lacks production, "
    "foodgrain area >= 30 % of the trailing-5-year median, and (only in state-years where new non-master districts report data: Rajasthan, MP, Chhattisgarh, Nagaland, Sikkim 2022+) "
    ">= 90 % of that median, so parents that lost area to child districts fall back to an earlier year. Real swings (e.g. 2023 drought-hit Nandurbar/Morbi) and long declines "
    "(Garhwal) are NOT rejected. The new districts themselves are not in the polygon master and are dropped (their area is therefore missing from 2023+ parents in split states "
    "where the 90 % test did not fire). `latest_stale` flags snapshots older than 2018 (urban districts with no real cropping: Mumbai, Hyderabad, ...).",
    "'Other' crops (incl. fruit/veg) excluded from foodgrain. Millets group follows common.CROP_GROUPS ('Other Cereals' counted as millets). Classification fixes "
    "applied locally: Peas (Vegetable), Pear, Peach, Guar -> other; Korra/Samai/Varagu -> millets. Cash = sugarcane, cotton, jute, mesta, tobacco; "
    "cash yield is null because the group mixes cane tonnes and lint tonnes.",
    "Group yields from < 500 ha (rounding noise: APY reports in 100 ha steps) are excluded from sensitivity and time series. Deviations clipped to +/-100 %.",
    "1997 (ONI El Nino) is excluded as an analog/baseline year (APY 1997-98 covers only ~500 districts; it is still used in detrending); analog years are therefore 2002, 2004, 2006, 2009, 2015, 2018, 2023. "
    "Yield sensitivity: per district/group linear trend over 1997-2024 (5-yr rolling median if < 12 obs, >= 6 obs required); trend fitted on all years including El Nino years "
    "(slightly biases the effect toward zero); effect = mean deviation in El Nino years minus mean in Neutral years (ONI-based, JJA-OND mean); requires >= 3 El Nino and >= 3 "
    "Neutral observations. These are historical analogs, not causal estimates; irrigated districts show weak signals and the deviation conflates rainfall with other shocks "
    "(e.g. 2018 and 2006 El Nino years were not monsoon deficits).",
    "deficit_year column uses non-deficit years (not Neutral ENSO years) as baseline; 2023 deficit-year data is UPAG (major crops only).",
    "irrigated_share = gross irrigated area / gross cropped area (both land-use statistics tables), latest year with valid data per district; zero numerators are "
    "treated as missing (tables report 0/NaN for non-reporting districts); share capped at 1. Coverage is patchy (2020-22 sparse; source-of-irrigation table is mostly empty for some districts, then the crop-wise irrigated table is used). "
    "Gross irrigated area can exceed net, so share is a cropping-intensity-weighted measure, not % of net sown area.",
    "small_marginal_share = (Marginal + Small, i.e. < 2 ha) / all operational holdings by count, latest Agriculture Census year per district (2015-16 where available, else 2010-11); "
    "districts created after 2011 may be missing.",
    "pmfby_farmers = PMFBY-scheme farmer_count summed over seasons and insurance-unit rows in the latest year (farmer-seasons, 2018-2022 only; loanee+non-loanee do not reconcile with farmer_count in source).",
]

if __name__ == "__main__":
    main()
