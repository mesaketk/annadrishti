"""06_export.py - assemble SCHEMA.md objects for the AnnaDrishti web app + API.

Reads  : artifacts/extra_district.parquet (v2: markets, groundwater, nutrition.poshan_live, crops.economics),
         artifacts/{crops_latest,yield_sensitivity,climate_district,social_district}.parquet, risk_district.json,
         risk_meta.json, ml_ensemble.parquet + ml_ensemble_meta.json (v3 `models` block), timesfm_summary.parquet, enso_status.json, buffer_stocks.json, gee_live.json (optional), timeseries_{crops,climate,social}/
Writes : artifacts/districts.json (753), artifacts/kpis.json, artifacts/timeseries/{lgd}.json
         and copies the three to web/public/mock/ (overwrites mock data; same filenames).
v4 (seasons, SCHEMA Addendum F): per-district `risk` carries every `<season>:<phase>` key (+ `current`) and the legacy aliases neutral | elnino | elnino_strong
(= <kharif>:<phase>, same content); `hindcast_rabi`, `season_context`, `models.by_scenario` for all keys; `kpis.outlook`, `kpis.by_season_scenario`,
`kpis.hindcast_rabi`, `kpis.models.rabi`. File size guard: if districts.json exceeds MAX_MB the drivers per scenario are trimmed (8 -> 6 -> 5 -> 4 -> 3).
v5 (imputation, SCHEMA Addendum G): the source layers are overlaid with artifacts/imputed_district.parquet (03c_impute.py) where they are null; `data_quality` gains `imputed` {dotted path: source},
`imputed_count`, `imputed_data_count`, `consumption_side` (from risk_district.json); blocks built from imputed values carry `estimated` (+ the imputed field names); `kpis.data_coverage` gains imputation counts; the
before/after null table, the imputed-count distribution and the imputed-vs-neighbour score table are written below the marker line of artifacts/reports/03c_impute_report.md.
v6 (SCHEMA Addendum I): per-district `crops.by_season` (01_crops kharif_top_json / rabi_top_json / season_top_source; split children take the parent's lists, flagged estimated), `season_outlook`
(04_risk), `kpis.season_outlook_national`; user-facing "MGNREGA" label is "NREGA" (CSV headers; JSON keys keep `mgnrega_persondays`). MAX_MB raised 17 -> 21 for these blocks.
Run    : python3 pipeline/06_export.py   (after 04_risk.py; idempotent, no network)
"""
from __future__ import annotations
import json, math, os, shutil, sys, time
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import districts, ART, ROOT, save_json

T0 = time.time()
SCEN = ["neutral", "elnino", "elnino_strong"]       # legacy scenario ids (aliases of <kharif>:<phase>)
MAX_MB = 21.0          # v6: was 17.0 (season_outlook + crops.by_season add ~3 MB; drivers were already at the 3-per-scenario floor); v5: was 15.0; the 188 newly rabi-scored + 34 newly kharif-scored districts add ~1.5 MB at the floor of the driver trimming
GROUPS = ["cereals", "millets", "pulses", "oilseeds"]
MOCK = ROOT / "web" / "public" / "mock"


def clean(o):
    """Recursively replace NaN/inf/NA with None."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if o is pd.NA:
        return None
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def jl(s):
    return json.loads(s) if isinstance(s, str) else None


def num(x, nd=None):
    if x is None or x is pd.NA:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, nd) if nd is not None else v


def integer(x):
    v = num(x)
    return None if v is None else int(round(v))


def r_int_if_whole(x, nd):
    return num(x, nd)


m = districts()
crops = pd.read_parquet(ART / "crops_latest.parquet").set_index("lgd")
ys = pd.read_parquet(ART / "yield_sensitivity.parquet").set_index("lgd")
clim = pd.read_parquet(ART / "climate_district.parquet").set_index("lgd")
soc = pd.read_parquet(ART / "social_district.parquet").set_index("lgd")
extra = pd.read_parquet(ART / "extra_district.parquet").set_index("lgd")
# ── v5: imputation overlay (fill only where the source layer is null) ────────────────────────────────────────────────
IMPQ_PATH = ART / "imputed_district.parquet"
IMPQ = pd.read_parquet(IMPQ_PATH).set_index("lgd") if (IMPQ_PATH.exists() and not os.environ.get("NO_IMPUTE")) else None
def overlay(frame):
    if IMPQ is None:
        return frame
    clim_imp = frame.jjas_normal_mm.isna() & IMPQ.jjas_normal_mm.reindex(frame.index).notna() if "jjas_normal_mm" in frame else None
    for c in IMPQ.columns:
        if c.endswith("__src") or c.endswith("__map") or c.startswith(("worldpop", "rabi_ndvi", "rabi_share_est", "rabi_structure", "rab_")) or c not in frame.columns:
            continue
        v = IMPQ[c].reindex(frame.index)
        if c in ("nfhs5_json", "nfhs6_json"):
            m_ = v.notna()
        elif c in ("jjas_anomaly_json", "ond_anomaly_json"):
            m_ = v.notna() & clim_imp
        else:
            m_ = frame[c].isna() & v.notna()
        if not m_.any():
            continue
        try:
            if pd.api.types.is_numeric_dtype(frame[c].dtype) and not pd.api.types.is_bool_dtype(frame[c].dtype):
                was_int = str(frame[c].dtype) == "Int64"
                col = frame[c].astype(float).copy(); col[m_] = pd.to_numeric(v, errors="coerce")[m_]
                frame[c] = col.round().astype("Int64") if was_int else col
            else:
                col = frame[c].astype(object).copy(); col[m_] = v[m_]; frame[c] = col
        except Exception as e_:      # noqa
            print("overlay skipped", c, e_)
    return frame
crops, clim, soc, extra = (overlay(f_) for f_ in (crops, clim, soc, extra))
SHOWCASE_TS = [486, 358, 191, 673, 502, 441, 426, 525, 290, 118]   # the only timeseries shipped in web/public/mock (full set: artifacts/timeseries)
risk = json.load(open(ART / "risk_district.json"))
meta = json.load(open(ART / "risk_meta.json"))
enso = json.load(open(ART / "enso_status.json"))
buf = json.load(open(ART / "buffer_stocks.json"))
gee = json.load(open(ART / "gee_live.json")) if (ART / "gee_live.json").exists() else None
el_ys = meta["elnino_years"]
SEAS_IDS = meta.get("season_ids") or {"kharif": "kharif_2027", "rabi": "rabi_2026_27"}
KID, RID = SEAS_IDS["kharif"], SEAS_IDS["rabi"]
PH4 = ["lanina", "neutral", "elnino", "elnino_strong"]
KEYS_K = [f"{KID}:{p}" for p in PH4 + ["current"]]; KEYS_R = [f"{RID}:{p}" for p in PH4 + ["current"]]; KEYS = KEYS_K + KEYS_R
PB = (enso.get("p_by_season") or {}).copy()
def kind_of(key):
    return "rabi" if key.split(":")[0] == RID else "kharif"
ENS = pd.read_parquet(ART / "ml_ensemble.parquet") if (ART / "ml_ensemble.parquet").exists() else None
ENSM = json.load(open(ART / "ml_ensemble_meta.json")) if (ART / "ml_ensemble_meta.json").exists() else None
ENS_R = pd.read_parquet(ART / "ml_ensemble_rabi.parquet") if (ART / "ml_ensemble_rabi.parquet").exists() else None
ENSM_R = json.load(open(ART / "ml_ensemble_rabi_meta.json")) if (ART / "ml_ensemble_rabi_meta.json").exists() else None
TFM = pd.read_parquet(ART / "timesfm_summary.parquet").set_index("lgd") if (ART / "timesfm_summary.parquet").exists() else None
ens_by, ens_by_r = {}, {}
if ENS is not None:
    for r_ in ENS.itertuples():
        ens_by.setdefault(int(r_.lgd), {})[r_.scenario] = r_
if ENS_R is not None:
    for r_ in ENS_R.itertuples():
        ens_by_r.setdefault(int(r_.lgd), {})[r_.scenario] = r_
TFM_VARIANT = "TimesFM 3.0 + ONI covariate"
TFM_VARIANT_UNI = "TimesFM 2.5 univariate"
TFM_DISTRICT_SKILL = "none (rho~0 vs history); national signal only"
today = date.today().isoformat()
def _imp(lgd):
    return ((risk.get(str(lgd)) or {}).get("data_quality") or {}).get("imputed") or {}
def _imp_fields(lgd, prefix):
    return sorted(k.split(".")[-1] for k in _imp(lgd) if k.startswith(prefix + "."))


def nfhs_block(js, lgd=None, rnd=None):
    d = jl(js)
    if not d:
        return None
    keys = ["stunting", "wasting", "underweight", "child_anaemia", "women_anaemia", "women_bmi_low"]
    out = {"year": d.get("year")}
    out.update({k: num(d.get(k), 1) for k in keys})
    out["severe_wasting"] = num(d.get("severe_wasting"), 1)
    fl = _imp_fields(lgd, f"nutrition.nfhs{rnd}") if lgd is not None else []
    if fl:
        out["estimated"] = fl          # indicators that are imputed (source: data_quality.imputed)
    return out


SPLIT_PARENT = {}
_ij = ART / "imputed_district.json"
if _ij.exists() and not os.environ.get("NO_IMPUTE"):
    SPLIT_PARENT = {int(k): int(v) for k, v in (json.load(open(_ij)).get("split_parent") or {}).items()}


def _season_top(js):
    return [{"crop": t["crop"], "share": num(t.get("share"), 4), "yield_t_ha": num(t.get("yield_t_ha"), 3), "area_ha": num(t.get("area_ha"), 0)}
            for t in (jl(js) or [])[:5]]


def by_season_block(lgd):
    """SCHEMA Addendum I `crops.by_season`: top-5 crops per season (01_crops v6). Split children without their own snapshot take the parent's lists (flagged `estimated`)."""
    src_l, est = lgd, False
    if (lgd not in crops.index or not isinstance(crops.loc[lgd].kharif_top_json, str)) and lgd in SPLIT_PARENT:
        src_l, est = SPLIT_PARENT[lgd], True
    if src_l not in crops.index or not isinstance(crops.loc[src_l].kharif_top_json, str):
        return None
    r = crops.loc[src_l]
    src = r.season_top_source if isinstance(r.season_top_source, str) else None
    o = {"kharif": {"top": _season_top(r.kharif_top_json), "source": src}, "rabi": {"top": _season_top(r.rabi_top_json), "source": src}}
    if est:
        for v in o.values():
            v["estimated"] = True; v["estimated_from"] = "parent_split_area_share"; v["share_basis"] = "parent district"
    return o


def crops_block(lgd):
    if lgd not in crops.index:
        return None
    r = crops.loc[lgd]
    if pd.isna(r.foodgrain_prod_t) and pd.isna(r.gross_cropped_area_ha):
        return None
    top = [{"crop": t["crop"], "share": num(t.get("share"), 4), "yield_t_ha": num(t.get("yield_t_ha"), 3), "area_ha": num(t.get("area_ha"), 0)}
           for t in (jl(r.top_json) or [])[:5]]
    groups = {}
    for g, v in (jl(r.groups_json) or {}).items():
        groups[g] = {"area_ha": num(v.get("area_ha"), 0), "prod_t": num(v.get("prod_t"), 0), "yield_t_ha": num(v.get("yield_t_ha"), 3)}
    est = _imp(lgd).get("crops")
    return {"year": r.year, "source": (r.source if not est else f"{r.source} (parent district x area share)"), "gross_cropped_area_ha": num(r.gross_cropped_area_ha, 0), "top": top, "groups": groups,
            "foodgrain_prod_t": num(r.foodgrain_prod_t, 0), "foodgrain_yield_t_ha": num(r.foodgrain_yield_t_ha, 3),
            "simpson_div": num(r.simpson_div, 3), "top_crop_share": num(r.top_crop_share, 3),
            "kharif_rabi_ratio": num(r.kharif_rabi_ratio, 2), "yield_cv10": num(r.yield_cv10, 3),
            "irrigated_share": num(r.irrigated_share, 3), "rainfed_share": num(r.rainfed_share, 3),
            "small_marginal_share": num(r.small_marginal_share, 3), "pmfby_farmers": integer(r.pmfby_farmers),
            "by_season": by_season_block(lgd),
            **({"estimated": True} if est else {})}


def _sjson(s_, nd=None):
    d = jl(s_)
    return {k: num(v, nd) for k, v in d.items() if num(v) is not None} if d else {}


def markets_block(lgd):
    if lgd not in extra.index:
        return None
    r = extra.loc[lgd]
    series = _sjson(r.price_series_json, 1)
    if not series and pd.isna(r.price_elnino_spike_pct) and pd.isna(r.price_volatility_idx):
        return None
    fl = _imp_fields(lgd, "markets")
    return {"price_crop": (r.price_crop if isinstance(r.price_crop, str) else None),
            "price_elnino_spike_pct": num(r.price_elnino_spike_pct, 1), "price_volatility_idx": num(r.price_volatility_idx, 3),
            "series": series, "n_years": integer(r.price_n_years),
            "source": ("ICRISAT farm-harvest prices (1990-2020, nominal Rs/qtl)" if not fl else "Estimated from neighbouring districts' ICRISAT farm-harvest price indices (no series for this district)"),
            **({"estimated": fl} if fl else {})}


def groundwater_block(lgd):
    if lgd not in extra.index:
        return None
    r = extra.loc[lgd]
    if pd.isna(r.gw_premonsoon_depth_m) and pd.isna(r.gw_stress_idx):
        return None
    return {"premonsoon_depth_m": num(r.gw_premonsoon_depth_m, 2), "decline_m_per_yr": num(r.gw_decline_10y_m_per_yr, 3),
            "stress_idx": num(r.gw_stress_idx, 3), "as_of_year": integer(r.gw_latest_year), "n_wells": integer(r.gw_n_wells),
            "source": (r.gw_source if isinstance(r.gw_source, str) else None), **({"estimated": _imp_fields(lgd, "groundwater")} if _imp_fields(lgd, "groundwater") else {})}


def poshan_block(lgd):
    if lgd not in extra.index:
        return None
    r = extra.loc[lgd]
    if pd.isna(r.poshan_underweight_pct) and pd.isna(r.poshan_stunted_pct) and pd.isna(r.poshan_wasted_pct):
        return None
    return {"underweight_pct": num(r.poshan_underweight_pct, 1), "stunted_pct": num(r.poshan_stunted_pct, 1), "wasted_pct": num(r.poshan_wasted_pct, 1),
            "as_of": (str(r.poshan_as_of)[:7] if isinstance(r.poshan_as_of, str) else None), "measured": integer(r.poshan_measured),
            "series": _sjson(r.poshan_series_json, 1), **({"estimated": _imp_fields(lgd, "nutrition.poshan_live")} if _imp_fields(lgd, "nutrition.poshan_live") else {})}


def economics_block(lgd):
    if lgd not in extra.index:
        return None
    r = extra.loc[lgd]
    cols = ["crop", "year", "cost_c2_per_ha", "value_per_ha", "margin_per_ha", "yield_q_ha"]
    def rows(js):
        return [{k: (t.get(k) if k in ("crop", "year") else num(t.get(k), 1)) for k in cols} for t in (jl(js) or [])]
    top, dt = rows(r.coc_json), rows(r.coc_drought_tolerant_json)
    if not top and not dt:
        return None
    return {"top": top, "drought_tolerant": dt, "source": "State-level cost of cultivation (C2), latest year per crop; Rs/ha nominal"}


def _mrow(r_):
    o = {"analog": num(r_.shock_analog_pct, 1), "lgbm": num(r_.shock_lgbm_pct, 1), "tabfm": num(r_.shock_tabfm_pct, 1),
         "ensemble": num(r_.shock_ensemble_pct, 1), "spread": num(r_.spread_pct, 1)}
    if o["tabfm"] is None:
        del o["tabfm"]                      # slot is null in every row (TabFM not used); omitted to keep districts.json small
    return o


def _mmix(rows, p):
    """probability-weighted mix of the lanina / neutral / elnino rows (the `current` entry)"""
    if not all(ph in rows for ph in ("lanina", "neutral", "elnino")):
        return None
    out = {}
    for f_ in ("analog", "lgbm", "ensemble"):
        v = [rows[ph][f_] for ph in ("lanina", "neutral", "elnino")]
        out[f_] = None if any(x is None for x in v) else round(sum(p[ph] * rows[ph][f_] for ph in ("lanina", "neutral", "elnino")) / sum(p.values()), 1)
    sp = [rows[ph]["spread"] for ph in ("lanina", "neutral", "elnino")]
    out["spread"] = None if any(x is None for x in sp) else round(sum(p[ph] * rows[ph]["spread"] for ph in ("lanina", "neutral", "elnino")) / sum(p.values()), 1)
    return out


def models_block(lgd, rk):
    """SCHEMA Addendum E (+F): per-district model ensemble + TimesFM display fields (null when no member / forecast exists).
    by_scenario keys: legacy neutral|elnino|elnino_strong (kharif) + `<season>:<phase>` incl. lanina and `current` (probability-weighted mix)."""
    by = None
    e = ens_by.get(lgd); er = ens_by_r.get(lgd)
    if e or er:
        by = {}
        kr = {sc: _mrow(e[sc]) for sc in e} if e else {}
        for sc in SCEN:
            by[sc] = ({**kr[sc], "tabfm": None} if kr.get(sc) else None)      # legacy keys keep the Addendum E shape (tabfm slot null)
        for sc in PH4:
            by[f"{KID}:{sc}"] = kr.get(sc)
        if kr:
            by[f"{KID}:current"] = _mmix(kr, {ph: (PB.get(KID) or {}).get(ph, 0.0) for ph in ("lanina", "neutral", "elnino")})
        rr = {sc: _mrow(er[sc]) for sc in er} if er else {}
        for sc in PH4:
            by[f"{RID}:{sc}"] = rr.get(sc)
        if rr:
            by[f"{RID}:current"] = _mmix(rr, {ph: (PB.get(RID) or {}).get(ph, 0.0) for ph in ("lanina", "neutral", "elnino")})
    tf = None
    if TFM is not None and lgd in TFM.index:
        t = TFM.loc[lgd]
        if pd.notna(t.jjas2027_anom_pct) or pd.notna(t.jjas2027_anom_pct_uni) or pd.notna(t.poshan_6m_forecast_pct):
            tf = {"jjas2027_forecast_mm": num(t.jjas2027_forecast_mm, 0), "jjas2027_anom_pct": num(t.jjas2027_anom_pct, 1),
                  "p10": num(t.jjas2027_p10_pct, 1), "p90": num(t.jjas2027_p90_pct, 1), "variant": TFM_VARIANT,
                  "jjas2027_anom_pct_uni": num(t.jjas2027_anom_pct_uni, 1), "p10_uni": num(t.jjas2027_p10_pct_uni, 1), "p90_uni": num(t.jjas2027_p90_pct_uni, 1),
                  "variant_uni": TFM_VARIANT_UNI,
                  "poshan_6m_forecast_pct": num(t.poshan_6m_forecast_pct, 1), "poshan_trend_pp": num(t.poshan_trend_pp, 2),
                  "district_skill": TFM_DISTRICT_SKILL}
    if by is None and tf is None:
        return None
    src = {sc: (rk["risk"].get(sc) or {}).get("expected_shock_source") for sc in SCEN} if rk["risk"] else {}
    return {"expected_shock_source": src.get("elnino") or ("ensemble" if by else None), "by_scenario": by,
            "weights": ({"analog": num(ENSM["weights"]["analog"], 2), "lgbm": num(ENSM["weights"]["lgbm"], 2)} if ENSM and by else None),
            "weights_rabi": ({"analog": num(ENSM_R["weights"]["analog"], 2), "lgbm": num(ENSM_R["weights"]["lgbm"], 2)} if ENSM_R and er else None),
            "skill": ({"lgbm_rho_loyo": num(ENSM["pooled"]["lgbm"]["rho"], 3), "analog_rho_loyo": num(ENSM["pooled"]["analog"]["rho"], 3),
                       "lgbm_mae": num(ENSM["pooled"]["lgbm"]["mae"], 1), "analog_mae": num(ENSM["pooled"]["analog"]["mae"], 1),
                       "zero_mae": num(ENSM["pooled"]["zero_baseline_mae"], 1)} if ENSM and by else None),
            "skill_rabi": ({"lgbm_rho_loyo": num(ENSM_R["pooled"]["lgbm"]["rho"], 3), "analog_rho_loyo": num(ENSM_R["pooled"]["analog"]["rho"], 3),
                            "lgbm_mae": num(ENSM_R["pooled"]["lgbm"]["mae"], 1), "analog_mae": num(ENSM_R["pooled"]["analog"]["mae"], 1),
                            "zero_mae": num(ENSM_R["pooled"]["zero_baseline_mae"], 1)} if ENSM_R and er else None),
            "timesfm": tf}


def climate_block(lgd):
    if lgd not in clim.index:
        return None
    r = clim.loc[lgd]
    has = pd.notna(r.jjas_normal_mm)
    s = soc.loc[lgd] if lgd in soc.index else None
    jj = jl(r.jjas_anomaly_json) or {}
    tm = jl(r.tmax_jjas_anomaly_json) or {}
    ond = jl(r.ond_anomaly_json) or {}
    tfm = jl(r.tmax_febmar_anomaly_json) or {}
    tfm_el = [tfm[str(y)] for y in el_ys if tfm.get(str(y)) is not None]
    out = {
        "jjas_normal_mm": num(r.jjas_normal_mm, 0),
        "jjas_anomaly_pct": {k: num(v, 1) for k, v in jj.items()} if has else {},
        "ond_anomaly_pct": {k: num(v, 1) for k, v in ond.items()} if has else {},
        "elnino_mean_anomaly_pct": num(r.elnino_mean_anomaly_pct, 1), "neutral_mean_anomaly_pct": num(r.neutral_mean_anomaly_pct, 1),
        "lanina_mean_anomaly_pct": num(r.lanina_mean_anomaly_pct, 1), "strong_elnino_anomaly_pct": num(r.strong_elnino_anomaly_pct, 1),
        "elnino_deficit_prob": num(r.elnino_deficit_prob, 3),
        "tmax_anomaly_c": {k: num(v, 2) for k, v in tm.items()} if has else {},
        "tmax_febmar_elnino_anomaly_c": round(float(np.mean(tfm_el)), 2) if (tfm_el and has) else None,   # rabi heat-stress signal (not in score)
        "latest_year_anomaly_pct": num(r.latest_year_anomaly_pct, 1), "latest_year": int(r.latest_year) if has else None,
        "clim_vuln_index": num(s.clim_vuln_index, 3) if s is not None else None,
        "live": None,
    }
    if gee:
        g = (gee.get("districts") or {}).get(str(lgd))
        if g:
            out["live"] = {"ndvi_anom": num(g.get("ndvi_anom"), 3), "chirps_30d_anom_pct": num(g.get("chirps_30d_anom_pct"), 1),
                           "wn_10d_rain_mm": num(g.get("wn_10d_rain_mm"), 1), "as_of": gee.get("as_of"),
                           "chirps_30d_mm": num(g.get("chirps_30d_mm"), 1), "soilm_anom": num(g.get("soilm_anom"), 3),
                           "wn_10d_tmax_c": num(g.get("wn_10d_tmax_c"), 1)}
    return out


def ys_block(lgd, rk):
    if lgd not in ys.index:
        return None
    r = ys.loc[lgd]
    bg = jl(r.by_group_json) or {}
    byg = {g: num(bg.get(g), 1) for g in GROUPS}
    if pd.isna(r.foodgrain_elnino_pct) and all(v is None for v in byg.values()):
        return None
    return {"foodgrain_elnino_pct": num(r.foodgrain_elnino_pct, 1), "n_elnino_years": int(r.n_elnino_years), "by_group": byg,
            "foodgrain_deficit_year_pct": num(r.foodgrain_deficit_year_pct, 1), "n_deficit_years": int(r.n_deficit_years),
            "beta_used_pct": rk.get("beta_used_pct")}


D = []
for _, r in m.iterrows():
    lgd = int(r.lgd); rk = risk[str(lgd)]; s = soc.loc[lgd] if lgd in soc.index else None
    n5 = nfhs_block(s.nfhs5_json, lgd, 5) if s is not None else None
    n6 = nfhs_block(s.nfhs6_json, lgd, 6) if s is not None else None
    dq = rk["data_quality"]
    D.append({
        "lgd": lgd, "district": r.district, "state": r.state, "census11": str(r.census11),
        "centroid": [float(r.centroid_lon), float(r.centroid_lat)],
        "population_2011": integer(s.population_2011) if s is not None else None,
        "population_2026": integer(s.population_2026) if s is not None else None,
        "children_u5_est": integer(s.children_u5_est) if s is not None else None,
        "main_season": rk["main_season"], "beta_source": rk["beta_source"],
        "data_quality": {"has_crops": dq["has_crops"], "has_climate": dq["has_climate"], "has_nfhs6": dq["has_nfhs6"],
                         "scored": dq["scored"], "no_data_reason": dq["no_data_reason"], "rainfed_imputed": dq["rainfed_imputed"],
                         "rabi_scored": dq.get("rabi_scored"), "rabi_no_data_reason": dq.get("rabi_no_data_reason"),
                         "capacity_terms": dq["capacity_terms"], "sensitivity_terms": dq["sensitivity_terms"],
                         "group_beta_fallback": dq["group_beta_fallback"],
                         "consumption_side": dq.get("consumption_side"), "imputed": dq.get("imputed") or {}, "imputed_count": dq.get("imputed_count", 0),
                         "imputed_data_count": dq.get("imputed_data_count", 0)},
        "crops": crops_block(lgd), "food_balance": rk["food_balance"],
        "nutrition": ({"nfhs5": n5, "nfhs6": n6, "poshan_live": poshan_block(lgd)} if (n5 or n6 or poshan_block(lgd)) else None),
        "markets": markets_block(lgd), "groundwater": groundwater_block(lgd),
        "climate": climate_block(lgd), "yield_sensitivity": ys_block(lgd, rk),
        "risk": rk["risk"], "hindcast": rk["hindcast"], "hindcast_rabi": rk.get("hindcast_rabi"), "season_context": rk.get("season_context"),
        "season_outlook": rk.get("season_outlook"),
        "models": models_block(lgd, rk),
    })
for d_ in D:
    eco = economics_block(d_["lgd"])
    if d_["crops"] is not None:
        d_["crops"]["economics"] = eco
D = clean(D)
assert len(D) == 753 and len({d["lgd"] for d in D}) == 753
def _trim(n):
    for d_ in D:
        for k_, o_ in (d_["risk"] or {}).items():
            if o_ and o_.get("drivers"):
                o_["drivers"] = o_["drivers"][:n]
save_json(D, ART / "districts.json")
sz = (ART / "districts.json").stat().st_size / 1e6
DRV_N = 8
for n_ in (6, 5, 4, 3):
    if sz <= MAX_MB:
        break
    _trim(n_); DRV_N = n_
    save_json(D, ART / "districts.json"); sz = (ART / "districts.json").stat().st_size / 1e6
    print(f"  districts.json {sz:.1f} MB after trimming drivers to top {n_}")
DRV_NOTE = f"drivers per scenario <= {DRV_N}"
if sz > MAX_MB:      # last resort: the two least-used views (neutral baseline, strong-El Nino stress test; incl. their legacy aliases) keep only their top 2 drivers
    for d_ in D:
        for k_, o_ in (d_["risk"] or {}).items():
            if o_ and o_.get("drivers") and k_.split(":")[-1] in ("neutral", "elnino_strong"):
                o_["drivers"] = o_["drivers"][:2]
    save_json(D, ART / "districts.json"); sz = (ART / "districts.json").stat().st_size / 1e6
    DRV_NOTE = f"drivers per scenario <= {DRV_N} (neutral / elnino_strong <= 2)"
    print(f"  districts.json {sz:.1f} MB after limiting neutral / elnino_strong to top 2 drivers")
print(f"[{time.time() - T0:5.1f}s] districts.json: {len(D)} ({sz:.1f} MB, {DRV_NOTE})")

# ── timeseries ───────────────────────────────────────────────────────────────
(ART / "timeseries").mkdir(exist_ok=True)
ond_cache = {int(l): jl(clim.loc[l].ond_anomaly_json) for l in clim.index}
n_ts = 0
for d in D:
    lgd = d["lgd"]
    def rd(folder):
        p = ART / folder / f"{lgd}.json"
        return json.load(open(p)) if p.exists() else {}
    c, k, so = rd("timeseries_crops"), rd("timeseries_climate"), rd("timeseries_social")
    ts = {
        "yield": {"foodgrain_t_ha": c.get("foodgrain_t_ha", {}), "by_group": c.get("by_group", {}),
                  "gross_area_ha": c.get("gross_area_ha", {}), "foodgrain_prod_t": c.get("foodgrain_prod_t", {})},
        "rain_jjas_mm": k.get("rain_jjas_mm", {}), "rain_annual_mm": k.get("rain_annual_mm", {}),
        "jjas_anomaly_pct": k.get("jjas_anomaly_pct", {}),
        "ond_anomaly_pct": (ond_cache.get(lgd) or {}) if d["data_quality"]["has_climate"] else {},
        "tmax_jjas_c": k.get("tmax_jjas_c", {}),
        "oni_phase": k.get("oni_phase", {}),
        "nfhs": so.get("nfhs", []), "pds_monthly": so.get("pds_monthly", []),
    }
    save_json(clean(ts), ART / "timeseries" / f"{lgd}.json"); n_ts += 1
print(f"[{time.time() - T0:5.1f}s] timeseries: {n_ts} files")

# ── kpis ──────────────────────────────────────────────────────────────────────
scored = [d for d in D if d["data_quality"]["scored"]]
lat = buf.get("latest", {})
_OS = enso.get("outlook_seasons") or []
def _argmax_phase(sid):
    p = (enso.get("p_by_season") or {}).get(sid) or {}
    return max(("elnino", "neutral", "lanina"), key=lambda k: p.get(k, 0.0)) if p else "elnino"
OUTLOOK = {
    "as_of": today,
    "seasons": [{k: v for k, v in x.items() if k in ("id", "label", "sowing", "harvest", "status", "lead")} for x in _OS],
    "enso": {"state": enso["state"], "nino34": enso["nino34_c"], "source": f"NOAA CPC {enso['as_of']}", "advisory": enso.get("advisory"),
             "p_by_season": enso.get("p_by_season"), "iri_published": next((k.replace("iri_plume_", "") for k in sorted(enso) if k.startswith("iri_plume_")), None),
             "note": enso.get("p_by_season_note")},
    "default_scenario": {x["id"]: _argmax_phase(x["id"]) for x in _OS},
    "refresh": {"enso": "monthly (pipeline/08_enso_status.py)", "live_layers": "daily (05_gee_live.py)", "crops": "annual (DES/UPAG release)", "nutrition": "NFHS round / Poshan monthly"},
}
kp = {
    "as_of": today,
    "enso": {"state": enso["state"], "nino34": enso["nino34_c"], "p_historic_ond": enso["p_historic_event"].get("OND2026"),
             "source": f"NOAA CPC {enso['as_of']}", "advisory": enso.get("advisory"), "cpc_text": enso.get("cpc_text"),
             "iri_p_elnino_mjj2027": (enso.get(next((k for k in sorted(enso) if k.startswith("iri_plume_")), "iri_plume_none")) or {}).get("MJJ2027", {}).get("elnino"),
             "p_by_season": enso.get("p_by_season"), "p_by_season_note": enso.get("p_by_season_note")},
    "central_pool": {"date": lat.get("date"), "rice_lmt": lat.get("rice"), "wheat_lmt": lat.get("wheat"),
                     "total_lmt": lat.get("total_rice_wheat"), "norm_lmt": lat.get("norm_total_nearest"),
                     "months_of_offtake": lat.get("months_of_offtake")} if lat else None,
    "band_thresholds": meta["band_thresholds"], "scenario_params": {"p_elnino": meta["p_elnino"]},
}
by_key, act_key, top_key, cnt_key = {}, {}, {}, {}
ACT_KEYS = ["grain_preposition_t", "pulses_preposition_t", "anganwadi_children", "women_anaemia_target", "seed_bank_ha", "mgnrega_persondays", "pmfby_gap_farmers"]
for s in KEYS:
    kd = kind_of(s)
    cnt = {"high": 0, "medium": 0, "low": 0}
    people = u5 = 0; sh_num = sh_den = 0.0; deficit = 0.0; below = 0; n_ss = 0
    tot = {k: 0.0 for k in ACT_KEYS}; has = {k: False for k in ACT_KEYS}; st = {}
    for d in scored:
        rk = d["risk"][s]
        if rk["band"] not in cnt:                      # no_data (e.g. no material rabi crop)
            continue
        cnt[rk["band"]] += 1
        if rk["band"] == "high":
            people += d["population_2026"] or 0; u5 += d["children_u5_est"] or 0
        fb = d["food_balance"] or {}; shk = rk["expected_yield_shock_pct"]
        rprod = ((d.get("season_context") or {}).get("rabi") or {}).get("foodgrain_prod_t")
        prod = (d["crops"] or {}).get("foodgrain_prod_t") if kd == "kharif" else rprod       # production the shock applies to (rabi: rabi foodgrain production)
        if shk is not None and prod:
            sh_num += shk * prod; sh_den += prod
        if shk is not None and fb.get("requirement_t") and fb.get("edible_prod_t") is not None and (kd == "kharif" or rprod is not None):
            e_s = fb["edible_prod_t"] * (1 + shk / 100) if kd == "kharif" else fb["edible_prod_t"] + rprod * 0.875 * shk / 100
            deficit += max(0.0, fb["requirement_t"] - e_s)
            n_ss += 1; below += int(e_s / fb["requirement_t"] < 1)
        a = rk.get("actions") or {}
        for k in ACT_KEYS:
            if a.get(k) is not None:
                tot[k] += a[k]; has[k] = True
        if a.get("grain_preposition_t") is not None:
            st[d["state"]] = st.get(d["state"], 0.0) + a["grain_preposition_t"]
    cnt_key[s] = cnt
    by_key[s] = {"people_in_high_risk": int(people), "children_u5_in_high_risk": int(u5),
                 "national_expected_shock_pct": round(sh_num / sh_den, 2) if sh_den else None,
                 "total_deficit_t": int(round(deficit)), "districts_below_self_sufficiency": below, "districts_with_balance": n_ss}
    act_key[s] = {k: (int(round(tot[k])) if has[k] else None) for k in ACT_KEYS}
    top_key[s] = [{"state": k, "grain_preposition_t": int(round(v))} for k, v in sorted(st.items(), key=lambda x: -x[1])[:10]]
# legacy (kharif alias) views: scenario_counts / by_scenario / actions_total / top_states keep their old three keys
sc_counts = {s: cnt_key[f"{KID}:{s}"] for s in SCEN}; by_sc = {s: by_key[f"{KID}:{s}"] for s in SCEN}
act_tot = {**{s: act_key[f"{KID}:{s}"] for s in SCEN}, **act_key}; top_states = {**{s: top_key[f"{KID}:{s}"] for s in SCEN}, **top_key}
by_season_scenario = {}
for s in KEYS:
    sid, ph = s.split(":")
    by_season_scenario.setdefault(sid, {})[ph] = {"counts": cnt_key[s], "n_scored": sum(cnt_key[s].values()), **by_key[s], "actions_total": act_key[s]}
def tfm_national(col, pcol=None):
    """national means over districts with a forecast: simple mean, cropped-area-weighted mean (as in 07_bigquery_report), share in deficit / below -10 %."""
    if TFM is None:
        return None
    v = TFM[col].dropna()
    ga = crops["gross_cropped_area_ha"].reindex(v.index)
    w = ga.fillna(0.0)
    out = {"n": int(len(v)), "mean_anom_pct": num(v.mean(), 2), "median_anom_pct": num(v.median(), 2),
           "area_weighted_mean_anom_pct": num((v * w).sum() / w.sum(), 2) if w.sum() > 0 else None,
           "share_deficit": num((v < 0).mean(), 3), "share_below_minus10": num((v < -10).mean(), 3)}
    if pcol:
        lo, hi = TFM[pcol[0]].reindex(v.index), TFM[pcol[1]].reindex(v.index)
        out["median_interval_width_pp"] = num((hi - lo).median(), 1)
    return out


def _skill_row(key, label):
    pm = ENSM["pooled"].get(key) if ENSM else None
    return None if not pm else {"model": key, "label": label, "mae": num(pm["mae"], 2), "rho": num(pm["rho"], 3), "mean_within_year_rho": num(pm.get("mean_within_year_rho"), 3), "gap": num(pm["gap"], 2), "n": pm["n"]}


models_kpi = None
if ENSM:
    rows_ = [_skill_row("analog", "Analog (El Nino beta x rain departure; betas refit leaving the year out)"), _skill_row("lgbm", "LightGBM (huber, 18 features, 3 seeds)"),
             _skill_row("ensemble", "Ensemble (inverse-MAE weights)"), _skill_row("analog_shipped", "Analog with shipped betas (leaky/optimistic; reference only)")]
    models_kpi = {
        "skill_table": [r for r in rows_ if r] + [{"model": "zero", "label": "Predict 0", "mae": num(ENSM["pooled"]["zero_baseline_mae"], 2), "rho": None, "mean_within_year_rho": None, "gap": None, "n": ENSM["pooled"]["analog"]["n"]}],
        "skill_note": ("Leave-one-year-out, 22 held-out monsoon years 2003-2024, 13,267 district-years. rho = Spearman(predicted shock, actual foodgrain yield deviation), positive = good; "
                       "gap = worst-predicted minus best-predicted tercile mean deviation (pp), negative = good. Not a forecasting backtest (training includes future years)."),
        "weights": {"analog": num(ENSM["weights"]["analog"], 3), "lgbm": num(ENSM["weights"]["lgbm"], 3), "tabfm": None},
        "tabfm": {"status": "evaluated, not used", "reason": "TabFM weights (6.6 GB) not cached and CPU inference exceeds the leave-one-year-out budget; slot left null"},
        "scenario_summary": ENSM.get("scenario_summary"),
        "rank_corr_lgbm_vs_analog": {k: num(v.get("shock_lgbm_pct"), 3) for k, v in (ENSM.get("rank_corr_with_analog") or {}).items()},
        "feature_importance_gain_pct": dict(list((ENSM.get("feature_importance_gain_pct") or {}).items())[:8]),
        "timesfm": {
            "variant": TFM_VARIANT, "variant_uni": TFM_VARIANT_UNI, "horizon": "JJAS 2027 rainfall (21-month horizon from 2026-01); Poshan underweight 6 months",
            "covariate": tfm_national("jjas2027_anom_pct", ("jjas2027_p10_pct", "jjas2027_p90_pct")),
            "univariate": tfm_national("jjas2027_anom_pct_uni", ("jjas2027_p10_pct_uni", "jjas2027_p90_pct_uni")),
            "poshan_6m": ({"n": int(TFM.poshan_trend_pp.notna().sum()), "mean_trend_pp": num(TFM.poshan_trend_pp.mean(), 2), "median_trend_pp": num(TFM.poshan_trend_pp.median(), 2),
                           "share_rising": num((TFM.poshan_trend_pp.dropna() > 0).mean(), 3), "mean_forecast_pct": num(TFM.poshan_6m_forecast_pct.mean(), 2)} if TFM is not None else None),
            "district_skill": TFM_DISTRICT_SKILL,
            "hindcast_jjas": [{"year": 2009, "actual_mean_anom_pct": -15.3, "cov_corr": 0.17, "cov_rmse": 27.6, "uni_corr": 0.23, "uni_rmse": 29.5, "climatology_rmse": 29.5},
                              {"year": 2015, "actual_mean_anom_pct": -10.6, "cov_corr": 0.04, "cov_rmse": 27.1, "uni_corr": -0.04, "uni_rmse": 30.3, "climatology_rmse": 26.7},
                              {"year": 2023, "actual_mean_anom_pct": -4.3, "cov_corr": -0.06, "cov_rmse": 26.9, "uni_corr": 0.07, "uni_rmse": 28.3, "climatology_rmse": 23.6},
                              {"year": 2025, "actual_mean_anom_pct": 10.8, "cov_corr": 0.26, "cov_rmse": 39.1, "uni_corr": 0.19, "uni_rmse": 41.0, "climatology_rmse": 35.6}],
            "hindcast_source": "artifacts/reports/07_bigquery_report.md (ONI covariate uses actual ONI = perfect-ENSO upper bound)",
            "caveat": ("Display-only, not in the risk score. District-level hindcast skill ~0 (corr -0.06..+0.26, RMSE not better than climatology); median forecasts run ~5-10 pp low; "
                       "ONI beyond JAS-2026 is an assumption; TimesFM 3.0 covariates are Preview. Use the national mean/direction only."),
        },
    }
if ENSM_R and models_kpi is not None:
    def _skill_row_r(key, label):
        pm = ENSM_R["pooled"].get(key)
        return None if not pm else {"model": key, "label": label, "mae": num(pm["mae"], 2), "rho": num(pm["rho"], 3), "mean_within_year_rho": num(pm.get("mean_within_year_rho"), 3), "gap": num(pm.get("gap"), 2), "n": pm["n"]}
    models_kpi["rabi"] = {
        "skill_table": [r for r in (_skill_row_r("analog", "Analog (rabi El Nino / La Nina phase beta, betas refit leaving the year out)"), _skill_row_r("lgbm", "LightGBM (huber, 14 features, 3 seeds)"),
                                    _skill_row_r("ensemble", "Ensemble (inverse-MAE weights)")) if r] + [{"model": "zero", "label": "Predict 0", "mae": num(ENSM_R["pooled"]["zero_baseline_mae"], 2), "rho": None, "mean_within_year_rho": None, "gap": None, "n": ENSM_R["pooled"]["analog"]["n"]}],
        "skill_note": ("Leave-one-year-out, crop years 2003-2024, rabi foodgrain yield deviation from trailing 10-year trend; rho = Spearman(predicted shock, actual deviation), positive = good. Not a forecasting backtest. "
                       "Rabi LightGBM scenario shocks are relative to the district's neutral-winter prediction."),
        "weights": {"analog": num(ENSM_R["weights"]["analog"], 3), "lgbm": num(ENSM_R["weights"]["lgbm"], 3), "tabfm": None},
        "scenario_summary": ENSM_R.get("scenario_summary"), "feature_importance_gain_pct": dict(list((ENSM_R.get("feature_importance_gain_pct") or {}).items())[:8]),
        "eligibility": ENSM_R.get("eligibility"),
    }
kp.update({
    "outlook": OUTLOOK, "by_season_scenario": by_season_scenario, "season_outlook_national": meta.get("season_outlook_national"),
    "hindcast_rabi": meta.get("hindcast_rabi"), "band_counts_by_scenario": cnt_key,
    "models": models_kpi,
    "scenario_counts": sc_counts,
    "people_in_high_risk": by_sc["elnino"]["people_in_high_risk"], "children_u5_in_high_risk": by_sc["elnino"]["children_u5_in_high_risk"],
    "national_expected_shock_pct": {s: by_sc[s]["national_expected_shock_pct"] for s in SCEN},
    "total_deficit_t": {s: by_sc[s]["total_deficit_t"] for s in SCEN},
    "districts_below_self_sufficiency": {s: by_sc[s]["districts_below_self_sufficiency"] for s in SCEN},
    "by_scenario": by_sc, "hindcast": meta["hindcast"], "actions_total": act_tot,
    "top_states": top_states["elnino"], "top_states_by_scenario": top_states,
    "data_coverage": {
        "districts": len(D), "with_crops": sum(d["data_quality"]["has_crops"] for d in D),
        "with_climate": sum(d["data_quality"]["has_climate"] for d in D), "with_nfhs6": sum(d["data_quality"]["has_nfhs6"] for d in D),
        "scored": len(scored), "no_data": len(D) - len(scored),
        "no_data_reasons": pd.Series([d["data_quality"]["no_data_reason"] for d in D if not d["data_quality"]["scored"]]).value_counts().to_dict(),
        "ond_main_season": sum(d["main_season"] == "OND" for d in D),
        "beta_source": pd.Series([d["beta_source"] for d in scored]).value_counts().to_dict(),
        "live_signals": sum(1 for d in D if (d["climate"] or {}).get("live")),
        # v2 extra sources
        "with_price_series": sum(1 for d in D if (d["markets"] or {}).get("series")),
        "with_price_spike": sum(1 for d in D if (d["markets"] or {}).get("price_elnino_spike_pct") is not None),
        "with_price_volatility": sum(1 for d in D if (d["markets"] or {}).get("price_volatility_idx") is not None),
        "with_groundwater": sum(1 for d in D if d["groundwater"]),
        "with_groundwater_stress": sum(1 for d in D if (d["groundwater"] or {}).get("stress_idx") is not None),
        "with_poshan_live": sum(1 for d in D if (d["nutrition"] or {}).get("poshan_live")),
        "with_poshan_wasted": sum(1 for d in D if ((d["nutrition"] or {}).get("poshan_live") or {}).get("wasted_pct") is not None),
        "with_crop_economics": sum(1 for d in D if (d["crops"] or {}).get("economics")),
        "with_drought_tolerant_economics": sum(1 for d in D if ((d["crops"] or {}).get("economics") or {}).get("drought_tolerant")),
        "scored_with_price_term": sum(1 for d in scored if (d["markets"] or {}).get("price_elnino_spike_pct") is not None and (d["markets"] or {}).get("price_volatility_idx") is not None),
        "scored_with_groundwater_term": sum(1 for d in scored if (d["groundwater"] or {}).get("stress_idx") is not None),
        # v3 models
        "with_models": sum(1 for d in D if d["models"]),
        "with_ensemble": sum(1 for d in D if (d["models"] or {}).get("by_scenario")),
        "scored_with_ensemble_shock": sum(1 for d in scored if d["risk"]["elnino"].get("expected_shock_source") == "ensemble"),
        "scored_with_analog_fallback": sum(1 for d in scored if d["risk"]["elnino"].get("expected_shock_source") == "analog"),
        "with_timesfm": sum(1 for d in D if (d["models"] or {}).get("timesfm")),
        "with_timesfm_jjas": sum(1 for d in D if ((d["models"] or {}).get("timesfm") or {}).get("jjas2027_anom_pct") is not None),
        "with_timesfm_jjas_uni": sum(1 for d in D if ((d["models"] or {}).get("timesfm") or {}).get("jjas2027_anom_pct_uni") is not None),
        "with_timesfm_poshan": sum(1 for d in D if ((d["models"] or {}).get("timesfm") or {}).get("poshan_6m_forecast_pct") is not None),
        "with_hindcast_oos": sum(1 for d in D if any((v or {}).get("predicted_shock_lgbm_oos_pct") is not None for v in (d["hindcast"] or {}).values())),
        "scored_with_poshan_term": sum(1 for d in scored if ((d["nutrition"] or {}).get("poshan_live") or {}).get("underweight_pct") is not None),
        # v5 imputation (Addendum G)
        "with_imputed_fields": sum(1 for d in D if d["data_quality"].get("imputed_data_count")),
        "imputed_entries": sum(d["data_quality"].get("imputed_count", 0) for d in D),
        "consumption_side": sum(1 for d in D if d["data_quality"].get("consumption_side")),
        "scored_on_imputed_exposure_kharif": sum(1 for d in scored if d["risk"][f"{KID}:elnino"].get("imputed") and d["risk"][f"{KID}:elnino"].get("imputed_from") != "imputed_inputs"),
        "scored_on_imputed_exposure_rabi": sum(1 for d in scored if (d["risk"][f"{RID}:elnino"] or {}).get("imputed") and d["risk"][f"{RID}:elnino"].get("imputed_from") != "imputed_inputs"),
        "risk_flagged_imputed_kharif": sum(1 for d in scored if d["risk"][f"{KID}:elnino"].get("imputed")),
        "risk_flagged_imputed_rabi": sum(1 for d in scored if (d["risk"][f"{RID}:elnino"] or {}).get("imputed")),
        "no_data_kharif": sum(1 for d in D if d["risk"][f"{KID}:elnino"]["band"] == "no_data"),
        "no_data_rabi": sum(1 for d in D if d["risk"][f"{RID}:elnino"]["band"] == "no_data"),
    },
    "method_note": ("Expected yield shocks are an ensemble of ENSO-analog and LightGBM models (leave-one-year-out skill reported in `models`); scores combine them with IMD rainfall, APY/UPAG yield, NFHS and other indicators; "
                    "the score hindcast (`spearman_rho`) is in-sample, the `*_oos` fields are out-of-sample. TimesFM forecasts are display-only. "
                    "Bands are tertiles of the El Nino scenario. See artifacts/reports/04_risk_report.md."),
})
save_json(clean(kp), ART / "kpis.json")
print(f"[{time.time() - T0:5.1f}s] kpis.json")

# ── copy to web mock ─────────────────────────────────────────────────────────
MOCK.mkdir(parents=True, exist_ok=True)
shutil.copy(ART / "districts.json", MOCK / "districts.json")
shutil.copy(ART / "kpis.json", MOCK / "kpis.json")
(MOCK / "timeseries").mkdir(exist_ok=True)
keep = {f"{l}.json" for l in SHOWCASE_TS}
for f in (MOCK / "timeseries").glob("*.json"):
    if f.name not in keep:
        f.unlink()
for l in SHOWCASE_TS:
    shutil.copy(ART / "timeseries" / f"{l}.json", MOCK / "timeseries" / f"{l}.json")
print(f"[{time.time() - T0:5.1f}s] copied to {MOCK}")

# ── validation report ────────────────────────────────────────────────────────
print("\n=== VALIDATION ===")
def nullrate(getter):
    n = sum(1 for d in D if getter(d) is None)
    return f"{n:3d} null ({n / len(D):.0%})"
fields = {"crops": lambda d: d["crops"], "crops.foodgrain_prod_t": lambda d: (d["crops"] or {}).get("foodgrain_prod_t"),
          "crops.rainfed_share": lambda d: (d["crops"] or {}).get("rainfed_share"), "crops.irrigated_share": lambda d: (d["crops"] or {}).get("irrigated_share"),
          "crops.small_marginal_share": lambda d: (d["crops"] or {}).get("small_marginal_share"), "crops.yield_cv10": lambda d: (d["crops"] or {}).get("yield_cv10"),
          "food_balance.self_sufficiency": lambda d: (d["food_balance"] or {}).get("self_sufficiency"),
          "food_balance.pds_dependency": lambda d: (d["food_balance"] or {}).get("pds_dependency"),
          "nutrition.nfhs5": lambda d: (d["nutrition"] or {}).get("nfhs5"), "nutrition.nfhs6": lambda d: (d["nutrition"] or {}).get("nfhs6"),
          "climate.jjas_normal_mm": lambda d: (d["climate"] or {}).get("jjas_normal_mm"), "climate.clim_vuln_index": lambda d: (d["climate"] or {}).get("clim_vuln_index"),
          "climate.live": lambda d: (d["climate"] or {}).get("live"), "yield_sensitivity": lambda d: d["yield_sensitivity"],
          "population_2026": lambda d: d["population_2026"], "children_u5_est": lambda d: d["children_u5_est"],
          "risk.elnino.score": lambda d: d["risk"]["elnino"]["score"], "hindcast": lambda d: d["hindcast"],
          "hindcast.2015.predicted": lambda d: ((d["hindcast"] or {}).get("2015") or {}).get("predicted_score"),
          "markets": lambda d: d["markets"], "markets.price_elnino_spike_pct": lambda d: (d["markets"] or {}).get("price_elnino_spike_pct"),
          "groundwater": lambda d: d["groundwater"], "groundwater.stress_idx": lambda d: (d["groundwater"] or {}).get("stress_idx"),
          "nutrition.poshan_live": lambda d: (d["nutrition"] or {}).get("poshan_live"),
          "crops.economics": lambda d: (d["crops"] or {}).get("economics"),
          "hindcast.2015.actual": lambda d: ((d["hindcast"] or {}).get("2015") or {}).get("actual_foodgrain_yield_dev_pct")}
for k, g in fields.items():
    print(f"  {k:34s} {nullrate(g)}")
sc = np.array([d["risk"]["elnino"]["score"] for d in scored])
print("\n  elnino score distribution:", {k: round(float(v), 1) for k, v in zip(["min", "p10", "p25", "p50", "p75", "p90", "max"], np.quantile(sc, [0, .1, .25, .5, .75, .9, 1]))})
print("  band counts:", sc_counts)
top = sorted(scored, key=lambda d: -d["risk"]["elnino"]["score"])[:20]
print("\n  top-20 under elnino:")
for i, d in enumerate(top, 1):
    print(f"   {i:2d}. {d['district']:<24s} {d['state']:<18s} {d['risk']['elnino']['score']:5.1f}  shock {d['risk']['elnino']['expected_yield_shock_pct']:6.1f}%")
rank = {d["lgd"]: i + 1 for i, d in enumerate(sorted(scored, key=lambda d: -d["risk"]["elnino"]["score"]))}
REG = {"Marathwada": [470, 481, 488, 479], "Vidarbha": [500, 468, 467], "Bundelkhand": [153, 161, 398, 434], "Rayalaseema": [502, 511],
       "KBK Odisha": [358, 345, 363], "South Rajasthan": [88, 99, 117]}
print("\n  regional cross-check (elnino national rank / %d):" % len(scored))
for reg, ls in REG.items():
    rs = [rank.get(l) for l in ls]
    pct = np.mean([1 - (r - 1) / len(scored) for r in rs if r])
    print(f"   {reg:<16s} ranks {rs}  mean percentile {pct:.0%}  -> {'OK' if pct >= 0.6 else 'LOWER THAN EXPECTED (see 04_risk_report investigation log)'}")
print("\n  hindcast:", {y: v["spearman_rho"] for y, v in meta["hindcast"].items()})
print("  actions_total (elnino):", act_tot["elnino"])
print("  top_states (elnino):", top_states["elnino"][:5])
bad = [f for f in [ART / "districts.json", ART / "kpis.json"] if "NaN" in open(f).read()]
print("  NaN tokens in output:", bad or "none")
print(f"\n[{time.time() - T0:5.1f}s] done")

# ── v5: append the before / after table, the imputed-count distribution and the neighbour sanity table to the 03c report ─────────────────────────
def _g(d, *ks):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return None
    return d
FIELDS = {
    "population_2011": ("population_2011",), "population_2026": ("population_2026",), "children_u5_est": ("children_u5_est",),
    "crops.foodgrain_prod_t": ("crops", "foodgrain_prod_t"), "crops.gross_cropped_area_ha": ("crops", "gross_cropped_area_ha"),
    "crops.rainfed_share": ("crops", "rainfed_share"), "crops.irrigated_share": ("crops", "irrigated_share"),
    "crops.small_marginal_share": ("crops", "small_marginal_share"), "crops.yield_cv10": ("crops", "yield_cv10"),
    "crops.simpson_div": ("crops", "simpson_div"), "crops.top_crop_share": ("crops", "top_crop_share"),
    "food_balance.self_sufficiency": ("food_balance", "self_sufficiency"), "food_balance.pds_dependency": ("food_balance", "pds_dependency"),
    "nutrition.nfhs5.stunting": ("nutrition", "nfhs5", "stunting"), "nutrition.nfhs5.wasting": ("nutrition", "nfhs5", "wasting"), "nutrition.nfhs5.child_anaemia": ("nutrition", "nfhs5", "child_anaemia"),
    "nutrition.nfhs6.stunting": ("nutrition", "nfhs6", "stunting"), "nutrition.nfhs6.wasting": ("nutrition", "nfhs6", "wasting"),
    "nutrition.nfhs6.underweight": ("nutrition", "nfhs6", "underweight"), "nutrition.nfhs6.women_bmi_low": ("nutrition", "nfhs6", "women_bmi_low"),
    "nutrition.poshan_live.underweight_pct": ("nutrition", "poshan_live", "underweight_pct"), "nutrition.poshan_live.wasted_pct": ("nutrition", "poshan_live", "wasted_pct"),
    "markets.price_volatility_idx": ("markets", "price_volatility_idx"), "markets.price_elnino_spike_pct": ("markets", "price_elnino_spike_pct"),
    "groundwater.premonsoon_depth_m": ("groundwater", "premonsoon_depth_m"), "groundwater.decline_m_per_yr": ("groundwater", "decline_m_per_yr"), "groundwater.stress_idx": ("groundwater", "stress_idx"),
    "climate.jjas_normal_mm": ("climate", "jjas_normal_mm"), "climate.elnino_mean_anomaly_pct": ("climate", "elnino_mean_anomaly_pct"), "climate.clim_vuln_index": ("climate", "clim_vuln_index"),
    "season_context.rabi.foodgrain_prod_t": ("season_context", "rabi", "foodgrain_prod_t"),
    f"risk.{KID}:elnino.score": ("risk", f"{KID}:elnino", "score"), f"risk.{RID}:elnino.score": ("risk", f"{RID}:elnino", "score"),
}
BEF_PATH = ART / "_v4_before.json"
REP_PATH = ART / "reports" / "03c_impute_report.md"
if BEF_PATH.exists() and REP_PATH.exists():
    bef = json.load(open(BEF_PATH)); MARK = "<!-- 06_export -->"
    base = REP_PATH.read_text().split(MARK)[0].rstrip() + "\n\n" + MARK + "\n"
    aft = {k: sum(1 for d in D if _g(d, *p) is None) for k, p in FIELDS.items()}
    L = ["", "## Result: nulls per field in districts.json, before -> after (753 districts)", "",
         "`before` = the v4 export (pre-imputation); `after` = this run. A null that remains is a field with nothing to estimate from (e.g. crop structure of consumption-side districts, NFHS-6 anaemia which the round does not publish).", "",
         "| field | null before | null after | filled |", "|---|---|---|---|"]
    for k in FIELDS:
        b_, a_ = bef["fields"].get(k), aft[k]
        L.append(f"| `{k}` | {b_} | {a_} | {b_ - a_ if b_ is not None else ''} |")
    nd_k = sum(1 for d in D if d["risk"][f"{KID}:elnino"]["band"] == "no_data"); nd_r = sum(1 for d in D if d["risk"][f"{RID}:elnino"]["band"] == "no_data")
    L += ["", f"**`no_data` bands (elnino): kharif {bef['no_data_k']} -> {nd_k}; rabi {bef['no_data_r']} -> {nd_r}.** Remaining rabi no_data = districts whose rabi foodgrain area is < 0.5 % of their foodgrain area (APY / imputed) "
          f"({sum(1 for d in D if d['risk'][f'{RID}:elnino']['band'] == 'no_data' and (d['data_quality'].get('rabi_no_data_reason') == 'negligible_rabi_foodgrain'))} negligible_rabi_foodgrain).", ""]
    bands_after = {k: pd.Series([d["risk"][k]["band"] for d in D]).value_counts().to_dict() for k in bef["bands"]}
    L += ["| scenario | before (high/medium/low/no_data) | after |", "|---|---|---|"]
    for k in bef["bands"]:
        f4 = lambda dct: "/".join(str(dct.get(b, 0)) for b in ("high", "medium", "low", "no_data"))
        L.append(f"| {k} | {f4(bef['bands'][k])} | {f4(bands_after[k])} |")
    # imputed-count distribution
    cnt = np.array([d["data_quality"].get("imputed_count", 0) for d in D]); cnt_d = np.array([d["data_quality"].get("imputed_data_count", 0) for d in D])
    bins = [(0, 0), (1, 5), (6, 10), (11, 20), (21, 40), (41, 999)]
    L += ["", "## Imputed-count distribution (`data_quality.imputed_count` = entries incl. `risk.*`; `imputed_data_count` = data fields only)", "",
          "| imputed entries | districts (imputed_count) | districts (data fields only) |", "|---|---|---|"]
    for lo, hi in bins:
        L.append(f"| {lo if lo == hi else (f'{lo}-{hi}' if hi < 999 else f'{lo}+')} | {int(((cnt >= lo) & (cnt <= hi)).sum())} | {int(((cnt_d >= lo) & (cnt_d <= hi)).sum())} |")
    srcs = {}
    for d in D:
        for k_, v_ in d["data_quality"].get("imputed", {}).items():
            if not k_.startswith("risk."):
                srcs[v_] = srcs.get(v_, 0) + 1
    L += ["", f"Mean {cnt.mean():.1f} / median {int(np.median(cnt))} / max {int(cnt.max())} entries per district; {int((cnt_d > 0).sum())} districts have at least one imputed data field. "
          "Data-field entries by source: " + ", ".join(f"{k} {v}" for k, v in sorted(srcs.items(), key=lambda x: -x[1])) + ".", ""]
    # sanity: imputed districts' scores vs their neighbours
    adj_ = {int(k): {int(a): float(b) for a, b in v.items()} for k, v in json.load(open(ART / "_adjacency.json"))["adj"].items()}
    byl = {d["lgd"]: d for d in D}
    flagged = lambda d, key: bool((d["risk"].get(key) or {}).get("imputed"))
    don = {int(k): v for k, v in (meta.get("imputation") or {}).get("consumption_side_donors", {}).items()}
    def nb_mean(d, key):
        """border-weighted mean score of the touching districts whose risk is NOT imputed (same state first, else any); consumption-side: its donor districts"""
        if d["data_quality"].get("consumption_side"):
            v = [byl[l]["risk"][key]["score"] for l in meta["imputation"]["consumption_side_donors"].get(str(d["lgd"]), []) if byl[l]["risk"][key]["score"] is not None]
            return (float(np.mean(v)) if v else None), len(v)
        nb = {l: w for l, w in adj_.get(d["lgd"], {}).items() if l in byl and (byl[l]["risk"].get(key) or {}).get("score") is not None and not flagged(byl[l], key)}
        same = {l: w for l, w in nb.items() if byl[l]["state"] == d["state"]}
        pick = same or nb
        if not pick:
            return None, 0
        return float(np.average([byl[l]["risk"][key]["score"] for l in pick], weights=list(pick.values()))), len(pick)
    KK, RR = f"{KID}:elnino", f"{RID}:elnino"
    groups = {"consumption side": lambda d: d["data_quality"].get("consumption_side"),
              "crop structure from the parent (split children)": lambda d: (d["risk"][KK].get("imputed_from") == "parent_split_area_share"),
              "other imputed inputs, kharif (AP / other new districts, partial layers)": lambda d: d["risk"][KK].get("imputed_from") == "imputed_inputs"}
    L += ["## Sanity: imputed districts vs their neighbours (elnino score; neighbours = border-weighted mean of touching districts whose score is not itself imputed; consumption side: its donor districts)", ""]
    def sanity_rows(sel, key, limit=None, sort=True):
        rows = []
        for d in D:
            if not sel(d):
                continue
            sc = (d["risk"].get(key) or {}).get("score")
            if sc is None:
                continue
            nm_, n_ = nb_mean(d, key)
            if nm_ is None:
                continue
            rows.append((d["district"], d["state"], (d["risk"][key] or {}).get("imputed_from", ""), sc, nm_, sc - nm_, n_, d["risk"][key]["band"]))
        return rows
    def summ(rows):
        a = np.array([r[3] for r in rows]); b = np.array([r[4] for r in rows])
        return f"n={len(rows)}, mean diff {np.mean(a - b):+.1f}, mean |diff| {np.mean(np.abs(a - b)):.1f}, Spearman {pd.Series(a).corr(pd.Series(b), method='spearman'):.2f}, within 10 pts of neighbours {int((np.abs(a - b) <= 10).sum())}/{len(rows)}"
    for gname, sel in groups.items():
        rows = sanity_rows(sel, KK)
        if not rows:
            continue
        L += [f"### Kharif - {gname}: {summ(rows)}", "", "| district | state | imputed from | score | neighbour mean | diff | n neighbours | band |", "|---|---|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: -abs(r[5]))[:40]:
            L.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:.1f} | {r[4]:.1f} | {r[5]:+.1f} | {r[6]} | {r[7]} |")
        L.append("")
    rrows = sanity_rows(lambda d: (d["risk"][RR] or {}).get("imputed_from") == "neighbours_exposure", RR)
    if rrows:
        L += [f"### Rabi - districts whose rabi shock is estimated from the touching districts' models: {summ(rrows)}", "",
              "Their own kharif elnino score (not imputed) vs their rabi score, and the neighbour mean rabi score, for the 15 largest differences:", "",
              "| district | state | rabi score | neighbour mean (rabi) | diff | n neighbours | band |", "|---|---|---|---|---|---|---|"]
        for r in sorted(rrows, key=lambda r: -abs(r[5]))[:15]:
            L.append(f"| {r[0]} | {r[1]} | {r[3]:.1f} | {r[4]:.1f} | {r[5]:+.1f} | {r[6]} | {r[7]} |")
        L.append("")
    REP_PATH.write_text(base + "\n".join(L) + "\n")
    print(f"[{time.time() - T0:5.1f}s] 03c_impute_report.md: before/after table, imputed-count distribution, neighbour sanity table appended")
