"""02_climate.py - IMD gridded rainfall/tmax -> district climate features + ENSO conditioning.

Outputs: artifacts/climate_district.parquet, artifacts/timeseries_climate/{lgd}.json,
         artifacts/reports/02_climate_report.md
Caches : artifacts/_imd_grid_lgd.parquet (cell->district map), artifacts/_climate_cache/{var}_{year}.npz
Idempotent; delete the cache files to force recompute.
"""
from __future__ import annotations
import sys, time, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from common import districts, GEOJSON, RAW, ART, enso_phase_by_monsoon_year, save_json

warnings.filterwarnings("ignore")
T0 = time.time()
IMD = RAW / "05_weather_drought_imd" / "imd_gridded"
CACHE = ART / "_climate_cache"; CACHE.mkdir(exist_ok=True)
(ART / "timeseries_climate").mkdir(exist_ok=True); (ART / "reports").mkdir(exist_ok=True)
GRID_PQ = ART / "_imd_grid_lgd.parquet"
Y0, Y1, NORM0, NORM1 = 2000, 2025, 2000, 2024
YEARS = list(range(Y0, Y1 + 1))
MAXDIST = {"rain": 0.75, "tmax": 1.5}   # deg; farther nearest-cell fallback => null
MISSING = {"rain": -999.0, "tmax": 99.9}

master = districts()
LGDS = master.lgd.values
NL = len(LGDS)
lgd_idx = {l: i for i, l in enumerate(LGDS)}

import imdlib as imd

def load_year(var, y):
    ds = imd.open_data(var, y, y, "yearwise", str(IMD)).get_xarray()
    a = ds[var].values.astype("float32")
    a[(a <= -900) | (a >= 99.0 if var != "rain" else False)] = np.nan
    if var != "rain":
        a[a > 70] = np.nan
    return ds.lat.values, ds.lon.values, ds.time.values, a

# ── 1. grid -> district map ───────────────────────────────────────────────────
def build_grid_map():
    import geopandas as gpd
    from shapely.geometry import Point
    g = gpd.read_file(GEOJSON)
    g = g[g.Dist_LGD.astype(int) > 0][["Dist_LGD", "geometry"]].rename(columns={"Dist_LGD": "lgd"})
    g["lgd"] = g.lgd.astype(int)
    g = g.drop_duplicates("lgd")
    gm = g.set_index("lgd").geometry
    rows = []
    for var, yr in (("rain", 2015), ("tmax", 2015)):
        lat, lon, _, a = load_year(var, yr)
        valid = np.isfinite(a).any(0)
        iy, ix = np.meshgrid(np.arange(len(lat)), np.arange(len(lon)), indexing="ij")
        pts = gpd.GeoDataFrame({"iy": iy.ravel(), "ix": ix.ravel(), "valid": valid.ravel()},
                               geometry=gpd.points_from_xy(lon[ix.ravel()], lat[iy.ravel()]), crs=g.crs)
        pts = pts[pts.valid]
        j = gpd.sjoin(pts, g, predicate="within", how="inner").drop_duplicates(["iy", "ix"])
        have = set(j.lgd)
        out = j[["iy", "ix", "lgd"]].copy().reset_index(drop=True); out["fallback"] = False; out["dist_deg"] = 0.0
        vx, vy = lon[pts.ix.values], lat[pts.iy.values]
        for l in LGDS:
            if l in have: continue
            rp = gm[l].representative_point()
            d = np.hypot(vx - rp.x, vy - rp.y)
            k = int(np.argmin(d))
            out.loc[len(out)] = dict(iy=pts.iy.values[k], ix=pts.ix.values[k], lgd=l, fallback=True, dist_deg=float(d[k]))
        out["grid"] = var
        out["lat"] = lat[out.iy.values]; out["lon"] = lon[out.ix.values]
        rows.append(out)
    df = pd.concat(rows, ignore_index=True)
    df[["iy", "ix", "lgd"]] = df[["iy", "ix", "lgd"]].astype(int)
    df.to_parquet(GRID_PQ)
    return df

if GRID_PQ.exists():
    grid = pd.read_parquet(GRID_PQ)
else:
    for f in CACHE.glob("*.npz"): f.unlink()   # caches depend on the grid map
    grid = build_grid_map()
print(f"[grid] {len(grid)} cell-district links, {time.time()-T0:.0f}s")

def wmatrix(var, shape):
    """sparse (NL x ncell) 0/1 membership, honouring distance cap for fallbacks."""
    from scipy.sparse import csr_matrix
    s = grid[grid.grid == var]
    s = s[~(s.fallback & (s.dist_deg > MAXDIST[var]))]
    r = s.lgd.map(lgd_idx).values; c = s.iy.values * shape[1] + s.ix.values
    return csr_matrix((np.ones(len(s), dtype="float32"), (r, c)), shape=(NL, shape[0] * shape[1]))

# ── 2. per-year district daily series (cached) ───────────────────────────────
def district_daily(var, y):
    f = CACHE / f"{var}_{y}.npz"
    if f.exists():
        z = np.load(f, allow_pickle=True); return z["daily"], pd.to_datetime(z["time"])
    lat, lon, t, a = load_year(var, y)
    W = wmatrix(var, a.shape[1:])
    flat = a.reshape(a.shape[0], -1).T                      # cell x day
    valid = np.isfinite(flat).astype("float32")
    num = W @ np.nan_to_num(flat, nan=0.0); den = W @ valid
    with np.errstate(invalid="ignore", divide="ignore"):
        daily = np.where(den > 0, num / den, np.nan).astype("float32")   # NL x day
    np.savez_compressed(f, daily=daily, time=t.astype("datetime64[ns]"))
    return daily, pd.to_datetime(t)

def run_dry(x, thr=2.5, n=10):
    """count runs >= n days with x<thr (x: NL x days)."""
    cnt = np.zeros(x.shape[0]); run = np.zeros(x.shape[0])
    bad = ~np.isfinite(x).all(1)
    for d in range(x.shape[1]):
        dry = x[:, d] < thr
        run = np.where(dry, run + 1, 0)
        cnt += (run == n)
    cnt[bad] = np.nan
    return cnt

rain = {k: {} for k in ("jjas", "ann", "ond", "dry", "onset")}
tmx = {k: {} for k in ("jjas", "febmar", "marmay")}
for y in YEARS:
    d, t = district_daily("rain", y)
    m = t.month.values
    for k, sel in (("jjas", (m >= 6) & (m <= 9)), ("ond", m >= 10), ("ann", np.ones_like(m, bool))):
        if k == "ond": sel = (m >= 10)
        v = np.nansum(d[:, sel], 1); v[~np.isfinite(d[:, sel]).any(1)] = np.nan
        rain[k][y] = v
    rain["ann"][y][~np.isfinite(d).all(1)] = np.nan
    j = d[:, (m >= 6) & (m <= 9)]
    rain["dry"][y] = run_dry(j)
    # onset: first day (after Jun 1) whose trailing 7-day sum >= 50 mm; value = days since Jun 1
    c = np.concatenate([np.zeros((NL, 1)), np.cumsum(np.nan_to_num(j), 1)], 1)
    s7 = c[:, 7:] - c[:, :-7]                           # window ending at day index 6..
    ok = s7 >= 50
    first = np.where(ok.any(1), ok.argmax(1) + 6, np.nan)
    first[~np.isfinite(j).any(1)] = np.nan
    rain["onset"][y] = first
    d, t = district_daily("tmax", y)
    m = t.month.values
    for k, sel in (("jjas", (m >= 6) & (m <= 9)), ("febmar", (m == 2) | (m == 3)), ("marmay", (m >= 3) & (m <= 5))):
        with np.errstate(all="ignore"):
            tmx[k][y] = np.nanmean(d[:, sel], 1)
print(f"[agg] yearly aggregates done, {time.time()-T0:.0f}s")

def frame(dct):
    return pd.DataFrame({y: v for y, v in dct.items()}, index=LGDS)

R = {k: frame(v) for k, v in rain.items()}
T = {k: frame(v) for k, v in tmx.items()}
nyrs = [y for y in YEARS if NORM0 <= y <= NORM1]
normal = R["jjas"][nyrs].mean(1)
anom = (R["jjas"].sub(normal, axis=0)).div(normal, axis=0) * 100
ond_n = R["ond"][nyrs].mean(1)
ond_anom = (R["ond"].sub(ond_n, axis=0)).div(ond_n.where(ond_n > 1), axis=0) * 100
T_anom = {k: T[k].sub(T[k][nyrs].mean(1), axis=0) for k in T}

# ── 3. ENSO conditioning ─────────────────────────────────────────────────────
phase = enso_phase_by_monsoon_year()
def mean_phase(p): 
    ys = [y for y in YEARS if phase.get(y) == p]; return anom[ys].mean(1), ys
el, el_ys = mean_phase("El Niño"); ne, ne_ys = mean_phase("Neutral"); la, la_ys = mean_phase("La Niña")
strong = anom[[2002, 2009, 2015]].mean(1)
defprob = (anom[el_ys] < -10).sum(1) / len(el_ys)
defprob[anom[el_ys].isna().all(1)] = np.nan
latest_year = 2025 if 2025 in anom.columns and anom[2025].notna().any() else 2024

def rj(df, nd=1):
    return [json.dumps({str(y): (None if not np.isfinite(v) else round(float(v), nd)) for y, v in row.items()})
            for _, row in df.iterrows()]

out = pd.DataFrame({
    "lgd": LGDS,
    "jjas_normal_mm": normal.round(1).values,
    "elnino_mean_anomaly_pct": el.round(1).values,
    "neutral_mean_anomaly_pct": ne.round(1).values,
    "lanina_mean_anomaly_pct": la.round(1).values,
    "strong_elnino_anomaly_pct": strong.round(1).values,
    "elnino_deficit_prob": defprob.round(3).values,
    "jjas_anomaly_json": rj(anom), "ond_anomaly_json": rj(ond_anom),
    "tmax_jjas_anomaly_json": rj(T_anom["jjas"], 2), "tmax_febmar_anomaly_json": rj(T_anom["febmar"], 2),
    "tmax_marmay_anomaly_json": rj(T_anom["marmay"], 2),
    "dry_spells_json": rj(R["dry"], 0), "onset_day_json": rj(R["onset"], 0),
    "latest_year_anomaly_pct": anom[latest_year].round(1).values, "latest_year": latest_year,
})
out.to_parquet(ART / "climate_district.parquet")

for i, l in enumerate(LGDS):
    def ser(df, nd=1):
        return {str(y): (None if not np.isfinite(df.iat[i, k]) else round(float(df.iat[i, k]), nd)) for k, y in enumerate(df.columns)}
    save_json({"rain_jjas_mm": ser(R["jjas"]), "rain_annual_mm": ser(R["ann"]), "jjas_anomaly_pct": ser(anom),
               "tmax_jjas_c": ser(T["jjas"], 2), "oni_phase": {str(y): phase.get(y) for y in YEARS}},
              ART / "timeseries_climate" / f"{l}.json")
print(f"[out] wrote parquet + {NL} timeseries, {time.time()-T0:.0f}s")

# ── 4. all-India sanity ──────────────────────────────────────────────────────
import geopandas as gpd
ga = gpd.read_file(GEOJSON); ga = ga[ga.Dist_LGD.astype(int) > 0].drop_duplicates("Dist_LGD")
area = ga.set_index(ga.Dist_LGD.astype(int)).to_crs(6933).area.reindex(LGDS).values
def india(df):
    w = np.where(df.notna(), area[:, None], 0.0)
    return (df.fillna(0).values * w).sum(0) / w.sum(0)
ai_mm = pd.Series(india(R["jjas"]), index=YEARS)
ai_norm = ai_mm[nyrs].mean()
ai_anom = (ai_mm - ai_norm) / ai_norm * 100
ref = {2002: -19, 2009: -22, 2014: -12, 2015: -14, 2019: 10, 2023: -6}
LPA = 868.6   # IMD all-India JJAS long period average (1971-2020), mm
ai_vs_lpa = (ai_mm - LPA) / LPA * 100
lines = ["| Year | ENSO | All-India JJAS (mm) | Anom vs 2000-24 mean (%) | Anom vs IMD LPA 868.6mm (%) | IMD reference (%) |", "|---|---|---|---|---|---|"]
for y in YEARS:
    lines.append(f"| {y} | {phase.get(y,'')} | {ai_mm[y]:.0f} | {ai_anom[y]:+.1f} | {ai_vs_lpa[y]:+.1f} | {ref.get(y,'')} |")
print("\n".join(lines))

# ── 5. report ────────────────────────────────────────────────────────────────
fb = grid[grid.fallback].copy()
fb = fb.merge(master[["lgd", "district", "state"]], on="lgd")
nulls = out[out.jjas_normal_mm.isna()].merge(master[["lgd", "district", "state"]], on="lgd")
tnull = int(T["jjas"].isna().all(1).sum())
dist_el = out.elnino_mean_anomaly_pct.describe(percentiles=[.05, .25, .5, .75, .95])
samples = [486, 673, 191, 502]
for nm in ("Beed", "Latur"):
    r = master[master.district.str.lower().str.contains(nm.lower())]
    if len(r): samples.append(int(r.lgd.iloc[0]))
def samp(l):
    r = out[out.lgd == l].iloc[0]; m = master[master.lgd == l].iloc[0]
    f1 = lambda v: "n/a" if pd.isna(v) else f"{v:.1f}"
    return (f"| {l} | {m.district} ({m.state}) | {f1(r.jjas_normal_mm)} | {f1(r.elnino_mean_anomaly_pct)} | {f1(r.neutral_mean_anomaly_pct)} | "
            f"{f1(r.lanina_mean_anomaly_pct)} | {f1(r.strong_elnino_anomaly_pct)} | {f1(r.elnino_deficit_prob)} | {f1(r.latest_year_anomaly_pct)} ({r.latest_year}) |")
rep = ["# 02_climate report", "",
       f"Grid: rain 0.25 deg (IMD), tmax 1 deg (IMD). Years {Y0}-{Y1}; normal = {NORM0}-{NORM1} mean. ENSO years (El Nino n={len(el_ys)}): {el_ys}; Neutral n={len(ne_ys)}; La Nina n={len(la_ys)}.", "",
       "## All-India JJAS anomaly (area-weighted district means) vs IMD reference", "", *lines, "",
       "Note: IMD all-India anomalies are relative to the 1971-2020 LPA (868.6 mm); ours are relative to the 2000-2024 mean (shown also vs LPA). Rain-gauge-gridded data are IMD's own, so agreement is expected within a few points.", "",
       "## Districts without in-polygon cells (nearest valid cell fallback)", "",
       f"Rain grid: {int(((fb.grid=='rain')).sum())} districts used fallback; tmax grid (1 deg): {int(((fb.grid=='tmax')).sum())} districts.",
       f"Districts with null rainfall (nearest cell beyond {MAXDIST['rain']} deg): {len(nulls)}; null tmax (beyond {MAXDIST['tmax']} deg): {tnull}.", ""]
if len(nulls):
    rep += ["Null-rain districts: " + ", ".join(f"{r.district} ({r.state}, lgd {r.lgd})" for r in nulls.itertuples()), ""]
rf = fb[fb.grid == "rain"].sort_values("dist_deg", ascending=False)
rep += ["Rain fallback districts (first 40, by distance):", "",
        "| lgd | district | state | dist deg |", "|---|---|---|---|"] + \
       [f"| {r.lgd} | {r.district} | {r.state} | {r.dist_deg:.2f} |" for r in rf.head(40).itertuples()] + [""]
rep += ["## Distribution of elnino_mean_anomaly_pct", "", "```", dist_el.round(2).to_string(), "```", "",
        f"Share of districts with El Nino mean anomaly < -10%: {(out.elnino_mean_anomaly_pct< -10).mean():.1%}; "
        f"< 0: {(out.elnino_mean_anomaly_pct<0).mean():.1%}. Mean elnino_deficit_prob: {out.elnino_deficit_prob.mean():.2f}.", "",
        "## Sample districts", "",
        "| lgd | district | JJAS normal mm | El Nino % | Neutral % | La Nina % | Strong El Nino % | P(deficit) | latest anom % |", "|---|---|---|---|---|---|---|---|---|",
        *[samp(l) for l in samples], "",
        "## Runtime", "", f"{time.time()-T0:.0f} s (with cache). Normal from 2000-2024 IMD (TerraClimate 1958-2017 normal not used).", ""]
(ART / "reports" / "02_climate_report.md").write_text("\n".join(rep))
print(f"[done] {time.time()-T0:.0f}s")
