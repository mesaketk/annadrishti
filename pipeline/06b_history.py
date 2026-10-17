"""06b_history.py - AnnaDrishti History mode artifacts (SCHEMA Addendum H).

Outputs
  artifacts/history/index.json     {years, enso{year: headline block}, band_thresholds, ond_scored_lgds, nfhs_rounds, method}
  artifacts/history/{year}.json    {year, enso{...}, nfhs_round, districts{lgd: {...}}}   for every year 2003-2024 (<= 150 KB each)

Per district-year: rain_anom_pct (JJAS), ond_anom_pct, yield_dev_pct (actual foodgrain yield vs trailing 10-yr Theil-Sen trend),
tool_score / tool_band (the hindcast score), lgbm_oos_shock_pct (leave-one-year-out LightGBM, 04b), warned, nfhs_round, stunting, underweight.

tool_score = the SAME formula as the 04_risk.py hindcast, extended from 4 to all years 2003-2024: that year's actual main-season
anomaly (JJAS; OND for Tamil Nadu / Puducherry / coastal-AP OND districts) is the scenario, the previous year's anomaly is the antecedent term,
structural terms (sensitivity S, capacity C, price term) are AS OF TODAY, no live NDVI. Bands use artifacts/kpis.json band_thresholds.

04_risk.py is a top-level script (reads inputs, writes artifacts) and cannot be imported. To stay in lock-step with the live model WITHOUT
editing it, this script executes ONLY the prefix of 04_risk.py that precedes its "6. drivers" section (inputs -> shocks -> S/C/exposure helpers;
no file writes happen in that prefix) in a private namespace, and re-implements the ~15 lines of the hindcast loop + actual_dev() here.
If 04_risk.py's structure changes so that the marker or the names below disappear, this script fails loudly (assertions) rather than drifting.

Run: python3 pipeline/06b_history.py     (after 04_risk.py / 04b; no network, < 1 min)
"""
from __future__ import annotations
import json, sys, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import theilslopes

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import ART, save_json, oni  # noqa: E402

T0 = time.time()
HIST_YEARS = list(range(2003, 2025))
OUT = ART / "history"
MAX_BYTES = 150_000          # decimal KB, conservative
MARKER = "# ── 6. drivers"
NFHS = {4: ("NFHS-4 (2015-16)", "nfhs4"), 5: ("NFHS-5 (2019-21)", "nfhs5"), 6: ("NFHS-6 (2023-24)", "nfhs6")}


def log(*a):
    print(f"[{time.time() - T0:5.1f}s]", *a, flush=True)


# ── 1. run the 04_risk.py prefix (structural terms + scoring helpers) ─────────────────────────────────────────────
src = (HERE / "04_risk.py").read_text()
assert MARKER in src, f"marker {MARKER!r} not found in 04_risk.py - update 06b_history.py"
ns: dict = {"__name__": "risk_prefix", "__file__": str(HERE / "04_risk.py")}
exec(compile(src.split(MARKER)[0], str(HERE / "04_risk.py"), "exec"), ns)
need = ["df", "N", "A", "O", "J", "yidx", "phase", "elig", "beta", "mult", "S_val", "C_val", "P_el", "P_neu", "is_ond",
        "frac", "exposure_terms", "combine", "top_level", "zrank", "SHOCK_CLIP", "panel", "YEARS"]
missing = [k for k in need if k not in ns]
assert not missing, f"04_risk.py prefix no longer defines {missing} - update 06b_history.py"
df, N, A, O, J, yidx, phase, elig = (ns[k] for k in ("df", "N", "A", "O", "J", "yidx", "phase", "elig"))
beta, mult, S_val, C_val, P_el, P_neu, is_ond = (ns[k] for k in ("beta", "mult", "S_val", "C_val", "P_el", "P_neu", "is_ond"))
frac, exposure_terms, combine, top_level, zrank = (ns[k] for k in ("frac", "exposure_terms", "combine", "top_level", "zrank"))
SHOCK_CLIP, panel = ns["SHOCK_CLIP"], ns["panel"]
lgds = df.lgd.astype(int).values
log("04_risk prefix executed;", N, "districts,", int(elig.sum()), "scored")

# ── 2. band thresholds (published, kpis.json) ─────────────────────────────────────────────────────────────────────
bt = json.load(open(ART / "kpis.json"))["band_thresholds"]
T_LO, T_HI = float(bt["low_below"]), float(bt["high_from"])
def band_of(x):
    return np.where(~np.isfinite(x), "", np.where(x >= T_HI, "high", np.where(x >= T_LO, "medium", "low")))

# ── 3. actual yield deviation (identical to 04_risk.actual_dev) ───────────────────────────────────────────────────
piv = panel.pivot_table(index="lgd", columns="crop_year", values="foodgrain_yield_t_ha", aggfunc="first")
prod_piv = panel.pivot_table(index="lgd", columns="crop_year", values="foodgrain_prod_t", aggfunc="first")
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

# ── 4. LOYO LightGBM, climate timeseries, nfhs, weights ───────────────────────────────────────────────────────────
loyo = pd.read_parquet(ART / "_ml_loyo_preds.parquet")
loyo_l = loyo.pivot_table(index="lgd", columns="year", values="pred_lgbm", aggfunc="first")
ts_rain = {}                                     # lgd -> {year: jjas anomaly %} from artifacts/timeseries_climate (02_climate)
ts_mm = {}                                       # lgd -> {year: JJAS rainfall mm}
for l in lgds:
    p = ART / "timeseries_climate" / f"{l}.json"
    if p.exists():
        _t = json.load(open(p))
        ts_rain[int(l)] = {int(k): v for k, v in (_t.get("jjas_anomaly_pct") or {}).items() if v is not None}
        ts_mm[int(l)] = {int(k): v for k, v in (_t.get("rain_jjas_mm") or {}).items() if v is not None}
_cl = pd.read_parquet(ART / "crops_latest.parquet"); _cl["lgd"] = _cl.lgd.astype(int)
gca = _cl.set_index("lgd").gross_cropped_area_ha.reindex(lgds).values.astype(float)
chk = np.nanmax([abs(ts_rain.get(int(l), {}).get(2015, np.nan) - J[i, yidx[2015]]) for i, l in enumerate(lgds)])
log(f"timeseries_climate vs climate_district JJAS 2015 max diff: {chk:.2f} pp")

oni_df = oni()

def aia_anom(Y):
    """All-India JJAS anomaly (%): gross-cropped-area-weighted mean JJAS rainfall (mm) of Y vs the same weighted series' 2000-2024 mean
    (same definition as artifacts/reports/02_climate_report.md, i.e. comparable to IMD's all-India figure; NOT a mean of district percentages)."""
    def wmean(y):
        v = np.array([ts_mm.get(int(l), {}).get(y, np.nan) for l in lgds], float)
        ok = np.isfinite(gca) & np.isfinite(v)
        return float(np.average(v[ok], weights=gca[ok]))
    normal = float(np.mean([wmean(y) for y in range(2000, 2025)]))
    return 100 * (wmean(Y) / normal - 1)

def oni_jja_son(y):
    s = oni_df[(oni_df.yr == y) & oni_df.seas.isin(["JJA", "JAS", "ASO", "SON"])]["anom"]
    return float(s.mean()) if len(s) else None

def nfhs_round_for(y):
    return 4 if y <= 2017 else (5 if y <= 2021 else 6)

def r1(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 1) + 0.0

def headline(ph, anom, dev):
    cat = "Deficit" if anom <= -10 else ("Excess" if anom >= 10 else "Near-normal")
    sgn = lambda v: f"{v:+.0f}".replace("-", "−")
    s = f"{cat} monsoon ({sgn(anom)} %) " + ("under " + ph if ph in ("El Niño", "La Niña") else "in a Neutral ENSO year")
    return s + (f"; foodgrain yields {sgn(dev)} % vs trend" if dev is not None else "")

# ── 5. per-year hindcast ──────────────────────────────────────────────────────────────────────────────────────────
OUT.mkdir(parents=True, exist_ok=True)
index_enso, summary = {}, []
for Y in HIST_YEARS:
    aY = A[:, yidx[Y]]; ant = zrank(-A[:, yidx[Y - 1]])
    ph = phase.get(Y)
    fY = frac(aY, np.where(ph == "El Niño", 1.0, 0.0) * np.ones(N))
    shY = np.where(elig, np.clip(beta * fY * mult, *SHOCK_CLIP) + 0.0, np.nan)
    lsY = np.where(np.isfinite(shY), np.maximum(0, -shY), np.nan)
    dfY = {"El Niño": P_el, "Neutral": P_neu}.get(ph, P_neu)
    t = exposure_terms(lsY, np.where(elig, dfY, np.nan), ant, with_live=False)
    E_Y, _, _ = combine(t)
    tl, _ = top_level(E_Y, S_val, C_val)
    score = np.where(elig, 100 * tl, np.nan)
    band = band_of(score)
    dev = np.array([actual_dev(int(l), Y) for l in lgds])
    rj = np.array([ts_rain.get(int(l), {}).get(Y, np.nan) for l in lgds], float)
    ro = np.where(is_ond & np.isfinite(O[:, yidx[Y]]), O[:, yidx[Y]], np.nan)   # OND anomaly kept only for OND-season districts (size budget)
    lg = np.array([float(loyo_l.at[l, Y]) if (l in loyo_l.index and Y in loyo_l.columns) else np.nan for l in lgds])
    rnd = nfhs_round_for(Y); rlabel, rkey = NFHS[rnd]
    stunt = df[f"stunting_{rkey}"].values.astype(float); uw = df[f"underweight_{rkey}"].values.astype(float)

    aia = aia_anom(Y)
    pw = np.array([prod_piv.at[l, Y] if (l in prod_piv.index and Y in prod_piv.columns) else np.nan for l in lgds], float)
    ok_y = np.isfinite(dev) & np.isfinite(pw) & (pw > 0)
    ydev = float(np.average(dev[ok_y], weights=pw[ok_y])) if ok_y.any() else None
    warned = np.isin(band, ["medium", "high"]) & np.isfinite(dev) & (dev <= -5)
    loss_ok = np.isfinite(dev) & (dev <= -5) & (band != "")
    n_loss = int(loss_ok.sum()); n_hit = int((warned & loss_ok).sum())
    o = oni_jja_son(Y)
    enso = {"phase": ph, "oni_jja_son": None if o is None else round(o, 2),
            "all_india_jjas_anom_pct": round(aia, 1),
            "yield_dev_pct": r1(ydev),
            "headline": headline(ph, round(aia, 1), r1(ydev)),
            "n_loss_districts": n_loss, "n_loss_warned": n_hit,
            "pct_loss_warned": round(100 * n_hit / n_loss, 1) if n_loss else None}
    enso = {k: v for k, v in enso.items() if v is not None}

    dists = {}
    for i, l in enumerate(lgds):
        rec = {"rain_anom_pct": r1(rj[i]), "ond_anom_pct": r1(ro[i]), "yield_dev_pct": r1(dev[i]),
               "tool_score": r1(score[i]), "tool_band": band[i] or None, "lgbm_oos_shock_pct": r1(lg[i]),
               "warned": (bool(warned[i]) if (band[i] and np.isfinite(dev[i])) else None),
               "nfhs_round": rlabel if (np.isfinite(stunt[i]) or np.isfinite(uw[i])) else None,
               "stunting": r1(stunt[i]), "underweight": r1(uw[i])}
        rec = {k: v for k, v in rec.items() if v is not None}
        if rec:
            dists[str(int(l))] = rec
    obj = {"year": Y, "enso": enso, "districts": dists}
    path = OUT / f"{Y}.json"
    save_json(obj, path)
    size = path.stat().st_size
    if size > MAX_BYTES:                         # shave the largest redundant text field, then re-check
        for d in dists.values():
            d.pop("nfhs_round", None)
        obj["nfhs_round"] = rlabel
        save_json(obj, path); size = path.stat().st_size
        log(f"{Y}: over budget, moved nfhs_round to year level -> {size} B")
    assert size <= MAX_BYTES, f"{path} is {size} bytes > {MAX_BYTES}"
    index_enso[str(Y)] = enso
    summary.append((Y, ph, enso["all_india_jjas_anom_pct"], enso.get("yield_dev_pct"), n_loss, n_hit, enso.get("pct_loss_warned"), size, len(dists)))
    log(f"{Y} {ph:8s} anom {aia:+6.1f}  ydev {ydev if ydev is None else round(ydev, 1)}  loss {n_loss} warned {n_hit}  {size / 1024:.1f} KB")

index = {"years": HIST_YEARS, "enso": index_enso,
         "band_thresholds": {"low_below": T_LO, "high_from": T_HI},
         "ond_scored_lgds": [int(l) for l in lgds[is_ond]],
         "nfhs_rounds": {"2003-2017": NFHS[4][0], "2018-2021": NFHS[5][0], "2022-2024": NFHS[6][0]},
         "method": ("tool_score = 04_risk hindcast formula with that year's actual main-season rainfall anomaly (JJAS; OND for ond_scored_lgds) as the scenario; "
                    "structural terms (sensitivity, capacity, price) as of today, no live NDVI; bands from kpis.json band_thresholds. "
                    "yield_dev_pct = actual foodgrain yield vs trailing 10-year Theil-Sen trend. warned = band in (medium, high) and yield_dev_pct <= -5. "
                    "lgbm_oos_shock_pct = leave-one-year-out LightGBM (04b). all_india_jjas_anom_pct = gross-cropped-area-weighted JJAS rainfall (mm) vs its 2000-2024 mean (same definition as 02_climate report); "
                    "all-India yield_dev_pct weighted by that year's foodgrain production; oni_jja_son = mean ONI JJA..SON; phase = monsoon-year ENSO phase (mean ONI JJA..OND).")}
save_json(index, OUT / "index.json")
log("wrote", OUT, "index.json", (OUT / "index.json").stat().st_size, "B")
print("\nyear phase anom ydev n_loss n_warned pct_warned bytes n_districts")
for r in summary:
    print(*r)
