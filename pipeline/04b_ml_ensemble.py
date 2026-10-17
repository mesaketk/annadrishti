"""04b_ml_ensemble.py - ML yield-shock ensemble (analog beta + LightGBM + TabFM) for AnnaDrishti.

Reads  : crops_district_year, climate_district, crops_latest, social_district, extra_district, yield_sensitivity,
         districts.json (shipped analog shock), timeseries_climate/*.json (oni_phase, only for sanity), NOAA ONI.
Writes : artifacts/_ml_panel.parquet            district x year panel (cache)
         artifacts/ml_ensemble.parquet          lgd x scenario predictions (analog / lgbm / tabfm / ensemble / spread)
         artifacts/ml_ensemble_meta.json        weights, pooled + per-year metrics, features, versions
         artifacts/reports/04b_ml_report.md

Target `ydev_pct` is IDENTICAL to the hindcast actual in 04_risk.py (`actual_dev`): Theil-Sen trend of foodgrain yield over
the trailing 10 crop years (>= 6 obs), deviation of year Y from that trend extrapolated to Y, in %, clipped +/-100.

Harness: leave-one-year-out (LOYO). For held-out year Y the model trains on all other years except Y+1 (whose
prev_year_ydev feature would contain Y's target). Analog baseline betas are recomputed with Y excluded.
TabFM (google-research/tabfm, PyTorch CPU) is optional: any failure is recorded and the `tabfm` slot left null.

v4 (seasons, SCHEMA Addendum F):
  * kharif (default): unchanged panel / target / harness / LightGBM; scenario rows gain `lanina` (La Nina-year mean climate, ONI -1.0). The analog member is now
    computed here for the pure phases (El Nino p = 1; v3 read a p(El Nino) = 0.61 weighted analog from the previous export, the probability weighting now lives in
    04_risk `current`), and La Nina follows the flood rule: shock = beta_LaNina (La Nina-year minus neutral-year foodgrain deviation) only where the district's
    La Nina-year main-season rain anomaly is > +15 % AND beta_LaNina < 0, else 0 (benign); the La Nina ensemble is gated the same way.
  * `--season rabi`: separate panel (artifacts/_ml_panel_rabi.parquet), target = rabi-season foodgrain yield deviation (rabi_fg_yield_t_ha from 01_crops, same
    trailing-10-year Theil-Sen deviation), features OND anomaly, Feb-Mar tmax anomaly, groundwater stress, previous kharif / rabi deviation, irrigation, state, ONI NDJ ...
    Same leave-one-year-out harness. Writes artifacts/ml_ensemble_rabi.parquet, ml_ensemble_rabi_meta.json, _ml_loyo_preds_rabi.parquet, reports/04b_ml_report_rabi.md.
    Scenario rows: lanina / neutral / elnino / elnino_strong built from phase-year means of the climate features (crop year Y: OND and JJAS of Y, Feb-Mar tmax of Y+1).

Run: python3 pipeline/04b_ml_ensemble.py [--season kharif|rabi] [--no-tabfm] [--tabfm-rows N] [--refresh-panel]
"""
from __future__ import annotations
import argparse, json, sys, time, warnings, os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import theilslopes, spearmanr

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import districts, ART, save_json, enso_phase_by_monsoon_year, oni

T0 = time.time()
ap = argparse.ArgumentParser()
ap.add_argument("--no-tabfm", action="store_true")
ap.add_argument("--tabfm-rows", type=int, default=int(os.environ.get("TABFM_ROWS", "3000")))
ap.add_argument("--tabfm-estimators", type=int, default=int(os.environ.get("TABFM_EST", "4")))
ap.add_argument("--tabfm-years", default=os.environ.get("TABFM_YEARS", "all"), help="'all' or comma list of held-out years scored with TabFM (CPU cost)")
ap.add_argument("--refresh-panel", action="store_true")
ap.add_argument("--season", choices=["kharif", "rabi"], default="kharif")
ARGS = ap.parse_args()

YEARS = list(range(2000, 2026))           # climate years
PANEL_YEARS = list(range(2000, 2025))     # target years (crop panel ends 2024)
EVAL_YEARS = list(range(2002, 2025))
HIND_YEARS = [2009, 2014, 2015, 2023]
OND_STATES = {"Tamil Nadu", "Puducherry"}
OND_EXTRA_LGD = {515, 503, 517}
SCEN = ["neutral", "elnino", "elnino_strong"]
SCEN_K = SCEN + ["lanina"]                 # v4: kharif scenario rows incl. La Nina
ONI_SCN = {"neutral": 0.0, "elnino": 1.5, "elnino_strong": 2.2, "lanina": -1.0}
FLOOD_THR = 15.0                           # La Nina kharif: main-season rain anomaly (%) above which a district is flood-exposed (Addendum F)
BETA_CLIP, SHOCK_CLIP, G_FLOOR, DEFICIT_YEARS = (-40.0, 15.0), (-45.0, 10.0), 0.5, [2002, 2004, 2009, 2012, 2014, 2015, 2023]
P_MJJ27_DEFAULT = 0.61
FEATS = ["jjas_anomaly_pct", "ond_anomaly_pct", "main_anom_pct", "dry_spells", "onset_day", "tmax_jjas_anom", "tmax_febmar_anom",
         "oni_jja_son", "prev_year_ydev", "irrigated_share", "simpson_div", "top_crop_share", "small_marginal_share",
         "gw_stress_idx", "state", "main_season_ond", "lat", "lon"]
CAT = ["state"]


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def jser(col: pd.Series, years):
    out = np.full((len(col), len(years)), np.nan)
    for i, s in enumerate(col.values):
        if isinstance(s, str):
            d = json.loads(s)
            for k, y in enumerate(years):
                v = d.get(str(y))
                if v is not None:
                    out[i, k] = v
    return out


# ── 1. panel ──────────────────────────────────────────────────────────────────
def trailing_dev(row: dict[int, float], Y: int) -> float:
    """== 04_risk.actual_dev: Theil-Sen on the 10 prior crop years (>= 6 obs)."""
    yv = row.get(Y, np.nan)
    ys = [y for y in range(Y - 10, Y) if np.isfinite(row.get(y, np.nan))]
    if len(ys) < 6 or not np.isfinite(yv):
        return np.nan
    sl, ic, _, _ = theilslopes([row[y] for y in ys], ys)
    pred = ic + sl * Y
    if pred <= 0.05:
        return np.nan
    return float(np.clip((yv - pred) / pred * 100, -100, 100))


def build_panel() -> pd.DataFrame:
    m = districts()[["lgd", "state", "centroid_lon", "centroid_lat"]].copy()
    cl = pd.read_parquet(ART / "climate_district.parquet")
    crops = pd.read_parquet(ART / "crops_latest.parquet")[["lgd", "irrigated_share", "small_marginal_share"]]
    extra = pd.read_parquet(ART / "extra_district.parquet")[["lgd", "gw_stress_idx"]]
    cy = pd.read_parquet(ART / "crops_district_year.parquet")
    for d in (m, cl, crops, extra, cy):
        d["lgd"] = d["lgd"].astype(int)
    d0 = m.merge(cl, on="lgd", how="inner").merge(crops, on="lgd", how="left").merge(extra, on="lgd", how="left")
    ond_main = (d0.state.isin(OND_STATES) | d0.lgd.isin(OND_EXTRA_LGD)).values
    J = jser(d0.jjas_anomaly_json, YEARS); O = np.clip(jser(d0.ond_anomaly_json, YEARS), -100, 100)
    DS = jser(d0.dry_spells_json, YEARS); ON = jser(d0.onset_day_json, YEARS)
    TX = jser(d0.tmax_jjas_anomaly_json, YEARS); TF = jser(d0.tmax_febmar_anomaly_json, YEARS)
    o = oni(); o = o[o.seas.isin(["JJA", "JAS", "ASO", "SON"])].groupby("yr").anom.mean()
    # yield series -> deviations (all years 1997..2024 so prev_year_ydev is available from 2004)
    piv = cy.pivot_table(index="lgd", columns="crop_year", values="foodgrain_yield_t_ha", aggfunc="first")
    ydev = {}
    for lgd in d0.lgd.values:
        if lgd not in piv.index:
            continue
        row = piv.loc[lgd].to_dict()
        ydev[lgd] = {Y: trailing_dev(row, Y) for Y in range(2000, 2025)}
    rows = []
    for i, r in enumerate(d0.itertuples()):
        yd = ydev.get(r.lgd, {})
        for k, y in enumerate(YEARS):
            if y > 2024:
                continue
            ond = bool(ond_main[i])
            rows.append(dict(lgd=r.lgd, year=y, ydev_pct=yd.get(y, np.nan), prev_year_ydev=yd.get(y - 1, np.nan),
                             jjas_anomaly_pct=J[i, k], ond_anomaly_pct=O[i, k], main_anom_pct=O[i, k] if ond else J[i, k],
                             dry_spells=DS[i, k], onset_day=ON[i, k], tmax_jjas_anom=TX[i, k], tmax_febmar_anom=TF[i, k],
                             oni_jja_son=float(o.get(y, np.nan)), irrigated_share=r.irrigated_share,
                             small_marginal_share=r.small_marginal_share, gw_stress_idx=r.gw_stress_idx,
                             state=r.state, main_season_ond=int(ond), lat=r.centroid_lat, lon=r.centroid_lon))
    P = pd.DataFrame(rows)
    # simpson_div / top_crop_share vary by year in the crop panel (diversification of that crop year)
    P = P.merge(cy[["lgd", "crop_year", "simpson_div", "top_crop_share"]].rename(columns={"crop_year": "year"}),
                on=["lgd", "year"], how="left")
    # fill missing yearly diversity with the district's median (static structure), never 0
    for c in ("simpson_div", "top_crop_share"):
        P[c] = P[c].fillna(P.groupby("lgd")[c].transform("median"))
    ld = pd.read_parquet(ART / "crops_latest.parquet")[["lgd", "simpson_div", "top_crop_share"]]
    for c in ("simpson_div", "top_crop_share"):
        P[c] = P[c].fillna(P.lgd.map(ld.set_index("lgd")[c]))
    return P


# ══════════════════════════════════════════════════════════════════════════════
# v4 RABI MODE  (python3 pipeline/04b_ml_ensemble.py --season rabi)  -- runs to completion and exits; the kharif flow below is untouched
# ══════════════════════════════════════════════════════════════════════════════
RABI_MIN_AREA_HA = 500           # rabi yield from < 500 ha is rounding noise (same as 01_crops MIN_AREA_HA)
RABI_ELIG_AREA_HA = 2000         # a district gets a rabi score only if its median (2018+) rabi foodgrain area >= 2000 ha ...
RABI_ELIG_SHARE = 0.05           # ... and rabi >= 5 % of (rabi + kharif) foodgrain area
RABI_ELIG_YEARS = 3              # ... and >= 3 crop years in 2018-2024 with rabi foodgrain area >= 2000 ha (Odisha / Kerala season-label gaps fail this)
RABI_HIND_YEARS = [2009, 2015, 2021, 2022]    # crop years (rabi sown Oct Y, harvested Mar Y+1): 2009-10 dry El Nino winter, 2015-16 El Nino winter, 2021-22 (March-2022 heatwave), 2022-23
RABI_FEATS = ["ond_anomaly_pct", "tmax_febmar_anom", "jjas_anomaly_pct", "oni_ndj", "prev_kharif_dev", "prev_rabi_dev", "irrigated_share",
              "gw_stress_idx", "small_marginal_share", "top_crop_share", "rabi_share", "state", "lat", "lon"]
RABI_SCEN = ["neutral", "lanina", "elnino", "elnino_strong"]
STRONG_YEARS = [2002, 2009, 2015]


def run_rabi():
    import lightgbm as lgb
    import sklearn
    t0 = time.time()
    CY = pd.read_parquet(ART / "crops_district_year.parquet"); CY["lgd"] = CY.lgd.astype(int)
    for c in ("rabi_fg_yield_t_ha", "kharif_fg_yield_t_ha", "rabi_fg_area_ha", "kharif_fg_area_ha"):
        if c not in CY.columns:
            raise SystemExit(f"{c} missing from crops_district_year.parquet - re-run pipeline/01_crops.py (v4) first")
    # ── panel ────────────────────────────────────────────────────────────────
    path = ART / "_ml_panel_rabi.parquet"
    m = districts()[["lgd", "state", "centroid_lon", "centroid_lat"]].copy()
    cl = pd.read_parquet(ART / "climate_district.parquet"); cl["lgd"] = cl.lgd.astype(int)
    crops = pd.read_parquet(ART / "crops_latest.parquet")[["lgd", "irrigated_share", "small_marginal_share", "top_crop_share"]]
    extra = pd.read_parquet(ART / "extra_district.parquet")[["lgd", "gw_stress_idx"]]
    for d in (m, crops, extra):
        d["lgd"] = d["lgd"].astype(int)
    d0 = m.merge(cl, on="lgd", how="inner").merge(crops, on="lgd", how="left").merge(extra, on="lgd", how="left")
    Jy = jser(d0.jjas_anomaly_json, YEARS); Oy = np.clip(jser(d0.ond_anomaly_json, YEARS), -100, 100); TFy = jser(d0.tmax_febmar_anomaly_json, YEARS)
    o = oni(); ndj = o[o.seas == "NDJ"].groupby("yr").anom.mean()
    def dev_table(col, area_col):
        w = CY.pivot_table(index="lgd", columns="crop_year", values=col, aggfunc="first")
        a = CY.pivot_table(index="lgd", columns="crop_year", values=area_col, aggfunc="first").reindex(index=w.index, columns=w.columns)
        w = w.where(a >= RABI_MIN_AREA_HA)
        return {l: {Y: trailing_dev(w.loc[l].to_dict(), Y) for Y in range(2000, 2025)} for l in d0.lgd.values if l in w.index}
    dev_r = dev_table("rabi_fg_yield_t_ha", "rabi_fg_area_ha"); dev_k = dev_table("kharif_fg_yield_t_ha", "kharif_fg_area_ha")
    st = CY[CY.crop_year >= 2018].groupby("lgd")[["rabi_fg_area_ha", "kharif_fg_area_ha"]].median()
    st["rabi_share"] = st.rabi_fg_area_ha / (st.rabi_fg_area_ha + st.kharif_fg_area_ha)
    rows = []
    for i, r in enumerate(d0.itertuples()):
        dr, dk = dev_r.get(r.lgd, {}), dev_k.get(r.lgd, {})
        rs = st.rabi_share.get(r.lgd, np.nan)
        for Y in range(2000, 2025):
            k, k1 = YEARS.index(Y), YEARS.index(Y + 1)
            rows.append(dict(lgd=r.lgd, year=Y, ydev_pct=dr.get(Y, np.nan), prev_rabi_dev=dr.get(Y - 1, np.nan), prev_kharif_dev=dk.get(Y, np.nan),
                             ond_anomaly_pct=Oy[i, k], jjas_anomaly_pct=Jy[i, k], tmax_febmar_anom=TFy[i, k1], oni_ndj=float(ndj.get(Y, np.nan)),
                             irrigated_share=r.irrigated_share, gw_stress_idx=r.gw_stress_idx, small_marginal_share=r.small_marginal_share,
                             top_crop_share=r.top_crop_share, rabi_share=rs, state=r.state, lat=r.centroid_lat, lon=r.centroid_lon))
    PAN = pd.DataFrame(rows); PAN["state"] = PAN.state.astype(str)
    PAN.to_parquet(path, index=False)
    STS = sorted(PAN.state.unique())
    Dr = PAN.dropna(subset=["ydev_pct"]).reset_index(drop=True)
    log(f"[rabi] panel rows {len(PAN)}, with target {len(Dr)}, districts {Dr.lgd.nunique()}, years {Dr.year.min()}-{Dr.year.max()}")

    def to_X(df):
        X = df[RABI_FEATS].copy(); X["state"] = pd.Categorical(X["state"], categories=STS); return X

    # ── analog (phase-year beta) ───────────────────────────────────────────────
    ph = enso_phase_by_monsoon_year()
    LG_ = sorted(PAN.lgd.unique()); LI_ = {l: i for i, l in enumerate(LG_)}
    stat = PAN.drop_duplicates("lgd").set_index("lgd")
    ST_OF = stat.state.reindex(LG_).values
    YR = list(range(2000, 2025)); YI_ = {y: k for k, y in enumerate(YR)}
    DEVR = np.full((len(LG_), len(YR)), np.nan)
    for r in PAN[["lgd", "year", "ydev_pct"]].itertuples():
        DEVR[LI_[r.lgd], YI_[r.year]] = r.ydev_pct
    YA = np.array(YR)
    EL_ = np.array([ph.get(y) == "El Niño" for y in YA]); NE_ = np.array([ph.get(y) == "Neutral" for y in YA]); LA_ = np.array([ph.get(y) == "La Niña" for y in YA])
    S3_ = np.isin(YA, STRONG_YEARS)

    def eff(M, a, b, mina=3, minb=3):
        A_, B_ = M[:, a], M[:, b]
        na, nb = np.isfinite(A_).sum(1), np.isfinite(B_).sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            e = np.nanmean(A_, 1) - np.nanmean(B_, 1)
        return np.where((na >= mina) & (nb >= minb), e, np.nan)

    def impute(b):
        b = b.copy(); sm = pd.Series(b).groupby(ST_OF).agg(["median", "count"]); nat = np.nanmedian(b)
        src = np.array(["district"] * len(b), dtype=object)
        for i in np.where(~np.isfinite(b))[0]:
            s_ = ST_OF[i]
            if s_ in sm.index and sm.loc[s_, "count"] >= 3:
                b[i] = sm.loc[s_, "median"]; src[i] = "state_median"
            else:
                b[i] = nat; src[i] = "national_median"
        return b, src

    def rabi_betas(keep):
        el, ne, la, s3 = EL_ & keep, NE_ & keep, LA_ & keep, S3_ & keep
        cl_ = lambda x: np.where(np.isfinite(x), np.clip(x, *BETA_CLIP), np.nan)
        b_el, src_el = impute(cl_(eff(DEVR, np.where(el)[0], np.where(ne)[0])))
        b_la, _ = impute(cl_(eff(DEVR, np.where(la)[0], np.where(ne)[0])))
        b_s3 = cl_(eff(DEVR, np.where(s3)[0], np.where(ne)[0], mina=2))
        b_st = np.where(np.isfinite(b_s3), np.minimum(b_el, 0.5 * b_el + 0.5 * b_s3), b_el)      # strong: never milder than the El Nino effect
        return b_el, b_la, b_st, src_el

    # ── harness ────────────────────────────────────────────────────────────────
    LGB_P = dict(objective="huber", alpha=15.0, learning_rate=0.04, num_leaves=15, min_child_samples=60, subsample=0.8, subsample_freq=1,
                 colsample_bytree=0.8, reg_lambda=5.0, n_estimators=800, verbose=-1, n_jobs=-1, random_state=7)

    def fit(Dtr, seed=7):
        yrs = np.array(sorted(Dtr.year.unique())); rng = np.random.default_rng(seed)
        val = set(rng.choice(yrs, size=max(2, len(yrs) // 6), replace=False)); isv = Dtr.year.isin(val).values
        mdl = lgb.LGBMRegressor(**{**LGB_P, "random_state": seed})
        mdl.fit(to_X(Dtr[~isv]), Dtr.ydev_pct[~isv], eval_set=[(to_X(Dtr[isv]), Dtr.ydev_pct[isv])], eval_metric="l1", categorical_feature=["state"],
                callbacks=[lgb.early_stopping(60, verbose=False)])
        return mdl

    def metr(y, p):
        ok = np.isfinite(y) & np.isfinite(p); y, p = y[ok], p[ok]
        if len(y) < 10:
            return dict(n=int(len(y)), mae=np.nan, rho=np.nan, gap=np.nan)
        rho = float(spearmanr(p, y)[0]) if np.std(p) > 0 else np.nan
        q1, q2 = np.quantile(p, [1 / 3, 2 / 3]); worst, best = y[p <= q1], y[p >= q2]
        return dict(n=int(len(y)), mae=float(np.mean(np.abs(y - p))), rho=rho, gap=float(worst.mean() - best.mean()) if len(worst) and len(best) else np.nan)

    EVAL = list(range(2003, 2025))
    preds = {k: pd.Series(np.nan, index=Dr.index) for k in ("analog", "lgbm")}
    for Y in EVAL:
        te = Dr.index[Dr.year == Y]
        if len(te) == 0:
            continue
        Dtr = Dr[(Dr.year != Y) & (Dr.year != Y + 1)]       # Y+1 dropped: its prev_rabi_dev feature contains Y's target
        b_el, b_la, _, _ = rabi_betas(YA != Y)
        li = Dr.loc[te, "lgd"].map(LI_).values
        pY = ph.get(Y)
        sh = b_el if pY == "El Niño" else (b_la if pY == "La Niña" else np.zeros(len(LG_)))
        preds["analog"].loc[te] = np.clip(sh, *SHOCK_CLIP)[li]
        ms = [fit(Dtr, sd) for sd in (7, 11, 19)]
        preds["lgbm"].loc[te] = np.mean([m_.predict(to_X(Dr.loc[te])) for m_ in ms], 0)
        log(f"[rabi] fold {Y}: n={len(te)} lgbm iters={[m_.best_iteration_ for m_ in ms]}")
    per_year = {k: {Y: metr(Dr.ydev_pct[Dr.year == Y].values, preds[k][Dr.year == Y].values) for Y in EVAL if (Dr.year == Y).any()} for k in preds}
    pooled = {}
    for k in preds:
        pm = metr(Dr.ydev_pct.values, preds[k].values)
        rh = [v["rho"] for v in per_year[k].values() if np.isfinite(v["rho"])]
        pm["mean_within_year_rho"] = float(np.mean(rh)) if rh else np.nan
        pm["mean_year_mae"] = float(np.mean([v["mae"] for v in per_year[k].values()]))
        pooled[k] = pm
    pooled["zero_baseline_mae"] = float(np.mean(np.abs(Dr.ydev_pct.values)))
    inv = {k: 1.0 / pooled[k]["mae"] for k in ("analog", "lgbm")}
    W = {k: inv[k] / sum(inv.values()) for k in inv}; W["tabfm"] = None
    ens = pd.Series(W["analog"] * preds["analog"].values + W["lgbm"] * preds["lgbm"].values, index=Dr.index)
    per_year["ensemble"] = {Y: metr(Dr.ydev_pct[Dr.year == Y].values, ens[Dr.year == Y].values) for Y in EVAL if (Dr.year == Y).any()}
    pm = metr(Dr.ydev_pct.values, ens.values); rh = [v["rho"] for v in per_year["ensemble"].values() if np.isfinite(v["rho"])]
    pm["mean_within_year_rho"] = float(np.mean(rh)); pm["mean_year_mae"] = float(np.mean([v["mae"] for v in per_year["ensemble"].values()])); pooled["ensemble"] = pm
    log("[rabi] pooled", {k: (round(v["mae"], 2), round(v["rho"], 3)) if isinstance(v, dict) else round(v, 2) for k, v in pooled.items()}, "weights", W)
    pd.DataFrame({"lgd": Dr.lgd.astype(int).values, "year": Dr.year.astype(int).values, "pred_lgbm": preds["lgbm"].values, "pred_analog": preds["analog"].values,
                  "pred_ensemble": ens.values, "actual": Dr.ydev_pct.values}).to_parquet(ART / "_ml_loyo_preds_rabi.parquet", index=False)

    # ── final models + scenario rows ───────────────────────────────────────────
    final = [fit(Dr, sd) for sd in (7, 11, 19)]
    imp = pd.Series(0.0, index=to_X(Dr.head(5)).columns)
    for m_ in final:
        imp += pd.Series(m_.booster_.feature_importance("gain"), index=imp.index)
    imp = (imp / imp.sum() * 100).sort_values(ascending=False)
    b_el, b_la, b_st, beta_src = rabi_betas(np.ones(len(YA), bool))
    clx = cl.set_index("lgd")
    Oc = np.clip(jser(clx.ond_anomaly_json, YEARS), -100, 100); Jc = jser(clx.jjas_anomaly_json, YEARS); TFc = jser(clx.tmax_febmar_anomaly_json, YEARS)
    ci = {l: i for i, l in enumerate(clx.index)}
    SHIP = json.load(open(ART / "districts.json")); SHD = {int(r["lgd"]): r for r in SHIP}
    scored = {l for l, r in SHD.items() if r["data_quality"]["scored"]}
    stt = CY[CY.crop_year >= 2018].groupby("lgd")[["rabi_fg_area_ha", "kharif_fg_area_ha"]].median()
    nyr = CY[CY.crop_year >= 2018].groupby("lgd").rabi_fg_area_ha.apply(lambda x_: int((x_ >= RABI_ELIG_AREA_HA).sum()))     # years with a material rabi crop (season-label gaps, e.g. Odisha, fail this)
    elig = {int(l) for l, r in stt.iterrows() if r.rabi_fg_area_ha >= RABI_ELIG_AREA_HA and r.rabi_fg_area_ha / (r.rabi_fg_area_ha + r.kharif_fg_area_ha) >= RABI_ELIG_SHARE and nyr.get(l, 0) >= RABI_ELIG_YEARS}
    last_r = PAN[PAN.year == 2024].set_index("lgd")
    sets = {"neutral": [y for y in YR if ph.get(y) == "Neutral"], "lanina": [y for y in YR if ph.get(y) == "La Niña"],
            "elnino": [y for y in YR if ph.get(y) == "El Niño"], "elnino_strong": STRONG_YEARS}
    # last observed deviations (crop year 2024) incl. rows without a target
    dr_last = {l: dev_r.get(l, {}).get(2024, np.nan) for l in d0.lgd.values}; dk_last = {l: dev_k.get(l, {}).get(2024, np.nan) for l in d0.lgd.values}
    ndj_by = {sc: float(np.nanmean([ndj.get(y, np.nan) for y in ys])) for sc, ys in sets.items()}
    rows = []
    for l in sorted(scored & elig):
        if l not in ci or l not in LI_:
            continue
        i, s = ci[l], stat.loc[l]
        for sc in RABI_SCEN:
            ys = sets[sc]
            ond = np.nanmean([Oc[i, YEARS.index(y)] for y in ys]); jj = np.nanmean([Jc[i, YEARS.index(y)] for y in ys])
            tf = np.nanmean([TFc[i, YEARS.index(y + 1)] for y in ys])
            an = {"neutral": 0.0, "lanina": b_la[LI_[l]], "elnino": b_el[LI_[l]], "elnino_strong": b_st[LI_[l]]}[sc]
            rows.append(dict(lgd=l, scenario=sc, ond_anomaly_pct=ond, tmax_febmar_anom=tf, jjas_anomaly_pct=jj, oni_ndj=ndj_by[sc],
                             prev_kharif_dev=dk_last.get(l, np.nan), prev_rabi_dev=dr_last.get(l, np.nan), irrigated_share=s.irrigated_share,
                             gw_stress_idx=s.gw_stress_idx, small_marginal_share=s.small_marginal_share, top_crop_share=s.top_crop_share,
                             rabi_share=s.rabi_share, state=s.state, lat=s.lat, lon=s.lon, shock_analog_pct=float(np.clip(an, *SHOCK_CLIP))))
    SXr = pd.DataFrame(rows)
    SXr["shock_lgbm_raw_pct"] = np.mean([m_.predict(to_X(SXr)) for m_ in final], 0)
    # RABI-SPECIFIC: LightGBM predicts the deviation from a lagged trailing trend (mean +5 pp: yields have risen faster than the trend, and prev_rabi_dev is
    # the strongest feature), so its absolute level is not a "shock". The scenario shock is expressed relative to the same district's NEUTRAL-winter prediction
    # (neutral = 0 by construction, like the analog member); the raw prediction is kept in `shock_lgbm_raw_pct`.
    neu = SXr[SXr.scenario == "neutral"].set_index("lgd").shock_lgbm_raw_pct
    SXr["shock_lgbm_pct"] = SXr.shock_lgbm_raw_pct - SXr.lgd.map(neu)
    SXr["shock_tabfm_pct"] = np.nan
    SXr["shock_ensemble_pct"] = W["analog"] * SXr.shock_analog_pct + W["lgbm"] * SXr.shock_lgbm_pct
    SXr["spread_pct"] = (SXr.shock_analog_pct - SXr.shock_lgbm_pct).abs()
    SXr["n_members"] = 2
    OUT = SXr[["lgd", "scenario", "shock_analog_pct", "shock_lgbm_pct", "shock_tabfm_pct", "shock_ensemble_pct", "spread_pct", "n_members", "shock_lgbm_raw_pct"]].copy()
    OUT["lgd"] = OUT.lgd.astype(int); OUT.to_parquet(ART / "ml_ensemble_rabi.parquet", index=False)
    loyo_shift = float(np.nanmean(preds["lgbm"].values))        # pooled mean of the leave-one-year-out LightGBM predictions (level bias removed in the 04_risk rabi hindcast)
    log("[rabi] ml_ensemble_rabi.parquet", OUT.shape, "districts", OUT.lgd.nunique())
    cols_ = ["shock_analog_pct", "shock_lgbm_pct", "shock_lgbm_raw_pct", "shock_ensemble_pct", "spread_pct"]
    meta = dict(season="rabi", generated=pd.Timestamp.now().isoformat(timespec="seconds"), n_rows=int(len(Dr)), n_districts=int(Dr.lgd.nunique()), eval_years=EVAL,
                hindcast_years=RABI_HIND_YEARS, features=RABI_FEATS,
                target="rabi ydev_pct (trailing-10y Theil-Sen deviation of rabi_fg_yield_t_ha, crop year Y = rabi sown Oct Y, harvested Mar Y+1; >= 500 ha rabi foodgrain)",
                weights=W, pooled=pooled, per_year={k: {str(y): v for y, v in d.items()} for k, d in per_year.items()},
                feature_importance_gain_pct={k: round(float(v), 2) for k, v in imp.items()}, lgbm_params=LGB_P,
                versions=dict(lightgbm=lgb.__version__, sklearn=sklearn.__version__, python=sys.version.split()[0]), tabfm={"ok": False, "reason": "not used for rabi (see kharif meta)"},
                hindcast_level_shift_pct=round(loyo_shift, 3), eligibility=dict(min_area_ha=RABI_ELIG_AREA_HA, min_share=RABI_ELIG_SHARE, min_years=RABI_ELIG_YEARS, n_eligible_scored=int(OUT.lgd.nunique())),
                scenario_assumptions=dict(oni_ndj={k: round(v, 2) for k, v in ndj_by.items()}, phase_years={k: v for k, v in sets.items()},
                                          analog="phase beta = mean rabi deviation in phase years minus neutral years (strong: min(El Nino beta, mean of El Nino beta and 2002/09/15 effect)); neutral 0",
                                          prev_deviation="actual 2024 rabi / kharif deviation", beta_source_counts={k: int(v) for k, v in pd.Series(beta_src[[LI_[l] for l in OUT.lgd.unique()]]).value_counts().items()}),
                scenario_summary={sc: {c: float(OUT[OUT.scenario == sc][c].mean()) for c in cols_} for sc in RABI_SCEN}, runtime_s=round(time.time() - t0, 1))
    save_json(meta, ART / "ml_ensemble_rabi_meta.json")
    f_ = lambda x, nd=2: "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"
    L = ["# 04b ML ensemble report - RABI", "",
         f"Target `ydev_pct`: **rabi-season foodgrain yield deviation** (%) from a Theil-Sen trend on the prior 10 crop years (>= 6 obs), clipped +/-100; crop year Y = rabi sown Oct Y, harvested Mar Y+1; "
         f"rabi yield = rabi_fg_yield_t_ha (01_crops: cereals + millets + pulses with season label Rabi, >= {RABI_MIN_AREA_HA} ha). Panel: **{len(Dr):,} district-years** ({Dr.lgd.nunique()} districts, {Dr.year.min()}-{Dr.year.max()}). "
         f"Features ({len(RABI_FEATS)}): {', '.join(RABI_FEATS)}. Climate alignment: OND and JJAS anomalies of year Y, Feb-Mar tmax anomaly of Y+1, ONI NDJ of year Y.", "",
         "Caveat: season labels in APY/UPAG are unreliable in Bihar, Odisha, West Bengal, Assam and Jharkhand (see 01_crops report) - rabi deviations there include label-switch jumps.", "",
         "## Harness", "",
         "Leave-one-year-out 2003-2024 exactly as kharif (the following year is dropped from training because its `prev_rabi_dev` contains the held-out target). `analog` = phase beta: held-out El Nino year -> beta(El Nino) "
         "(mean rabi deviation in El Nino years minus neutral years, recomputed without the held-out year, clipped, state/national-median imputed), La Nina year -> beta(La Nina), neutral year -> 0; no irrigation buffer "
         "(terminal heat hits irrigated wheat). `lgbm` = LightGBM huber, 3-seed mean. TabFM not used. Not a forecasting backtest.", "",
         f"## Pooled results ({len(Dr):,} held-out district-years)", "", "| model | MAE (pp) | pooled rho | mean within-year rho | mean per-year MAE |", "|---|---|---|---|---|"]
    for k in ("analog", "lgbm", "ensemble"):
        v = pooled[k]; L.append(f"| {k} | {f_(v['mae'])} | {f_(v['rho'], 3)} | {f_(v['mean_within_year_rho'], 3)} | {f_(v['mean_year_mae'])} |")
    L += [f"| (predict 0) | {f_(pooled['zero_baseline_mae'])} | - | - | - |", "", f"Ensemble weights (1/MAE): analog {W['analog']:.3f}, lgbm {W['lgbm']:.3f}.", "",
          "## Hindcast crop years", "", "| crop year | phase | n | analog MAE / rho / gap | lgbm MAE / rho / gap | ensemble MAE / rho / gap |", "|---|---|---|---|---|---|"]
    for Y in RABI_HIND_YEARS:
        cells = []
        for k in ("analog", "lgbm", "ensemble"):
            v = per_year[k].get(Y); cells.append("-" if v is None else f"{f_(v['mae'])} / {f_(v['rho'], 3)} / {f_(v['gap'])}")
        L.append(f"| {Y}-{(Y + 1) % 100:02d} | {ph.get(Y)} | {per_year['lgbm'].get(Y, {}).get('n', '-')} | " + " | ".join(cells) + " |")
    L += ["", "## Per-year rho", "", "| crop year | phase | n | analog | lgbm | ensemble |", "|---|---|---|---|---|---|"]
    for Y in EVAL:
        if Y in per_year["lgbm"]:
            L.append(f"| {Y} | {ph.get(Y)} | {per_year['lgbm'][Y]['n']} | " + " | ".join(f_(per_year[k][Y]["rho"], 3) for k in ("analog", "lgbm", "ensemble")) + " |")
    L += ["", "## LightGBM feature importance (gain %)", "", "| feature | gain % |", "|---|---|"] + [f"| {k} | {v:.1f} |" for k, v in imp.items()]
    L += ["", f"## Scenario predictions ({OUT.lgd.nunique()} rabi-eligible scored districts)", "", "| scenario | analog | lgbm (vs neutral) | lgbm raw | ensemble | spread | ONI NDJ | phase years |", "|---|---|---|---|---|---|---|---|"]
    for sc in RABI_SCEN:
        g = OUT[OUT.scenario == sc]
        L.append(f"| {sc} | {f_(g.shock_analog_pct.mean())} | {f_(g.shock_lgbm_pct.mean())} | {f_(g.shock_lgbm_raw_pct.mean())} | {f_(g.shock_ensemble_pct.mean())} | {f_(g.spread_pct.mean())} | {ndj_by[sc]:.2f} | {sets[sc]} |")
    L += ["", "LightGBM scenario shocks are **relative to the same district's neutral-winter prediction** (the raw prediction is the deviation from a lagged trailing trend, mean about +5 pp, dominated by the carried-over "
          "2024 deviation; subtracting the neutral row removes that level and the persistence term so the shock is the climate / ENSO-attributable part, neutral = 0 as for the analog). "
          f"Pooled mean of the leave-one-year-out LightGBM predictions (the level used to de-bias the 04_risk rabi hindcast): {loyo_shift:+.2f} pp."]
    L += ["", "## Honest conclusion", "",
          f"- Pooled MAE: lgbm {f_(pooled['lgbm']['mae'])} pp, analog {f_(pooled['analog']['mae'])} pp, predict-0 {f_(pooled['zero_baseline_mae'])} pp; within-year rank skill rho: lgbm {f_(pooled['lgbm']['mean_within_year_rho'], 3)}, analog {f_(pooled['analog']['mean_within_year_rho'], 3)}.",
          "- Scenario rows are phase-year means of the climate features, so they shrink towards the mean; the ONI NDJ of the 2026-27 event (about +2.5) is outside the training range of any winter, and the strong scenario mainly differs through the analog beta.",
          "- `prev_kharif_dev` / `prev_rabi_dev` in the scenario rows are the last observed (crop year 2024) deviations, not the unobserved 2026 values."]
    (ART / "reports" / "04b_ml_report_rabi.md").write_text("\n".join(L) + "\n")
    log("[rabi] done; report written")


if ARGS.season == "rabi":
    run_rabi()
    sys.exit(0)


PANEL_PATH = ART / "_ml_panel.parquet"
if PANEL_PATH.exists() and not ARGS.refresh_panel:
    PANEL = pd.read_parquet(PANEL_PATH)
else:
    PANEL = build_panel()
    PANEL.to_parquet(PANEL_PATH, index=False)
PANEL["state"] = PANEL["state"].astype(str)
STATES = sorted(PANEL.state.unique())
D = PANEL.dropna(subset=["ydev_pct"]).reset_index(drop=True)
log(f"panel rows {len(PANEL)}, with target {len(D)}, districts {D.lgd.nunique()}, years {D.year.min()}-{D.year.max()}")


def to_X(df: pd.DataFrame) -> pd.DataFrame:
    X = df[FEATS].copy()
    X["state"] = pd.Categorical(X["state"], categories=STATES)
    return X


# ── 2. analog baseline (04_risk formula, betas recomputed leave-year-out) ───────
phase = enso_phase_by_monsoon_year()
LG = sorted(PANEL.lgd.unique()); LI = {l: i for i, l in enumerate(LG)}
STATE_OF = PANEL.drop_duplicates("lgd").set_index("lgd").state.reindex(LG).values
IS_OND = PANEL.drop_duplicates("lgd").set_index("lgd").main_season_ond.reindex(LG).values.astype(bool)
YI = {y: k for k, y in enumerate(range(2000, 2025))}
DEVM = np.full((len(LG), len(YI)), np.nan)          # ydev matrix
AM = np.full((len(LG), len(YI)), np.nan)            # main-season anomaly matrix
for r in PANEL[["lgd", "year", "ydev_pct", "main_anom_pct"]].itertuples():
    DEVM[LI[r.lgd], YI[r.year]] = r.ydev_pct; AM[LI[r.lgd], YI[r.year]] = r.main_anom_pct
cy_ = pd.read_parquet(ART / "crops_latest.parquet"); cy_["lgd"] = cy_.lgd.astype(int)
rain = cy_.set_index("lgd").rainfed_share.reindex(LG).values.astype(float)
sm_ = pd.Series(rain).groupby(STATE_OF).median()
rain = np.where(np.isfinite(rain), rain, pd.Series(STATE_OF).map(sm_).values)
rain = np.where(np.isfinite(rain), rain, np.nanmedian(rain))
MULT = 0.4 + 0.6 * rain
YRS_ALL = np.array(sorted(YI))
EL = np.array([phase.get(y) == "El Niño" for y in YRS_ALL]); NE = np.array([phase.get(y) == "Neutral" for y in YRS_ALL])
DE = np.isin(YRS_ALL, DEFICIT_YEARS)


def _eff(M, a, b, mina=3, minb=3):
    A, B = M[:, a], M[:, b]
    na, nb = np.isfinite(A).sum(1), np.isfinite(B).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        e = np.nanmean(A, 1) - np.nanmean(B, 1)
    return np.where((na >= mina) & (nb >= minb), e, np.nan)


def analog_fold(Y: int):
    """Return predict(year_vector_of_anomalies, is_el) for held-out Y using only other years."""
    keep = YRS_ALL != Y
    el, ne, de = EL & keep, NE & keep, DE & keep
    nde = ~DE & keep
    b_el = _eff(DEVM, np.where(el)[0], np.where(ne)[0]); b_de = _eff(DEVM, np.where(de)[0], np.where(nde)[0])
    b_el = np.where(np.isfinite(b_el), np.clip(b_el, *BETA_CLIP), np.nan)
    b_de = np.where(np.isfinite(b_de), np.clip(b_de, *BETA_CLIP), np.nan)
    beta = np.where(np.isfinite(b_el) & np.isfinite(b_de), (b_el + b_de) / 2, b_el)
    stm = pd.Series(beta).groupby(STATE_OF).agg(["median", "count"]); nat = np.nanmedian(beta)
    for i in np.where(~np.isfinite(beta))[0]:
        st = STATE_OF[i]
        beta[i] = stm.loc[st, "median"] if st in stm.index and stm.loc[st, "count"] >= 3 else nat
    a_el = np.nanmean(AM[:, np.where(el)[0]], 1); a_ne = np.nanmean(AM[:, np.where(ne)[0]], 1)
    return beta, a_el, a_ne


def analog_shock(beta, a_el, a_ne, a_scn, w_el):
    denom = np.minimum(a_el - a_ne, -5.0)
    f = np.maximum(np.clip((a_scn - a_ne) / denom, 0, 2), np.where(IS_OND, 0.0, G_FLOOR) * w_el)
    return np.clip(beta * f * MULT, *SHOCK_CLIP) + 0.0


SHIPPED = json.load(open(ART / "districts.json"))
SH = {int(r["lgd"]): r for r in SHIPPED}
beta_shipped = np.array([(SH[l]["yield_sensitivity"] or {}).get("beta_used_pct") if l in SH else np.nan for l in LG], float)
beta_shipped = np.array([np.nan if v is None else v for v in beta_shipped], float)


# ── 3. models ─────────────────────────────────────────────────────────────────
import lightgbm as lgb
LGB_PARAMS = dict(objective="huber", alpha=15.0, learning_rate=0.04, num_leaves=15, min_child_samples=60, subsample=0.8, subsample_freq=1,
                  colsample_bytree=0.8, reg_lambda=5.0, n_estimators=800, verbose=-1, n_jobs=-1, random_state=7)


def fit_lgbm(Dtr: pd.DataFrame, seed=7):
    yrs = np.array(sorted(Dtr.year.unique())); rng = np.random.default_rng(seed)
    val_y = set(rng.choice(yrs, size=max(2, len(yrs) // 6), replace=False))
    is_val = Dtr.year.isin(val_y).values
    mdl = lgb.LGBMRegressor(**{**LGB_PARAMS, "random_state": seed})
    mdl.fit(to_X(Dtr[~is_val]), Dtr.ydev_pct[~is_val], eval_set=[(to_X(Dtr[is_val]), Dtr.ydev_pct[is_val])], eval_metric="l1",
            categorical_feature=CAT, callbacks=[lgb.early_stopping(60, verbose=False)])
    return mdl


TAB_YEARS = set() if ARGS.tabfm_years == "all" else {int(v) for v in ARGS.tabfm_years.split(",")}
TABFM = dict(ok=False, reason=None, version=None, device="cpu", rows_limit=None, n_estimators=None)
tab_model = None
if ARGS.no_tabfm:
    TABFM["reason"] = "disabled via --no-tabfm"
else:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import sklearn.utils.validation as _v
        if not hasattr(_v, "validate_data"):      # tabfm needs sklearn >= 1.6; env has 1.3 -> minimal shim (check_array + n_features_in_)
            from sklearn.utils import check_array

            def _validate_data(est, X=None, y="no_validation", reset=True, **kw):
                X = check_array(X, **kw)
                if reset:
                    est.n_features_in_ = X.shape[1]
                return X
            _v.validate_data = _validate_data
            TABFM["shim"] = "sklearn.utils.validation.validate_data shim (sklearn %s < 1.6)" % __import__("sklearn").__version__
        import tabfm, torch
        if tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2]) < (2, 1):   # F.scaled_dot_product_attention(scale=) needs torch >= 2.1
            import math, torch.nn.functional as F
            _orig = F.scaled_dot_product_attention

            def _sdpa(q, k, v, attn_mask=None, dropout_p=0.0, is_causal=False, scale=None, **kw):
                if scale is not None:
                    q = q * (scale * math.sqrt(q.shape[-1]))
                return _orig(q, k, v, attn_mask=attn_mask, dropout_p=dropout_p, is_causal=is_causal)
            F.scaled_dot_product_attention = _sdpa
            TABFM["shim_torch"] = f"sdpa(scale=) shim (torch {torch.__version__} < 2.1)"
        from huggingface_hub import try_to_load_from_cache
        _w = try_to_load_from_cache("google/tabfm-1.0.0-pytorch", "regression/model.safetensors")
        if not isinstance(_w, str) and not os.environ.get("TABFM_FORCE_DOWNLOAD"):
            raise RuntimeError("regression weights (google/tabfm-1.0.0-pytorch, 6.6 GB fp32) not fully cached; download ran at ~1.8 MB/s (~1 h) and was stopped at ~3.4 GB; "
                               "set TABFM_FORCE_DOWNLOAD=1 to download. Even with weights, CPU inference of a 3000-row context took > 8 min per fold in a random-init timing test "
                               "(torch 2.0.1, shared CPU), i.e. LOYO over 22 folds exceeds the 15-min budget; use --tabfm-years 2009,2014,2015,2023 --tabfm-rows 1500 on a GPU/newer torch")
        from tabfm import tabfm_v1_0_0_pytorch as _tm, TabFMRegressor
        tab_model = _tm.load(model_type="regression")
        TABFM.update(ok=True, version=f"tabfm {tabfm.__version__} / TabFM v1.0.0 pytorch (torch {torch.__version__})",
                     device=str(next(tab_model.parameters()).device), rows_limit=ARGS.tabfm_rows, n_estimators=ARGS.tabfm_estimators)
        log("TabFM loaded:", TABFM["version"], TABFM["device"])
    except Exception as e:                      # noqa: BLE001
        TABFM["reason"] = f"load failed: {type(e).__name__}: {e}"[:400]
        log("TabFM unavailable:", TABFM["reason"])


def tab_X(df):
    X = df[FEATS].copy()
    X["state"] = X["state"].astype(str)
    return X


def strat_sample(Dtr: pd.DataFrame, n: int, seed=3):
    if len(Dtr) <= n:
        return Dtr
    g = Dtr.groupby(["year", "state"], group_keys=False)
    frac = n / len(Dtr)
    return g.apply(lambda x: x.sample(max(1, int(round(len(x) * frac))), random_state=seed)).sample(frac=1, random_state=seed)


def fit_tabfm(Dtr: pd.DataFrame):
    S = strat_sample(Dtr, ARGS.tabfm_rows)
    reg = TabFMRegressor(model=tab_model, n_estimators=ARGS.tabfm_estimators) if _accepts_nest() else TabFMRegressor(model=tab_model)
    reg.fit(tab_X(S), S.ydev_pct.values)
    return reg


def _accepts_nest():
    import inspect
    return "n_estimators" in inspect.signature(TabFMRegressor.__init__).parameters


# ── 4. LOYO harness ──────────────────────────────────────────────────────────
def metrics(y, p):
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    if len(y) < 10:
        return dict(n=int(len(y)), mae=np.nan, rho=np.nan, gap=np.nan)
    rho = float(spearmanr(p, y)[0]) if np.std(p) > 0 else np.nan
    q1, q2 = np.quantile(p, [1 / 3, 2 / 3])
    worst, best = y[p <= q1], y[p >= q2]       # predicted shock lowest = predicted worst
    gap = float(worst.mean() - best.mean()) if len(worst) and len(best) else np.nan   # negative = model separates correctly (same sign as 04_risk)
    return dict(n=int(len(y)), mae=float(np.mean(np.abs(y - p))), rho=rho, gap=gap)


MODELS = ["analog", "analog_shipped", "lgbm", "tabfm"]
preds = {k: pd.Series(np.nan, index=D.index) for k in MODELS}
tab_fail_folds = 0
for Y in EVAL_YEARS:
    te = D.index[D.year == Y]
    if len(te) == 0:
        continue
    Dtr = D[(D.year != Y) & (D.year != Y + 1)]
    # analog
    beta, a_el, a_ne = analog_fold(Y)
    li = D.loc[te, "lgd"].map(LI).values
    aY = AM[:, YI[Y]]
    w = np.full(len(LG), 1.0 if phase.get(Y) == "El Niño" else 0.0)
    sh = analog_shock(beta, a_el, a_ne, aY, w)
    preds["analog"].loc[te] = sh[li]
    # shipped-beta analog (as 04_risk; beta saw all years incl. Y -> optimistic, reference only)
    bs = np.where(np.isfinite(beta_shipped), beta_shipped, np.nanmedian(beta_shipped))
    sh2 = analog_shock(bs, a_el, a_ne, aY, w)
    preds["analog_shipped"].loc[te] = sh2[li]
    # lgbm (3-seed average)
    ms = [fit_lgbm(Dtr, s) for s in (7, 11, 19)]
    preds["lgbm"].loc[te] = np.mean([m_.predict(to_X(D.loc[te])) for m_ in ms], 0)
    # tabfm
    if TABFM["ok"] and (ARGS.tabfm_years == "all" or Y in TAB_YEARS):
        try:
            t1 = time.time(); reg = fit_tabfm(Dtr)
            preds["tabfm"].loc[te] = reg.predict(tab_X(D.loc[te]))
            log(f"  tabfm fold {Y}: {time.time() - t1:.0f}s")
        except Exception as e:                  # noqa: BLE001
            tab_fail_folds += 1
            TABFM["reason"] = f"fold {Y} failed: {type(e).__name__}: {e}"[:400]
            log("  tabfm fold failed:", TABFM["reason"])
            if tab_fail_folds >= 2:
                TABFM["ok"] = False
    log(f"fold {Y}: n={len(te)} lgbm iters={[m_.best_iteration_ for m_ in ms]}")
TAB_AVAILABLE = preds["tabfm"].notna().sum() > 0
if not TAB_AVAILABLE:
    TABFM["ok"] = False

per_year = {k: {} for k in MODELS}
for k in MODELS:
    for Y in EVAL_YEARS:
        sel = D.year == Y
        if sel.sum() and preds[k][sel].notna().any():
            per_year[k][Y] = metrics(D.ydev_pct[sel].values, preds[k][sel].values)
common = np.ones(len(D), bool)
for k in MODELS:
    if k == "tabfm" and not TAB_AVAILABLE:
        continue
    common &= preds[k].notna().values
CY = sorted(set(D.year[common]))          # years where every member has a held-out prediction


def pool(k, mask, years, P=None):
    P = preds[k] if P is None else P
    pm = metrics(D.ydev_pct.values[mask], P.values[mask])
    pys = {Y: metrics(D.ydev_pct[D.year == Y].values, P[D.year == Y].values) for Y in years}
    rh = [v["rho"] for v in pys.values() if np.isfinite(v["rho"])]
    pm["mean_within_year_rho"] = float(np.mean(rh)) if rh else np.nan
    pm["mean_year_mae"] = float(np.mean([v["mae"] for v in pys.values()]))
    return pm


pooled = {k: pool(k, common, CY) for k in MODELS if not (k == "tabfm" and not TAB_AVAILABLE)}
pooled["zero_baseline_mae"] = float(np.mean(np.abs(D.ydev_pct.values[common])))
pooled["mean_baseline_mae"] = float(np.mean(np.abs(D.ydev_pct.values[common] - D.ydev_pct.values[common].mean())))
allmask = np.ones(len(D), bool)
pooled_all = {k: pool(k, allmask, EVAL_YEARS) for k in ("analog", "analog_shipped", "lgbm")}
pooled_all["zero_baseline_mae"] = float(np.mean(np.abs(D.ydev_pct.values)))
log("pooled(common)", {k: (round(v["mae"], 2), round(v["rho"], 3)) if isinstance(v, dict) else round(v, 2) for k, v in pooled.items()})
log("pooled(all rows)", {k: (round(v["mae"], 2), round(v["rho"], 3)) if isinstance(v, dict) else round(v, 2) for k, v in pooled_all.items()})

# ── 5. weights ──────────────────────────────────────────────────────────────
members = ["analog", "lgbm"] + (["tabfm"] if TAB_AVAILABLE else [])
inv = {k: 1.0 / pooled[k]["mae"] for k in members}
WTS = {k: inv[k] / sum(inv.values()) for k in members}
if not TAB_AVAILABLE:
    WTS["tabfm"] = None
log("weights", WTS)

# ensemble LOYO predictions: weighted mean of the members available for each row
PM = np.column_stack([preds[k].values for k in members]); Wm = np.array([WTS[k] for k in members])
ok_ = np.isfinite(PM)
ens = pd.Series(np.where(ok_, PM, 0) @ Wm / np.where(ok_, Wm[None, :], 0).sum(1), index=D.index)
preds["ensemble"] = ens
# export the leave-one-year-out predictions (consumed by 04_risk.py hindcast + 06_export.py)
_loyo = pd.DataFrame({"lgd": D.lgd.astype(int).values, "year": D.year.astype(int).values, "pred_lgbm": preds["lgbm"].values,
                      "pred_analog": preds["analog"].values, "pred_analog_shipped": preds["analog_shipped"].values,
                      "pred_ensemble": ens.values, "actual": D.ydev_pct.values})
_loyo.to_parquet(ART / "_ml_loyo_preds.parquet", index=False)
per_year["ensemble"] = {Y: metrics(D.ydev_pct[D.year == Y].values, ens[D.year == Y].values) for Y in EVAL_YEARS if (D.year == Y).any()}
pooled["ensemble"] = pool("ensemble", common, CY)
pooled_all["ensemble"] = pool("ensemble", allmask, EVAL_YEARS)

# ── 6. final models + feature importance ────────────────────────────────────
final_lgb = [fit_lgbm(D, s) for s in (7, 11, 19)]
imp = pd.Series(0.0, index=to_X(D.head(5)).columns)
for m_ in final_lgb:
    imp += pd.Series(m_.booster_.feature_importance("gain"), index=imp.index)
imp = (imp / imp.sum() * 100).sort_values(ascending=False)
final_tab = None
if TAB_AVAILABLE:
    try:
        final_tab = fit_tabfm(D)
    except Exception as e:                      # noqa: BLE001
        TABFM["reason"] = f"final fit failed: {type(e).__name__}: {e}"[:400]; TAB_AVAILABLE = False; TABFM["ok"] = False
        WTS = {k: (inv[k] / sum(inv[j] for j in ["analog", "lgbm"]) if k in ("analog", "lgbm") else None) for k in WTS}
        members = ["analog", "lgbm"]

# ── 7. scenario predictions ──────────────────────────────────────────────────
cl = pd.read_parquet(ART / "climate_district.parquet"); cl["lgd"] = cl.lgd.astype(int); cl = cl.set_index("lgd")
els = [y for y in YEARS if phase.get(y) == "El Niño"]
Jc, Oc = jser(cl.jjas_anomaly_json, YEARS), np.clip(jser(cl.ond_anomaly_json, YEARS), -100, 100)
DSc, ONc, TXc, TFc = (jser(cl[c], YEARS) for c in ("dry_spells_json", "onset_day_json", "tmax_jjas_anomaly_json", "tmax_febmar_anomaly_json"))
ci = {l: i for i, l in enumerate(cl.index)}; yc = {y: k for k, y in enumerate(YEARS)}
el_cols = [yc[y] for y in els]
static = PANEL.sort_values("year").groupby("lgd").tail(1).set_index("lgd")
last = D[D.year == 2024].set_index("lgd").ydev_pct
last_all = PANEL[PANEL.year == 2024].set_index("lgd")["ydev_pct"]
enso = json.load(open(ART / "enso_status.json"))
P_MJJ27 = float(enso.get("iri_plume_2026-09-21", {}).get("MJJ2027", {}).get("elnino", P_MJJ27_DEFAULT))
scored = [int(r["lgd"]) for r in SHIPPED if ((r["risk"].get("kharif_2027:elnino") or r["risk"].get("elnino")) or {}).get("expected_yield_shock_pct") is not None]

# ── v4: analog member for the PURE phases, computed here (no dependency on the previous export; v3 read a p(El Nino)=0.61 weighted analog) ──────────────
# Same formula as 04_risk: shock = clip(beta x f x (0.4 + 0.6 x rainfed)), f = max(clip((a_scn - a_neutral) / min(a_elnino - a_neutral, -5), 0, 2), floor x w_el), w_el = 1 for El Nino phases, 0 neutral.
# La Nina (Addendum F flood rule): shock = beta_LaNina (La Nina-year minus neutral-year foodgrain deviation, clipped, state/national-median imputed) only where the
# district's La Nina-year mean main-season rain anomaly > +15 % AND beta_LaNina < 0; otherwise 0 (benign). No irrigation buffer for floods.
# beta incl. the state / national-median imputation 04_risk applies (districts.json `yield_sensitivity` is null for ~65 scored districts without their own El Nino effect)
_RD = json.load(open(ART / "risk_district.json"))
beta_shipped = np.array([np.nan if (_RD.get(str(l)) or {}).get("beta_used_pct") is None else float(_RD[str(l)]["beta_used_pct"]) for l in LG], float)
cidx = np.array([ci[l] for l in LG])
A_lg = np.where(IS_OND[:, None], Oc[cidx], Jc[cidx])
ne_cols = [yc[y] for y in YEARS if phase.get(y) == "Neutral"]; la_cols = [yc[y] for y in YEARS if phase.get(y) == "La Niña"]
a_el_, a_ne_, a_la_ = (np.nanmean(A_lg[:, c_], 1) for c_ in (el_cols, ne_cols, la_cols)); a_st_ = np.nanmean(A_lg[:, [yc[y] for y in (2002, 2009, 2015)]], 1)
den_ = np.minimum(a_el_ - a_ne_, -5.0)
def _frac(a_scn, w):
    return np.maximum(np.clip((a_scn - a_ne_) / den_, 0, 2), np.where(IS_OND, 0.0, G_FLOOR) * w)
la_y = np.where(np.isin(YRS_ALL, [y for y in YRS_ALL if phase.get(y) == "La Niña"]))[0]; ne_y = np.where(NE)[0]
b_la_raw = _eff(DEVM, la_y, ne_y); b_la_raw = np.where(np.isfinite(b_la_raw), np.clip(b_la_raw, *BETA_CLIP), np.nan)
_sm = pd.Series(b_la_raw).groupby(STATE_OF).agg(["median", "count"]); _nat = np.nanmedian(b_la_raw); b_la_ = b_la_raw.copy()
for _i in np.where(~np.isfinite(b_la_))[0]:
    _s = STATE_OF[_i]; b_la_[_i] = _sm.loc[_s, "median"] if _s in _sm.index and _sm.loc[_s, "count"] >= 3 else _nat
FLOOD = (a_la_ > FLOOD_THR) & (b_la_ < 0)
ANALOG_K = {"neutral": np.clip(beta_shipped * _frac(a_ne_, 0.0) * MULT, *SHOCK_CLIP) + 0.0,
            "elnino": np.clip(beta_shipped * _frac(a_el_, 1.0) * MULT, *SHOCK_CLIP) + 0.0,
            "elnino_strong": np.clip(beta_shipped * _frac(a_st_, 1.0) * MULT, *SHOCK_CLIP) + 0.0,
            "lanina": np.where(FLOOD, np.clip(b_la_, *SHOCK_CLIP), 0.0)}
log(f"analog (pure phases): La Nina flood-flagged districts {int(FLOOD[np.isfinite(beta_shipped)].sum())} of {int(np.isfinite(beta_shipped).sum())} scored; "
    f"mean analog shock " + ", ".join(f"{k} {np.nanmean(v[np.isfinite(beta_shipped)]):.2f}" for k, v in ANALOG_K.items()))
rows = []
for l in scored:
    if l not in ci or l not in static.index:
        continue
    i = ci[l]; s = static.loc[l]; ond = bool(s.main_season_ond); c = cl.loc[l]
    for sc in SCEN_K:
        if sc == "neutral":
            jj = c.neutral_mean_anomaly_pct
        elif sc == "elnino":
            jj = c.elnino_mean_anomaly_pct
        elif sc == "lanina":
            jj = c.lanina_mean_anomaly_pct
        else:
            jj = c.strong_elnino_anomaly_pct
        if sc == "neutral":
            dsv, onv, txv, tfv = (np.nanmean(M[i, ne_cols]) for M in (DSc, ONc, TXc, TFc))
            ov = np.nanmean(Oc[i, ne_cols])
        elif sc == "lanina":
            dsv, onv, txv, tfv = (np.nanmean(M[i, la_cols]) for M in (DSc, ONc, TXc, TFc))
            ov = np.nanmean(Oc[i, la_cols])
        else:
            dsv, onv, txv, tfv = (np.nanmean(M[i, el_cols]) for M in (DSc, ONc, TXc, TFc))
            ov = np.nanmean(Oc[i, el_cols])
        # for the strong scenario use the 2002/2009/2015 analog mean for the OND anomaly as well
        if sc == "elnino_strong":
            ov = np.nanmean(Oc[i, [yc[y] for y in (2002, 2009, 2015)]])
        main = ov if ond else jj
        if ond and sc != "neutral":
            main = ov
        rows.append(dict(lgd=l, scenario=sc, jjas_anomaly_pct=jj, ond_anomaly_pct=ov, main_anom_pct=main, dry_spells=dsv, onset_day=onv,
                         tmax_jjas_anom=txv, tmax_febmar_anom=tfv, oni_jja_son=ONI_SCN[sc], prev_year_ydev=last_all.get(l, np.nan),
                         irrigated_share=s.irrigated_share, simpson_div=s.simpson_div, top_crop_share=s.top_crop_share,
                         small_marginal_share=s.small_marginal_share, gw_stress_idx=s.gw_stress_idx, state=s.state,
                         main_season_ond=int(ond), lat=s.lat, lon=s.lon))
SX = pd.DataFrame(rows)
# present-day structure (latest simpson / top-crop share) rather than the 2024-row values
ld = pd.read_parquet(ART / "crops_latest.parquet"); ld["lgd"] = ld.lgd.astype(int); ld = ld.set_index("lgd")
for c in ("simpson_div", "top_crop_share", "irrigated_share", "small_marginal_share"):
    v = SX.lgd.map(ld[c]); SX[c] = v.where(v.notna(), SX[c])
SX["shock_lgbm_pct"] = np.mean([m_.predict(to_X(SX)) for m_ in final_lgb], 0)
SX["shock_tabfm_pct"] = np.nan
if final_tab is not None:
    try:
        SX["shock_tabfm_pct"] = final_tab.predict(tab_X(SX))
    except Exception as e:                      # noqa: BLE001
        TABFM["reason"] = f"scenario predict failed: {type(e).__name__}: {e}"[:400]; TAB_AVAILABLE = False; TABFM["ok"] = False
        members = ["analog", "lgbm"]
        WTS = {k: (inv[k] / sum(inv[j] for j in members) if k in members else None) for k in ("analog", "lgbm", "tabfm")}
# since 04_risk v3 `expected_yield_shock_pct` holds the ENSEMBLE; the pure analog value lives in `expected_yield_shock_analog_pct` (falls back for pre-v3 exports)
SX["shock_analog_pct"] = [float(ANALOG_K[sc][LI[l]]) for l, sc in zip(SX.lgd, SX.scenario)]
def _prev_analog(l, sc):
    if sc not in ("neutral", "elnino_strong"):
        return np.nan
    v = (SH[l]["risk"].get(sc) or {}).get("expected_yield_shock_analog_pct")
    return np.nan if v is None else float(v)
_old_an = np.array([_prev_analog(l, sc) for l, sc in zip(SX.lgd, SX.scenario)], float)
if np.isfinite(_old_an).any():
    _m = np.isfinite(_old_an); log(f"analog self-check vs previous export (neutral / strong rows): max |diff| {np.nanmax(np.abs(_old_an[_m] - SX.shock_analog_pct.values[_m])):.3f} pp")
mem_cols = {"analog": "shock_analog_pct", "lgbm": "shock_lgbm_pct", "tabfm": "shock_tabfm_pct"}
active = [k for k in members if SX[mem_cols[k]].notna().any()]
W = np.array([WTS[k] for k in active]); W = W / W.sum()
V = SX[[mem_cols[k] for k in active]].values
wv = np.where(np.isfinite(V), W[None, :], 0.0)
SX["shock_ensemble_pct"] = np.nansum(np.where(np.isfinite(V), V, 0) * wv, 1) / wv.sum(1)
SX["spread_pct"] = np.nanmax(V, 1) - np.nanmin(V, 1)
SX["n_members"] = np.isfinite(V).sum(1)
# La Nina gate (Addendum F): ensemble = 0 (benign) outside flood-flagged districts; inside, capped at <= 0 (it is an excess-water loss scenario)
SX["flood_flag"] = np.nan
_ml = (SX.scenario == "lanina").values
_fl = np.array([bool(FLOOD[LI[l]]) for l in SX.lgd[_ml]])
SX.loc[_ml, "flood_flag"] = _fl.astype(float)
SX.loc[_ml, "shock_ensemble_pct"] = np.where(_fl, np.minimum(SX.loc[_ml, "shock_ensemble_pct"].values, 0.0), 0.0)
OUT = SX[["lgd", "scenario", "shock_analog_pct", "shock_lgbm_pct", "shock_tabfm_pct", "shock_ensemble_pct", "spread_pct", "n_members", "flood_flag"]].copy()
OUT["lgd"] = OUT.lgd.astype(int)
OUT.to_parquet(ART / "ml_ensemble.parquet", index=False)
log("ml_ensemble.parquet", OUT.shape)
summ = OUT.groupby("scenario")[["shock_analog_pct", "shock_lgbm_pct", "shock_tabfm_pct", "shock_ensemble_pct", "spread_pct"]].agg(["mean", "median"]).round(2)
corr = {sc: {k: float(spearmanr(g.shock_analog_pct, g[k], nan_policy="omit")[0]) for k in ("shock_lgbm_pct", "shock_tabfm_pct") if g[k].notna().any()}
        for sc, g in OUT.groupby("scenario")}

# ── 8. meta + report ─────────────────────────────────────────────────────────
import sklearn
meta = dict(generated=pd.Timestamp.now().isoformat(timespec="seconds"), n_rows=int(len(D)), n_districts=int(D.lgd.nunique()),
            eval_years=EVAL_YEARS, hindcast_years=HIND_YEARS, features=FEATS, target="ydev_pct (trailing-10y Theil-Sen foodgrain yield deviation %, == 04_risk.actual_dev)",
            weights=WTS, pooled={k: v for k, v in pooled.items()}, pooled_all_rows=pooled_all, tabfm_eval_years=CY, per_year={k: {str(y): v for y, v in d.items()} for k, d in per_year.items()},
            feature_importance_gain_pct={k: round(float(v), 2) for k, v in imp.items()}, lgbm_params=LGB_PARAMS,
            versions=dict(lightgbm=lgb.__version__, sklearn=sklearn.__version__, python=sys.version.split()[0]), tabfm=TABFM,
            scenario_assumptions=dict(oni=ONI_SCN, p_elnino_mjj27=P_MJJ27, analog="pure phases (El Nino p=1); La Nina = flood rule (anomaly > +15 % and beta_LaNina < 0, else 0); ensemble La Nina gated the same way", flood_flagged_districts=int(np.nansum(OUT[OUT.scenario == "lanina"].flood_flag)), prev_year_ydev="actual 2024 deviation", n_scored=int(OUT.lgd.nunique())),
            scenario_summary={sc: {c: float(OUT[OUT.scenario == sc][c].mean()) for c in ["shock_analog_pct", "shock_lgbm_pct", "shock_tabfm_pct", "shock_ensemble_pct", "spread_pct"] if OUT[OUT.scenario == sc][c].notna().any()} for sc in SCEN_K},
            rank_corr_with_analog=corr, common_rows_for_pooled=int(common.sum()), runtime_s=round(time.time() - T0, 1))
save_json(meta, ART / "ml_ensemble_meta.json")


def f(x, nd=2):
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


L = ["# 04b ML ensemble report", "",
     f"Target `ydev_pct`: foodgrain yield deviation (%) from a Theil-Sen trend fitted on the prior 10 crop years (>= 6 obs), clipped +/-100 -- identical to the 04_risk hindcast `actual_dev`. "
     f"Panel: **{len(D):,} district-years** ({D.lgd.nunique()} districts, {D.year.min()}-{D.year.max()}; no target before 2003 because the trend needs 6 prior years from 1997, so the 2002 fold is empty). "
     f"Features ({len(FEATS)}): {', '.join(FEATS)} (`main_anom_pct` = the district's main-season anomaly, OND for TN/Puducherry/Nellore/Chittoor/Prakasam, added so the ML models see the same driver as the analog).", "",
     "## Harness", "",
     "Leave-one-year-out over 2003-2024 (held-out year predicted by a model trained on all other years, except Y+1 which is dropped because its `prev_year_ydev` feature contains Y's target). "
     "This is **not** a forecasting backtest: training includes future years, which is the right design for 'does the model generalise to an unseen monsoon' but flatters models that learn secular structure. "
     "`analog` = 04_risk formula `clip(beta x f x (0.4+0.6 rainfed))` with beta, El Nino/neutral anomaly means recomputed excluding the held-out year (from this same ydev panel, so betas are noisier than the shipped ones: ydev starts 2003 -> El Nino years 2004/06/09/15/18/23). "
     "`analog_shipped` uses the shipped `beta_used_pct` (computed on all years incl. the held-out one: **optimistic/leaky**, reference only). `lgbm` = LightGBM huber, 3-seed mean, early stopping on 1/6 of training years held out. "
     f"`tabfm` = TabFM zero-shot regression" + (f" (training table subsampled to {TABFM['rows_limit']} rows per fold, stratified by year x state; n_estimators={TABFM['n_estimators']}; CPU)." if TAB_AVAILABLE else f" -- **NOT AVAILABLE**: {TABFM['reason']}"), "",
     "Sign conventions: rho = Spearman(predicted shock, actual deviation), **positive = good**; tercile gap = mean actual dev of worst-predicted tercile minus best-predicted tercile, **negative = good** (same sign as 04_risk's top-minus-bottom).", "",
     f"## Pooled results ({int(common.sum()):,} held-out district-years from {len(CY)} folds ({CY[0]}-{CY[-1]}) where every member has a prediction)", "",
     "| model | MAE (pp) | pooled rho | mean within-year rho | mean per-year MAE |", "|---|---|---|---|---|"]
for k in ["analog", "analog_shipped", "lgbm", "tabfm", "ensemble"]:
    if k in pooled:
        v = pooled[k]; L.append(f"| {k} | {f(v['mae'])} | {f(v['rho'], 3)} | {f(v['mean_within_year_rho'], 3)} | {f(v['mean_year_mae'])} |")
L += [f"| (predict 0) | {f(pooled['zero_baseline_mae'])} | - | - | - |", f"| (predict global mean) | {f(pooled['mean_baseline_mae'])} | - | - | - |", ""]
if len(CY) < len(EVAL_YEARS):
    L += [f"All {len(D):,} rows / {len(EVAL_YEARS)} folds, models without the TabFM CPU restriction:", "", "| model | MAE (pp) | pooled rho | mean within-year rho |", "|---|---|---|---|"]
    for k in ["analog", "analog_shipped", "lgbm", "ensemble"]:
        v = pooled_all[k]; L.append(f"| {k} | {f(v['mae'])} | {f(v['rho'], 3)} | {f(v['mean_within_year_rho'], 3)} |")
    L += [f"| (predict 0) | {f(pooled_all['zero_baseline_mae'])} | - | - |", ""]
L += ["## Hindcast years (the 4 years 04_risk reports)", "", "| year | phase | n | " + " | ".join(f"{k} MAE / rho / gap" for k in ["analog", "lgbm", "tabfm", "ensemble"]) + " |", "|---|---|---|---|---|---|---|"]
for Y in HIND_YEARS:
    cells = []
    for k in ["analog", "lgbm", "tabfm", "ensemble"]:
        v = per_year.get(k, {}).get(Y)
        cells.append("-" if (v is None or (k in ("tabfm",) and not TAB_AVAILABLE)) else f"{f(v['mae'])} / {f(v['rho'], 3)} / {f(v['gap'])}")
    n = per_year["lgbm"][Y]["n"]
    L.append(f"| {Y} | {phase.get(Y)} | {n} | " + " | ".join(cells) + " |")
L += ["", "## Per-year rho (all folds)", "", "| year | phase | n | analog | analog_shipped | lgbm | tabfm | ensemble |", "|---|---|---|---|---|---|---|---|"]
for Y in EVAL_YEARS:
    if Y not in per_year["lgbm"]:
        continue
    L.append(f"| {Y} | {phase.get(Y)} | {per_year['lgbm'][Y]['n']} | " + " | ".join(f(per_year[k].get(Y, {}).get('rho'), 3) for k in ["analog", "analog_shipped", "lgbm", "tabfm", "ensemble"]) + " |")
L += ["", "## Per-year MAE", "", "| year | analog | lgbm | tabfm | ensemble |", "|---|---|---|---|---|"]
for Y in EVAL_YEARS:
    if Y in per_year["lgbm"]:
        L.append(f"| {Y} | " + " | ".join(f(per_year[k].get(Y, {}).get('mae')) for k in ["analog", "lgbm", "tabfm", "ensemble"]) + " |")
L += ["", "## LightGBM feature importance (gain %, final model on all years, 3-seed sum)", "", "| feature | gain % |", "|---|---|"]
L += [f"| {k} | {v:.1f} |" for k, v in imp.items()]
L += ["", "## Ensemble weights", "", "| member | weight (proportional to 1/pooled MAE) |", "|---|---|"]
L += [f"| {k} | {f(WTS[k], 3) if WTS.get(k) is not None else 'null (unavailable)'} |" for k in ["analog", "lgbm", "tabfm"]]
L += ["", "## Scenario predictions (today)", "", f"{OUT.lgd.nunique()} scored districts x 4 scenarios (v4: analog member = pure phases, El Nino p = 1; `lanina` follows the flood rule: analog = beta_LaNina only where La Nina-year rain > +15 % and beta_LaNina < 0, "
      f"ensemble gated the same way - {int(np.nansum(OUT[OUT.scenario == 'lanina'].flood_flag))} flood-flagged districts). Mean shock % and member spread:", "",
      "| scenario | analog | lgbm | tabfm | ensemble | spread |", "|---|---|---|---|---|---|"]
for sc in SCEN_K:
    g = OUT[OUT.scenario == sc]
    L.append(f"| {sc} | " + " | ".join(f(g[c].mean()) for c in ["shock_analog_pct", "shock_lgbm_pct", "shock_tabfm_pct", "shock_ensemble_pct", "spread_pct"]) + " |")
L += ["", "Rank correlation of analog with other members across districts: " + json.dumps({k: {a: round(b, 3) for a, b in v.items()} for k, v in corr.items()}), ""]
L += ["## Honest conclusion", ""]
best_mae = min(members, key=lambda k: pooled[k]["mae"]); best_rho = max(members, key=lambda k: pooled[k]["mean_within_year_rho"])
L += [f"- Pooled MAE: best = **{best_mae}** ({f(pooled[best_mae]['mae'])} pp) vs analog {f(pooled['analog']['mae'])} pp, predict-0 {f(pooled['zero_baseline_mae'])} pp. "
      f"Within-year ranking (what the risk score needs): best mean rho = **{best_rho}** ({f(pooled[best_rho]['mean_within_year_rho'], 3)}) vs analog {f(pooled['analog']['mean_within_year_rho'], 3)}.",
      "- ML members see year-specific weather (dry spells, onset, heat, previous-year yield) and the district's static structure, so they can rank districts within a year; the analog uses one anomaly and a fixed per-district beta and is blind to everything else. "
      "The ML advantage is largest where the analog's beta is noisy (few El Nino years, 6 in the ydev panel).",
      "- Caveats: (1) LOYO trains on future years (not a true forecast skill estimate); (2) yield deviation is noisy and partially reporting-error driven (clip +/-100), so absolute MAE floors are high; "
      "(3) scenario rows are synthetic composites (El Nino-year mean dry spells/onset/tmax, ONI +1.5/+2.2) that average out year-specific extremes, so ML scenario shocks are shrunk towards the mean vs. any real year; "
      "(4) the ML models extrapolate `oni_jja_son`=2.2 using only 2015/2023 (~1.0-2.0) so strong scenario is mostly the rainfall-anomaly channel; (5) the analog n=719 scored districts, ML trained on all districts with a target; "
      "(6) trailing Theil-Sen detrending means a target year following a drop has an inflated deviation (mean reversion) which prev_year_ydev partly exploits -- it is a legitimate predictor but not climate-driven.",
      f"- Sample sizes: {len(D):,} train rows overall, ~{int(len(D) / len(EVAL_YEARS))} per held-out year, hindcast years n = {', '.join(str(per_year['lgbm'][y]['n']) for y in HIND_YEARS)}."]
if not TAB_AVAILABLE:
    L.append(f"- TabFM: unavailable ({TABFM['reason']}); `tabfm` slot is null and ensemble = analog + lgbm.")
(ART / "reports" / "04b_ml_report.md").write_text("\n".join(L) + "\n")
log("done; report written")
