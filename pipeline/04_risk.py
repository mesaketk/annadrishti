"""04_risk.py - AnnaDrishti risk model (spec: docs/RISK_MODEL.md + SCHEMA Addendum A).

Outputs
  artifacts/risk_district.json   per-lgd risk / hindcast / food_balance / flags (consumed by 06_export.py)
  artifacts/risk_meta.json       thresholds, parameters, hindcast summary
  artifacts/actions_{scenario}.csv
  artifacts/reports/04_risk_report.md

Method refinements agreed for the hackathon build (see report): season-aware exposure (JJAS vs OND),
clipped/imputed El Nino yield betas, null-safe scoring (never 0 for missing), bands from elnino tertiles,
hindcast with actual-year anomaly as the "forecast".
v2 (extra sources, artifacts/extra_district.parquet): +price_spike_risk (exposure, 0.10), +groundwater_stress (sensitivity, 0.10),
+poshan_underweight_live (capacity, 0.10); effective weights renormalised, missing -> reweight.

v3 (ML ensemble, artifacts/ml_ensemble.parquet from 04b_ml_ensemble.py): `expected_yield_shock_pct` = shock_ensemble_pct (analog + LightGBM,
inverse-MAE weights) where available, else the analog formula (`expected_shock_source`); the analog value is kept as `expected_yield_shock_analog_pct`.
Hindcast gains leave-one-year-out LightGBM / analog predictions (artifacts/_ml_loyo_preds.parquet) and out-of-sample rho / gap in risk_meta.hindcast.
Everything else (score pipeline, weights, in-sample hindcast formula) is unchanged; exposure uses the new shock.

v4 (seasons, SCHEMA Addendum F): risk is scored for every `season:phase` key - `<kharif>:{lanina,neutral,elnino,elnino_strong,current}` and
`<rabi>:{...}` (season ids from artifacts/enso_status.json `outlook_seasons`; `current` = probability-weighted mix of the lanina / neutral / elnino phase SHOCKS with
p from enso_status `p_by_season`, then scored). Phases are PURE (the v3 `elnino` scenario weighted the analog by p(El Nino) = 0.61; that weighting now lives in `current`).
The old keys neutral | elnino | elnino_strong are kept as aliases of `<kharif>:*` (same objects). Kharif La Nina = flood scenario (Addendum F rule, from 04b).
Rabi: shocks from artifacts/ml_ensemble_rabi.parquet (04b --season rabi), exposure = expected rabi yield loss (0.5) + terminal-heat hazard (0.3) + weak previous kharif (0.2)
(+ live NDVI, price term); sensitivity and capacity shared with kharif; bands = tertiles of `<kharif>:elnino` for BOTH seasons (comparable thresholds); exposure
percentiles use each season's own El Nino distribution as reference. Districts without a material rabi foodgrain crop (rabi area < 2000 ha or < 5 % of foodgrain area) are
`no_data` for rabi. Rabi hindcast (crop years 2009, 2015, 2021, 2022) uses the leave-one-year-out ensemble predictions (artifacts/_ml_loyo_preds_rabi.parquet).

v5 (imputation, SCHEMA Addendum G; artifacts/imputed_district.parquet + .json from 03c_impute.py): every layer is overlaid with the imputed values WHERE THE SOURCE IS NULL (observed values never change);
percentile ranks / band thresholds still use the OBSERVED districts only (`elig_ref`, observed-only reference per term) so existing districts are not re-ranked by their imputed neighbours.
Newly scored: split / enclave districts whose crop structure comes from the parent (regular model, analog shock), island districts with CHIRPS climate, and `consumption_side` districts
(Delhi, Mumbai, Kolkata, ...: exposure = mean exposure of the donor districts (same state if >= 3 scored, else touching districts, else nearest), sensitivity = low self-sufficiency of the donor pool + PDS
dependency only, capacity as usual; `risk.*.imputed = true`, `imputed_from = urban_consumption_side`). Rabi: districts without a 04b rabi row (negligible-rabi + season-label-gap, rabi area share >= 0.5 %)
take the border-weighted median of their touching districts' rabi model shocks (`expected_shock_source = neighbours`). Emits `data_quality.imputed` / `imputed_count`, `risk.*.imputed`, `imputed_from`, `imputed_share`.

Run: python3 pipeline/04_risk.py      (no network, < 1 min; run 04b (kharif) and 04b --season rabi first when their inputs change)
"""
from __future__ import annotations
import json, os, sys, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import theilslopes

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import districts, ART, save_json, enso_phase_by_monsoon_year

T0 = time.time()
SCEN = ["neutral", "elnino", "elnino_strong"]       # legacy (v3) scenario ids = aliases of <kharif>:* (see KEYS below)
YEARS = list(range(2000, 2026))
HIND_YEARS = [2009, 2014, 2015, 2023]
STRONG_ANALOGS = [2002, 2009, 2015]
GROUPS = ["cereals", "millets", "pulses", "oilseeds"]
OND_STATES = {"Tamil Nadu", "Puducherry"}
OND_EXTRA_LGD = {515: "Sri Potti Sriramulu Nellore", 503: "Chittoor", 517: "Prakasam"}   # coastal AP, NE-monsoon dominated
DRIVERS_N = int(os.environ.get("DRIVERS_N", "8"))      # drivers kept per scenario object (06_export may trim further for file size)
BETA_CLIP = (-40.0, 15.0)
SHOCK_CLIP = (-45.0, 10.0)
import os
BETA_MODE = os.environ.get("BETA_MODE", "blend")   # "elnino" = spec beta only; "blend" = mean(El Nino, rain-deficit-year) effect
G_FLOOR = float(os.environ.get("G_FLOOR", "0.5"))   # JJAS: min share of the El Nino effect realised when the district's own rainfall signal is weak
DEFICIT_THR = -10.0
W_TOP = {"E": 0.45, "S": 0.30, "C": 0.25}
W_NEW = 0.10               # effective (post-renormalisation) weight of each v2 term inside its component
SPIKE_CLIP = (0.0, 40.0)   # only positive El Nino price spikes count (median spike in the data is negative)
BASELINE2 = ART / "_risk_v2_baseline.json"   # frozen snapshot of the v2 (analog-only shock) model, used for the v2 -> v3 section
ENS_PATH = ART / "ml_ensemble.parquet"; ENS_META = ART / "ml_ensemble_meta.json"; LOYO_PATH = ART / "_ml_loyo_preds.parquet"
BASELINE = ART / "_risk_v1_baseline.json"   # frozen snapshot of the pre-v2 model, used for the before/after section
ENS_R_PATH = ART / "ml_ensemble_rabi.parquet"; ENS_R_META = ART / "ml_ensemble_rabi_meta.json"; LOYO_R_PATH = ART / "_ml_loyo_preds_rabi.parquet"
RABI_HIND_YEARS = [2009, 2015, 2021, 2022]           # crop years (rabi sown Oct Y, harvested Mar Y+1)
HEAT_THR_C = 0.5                                      # Feb-Mar tmax anomaly (C) counted as a terminal-heat year
FLOOD_THR = 15.0                                      # La Nina kharif: main-season rain anomaly (%) counted as an excess-rain year (Addendum F)
PH4 = ["lanina", "neutral", "elnino", "elnino_strong"]
STRONG_SET = [2002, 2009, 2015]
CEREAL_KG_PP = 0.18        # t / person / year (ICMR-NIN)
EDIBLE = 0.875
SEASON_LABEL = {"JJAS": "June-Sept (SW monsoon)", "OND": "Oct-Dec (NE monsoon)"}


def log(*a):
    print(f"[{time.time() - T0:5.1f}s]", *a, flush=True)


# ── load ──────────────────────────────────────────────────────────────────────
m = districts()[["lgd", "district", "state", "census11", "centroid_lon", "centroid_lat"]].copy()
crops = pd.read_parquet(ART / "crops_latest.parquet").drop(columns=["district", "state"])
ys_ = pd.read_parquet(ART / "yield_sensitivity.parquet")
clim = pd.read_parquet(ART / "climate_district.parquet")
soc = pd.read_parquet(ART / "social_district.parquet")
panel = pd.read_parquet(ART / "crops_district_year.parquet")
extra = pd.read_parquet(ART / "extra_district.parquet")
for d in (crops, ys_, clim, soc, panel, extra):
    d["lgd"] = d["lgd"].astype(int)
df = (m.merge(crops, on="lgd", how="left").merge(ys_, on="lgd", how="left")
        .merge(clim, on="lgd", how="left").merge(soc, on="lgd", how="left").merge(extra, on="lgd", how="left"))
assert len(df) == 753 and df.lgd.is_unique
N = len(df)

# ── v5: imputation overlay (03c_impute.py): fill ONLY where the source layer is null; df0 keeps the observed layers ─────────────────────────
IMPQ_PATH = ART / "imputed_district.parquet"; IMPJ_PATH = ART / "imputed_district.json"; ADJ_PATH = ART / "_adjacency.json"
df0 = df.copy()
IMPM: dict = {}         # source column -> bool array (row value imputed)
RABO: dict = {}         # rabi structure overrides (rab_*) from 03c (season-label-gap districts: NDVI; split children: parent share)
IMPJ = {"districts": {}, "consumption_side": {}, "split_parent": {}, "rabi_structure": {}}
USE_IMP = IMPQ_PATH.exists() and IMPJ_PATH.exists() and not os.environ.get("NO_IMPUTE")
if USE_IMP:
    _q = pd.read_parquet(IMPQ_PATH).set_index("lgd").reindex(df.lgd.values)
    IMPJ = json.load(open(IMPJ_PATH))
    for c in _q.columns:
        if c.endswith("__src") or c.endswith("__map") or c.startswith(("worldpop", "rabi_ndvi", "rabi_share_est", "rabi_structure")):
            continue
        if c.startswith("rab_"):
            RABO[c] = pd.to_numeric(_q[c], errors="coerce").values.astype(float); continue
        if c not in df.columns:
            continue
        v = _q[c]
        if c in ("jjas_anomaly_json", "ond_anomaly_json"):        # the original JSON exists but holds only nulls where there is no IMD cell
            m_ = v.notna().values & (df.jjas_normal_mm.isna().values & _q.jjas_normal_mm.notna().values)
            df[c] = np.where(m_, v.values, df[c].values); IMPM[c] = m_; continue
        if c in ("nfhs5_json", "nfhs6_json"):
            m_ = v.notna().values
            df[c] = np.where(m_, v.values, df[c].values); IMPM[c] = m_; continue
        m_ = df[c].isna().values & v.notna().values
        if not m_.any():
            continue
        try:
            if pd.api.types.is_numeric_dtype(df[c].dtype) and not pd.api.types.is_bool_dtype(df[c].dtype):
                col = df[c].astype(float).values.copy(); col[m_] = pd.to_numeric(v, errors="coerce").values[m_]
                df[c] = pd.array(col, dtype="Int64") if str(df[c].dtype) == "Int64" else col
            else:
                col = df[c].astype(object).values.copy(); col[m_] = v.values[m_]; df[c] = col
            IMPM[c] = m_
        except Exception as e_:      # noqa
            print("overlay skipped", c, e_)
CONS = np.array([str(int(l)) in IMPJ["consumption_side"] for l in df.lgd.values])      # consumption-side (urban / negligible agriculture / no crops) districts declared by 03c
def IM(col):
    return IMPM.get(col, np.zeros(N, bool))
ADJ04 = {int(k): {int(a): float(b) for a, b in v.items()} for k, v in json.load(open(ADJ_PATH))["adj"].items()} if ADJ_PATH.exists() else {}
LGI = {int(l): i for i, l in enumerate(df.lgd.values)}
log(f"imputation overlay: {'on' if USE_IMP else 'OFF'}; columns overlaid {len(IMPM)}; rabi overrides {len(RABO)}; consumption-side {int(CONS.sum())}")
enso = json.load(open(ART / "enso_status.json"))
gee_path = ART / "gee_live.json"
gee = json.load(open(gee_path)) if gee_path.exists() else None
log("loaded", N, "districts; gee_live:", "present" if gee else "absent")

# ── v4: outlook seasons and ENSO phase probabilities (08_enso_status.py) ─────────────────────────────────────────
_OS = {x["id"]: x for x in (enso.get("outlook_seasons") or [])}
if not _OS:
    _OS = {"rabi_2026_27": {"id": "rabi_2026_27", "lead": "by 2026-11-15"}, "kharif_2027": {"id": "kharif_2027", "lead": "by 2027-05-15"}}
RID = next(i for i in _OS if i.startswith("rabi")); KID = next(i for i in _OS if i.startswith("kharif"))
LEAD = {RID: _OS[RID].get("lead"), KID: _OS[KID].get("lead")}
_PBY = enso.get("p_by_season") or {}
def _pp(sid, dflt):
    v = _PBY.get(sid) or dflt
    t = {k: float(v.get(k, 0.0)) for k in ("elnino", "neutral", "lanina")}
    tot = sum(t.values()) or 1.0
    return {k: x / tot for k, x in t.items()}
P_K = _pp(KID, {"elnino": 0.61, "neutral": 0.33, "lanina": 0.06}); P_R = _pp(RID, {"elnino": 1.0, "neutral": 0.0, "lanina": 0.0})
P_MJJ27, P_OND26 = P_K["elnino"], P_R["elnino"]          # legacy names (risk_meta.p_elnino, report text)
KP = {ph: f"{KID}:{ph}" for ph in PH4 + ["current"]}      # kharif keys
RP = {ph: f"{RID}:{ph}" for ph in PH4 + ["current"]}      # rabi keys
KEYS_K = list(KP.values()); KEYS_R = list(RP.values()); KEYS = KEYS_K + KEYS_R
KREF = KP["elnino"]                                       # reference scenario: exposure percentiles + band tertiles
def kind_of(key):
    return "rabi" if key.split(":")[0] == RID else "kharif"
def phase_of(key):
    return key.split(":")[1]


def series(col: str) -> np.ndarray:
    out = np.full((N, len(YEARS)), np.nan)
    for i, s in enumerate(df[col].values):
        if isinstance(s, str):
            d = json.loads(s)
            for k, y in enumerate(YEARS):
                v = d.get(str(y))
                if v is not None:
                    out[i, k] = v
    return out


def nn(x, nd=None):
    """NaN/NA -> None (never 0)."""
    if x is None or x is pd.NA:
        return None
    try:
        if isinstance(x, (float, np.floating)) and not np.isfinite(x):
            return None
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return (round(float(x), nd) if nd is not None else float(x)) + 0.0
    return x


# ── 1. season-aware rainfall anomalies and ENSO analogs ──────────────────────
is_ond = (df.state.isin(OND_STATES) | df.lgd.isin(OND_EXTRA_LGD)).values
main_season = np.where(is_ond, "OND", "JJAS")
J = series("jjas_anomaly_json"); O = series("ond_anomaly_json")
O = np.clip(O, -100, 100)
A = np.where(is_ond[:, None], O, J)                       # anomaly of each district's MAIN rainy season
phase = enso_phase_by_monsoon_year()
yidx = {y: k for k, y in enumerate(YEARS)}
el_ys = [y for y in YEARS if phase.get(y) == "El Niño"]
ne_ys = [y for y in YEARS if phase.get(y) == "Neutral"]
cols = lambda ys: [yidx[y] for y in ys]
a_el = np.nanmean(A[:, cols(el_ys)], 1); a_neu = np.nanmean(A[:, cols(ne_ys)], 1)
a_strong = np.nanmean(A[:, cols(STRONG_ANALOGS)], 1)
def share_def(ys):
    sub = A[:, cols(ys)]
    n = np.isfinite(sub).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, (sub < DEFICIT_THR).sum(1) / n, np.nan)
P_el = share_def(el_ys); P_neu = share_def(ne_ys); P_strong = share_def(STRONG_ANALOGS)
# consistency with 02_climate parquet (JJAS districts)
jj = ~is_ond & np.isfinite(a_el)
chk_el = float(np.nanmax(np.abs(a_el[jj] - df.elnino_mean_anomaly_pct.values[jj])))
chk_p = float(np.nanmax(np.abs(P_el[jj] - df.elnino_deficit_prob.values[jj])))
log(f"El Nino years {el_ys}; neutral {ne_ys}; max |a_el - parquet| = {chk_el:.2f} pp, max |P_el - parquet| = {chk_p:.3f}")
la_ys = [y for y in YEARS if phase.get(y) == "La Niña"]
a_la = np.nanmean(A[:, cols(la_ys)], 1)
P_flood = np.where(np.isfinite(A[:, cols(la_ys)]).sum(1) > 0, (A[:, cols(la_ys)] > FLOOD_THR).sum(1) / np.maximum(np.isfinite(A[:, cols(la_ys)]).sum(1), 1), np.nan)
# phase probabilities per district: JJAS-main districts use the kharif-season outlook, OND-main districts (NE monsoon = this winter) the rabi-season outlook, as v3 did
pk = {ph: np.where(is_ond, P_R[ph], P_K[ph]) for ph in ("lanina", "neutral", "elnino")}
p_s = pk["elnino"]                                          # El Nino probability for the relevant season/horizon
latest_anom = A[:, yidx[2025]]
has_climate = np.isfinite(a_el) & np.isfinite(a_neu)
has_crops = (df.foodgrain_prod_t.fillna(0) > 0).values
rural = df.rural_share.astype(float).values
no_agri = (rural < 0.05) | (df.foodgrain_area_ha.fillna(0).values < 100)     # all-urban / negligible foodgrain area: crop-shock model not meaningful
no_agri &= has_crops
# v5: `elig_ref` = the pre-imputation scored set (observed climate + crops): the reference population for percentile ranks and band thresholds.
# `elig_reg` = regular model (observed or imputed climate / crop structure); `elig` = elig_reg + consumption-side districts (scored, but with exposure / sensitivity from the surrounding districts).
has_climate_ref = df0.elnino_mean_anomaly_pct.notna().values & df0.neutral_mean_anomaly_pct.notna().values
has_crops_ref = (df0.foodgrain_prod_t.fillna(0) > 0).values
no_agri_ref = ((df0.rural_share.astype(float).values < 0.05) | (df0.foodgrain_area_ha.fillna(0).values < 100)) & has_crops_ref
elig_ref = has_climate_ref & has_crops_ref & ~no_agri_ref
elig_reg = has_climate & has_crops & ~no_agri & ~CONS
elig = elig_reg | CONS
log(f"has_climate {has_climate.sum()}, has_crops {has_crops.sum()}, negligible-agriculture {int((no_agri & has_climate).sum())}, scored {elig.sum()}; OND-main districts {is_ond.sum()}")

# ── 2. yield sensitivity (beta) with clipping and imputation ─────────────────
raw = df.foodgrain_elnino_pct.values.astype(float)
nel = df.n_elnino_years.fillna(0).values
valid = np.isfinite(raw) & (nel >= 3)
beta_el_c = np.where(valid, np.clip(raw, *BETA_CLIP), np.nan)
rawd = df.foodgrain_deficit_year_pct.values.astype(float)
ndf = df.n_deficit_years.fillna(0).values
beta_def_c = np.where(np.isfinite(rawd) & (ndf >= 3), np.clip(rawd, *BETA_CLIP), np.nan)
if BETA_MODE == "blend":
    beta_c = np.where(np.isfinite(beta_el_c) & np.isfinite(beta_def_c), (beta_el_c + beta_def_c) / 2, beta_el_c)
else:
    beta_c = beta_el_c
state_med = pd.Series(beta_c).groupby(df.state.values).agg(["median", "count"])
nat_med = float(np.nanmedian(beta_c))
beta = beta_c.copy(); beta_src = np.array(["district"] * N, dtype=object)
for i in range(N):
    if not np.isfinite(beta[i]):
        st = df.state.iat[i]
        if st in state_med.index and state_med.loc[st, "count"] >= 3:
            beta[i] = state_med.loc[st, "median"]; beta_src[i] = "state_median"
        else:
            beta[i] = nat_med; beta_src[i] = "national_median"
log(f"beta source: {pd.Series(beta_src[elig_reg]).value_counts().to_dict()}; national median {nat_med:.2f}")
beta_g = {}
for g in GROUPS:
    v = df[f"{g}_elnino_pct"].values.astype(float)
    vd = df[f"{g}_deficit_year_pct"].values.astype(float)
    v = np.where(np.isfinite(v), np.clip(v, *BETA_CLIP), np.nan); vd = np.where(np.isfinite(vd), np.clip(vd, *BETA_CLIP), np.nan)
    beta_g[g] = np.where(np.isfinite(v) & np.isfinite(vd), (v + vd) / 2, v) if BETA_MODE == "blend" else v

rain = df.rainfed_share.values.astype(float)
rain_imp = rain.copy(); rain_imputed = ~np.isfinite(rain)
sm = pd.Series(rain).groupby(df.state.values).median()
for i in np.where(rain_imputed)[0]:
    v = sm.get(df.state.iat[i], np.nan)
    rain_imp[i] = v if np.isfinite(v) else np.nanmedian(rain)
mult = 0.4 + 0.6 * rain_imp                               # irrigated districts buffered

gap = a_el - a_neu
denom = np.minimum(gap, -5.0)                              # regularised drying gap (>= 5 pp magnitude)
def frac(a_scn, w_el):
    """Share of the historical El Nino effect realised: 0 = none, 1 = typical El Nino, capped at 2.
    w_el = weight of El Nino in the scenario (0 neutral, p elnino, 1 strong). JJAS districts keep at least
    G_FLOOR x w_el of the empirical El Nino yield effect even if their own 7-year rainfall signal is weak
    (small sample; heat / timing pathways); OND districts get no floor (El Nino usually wets the NE monsoon)."""
    raw_f = np.clip((a_scn - a_neu) / denom, 0, 2)
    return np.maximum(raw_f, np.where(is_ond, 0.0, G_FLOOR) * w_el)

# v4: PURE phases (El Nino weight 1; the v3 `elnino` scenario mixed in p(El Nino) = 0.61 - that weighting now lives in `current`)
KPH3 = [KP["neutral"], KP["elnino"], KP["elnino_strong"]]
a_scn = {KP["neutral"]: a_neu, KP["elnino"]: a_el, KP["elnino_strong"]: a_strong, KP["lanina"]: a_la}
pd_scn = {KP["neutral"]: P_neu, KP["elnino"]: P_el, KP["elnino_strong"]: (P_el + P_strong) / 2, KP["lanina"]: P_flood}
W_EL = {KP["neutral"]: np.zeros(N), KP["elnino"]: np.ones(N), KP["elnino_strong"]: np.ones(N)}
F = {s: frac(a_scn[s], W_EL[s]) for s in KPH3}
shock = {}
for s in KPH3:
    v = np.clip(beta * F[s] * mult, *SHOCK_CLIP) + 0.0
    shock[s] = np.where(elig_reg, v, np.nan)
shock[KP["lanina"]] = np.where(elig_reg, 0.0, np.nan)            # benign unless flagged by the 04b flood rule (set from the ensemble file below)
shock_g = {s: {} for s in KEYS}
for s in KPH3:
    for g in GROUPS:
        b = np.where(np.isfinite(beta_g[g]), beta_g[g], beta)     # fallback to foodgrain beta (flagged)
        shock_g[s][g] = np.where(elig_reg, np.clip(b * F[s] * mult, *SHOCK_CLIP) + 0.0, np.nan)
for g in GROUPS:
    shock_g[KP["lanina"]][g] = shock[KP["lanina"]].copy()
# ── 2b. v3: replace the analog shock by the ML ensemble (analog + LightGBM) where available ─────────────────
shock_analog = {s: shock[s].copy() for s in list(shock)}
shock_src = {s: np.array(["analog"] * N, dtype=object) for s in KEYS}
ens_info = {s: {} for s in KEYS}
ENS_W = None; ENS_RW = None
_li = {int(l): i for i, l in enumerate(df.lgd.values)}
if ENS_PATH.exists():
    _e = pd.read_parquet(ENS_PATH); _e["lgd"] = _e.lgd.astype(int)
    for r_ in _e.itertuples():
        i_ = _li.get(int(r_.lgd))
        k_ = f"{KID}:{r_.scenario}"
        if i_ is None or not elig_reg[i_] or k_ not in shock:
            continue
        if r_.scenario == "lanina":                      # flood rule (04b): analog = beta_LaNina only where flood-flagged, else 0
            shock_analog[k_][i_] = float(r_.shock_analog_pct)
        if not np.isfinite(r_.shock_ensemble_pct):
            continue
        shock[k_][i_] = float(np.clip(r_.shock_ensemble_pct, *SHOCK_CLIP)) + 0.0
        shock_src[k_][i_] = "ensemble"
        ens_info[k_][i_] = dict(analog=r_.shock_analog_pct, lgbm=r_.shock_lgbm_pct, tabfm=r_.shock_tabfm_pct, spread=r_.spread_pct,
                                flood=(bool(r_.flood_flag) if "flood_flag" in _e.columns and np.isfinite(r_.flood_flag) else None))
    if ENS_META.exists():
        ENS_W = json.load(open(ENS_META)).get("weights")
    # group shocks follow the foodgrain shock: group ratio = (group beta / foodgrain beta) from the analog betas (ratio 1 when |beta| < 2 pp, clipped +/-3); La Nina: ratio 1 (flood, not drought)
    for g in GROUPS:
        bg_ = np.where(np.isfinite(beta_g[g]), beta_g[g], beta)
        rg_ = np.where(np.abs(beta) >= 2.0, np.clip(bg_ / np.where(beta == 0, 1, beta), -3, 3), 1.0)
        for s in KPH3:
            new_ = np.clip(rg_ * shock[s], *SHOCK_CLIP) + 0.0
            shock_g[s][g] = np.where(shock_src[s] == "ensemble", new_, shock_g[s][g])
        shock_g[KP["lanina"]][g] = shock[KP["lanina"]].copy()
# La Nina hazard term only for flood-flagged districts (Addendum F: "otherwise benign"): a high share of wet La Nina years with no yield loss is not an exposure
flood_flag_arr = np.array([bool(ens_info[KP["lanina"]].get(i, {}).get("flood")) for i in range(N)])
pd_scn[KP["lanina"]] = np.where(flood_flag_arr, P_flood, np.where(np.isfinite(P_flood), 0.0, np.nan))
# ── v4: RABI phases from artifacts/ml_ensemble_rabi.parquet (04b --season rabi): ensemble / analog / LightGBM shock per scenario, rabi-eligible scored districts only
for ph in PH4:
    shock[RP[ph]] = np.full(N, np.nan); shock_analog[RP[ph]] = np.full(N, np.nan)
rabi_has_ens = np.zeros(N, bool)
if ENS_R_PATH.exists():
    _er = pd.read_parquet(ENS_R_PATH); _er["lgd"] = _er.lgd.astype(int)
    for r_ in _er.itertuples():
        i_ = _li.get(int(r_.lgd))
        if i_ is None or not elig_reg[i_] or not np.isfinite(r_.shock_ensemble_pct):
            continue
        k_ = RP[r_.scenario]
        shock[k_][i_] = float(np.clip(r_.shock_ensemble_pct, *SHOCK_CLIP)) + 0.0
        shock_analog[k_][i_] = float(r_.shock_analog_pct); shock_src[k_][i_] = "ensemble"; rabi_has_ens[i_] = True
        ens_info[k_][i_] = dict(analog=r_.shock_analog_pct, lgbm=r_.shock_lgbm_pct, tabfm=np.nan, spread=r_.spread_pct, flood=None)
    if ENS_R_META.exists():
        ENS_RW = json.load(open(ENS_R_META)).get("weights")
else:
    log("WARNING: artifacts/ml_ensemble_rabi.parquet missing -> rabi keys are no_data (run 04b --season rabi)")
for ph in PH4:
    shock_g[RP[ph]] = {g: np.full(N, np.nan) for g in GROUPS}      # rabi is modelled for total rabi foodgrain, not by crop group
# ── `current` = probability-weighted mix of the lanina / neutral / elnino PHASE SHOCKS (p_by_season), per season
def _mix(d, prefix, w):
    """probability-weighted mean of the lanina / neutral / elnino entries of d (w: scalars or per-district arrays; renormalised)."""
    phs = ("lanina", "neutral", "elnino")
    return sum(w[ph] * d[prefix[ph]] for ph in phs) / sum(w[ph] for ph in phs)
shock[KP["current"]] = _mix(shock, KP, pk); shock_analog[KP["current"]] = _mix(shock_analog, KP, pk)
for g in GROUPS:
    shock_g[KP["current"]][g] = sum(pk[ph] * shock_g[KP[ph]][g] for ph in ("lanina", "neutral", "elnino")) / (pk["lanina"] + pk["neutral"] + pk["elnino"])
shock[RP["current"]] = _mix(shock, RP, P_R); shock_analog[RP["current"]] = _mix(shock_analog, RP, P_R)
for g in GROUPS:
    shock_g[RP["current"]][g] = np.full(N, np.nan)
for pre in (KP, RP):
    shock_src[pre["current"]] = np.where(np.all([shock_src[pre[ph]] == "ensemble" for ph in ("lanina", "neutral", "elnino")], axis=0), "ensemble", "analog").astype(object)
a_scn[KP["current"]] = sum(pk[ph] * a_scn[KP[ph]] for ph in ("lanina", "neutral", "elnino"))
pd_scn[KP["current"]] = sum(pk[ph] * pd_scn[KP[ph]] for ph in ("lanina", "neutral", "elnino"))
log("shock source (scored):", {s: pd.Series(shock_src[s][elig_reg]).value_counts().to_dict() for s in KEYS_K}, "| rabi ensemble rows:", int(rabi_has_ens.sum()))
loss = {s: np.where(np.isfinite(shock[s]), np.maximum(0, -shock[s]), np.nan) for s in KEYS}   # only losses raise exposure

# ── 3. normalisation helpers ─────────────────────────────────────────────────
def ecdf_ref(x):
    r = np.sort(x[np.isfinite(x)]); return r

def pr(x, ref):
    """mid-rank percentile of x against reference sample -> 0..1; NaN stays NaN."""
    x = np.asarray(x, float)
    left = np.searchsorted(ref, x, "left"); right = np.searchsorted(ref, x, "right")
    out = (left + right) / 2 / len(ref)
    return np.where(np.isfinite(x), out, np.nan)

def zrank(x, imp=None):
    """rank-normalise: percentile of every scored district against the OBSERVED reference population (elig_ref, imputed entries of this term excluded),
    so imputed districts never move the existing ones."""
    x = np.where(elig, x, np.nan)
    refm = elig_ref if imp is None else (elig_ref & ~imp)
    return pr(x, ecdf_ref(np.where(refm, x, np.nan)))

def combine(terms):
    """terms: [(name, z, weight)] -> value, effective-weight matrix, z matrix. Rows reweighted over finite terms."""
    Z = np.column_stack([t[1] for t in terms]); W = np.array([t[2] for t in terms], float)
    fin = np.isfinite(Z)
    Wm = fin * W
    tot = Wm.sum(1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        eff = np.where(tot > 0, Wm / tot, 0.0)
    val = np.where(tot[:, 0] > 0, (eff * np.nan_to_num(Z)).sum(1), np.nan)
    return val, eff, np.nan_to_num(Z)

# ── 4. food balance (static + per scenario) ──────────────────────────────────
pop26 = df.population_2026.astype(float).values
prod = df.foodgrain_prod_t.astype(float).values
req = pop26 * CEREAL_KG_PP
edible = prod * EDIBLE
with np.errstate(invalid="ignore", divide="ignore"):
    ss = np.where(req > 0, edible / req, np.nan)
    pds_dep = np.where(req > 0, df.pds_rice_wheat_t_latest12m.values.astype(float) / req, np.nan)
# v4: rabi structure from the season-split panel columns (01_crops v4): median of the last three complete crop years (2021-2023; 2024 is provisional)
_pn = panel[panel.crop_year.between(2021, 2023)]
_g = _pn.groupby("lgd")
rabi_prod = _g.rabi_fg_prod_t.median().reindex(df.lgd.values).values.astype(float)
kharif_prod = _g.kharif_fg_prod_t.median().reindex(df.lgd.values).values.astype(float)
rabi_pulses = _g.rabi_pulses_prod_t.median().reindex(df.lgd.values).values.astype(float)
rabi_area = _g.rabi_fg_area_ha.median().reindex(df.lgd.values).values.astype(float)
rabi_share_prod = np.where((rabi_prod + kharif_prod) > 0, rabi_prod / (rabi_prod + kharif_prod), np.nan)
_a18 = panel[panel.crop_year >= 2018].groupby("lgd")[["rabi_fg_area_ha", "kharif_fg_area_ha"]].median().reindex(df.lgd.values)
rabi_area_share18 = (_a18.rabi_fg_area_ha / (_a18.rabi_fg_area_ha + _a18.kharif_fg_area_ha)).values.astype(float)
rabi_area18 = _a18.rabi_fg_area_ha.values.astype(float)
# v5: rabi structure overrides from 03c (season-label-gap districts: max(APY share, NDVI estimate); split children: the parent's share) - only where 03c provided a value
def _ov(name, arr):
    o = RABO.get(name)
    return arr if o is None else np.where(np.isfinite(o), o, arr)
rabi_prod = _ov("rab_rabi_prod_t", rabi_prod); kharif_prod = _ov("rab_kharif_prod_t", kharif_prod); rabi_pulses = _ov("rab_rabi_pulses_t", rabi_pulses)
rabi_area = _ov("rab_rabi_area_ha", rabi_area); rabi_area18 = _ov("rab_rabi_area_ha_18", rabi_area18); rabi_area_share18 = _ov("rab_rabi_share_area_18", rabi_area_share18)
rabi_share_prod = np.where((rabi_prod + kharif_prod) > 0, rabi_prod / (rabi_prod + kharif_prod), np.nan)
rabi_struct_imp = np.isfinite(RABO.get("rab_rabi_prod_t", np.full(N, np.nan)))
rabi_elig_ref = elig_ref & rabi_has_ens                                    # pre-v5 rule: rabi score only where 04b has a rabi ensemble row (rabi area >= 2000 ha and >= 5 % of foodgrain area, 2018+ median)
RABI_MIN_SHARE = 0.005                                                     # v5: districts below this rabi share of foodgrain area (APY / imputed) have no rabi cropping to score -> rabi no_data
rabi_material = np.isfinite(rabi_area_share18) & (rabi_area_share18 >= RABI_MIN_SHARE)
rabi_nb = elig_reg & ~rabi_has_ens & rabi_material                         # rabi shock estimated from the touching districts' model rows
rabi_elig = (elig_reg & (rabi_has_ens | rabi_nb)) | CONS

def _hav(lon1, lat1, lon2, lat2):
    r = np.pi / 180
    a = np.sin((lat2 - lat1) * r / 2) ** 2 + np.cos(lat1 * r) * np.cos(lat2 * r) * np.sin((lon2 - lon1) * r / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))

def nb_fill(vals, donor_mask, targets):
    """{row i: (value, source)}: border-weighted median of the touching donors (same state first, else any touching; then 2-hop same state; state median; national median)."""
    ok = donor_mask & np.isfinite(vals)
    st = df.state.values; lg = df.lgd.values
    nat = float(np.median(vals[ok]))
    out = {}
    def wm(v, w):
        v = np.asarray(v, float); w = np.asarray(w, float)
        if len(v) <= 2:
            return float(np.average(v, weights=w))
        o = np.argsort(v); cw = np.cumsum(w[o]) / w.sum(); return float(v[o][np.searchsorted(cw, 0.5)])
    for i in targets:
        nb = {LGI[n]: w for n, w in ADJ04.get(int(lg[i]), {}).items() if n in LGI}
        same = {j: w for j, w in nb.items() if ok[j] and st[j] == st[i]}; anyd = {j: w for j, w in nb.items() if ok[j]}
        pick = same or anyd
        if pick:
            out[i] = (wm([vals[j] for j in pick], list(pick.values())), "neighbours_knn"); continue
        two = {}
        for j in nb:
            for n2, w in ADJ04.get(int(lg[j]), {}).items():
                j2 = LGI.get(n2)
                if j2 is not None and j2 != i and ok[j2] and st[j2] == st[i]:
                    two[j2] = max(two.get(j2, 0), w)
        if two:
            out[i] = (wm([vals[j] for j in two], list(two.values())), "neighbours_2hop"); continue
        same_s = np.where(ok & (st == st[i]))[0]
        out[i] = (float(np.median(vals[same_s])), "state_median") if len(same_s) >= 3 else (nat, "national_median")
    return out

def find_donors(i, pool, kmin=3, knear=5):
    """donor rows for a consumption-side district: same-state scored districts (>= kmin), else the touching districts (BFS through the adjacency, also through other consumption-side districts), topped up with the nearest by centroid."""
    lg = df.lgd.values; st = df.state.values
    same = np.where(pool & (st == st[i]))[0]
    if len(same) >= kmin:
        return same
    seen = {int(lg[i])}; frontier = [int(lg[i])]; found = []
    for _ in range(8):
        nxt = []
        for l in frontier:
            for n in ADJ04.get(l, {}):
                if n not in seen:
                    seen.add(n); nxt.append(n)
        found = [LGI[n] for n in seen if n in LGI and pool[LGI[n]]]
        if len(found) >= kmin or not nxt:
            break
        frontier = nxt
    found = sorted(set(found) | set(same.tolist()))
    if len(found) < kmin:
        cand = np.where(pool)[0]
        d = _hav(df.centroid_lon.values[i], df.centroid_lat.values[i], df.centroid_lon.values[cand], df.centroid_lat.values[cand])
        found = sorted(set(found) | set(cand[np.argsort(d)[:knear]].tolist()))
    return np.array(found, int)

if rabi_nb.any() and ADJ04:
    _tg = list(np.where(rabi_nb)[0])
    for ph in PH4:
        k_ = RP[ph]
        for arr_ in (shock[k_], shock_analog[k_]):
            for i_, (v_, src_) in nb_fill(arr_, rabi_has_ens, _tg).items():
                arr_[i_] = v_
        for i_ in _tg:
            shock_src[k_][i_] = "neighbours"
    shock[RP["current"]] = _mix(shock, RP, P_R); shock_analog[RP["current"]] = _mix(shock_analog, RP, P_R)
    shock_src[RP["current"]] = np.where(np.all([shock_src[RP[ph]] == "ensemble" for ph in ("lanina", "neutral", "elnino")], axis=0), "ensemble",
                                        np.where(rabi_nb, "neighbours", "analog")).astype(object)
# consumption-side districts: donor rows (kharif: regular scored districts; rabi: regular rabi-scored) and donor-mean shocks for every key
DON_K, DON_R = {}, {}
if CONS.any():
    _pool_k = elig_reg; _pool_r = rabi_elig & ~CONS
    for i_ in np.where(CONS)[0]:
        DON_K[i_] = find_donors(i_, _pool_k); DON_R[i_] = find_donors(i_, _pool_r)
    for s_ in KEYS:
        for i_ in np.where(CONS)[0]:
            d_ = (DON_R if kind_of(s_) == "rabi" else DON_K)[i_]
            for arr_ in (shock[s_], shock_analog[s_]):
                v_ = arr_[d_]; v_ = v_[np.isfinite(v_)]
                arr_[i_] = float(v_.mean()) if len(v_) else np.nan
            shock_src[s_][i_] = "neighbours"
loss = {s: np.where(np.isfinite(shock[s]), np.maximum(0, -shock[s]), np.nan) for s in KEYS}
_kd = pd.read_parquet(ART / "_ml_panel_rabi.parquet") if (ART / "_ml_panel_rabi.parquet").exists() else None
kdev_last = (_kd[_kd.year == 2024].set_index("lgd").prev_kharif_dev.reindex(df.lgd.values).values.astype(float) if _kd is not None else np.full(N, np.nan))   # kharif 2024 deviation from trend (latest observed)
rdev_last = (_kd[_kd.year == 2024].set_index("lgd").prev_rabi_dev.reindex(df.lgd.values).values.astype(float) if _kd is not None else np.full(N, np.nan))
_nyr = panel[panel.crop_year >= 2018].groupby("lgd").rabi_fg_area_ha.apply(lambda x_: int((x_ >= 2000).sum())).reindex(df.lgd.values).fillna(0).values
rabi_reason = np.where(~elig, "not_scored", np.where(~np.isfinite(rabi_area18) | (rabi_area18 < 2000) | (rabi_area_share18 < 0.05), "negligible_rabi_foodgrain",
                       np.where(_nyr < 3, "rabi_season_label_gap", "no_rabi_model_row")))
log(f"rabi-eligible scored districts {int(rabi_elig.sum())} of {int(elig.sum())} (pre-v5 rule {int(rabi_elig_ref.sum())}; neighbour-imputed {int(rabi_nb.sum())}; consumption side {int((CONS & rabi_elig).sum())}); not eligible: {pd.Series(rabi_reason[elig & ~rabi_elig]).value_counts().to_dict()}")

deficit = {}
for s in KEYS:
    with np.errstate(invalid="ignore"):
        if kind_of(s) == "rabi":
            edible_s = edible + rabi_prod * EDIBLE * shock[s] / 100          # only the rabi part of the annual foodgrain edible output is shocked
        else:
            edible_s = edible * (1 + shock[s] / 100)
        deficit[s] = np.maximum(0, req - edible_s)
        deficit[s] = np.where(np.isfinite(edible_s) & np.isfinite(req), deficit[s], np.nan)

# ── 5. components ─────────────────────────────────────────────────────────────
def nfhs_pick(base, fallback_ok=True):
    a = df[f"{base}_nfhs6"].values.astype(float) if f"{base}_nfhs6" in df else np.full(N, np.nan)
    b = df[f"{base}_nfhs5"].values.astype(float) if f"{base}_nfhs5" in df else np.full(N, np.nan)
    return np.where(np.isfinite(a), a, b), np.where(np.isfinite(a), 6, np.where(np.isfinite(b), 5, 0))

def json_field(col, key, frame=None):
    out = np.full(N, np.nan)
    for i, s in enumerate((df if frame is None else frame)[col].values):
        if isinstance(s, str):
            v = json.loads(s).get(key)
            if v is not None:
                out[i] = v
    return out

stunt, stunt_r = nfhs_pick("stunting"); wast, wast_r = nfhs_pick("wasting"); anae, anae_r = nfhs_pick("child_anaemia")
def nfhs_imp(base):
    a_ = df[f"{base}_nfhs6"].values.astype(float) if f"{base}_nfhs6" in df else np.full(N, np.nan)
    return np.where(np.isfinite(a_), IM(f"{base}_nfhs6"), IM(f"{base}_nfhs5"))
I_stunt, I_wast, I_anae = nfhs_imp("stunting"), nfhs_imp("wasting"), nfhs_imp("child_anaemia")
bmi6 = json_field("nfhs6_json", "women_bmi_low"); bmi5 = json_field("nfhs5_json", "women_bmi_low")
bmi = np.where(np.isfinite(bmi6), bmi6, bmi5); bmi_r = np.where(np.isfinite(bmi6), 6, np.where(np.isfinite(bmi5), 5, 0))
I_bmi = np.where(np.isfinite(bmi6), ~np.isfinite(json_field("nfhs6_json", "women_bmi_low", df0)), ~np.isfinite(json_field("nfhs5_json", "women_bmi_low", df0)))
wan = np.where(np.isfinite(df.women_anaemia_nfhs6.values.astype(float)), df.women_anaemia_nfhs6.values.astype(float),
               df.women_anaemia_nfhs5.values.astype(float))
cvi = df.clim_vuln_index.values.astype(float)
top_share = df.top_crop_share.values.astype(float); cv10 = df.yield_cv10.values.astype(float)
smf = df.small_marginal_share.values.astype(float)
low_ss = 1 - np.clip(ss, 0, 1.5) / 1.5
# v5 imputed-input masks (these entries are excluded from the reference distribution of their term and are flagged in the output)
I_rain, I_top, I_cv, I_smf, I_cvi = IM("rainfed_share"), IM("top_crop_share"), IM("yield_cv10"), IM("small_marginal_share"), IM("clim_vuln_index")
I_ss = IM("foodgrain_prod_t") | IM("population_2026"); I_pds = IM("pds_rice_wheat_t_latest12m") | IM("population_2026")
I_gw = IM("gw_stress_idx"); I_pw = IM("poshan_underweight_pct"); I_price = IM("price_elnino_spike_pct") | IM("price_volatility_idx"); I_clim = IM("jjas_normal_mm")

# v2 extra sources (NaN stays NaN -> term dropped and the rest reweighted; never 0 for missing)
f_ = lambda c: df[c].values.astype(float)
px_spike = f_("price_elnino_spike_pct"); px_vol = f_("price_volatility_idx")
px_raw = np.where(np.isfinite(px_spike) & np.isfinite(px_vol),
                  0.5 * np.clip(px_spike, *SPIKE_CLIP) / SPIKE_CLIP[1] + 0.5 * px_vol, np.nan)
px_crop = df.price_crop.values
gw_stress = f_("gw_stress_idx"); gw_depth = f_("gw_premonsoon_depth_m"); gw_dec = f_("gw_decline_10y_m_per_yr")
gw_year = df.gw_latest_year.astype("float").values; gw_src = df.gw_source.values
pw_uw = f_("poshan_underweight_pct"); pw_asof = df.poshan_as_of.values

# live NDVI (optional)
ndvi = np.full(N, np.nan)
if gee:
    dd = gee.get("districts", {})
    for i, l in enumerate(df.lgd.values):
        v = (dd.get(str(l)) or {}).get("ndvi_anom")
        if v is not None:
            ndvi[i] = v
has_live_ndvi = bool(np.isfinite(ndvi[elig]).any())

Z_S = [("rainfed_share", zrank(rain, I_rain), 0.30), ("top_crop_share", zrank(top_share, I_top), 0.20), ("yield_cv", zrank(cv10, I_cv), 0.15),
       ("small_marginal_share", zrank(smf, I_smf), 0.20), ("low_self_sufficiency", zrank(low_ss, I_ss), 0.15)]
Z_S.append(("groundwater_stress", zrank(gw_stress, I_gw), sum(t[2] for t in Z_S) * W_NEW / (1 - W_NEW)))
Z_C = [("child_stunting", zrank(stunt, I_stunt), 0.30), ("child_wasting", zrank(wast, I_wast), 0.15), ("child_anaemia", zrank(anae, I_anae), 0.15),
       ("women_bmi_low", zrank(bmi, I_bmi), 0.10), ("pds_dependency", zrank(pds_dep, I_pds), 0.15), ("climate_vulnerability", zrank(cvi, I_cvi), 0.15)]
Z_C.append(("poshan_underweight_live", zrank(pw_uw, I_pw), sum(t[2] for t in Z_C) * W_NEW / (1 - W_NEW)))
S_IMP = np.column_stack([I_rain, I_top, I_cv, I_smf, I_ss, I_gw]); C_IMP = np.column_stack([I_stunt, I_wast, I_anae, I_bmi, I_pds, I_cvi, I_pw])
S_val, S_eff, S_z = combine(Z_S)
C_val, C_eff, C_z = combine(Z_C)
# v5 consumption side: sensitivity = low self-sufficiency of the donor pool (they eat what the region grows) + PDS dependency only; no crop-structure terms
Z_CS = None
if CONS.any():
    lowss_cs = np.full(N, np.nan)
    for i_ in np.where(CONS)[0]:
        d_ = DON_K[i_]; e_ = edible[d_]; r_ = req[d_]; okd = np.isfinite(e_) & np.isfinite(r_)
        if okd.any():
            lowss_cs[i_] = 1 - np.clip(e_[okd].sum() / r_[okd].sum(), 0, 1.5) / 1.5
    z_low_cs = pr(lowss_cs, ecdf_ref(np.where(elig_ref & ~I_ss, low_ss, np.nan)))
    z_pds_cs = pr(np.where(CONS, pds_dep, np.nan), ecdf_ref(np.where(elig_ref & ~I_pds, pds_dep, np.nan)))
    Z_CS = [("low_self_sufficiency", z_low_cs, 0.5), ("pds_dependency_s", z_pds_cs, 0.5)]
    S_cs, S_cs_eff, S_cs_z = combine(Z_CS)
    S_val = np.where(CONS, S_cs, S_val)
    S_eff = np.where(CONS[:, None], 0.0, S_eff); S_z = np.where(CONS[:, None], 0.0, S_z)
# v4: temperature / OND structure for rabi hazard terms
TF = series("tmax_febmar_anomaly_json")
def share_heat(ys):
    sub = TF[:, [yidx[y + 1] for y in ys]]
    n = np.isfinite(sub).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, (sub >= HEAT_THR_C).sum(1) / np.maximum(n, 1), np.nan)
def mean_tf(ys):
    return np.nanmean(TF[:, [yidx[y + 1] for y in ys]], 1)
def mean_ond(ys):
    return np.nanmean(O[:, [yidx[y] for y in ys]], 1)
_cy = YEARS[:-1]       # crop years with an observed Feb-Mar of Y+1
_pyrs = {"neutral": [y for y in _cy if phase.get(y) == "Neutral"], "lanina": [y for y in _cy if phase.get(y) == "La Niña"],
         "elnino": [y for y in _cy if phase.get(y) == "El Niño"], "elnino_strong": STRONG_SET}
tf_scn, ond_scn = {}, {}
for ph in PH4:
    pd_scn[RP[ph]] = share_heat(_pyrs[ph]); tf_scn[RP[ph]] = mean_tf(_pyrs[ph]); ond_scn[RP[ph]] = mean_ond(_pyrs[ph])
pd_scn[RP["current"]] = sum(P_R[ph] * pd_scn[RP[ph]] for ph in ("lanina", "neutral", "elnino"))
tf_scn[RP["current"]] = sum(P_R[ph] * tf_scn[RP[ph]] for ph in ("lanina", "neutral", "elnino"))
ond_scn[RP["current"]] = sum(P_R[ph] * ond_scn[RP[ph]] for ph in ("lanina", "neutral", "elnino"))
a_scn.update({RP[ph]: ond_scn[RP[ph]] for ph in PH4 + ["current"]})      # `rain_anomaly_pct` of a rabi scenario = mean OND anomaly of its phase years
def zrank_r(x, imp=None):
    x = np.where(rabi_elig, x, np.nan)
    refm = rabi_elig_ref if imp is None else (rabi_elig_ref & ~imp)
    return pr(x, ecdf_ref(np.where(refm, x, np.nan)))
ref_loss = ecdf_ref(loss[KREF][elig_ref]); ref_def = ecdf_ref(pd_scn[KREF][elig_ref])
ref_loss_r = ecdf_ref(loss[RP["elnino"]][rabi_elig_ref]); ref_haz_r = ecdf_ref(pd_scn[RP["elnino"]][rabi_elig_ref])
z_ant = zrank(-latest_anom, I_clim)
z_carry = zrank_r(-kdev_last)
z_ndvi = zrank(-ndvi) if has_live_ndvi else np.full(N, np.nan)
z_price = zrank(px_raw, I_price)

def hz_name_for(key):
    return {"lanina": "rain_excess_risk", "current": "rain_hazard_risk"}.get(phase_of(key), "rain_deficit_risk")

def exposure_terms(loss_v, def_v, ant_z, with_live=True, kind="kharif", hz_name="rain_deficit_risk"):
    if kind == "rabi":
        # rabi drivers: expected rabi yield loss, terminal-heat hazard (share of phase winters with Feb-Mar tmax >= +0.5 C), weak previous kharif (income / seed carry-over)
        # a district with no expected loss gets 0 on the loss term (the rabi El Nino reference has ~45 % zero-loss districts, whose mid-rank percentile would otherwise be ~0.22)
        _lz = np.where(rabi_elig, loss_v, np.nan)
        t = [("expected_yield_loss", np.where(_lz > 0, pr(_lz, ref_loss_r), np.where(np.isfinite(_lz), 0.0, np.nan)), 0.5),
             ("terminal_heat_risk", pr(np.where(rabi_elig, def_v, np.nan), ref_haz_r), 0.3),
             ("weak_kharif_carryover", ant_z, 0.2)]
    else:
        t = [("expected_yield_loss", pr(np.where(elig, loss_v, np.nan), ref_loss), 0.5),
             (hz_name, pr(np.where(elig, def_v, np.nan), ref_def), 0.3),
             ("dry_antecedent_season", ant_z, 0.2)]
    if with_live and has_live_ndvi:
        t.append(("ndvi_stress", z_ndvi, 0.15))
    # v2: price spike risk gets an effective weight of W_NEW (the other terms, incl. live NDVI, are scaled to 1 - W_NEW)
    t.append(("price_spike_risk", z_price, sum(x[2] for x in t) * W_NEW / (1 - W_NEW)))
    return t

def top_level(E, S, C):
    B = np.column_stack([E, S, C]); w = np.array([W_TOP["E"], W_TOP["S"], W_TOP["C"]])
    fin = np.isfinite(B); Wm = fin * w; tot = Wm.sum(1, keepdims=True)
    eff = np.where(tot > 0, Wm / tot, 0.0)
    val = np.where(tot[:, 0] > 0, (eff * np.nan_to_num(B)).sum(1), np.nan)
    return val, eff

RES = {}
for s in KEYS:
    kd = kind_of(s); ok = rabi_elig if kd == "rabi" else elig
    kw = dict(kind=kd, hz_name=hz_name_for(s))
    ant_ = z_carry if kd == "rabi" else z_ant
    tms = exposure_terms(loss[s], pd_scn[s], ant_, **kw)
    E_val, E_eff, E_z = combine(tms)
    E_val = np.where(ok & ~CONS, E_val, np.nan)
    for i_ in np.where(CONS & ok)[0]:                       # v5: consumption side - exposure of the districts they draw their food from
        d_ = (DON_R if kd == "rabi" else DON_K)[i_]; v_ = E_val[d_]; v_ = v_[np.isfinite(v_)]
        E_val[i_] = float(v_.mean()) if len(v_) else np.nan
        E_eff[i_, :] = 0.0; E_z[i_, :] = 0.0
    tl, eff = top_level(E_val, S_val, C_val)
    score = np.where(ok, 100 * tl, np.nan)
    RES[s] = dict(E=E_val, E_eff=E_eff, E_z=E_z, score=score, eff=eff, E_names=[t[0] for t in tms], ok=ok)

PRICE_W_RAW = exposure_terms(loss[KREF], pd_scn[KREF], z_ant)[-1][2]
# bands: tertiles of the kharif elnino scenario scores, applied to every season / scenario (comparable thresholds)
sc_el = RES[KREF]["score"][elig_ref]
t_lo, t_hi = float(np.quantile(sc_el, 1 / 3)), float(np.quantile(sc_el, 2 / 3))
def band_of(x):
    return np.where(~np.isfinite(x), "no_data", np.where(x >= t_hi, "high", np.where(x >= t_lo, "medium", "low")))
for s in KEYS:
    RES[s]["band"] = band_of(RES[s]["score"])
    sc = RES[s]["score"]
    # priority ranks: score desc, tie -> larger loss, then lgd
    order = pd.DataFrame({"i": np.arange(N), "sc": np.where(np.isfinite(sc), sc, -1), "ls": np.nan_to_num(loss[s], nan=-1), "lgd": df.lgd.values})
    order = order[np.isfinite(sc)].sort_values(["sc", "ls", "lgd"], ascending=[False, False, True])
    rn = np.full(N, np.nan); rn[order.i.values] = np.arange(1, len(order) + 1)
    rs = np.full(N, np.nan)
    for st, g in order.assign(state=df.state.values[order.i.values]).groupby("state"):
        rs[g.i.values] = np.arange(1, len(g) + 1)
    RES[s]["rank_nat"] = rn; RES[s]["rank_state"] = rs
log(f"bands from {KREF} tertiles: lo {t_lo:.1f}, hi {t_hi:.1f}; counts " +
    str({s: pd.Series(RES[s]["band"]).value_counts().to_dict() for s in KEYS}))

# ── 6. drivers (term, weight x z, plain-English label) ───────────────────────
top_crop = df.top_crop.fillna("one crop").values
def _pm(x):
    return "0.0%" if abs(x) < 0.05 else f"{x:+.1f}%".replace("-", "\u2212")
def lab_loss(i, s):
    v = shock[s][i]; kw_ = "rabi " if kind_of(s) == "rabi" else ""
    if not (v < -0.05):
        return f"No {kw_}foodgrain yield loss expected under this scenario"
    if shock_src[s][i] == "neighbours":
        return f"Expected {kw_}foodgrain yield loss {abs(v):.1f}% (estimated from the models of neighbouring districts)"
    if shock_src[s][i] == "ensemble" and i in ens_info[s]:
        e = ens_info[s][i]
        mem = [f"analog {_pm(e['analog'])}", f"LightGBM {_pm(e['lgbm'])}"] + ([f"TabFM {_pm(e['tabfm'])}"] if np.isfinite(e["tabfm"]) else [])
        extra = " - flood-prone district (La Nina excess rain)" if e.get("flood") else ""
        return f"Expected {kw_}foodgrain yield loss {abs(v):.1f}% (ensemble of {' and '.join(mem)}, spread {e['spread']:.1f} pp){extra}"
    if phase_of(s) == "current":
        return f"Expected {kw_}foodgrain yield loss {abs(v):.1f}% (ENSO-probability-weighted mix of phase scenarios)"
    return f"Expected {kw_}foodgrain yield loss of {abs(v):.0f}% vs trend under this scenario"
def lab_def(i, s):
    ph = phase_of(s)
    if ph == "lanina":
        return f"{pd_scn[s][i] * 100:.0f}% of La Nina years had >{FLOOD_THR:.0f}% excess {main_season[i]} rainfall (flood risk)"
    if ph == "current":
        return f"{pd_scn[s][i] * 100:.0f}% probability-weighted chance of a damaging {main_season[i]} rainfall anomaly (deficit >10% or excess >{FLOOD_THR:.0f}%)"
    return f"{pd_scn[s][i] * 100:.0f}% chance of a >10% {main_season[i]} rainfall deficit"
def lab_ant(i, s):
    return f"Last {main_season[i]} season (2025) rainfall was {latest_anom[i]:+.0f}% vs normal"
def lab_heat(i, s):
    return f"{pd_scn[s][i] * 100:.0f}% of comparable winters had terminal heat (Feb-Mar max temperature >= {HEAT_THR_C:+.1f} C above normal)"
def lab_carry(i, s):
    return f"Last observed kharif (2024) foodgrain yield was {kdev_last[i]:+.0f}% vs trend (income and seed carry-over into rabi)"
def lab_price(i, s):
    c = px_crop[i] if isinstance(px_crop[i], str) else "main crop"
    if px_spike[i] >= 0.5:
        return f"El Niño-year farm-gate price spike {px_spike[i]:+.0f}% (ICRISAT, main crop {c})"
    return f"Farm-gate price volatility index {px_vol[i]:.2f} of 1 (ICRISAT, main crop {c}); no El Niño-year price spike"
def lab_gw(i, s):
    d = gw_dec[i]
    trend = f"deepening {d:.1f} m/yr" if d > 0.05 else (f"recovering {abs(d):.1f} m/yr" if d < -0.05 else "stable")
    src = gw_src[i] if isinstance(gw_src[i], str) else "CGWB"
    yr = f" {int(gw_year[i])}" if np.isfinite(gw_year[i]) else ""
    return f"Pre-monsoon water table {gw_depth[i]:.1f} m, {trend} ({src}{yr})"
def lab_poshan(i, s):
    mo = pd.Timestamp(pw_asof[i]).strftime("%b-%Y") if isinstance(pw_asof[i], str) else "latest"
    return f"Poshan Tracker {mo}: {pw_uw[i]:.0f}% of measured children underweight"
LABELS = {
    "price_spike_risk": lab_price, "groundwater_stress": lab_gw, "poshan_underweight_live": lab_poshan,
    "expected_yield_loss": lab_loss, "rain_deficit_risk": lab_def, "rain_excess_risk": lab_def, "rain_hazard_risk": lab_def, "dry_antecedent_season": lab_ant,
    "terminal_heat_risk": lab_heat, "weak_kharif_carryover": lab_carry,
    "ndvi_stress": lambda i, s: f"Live vegetation (NDVI) anomaly {ndvi[i]:+.2f} vs normal",
    "rainfed_share": lambda i, s: f"{rain[i] * 100:.0f}% of cropped area is rainfed",
    "top_crop_share": lambda i, s: f"{top_share[i] * 100:.0f}% of cropped area is under a single crop ({top_crop[i]})",
    "yield_cv": lambda i, s: f"Foodgrain yields vary {cv10[i] * 100:.0f}% year to year (10-yr CV)",
    "small_marginal_share": lambda i, s: f"{smf[i] * 100:.0f}% of holdings are small or marginal (<2 ha)",
    "low_self_sufficiency": lambda i, s: f"Local foodgrain meets only {ss[i] * 100:.0f}% of cereal+pulse needs",
    "child_stunting": lambda i, s: f"{stunt[i]:.0f}% of children under 5 are stunted (NFHS-{stunt_r[i]})",
    "child_wasting": lambda i, s: f"{wast[i]:.0f}% of children under 5 are wasted (NFHS-{wast_r[i]})",
    "child_anaemia": lambda i, s: f"{anae[i]:.0f}% of children are anaemic (NFHS-{anae_r[i]})",
    "women_bmi_low": lambda i, s: f"{bmi[i]:.0f}% of women are underweight (BMI<18.5, NFHS-{bmi_r[i]})",
    "pds_dependency": lambda i, s: f"PDS rice+wheat supply equals {pds_dep[i] * 100:.0f}% of cereal needs",
    "climate_vulnerability": lambda i, s: f"Climate vulnerability index {cvi[i]:.2f} (0-1)",
}

IMP_TERM = {"rainfed_share": I_rain, "top_crop_share": I_top, "yield_cv": I_cv, "small_marginal_share": I_smf, "low_self_sufficiency": I_ss, "groundwater_stress": I_gw,
            "child_stunting": I_stunt, "child_wasting": I_wast, "child_anaemia": I_anae, "women_bmi_low": I_bmi, "pds_dependency": I_pds, "climate_vulnerability": I_cvi,
            "poshan_underweight_live": I_pw, "price_spike_risk": I_price, "dry_antecedent_season": I_clim}
LABELS["consumption_exposure"] = lambda i, s: "Food supply here depends on the surrounding districts' harvests; their combined climate / yield exposure is " + f"{RES[s]['E'][i]:.2f} of 1"
LABELS["pds_dependency_s"] = LABELS["pds_dependency"]
_lab_ss = LABELS["low_self_sufficiency"]
def _ss_cs_label(i, s):
    if CONS[i] and Z_CS is not None and np.isfinite(lowss_cs[i]):
        return f"Foodgrain grown in the surrounding districts meets only {100 * (1 - lowss_cs[i]) * 1.5:.0f}% of the cereal+pulse needs of the region"
    return _lab_ss(i, s)
LABELS["low_self_sufficiency"] = _ss_cs_label
def drivers_cons(i, s):
    r = RES[s]; wE, wS, wC = r["eff"][i]
    items = [("consumption_exposure", wE * (r["E"][i] if np.isfinite(r["E"][i]) else 0.0))]
    for k, t in enumerate(Z_CS):
        v = t[1][i]
        if np.isfinite(v):
            items.append((t[0], wS * float(S_cs_eff[i, k]) * v))
    for k, t in enumerate(Z_C):
        items.append((t[0], wC * C_eff[i, k] * C_z[i, k]))
    items = sorted([(n, c) for n, c in items if c > 0], key=lambda x: -x[1])
    out = []
    for n, c in items[:DRIVERS_N]:
        try:
            lab = LABELS[n](i, s)
        except Exception:
            lab = n.replace("_", " ")
        if n in IMP_TERM and IMP_TERM[n][i]:
            lab += " (estimated)"
        out.append({"name": n, "contrib": round(float(c), 3), "label": lab})
    return out

def drivers_for(i, s):
    if CONS[i]:
        return drivers_cons(i, s)
    r = RES[s]; wE, wS, wC = r["eff"][i]
    items = []
    for k, nme in enumerate(r["E_names"]):
        items.append((nme, wE * r["E_eff"][i, k] * r["E_z"][i, k]))
    for k, t in enumerate(Z_S):
        items.append((t[0], wS * S_eff[i, k] * S_z[i, k]))
    for k, t in enumerate(Z_C):
        items.append((t[0], wC * C_eff[i, k] * C_z[i, k]))
    items = [(n, c) for n, c in items if c > 0]
    items.sort(key=lambda x: -x[1])
    out = []
    for n, c in items[:DRIVERS_N]:
        try:
            lab = LABELS[n](i, s)
        except Exception:
            lab = n.replace("_", " ")
        if n in IMP_TERM and IMP_TERM[n][i]:
            lab += " (estimated)"
        out.append({"name": n, "contrib": round(float(c), 3), "label": lab})
    return out

# ── 7. actions ────────────────────────────────────────────────────────────────
gca = df.gross_cropped_area_ha.astype(float).values
u5 = df.children_u5_est.astype(float).values
agri_share = df.agri_workers_share.astype(float).values
cult_est = (pop26 * df.worker_participation.astype(float).values * df.cultivator_share_workers.astype(float).values)
pmfby = df.pmfby_farmers.astype(float).values
groups_parsed = [json.loads(s) if isinstance(s, str) else {} for s in df.groups_json.values]
def grp(i, g, k):
    v = (groups_parsed[i].get(g) or {}).get(k)
    return np.nan if v is None else float(v)
pulses_prod = np.array([grp(i, "pulses", "prod_t") for i in range(N)])
mill_area = np.nan_to_num(np.array([grp(i, "millets", "area_ha") for i in range(N)]))
cash_area = np.nan_to_num(np.array([grp(i, "cash", "area_ha") for i in range(N)]))
fodder_share = np.where(gca > 0, (mill_area + cash_area) / gca, np.nan)

ACT = {}
for s in KEYS:
    band = RES[s]["band"]; kd = kind_of(s)
    nk = KP["neutral"] if kd == "kharif" else RP["neutral"]
    a = {}
    a["grain_preposition_t"] = np.maximum(0, deficit[s] - deficit[nk])
    if kd == "kharif":
        ps = shock_g[s]["pulses"]
        a["pulses_preposition_t"] = np.where(pulses_prod > 0, pulses_prod * np.maximum(0, -ps) / 100 * EDIBLE, np.nan)
    else:       # rabi pulses (gram, lentil, peas): rabi foodgrain shock applied to rabi pulses production (no separate rabi group model)
        a["pulses_preposition_t"] = np.where(rabi_pulses > 0, rabi_pulses * np.maximum(0, -shock[s]) / 100 * EDIBLE, np.nan)
    a["anganwadi_children"] = u5 * stunt / 100
    a["women_anaemia_target"] = pop26 * 0.26 * wan / 100
    sb = 0.2 * rain * gca if kd == "kharif" else 0.2 * rabi_area      # kharif: short-duration / millet / flood-tolerant seed; rabi: heat-tolerant / early-sown wheat varieties
    a["seed_bank_ha"] = np.where(band == "no_data", np.nan, np.where(band != "low", sb, np.where(np.isfinite(sb), 0.0, np.nan)))
    mg = pop26 * agri_share * 0.4 * 50 * rain
    a["mgnrega_persondays"] = np.where(band == "no_data", np.nan, np.where(band == "high", mg, np.where(np.isfinite(mg), 0.0, np.nan)))
    pm_eff = pmfby / 2.0     # PMFBY farmer_count is farmer-seasons (kharif+rabi) -> ~unique farmers
    gapf = np.maximum(0, cult_est - pm_eff)
    a["pmfby_gap_farmers"] = np.where(np.isfinite(cult_est) & np.isfinite(pmfby), gapf, np.nan)
    ff = np.where(band == "no_data", np.nan, ((band == "high") & (fodder_share > 0.3)).astype(float))
    ff = np.where(CONS, np.nan, ff)
    a["fodder_flag"] = ff
    if kd == "rabi":
        # Addendum F rabi menu: timely sowing before 15 Nov, heat-tolerant / early wheat varieties (seed_bank_ha), 1-2 protective irrigations at crown-root and grain filling
        # (protective_irrigation_ha = rabi foodgrain area x irrigated share, band != low), groundwater budgeting (flag: gw_stress_idx >= 0.67 and band != low), PDS wheat lifting (grain_preposition_t)
        irr_ = df.irrigated_share.astype(float).values
        pi_ = rabi_area * irr_
        a["protective_irrigation_ha"] = np.where(band == "no_data", np.nan, np.where(band != "low", pi_, np.where(np.isfinite(pi_), 0.0, np.nan)))
        gwf = np.where(band == "no_data", np.nan, ((gw_stress >= 0.67) & (band != "low")).astype(float))
        gwf = np.where(np.isfinite(gw_stress) | (band == "no_data"), gwf, np.nan)
        a["groundwater_budget_flag"] = gwf
    ACT[s] = a

# v4: legacy in-memory aliases (neutral | elnino | elnino_strong -> <kharif>:<phase>) used by the v1-v3 report sections below
for _so in SCEN:
    for _d in (RES, shock, shock_analog, shock_src, ens_info, shock_g, loss, deficit, a_scn, pd_scn, ACT):
        _d[_so] = _d[KP[_so]]

# ── 8. hindcast ──────────────────────────────────────────────────────────────
_elig_x, _rabi_elig_x = elig, rabi_elig
elig, rabi_elig = elig_ref, rabi_elig_ref            # v5: the hindcasts stay on the observed population (imputed districts have no observed yield deviations anyway)
piv = panel.pivot_table(index="lgd", columns="crop_year", values="foodgrain_yield_t_ha", aggfunc="first")
def actual_dev(lgd, Y):
    if lgd not in piv.index or Y not in piv.columns:
        return np.nan
    row = piv.loc[lgd]
    yv = row.get(Y, np.nan)
    ys_ = [y for y in range(Y - 10, Y) if y in row.index and np.isfinite(row[y])]
    if len(ys_) < 6 or not np.isfinite(yv):
        return np.nan
    sl, ic, _, _ = theilslopes([row[y] for y in ys_], ys_)
    pred = ic + sl * Y
    if pred <= 0.05:
        return np.nan
    return float(np.clip((yv - pred) / pred * 100, -100, 100))

def spearman(x, y):
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(d) < 10:
        return np.nan, len(d)
    return float(np.corrcoef(d.x.rank().values, d.y.rank().values)[0, 1]), len(d)

HC = {}; HSUM = {}
LOYO = pd.read_parquet(LOYO_PATH) if LOYO_PATH.exists() else None
ML_META = json.load(open(ENS_META)) if ENS_META.exists() else None
def loyo_pivot(col):
    if LOYO is None:
        return None
    return LOYO.pivot_table(index="lgd", columns="year", values=col, aggfunc="first")
LOYO_L, LOYO_A = loyo_pivot("pred_lgbm"), loyo_pivot("pred_analog")
def oos_pred(piv_, lgd_, Y):
    if piv_ is None or lgd_ not in piv_.index or Y not in piv_.columns:
        return np.nan
    return float(piv_.at[lgd_, Y])
for Y in HIND_YEARS:
    aY = A[:, yidx[Y]]; ant = zrank(-A[:, yidx[Y - 1]])
    fY = frac(aY, np.where(phase.get(Y) == "El Niño", 1.0, 0.0) * np.ones(N))
    shY = np.where(elig, np.clip(beta * fY * mult, *SHOCK_CLIP) + 0.0, np.nan)
    lsY = np.where(np.isfinite(shY), np.maximum(0, -shY), np.nan)
    ph = phase.get(Y)
    dfY = {"El Niño": P_el, "Neutral": P_neu}.get(ph, P_neu)
    t = exposure_terms(lsY, np.where(elig, dfY, np.nan), ant, with_live=False)
    E_Y, _, _ = combine(t)
    tl, _ = top_level(E_Y, S_val, C_val)
    pscore = np.where(elig, 100 * tl, np.nan)
    dev = np.array([actual_dev(int(l), Y) for l in df.lgd.values])
    HC[Y] = dict(pred=pscore, dev=dev, anom=aY,
                 lgbm_oos=np.array([oos_pred(LOYO_L, int(l), Y) for l in df.lgd.values]),
                 analog_oos=np.array([oos_pred(LOYO_A, int(l), Y) for l in df.lgd.values]))
    rho, n = spearman(pscore, dev)
    rho_e, _ = spearman(E_Y, dev)
    rho_rain, _ = spearman(np.where(elig, -aY, np.nan), dev)
    ok = np.isfinite(pscore) & np.isfinite(dev)
    q1, q2 = np.quantile(pscore[ok], [1 / 3, 2 / 3])
    topm = float(dev[ok & (pscore >= q2)].mean()); botm = float(dev[ok & (pscore <= q1)].mean())
    HSUM[str(Y)] = dict(phase=ph, n=int(n), spearman_rho=round(rho, 3), rho_exposure_only=round(rho_e, 3),
                        rho_dryness_only=round(rho_rain, 3), top_tercile_mean_dev_pct=round(topm, 2),
                        bottom_tercile_mean_dev_pct=round(botm, 2), top_minus_bottom_pct=round(topm - botm, 2),
                        mean_all_india_anomaly_pct=round(float(np.nanmean(aY[elig])), 1))
    if ML_META is not None:
        py = ML_META["per_year"]
        def _g(k, f, nd):
            v = (py.get(k, {}).get(str(Y)) or {}).get(f)
            return None if v is None or not np.isfinite(v) else round(float(v), nd)
        # out-of-sample (leave-one-year-out, 04b): Spearman(predicted shock, actual dev) -> POSITIVE = good; gap = worst-predicted minus best-predicted tercile -> NEGATIVE = good
        HSUM[str(Y)].update(rho_lgbm_oos=_g("lgbm", "rho", 3), rho_analog_oos=_g("analog", "rho", 3), rho_ensemble_oos=_g("ensemble", "rho", 3),
                            gap_lgbm_oos=_g("lgbm", "gap", 2), gap_analog_oos=_g("analog", "gap", 2), gap_ensemble_oos=_g("ensemble", "gap", 2),
                            mae_lgbm_oos=_g("lgbm", "mae", 2), mae_analog_oos=_g("analog", "mae", 2), n_oos=int((py.get("lgbm", {}).get(str(Y)) or {}).get("n") or 0))
log("hindcast:", {y: (v["spearman_rho"], v["top_minus_bottom_pct"], v.get("rho_lgbm_oos"), v.get("rho_analog_oos")) for y, v in HSUM.items()})

# ── 8b. v4: rabi hindcast (crop years 2009-10, 2015-16 El Nino winters, 2021-22 incl. the March-2022 heatwave, 2022-23) ──────────────────────────────────────────
HCR = {}; HSUM_R = {}
LOYO_R = pd.read_parquet(LOYO_R_PATH) if LOYO_R_PATH.exists() else None
MR_META = json.load(open(ENS_R_META)) if ENS_R_META.exists() else None
if LOYO_R is not None and MR_META is not None and _kd is not None:
    shift_r = float(MR_META.get("hindcast_level_shift_pct") or 0.0)
    _pv = lambda col: LOYO_R.pivot_table(index="lgd", columns="year", values=col, aggfunc="first")
    P_L, P_A, P_E, P_ACT = (_pv(c) for c in ("pred_lgbm", "pred_analog", "pred_ensemble", "actual"))
    _kdy = _kd.pivot_table(index="lgd", columns="year", values="prev_kharif_dev", aggfunc="first")      # kharif deviation of the same crop year (precedes the rabi)
    def _gv(piv_, Y):
        return np.array([float(piv_.at[l, Y]) if (l in piv_.index and Y in piv_.columns) else np.nan for l in df.lgd.values])
    for Y in RABI_HIND_YEARS:
        ens_Y, act_Y = _gv(P_E, Y), _gv(P_ACT, Y)
        shY = np.where(rabi_elig & np.isfinite(ens_Y), np.clip(ens_Y - shift_r, *SHOCK_CLIP), np.nan)      # leave-one-year-out ensemble, pooled level bias removed
        lsY = np.where(np.isfinite(shY), np.maximum(0, -shY), np.nan)
        tfY = TF[:, yidx[Y + 1]]
        hzY = np.where(np.isfinite(tfY), (tfY >= HEAT_THR_C).astype(float), np.nan)          # observed terminal-heat winter: 1 / 0
        tY = exposure_terms(lsY, np.where(rabi_elig, hzY, np.nan), zrank_r(-_gv(_kdy, Y)), with_live=False, kind="rabi")
        E_Y, _, _ = combine(tY); E_Y = np.where(rabi_elig, E_Y, np.nan)
        tl, _ = top_level(E_Y, S_val, C_val)
        pscore = np.where(rabi_elig & np.isfinite(shY), 100 * tl, np.nan)
        HCR[Y] = dict(pred=pscore, dev=act_Y, tf=tfY, lgbm=_gv(P_L, Y), analog=_gv(P_A, Y), ens=ens_Y, shock=shY)
        rho, n = spearman(pscore, act_Y); rho_e, _ = spearman(E_Y, act_Y); rho_heat, _ = spearman(np.where(rabi_elig, tfY, np.nan), act_Y)
        ok_ = np.isfinite(pscore) & np.isfinite(act_Y)
        q1, q2 = np.quantile(pscore[ok_], [1 / 3, 2 / 3])
        topm = float(act_Y[ok_ & (pscore >= q2)].mean()); botm = float(act_Y[ok_ & (pscore <= q1)].mean())
        HSUM_R[str(Y)] = dict(crop_year=f"{Y}-{(Y + 1) % 100:02d}", phase=phase.get(Y), n=int(n), spearman_rho=round(rho, 3), rho_exposure_only=round(rho_e, 3),
                              rho_heat_only=round(rho_heat, 3), top_tercile_mean_dev_pct=round(topm, 2), bottom_tercile_mean_dev_pct=round(botm, 2),
                              top_minus_bottom_pct=round(topm - botm, 2), mean_tmax_febmar_anomaly_c=round(float(np.nanmean(tfY[rabi_elig])), 2),
                              share_districts_heat_year=round(float(np.nanmean(hzY[rabi_elig])), 2), mean_actual_dev_pct=round(float(np.nanmean(act_Y[ok_])), 2))
        py = MR_META["per_year"]
        def _gr(k, f_, nd):
            v = (py.get(k, {}).get(str(Y)) or {}).get(f_)
            return None if v is None or not np.isfinite(v) else round(float(v), nd)
        HSUM_R[str(Y)].update(rho_lgbm_oos=_gr("lgbm", "rho", 3), rho_analog_oos=_gr("analog", "rho", 3), rho_ensemble_oos=_gr("ensemble", "rho", 3),
                              gap_lgbm_oos=_gr("lgbm", "gap", 2), gap_analog_oos=_gr("analog", "gap", 2), gap_ensemble_oos=_gr("ensemble", "gap", 2),
                              mae_lgbm_oos=_gr("lgbm", "mae", 2), mae_analog_oos=_gr("analog", "mae", 2), n_oos=int((py.get("lgbm", {}).get(str(Y)) or {}).get("n") or 0))
    log("rabi hindcast:", {y: (v["spearman_rho"], v["top_minus_bottom_pct"], v["rho_lgbm_oos"], v["rho_heat_only"]) for y, v in HSUM_R.items()})
else:
    log("rabi hindcast skipped (missing _ml_loyo_preds_rabi.parquet / meta / _ml_panel_rabi.parquet)")

elig, rabi_elig = _elig_x, _rabi_elig_x
# ── 8b. v6 (Addendum I): season_outlook[season][phase] per district + national means ─────────────────────────────────────────
# Kharif: rain = the scenario anomaly used in exposure (a_scn; main season: JJAS, or OND for the OND-main districts); p_deficit_gt10 = share of El Nino years with a > 10 % deficit (strong: mean with the strong
# analogs; neutral: climatological share of all years; La Nina: share of La Nina years > +15 %, i.e. the flood share, as the contract says; current: probability-weighted TRUE deficit share);
# tmax = JJAS tmax anomaly of the phase's years (neutral 0); onset delay = phase-year mean onset day - climatology; TimesFM (JJAS 2027) display fields, JJAS-main districts only.
# Rabi: rain = OND anomaly of the phase's years (ond_scn), tmax = Feb-Mar (following year) tmax anomaly of the phase's years, the same series as the rabi score's terminal-heat hazard (tf_scn; neutral 0, La Nina -0.3 stated assumption).
def _nm(M, ys):
    sub = M[:, [yidx[y] for y in ys if y in yidx]]
    n = np.isfinite(sub).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, np.nansum(np.where(np.isfinite(sub), sub, 0.0), 1) / np.maximum(n, 1), np.nan)
TJ_ = series("tmax_jjas_anomaly_json"); ON_ = series("onset_day_json")
P_clim_def = share_def(YEARS); P_la_def = share_def(la_ys)
TMAX_K = {"elnino": _nm(TJ_, el_ys), "elnino_strong": _nm(TJ_, STRONG_ANALOGS), "lanina": _nm(TJ_, la_ys)}
TMAX_K["neutral"] = np.where(np.isfinite(TMAX_K["elnino"]), 0.0, np.nan)
_on_clim = _nm(ON_, YEARS)
ONSET_K = {"elnino": _nm(ON_, el_ys) - _on_clim, "elnino_strong": _nm(ON_, STRONG_ANALOGS) - _on_clim, "lanina": _nm(ON_, la_ys) - _on_clim, "neutral": _nm(ON_, ne_ys) - _on_clim}
_tf_el = _nm(TF, el_ys)
TMAX_R = {"elnino": tf_scn[RP["elnino"]], "elnino_strong": tf_scn[RP["elnino_strong"]], "neutral": np.where(np.isfinite(tf_scn[RP["elnino"]]), 0.0, np.nan), "lanina": np.where(np.isfinite(tf_scn[RP["elnino"]]), -0.3, np.nan)}
PDEF_K = {"elnino": P_el, "elnino_strong": (P_el + P_strong) / 2, "neutral": P_clim_def, "lanina": P_flood}
PDEF_TRUE = {"elnino": P_el, "neutral": P_clim_def, "lanina": P_la_def}
_tfm = pd.read_parquet(ART / "timesfm_summary.parquet").set_index("lgd").reindex(df.lgd.values) if (ART / "timesfm_summary.parquet").exists() else None
def _wmix(d, w):
    """probability-weighted mean over lanina / neutral / elnino of the arrays / scalars in d (NaN where any member is NaN)"""
    return sum(w[ph] * d[ph] for ph in ("lanina", "neutral", "elnino")) / sum(w[ph] for ph in ("lanina", "neutral", "elnino"))
PDEF_K["current"] = _wmix(PDEF_TRUE, pk)
TMAX_K["current"] = _wmix(TMAX_K, pk); ONSET_K["current"] = _wmix(ONSET_K, pk)
TMAX_R["current"] = _wmix(TMAX_R, P_R)
_TXT = {"lanina": "La Niña", "neutral": "neutral", "elnino": "El Niño", "elnino_strong": "El Niño"}
def _lw(p):
    """likelihood word from a phase probability: >= 0.8 very likely, 0.5-0.8 likely, 0.1-0.5 possible, < 0.1 unlikely (the contract's 'else possible' split at 0.1 so a 0 % phase is not called possible)"""
    if p is None or not np.isfinite(p):
        return "possible"
    return "very likely" if p >= 0.8 else ("likely" if p >= 0.5 else ("possible" if p >= 0.10 else "unlikely"))
def _rain_phr(a, wnd):
    r = "rain" if wnd == "Jun–Sep" else f"{wnd} rain"
    if a <= -5: return f"about {abs(a):.0f} % less {r} than normal"
    if a >= 5: return f"about {a:.0f} % more {r} than normal"
    return f"{r} close to normal on average"
def _n10(p):
    return max(1, int(round(p * 10)))
def plain_kharif(ph, pword, a, pdef, wnd, drying=None, pflood=None):
    """farmer-facing sentence (phrasing rule): El Nino -> weak monsoon, La Nina -> heavy rain / flooding, neutral -> near-normal season; probability word from the ENSO phase probability `pword`
    (a phase with p < 0.1 is written as 'in <phase> years (unlikely this season)'; the strong El Nino analog carries no probability word - p_by_season has no strong split).
    `drying` / `pflood` (default from a / pdef) decide whether the district's own record supports the El Nino / La Nina head line."""
    if a is None or not np.isfinite(a):
        return None
    pd_ = pdef if (pdef is not None and np.isfinite(pdef)) else None
    unl = (pword is not None and np.isfinite(pword) and pword < 0.10)
    if ph in ("elnino", "elnino_strong"):
        dry = drying if drying is not None else (a <= -5 or (pd_ is not None and pd_ >= 0.5))
        w = "" if ph == "elnino_strong" else f" {_lw(pword)}"
        if ph == "elnino_strong":
            head = "In a strong El Ni\u00f1o, weak monsoon" if dry else "In a strong El Ni\u00f1o, near-normal monsoon"
        else:
            head = f"Weak monsoon{w}" if dry else "Near-normal monsoon possible even in El Ni\u00f1o years here"
        tail = [_rain_phr(a, wnd)] + ([f"{_n10(pd_)} in 10 chance of a serious deficit"] if pd_ is not None and pd_ >= 0.15 else [])
    elif ph == "lanina":
        pf = pflood if pflood is not None else pd_
        fl = (pf is not None and pf >= 0.25) or a >= 5
        if fl:
            head = f"Heavy rain / flooding {_lw(pword)}" if not unl else "Heavy rain / flooding possible in La Ni\u00f1a years here (unlikely this season)"
        else:
            head = "Heavy rain / flooding unlikely here even in La Ni\u00f1a years"
        tail = ([_rain_phr(a, wnd)] if a >= 5 else []) + ([f"{_n10(pf)} in 10 La Ni\u00f1a years had flood-level excess rain"] if pf is not None and pf >= 0.15 else [])
        if not tail:
            tail = ["La Ni\u00f1a years have rarely brought excess rain here"]
    else:
        head = f"Near-normal season {_lw(pword)}"
        tail = [_rain_phr(a, wnd)] + ([f"a serious deficit hits about {_n10(pd_)} in 10 years"] if pd_ is not None and pd_ >= 0.15 else [])
    return f"{head}: {', '.join(tail)}"
def plain_rabi(ph, pword, a, tmax, strong=False):
    if a is None or not np.isfinite(a):
        return None
    dry, wet = a <= -5, a >= 5
    hot = tmax is not None and np.isfinite(tmax) and tmax >= 0.3
    cool = tmax is not None and np.isfinite(tmax) and tmax <= -0.3
    w1 = "Dry" if dry else ("Wet" if wet else "")
    w2 = "warm" if hot else ("cool" if cool else "")
    name = (f"{w1}, {w2} winter" if (w1 and w2) else (f"{w1} winter" if w1 else (f"{w2.capitalize()} winter" if w2 else "Near-normal winter")))
    rain = "less Oct\u2013Dec rain" if dry else ("more Oct\u2013Dec rain" if wet else "Oct\u2013Dec rain close to normal")
    heat = f"hotter Feb\u2013Mar (about +{tmax:.1f} \u00b0C)" if hot else ("cooler Feb\u2013Mar" if cool else "Feb\u2013Mar temperatures close to normal")
    if strong:
        head = f"In a strong El Ni\u00f1o, {name[0].lower()}{name[1:]}"
    elif pword is not None and np.isfinite(pword) and pword < 0.10:
        head = f"{name} in {_TXT.get(ph, ph)} years (unlikely this season)"
    else:
        head = f"{name} {_lw(pword)}"
    return f"{head}: {rain} and {heat}"
def _dom(pdict):
    return max(("elnino", "neutral", "lanina"), key=lambda k: pdict[k])
def so_phase_obj(kind, ph, i):
    """one season_outlook[season][phase] object for district index i (None fields where there is no data)"""
    if kind == "kharif":
        wnd = "Oct–Dec" if is_ond[i] else "Jun–Sep"
        a = a_scn[KP[ph]][i]
        pdef = PDEF_K[ph][i] if ph in PDEF_K else np.nan
        pp = {k: float(pk[k][i]) for k in ("elnino", "neutral", "lanina")}
        if ph == "current":
            d = _dom(pp); pw = pp[d]
            # the head line follows the dominant phase and that phase's own record (drying / flood-prone), numbers are the probability-weighted ones
            dry = (a_scn[KP["elnino"]][i] <= -5 or P_el[i] >= 0.5) if d == "elnino" else None
            txt = plain_kharif(d if d != "elnino" else "elnino", pw, a, pdef, wnd, drying=dry, pflood=P_flood[i])
        else:
            pw = pp["elnino" if ph == "elnino_strong" else ph]
            txt = plain_kharif(ph, pw, a, pdef, wnd)
        o = {"rain_anom_pct": nn(a, 1), "rain_window": wnd, "p_deficit_gt10": nn(pdef, 2), "tmax_anom_c": nn(TMAX_K[ph][i], 2), "heat_window": "Jun–Sep",
             "onset_delay_days": nn(ONSET_K[ph][i], 1)}
        if _tfm is not None and not is_ond[i]:
            o.update(timesfm_rain_anom_pct=nn(_tfm.jjas2027_anom_pct.iat[i], 1), timesfm_p10=nn(_tfm.jjas2027_p10_pct.iat[i], 1), timesfm_p90=nn(_tfm.jjas2027_p90_pct.iat[i], 1))
        else:
            o.update(timesfm_rain_anom_pct=None, timesfm_p10=None, timesfm_p90=None)
        o["plain"] = txt
        return o
    a = a_scn[RP[ph]][i]; tm = TMAX_R[ph][i]
    d = _dom(P_R) if ph == "current" else None
    pw = P_R[d] if ph == "current" else P_R["elnino" if ph == "elnino_strong" else ph]
    return {"rain_anom_pct": nn(a, 1), "rain_window": "Oct–Dec", "tmax_anom_c": nn(tm, 2), "heat_window": "Feb–Mar", "plain": plain_rabi(d or ph, pw, a, tm, strong=(ph == "elnino_strong"))}
SO_PH = ["lanina", "neutral", "elnino", "elnino_strong", "current"]
SEASON_OUTLOOK = {}
for _i in range(N):
    if not has_climate[_i]:
        SEASON_OUTLOOK[_i] = None; continue
    SEASON_OUTLOOK[_i] = {KID: {ph: so_phase_obj("kharif", ph, _i) for ph in SO_PH}, RID: {ph: so_phase_obj("rabi", ph, _i) for ph in SO_PH}}
# national: cropped-area-weighted means of the same fields, `plain` built from the national means with the national phase probabilities
_wgt = df.gross_cropped_area_ha.astype(float).values
SO_NATIONAL = {}
for _kind, _sid, _P in (("kharif", KID, P_K), ("rabi", RID, P_R)):
    SO_NATIONAL[_sid] = {}
    for ph in SO_PH:
        acc = {}
        for f in (["rain_anom_pct", "p_deficit_gt10", "tmax_anom_c", "onset_delay_days", "timesfm_rain_anom_pct", "timesfm_p10", "timesfm_p90"] if _kind == "kharif" else ["rain_anom_pct", "tmax_anom_c"]):
            v = np.array([np.nan if SEASON_OUTLOOK[i_] is None or SEASON_OUTLOOK[i_][_sid][ph][f] is None else SEASON_OUTLOOK[i_][_sid][ph][f] for i_ in range(N)], float)
            w = np.where(np.isfinite(v) & np.isfinite(_wgt) & (_wgt > 0), _wgt, 0.0)
            acc[f] = (float((np.nan_to_num(v) * w).sum() / w.sum()) if w.sum() > 0 else None, int((w > 0).sum()))
        o = {f: (None if m is None else round(m, 2 if f in ("p_deficit_gt10", "tmax_anom_c") else 1)) for f, (m, n_) in acc.items()}
        o["n_districts"] = max(n_ for _, n_ in acc.values())
        if _kind == "kharif":
            o = {"rain_anom_pct": o["rain_anom_pct"], "rain_window": "Jun–Sep", "p_deficit_gt10": o["p_deficit_gt10"], "tmax_anom_c": o["tmax_anom_c"], "heat_window": "Jun–Sep",
                 "onset_delay_days": o["onset_delay_days"], "timesfm_rain_anom_pct": o["timesfm_rain_anom_pct"], "timesfm_p10": o["timesfm_p10"], "timesfm_p90": o["timesfm_p90"], "n_districts": o["n_districts"]}
            if ph == "current":
                d_ = _dom(_P); o["plain"] = plain_kharif(d_, _P[d_], o["rain_anom_pct"], o["p_deficit_gt10"], "Jun–Sep", drying=(None if d_ != "elnino" else (SO_NATIONAL[_sid]["elnino"]["rain_anom_pct"] <= -5 or SO_NATIONAL[_sid]["elnino"]["p_deficit_gt10"] >= 0.5)), pflood=SO_NATIONAL[_sid]["lanina"]["p_deficit_gt10"])
            else:
                o["plain"] = plain_kharif(ph, _P["elnino" if ph == "elnino_strong" else ph], o["rain_anom_pct"], o["p_deficit_gt10"], "Jun–Sep")
        else:
            o = {"rain_anom_pct": o["rain_anom_pct"], "rain_window": "Oct–Dec", "tmax_anom_c": o["tmax_anom_c"], "heat_window": "Feb–Mar", "n_districts": o["n_districts"]}
            d_ = _dom(_P) if ph == "current" else None
            o["plain"] = plain_rabi(d_ or ph, _P[d_] if d_ else _P["elnino" if ph == "elnino_strong" else ph], o["rain_anom_pct"], o["tmax_anom_c"], strong=(ph == "elnino_strong"))
        SO_NATIONAL[_sid][ph] = o
log("season_outlook built:", sum(v is not None for v in SEASON_OUTLOOK.values()), "districts")

# ── 9. assemble per-district output ──────────────────────────────────────────
IMP_FLAG_SHARE = 0.25            # risk.*.imputed = true when imputed inputs carry >= 25 % of the score weight (or the exposure itself is imputed)
_I_prod = IM("foodgrain_prod_t")
STRUCT_K = np.full(N, None, dtype=object); STRUCT_R = np.full(N, None, dtype=object)
for _i in range(N):
    _t = "urban_consumption_side" if CONS[_i] else ("ee_chirps" if I_clim[_i] else ("parent_split_area_share" if _I_prod[_i] else None))
    STRUCT_K[_i] = _t
    STRUCT_R[_i] = _t or ("neighbours_exposure" if rabi_nb[_i] else None)
def imputed_share(s_, i_):
    """share of the district's score weight that rests on imputed inputs (0-1)"""
    r_ = RES[s_]; wE, wS, wC = r_["eff"][i_]; kd_ = kind_of(s_); sh = 0.0
    if CONS[i_]:
        sh += wE + wS                                                       # exposure from the donors, sensitivity from donor-pool supply (+ own PDS)
    else:
        for k_, nme in enumerate(r_["E_names"]):
            if nme == "price_spike_risk" and I_price[i_]:
                sh += wE * r_["E_eff"][i_, k_]
            elif nme in ("expected_yield_loss", "rain_deficit_risk", "rain_excess_risk", "rain_hazard_risk", "dry_antecedent_season") and (I_clim[i_] or (nme == "expected_yield_loss" and kd_ == "rabi" and rabi_nb[i_])):
                sh += wE * r_["E_eff"][i_, k_]
        sh += wS * float((S_eff[i_] * S_IMP[i_]).sum())
    sh += wC * float((C_eff[i_] * C_IMP[i_]).sum())
    return min(1.0, sh)
def _qi(x):
    """rounded whole-number quantity as int (smaller JSON than 15521.0), null for missing"""
    v = nn(x, 0)
    return None if v is None else int(v)

def act_obj(s, i):
    a = ACT[s]; kd = kind_of(s)
    if RES[s]["band"][i] == "no_data":
        return None
    fl = a["fodder_flag"][i]
    o = {
        "grain_preposition_t": _qi(a["grain_preposition_t"][i]), "pulses_preposition_t": _qi(a["pulses_preposition_t"][i]),
        "anganwadi_children": _qi(a["anganwadi_children"][i]), "women_anaemia_target": _qi(a["women_anaemia_target"][i]),
        "seed_bank_ha": _qi(a["seed_bank_ha"][i]), "mgnrega_persondays": _qi(a["mgnrega_persondays"][i]),
        "pmfby_gap_farmers": _qi(a["pmfby_gap_farmers"][i]),
        "fodder_flag": None if not np.isfinite(fl) else bool(fl), "lead": (dict(LEAD) if kd == "kharif" else {RID: LEAD[RID]}),   # kharif objects keep both lead dates (v3 shape)
        "priority_rank_state": nn(RES[s]["rank_state"][i]) and int(RES[s]["rank_state"][i]),
        "priority_rank_national": nn(RES[s]["rank_nat"][i]) and int(RES[s]["rank_nat"][i]),
        "season": KID if kd == "kharif" else RID,
    }
    if kd == "rabi":
        g_ = a["groundwater_budget_flag"][i]
        o["protective_irrigation_ha"] = _qi(a["protective_irrigation_ha"][i])
        o["groundwater_budget_flag"] = None if not np.isfinite(g_) else bool(g_)
    return o

def risk_obj(s, i):
    r = RES[s]; kd = kind_of(s); sid = KID if kd == "kharif" else RID
    if r["band"][i] == "no_data":
        o = {"score": None, "band": "no_data", "exposure": None, "sensitivity": None, "capacity": None,
             "expected_yield_shock_pct": None, "drivers": [], "actions": None}
        if kd == "rabi":
            o["no_data_reason"] = str(rabi_reason[i]) if elig[i] else "not_scored"
        return o
    o = {"score": nn(r["score"][i], 1), "band": str(r["band"][i]),
         "exposure": nn(r["E"][i], 3), "sensitivity": nn(S_val[i], 3), "capacity": nn(C_val[i], 3),
         "expected_yield_shock_pct": nn(shock[s][i], 1),
         "expected_shock_source": str(shock_src[s][i]),
         "expected_yield_shock_analog_pct": nn(shock_analog[s][i], 1),
         "rain_anomaly_pct": nn(a_scn[s][i], 1), "season": (str(main_season[i]) if kd == "kharif" else "rabi"),
         "shock_by_group": ({g: (nn(shock_g[s][g][i], 1) if (np.isfinite(grp(i, g, "prod_t")) and grp(i, g, "prod_t") > 0) else None) for g in GROUPS} if kd == "kharif" else None),   # rabi is not modelled by crop group
         "drivers": drivers_for(i, s), "actions": act_obj(s, i)}
    st_ = STRUCT_R[i] if kd == "rabi" else STRUCT_K[i]
    ish_ = imputed_share(s, i)
    if st_ is not None or ish_ >= IMP_FLAG_SHARE:             # Addendum G: still a real band, flagged
        o["imputed"] = True; o["imputed_from"] = st_ or "imputed_inputs"; o["imputed_share"] = round(ish_, 2)
    if kd == "rabi":
        o["tmax_febmar_anomaly_c"] = nn(tf_scn[s][i], 2); o["terminal_heat_year_share"] = nn(pd_scn[s][i], 2)
    elif phase_of(s) == "lanina":
        o["flood_flag"] = (None if i not in ens_info[s] or ens_info[s][i].get("flood") is None else bool(ens_info[s][i]["flood"]))
        o["flood_year_share"] = nn(P_flood[i], 2)
    return o

out = {}
for i, lgd in enumerate(df.lgd.values):
    risk = {s: risk_obj(s, i) for s in KEYS}
    for s_old in SCEN:                                   # backward-compatible aliases: the same objects as <kharif>:<phase>
        risk[s_old] = risk[KP[s_old]]
    hind = {}
    for Y in HIND_YEARS:
        hind[str(Y)] = {"predicted_score": nn(HC[Y]["pred"][i], 1), "actual_foodgrain_yield_dev_pct": nn(HC[Y]["dev"][i], 1),
                        "rain_anomaly_pct": nn(HC[Y]["anom"][i], 1),
                        "predicted_shock_lgbm_oos_pct": nn(HC[Y]["lgbm_oos"][i], 1),
                        "predicted_shock_analog_oos_pct": nn(HC[Y]["analog_oos"][i], 1)}
    if all(v["predicted_score"] is None and v["actual_foodgrain_yield_dev_pct"] is None and v["predicted_shock_lgbm_oos_pct"] is None for v in hind.values()):
        hind = None
    hind_r = {}
    for Y, h in HCR.items():
        hind_r[str(Y)] = {"predicted_score": nn(h["pred"][i], 1), "actual_rabi_yield_dev_pct": nn(h["dev"][i], 1), "tmax_febmar_anomaly_c": nn(h["tf"][i], 2),
                          "predicted_shock_lgbm_oos_pct": nn(h["lgbm"][i], 1)}
    if not hind_r or all(v["predicted_score"] is None and v["actual_rabi_yield_dev_pct"] is None for v in hind_r.values()):
        hind_r = None
    fb_ok = np.isfinite(req[i]) and np.isfinite(prod[i])
    fb = {"requirement_t": nn(req[i], 0), "edible_prod_t": nn(edible[i], 0), "self_sufficiency": nn(ss[i], 3),
          "pds_dependency": nn(pds_dep[i], 3)}
    if not np.isfinite(req[i]) and not np.isfinite(prod[i]):
        fb = None
    gfb = [g for g in GROUPS if not np.isfinite(beta_g[g][i]) and np.isfinite(grp(i, g, "prod_t")) and grp(i, g, "prod_t") > 0]
    # Addendum G: imputed map {dotted path: source}; entries from 03c + those derived here
    imp_map = dict(IMPJ["districts"].get(str(int(lgd)), {}))
    if np.isfinite(ss[i]) and (_I_prod[i] or IM("population_2026")[i]) and "food_balance.self_sufficiency" not in imp_map:
        imp_map["food_balance.self_sufficiency"] = ("parent_split_area_share" if _I_prod[i] else imp_map.get("population_2026", "ee_worldpop"))
    if elig_reg[i] and beta_src[i] != "district":
        imp_map["yield_sensitivity.beta_used_pct"] = str(beta_src[i])
    if elig_reg[i] and rain_imputed[i] and "crops.rainfed_share" not in imp_map:
        imp_map["crops.rainfed_share"] = "state_median"
    n_data_imp = len(imp_map)
    for s_ in KEYS:
        if risk[s_].get("imputed"):
            imp_map[f"risk.{s_}"] = risk[s_]["imputed_from"]
    out[str(int(lgd))] = {
        "main_season": str(main_season[i]), "beta_source": (str(beta_src[i]) if elig_reg[i] else None),
        "beta_used_pct": nn(beta[i], 2) if elig_reg[i] else None,
        "p_elnino": nn(p_s[i], 2), "p_phase": {ph: nn(pk[ph][i], 2) for ph in ("elnino", "neutral", "lanina")},
        "elnino_mean_anomaly_season_pct": nn(a_el[i], 1), "neutral_mean_anomaly_season_pct": nn(a_neu[i], 1),
        "strong_elnino_anomaly_season_pct": nn(a_strong[i], 1), "elnino_deficit_prob_season": nn(P_el[i], 3),
        "lanina_mean_anomaly_season_pct": nn(a_la[i], 1), "lanina_flood_prob_season": nn(P_flood[i], 3),
        "risk": risk, "hindcast": hind, "hindcast_rabi": hind_r, "food_balance": fb, "season_outlook": SEASON_OUTLOOK[i],
        "season_context": {"rabi": {"foodgrain_prod_t": nn(rabi_prod[i], 0), "share_of_foodgrain_prod": nn(rabi_share_prod[i], 3), "prev_kharif_dev_pct": nn(kdev_last[i], 1), "prev_rabi_dev_pct": nn(rdev_last[i], 1), "scored": bool(rabi_elig[i]),
                                    "terminal_heat_year_share_elnino": nn(pd_scn[RP["elnino"]][i], 2)}},
        "data_quality": {"has_crops": bool(has_crops[i]), "has_climate": bool(has_climate[i]),
                         "has_nfhs6": bool(np.isfinite(df0.stunting_nfhs6.iat[i])), "scored": bool(elig[i]),
                         "no_data_reason": (None if elig[i] else ("no_climate" if not has_climate[i] else ("no_crops" if not has_crops[i] else "negligible_agriculture"))),
                         "rabi_scored": bool(rabi_elig[i]), "rabi_no_data_reason": (None if rabi_elig[i] else str(rabi_reason[i])),
                         "rainfed_imputed": (bool(rain_imputed[i] or I_rain[i]) if elig_reg[i] else None),
                         "has_price": bool(np.isfinite(df0.price_volatility_idx.iat[i]) and np.isfinite(df0.price_elnino_spike_pct.iat[i])),
                         "has_groundwater": bool(np.isfinite(df0.gw_stress_idx.iat[i])), "has_poshan": bool(np.isfinite(df0.poshan_underweight_pct.iat[i])),
                         "consumption_side": bool(CONS[i]), "imputed": imp_map, "imputed_count": len(imp_map), "imputed_data_count": n_data_imp,
                         "capacity_terms": int(np.isfinite(np.column_stack([t[1] for t in Z_C])[i]).sum()),
                         "sensitivity_terms": int(np.isfinite(np.column_stack([t[1] for t in Z_S])[i]).sum()),
                         "group_beta_fallback": gfb if elig[i] else []},
    }
save_json(out, ART / "risk_district.json")

BANDC = {s: {b: int((RES[s]["band"][RES[s]["ok"]] == b).sum()) for b in ("high", "medium", "low")} for s in KEYS}
meta = {"as_of": str(pd.Timestamp.today().date()), "band_thresholds": {"low_below": round(t_lo, 2), "high_from": round(t_hi, 2), "reference": KREF},
        "p_elnino": {"JJAS_kharif_2027": P_MJJ27, "OND_2026": P_OND26},
        "p_by_season": {KID: P_K, RID: P_R}, "season_ids": {"kharif": KID, "rabi": RID}, "scenario_keys": KEYS,
        "elnino_years": el_ys, "neutral_years": ne_ys, "lanina_years": la_ys, "strong_elnino_analogs": STRONG_SET,
        "weights": {"top": W_TOP, "v2_effective_term_weight": W_NEW, "v2_terms": ["price_spike_risk (E)", "groundwater_stress (S)", "poshan_underweight_live (C)"]}, "hindcast": HSUM, "hindcast_rabi": HSUM_R, "beta_national_median": round(nat_med, 2),
        "gee_live_used": has_live_ndvi, "n_scored": int(elig.sum()), "n_scored_rabi": int(rabi_elig.sum()), "ond_districts": int(is_ond.sum()),
        "band_counts": BANDC,
        "shock_source_counts": {s: {k: int(v) for k, v in pd.Series(shock_src[s][RES[s]["ok"]]).value_counts().items()} for s in KEYS},
        "ensemble_weights": ENS_W, "ensemble_weights_rabi": ENS_RW,
        "rabi": {"heat_threshold_c": HEAT_THR_C, "eligibility": {"min_rabi_foodgrain_area_ha": 2000, "min_rabi_share_of_foodgrain_area": 0.05, "min_years_with_rabi_area": 3, "area_basis": "median crop years 2018+"},
                 "exposure_terms": {"expected_yield_loss": 0.5, "terminal_heat_risk": 0.3, "weak_kharif_carryover": 0.2},
                 "not_eligible_reasons": {k: int(v) for k, v in pd.Series(rabi_reason[elig & ~rabi_elig]).value_counts().items()}}}
meta["season_outlook_national"] = SO_NATIONAL
meta["imputation"] = {"overlay": USE_IMP, "n_scored_observed": int(elig_ref.sum()), "n_scored_regular": int(elig_reg.sum()), "n_consumption_side": int(CONS.sum()),
                      "n_rabi_scored_observed": int(rabi_elig_ref.sum()), "n_rabi_neighbour_shock": int(rabi_nb.sum()), "rabi_min_share": RABI_MIN_SHARE,
                      "imputed_flag_share": IMP_FLAG_SHARE, "reference": "percentile ranks and band thresholds use observed districts only (elig_ref)",
                      "consumption_side_donors": {str(int(df.lgd.values[i_])): [int(df.lgd.values[j_]) for j_ in DON_K[i_]] for i_ in DON_K}}
save_json(meta, ART / "risk_meta.json")

# ── 10. actions CSVs ─────────────────────────────────────────────────────────
for s in KEYS:
    a = ACT[s]; r = RES[s]; kd = kind_of(s)
    cols_a = ["grain_preposition_t", "pulses_preposition_t", "anganwadi_children", "women_anaemia_target", "seed_bank_ha", "mgnrega_persondays", "pmfby_gap_farmers"]
    t = pd.DataFrame({
        "priority_rank_national": r["rank_nat"], "priority_rank_state": r["rank_state"], "state": df.state.values,
        "district": df.district.values, "lgd": df.lgd.values, "score": np.round(r["score"], 1), "band": r["band"],
        "expected_yield_shock_pct": np.round(shock[s], 1) + 0.0,
        **{k: np.round(a[k], 0) + 0.0 for k in cols_a},
        "fodder_flag": pd.Series(a["fodder_flag"]).map({1.0: True, 0.0: False}),
        **({"protective_irrigation_ha": np.round(a["protective_irrigation_ha"], 0) + 0.0,
            "groundwater_budget_flag": pd.Series(a["groundwater_budget_flag"]).map({1.0: True, 0.0: False})} if kd == "rabi" else {}),
        f"lead_{RID}": LEAD[RID], f"lead_{KID}": LEAD[KID],
        "expected_shock_source": shock_src[s], "season": KID if kd == "kharif" else RID, "phase": phase_of(s)})
    t = t[t.band != "no_data"].sort_values(["score", "lgd"], ascending=[False, True])
    for c in ["priority_rank_national", "priority_rank_state"]:
        t[c] = t[c].astype(int)
    t = t.rename(columns={"mgnrega_persondays": "nrega_persondays"})        # user-facing CSV header says NREGA (JSON key stays mgnrega_persondays)
    t.to_csv(ART / f"actions_{s.replace(':', '_')}.csv", index=False)
    if s in [KP[x] for x in SCEN]:                      # legacy names = copies of the kharif files
        t.to_csv(ART / f"actions_{phase_of(s)}.csv", index=False)
log("wrote risk_district.json, risk_meta.json, actions csvs (", len(KEYS), "scenario files + 3 legacy copies)")

# ── 11. report ───────────────────────────────────────────────────────────────
elig_x, rabi_elig_x = elig.copy(), rabi_elig.copy()          # v5 (extended) populations, used by the v5 section
elig, rabi_elig = elig_ref, rabi_elig_ref                    # the historical v1-v4 sections below describe the observed (pre-v5) population
lines = ["# 04_risk report", "",
         f"Scored districts: **{int(elig_x.sum())} / {N}** ({int(elig_ref.sum())} on observed climate + crop data, {int((elig_x & ~elig_ref).sum())} on imputed data, see the v5 section; "
         f"unscored -> `band = no_data`, score null: {int((~elig_x).sum())}). Observed-data screening (pre-v5): no climate: {int((~has_climate_ref).sum())}; no crops: {int((~has_crops_ref).sum())}; "
         f"all-urban / negligible foodgrain area (rural share < 5 % or < 100 ha foodgrain): {int((no_agri_ref & has_climate_ref).sum())}.", "",
         "## Parameters", "",
         f"- El Nino years used ({len(el_ys)}): {el_ys}; neutral ({len(ne_ys)}): {ne_ys}; strong analogs: {STRONG_ANALOGS}.",
         f"- v4 scenarios (`<season>:<phase>`): phases are PURE (El Nino weight 1; the v3 `elnino` weighted the analog by p(El Nino) = {P_MJJ27:.2f}); `current` = probability-weighted mix of the lanina / neutral / elnino phase shocks, "
         f"p kharif {KID} = El Nino {P_K['elnino']:.2f} / neutral {P_K['neutral']:.2f} / La Nina {P_K['lanina']:.2f}; p rabi {RID} = {P_R['elnino']:.2f} / {P_R['neutral']:.2f} / {P_R['lanina']:.2f} (IRI plume via 08_enso_status.py); "
         f"the {int(is_ond.sum())} OND-main districts use the rabi-season probabilities for their kharif `current` mix (their NE monsoon is this winter), as v3 did.",
         f"- Main rainy season: OND for Tamil Nadu + Puducherry and lgd {sorted(OND_EXTRA_LGD)} (Nellore, Chittoor, Prakasam); JJAS elsewhere. OND anomalies are clipped to +/-100 %.",
         f"- Beta (yield sensitivity). Spec beta = `foodgrain_elnino_pct`; **{'used as the mean of the El Nino-year effect and the rain-deficit-year effect (`foodgrain_deficit_year_pct`)' if BETA_MODE == 'blend' else 'used as-is'}** "
         f"(see 'Investigation log'). Each clipped to {BETA_CLIP}; districts with n < 3 or null take the state median (>= 3 donors) else the national median ({nat_med:.2f} %). "
         f"Sources among scored districts: {pd.Series(beta_src[elig]).value_counts().to_dict()}.",
         "- Shock = clip(beta x f x (0.4 + 0.6 x rainfed_share), -45, +10) with f = max(clip((a_scn - a_neutral) / min(a_elnino - a_neutral, -5), 0, 2), floor x w_el): the share of the district's historical El Nino "
         f"rainfall departure that the scenario realises (w_el = El Nino weight of the scenario: 0 neutral, 1 for the El Nino phases; floor = {G_FLOOR} for JJAS districts, 0 for OND districts). "
         "This replaces the spec's `anomaly_scn / anomaly_elnino_hist`, which explodes or flips sign when the historical El Nino anomaly is near zero or wetter than neutral. "
         "NE-monsoon districts (OND): El Nino enhances rain -> f = 0 -> no shock -> low exposure, as intended. Neutral shock is 0 by construction. Only losses (shock < 0) raise exposure.",
         "- Percentile normalisation: every scenario's exposure terms are normalised against the **elnino** scenario's distribution (not re-ranked per scenario), so neutral/strong scores genuinely move "
         "relative to the fixed band thresholds. S and C terms are rank-normalised over scored districts; missing terms are reweighted per district.",
         f"- Bands from tertiles of elnino scores: low < **{t_lo:.1f}**, medium {t_lo:.1f}-{t_hi:.1f}, high >= **{t_hi:.1f}**, applied to all scenarios.",
         "- **v3 override**: the analog shock above is computed, then replaced per district/scenario by the ML ensemble shock (`shock_ensemble_pct`, artifacts/ml_ensemble.parquet) where present; "
         "tables below from 'Expected foodgrain yield shock' onward use the ensemble. See the 'v3 - ensemble' section at the end.",
         f"- Live NDVI term {'**used**' if has_live_ndvi else 'not used (artifacts/gee_live.json absent or empty)'}.", ""]
lines += ["## Score distribution by scenario", "", "| scenario | mean | sd | min | p10 | p25 | median | p75 | p90 | max | high | medium | low |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for s in SCEN:
    x = RES[s]["score"][elig]; q = np.quantile(x, [0, .1, .25, .5, .75, .9, 1]); b = pd.Series(RES[s]["band"][elig]).value_counts()
    lines.append(f"| {s} | {x.mean():.1f} | {x.std():.1f} | {q[0]:.1f} | {q[1]:.1f} | {q[2]:.1f} | {q[3]:.1f} | {q[4]:.1f} | {q[5]:.1f} | {q[6]:.1f} | {b.get('high', 0)} | {b.get('medium', 0)} | {b.get('low', 0)} |")
lines += ["", "Expected foodgrain yield shock (%), scored districts:", "", "| scenario | mean | median | p10 | min | share of districts with loss > 5 % |", "|---|---|---|---|---|---|"]
for s in SCEN:
    x = shock[s][elig]
    lines.append(f"| {s} | {x.mean():.1f} | {np.median(x):.1f} | {np.quantile(x, .1):.1f} | {x.min():.1f} | {(x < -5).mean():.0%} |")

dfo = df[["lgd", "district", "state"]].copy()
dfo["score"] = RES["elnino"]["score"]; dfo["rank"] = RES["elnino"]["rank_nat"]; dfo["band"] = RES["elnino"]["band"]
top = dfo[elig].sort_values("rank").head(25)
lines += ["", "## Top 25 districts, `elnino` scenario", "", "| # | district | state | score | shock % | season | top 3 drivers |", "|---|---|---|---|---|---|---|"]
for _, r in top.iterrows():
    i = int(np.where(df.lgd.values == r.lgd)[0][0]); d3 = "; ".join(x["label"] for x in out[str(r.lgd)]["risk"]["elnino"]["drivers"][:3])
    lines.append(f"| {int(r['rank'])} | {r.district} | {r.state} | {r.score:.1f} | {shock['elnino'][i]:.1f} | {main_season[i]} | {d3} |")

st = dfo[elig].groupby("state").score.agg(["count", "mean"]).query("count >= 5").sort_values("mean", ascending=False).head(10)
lines += ["", "State mean elnino score (>= 5 scored districts), top 10:", "", "| state | districts | mean score |", "|---|---|---|"]
lines += [f"| {k} | {int(v['count'])} | {v['mean']:.1f} |" for k, v in st.iterrows()]

lines += ["", "## Hindcast (does the model's ranking line up with what actually happened?)", "",
          "Method: the *actual* main-season rainfall anomaly of year Y is the 'forecast' (same shock formula; El Nino/neutral deficit probability by that year's ENSO phase; antecedent = anomaly of Y-1). "
          "Sensitivity (beta, S) and capacity (C) are today's values, so this is **not** a clean out-of-sample test (beta is fitted on all years including Y; NFHS-6 is later than Y). "
          "Actual = % deviation of foodgrain yield from a Theil-Sen linear trend fitted on the 10 years before Y (>= 6 obs), clipped +/-100 %. "
          "A good model has **negative** rho (high predicted risk -> negative deviation). `rho_dryness` is the baseline using raw dryness (-anomaly) alone.", "",
          "| year | ENSO | all-India anomaly % | n | rho (score) | rho (exposure only) | rho (dryness only) | top-tercile mean dev % | bottom-tercile mean dev % | gap (top - bottom) |", "|---|---|---|---|---|---|---|---|---|---|"]
for y, v in HSUM.items():
    lines.append(f"| {y} | {v['phase']} | {v['mean_all_india_anomaly_pct']} | {v['n']} | {v['spearman_rho']} | {v['rho_exposure_only']} | {v['rho_dryness_only']} | {v['top_tercile_mean_dev_pct']} | {v['bottom_tercile_mean_dev_pct']} | {v['top_minus_bottom_pct']} |")

REGIONS = {
    "Marathwada (Beed spelled 'Bid')": [470, 481, 488, 479],
    "Vidarbha": [500, 468, 467],
    "Bundelkhand": [153, 161, 398, 434],
    "Rayalaseema": [502, 511],
    "KBK Odisha": [358, 345, 363],
    "South Rajasthan": [88, 99, 117],
}
nsc = int(elig.sum())
lines += ["", f"## Regional sanity check (elnino rank out of {nsc}; 1 = highest risk)", "",
          "| region | district | rank | percentile | score | band | shock % | beta | beta src | main driver |", "|---|---|---|---|---|---|---|---|---|---|"]
reg_pct = {}
for reg, ls in REGIONS.items():
    ps = []
    for l in ls:
        i = int(np.where(df.lgd.values == l)[0][0])
        if not elig[i]:
            lines.append(f"| {reg} | {df.district.iat[i]} | n/a | n/a | n/a | no_data | | | | |"); continue
        rk = RES["elnino"]["rank_nat"][i]; pct = 1 - (rk - 1) / nsc; ps.append(pct)
        d1 = out[str(l)]["risk"]["elnino"]["drivers"][0]["label"] if out[str(l)]["risk"]["elnino"]["drivers"] else ""
        lines.append(f"| {reg} | {df.district.iat[i]} | {int(rk)} | {pct:.0%} | {RES['elnino']['score'][i]:.1f} | {RES['elnino']['band'][i]} | {shock['elnino'][i]:.1f} | {beta[i]:.1f} | {beta_src[i]} | {d1} |")
    reg_pct[reg] = float(np.mean(ps)) if ps else None
lines += ["", "Regional mean percentile (100 % = riskiest): " + "; ".join(f"{k}: {v:.0%}" for k, v in reg_pct.items() if v is not None), ""]
lines += ["## Investigation log (data checked before any weight change; component weights 0.45/0.30/0.25 and term weights are UNCHANGED from the spec)", "",
          "1. First run (spec beta = El Nino-year effect only, no floor): Beed ('Bid', lgd 470) ranked ~596/726 and Banswara/Koraput were mid-table with shock 0. "
          "Data check: Beed's El Nino-year effect is **+4.7 %** because 2006 and 2018 (ONI El Nino years that were *not* monsoon-deficit years; yields 0.83 and 0.34 t/ha) offset the real droughts, "
          "while its rain-deficit-year effect (2002, 2004, 2009, 2012, 2014, 2015, 2023) is **-18.3 %**. Latur: -31.9 / -21.6. Jhansi: +1.0 / -8.0. Koraput and Banswara have El Nino-year JJAS rainfall *wetter* than neutral in this 7-year IMD sample (+2.0 vs -1.9; +2.4 vs +0.7) "
          "so a pure rainfall-gated shock is 0 even though yields fall in El Nino years. Both are small-sample (n = 7) artefacts, not weights. "
          "**Fix = estimator change, not weight change:** beta = mean(El Nino effect, deficit-year effect), and a JJAS floor of 0.5 on the realised share of the El Nino effect.",
          "2. Top-5 included Mumbai (rank 3), Mumbai Suburban (65), Hyderabad (99): their latest 'crop' rows are 3 ha / 100 ha / 37 ha (1997-98, 2016-17, 1999-00). Districts with rural share < 5 % or < 100 ha foodgrain are now `no_data` (reason `negligible_agriculture`).",
          "3. Alternatives tried (regional mean percentile, 100 % = riskiest; Marathwada / Vidarbha / Bundelkhand / Rayalaseema / KBK / S.Rajasthan): spec beta, no floor 64/58/45/83/74/74; spec beta, floor 0.5 62/51/43/82/81/84; blend, no floor 80/71/48/80/75/73; "
          "**blend, floor 0.5 (chosen) 79/69/46/78/87/82**. Hindcast rho improved or held in all four years in the chosen setting (spec-only: -0.25, +0.02, -0.50, -0.17). These comparisons pre-date the live-NDVI term (gee_live.json arrived later); the final percentile line below includes it and is the one to quote.",
          "4. Bundelkhand remains mid-table: Jhansi and Lalitpur are canal-irrigated (Jhansi irrigated share 59 %, yields rising 1.2 -> 2.2 t/ha) with small El Nino/deficit effects (+1.0 / -8.0 %); the data do not support a high exposure there. Reported as a genuine divergence from the prior, not tuned away.", ""]
lines += ["## Caveats", "",
          "- Shocks use historical El Nino-minus-neutral yield deviations (analogs, not causal); irrigated districts show weak signals; beta is clipped and sometimes imputed (see `beta_source`).",
          "- 'Exposure' for OND-main districts uses NE-monsoon rainfall; El Nino typically enhances it, so they score low on exposure. Their Kharif (JJAS) risk is not modelled separately.",
          "- Hindcast is an in-sample sanity check, not skill validation.",
          "- pmfby_gap_farmers: cultivators_est = pop_2026 x worker_participation x cultivator share of workers (Census 2011 ratios); PMFBY farmer_count is farmer-seasons so is halved to approximate unique farmers. Indicative only.",
          "- women_anaemia_target uses NFHS-5 (NFHS-6 district fact sheets carry no anaemia); anganwadi_children uses NFHS-6 stunting else NFHS-5.",
          "- fodder_flag = band high and (millets + cash-crop area) / gross cropped area > 0.3.",
          "- Actions zero (not null) when not triggered by band (seed bank: low band; NREGA: not high); null when inputs are missing.",
          "- UPAG-sourced latest years cover major crops only; gross_cropped_area_ha (and thus seed_bank_ha) is a lower bound there. Split-parent districts have overstated population.",
          f"- Consistency check vs climate parquet (JJAS districts): max |El Nino mean anomaly diff| {chk_el:.2f} pp, max |deficit prob diff| {chk_p:.3f}.", ""]
# ── 12. v2 section: before / after the extra sources ─────────────────────────
if BASELINE.exists():
    B1 = json.load(open(BASELINE)); bd = B1["districts"]
    v1 = pd.Series({int(l): (v["elnino"]["score"] if v["elnino"]["score"] is not None else np.nan) for l, v in bd.items()})
    v1 = v1.reindex(df.lgd.values)
    v2 = pd.Series(RES["elnino"]["score"], index=df.lgd.values)
    ok = v1.notna() & v2.notna()
    r1 = v1[ok].rank(ascending=False, method="first"); r2 = v2[ok].rank(ascending=False, method="first")
    n2 = int(ok.sum())
    rho_12 = float(np.corrcoef(v1[ok].rank(), v2[ok].rank())[0, 1])
    cov = {"price_spike_risk (E)": int(np.isfinite(z_price[elig]).sum()), "groundwater_stress (S)": int(np.isfinite(zrank(gw_stress)[elig]).sum()),
           "poshan_underweight_live (C)": int(np.isfinite(zrank(pw_uw)[elig]).sum())}
    L = ["", "---", "", "## v2 — extra sources (price spike, groundwater, Poshan live)", "",
         "Inputs: `artifacts/extra_district.parquet` (ICRISAT farm-harvest prices, CGWB/state-board groundwater, Poshan Tracker). Component weights 0.45/0.30/0.25 and all earlier term definitions, "
         "the beta estimator, the JJAS floor and the live-NDVI handling are UNCHANGED. Bands are re-derived from the new elnino tertiles; hindcast is recomputed with the new terms.", "",
         "### New terms", "",
         f"- **price_spike_risk** (exposure): rank-normalise(0.5 x clip(price_elnino_spike_pct, 0, +40)/40 + 0.5 x price_volatility_idx), needs both inputs. Effective weight {W_NEW:.2f} inside exposure; "
         f"the existing terms (incl. live NDVI) are scaled by {1 - W_NEW:.2f} (raw weight {PRICE_W_RAW:.4f} against raw sum {PRICE_W_RAW * (1 - W_NEW) / W_NEW:.2f}). Same value in every scenario (like S and C).",
         f"- **groundwater_stress** (sensitivity): `gw_stress_idx` (0-1 rank of depth + 10-yr deepening), effective weight {W_NEW:.2f}; other S terms scaled by {1 - W_NEW:.2f}.",
         f"- **poshan_underweight_live** (capacity deficit): rank-normalised `poshan_underweight_pct` (Poshan Tracker, latest month), effective weight {W_NEW:.2f}; other C terms scaled by {1 - W_NEW:.2f}. "
         "Poshan reads ~18 pp lower than NFHS-6 on average (administrative, integer-rounded) but ranks correlate (Spearman 0.61); only the rank enters the score.",
         "- Missing term -> dropped and the rest of that component reweighted (never imputed as 0). Coverage among scored districts: " + "; ".join(f"{k} {v}/{int(elig.sum())}" for k, v in cov.items()) + ".",
         "- **Honest note on prices.** In this data the El Nino-year farm-harvest price effect is *negative on the median* (median spike -4.3 pp, 75th percentile +0.8 pp; farm-gate prices were below their log-linear trend in El Nino years, "
         "i.e. no widespread price spike). Only positive spikes count (clip at 0), so roughly three quarters of districts get zero from the spike half and the term is driven mostly by price volatility. "
         "It is a market-instability proxy for farm-gate price shocks, not a food-price inflation forecast, and it uses the district's main foodgrain only (ICRISAT ends 2020; 511/753 districts have a price series).", "",
         "### Bands and score distribution", "",
         f"- Thresholds (elnino tertiles): v1 low < {B1['meta']['band_thresholds']['low_below']}, high >= {B1['meta']['band_thresholds']['high_from']}  ->  v2 low < **{t_lo:.1f}**, high >= **{t_hi:.1f}**.",
         "- Band counts (scored districts), v1 -> v2: " + "; ".join(
             f"{sc}: " + "/".join(str(sum(1 for l, v in bd.items() if v[sc]["band"] == b)) for b in ["high", "medium", "low"]) + " -> " +
             "/".join(str(int((RES[sc]['band'][elig] == b).sum())) for b in ["high", "medium", "low"]) + " (high/medium/low)" for sc in SCEN) + ".",
         f"- Spearman correlation of elnino scores v1 vs v2: **{rho_12:.3f}** (n = {n2}).",
         "- Band moves elnino, v1 -> v2 (rows v1): " + "; ".join(
             f"{b1}: " + ", ".join(f"{int(sum(1 for l in df.lgd.values[elig] if bd[str(l)]['elnino']['band'] == b1 and RES['elnino']['band'][np.where(df.lgd.values == l)[0][0]] == b2))} {b2}" for b2 in ["high", "medium", "low"])
             for b1 in ["high", "medium", "low"]) + ".", "",
         "### Hindcast rho (score vs actual yield deviation; more negative is better), v1 -> v2", "",
         "| year | rho v1 | rho v2 | rho exposure-only v1 | v2 | top-bottom tercile gap v1 | v2 |", "|---|---|---|---|---|---|---|"]
    for y, v in HSUM.items():
        o = B1["meta"]["hindcast"][y]
        L.append(f"| {y} | {o['spearman_rho']} | {v['spearman_rho']} | {o['rho_exposure_only']} | {v['rho_exposure_only']} | {o['top_minus_bottom_pct']} | {v['top_minus_bottom_pct']} |")
    L += ["", "Caveat: the new terms are contemporary snapshots (prices fitted on 1990-2020 El Nino years that include 2009/2015; groundwater mostly 2019; Poshan 2023-26), "
          "so the hindcast is even less out-of-sample than before.", ""]
    # top 25 before/after
    top1 = set(r1[r1 <= 25].index); top2 = set(r2[r2 <= 25].index)
    nm = dict(zip(df.lgd.values, df.district.values)); stt = dict(zip(df.lgd.values, df.state.values))
    L += [f"### Top 25 (elnino), before vs after — {len(top1 & top2)} of 25 unchanged", "",
          "| v2 # | district | state | v2 score | v1 rank | v1 score | new-term contribution (pts) |", "|---|---|---|---|---|---|---|"]
    def new_contrib(i):
        r = RES["elnino"]; wE = r["eff"][i][0]; wS = r["eff"][i][1]; wC = r["eff"][i][2]
        k = r["E_names"].index("price_spike_risk")
        return 100 * (wE * r["E_eff"][i, k] * r["E_z"][i, k] + wS * S_eff[i, -1] * S_z[i, -1] + wC * C_eff[i, -1] * C_z[i, -1])
    for l in r2.sort_values().index[:25]:
        i = int(np.where(df.lgd.values == l)[0][0])
        L.append(f"| {int(r2[l])} | {nm[l]} | {stt[l]} | {v2[l]:.1f} | {int(r1[l])} | {v1[l]:.1f} | {new_contrib(i):.1f} |")
    L += ["", "Dropped out of the v1 top 25: " + (", ".join(f"{nm[l]} ({stt[l]}, v1 #{int(r1[l])} -> v2 #{int(r2[l])})" for l in sorted(top1 - top2, key=lambda x: r1[x])) or "none") + ".", "",
          "Biggest rank movers (elnino, v1 -> v2):", ""]
    dr = (r1 - r2)   # + = moved up the risk ranking
    for lab, idx in (("up", dr.sort_values(ascending=False).index[:8]), ("down", dr.sort_values().index[:8])):
        L.append(f"- {lab}: " + "; ".join(f"{nm[l]} ({stt[l]}) #{int(r1[l])} -> #{int(r2[l])}" for l in idx))
    L += ["", f"Median absolute rank change: {float((r1 - r2).abs().median()):.0f}; 90th percentile: {float((r1 - r2).abs().quantile(0.9)):.0f} (of {n2}).", ""]
    # regional percentile before/after
    L += ["### Regional mean percentile (elnino, 100 % = riskiest), v1 -> v2", "",
          "| region | v1 | v2 | mean new-term contribution (pts) | all-district mean (pts) | drivers of the move |", "|---|---|---|---|---|---|"]
    allc = float(np.mean([new_contrib(int(i)) for i in np.where(elig)[0]]))
    for reg, ls in REGIONS.items():
        ii = [int(np.where(df.lgd.values == l)[0][0]) for l in ls if elig[int(np.where(df.lgd.values == l)[0][0])]]
        p1 = np.mean([1 - (r1[df.lgd.values[i]] - 1) / n2 for i in ii]); p2 = np.mean([1 - (r2[df.lgd.values[i]] - 1) / n2 for i in ii])
        pz = lambda z_: float(np.nanmean([z_[i] for i in ii]))
        L.append(f"| {reg} | {p1:.0%} | {p2:.0%} | {np.mean([new_contrib(i) for i in ii]):.1f} | {allc:.1f} | "
                 f"mean rank-z: price {pz(z_price):.2f}, groundwater {pz(Z_S[-1][1]):.2f}, poshan {pz(Z_C[-1][1]):.2f} (0.5 = average) |")
    L += ["", "### State-level shift (elnino score, mean v2 - v1, states with >= 5 scored districts)", "",
          "| state | n | mean score change | median Poshan underweight % | mean Poshan rank-z | price coverage | groundwater coverage |", "|---|---|---|---|---|---|---|"]
    sdf = pd.DataFrame({"state": df.state.values, "d": (v2 - v1).values, "pw": pw_uw, "zc": Z_C[-1][1], "zp": z_price, "zg": Z_S[-1][1]})[elig]
    sg = sdf.groupby("state").agg(n=("d", "count"), d=("d", "mean"), pw=("pw", "median"), zc=("zc", "mean"),
                                  pc=("zp", lambda x: x.notna().mean()), gc=("zg", lambda x: x.notna().mean())).query("n >= 5").sort_values("d")
    for st_, r_ in pd.concat([sg.head(5), sg.tail(5)]).iterrows():
        L.append(f"| {st_} | {int(r_.n)} | {r_.d:+.1f} | {r_.pw:.0f} | {r_.zc:.2f} | {r_.pc:.0%} | {r_.gc:.0%} |")
    L += ["", "Reading the swings: the largest negative shift is Andhra Pradesh (most new AP districts - Annamayya, Sri Sathya Sai, Palnadu, Konaseema, Bapatla, Eluru, Kakinada - drop 100-300 ranks). "
          "The cause is the Poshan term, not a change in climate or crop exposure: AP districts report very low underweight on Poshan Tracker (median 4 % vs ~10 % nationally; NFHS-6 shows ~30 %), "
          "so their rank-z on this term is near the bottom and the capacity deficit falls; the split districts also have no price or groundwater series (name match only), so nothing offsets it. "
          "This is partly a state reporting-practice effect (Poshan is administrative and integer-rounded), i.e. a bias, not necessarily better nutrition. Not tuned away; if it matters for allocation, "
          "consider a within-state rank or an NFHS-calibrated adjustment for the Poshan term in a later version. As of this run, regions in the sanity check moved by <= 6 points of percentile (Vidarbha +6, Marathwada +3, "
          "Rayalaseema +2, Bundelkhand/KBK/South Rajasthan -1 to 0); none lost its prior ordering: Bundelkhand stays mid-table because its price term is low (rank-z 0.11) and its irrigated profile is unchanged.", ""]
    lines += L

# ── 13. v3 section: analog-only shock -> ML ensemble shock ───────────────────
if BASELINE2.exists():
    B2 = json.load(open(BASELINE2)); b2 = B2["districts"]
    u2 = pd.Series({int(l): (v["elnino"]["score"] if v["elnino"]["score"] is not None else np.nan) for l, v in b2.items()}).reindex(df.lgd.values)
    u3 = pd.Series(RES["elnino"]["score"], index=df.lgd.values)
    ok3 = u2.notna() & u3.notna(); n3 = int(ok3.sum())
    q2 = u2[ok3].rank(ascending=False, method="first"); q3 = u3[ok3].rank(ascending=False, method="first")
    nm = dict(zip(df.lgd.values, df.district.values)); stt = dict(zip(df.lgd.values, df.state.values)); li_ = {int(l): i for i, l in enumerate(df.lgd.values)}
    rho_23 = float(np.corrcoef(u2[ok3].rank(), u3[ok3].rank())[0, 1])
    wprod = np.where(elig, np.nan_to_num(prod, nan=0.0), 0.0)
    def wmean(x_):
        m_ = np.isfinite(x_) & (wprod > 0)
        return float((x_[m_] * wprod[m_]).sum() / wprod[m_].sum())
    L = ["", "---", "", "## v3 - ensemble (analog + LightGBM expected yield shock)", "",
         "Inputs: `artifacts/ml_ensemble.parquet` (04b: lgd x scenario predictions of the foodgrain yield deviation, `shock_analog_pct`, `shock_lgbm_pct`, `shock_ensemble_pct`, `spread_pct`) and "
         "`artifacts/_ml_loyo_preds.parquet` (leave-one-year-out predictions for the hindcast). `expected_yield_shock_pct` of every scenario is now the **ensemble** shock "
         f"(weights analog {ENS_W['analog']:.2f} / LightGBM {ENS_W['lgbm']:.2f}, inverse pooled out-of-sample MAE; TabFM not available) for "
         + ", ".join(f"{pd.Series(shock_src[sc][elig]).eq('ensemble').sum()}/{int(elig.sum())} ({sc})" for sc in SCEN) +
         " scored districts; the rest fall back to the analog formula. The analog value is kept as `expected_yield_shock_analog_pct`. "
         "Exposure percentiles are re-referenced to the new elnino shock distribution; component weights, S and C terms, the live-NDVI term and the in-sample hindcast formula are UNCHANGED; "
         "group shocks keep the analog group/foodgrain beta ratios (ratio 1 when |beta| < 2 pp, clipped +/-3) scaled to the new foodgrain shock.", "",
         "### Expected yield shock (%), scored districts (v2 analog -> v3 ensemble)", "",
         "| scenario | mean v2 | mean v3 | production-weighted national v2 | v3 | median v3 | share with loss > 5 % v2 -> v3 | mean analog-LightGBM spread (pp) |", "|---|---|---|---|---|---|---|---|"]
    for sc in SCEN:
        x3_ = shock[sc]; x2_ = shock_analog[sc]; sp_ = np.array([ens_info[sc].get(i, {}).get("spread", np.nan) for i in range(N)])
        L.append(f"| {sc} | {np.nanmean(x2_[elig]):.2f} | {np.nanmean(x3_[elig]):.2f} | {wmean(x2_):.2f} | {wmean(x3_):.2f} | {np.nanmedian(x3_[elig]):.2f} | "
                 f"{(x2_[elig] < -5).mean():.0%} -> {(x3_[elig] < -5).mean():.0%} | {np.nanmean(sp_[elig]):.1f} |")
    L += ["", "Note: the neutral scenario is no longer exactly zero (LightGBM carries district-level structure such as the previous-year deviation and state effects; analog neutral stays 0 by construction).", "",
          "### Bands and score distribution", "",
          f"- Thresholds (elnino tertiles): v2 low < {B2['meta']['band_thresholds']['low_below']}, high >= {B2['meta']['band_thresholds']['high_from']}  ->  v3 low < **{t_lo:.1f}**, high >= **{t_hi:.1f}**.",
          "- Band counts (scored districts), v2 -> v3 (high/medium/low): " + "; ".join(
              f"{sc}: " + "/".join(str(sum(1 for l, v in b2.items() if v[sc]["band"] == b)) for b in ["high", "medium", "low"]) + " -> " +
              "/".join(str(int((RES[sc]['band'][elig] == b).sum())) for b in ["high", "medium", "low"]) for sc in SCEN) + ".",
          f"- Spearman correlation of elnino scores v2 vs v3: **{rho_23:.3f}** (n = {n3}).",
          "- Band moves elnino, v2 -> v3 (rows v2): " + "; ".join(
              f"{b1}: " + ", ".join(f"{int(sum(1 for l in df.lgd.values[elig] if b2[str(l)]['elnino']['band'] == b1 and RES['elnino']['band'][li_[int(l)]] == b2_))} {b2_}" for b2_ in ["high", "medium", "low"])
              for b1 in ["high", "medium", "low"]) + ".", ""]
    t2_ = set(q2[q2 <= 25].index); t3_ = set(q3[q3 <= 25].index)
    L += [f"### Top 25 (elnino), v2 -> v3 - {len(t2_ & t3_)} of 25 unchanged", "",
          "| v3 # | district | state | v3 score | v2 rank | v2 score | shock v3 % (analog / LightGBM) |", "|---|---|---|---|---|---|---|"]
    for l in q3.sort_values().index[:25]:
        i = li_[int(l)]; e = ens_info["elnino"].get(i)
        sh_ = f"{shock['elnino'][i]:.1f} ({e['analog']:.1f} / {e['lgbm']:.1f})" if e else f"{shock['elnino'][i]:.1f} (analog only)"
        L.append(f"| {int(q3[l])} | {nm[l]} | {stt[l]} | {u3[l]:.1f} | {int(q2[l])} | {u2[l]:.1f} | {sh_} |")
    L += ["", "Dropped out of the v2 top 25: " + (", ".join(f"{nm[l]} ({stt[l]}, v2 #{int(q2[l])} -> v3 #{int(q3[l])})" for l in sorted(t2_ - t3_, key=lambda x: q2[x])) or "none") + ".", "",
          "Biggest rank movers (elnino, v2 -> v3):", ""]
    dr3 = (q2 - q3)
    for lab, idx in (("up", dr3.sort_values(ascending=False).index[:8]), ("down", dr3.sort_values().index[:8])):
        L.append(f"- {lab}: " + "; ".join(f"{nm[l]} ({stt[l]}) #{int(q2[l])} -> #{int(q3[l])}" for l in idx))
    L += ["", f"Median absolute rank change: {float(dr3.abs().median()):.0f}; 90th percentile: {float(dr3.abs().quantile(0.9)):.0f} (of {n3}).", "",
          "### Regional mean percentile (elnino, 100 % = riskiest), v2 -> v3", "",
          "| region | v2 | v3 | mean shock v2 analog % | mean shock v3 ensemble % |", "|---|---|---|---|---|"]
    for reg, ls in REGIONS.items():
        ii = [li_[l] for l in ls if elig[li_[l]]]
        p2_ = np.mean([1 - (q2[df.lgd.values[i]] - 1) / n3 for i in ii]); p3_ = np.mean([1 - (q3[df.lgd.values[i]] - 1) / n3 for i in ii])
        L.append(f"| {reg} | {p2_:.0%} | {p3_:.0%} | {np.mean([shock_analog['elnino'][i] for i in ii]):.1f} | {np.mean([shock['elnino'][i] for i in ii]):.1f} |")
    st3 = pd.DataFrame({"state": df.state.values, "d": (u3 - u2).values})[elig].groupby("state").d.agg(["count", "mean"]).query("count >= 5").sort_values("mean")
    L += ["", "State-level shift (elnino score, mean v3 - v2, states with >= 5 scored districts): largest falls " +
          "; ".join(f"{k} {v['mean']:+.1f}" for k, v in st3.head(4).iterrows()) + "; largest rises " + "; ".join(f"{k} {v['mean']:+.1f}" for k, v in st3.tail(4).iloc[::-1].iterrows()) + ".", ""]
    if ML_META is not None:
        L += ["### Hindcast: in-sample score vs out-of-sample shock models", "",
              "Two different tests share these four years. **In-sample (04_risk)**: the risk *score* built from the *actual* rainfall anomaly of year Y with betas fitted on all years incl. Y "
              "-> rho = Spearman(score, actual deviation), **negative = good**. **Out-of-sample (04b leave-one-year-out)**: models that never saw year Y predict the foodgrain yield deviation "
              "-> rho = Spearman(predicted shock, actual deviation), **positive = good**; gap = mean actual deviation of the worst-predicted tercile minus the best-predicted tercile, **negative = good**. "
              "Not a forecasting backtest (training includes future years). Pooled over all 22 held-out years: LightGBM rho {:.3f} / MAE {:.2f} pp, analog rho {:.3f} / MAE {:.2f} pp, ensemble rho {:.3f} / MAE {:.2f} pp, predict-0 MAE {:.2f} pp.".format(
                  ML_META["pooled"]["lgbm"]["rho"], ML_META["pooled"]["lgbm"]["mae"], ML_META["pooled"]["analog"]["rho"], ML_META["pooled"]["analog"]["mae"],
                  ML_META["pooled"]["ensemble"]["rho"], ML_META["pooled"]["ensemble"]["mae"], ML_META["pooled"]["zero_baseline_mae"]), "",
              "| year | ENSO | in-sample score rho v2 | v3 | in-sample gap v2 | v3 | OOS rho analog | OOS rho LightGBM | OOS rho ensemble | OOS gap analog | OOS gap LightGBM | OOS gap ensemble |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for y, v in HSUM.items():
            o = B2["meta"]["hindcast"][y]
            L.append(f"| {y} | {v['phase']} | {o['spearman_rho']} | {v['spearman_rho']} | {o['top_minus_bottom_pct']} | {v['top_minus_bottom_pct']} | {v['rho_analog_oos']} | {v['rho_lgbm_oos']} | "
                     f"{v['rho_ensemble_oos']} | {v['gap_analog_oos']} | {v['gap_lgbm_oos']} | {v['gap_ensemble_oos']} |")
        L += [""]
    L += ["### Caveats (v3)", "",
          "- LightGBM beats the analog out of sample (pooled rho 0.31 vs 0.08) but its skill comes largely from `prev_year_ydev` (persistence of the deviation), state effects and ONI; "
          "the scenario predictions hold the previous-year deviation at the actual 2024 value, so the three scenarios differ only through rainfall/heat/ONI features.",
          "- LightGBM scenario predictions are not rank-identical to the analog (Spearman 0.60 elnino); the ensemble is the compromise, weights from pooled MAE, not tuned per district. Spread = max - min of members; large spread = low confidence.",
          "- Out-of-sample rho is a ranking skill for the *foodgrain yield deviation*; it does not validate the 0-100 risk score, which also contains sensitivity and capacity terms.",
          "- TimesFM rainfall/Poshan forecasts are display-only and do not enter the score (no district-level skill, hindcast rho ~0).", ""]
    lines += L

# ── 14. v4 section: seasons (rabi + kharif La Nina + current outlook) ───────────────────────────────────────────────
nm_ = dict(zip(df.lgd.values, df.district.values)); st_ = dict(zip(df.lgd.values, df.state.values)); li4 = {int(l): i for i, l in enumerate(df.lgd.values)}
KR = RP["elnino"]
L = ["", "---", "", "## v4 — seasons (every year, every season: rabi + kharif, five scenarios each)", "",
     f"Outlook as of {pd.Timestamp.today().date()}: seasons **{RID}** (sowing now) and **{KID}**; ENSO phase probabilities (IRI plume via `08_enso_status.py`): "
     f"{RID} El Nino {P_R['elnino']:.2f} / neutral {P_R['neutral']:.2f} / La Nina {P_R['lanina']:.2f}; {KID} {P_K['elnino']:.2f} / {P_K['neutral']:.2f} / {P_K['lanina']:.2f}.", "",
     "### What changed", "",
     f"- **Scenario keys** `<season>:<phase>` for phase in lanina, neutral, elnino, elnino_strong, current (10 keys). The old keys `neutral | elnino | elnino_strong` are aliases of `{KID}:*` (same objects in `risk_district.json` / `districts.json`).",
     f"- **Phases are pure.** v3's `elnino` weighted the analog member by p(El Nino) = {P_MJJ27:.2f} (while LightGBM was already pure El Nino); the analog is now computed for the pure phase in 04b (El Nino weight 1) and the probability weighting lives only in `current`. "
     "Consequence (measured at the v3 -> v4 switch): kharif `elnino` analog shocks are larger (mean -4.48 % vs -2.75 %) and so is the ensemble (-5.52 % vs -4.70 %); `neutral` and `elnino_strong` are numerically unchanged (LightGBM members are bit-identical). Hindcast formula unchanged (its exposure percentiles are re-referenced to the new elnino distribution, so rho moved by <= 0.011).",
     f"- **`current`** = probability-weighted mix of the lanina / neutral / elnino phase **shocks** (`p_by_season`), then scored (not a mix of scores). Rabi `current` equals rabi `elnino` while p(El Nino) = 1.00 (the very-strong event is only represented in `elnino_strong`, a stress test of the 2002/2009/2015 analogs).",
     f"- **Kharif La Nina = flood scenario** (Addendum F): shock = beta of La Nina years (foodgrain deviation, La Nina-year minus neutral-year mean, clipped, imputed) only where the district's La Nina-year main-season rain anomaly is > +{FLOOD_THR:.0f} % **and** beta < 0; otherwise benign (0). Ensemble gated the same way (04b). "
     f"Flood-flagged districts: **{int(sum(1 for i in ens_info[KP['lanina']] if ens_info[KP['lanina']][i].get('flood')))}**. The hazard term is the share of La Nina years with > +{FLOOD_THR:.0f} % rain (`rain_excess_risk`, flood-flagged districts only, 0 elsewhere), referenced to the El Nino deficit-probability distribution so the two hazards are on one scale.",
     f"- **Rabi** ({RID}; crop year Y = rabi sown Oct Y, harvested Mar Y+1): shock from `ml_ensemble_rabi.parquet` (04b --season rabi; analog phase-beta + LightGBM, weights analog {ENS_RW['analog']:.2f} / LightGBM {ENS_RW['lgbm']:.2f}). Exposure = 0.5 x expected rabi yield loss (percentile vs the rabi El Nino distribution; zero loss -> 0) + 0.3 x terminal-heat hazard "
     f"(share of the phase's winters with Feb-Mar tmax anomaly >= +{HEAT_THR_C} C; percentile vs rabi El Nino) + 0.2 x weak previous kharif (rank of -(2024 kharif deviation), the latest observed; the unobserved 2026 kharif is not available) [+ live NDVI, price term as kharif]. "
     "OND rainfall anomaly is a LightGBM feature (residual soil moisture) but not a separate exposure term: OND % anomalies are unstable where normals are tiny (e.g. Nandurbar: most years below -80 %). Groundwater stress sits in the shared sensitivity component. S and C are shared with kharif.",
     f"- **Eligibility**: rabi score only where rabi foodgrain area >= 2,000 ha in >= 3 of the years 2018-2024, median >= 2,000 ha and >= 5 % of foodgrain area: **{int(rabi_elig.sum())} of {int(elig.sum())}** scored districts; "
     f"{', '.join(f'{k}: {v}' for k, v in pd.Series(rabi_reason[elig & ~rabi_elig]).value_counts().items())} are `no_data` for rabi (`rabi_season_label_gap` = Odisha, Kerala, Dadra-Nagar Haveli: the APY/UPAG season labels carry no Rabi rows in most years).",
     f"- **Bands**: the same thresholds for every season and scenario = tertiles of `{KREF}` (low < {t_lo:.1f}, high >= {t_hi:.1f}); exposure percentiles use each season's own El Nino distribution as reference, so rabi El Nino exposure is spread like kharif El Nino exposure and the seasons are comparable as *relative* vulnerability, not as absolute tonnes lost (rabi shocks are milder: mean rabi El Nino ensemble shock {np.nanmean(shock[KR][rabi_elig]):.2f} % vs kharif {np.nanmean(shock[KREF][elig]):.2f} %).",
     "- **Rabi LightGBM shocks are relative to the district's own neutral-winter prediction** (04b): the raw prediction is a deviation from a lagged trailing trend (mean +5 pp; `prev_rabi_dev` is the strongest feature), so the level is not a shock; neutral = 0 by construction.", ""]
L += ["### Band counts by scenario (scored districts; thresholds fixed from kharif elnino)", "", "| scenario | high | medium | low | no_data | mean score | mean shock % |", "|---|---|---|---|---|---|---|"]
for s_ in KEYS:
    ok_ = RES[s_]["ok"]; b_ = pd.Series(RES[s_]["band"]).value_counts()
    L.append(f"| {s_} | {b_.get('high', 0)} | {b_.get('medium', 0)} | {b_.get('low', 0)} | {b_.get('no_data', 0)} | {np.nanmean(RES[s_]['score'][ok_]):.1f} | {np.nanmean(shock[s_][ok_]):.2f} |")
# kharif v3 -> v4
if (ART / "_risk_v3_baseline.json").exists():
    B3 = json.load(open(ART / "_risk_v3_baseline.json")); b3 = B3["districts"]
    v3s = pd.Series({int(l): (v["elnino"]["score"] if v["elnino"]["score"] is not None else np.nan) for l, v in b3.items()}).reindex(df.lgd.values)
    v4s = pd.Series(RES[KREF]["score"], index=df.lgd.values); ok3 = v3s.notna() & v4s.notna()
    r3 = v3s[ok3].rank(ascending=False, method="first"); r4 = v4s[ok3].rank(ascending=False, method="first")
    L += ["", "### Kharif: v3 -> v4 (old keys neutral / elnino / elnino_strong)", "",
          f"- Thresholds (elnino tertiles): v3 low < {B3['meta']['band_thresholds']['low_below']}, high >= {B3['meta']['band_thresholds']['high_from']} -> v4 low < **{t_lo:.1f}**, high >= **{t_hi:.1f}**.",
          "- Band counts (high/medium/low), v3 -> v4: " + "; ".join(
              f"{sc}: " + "/".join(str(sum(1 for l, v in b3.items() if v[sc]['band'] == b)) for b in ['high', 'medium', 'low']) + " -> " + "/".join(str(int((RES[sc]['band'][elig] == b).sum())) for b in ['high', 'medium', 'low']) for sc in SCEN) + ".",
          f"- Spearman of elnino scores v3 vs v4: **{float(np.corrcoef(v3s[ok3].rank(), v4s[ok3].rank())[0, 1]):.3f}**; top-25 overlap {len(set(r3[r3 <= 25].index) & set(r4[r4 <= 25].index))} of 25; "
          f"median |rank change| {float((r3 - r4).abs().median()):.0f} of {int(ok3.sum())}. (The v2 -> v3 comparison earlier in this report is computed against the frozen v2 baseline and now includes this v4 change.)"]
# kharif La Nina
kl = KP["lanina"]; il = np.where(elig)[0]
top_l = sorted(il, key=lambda i: -RES[kl]["score"][i])[:10]
L += ["", f"### Kharif La Nina (flood scenario): {int((RES[kl]['band'][elig] == 'high').sum())} high, {int((RES[kl]['band'][elig] == 'medium').sum())} medium, {int((RES[kl]['band'][elig] == 'low').sum())} low", "",
      f"Only flood-flagged districts carry a shock; the rest score on shared S and C. Top 10:", "", "| # | district | state | score | shock % | La Nina flood-year share | flagged |", "|---|---|---|---|---|---|---|"]
for n_, i in enumerate(top_l, 1):
    L.append(f"| {n_} | {df.district.iat[i]} | {df.state.iat[i]} | {RES[kl]['score'][i]:.1f} | {shock[kl][i]:.1f} | {P_flood[i]:.2f} | {ens_info[kl].get(i, {}).get('flood')} |")
# rabi top 15
ir = np.where(rabi_elig)[0]
top_r = sorted(ir, key=lambda i: -RES[KR]["score"][i])[:15]
L += ["", f"### Rabi El Nino ({KR}): top 15 of {len(ir)} rabi-scored districts", "",
      "| # | district | state | score | kharif elnino score | rabi shock % (analog / LightGBM) | heat-winter share | irrigated share | rabi share of foodgrain prod | top drivers |", "|---|---|---|---|---|---|---|---|---|---|"]
for n_, i in enumerate(top_r, 1):
    e_ = ens_info[KR].get(i, {}); ir_ = df.irrigated_share.iat[i]
    d3_ = "; ".join(x["label"] for x in out[str(int(df.lgd.iat[i]))]["risk"][KR]["drivers"][:3])
    L.append(f"| {n_} | {df.district.iat[i]} | {df.state.iat[i]} | {RES[KR]['score'][i]:.1f} | {RES[KREF]['score'][i]:.1f} | {shock[KR][i]:.1f} ({e_.get('analog', np.nan):.1f} / {e_.get('lgbm', np.nan):.1f}) | "
             f"{pd_scn[KR][i]:.2f} | {ir_:.2f} | {rabi_share_prod[i]:.2f} | {d3_} |")
hs = pd.Series(RES[KR]["band"][rabi_elig]).value_counts()
stt_ = pd.DataFrame({"state": df.state.values, "r": RES[KR]["score"], "k": RES[KREF]["score"], "rs": shock[KR], "ra": shock_analog[KR], "heat": pd_scn[KR], "band": RES[KR]["band"], "S": S_val, "C": C_val, "E": RES[KR]["E"], "kE": RES[KREF]["E"]})[rabi_elig]
gst = stt_.groupby("state").agg(n=("r", "size"), high=("band", lambda x: int((x == "high").sum())), rabi=("r", "mean"), kharif=("k", "mean"), E_r=("E", "mean"), E_k=("kE", "mean"),
                              S=("S", "mean"), C=("C", "mean"), shock=("rs", "mean"), analog=("ra", "mean")).query("n >= 8").sort_values("rabi", ascending=False)
L += ["", f"Rabi El Nino band counts: high {int(hs.get('high', 0))}, medium {int(hs.get('medium', 0))}, low {int(hs.get('low', 0))}. States (>= 8 rabi-scored districts), mean scores and components:", "",
      "| state | n | high (rabi) | mean rabi score | mean kharif score | mean exposure rabi / kharif | mean S | mean C | mean rabi shock % | mean analog shock % |", "|---|---|---|---|---|---|---|---|---|---|"]
for st__, r_ in gst.iterrows():
    L.append(f"| {st__} | {int(r_.n)} | {int(r_.high)} | {r_.rabi:.1f} | {r_.kharif:.1f} | {r_.E_r:.2f} / {r_.E_k:.2f} | {r_.S:.2f} | {r_.C:.2f} | {r_['shock']:.2f} | {r_.analog:.2f} |")
# heat sensitivity evidence
if _kd is not None:
    Pk = _kd.dropna(subset=["ydev_pct", "tmax_febmar_anom"]).copy()
    Pk["y"] = Pk.ydev_pct - Pk.groupby("lgd").ydev_pct.transform("mean"); Pk["x"] = Pk.tmax_febmar_anom - Pk.groupby("lgd").tmax_febmar_anom.transform("mean")
    hrows = []
    for st__, g_ in Pk.groupby("state"):
        if g_.lgd.nunique() >= 8:
            hrows.append((st__, g_.lgd.nunique(), len(g_), float((g_.x * g_.y).sum() / (g_.x ** 2).sum())))
    hdf = pd.DataFrame(hrows, columns=["state", "n_districts", "n", "slope"]).sort_values("slope")
    L += ["", "Evidence on terminal heat (within-district OLS: change in rabi yield deviation, pp, per +1 C of Feb-Mar tmax anomaly; 2003-2024; states with >= 8 districts):", "",
          "| state | districts | district-years | pp per +1 C |", "|---|---|---|---|"] + [f"| {r_.state} | {r_.n_districts} | {r_.n} | {r_.slope:+.1f} |" for r_ in hdf.itertuples()]
    wb = ["Punjab", "Haryana", "Uttar Pradesh", "Madhya Pradesh", "Rajasthan"]
    wbm = stt_[stt_.state.isin(wb)].groupby("state").agg(n=("r", "size"), rabi=("r", "mean"), kharif=("k", "mean"), high=("band", lambda x: int((x == "high").sum())))
    L += ["", "**Honest reading on the wheat belt.** The expectation that heat-sensitive irrigated wheat districts (Punjab / Haryana / UP / MP) would rise sharply in the rabi ranking is **not** borne out by the data: "
          "in the district panel the Feb-Mar tmax anomaly explains rabi yield deviations mainly in Karnataka, Andhra Pradesh, Assam, Maharashtra, Bihar and West Bengal (slopes above), and is flat in Punjab / Haryana / Uttar Pradesh / Rajasthan "
          "(irrigated, administratively smooth yields; March-2022 heat is not visible in district APY numbers), and El Nino winters were not systematically hotter or lower-yielding there (analog shocks near zero or positive). "
          "Those states also have low sensitivity and capacity-deficit components (high self-sufficiency, low malnutrition), so their scores stay low: mean rabi / kharif scores " +
          "; ".join(f"{k} {v.rabi:.0f} / {v.kharif:.0f} ({int(v.high)} high of {int(v.n)})" for k, v in wbm.iterrows()) + ". "
          "The rabi high-risk set is led by Jharkhand, Karnataka, Telangana, Andhra Pradesh and tribal / peninsular Madhya Pradesh and Maharashtra, where heat sensitivity, rainfed share and malnutrition coincide. "
          "Rabi exposure of Punjab and Haryana is modestly higher than their kharif exposure (they gain a heat-hazard and a weak-carryover share), but not enough to move them out of the low band. Not tuned: reporting this as the data say."]
# hindcast
if HSUM_R:
    L += ["", "### Rabi hindcast (leave-one-year-out ensemble shock -> score; crop year Y = rabi Y-(Y+1))", "",
          "Method: for crop year Y the predicted shock is the leave-one-year-out ensemble prediction (04b rabi; the model never saw Y) minus the pooled mean of the LOYO LightGBM predictions (level de-bias), the heat hazard is the *observed* Feb-Mar tmax >= +0.5 C indicator of Y+1, "
          "the carry-over term is the same-year kharif deviation, S and C are today's values. rho = Spearman(score, actual rabi deviation), **negative = good**; `rho heat only` = Spearman(Feb-Mar tmax anomaly, actual deviation) as a naive baseline; OOS columns are Spearman(predicted shock, actual), positive = good. "
          "2021-22 is the crop year of the March-2022 heatwave (the brief's '2022-23 (heat March 2022)' refers to the harvest year; both 2021-22 and 2022-23 are shown). Not a forecasting backtest.", "",
          "| crop year | ENSO | n | mean all-India Feb-Mar tmax anom C | rho (score) | rho (exposure only) | rho heat only | top-bottom tercile gap pp | OOS rho analog | OOS rho LightGBM | OOS rho ensemble |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for y_, v_ in HSUM_R.items():
        L.append(f"| {v_['crop_year']} | {v_['phase']} | {v_['n']} | {v_['mean_tmax_febmar_anomaly_c']} | {v_['spearman_rho']} | {v_['rho_exposure_only']} | {v_['rho_heat_only']} | {v_['top_minus_bottom_pct']} | {v_['rho_analog_oos']} | {v_['rho_lgbm_oos']} | {v_['rho_ensemble_oos']} |")
    _rr = [v_["spearman_rho"] for v_ in HSUM_R.values()]; _kr = [v_["spearman_rho"] for v_ in HSUM.values()]
    _hot = [f"{v_['crop_year']} ({v_['share_districts_heat_year']:.0%} of districts)" for v_ in HSUM_R.values() if v_["share_districts_heat_year"] > 0.8]
    L += ["", f"The score has the {'right' if max(_rr) < 0 else 'wrong'} sign in {sum(1 for x_ in _rr if x_ < 0)} of {len(_rr)} winters (rho {min(_rr):.2f} to {max(_rr):.2f}) but is weaker than kharif ({min(_kr):.2f} to {max(_kr):.2f}); "
              + (f"in {', '.join(_hot)} nearly every district was a 'heat winter' (Feb-Mar tmax anomaly >= +{HEAT_THR_C} C), so the heat term does not discriminate there; " if _hot else "")
              + "the discrimination comes from the LightGBM shock and S / C."]
L += ["", "### Caveats (v4)", "",
      f"- Rabi skill is modest: pooled leave-one-year-out LightGBM rho {MR_META['pooled']['lgbm']['rho']:.2f} / MAE {MR_META['pooled']['lgbm']['mae']:.1f} pp vs predict-0 MAE {MR_META['pooled']['zero_baseline_mae']:.1f} pp; the analog (ENSO phase beta) has **no** out-of-sample skill (rho {MR_META['pooled']['analog']['rho']:.2f}, MAE {MR_META['pooled']['analog']['mae']:.1f} pp, worse than predict-0) but carries {ENS_RW['analog']:.2f} of the ensemble weight (inverse-MAE, as kharif) - it is the interpretable ENSO signal, and its disagreement with LightGBM is the `spread` confidence flag." if MR_META else "- Rabi model metadata missing.",
      "- Rabi yields use the APY/UPAG `season` label; Bihar, Odisha, West Bengal, Assam and Jharkhand shift area between seasons across years (Odisha has no Rabi rows in most years -> `no_data`); their rabi deviations include label-switch jumps. UPAG 2023+ covers major crops only.",
      "- Scenario rows use phase-year means of the climate features; the 2026-27 event (ONI NDJ about +2.5 expected) is outside any observed winter, so `elnino_strong` is an analog stress test, not a forecast of the realised event. `prev_kharif_dev` / `prev_rabi_dev` in the scenario rows are the 2024 values.",
      "- Season probabilities beyond the IRI plume horizon are not available: kharif 2027 uses the MJJ-2027 plume (La Nina / neutral split from the previous release ratio); OND-main (Tamil Nadu etc.) districts use the rabi-season probabilities for their kharif `current` mix.",
      "- The kharif ML target remains the all-season foodgrain deviation (kharif-dominated) - Addendum F's 'kharif-season foodgrain yield deviation' split is available (`kharif_fg_*` columns) but the kharif hindcast and models were deliberately left unchanged.",
      f"- La Nina rabi shocks are *gains* on average (mean ensemble {np.nanmean(shock[RP['lanina']][rabi_elig]):+.2f} pp; analog {np.nanmean(shock_analog[RP['lanina']][rabi_elig]):+.2f}); only losses raise exposure, so rabi La Nina scores reflect the heat-hazard / carry-over terms and S / C, not a crop loss.", ""]
lines += L

# ── 15. v5 section: imputation (SCHEMA Addendum G) ──────────────────────────────────────────────────────────────────────
V4B = ART / "_v4_before.json"
nm5 = dict(zip(df.lgd.values, df.district.values)); st5 = dict(zip(df.lgd.values, df.state.values))
L = ["", "---", "", "## v5 — imputation (`pipeline/03c_impute.py`, SCHEMA Addendum G)", "",
     "### What changed", "",
     f"- **Overlay, never overwrite.** Every layer is filled from `artifacts/imputed_district.parquet` only where it is null ({len(IMPM)} columns touched; method tags and per-district map in `imputed_district.json`; details and validation in `reports/03c_impute_report.md`). "
     "Sources: neighbours (touching polygons, border-weighted median, same state first), state / national median as last resort, state NFHS-5 -> NFHS-6 ratio, parent district for post-2011 splits, Earth Engine (WorldPop population, CHIRPS island climate, MODIS-NDVI rabi share).",
     f"- **Existing districts are not re-ranked by imputed ones.** Percentile ranks use the *observed* population of each term (`elig_ref`: {int(elig_ref.sum())} districts, imputed entries of a term excluded from its reference) and the band thresholds are still the tertiles of the observed kharif elnino scores "
     f"(low < **{t_lo:.1f}**, high >= **{t_hi:.1f}**; v4: low < 44.9, high >= 55.4 - the shift is the effect of newly filled price / groundwater / NFHS terms on the {int(elig_ref.sum())} observed districts).",
     f"- **Newly scored, regular model ({int((elig_x & elig_reg & ~elig_ref).sum())} districts):** split children / new districts whose crop structure is the parent's (area share), and island districts with CHIRPS climate. Their shock is the analog formula (no 04b model row) with state-median beta where needed.",
     f"- **Consumption side ({int(CONS.sum())} districts: Delhi x11, Mumbai x2, Kolkata, Chennai, Hyderabad, Chandigarh, Srinagar, The Nilgiris, Mahe, Yanam, Lakshadweep, South Andaman, Nicobars):** exposure = mean exposure of the donor districts "
     "(same state if >= 3 scored, else the touching districts found by breadth-first search, topped up with the 5 nearest by centroid for islands), expected shock = donors' mean shock, sensitivity = low self-sufficiency of the donor pool x 0.5 + PDS dependency x 0.5 "
     "(no crop-structure terms), capacity as usual (NFHS, Poshan, climate vulnerability, PDS). Actions that need local production (grain pre-position, seed bank, NREGA, fodder, PMFBY) are null; child / women-anaemia targets are computed. `risk.*.imputed = true`, `imputed_from = urban_consumption_side`.",
     f"- **Rabi without a 04b model row ({int(rabi_nb.sum())} districts: negligible-rabi and season-label-gap, rabi share of foodgrain area >= {RABI_MIN_SHARE:.1%}):** the rabi shock of every phase is the border-weighted median of the touching districts' model shocks (`expected_shock_source = neighbours`, `imputed_from = neighbours_exposure`); "
     "the heat-hazard term uses the district's own Feb-Mar temperature. Season-label-gap districts (Odisha, Kerala, DNH) also get their rabi foodgrain area / production from the NDVI estimate (`ee_rabi_ndvi`; map R2 is only ~0.24, see 03c report) instead of the under-reported APY rows. "
     f"The {int((elig_x & ~rabi_elig_x).sum())} districts below the {RABI_MIN_SHARE:.1%} rabi-share floor stay `no_data` for rabi (`negligible_rabi_foodgrain`).",
     f"- **Flags.** `risk.<key>.imputed = true` (+ `imputed_from`, `imputed_share`) when the exposure is imputed (consumption side / neighbour rabi shock / imputed climate / parent crop structure) or imputed inputs carry >= {IMP_FLAG_SHARE:.0%} of the score weight (`imputed_inputs`); `data_quality.imputed` {{dotted path: source}} and `imputed_count` list every imputed entry incl. `risk.<key>`.", ""]
if V4B.exists():
    V4 = json.load(open(V4B)); sc0 = V4["scores"]
    L += ["### no_data and band counts, before -> after", "", "| scenario | before (high/medium/low/no_data) | after |", "|---|---|---|"]
    for k_ in KEYS:
        b0 = V4["bands"].get(k_)
        if b0 is None:
            continue
        f4 = lambda d_: "/".join(str(d_.get(b, 0)) for b in ("high", "medium", "low", "no_data"))
        b1 = pd.Series(RES[k_]["band"]).value_counts().to_dict()
        L.append(f"| {k_} | {f4(b0)} | {f4(b1)} |")
    L += ["", f"Kharif elnino `no_data`: {V4['no_data_k']} -> {int((RES[KREF]['band'] == 'no_data').sum())}; rabi elnino `no_data`: {V4['no_data_r']} -> {int((RES[RP['elnino']]['band'] == 'no_data').sum())} "
          f"({', '.join(f'{k}: {v}' for k, v in pd.Series(rabi_reason[elig_x & ~rabi_elig_x]).value_counts().items())}).", ""]
    k0 = pd.Series({int(l): v["k"] for l, v in sc0.items()}).reindex(df.lgd.values); r0 = pd.Series({int(l): v["r"] for l, v in sc0.items()}).reindex(df.lgd.values)
    kb0 = pd.Series({int(l): v["kb"] for l, v in sc0.items()}).reindex(df.lgd.values); rb0 = pd.Series({int(l): v["rb"] for l, v in sc0.items()}).reindex(df.lgd.values)
    k1 = pd.Series(RES[KREF]["score"], index=df.lgd.values); r1 = pd.Series(RES[RP["elnino"]]["score"], index=df.lgd.values)
    kb1 = pd.Series(RES[KREF]["band"], index=df.lgd.values); rb1 = pd.Series(RES[RP["elnino"]]["band"], index=df.lgd.values)
    L += ["### Stability of the districts that were already scored (elnino)", ""]
    for lab_, a0, a1, b0_, b1_ in (("kharif", k0, k1, kb0, kb1), ("rabi", r0, r1, rb0, rb1)):
        okk = a0.notna() & a1.notna()
        rho_ = float(np.corrcoef(a0[okk].rank(), a1[okk].rank())[0, 1]); dd_ = (a1[okk] - a0[okk])
        ct = pd.crosstab(b0_[okk], b1_[okk]).reindex(index=["high", "medium", "low"], columns=["high", "medium", "low"]).fillna(0).astype(int)
        t25a = set(a0[okk].sort_values(ascending=False).index[:25]); t25b = set(a1[okk].sort_values(ascending=False).index[:25])
        moved = int(ct.values.sum() - np.trace(ct.values))
        L.append(f"- **{lab_}**: n = {int(okk.sum())}, Spearman before vs after = **{rho_:.3f}**, mean |score change| {dd_.abs().mean():.2f} pts (max {dd_.abs().max():.1f}), {moved} band moves ({100 * moved / int(okk.sum()):.0f} %), top-25 overlap {len(t25a & t25b)} of 25. "
                 "Band matrix (rows before, columns after; high/medium/low): " + "; ".join(f"{r_}: " + "/".join(str(int(ct.loc[r_, c_])) for c_ in ct.columns) for r_ in ct.index) + ".")
    big = (k1 - k0).dropna().abs().sort_values(ascending=False).head(8)
    L += ["", "Largest kharif elnino score changes among observed districts (cause = terms that were missing and are now estimated, mostly price / groundwater / NFHS): " +
          "; ".join(f"{nm5[l]} ({st5[l]}) {k0[l]:.1f} -> {k1[l]:.1f}" for l in big.index) + ".", ""]
L += ["### Consumption-side districts (kharif elnino): score vs the donors they inherit exposure from", "",
      "| district | state | score | band | exposure | sensitivity | capacity | donors (n) | donor mean score | donor mean exposure |", "|---|---|---|---|---|---|---|---|---|---|"]
for i_ in np.where(CONS)[0]:
    d_ = DON_K[i_]; rk_ = RES[KREF]
    L.append(f"| {nm5[df.lgd.values[i_]]} | {st5[df.lgd.values[i_]]} | {rk_['score'][i_]:.1f} | {rk_['band'][i_]} | {rk_['E'][i_]:.2f} | {S_val[i_]:.2f} | {C_val[i_]:.2f} | {len(d_)} | {np.nanmean(rk_['score'][d_]):.1f} | {np.nanmean(rk_['E'][d_]):.2f} |")
L += ["", "### Flags", ""]
for key_, lab_ in ((KREF, "kharif elnino"), (RP["elnino"], "rabi elnino")):
    okk = RES[key_]["ok"] & (RES[key_]["band"] != "no_data")
    fl_ = pd.Series([("imputed_inputs" if (imputed_share(key_, i_) >= IMP_FLAG_SHARE and (STRUCT_R if kind_of(key_) == "rabi" else STRUCT_K)[i_] is None) else (STRUCT_R if kind_of(key_) == "rabi" else STRUCT_K)[i_]) for i_ in np.where(okk)[0]])
    L.append(f"- {lab_}: {int(okk.sum())} scored; flagged `imputed`: {int(fl_.notna().sum())} ({', '.join(f'{k}: {v}' for k, v in fl_.value_counts().items())}); the other {int(fl_.isna().sum())} are scored on observed inputs (some single terms may still be estimated and carry the `(estimated)` tag in their driver label).")
L += ["", "### Caveats (v5)", "",
      "- Imputed values are *typical for the area*, not local measurements: the leave-one-out table in the 03c report shows the neighbour method beats a state median clearly for nutrition, rainfed / small-holding shares and groundwater depth, and not at all for NFHS-5 wasting, the price indices, groundwater decline and PDS tonnes per person (spatially noisy). About 600 entries (mostly price / groundwater) fall back to the national median because whole states (NE hills, Himachal, Uttarakhand) have no data.",
      "- Consumption-side scores are a *supply-chain exposure proxy*, not a crop-yield risk; Mumbai scores high because Maharashtra's donors are high, Delhi low-to-medium because Haryana / UP / Rajasthan districts are. Lakshadweep (donors = 5 nearest Kerala-coast districts, no touching land) and the Andamans are the least certain.",
      "- Rabi band of the 154 neighbour-shock districts inherits the neighbours' *model* shock; for districts with almost no rabi cropping (Arunachal, Mizoram, Nagaland, Chhattisgarh Bastar) it is a notional exposure of a minor activity - read together with `season_context.rabi.share_of_foodgrain_prod`. The NDVI rabi-share map has R2 ~ 0.24, so imputed rabi production for the 14 season-label-gap districts is indicative.",
      "- WorldPop population (calibrated to the census-based level by the state median ratio) fills the 22 post-2011 districts; split PARENTS still carry pre-split census populations and crop totals (unchanged known caveat), so a parent / child pair double counts a little in national totals.",
      "- `districts.json` grew from 14.9 to ~16.9 MB (the 06_export size guard `MAX_MB` is raised from 15 to 17): 188 more districts have a rabi risk block."]
lines += L

# ── v6 report section: season outlook (Addendum I) ───────────────────────────────────────────────────────────────────────────
_so_n = sum(v is not None for v in SEASON_OUTLOOK.values())
L = ["", "---", "", "## v6 — season outlook (`season_outlook`, SCHEMA Addendum I)", "",
     f"- `season_outlook[season][phase]` for {_so_n} / {N} districts (every district with a climate record, observed or imputed), 5 phases x 2 seasons; `kpis.season_outlook_national` = cropped-area-weighted means (gross cropped area) of the same fields.",
     f"- Kharif: `rain_anom_pct` = the scenario anomaly used in the exposure terms (main-season: JJAS, or OND for the {int(is_ond.sum())} OND-main districts - their rain_window is Oct\u2013Dec and TimesFM JJAS fields are null); "
     "`p_deficit_gt10` = share of El Nino years with a > 10 % deficit (strong analog: mean of that and the strong-analog share, as in the exposure hazard; neutral: climatological share of all 2000-2025 years; "
     "La Nina: share of La Nina years > +15 % = the flood share, as the contract says; current: probability-weighted TRUE deficit share of the three phases); `tmax_anom_c` = JJAS tmax anomaly of the phase's years (neutral 0); "
     "`onset_delay_days` = phase-year mean onset day minus all-year mean (02_climate onset: first day after 1 Jun with 7-day rain >= 50 mm); TimesFM fields display-only.",
     "- Rabi: `rain_anom_pct` = mean OND anomaly of the phase's crop years (the `rain_anomaly_pct` of the rabi scenario); `tmax_anom_c` = Feb\\u2013Mar tmax anomaly of the FOLLOWING year (crop year Y -> Feb\\u2013Mar Y+1) averaged over the phase's years (strong: 2002 / 2009 / 2015) - the same series as the rabi score's terminal-heat hazard (`risk.*.tmax_febmar_anomaly_c`); neutral 0; La Nina -0.3 C **assumption**, not data. "
     f"NOTE: this differs from `climate.tmax_febmar_elnino_anomaly_c` (same calendar year, national El Nino mean {np.nanmean(_tf_el):+.2f} C vs {np.nanmean(tf_scn[RP['elnino']]):+.2f} C here); per coordinator decision the outlook matches the score.",
     "- `plain` sentence: probability word from `enso_status.p_by_season` of the phase (>= 0.8 very likely, 0.5\u20130.8 likely, 0.1\u20130.5 possible; **< 0.1 is written 'in <phase> years (unlikely this season)'**, an addition so a 0 % phase is not called possible; the strong El Nino analog carries no probability word); `current` uses the dominant phase's probability and the probability-weighted numbers. "
     "The head line follows the phrasing rule (El Nino kharif -> weak monsoon; La Nina -> heavy rain / flooding; neutral -> near-normal; El Nino rabi -> dry / warm winter) but only where the district's own record supports it (kharif El Nino: rain <= -5 % or deficit chance >= 50 %; La Nina: flood share >= 25 % or rain >= +5 %; rabi: dry <= -5 %, wet >= +5 %, warm >= +0.3 C, cool <= -0.3 C), otherwise a near-normal wording is used.", "",
     "| season | phase | rain % | p deficit | tmax C | onset d | plain |", "|---|---|---|---|---|---|---|"]
for _sid in (KID, RID):
    for _ph in SO_PH:
        _o = SO_NATIONAL[_sid][_ph]
        L.append(f"| {_sid} | {_ph} | {_o.get('rain_anom_pct')} | {_o.get('p_deficit_gt10', '')} | {_o.get('tmax_anom_c')} | {_o.get('onset_delay_days', '')} | {_o.get('plain')} |")
L += ["", "Labels: every user-facing 'MGNREGA' is now 'NREGA' (actions CSV header `nrega_persondays`, report text); JSON keys keep `mgnrega_persondays`.", ""]
lines += L

(ART / "reports").mkdir(exist_ok=True)
(ART / "reports" / "04_risk_report.md").write_text("\n".join(lines))
log("report written; done")
