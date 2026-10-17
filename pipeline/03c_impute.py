"""03c_impute.py - fill the gaps in the district layers before scoring (runs after 03b, before 04b / 04).

Reads   : artifacts/{_districts_master,crops_latest,crops_district_year,yield_sensitivity,climate_district,social_district,extra_district}.parquet,
          INDIA_DISTRICTS.geojson (adjacency), Earth Engine (WorldPop, MODIS NDVI + WorldCover, CHIRPS; user OAuth, project ee-chvi; cached).
Writes  : artifacts/imputed_district.parquet   one row per lgd; columns are named like the SOURCE parquet columns (value only where imputed, NaN elsewhere)
                                                 + `<col>__src` (source tag) + cross-check columns (`worldpop_2020`, `rabi_ndvi_*`, rabi structure overrides `rab_*`)
          artifacts/imputed_district.json      {"districts": {lgd: {"<dotted schema path>": "<source>"}}, "consumption_side": {lgd: tag}, "split_parent": {lgd: parent_lgd}, "meta": {...}}
          artifacts/_adjacency.json            polygon adjacency cache (touch within 500 m; value = shared-border length in km) + area km2
          artifacts/_gee_cache/imp_*.json      Earth Engine results (re-used on re-runs; --refresh-ee to recompute)
          artifacts/reports/03c_impute_report.md   (06_export.py appends the before/after null table below the marker line)

Consumers (04_risk.py, 06_export.py) overlay `imputed_district.parquet` onto the original layers by column name (fillna) and never alter an observed value.
04_risk.py uses the observed values only as the reference distribution for percentile ranks / band thresholds, so existing districts are not re-ranked by their imputed neighbours.

Methods (SCHEMA Addendum G source tags)
  neighbours_knn        median (border-length weighted) of the touching districts that have an OBSERVED value: same state first, else any touching district
  neighbours_2hop       same, over neighbours-of-neighbours in the same state (islands / enclaves with no touching donors fall through to the state median)
  state_median / national_median   last resorts
  state_ratio_nfhs5 / state_ratio_nfhs6   NFHS-6 = NFHS-5 x state median(NFHS-6/NFHS-5) (and the inverse when only NFHS-6 exists)
  parent_inherit        post-2011 split district inherits ratio / rate fields from its parent district (explicit parent table, see SPLIT_PARENT)
  parent_split_area_share   absolute fields (foodgrain production / area, rabi structure) = parent value x area / (parent + all its new children's area)
  ee_worldpop           WorldPop 100 m 2020 sum per polygon, scaled to 2011 / 2026 with the state growth factor
  ee_rabi_ndvi          rabi foodgrain area share from MODIS NDVI (Dec-Feb mean minus Sep-Oct minimum on WorldCover cropland), linear map calibrated on districts with APY rabi data
  ee_chirps             island climate (no IMD cells) from CHIRPS v2 daily rainfall 2000-2025
  urban_consumption_side   (declared here, applied in 04_risk.py) exposure from the surrounding districts, sensitivity from supply / PDS dependency only

Run: python3 pipeline/03c_impute.py [--no-ee] [--refresh-ee]
"""
from __future__ import annotations
import argparse, json, math, sys, time, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import districts, GEOJSON, ART, save_json, enso_phase_by_monsoon_year

T0 = time.time()
ap = argparse.ArgumentParser()
ap.add_argument("--no-ee", action="store_true", help="skip Earth Engine (cache is still used if present)")
ap.add_argument("--refresh-ee", action="store_true", help="recompute the Earth Engine layers")
ARGS = ap.parse_args()
EE_PROJECT = "ee-chvi"
CACHE = ART / "_gee_cache"; CACHE.mkdir(parents=True, exist_ok=True)
ADJ_PATH = ART / "_adjacency.json"
YEARS = list(range(2000, 2026)); NORM0, NORM1 = 2000, 2024
BUF_M = 500


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


# ── 0. load ────────────────────────────────────────────────────────────────────────────────────────────────────────
m = districts()[["lgd", "district", "state", "state_lgd", "census11", "centroid_lon", "centroid_lat"]].copy()
LG = m.lgd.astype(int).values
STATE = dict(zip(m.lgd, m.state)); NAME = dict(zip(m.lgd, m.district))
crops = pd.read_parquet(ART / "crops_latest.parquet").set_index("lgd")
ys_ = pd.read_parquet(ART / "yield_sensitivity.parquet").set_index("lgd")
clim = pd.read_parquet(ART / "climate_district.parquet").set_index("lgd")
soc = pd.read_parquet(ART / "social_district.parquet").set_index("lgd")
extra = pd.read_parquet(ART / "extra_district.parquet").set_index("lgd")
panel = pd.read_parquet(ART / "crops_district_year.parquet")
for d_ in (crops, ys_, clim, soc, extra):
    d_.index = d_.index.astype(int)
crops, ys_, clim, soc, extra = (d_.reindex(LG) for d_ in (crops, ys_, clim, soc, extra))
assert len(LG) == 753
IMP: dict[int, dict[str, str]] = {int(l): {} for l in LG}          # lgd -> {schema path: source}
VAL: dict[str, dict[int, object]] = {}                              # source-parquet column -> {lgd: value}
SRC: dict[str, dict[int, str]] = {}


def put(col, path, lgd, value, src):
    """record an imputed value for source column `col` (schema path `path`)"""
    VAL.setdefault(col, {})[int(lgd)] = value
    SRC.setdefault(col, {})[int(lgd)] = src
    if path:
        IMP[int(lgd)][path] = src


# ── 1. adjacency (polygon touches, 500 m tolerance) ────────────────────────────────────────────────────────────────
def build_adjacency():
    import geopandas as gpd
    from shapely.validation import make_valid
    g = gpd.read_file(GEOJSON)
    g = g[g.Dist_LGD.fillna(0).astype(int) > 0].drop_duplicates("Dist_LGD").copy()
    g["lgd"] = g.Dist_LGD.astype(int)
    g["geometry"] = g.geometry.apply(make_valid)
    p = g.to_crs(7755)                                   # India NSF LCC (metres)
    geoms = dict(zip(p.lgd, p.geometry)); sidx = p.sindex
    adj = {}
    for l, geom in geoms.items():
        cand = sidx.query(geom.buffer(BUF_M), predicate="intersects")
        d = {}
        for c in cand:
            l2 = int(p.lgd.iloc[c])
            if l2 == l:
                continue
            d[str(l2)] = round(geom.boundary.intersection(geoms[l2].buffer(BUF_M)).length / 1000, 2)
        adj[str(l)] = d
    area = {str(l): round(geom.area / 1e6, 1) for l, geom in geoms.items()}
    out = {"buffer_m": BUF_M, "adj": adj, "area_km2": area}
    save_json(out, ADJ_PATH)
    return out


if ADJ_PATH.exists():
    A_ = json.load(open(ADJ_PATH)); log("adjacency cache hit")
else:
    log("building adjacency (geopandas, ~30 s)"); A_ = build_adjacency()
ADJ = {int(k): {int(a): max(float(b), 1.0) for a, b in v.items()} for k, v in A_["adj"].items()}
AREA = {int(k): float(v) for k, v in A_["area_km2"].items()}
log(f"adjacency: mean {np.mean([len(v) for v in ADJ.values()]):.1f} neighbours, isolated {[NAME[l] for l, v in ADJ.items() if not v]}")

# ── 2. post-2011 split districts -> parent (the polygons are POST-split: parents shrank, nothing overlaps) ────────────────
SPLIT_PARENT_NAMES = {      # child (state, name) -> parent name in the same state (administrative facts, checked against the polygons)
    "Kakching": "Thoubal", "Kangpokpi": "Senapati", "Jiribam": "Imphal East", "Noney": "Tamenglong", "Pherzawl": "Churachandpur",
    "Tengnoupal": "Chandel", "Kamjong": "Ukhrul", "Mayiladuthurai": "Nagapattinam", "Noklak": "Tuensang", "Malerkotla": "Sangrur",
    "Vijayanagar": "Ballari", "Bajali": "Barpeta", "Eastern West Khasi Hills": "West Khasi Hills",
    "Parvathipuram Manyam": "Vizianagaram", "Anakapalli": "Visakhapatnam", "Alluri Sitharama Raju": "Visakhapatnam",
    "Kakinada": "East Godavari", "Konaseema": "East Godavari", "Eluru": "West Godavari", "NTR": "Krishna", "Bapatla": "Guntur",
    "Palnadu": "Guntur", "Tirupati": "Chittoor", "Annamayya": "Y.S.R.", "Sri Sathya sai": "Anantpur", "Nandyal": "Kurnool",
}
SPLIT_PARENT: dict[int, int] = {}
for ch, pa in SPLIT_PARENT_NAMES.items():
    c = m[m.district == ch]; p_ = m[(m.district == pa)]
    assert len(c) == 1 and len(p_) == 1, (ch, pa)
    assert c.state.iat[0] == p_.state.iat[0], (ch, pa)
    SPLIT_PARENT[int(c.lgd.iat[0])] = int(p_.lgd.iat[0])
KIDS: dict[int, list[int]] = {}
for c_, p_ in SPLIT_PARENT.items():
    KIDS.setdefault(p_, []).append(c_)
def split_share(child):
    """area share of the child within the parent's pre-split territory = A_child / (A_parent_now + sum A_children)"""
    p_ = SPLIT_PARENT[child]
    return AREA[child] / (AREA[p_] + sum(AREA[k] for k in KIDS[p_]))
SHARE = {c_: split_share(c_) for c_ in SPLIT_PARENT}
log(f"{len(SPLIT_PARENT)} split children -> {len(KIDS)} parents")
# Mahe / Yanam are enclaves, not splits: they are handled by the neighbour methods / consumption side.


# ── 3. spatial imputation engine ────────────────────────────────────────────────────────────────────────────────────
def wmedian(vals, w):
    vals = np.asarray(vals, float); w = np.asarray(w, float)
    if len(vals) <= 2:
        return float(np.average(vals, weights=w))
    o = np.argsort(vals); v, ww = vals[o], w[o]; cw = np.cumsum(ww) / ww.sum()
    return float(v[np.searchsorted(cw, 0.5)])


def spatial_fill(obs: pd.Series, targets, cat=False):
    """obs: Series indexed by lgd (NaN = no OBSERVED value). Returns {lgd: (value, source)} for the targets.
    Order: touching donors in the same state -> touching donors anywhere -> 2-hop same-state donors -> state median (>= 3 donors) -> national median."""
    have = obs.dropna()
    hv = set(have.index)
    st = pd.Series({l: STATE[l] for l in have.index})
    if cat:
        st_mode = have.groupby(st).agg(lambda s: s.value_counts().index[0]); nat = have.value_counts().index[0]
    else:
        g = have.groupby(st).agg(["median", "count"]); nat = float(have.median())
    out = {}
    for t in targets:
        s = STATE[t]; nb = ADJ.get(t, {})
        same = {n: w for n, w in nb.items() if n in hv and STATE[n] == s}
        anyd = {n: w for n, w in nb.items() if n in hv}
        pick = same or anyd
        if pick:
            if cat:
                cnt = {}
                for n, w in pick.items():
                    cnt[have[n]] = cnt.get(have[n], 0) + w
                out[t] = (max(cnt, key=cnt.get), "neighbours_knn")
            else:
                out[t] = (wmedian([have[n] for n in pick], [w for w in pick.values()]), "neighbours_knn")
            continue
        two = {}
        for n in nb:
            for n2, w in ADJ.get(n, {}).items():
                if n2 != t and n2 in hv and STATE[n2] == s:
                    two[n2] = max(two.get(n2, 0), w)
        if two:
            if cat:
                out[t] = (have[list(two)].value_counts().index[0], "neighbours_2hop")
            else:
                out[t] = (wmedian([have[n] for n in two], list(two.values())), "neighbours_2hop")
            continue
        if cat:
            out[t] = (st_mode[s], "state_median") if s in st_mode.index else (nat, "national_median")
        elif s in g.index and g.loc[s, "count"] >= 3:
            out[t] = (float(g.loc[s, "median"]), "state_median")
        else:
            out[t] = (nat, "national_median")
    return out


def fill_ratio(col, path, obs: pd.Series, targets=None, parent=True, lo=None, hi=None, extra_obs=None):
    """impute the missing entries of `obs` (ratio/rate/index fields): split children inherit from the parent's value (observed, else the parent's own
    imputed value in `extra_obs`), everything else from the neighbours. Records into VAL/SRC/IMP and returns {lgd: (value, src)}."""
    targets = [int(l) for l in (obs.index[obs.isna()] if targets is None else targets) if pd.isna(obs.get(int(l), np.nan))]
    res = {}
    rest = []
    for t in targets:
        pv = np.nan
        if parent and t in SPLIT_PARENT:
            p_ = SPLIT_PARENT[t]
            pv = obs.get(p_, np.nan)
            if pd.isna(pv) and extra_obs is not None:
                pv = extra_obs.get(p_, np.nan)
        if parent and t in SPLIT_PARENT and not pd.isna(pv):
            res[t] = (float(pv), "parent_inherit")
        else:
            rest.append(t)
    res.update(spatial_fill(obs, rest))
    for t, (v, s) in res.items():
        if lo is not None: v = max(lo, v)
        if hi is not None: v = min(hi, v)
        res[t] = (v, s)
        put(col, path, t, v, s)
    return res


# ── 4. Earth Engine layers (cached) ────────────────────────────────────────────────────────────────────────────────
EE = {"ok": False, "why": None}
WP, NDVI, CHIRPS = {}, {}, {}


def ee_init():
    try:
        import ee
        ee.Initialize(project=EE_PROJECT)
        EE["ok"] = True; EE["ee"] = ee
    except Exception as e:      # noqa
        EE["why"] = str(e)[:160]
        log("Earth Engine unavailable:", EE["why"])


def retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1) ** 2); log("  retry after:", str(e)[:100])


def geo_feats(lgds, simplify=0.002, buffer_deg=0.0):
    import geopandas as gpd
    from shapely.validation import make_valid
    g = gpd.read_file(GEOJSON)
    g = g[g.Dist_LGD.fillna(0).astype(int) > 0].drop_duplicates("Dist_LGD").copy(); g["lgd"] = g.Dist_LGD.astype(int)
    g = g[g.lgd.isin(lgds)]
    g["geometry"] = g.geometry.apply(make_valid)
    if buffer_deg:
        g["geometry"] = g.geometry.buffer(buffer_deg)
    g["geometry"] = g.geometry.simplify(simplify, preserve_topology=True)
    ee = EE["ee"]
    feats = []
    for l, geom in zip(g.lgd, g.geometry):
        gj = json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]
        feats.append(ee.Feature(ee.Geometry(gj, None, False), {"lgd": int(l)}))
    return feats


def reduce_chunks(image, feats, scale, reducer, chunk=30, workers=4, tile_scale=4):
    ee = EE["ee"]
    chunks = [feats[i:i + chunk] for i in range(0, len(feats), chunk)]

    def one(fs):
        return retry(lambda: image.reduceRegions(collection=ee.FeatureCollection(fs), reducer=reducer, scale=scale, tileScale=tile_scale).getInfo()["features"])
    res = {}
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, c) for c in chunks]
        for n, fu in enumerate(as_completed(futs), 1):
            for f in fu.result():
                p = f["properties"]; res[int(p["lgd"])] = {k: v for k, v in p.items() if k != "lgd"}
            if n % 5 == 0 or n == len(futs):
                log(f"    chunks {n}/{len(futs)}")
    return res


def ee_cached(name, fn):
    p = CACHE / f"imp_{name}.json"
    if p.exists() and not ARGS.refresh_ee:
        log(f"EE {name}: cache hit"); return {int(k): v for k, v in json.load(open(p)).items()}
    if not EE["ok"]:
        return {}
    log(f"EE {name}: computing")
    r = fn()
    save_json({str(k): v for k, v in r.items()}, p)
    return r


def ee_worldpop():
    ee = EE["ee"]
    wp = ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IND")).filter(ee.Filter.eq("year", 2020)).mosaic()
    return reduce_chunks(wp, geo_feats(list(LG), 0.002), 100, ee.Reducer.sum(), chunk=30, tile_scale=8)


def ee_ndvi():
    """Per district, cropland-fraction-weighted means (WorldCover v200 class 40, aggregated to the MODIS 250 m grid) of
    winter NDVI (Dec-Feb mean) and of winter minus autumn trough (Sep-Oct minimum), averaged over winters 2021-22 .. 2024-25."""
    ee = EE["ee"]
    coll = ee.ImageCollection("MODIS/061/MOD13Q1").select("NDVI")
    proj = ee.Image(coll.first()).projection()
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").eq(40)
    frac = wc.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024).reproject(proj).rename("f")
    wins, dels = [], []
    for w in (2021, 2022, 2023, 2024):
        win = coll.filterDate(f"{w}-12-01", f"{w + 1}-03-01").mean().multiply(0.0001)
        aut = coll.filterDate(f"{w}-09-01", f"{w}-11-01").min().multiply(0.0001)
        wins.append(win); dels.append(win.subtract(aut))
    win = ee.ImageCollection(wins).mean(); dlt = ee.ImageCollection(dels).mean()
    img = ee.Image.cat([win.multiply(frac).rename("wf"), dlt.multiply(frac).rename("df"), frac]).rename(["wf", "df", "f"])
    r = reduce_chunks(img, geo_feats(list(LG), 0.002), 250, ee.Reducer.sum(), chunk=25, tile_scale=8)
    out = {}
    for l, v in r.items():
        f = v.get("f") or 0.0
        out[l] = {"winter": (v["wf"] / f if f > 0 else None), "delta": (v["df"] / f if f > 0 else None), "crop_px": f}
    return out


def ee_chirps(lgds):
    """JJAS (Jun-Sep) and OND (Oct-Dec) CHIRPS rainfall sums per year 2000-2025 for the island districts (polygons buffered 0.1 deg: the islands are
    smaller than a 5.5 km pixel) plus a validation sample of IMD districts (unbuffered)."""
    ee = EE["ee"]
    coll = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
    bands = []
    for y in YEARS:
        bands.append(coll.filterDate(f"{y}-06-01", f"{y}-10-01").sum().rename(f"j{y}"))
        bands.append(coll.filterDate(f"{y}-10-01", f"{y + 1}-01-01").sum().rename(f"o{y}"))
    img = ee.Image.cat(bands)
    feats = geo_feats(list(lgds), 0.001, buffer_deg=0.1)
    return reduce_chunks(img, feats, 5566, ee.Reducer.mean(), chunk=10, tile_scale=2)


def ee_chirps_val(lgds):
    ee = EE["ee"]
    coll = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
    bands = [coll.filterDate(f"{y}-06-01", f"{y}-10-01").sum().rename(f"j{y}") for y in YEARS]
    return reduce_chunks(ee.Image.cat(bands), geo_feats(list(lgds), 0.01), 5566, ee.Reducer.mean(), chunk=15, tile_scale=2)


no_clim = [int(l) for l in clim.index[clim.jjas_normal_mm.isna()]]
if not ARGS.no_ee or any((CACHE / f"imp_{n}.json").exists() for n in ("worldpop", "ndvi", "chirps")):
    if not ARGS.no_ee:
        ee_init()
    WP = ee_cached("worldpop", ee_worldpop)
    NDVI = ee_cached("ndvi", ee_ndvi)
    CHIRPS = ee_cached("chirps", lambda: ee_chirps(no_clim))
    rng = np.random.RandomState(7)
    val_l = [int(x) for x in rng.choice([l for l in LG if l not in no_clim], 40, replace=False)]
    CHVAL = ee_cached("chirps_val", lambda: ee_chirps_val(val_l))
else:
    CHVAL = {}
log(f"EE layers: worldpop {len(WP)}, ndvi {len(NDVI)}, chirps islands {len(CHIRPS)}, chirps validation {len(CHVAL)}")

REP: list[str] = []          # report lines
STATS: dict = {}             # numbers for the report / JSON meta

# ── 5. population (WorldPop; cross-check for all districts) ─────────────────────────────────────────────────────────
g26 = soc.state_pop_factor.astype(float)                               # 2026 / 2011 state factor (03_nutrition_social)
pop11 = soc.population_2011.astype(float); pop26 = soc.population_2026.astype(float)
wp20 = pd.Series({l: (WP.get(l) or {}).get("sum", np.nan) for l in LG}, dtype=float)
wp_cross = {}
if wp20.notna().any():
    # cross-check vs census-based 2020 (district 2011 x state factor ^ (9/15)) on districts that are not split parents / children (their census counts are pre-split)
    split_involved = set(SPLIT_PARENT) | set(SPLIT_PARENT.values())
    census20 = pop11 * (g26 ** (9 / 15))
    ok = census20.notna() & wp20.notna() & ~pd.Series(LG, index=LG).isin(split_involved) & (census20 > 0) & (wp20 > 0)
    r_log = float(np.corrcoef(np.log(census20[ok]), np.log(wp20[ok]))[0, 1]); r_lin = float(np.corrcoef(census20[ok], wp20[ok])[0, 1])
    ratio = (wp20[ok] / census20[ok])
    big = ok & (census20 > 1e6)
    wp_cross = dict(n=int(ok.sum()), pearson_log=round(r_log, 4), pearson_linear=round(r_lin, 4), median_ratio_wp_over_census=round(float(ratio.median()), 3),
                    p10=round(float(ratio.quantile(.1)), 3), p90=round(float(ratio.quantile(.9)), 3), total_wp_M=round(float(wp20.sum() / 1e6), 1),
                    total_census20_M=round(float(census20[ok].sum() / 1e6), 1), total_wp_ok_M=round(float(wp20[ok].sum() / 1e6), 1),
                    pearson_log_pop26=None)
    ok26 = ok & pop26.notna()
    wp26 = wp20 * (g26 ** (6 / 15))
    wp_cross["pearson_log_pop26"] = round(float(np.corrcoef(np.log(pop26[ok26]), np.log(wp26[ok26]))[0, 1]), 4)
    wp_cross["median_ratio_wp26_over_census26"] = round(float((wp26[ok26] / pop26[ok26]).median()), 3)
    log("WorldPop cross-check:", wp_cross)
# calibration: WorldPop (UN-adjusted, unconstrained) sums to ~0.90 x the census-based 2020 level; scale each state by its median census/WorldPop ratio (>= 5 districts, split parents/children excluded) else the national median
WP_CAL = {}
if wp_cross:
    rr_ = (census20 / wp20)[ok]; st_ok = pd.Series({l: STATE[l] for l in rr_.index})
    gst = rr_.groupby(st_ok).agg(["median", "count"]); nat_cal = float(rr_.median())
    WP_CAL = {s_: (float(gst.loc[s_, "median"]) if (s_ in gst.index and gst.loc[s_, "count"] >= 5) else nat_cal) for s_ in set(STATE.values())}
    wp_cross["national_calibration"] = round(nat_cal, 3)
    wp20_raw = wp20.copy()
    wp20 = pd.Series({l: wp20_raw[l] * WP_CAL[STATE[l]] for l in LG})
    ratio_cal = (wp20[ok] / census20[ok]); wp_cross["median_ratio_after_calibration"] = round(float(ratio_cal.median()), 3)
    wp_cross["pearson_log_calibrated"] = round(float(np.corrcoef(np.log(census20[ok]), np.log(wp20[ok]))[0, 1]), 4)
pop_targets = [int(l) for l in LG if pd.isna(pop11[l]) or pd.isna(pop26[l])]
STATS["pop_targets"] = len(pop_targets)
pop_val_check = []     # area-share split of the parent's census population vs WorldPop for the split children that have a census count or WorldPop
for t in pop_targets:
    p11 = p26 = None; src = None
    if wp20.notna().get(t, False):
        f = g26[t] if not pd.isna(g26[t]) else float(g26.median())
        p26 = wp20[t] * (f ** (6 / 15)); p11 = wp20[t] / (f ** (9 / 15)); src = "ee_worldpop"
    elif t in SPLIT_PARENT and not pd.isna(pop11.get(SPLIT_PARENT[t])):
        pp = SPLIT_PARENT[t]; p11 = pop11[pp] * SHARE[t]; p26 = pop26[pp] * SHARE[t]; src = "parent_split_area_share"
    else:
        dens = fill_ratio("_dens", None, (pop26 / pd.Series({l: AREA[l] for l in LG})).where(pop26.notna()), targets=[t], parent=False)
        p26 = dens[t][0] * AREA[t]; p11 = p26 / (g26.get(t, 1.2) if not pd.isna(g26.get(t)) else 1.2); src = "neighbours_knn"
        VAL.pop("_dens", None); SRC.pop("_dens", None)
    if pd.isna(pop11[t]):
        put("population_2011", "population_2011", t, float(round(p11)), src)
    if pd.isna(pop26[t]):
        put("population_2026", "population_2026", t, float(round(p26)), src)
    if t in SPLIT_PARENT and not pd.isna(pop11.get(SPLIT_PARENT[t])) and wp20.notna().get(t, False):
        pp = SPLIT_PARENT[t]
        pop_val_check.append((t, NAME[t], float(wp20[t] * (g26[t] ** (6 / 15)) if not pd.isna(g26[t]) else np.nan), float(pop26[pp] * SHARE[t])))
POP26 = pop26.copy()
for t, v in VAL.get("population_2026", {}).items():
    POP26[t] = v
POP11 = pop11.copy()
for t, v in VAL.get("population_2011", {}).items():
    POP11[t] = v
if pop_val_check:
    pv = pd.DataFrame(pop_val_check, columns=["lgd", "district", "worldpop_2026", "parent_area_share_2026"]).dropna()
    STATS["pop_split_check"] = pv
# the area-share split vs WorldPop for ALL split children with a parent census count (validation of method 2, independent of the null-population ones)
chk = []
for c_, p_ in SPLIT_PARENT.items():
    if wp20.notna().get(c_, False) and not pd.isna(pop26.get(p_)):
        f = g26[c_] if not pd.isna(g26[c_]) else float(g26.median())
        chk.append((c_, NAME[c_], NAME[p_], float(wp20[c_] * (f ** (6 / 15))), float(pop26[p_] * SHARE[c_]), float(pop26[c_]) if not pd.isna(pop26.get(c_)) else np.nan))
STATS["pop_split_all"] = pd.DataFrame(chk, columns=["lgd", "district", "parent", "worldpop_2026", "parent_area_share_2026", "census_2026"]) if chk else None

# ── 6. NFHS (stunting / wasting / underweight / child anaemia / women anaemia / women BMI) ───────────────────────────
def jget(js, k):
    if isinstance(js, str):
        v = json.loads(js).get(k)
        return np.nan if v is None else float(v)
    return np.nan
IND = ["stunting", "wasting", "underweight", "child_anaemia", "women_anaemia", "women_bmi_low"]
N5 = {i: (soc[f"{i}_nfhs5"].astype(float) if f"{i}_nfhs5" in soc else soc.nfhs5_json.map(lambda s, i=i: jget(s, i))) for i in IND}
N6 = {i: (soc[f"{i}_nfhs6"].astype(float) if f"{i}_nfhs6" in soc else soc.nfhs6_json.map(lambda s, i=i: jget(s, i))) for i in IND}
N5["women_bmi_low"] = soc.nfhs5_json.map(lambda s: jget(s, "women_bmi_low")); N6["women_bmi_low"] = soc.nfhs6_json.map(lambda s: jget(s, "women_bmi_low"))
N5["severe_wasting"] = soc.nfhs5_json.map(lambda s: jget(s, "severe_wasting")); N6["severe_wasting"] = soc.nfhs6_json.map(lambda s: jget(s, "severe_wasting"))
IND_ALL = IND + ["severe_wasting"]
N6_AVAILABLE = [i for i in IND_ALL if N6[i].notna().sum() >= 100]      # NFHS-6 district fact sheets carry no anaemia: those stay null
nf_new5 = {i: {} for i in IND_ALL}; nf_new6 = {i: {} for i in IND_ALL}
nf_src5 = {i: {} for i in IND_ALL}; nf_src6 = {i: {} for i in IND_ALL}
for i in IND_ALL:
    both = N5[i].notna() & N6[i].notna() & (N5[i] > 0)
    rt = (N6[i][both] / N5[i][both]); st_ = pd.Series({l: STATE[l] for l in rt.index})
    rg = rt.groupby(st_).agg(["median", "count"]); rnat = float(rt.median()) if len(rt) else np.nan
    ratio_state = {s: (float(rg.loc[s, "median"]) if (s in rg.index and rg.loc[s, "count"] >= 5) else rnat) for s in set(STATE.values())}
    # NFHS-5 first
    t5 = [int(l) for l in LG if pd.isna(N5[i][l])]
    own6 = [t for t in t5 if not pd.isna(N6[i][t]) and i in N6_AVAILABLE]
    for t in own6:                                          # NFHS-6 observed -> NFHS-5 = NFHS-6 / state ratio
        nf_new5[i][t] = float(N6[i][t] / ratio_state[STATE[t]]); nf_src5[i][t] = "state_ratio_nfhs6"
    rest5 = [t for t in t5 if t not in own6]
    if rest5:
        pre5 = {}
        for t in rest5:
            if t in SPLIT_PARENT and not pd.isna(N5[i].get(SPLIT_PARENT[t])):
                pre5[t] = (float(N5[i][SPLIT_PARENT[t]]), "parent_inherit")
        spat = spatial_fill(N5[i], [t for t in rest5 if t not in pre5])
        for t, (v, s) in {**pre5, **spat}.items():
            nf_new5[i][t] = v; nf_src5[i][t] = s
    # NFHS-6
    if i in N6_AVAILABLE:
        t6 = [int(l) for l in LG if pd.isna(N6[i][l])]
        own5 = [t for t in t6 if not pd.isna(N5[i][t])]
        for t in own5:                                      # NFHS-5 observed -> NFHS-6 = NFHS-5 x state ratio
            nf_new6[i][t] = float(N5[i][t] * ratio_state[STATE[t]]); nf_src6[i][t] = "state_ratio_nfhs5"
        rest6 = [t for t in t6 if t not in own5]
        pre6 = {}
        for t in rest6:
            if t in SPLIT_PARENT and not pd.isna(N6[i].get(SPLIT_PARENT[t])):
                pre6[t] = (float(N6[i][SPLIT_PARENT[t]]), "parent_inherit")
        spat6 = spatial_fill(N6[i], [t for t in rest6 if t not in pre6])
        for t, (v, s) in {**pre6, **spat6}.items():
            if s in ("state_median", "national_median") and t in nf_new5[i]:      # no touching NFHS-6 donor (e.g. Manipur has no NFHS-6 rows): scale the district's (imputed) NFHS-5 instead
                v, s = float(nf_new5[i][t] * ratio_state[STATE[t]]), "state_ratio_nfhs5"
            nf_new6[i][t] = v; nf_src6[i][t] = s
STATS["nfhs_ratio_national"] = {i: round(float((N6[i][N5[i].notna() & N6[i].notna()] / N5[i][N5[i].notna() & N6[i].notna()].replace(0, np.nan)).median()), 3) for i in ("stunting", "wasting", "underweight", "women_bmi_low")}
# write scalar columns and the JSON blocks
SCAL5 = {"stunting": "stunting_nfhs5", "wasting": "wasting_nfhs5", "underweight": "underweight_nfhs5", "child_anaemia": "child_anaemia_nfhs5", "women_anaemia": "women_anaemia_nfhs5"}
SCAL6 = {"stunting": "stunting_nfhs6", "wasting": "wasting_nfhs6", "underweight": "underweight_nfhs6", "child_anaemia": "child_anaemia_nfhs6", "women_anaemia": "women_anaemia_nfhs6"}
for rnd, newd, srcd, scal, jscol, yr in ((5, nf_new5, nf_src5, SCAL5, "nfhs5_json", "2019-21"), (6, nf_new6, nf_src6, SCAL6, "nfhs6_json", "2023-24")):
    js_new = {}; js_src = {}
    for i in IND_ALL:
        for t, v in newd[i].items():
            v = float(round(v, 1))
            path = f"nutrition.nfhs{rnd}.{i}"
            if i in scal:
                put(scal[i], path, t, v, srcd[i][t])
            else:
                IMP[t][path] = srcd[i][t]
            js_new.setdefault(t, {})[i] = v; js_src.setdefault(t, {})[i] = srcd[i][t]
    for t, upd in js_new.items():
        base = json.loads(soc[jscol][t]) if isinstance(soc[jscol][t], str) else {"year": yr}
        for k, v in upd.items():
            if base.get(k) is None:
                base[k] = v
        base["year"] = base.get("year") or yr
        put(jscol, None, t, json.dumps(base), "mixed")
        SRC.setdefault(jscol + "__map", {})[t] = json.dumps(js_src[t])

# ── 7. under-5 children, PDS, census ratios, climate vulnerability ─────────────────────────────────────────────────
u5s = soc.u5_share.astype(float)
fill_ratio("u5_share", None, u5s)
U5S = u5s.copy()
for t, v in VAL.get("u5_share", {}).items():
    U5S[t] = v
c_u5 = soc.children_u5_est.astype(float)
for t in [int(l) for l in LG if pd.isna(c_u5[l])]:
    if not pd.isna(POP26[t]):
        src = SRC.get("population_2026", {}).get(t) or SRC.get("u5_share", {}).get(t, "neighbours_knn")
        put("children_u5_est", "children_u5_est", t, float(round(POP26[t] * U5S[t])), src)
# PDS rice+wheat tonnes (12 m): per-person ratio imputed, tonnes = ratio x population_2026
pds = soc.pds_rice_wheat_t_latest12m.astype(float)
pds_pc = (pds / POP26).where(pds.notna())
for t, (v, s) in fill_ratio("_pds_pc", None, pds_pc).items():
    if not pd.isna(POP26[t]):
        put("pds_rice_wheat_t_latest12m", "food_balance.pds_dependency", t, float(round(v * POP26[t], 1)), s)
VAL.pop("_pds_pc", None); SRC.pop("_pds_pc", None)
for col in ("rural_share", "agri_workers_share", "cultivator_share_workers", "worker_participation", "pop_0_6_share"):
    fill_ratio(col, None, soc[col].astype(float), lo=0.0, hi=1.0)
fill_ratio("clim_vuln_index", "climate.clim_vuln_index", soc.clim_vuln_index.astype(float), lo=0.0)
RURAL = soc.rural_share.astype(float).copy()
for t, v in VAL.get("rural_share", {}).items():
    RURAL[t] = v

# ── 8. consumption side (urban / negligible agriculture / no crops & not a split child) ────────────────────────────
cr_prod = crops.foodgrain_prod_t.astype(float); cr_area = crops.foodgrain_area_ha.astype(float)
has_crops = cr_prod.fillna(0) > 0
no_agri_rule = ((RURAL < 0.05) | (cr_area.fillna(0) < 100)) & has_crops           # same rule as 04_risk (negligible agriculture)
no_crops = ~has_crops
cons: dict[int, str] = {}
for l in LG:
    l = int(l)
    if no_agri_rule[l]:
        cons[l] = "urban_consumption_side"
    elif no_crops[l] and l not in SPLIT_PARENT:
        cons[l] = "urban_consumption_side"
STATS["consumption_side"] = {NAME[l]: s for l, s in cons.items()}
# island districts (no touching donors) are flagged for the report
log(f"consumption-side districts: {len(cons)}; split children without crops: {[NAME[l] for l in SPLIT_PARENT if no_crops[l]]}")

# ── 9. crops: ratio fields, then absolute fields of no-crops split children ────────────────────────────────────────
rural_crop_targets = [int(l) for l in LG if int(l) not in cons]
rf = crops.rainfed_share.astype(float)
nonrural_mask = pd.Series([int(l) in cons for l in LG], index=LG)
obs_rf = rf.copy()
r = fill_ratio("rainfed_share", "crops.rainfed_share", obs_rf, targets=[t for t in rural_crop_targets if pd.isna(rf[t])], lo=0.0, hi=1.0)
for t, (v, s) in r.items():
    put("irrigated_share", "crops.irrigated_share", t, float(round(1 - v, 4)), s)
for col, hi in (("small_marginal_share", 1.0), ("yield_cv10", None), ("simpson_div", 1.0), ("top_crop_share", 1.0)):
    o = crops[col].astype(float)
    fill_ratio(col, f"crops.{col}", o, targets=[t for t in rural_crop_targets if pd.isna(o[t])], lo=0.0, hi=hi)
# top crop name where top_crop_share / structure imputed for a no-crops child: parent's top crop
tc = crops.top_crop.astype(object)
for t in rural_crop_targets:
    if (pd.isna(tc[t]) or tc[t] is None) and t in SPLIT_PARENT and isinstance(tc[SPLIT_PARENT[t]], str):
        put("top_crop", None, t, tc[SPLIT_PARENT[t]], "parent_inherit")
# absolute fields (split children with no crop data): parent x area share
ABS_COLS = ["foodgrain_area_ha", "foodgrain_prod_t", "gross_cropped_area_ha"]
def scaled_json(js, sh, key_area=("area_ha", "prod_t")):
    d = json.loads(js)
    if isinstance(d, dict):
        return json.dumps({k: {kk: (None if vv is None or kk == "yield_t_ha" and False else (vv * sh if kk in key_area else vv)) for kk, vv in v.items()} for k, v in d.items()})
    return json.dumps([{kk: (vv * sh if kk in key_area else vv) for kk, vv in e.items()} for e in d])
for t in [int(l) for l in LG if int(l) in SPLIT_PARENT and no_crops[int(l)]]:
    p_ = SPLIT_PARENT[t]
    if has_crops.get(p_, False):
        sh = SHARE[t]
        for col in ABS_COLS:
            put(col, f"crops.{col}" if col != "foodgrain_area_ha" else None, t, float(round(crops[col][p_] * sh, 1)), "parent_split_area_share")
        put("foodgrain_yield_t_ha", "crops.foodgrain_yield_t_ha", t, float(crops.foodgrain_yield_t_ha[p_]), "parent_inherit")
        IMP[t]["crops.foodgrain_prod_t"] = "parent_split_area_share"; IMP[t]["crops.gross_cropped_area_ha"] = "parent_split_area_share"
        if isinstance(crops.groups_json[p_], str):
            put("groups_json", None, t, scaled_json(crops.groups_json[p_], sh), "parent_split_area_share")
        if isinstance(crops.top_json[p_], str):
            put("top_json", None, t, scaled_json(crops.top_json[p_], sh, ("area_ha",)), "parent_split_area_share")
        for col in ("year", "source", "latest_crop_year", "latest_complete", "latest_stale"):
            put(col, None, t, crops[col][p_], "parent_inherit")
        for col in ("irrigation_year", "small_marginal_year"):
            if col in crops:
                put(col, None, t, crops[col][p_], "parent_inherit")
        IMP[t]["crops"] = "parent_split_area_share"

# ── 10. extra layers: prices, groundwater, Poshan ───────────────────────────────────────────────────────────────
for col, path, lo, hi in (("price_elnino_spike_pct", "markets.price_elnino_spike_pct", None, None), ("price_volatility_idx", "markets.price_volatility_idx", 0.0, 1.0),
                          ("gw_premonsoon_depth_m", "groundwater.premonsoon_depth_m", 0.0, None), ("gw_decline_10y_m_per_yr", "groundwater.decline_m_per_yr", None, None),
                          ("gw_stress_idx", "groundwater.stress_idx", 0.0, 1.0),
                          ("poshan_underweight_pct", "nutrition.poshan_live.underweight_pct", 0.0, 100.0), ("poshan_stunted_pct", "nutrition.poshan_live.stunted_pct", 0.0, 100.0),
                          ("poshan_wasted_pct", "nutrition.poshan_live.wasted_pct", 0.0, 100.0)):
    fill_ratio(col, path, extra[col].astype(float), lo=lo, hi=hi)
pcrop = extra.price_crop.astype(object).where(extra.price_crop.notna())
need_pc = [int(l) for l in LG if int(l) in VAL.get("price_volatility_idx", {}) or int(l) in VAL.get("price_elnino_spike_pct", {})]
need_pc = [t for t in need_pc if pd.isna(pcrop[t]) or pcrop[t] is None]
for t, (v, s) in spatial_fill(pcrop, [t for t in need_pc if t not in SPLIT_PARENT or pd.isna(pcrop.get(SPLIT_PARENT.get(t)))], cat=True).items():
    put("price_crop", None, t, v, s)
for t in [t for t in need_pc if t in SPLIT_PARENT and not pd.isna(pcrop.get(SPLIT_PARENT[t]))]:
    put("price_crop", None, t, pcrop[SPLIT_PARENT[t]], "parent_inherit")
for t in [int(l) for l in LG if pd.isna(extra.gw_n_wells[l]) and (int(l) in VAL.get("gw_stress_idx", {}))]:
    put("gw_source", None, t, "estimated from neighbouring districts", SRC["gw_stress_idx"][t])

# ── 11. island / no-IMD-cell climate from CHIRPS ────────────────────────────────────────────────────────────────────
def clim_from_chirps(l, chirps_row):
    j = np.array([chirps_row.get(f"j{y}", np.nan) for y in YEARS], float); o = np.array([chirps_row.get(f"o{y}", np.nan) for y in YEARS], float)
    ny = [k for k, y in enumerate(YEARS) if NORM0 <= y <= NORM1]
    jn = np.nanmean(j[ny]); on = np.nanmean(o[ny])
    ja = (j - jn) / jn * 100
    oa = np.where(on > 1, (o - on) / on * 100, np.nan)
    ph = enso_phase_by_monsoon_year()
    ysel = lambda p: [k for k, y in enumerate(YEARS) if ph.get(y) == p]
    el, ne, la = (np.nanmean(ja[ysel(p)]) for p in ("El Niño", "Neutral", "La Niña"))
    strong = np.nanmean(ja[[YEARS.index(y) for y in (2002, 2009, 2015)]])
    dprob = float((ja[ysel("El Niño")] < -10).sum() / len(ysel("El Niño")))
    rj = lambda a, nd=1: json.dumps({str(y): (None if not np.isfinite(v) else round(float(v), nd)) for y, v in zip(YEARS, a)})
    return {"jjas_normal_mm": round(float(jn), 1), "elnino_mean_anomaly_pct": round(float(el), 1), "neutral_mean_anomaly_pct": round(float(ne), 1),
            "lanina_mean_anomaly_pct": round(float(la), 1), "strong_elnino_anomaly_pct": round(float(strong), 1), "elnino_deficit_prob": round(dprob, 3),
            "jjas_anomaly_json": rj(ja), "ond_anomaly_json": rj(oa), "latest_year_anomaly_pct": round(float(ja[-1]), 1), "latest_year": 2025}
for l in no_clim:
    row = CHIRPS.get(l)
    if not row or not np.isfinite(row.get(f"j{NORM0}", np.nan)):
        continue
    for col, v in clim_from_chirps(l, row).items():
        put(col, f"climate.{col}" if col not in ("jjas_anomaly_json", "ond_anomaly_json") else "climate.jjas_anomaly_pct" if col.startswith("jjas") else "climate.ond_anomaly_pct", l, v, "ee_chirps")
    IMP[l]["climate"] = "ee_chirps"
# CHIRPS vs IMD validation (yearly JJAS anomaly correlation over a sample of IMD districts)
chv = []
for l, row in CHVAL.items():
    j = np.array([row.get(f"j{y}", np.nan) for y in YEARS], float)
    if not np.isfinite(j).all() or j[:25].mean() <= 0:
        continue
    ja = (j - j[:25].mean()) / j[:25].mean() * 100
    imd = json.loads(clim.jjas_anomaly_json[l]); ia = np.array([imd.get(str(y), np.nan) if imd.get(str(y)) is not None else np.nan for y in YEARS], float)
    ok = np.isfinite(ia)
    if ok.sum() >= 15:
        chv.append((l, float(np.corrcoef(ja[ok], ia[ok])[0, 1]), float(np.mean(np.abs(ja[ok] - ia[ok])))))
STATS["chirps_val"] = pd.DataFrame(chv, columns=["lgd", "r", "mae_pp"]) if chv else None

# ── 12. rabi cropping intensity (NDVI) and rabi structure ───────────────────────────────────────────────────────────
pn18 = panel[panel.crop_year >= 2018].groupby("lgd")[["rabi_fg_area_ha", "kharif_fg_area_ha"]].median().reindex(LG)
rab_share18 = (pn18.rabi_fg_area_ha / (pn18.rabi_fg_area_ha + pn18.kharif_fg_area_ha))
n_yr = panel[panel.crop_year >= 2018].groupby("lgd").rabi_fg_area_ha.apply(lambda x: int((x >= 2000).sum())).reindex(LG).fillna(0)
rab_ok = (pn18.rabi_fg_area_ha >= 2000) & (rab_share18 >= 0.05) & (n_yr >= 3)          # = 04b rabi eligibility (APY rabi share is trustworthy)
nd = pd.DataFrame({"winter": pd.Series({l: (NDVI.get(l) or {}).get("winter") for l in LG}, dtype=float),
                   "delta": pd.Series({l: (NDVI.get(l) or {}).get("delta") for l in LG}, dtype=float),
                   "crop_px": pd.Series({l: (NDVI.get(l) or {}).get("crop_px") for l in LG}, dtype=float)})
nd["share18"] = rab_share18; nd["calib"] = rab_ok & nd.delta.notna()
rabi_cal = {}
if nd.delta.notna().sum() > 100:
    lo_, hi_ = nd.delta.quantile(0.02), nd.delta.quantile(0.98)
    nd["intensity"] = ((nd.delta - lo_) / (hi_ - lo_)).clip(0, 1)
    lo2, hi2 = nd.winter.quantile(0.02), nd.winter.quantile(0.98)
    nd["intensity_win"] = ((nd.winter - lo2) / (hi2 - lo2)).clip(0, 1)
    cal = nd[nd.calib]
    def fit(x, y):
        b, a = np.polyfit(x, y, 1); pred = a + b * x
        return a, b, 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum(), float(np.sqrt(((y - pred) ** 2).mean()))
    def cv(xcol, k=5):
        rs = np.random.RandomState(3); idx = rs.permutation(len(cal)); folds = np.array_split(idx, k); pr_ = np.zeros(len(cal))
        for f in folds:
            tr = np.setdiff1d(idx, f); a, b, _, _ = fit(cal[xcol].values[tr], cal.share18.values[tr]); pr_[f] = a + b * cal[xcol].values[f]
        y = cal.share18.values
        return 1 - ((y - pr_) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    a1, b1, r2_1, rm1 = fit(cal.intensity.values, cal.share18.values); a2, b2, r2_2, rm2 = fit(cal.intensity_win.values, cal.share18.values)
    # spec index = intensity (delta); keep the winter-only index as a reported alternative
    rabi_cal = dict(n=int(len(cal)), a=float(a1), b=float(b1), r2=float(r2_1), rmse=float(rm1), r2_cv5=float(cv("intensity")), r2_winter_only=float(r2_2), r2_cv5_winter_only=float(cv("intensity_win")),
                    rho=float(cal[["intensity", "share18"]].corr(method="spearman").iloc[0, 1]), delta_p2=float(lo_), delta_p98=float(hi_))
    nd["share_est"] = (a1 + b1 * nd.intensity).clip(0.0, 0.9)
    log("rabi NDVI calibration:", {k: round(v, 3) if isinstance(v, float) else v for k, v in rabi_cal.items()})
else:
    nd["intensity"] = np.nan; nd["share_est"] = np.nan
# rabi structure (04_risk reads these names): medians of crop years 2021-23 (prod / pulses / area) and 2018+ (area share, area)
_pn = panel[panel.crop_year.between(2021, 2023)].groupby("lgd")
st2123 = pd.DataFrame({"rab_rabi_prod_t": _pn.rabi_fg_prod_t.median(), "rab_kharif_prod_t": _pn.kharif_fg_prod_t.median(), "rab_rabi_pulses_t": _pn.rabi_pulses_prod_t.median(),
                       "rab_rabi_area_ha": _pn.rabi_fg_area_ha.median()}).reindex(LG)
st2123["rab_rabi_area_ha_18"] = pn18.rabi_fg_area_ha; st2123["rab_rabi_share_area_18"] = rab_share18
RAB_IMP: dict[int, str] = {}
fg_area = cr_area.copy(); fg_prod = cr_prod.copy()
for col in ("foodgrain_area_ha", "foodgrain_prod_t"):
    for t, v in VAL.get(col, {}).items():
        (fg_area if col == "foodgrain_area_ha" else fg_prod)[t] = v
pulses_prod = pd.Series({l: (json.loads(crops.groups_json[l]).get("pulses") or {}).get("prod_t") if isinstance(crops.groups_json[l], str) else np.nan for l in LG}, dtype=float)
def set_rabi(t, share, src, kind):
    """override the rabi structure of district t with a rabi AREA share (production share = area share: rabi / kharif yields not separable here)"""
    fa, fp = fg_area.get(t, np.nan), fg_prod.get(t, np.nan)
    if pd.isna(fa) or pd.isna(fp) or pd.isna(share):
        return False
    RAB_IMP[t] = src
    put("rab_rabi_area_ha_18", None, t, float(share * fa), src)
    put("rab_rabi_share_area_18", None, t, float(share), src)
    put("rab_rabi_area_ha", None, t, float(share * fa), src)
    put("rab_rabi_prod_t", "season_context.rabi.foodgrain_prod_t", t, float(share * fp), src)
    put("rab_kharif_prod_t", None, t, float((1 - share) * fp), src)
    pp = pulses_prod.get(t, np.nan)
    if not pd.isna(pp):
        put("rab_rabi_pulses_t", None, t, float(share * pp), src)
    IMP[t]["season_context.rabi.share_of_foodgrain_prod"] = src
    return True
# (a) split children without own crop panel: the parent's rabi share (observed), (b) label-gap districts (< 3 crop years with >= 2000 ha rabi area): NDVI map, else neighbours
# the 04b / 04_risk reason split: negligible (stable rabi data, small) vs season-label gap (rabi_area >= 2000 in some years, < 3 years) -> reproduce it exactly
def rabi_reason_of(l):
    a = pn18.rabi_fg_area_ha[l]; s = rab_share18[l]
    if pd.isna(a) or a < 2000 or pd.isna(s) or s < 0.05:
        return "negligible_rabi_foodgrain"
    return "rabi_season_label_gap" if n_yr[l] < 3 else "eligible"
gap_ids = [int(l) for l in LG if has_crops[l] and l not in cons and rabi_reason_of(int(l)) == "rabi_season_label_gap"]
neg_ids = [int(l) for l in LG if has_crops[l] and l not in cons and rabi_reason_of(int(l)) == "negligible_rabi_foodgrain"]
child_ids = [int(l) for l in LG if int(l) in SPLIT_PARENT and no_crops[int(l)]]
share_obs = rab_share18.copy()
for t in child_ids:                     # (a)
    p_ = SPLIT_PARENT[t]
    if not pd.isna(rab_share18.get(p_)):
        set_rabi(t, float(rab_share18[p_]), "parent_split_area_share", "child")
RAB_SUMMARY = []
for t in gap_ids:                       # (b)
    est = nd.share_est.get(t, np.nan)
    if not pd.isna(est):
        obs_ = rab_share18.get(t, np.nan)
        est = float(max(est, obs_)) if not pd.isna(obs_) else float(est)         # APY under-reports rabi in label-gap districts: the APY share is a lower bound
        ok = set_rabi(t, est, "ee_rabi_ndvi", "gap"); how = "ee_rabi_ndvi"
    else:
        v, s = spatial_fill(rab_share18.where(rab_ok), [t])[t]; ok = set_rabi(t, v, s, "gap"); how = s
        est = v
    RAB_SUMMARY.append((t, NAME[t], STATE[t], "label_gap", float(rab_share18.get(t, np.nan)), float(nd.intensity.get(t, np.nan)), float(est), how))
for t in neg_ids:                       # (c) negligible rabi: APY value is small but measured (R2 of the NDVI map is too low to overrule it) -> kept; intensity reported only
    est = nd.share_est.get(t, np.nan); obs_ = rab_share18.get(t, np.nan)
    RAB_SUMMARY.append((t, NAME[t], STATE[t], "negligible", float(obs_), float(nd.intensity.get(t, np.nan)), float(est) if not pd.isna(est) else np.nan, "kept observed"))
STATS["rabi_summary"] = pd.DataFrame(RAB_SUMMARY, columns=["lgd", "district", "state", "kind", "apy_share", "ndvi_intensity", "est_share", "how"])
STATS["rabi_cal"] = rabi_cal
log(f"rabi structure imputed: {len(RAB_IMP)} districts (children {len(child_ids)}, gap {len(gap_ids)}, negligible "
    f"{0} of {len(neg_ids)} negligible kept as observed)")

# ── 13. leave-one-out validation of the neighbour method (observed districts, masked one at a time) ───────────────────
def loo(col, obs: pd.Series, n_max=450):
    have = obs.dropna()
    ids = list(have.index)
    rs = np.random.RandomState(11)
    if len(ids) > n_max:
        ids = list(rs.choice(ids, n_max, replace=False))
    pred, base_st, truth, srcs = [], [], [], []
    st_all = pd.Series({l: STATE[l] for l in have.index})
    for t in ids:
        o2 = obs.copy(); o2[t] = np.nan
        v, s = spatial_fill(o2, [t])[t]
        pred.append(v); truth.append(float(obs[t])); srcs.append(s)
        same = have[(st_all == STATE[t]) & (have.index != t)]
        base_st.append(float(same.median()) if len(same) >= 3 else float(have[have.index != t].median()))
    pred, truth, base_st = np.array(pred), np.array(truth), np.array(base_st)
    nat = float(have.median())
    from scipy.stats import spearmanr
    return dict(field=col, n=len(ids), rho=float(spearmanr(pred, truth)[0]), mae=float(np.abs(pred - truth).mean()), mae_state_median=float(np.abs(base_st - truth).mean()),
                mae_national=float(np.abs(nat - truth).mean()), pct_knn=float(np.mean([s == "neighbours_knn" for s in srcs])))
LOO_FIELDS = {"stunting_nfhs5": N5["stunting"], "wasting_nfhs5": N5["wasting"], "underweight_nfhs5": N5["underweight"], "child_anaemia_nfhs5": N5["child_anaemia"],
              "stunting_nfhs6": N6["stunting"], "women_bmi_low_nfhs6": N6["women_bmi_low"],
              "rainfed_share": crops.rainfed_share.astype(float), "small_marginal_share": crops.small_marginal_share.astype(float), "yield_cv10": crops.yield_cv10.astype(float),
              "top_crop_share": crops.top_crop_share.astype(float), "simpson_div": crops.simpson_div.astype(float),
              "price_volatility_idx": extra.price_volatility_idx.astype(float), "price_elnino_spike_pct": extra.price_elnino_spike_pct.astype(float),
              "gw_premonsoon_depth_m": extra.gw_premonsoon_depth_m.astype(float), "gw_decline_10y_m_per_yr": extra.gw_decline_10y_m_per_yr.astype(float),
              "gw_stress_idx": extra.gw_stress_idx.astype(float), "poshan_underweight_pct": extra.poshan_underweight_pct.astype(float),
              "clim_vuln_index": soc.clim_vuln_index.astype(float), "pds_per_person_t": pds_pc}
LOO = pd.DataFrame([loo(k, v) for k, v in LOO_FIELDS.items()])
log("LOO done")

# ── 14. outputs ─────────────────────────────────────────────────────────────────────────────────────────────────────
cols = sorted(c for c in VAL if not c.startswith("_"))
out = pd.DataFrame(index=pd.Index(LG, name="lgd"))
for c in cols:
    s = pd.Series(VAL[c]); s.index = s.index.astype(int)
    try:
        out[c] = pd.to_numeric(s.reindex(LG), errors="raise")
    except (ValueError, TypeError):
        out[c] = s.reindex(LG).astype(object)
    out[c + "__src"] = pd.Series(SRC[c]).reindex(LG)
for c in list(SRC):
    if c.endswith("__map"):
        out[c] = pd.Series(SRC[c]).reindex(LG)
out["worldpop_2020"] = (wp20_raw if wp_cross else wp20).reindex(LG).values
out["worldpop_2020_calibrated"] = wp20.reindex(LG).values
out["rabi_ndvi_intensity"] = nd.intensity.reindex(LG).values if "intensity" in nd else np.nan
out["rabi_ndvi_winter"] = nd.winter.reindex(LG).values
out["rabi_ndvi_delta"] = nd.delta.reindex(LG).values
out["rabi_share_est_ndvi"] = nd.share_est.reindex(LG).values
out["rabi_structure_src"] = pd.Series(RAB_IMP).reindex(LG)
out.reset_index().to_parquet(ART / "imputed_district.parquet")
imp_json = {"meta": {"generated": pd.Timestamp.now().isoformat(timespec="seconds"), "ee": EE["ok"], "ee_note": EE["why"], "adjacency_buffer_m": BUF_M},
            "districts": {str(l): v for l, v in IMP.items() if v}, "consumption_side": {str(l): s for l, s in cons.items()},
            "split_parent": {str(c): int(p) for c, p in SPLIT_PARENT.items()}, "split_area_share": {str(c): round(s, 4) for c, s in SHARE.items()},
            "rabi_structure": {str(l): s for l, s in RAB_IMP.items()}}
save_json(imp_json, ART / "imputed_district.json")
log(f"wrote imputed_district.parquet {out.shape} and imputed_district.json ({sum(1 for v in IMP.values() if v)} districts, {sum(len(v) for v in IMP.values())} imputed entries)")

# ── 15. report ─────────────────────────────────────────────────────────────────────────────────────────────────────
src_by_path = {}
for l, d_ in IMP.items():
    for p_, s_ in d_.items():
        src_by_path.setdefault(p_, {}).setdefault(s_, 0); src_by_path[p_][s_] += 1
L = ["# 03c impute report", "",
     f"Run {pd.Timestamp.now().date()} | {sum(1 for v in IMP.values() if v)} of {len(LG)} districts have at least one imputed field; {sum(len(v) for v in IMP.values())} (district, field) entries; "
     f"Earth Engine {'used' if EE['ok'] or WP else 'NOT used (' + str(EE['why']) + ')'}.", "",
     "Observed values are never overwritten: `04_risk.py` / `06_export.py` fill only where the source layer is null. Every entry is flagged in `data_quality.imputed` (SCHEMA Addendum G).", "",
     "## Imputed entries by field and source", "", "| field (schema path) | imputed | sources |", "|---|---|---|"]
for p_ in sorted(src_by_path, key=lambda k: -sum(src_by_path[k].values())):
    L.append(f"| `{p_}` | {sum(src_by_path[p_].values())} | " + ", ".join(f"{s} {n}" for s, n in sorted(src_by_path[p_].items(), key=lambda x: -x[1])) + " |")
L += ["", "## Methods and validation", ""]
L += ["### 1. Neighbour method (adjacency: polygons touching within 500 m, `artifacts/_adjacency.json`)", "",
      f"Donors are districts with an OBSERVED value; median weighted by shared border length (simple mean when <= 2 donors); order: touching same state -> touching any state -> 2-hop same state -> state median (>= 3 donors) -> national median. "
      f"Mean {np.mean([len(v) for v in ADJ.values()]):.1f} touching districts; no touching donors (island): {', '.join(NAME[l] for l, v in ADJ.items() if not v)}.", "",
      "Leave-one-out check (each observed district masked in turn and re-estimated from its neighbours; `pct_knn` = share estimated from touching districts). MAE of the neighbour estimate vs the state-median and national-median baselines:", "",
      "| field | n | Spearman rho | MAE neighbours | MAE state median | MAE national median | pct touching |", "|---|---|---|---|---|---|---|"]
for r_ in LOO.itertuples():
    L.append(f"| {r_.field} | {r_.n} | {r_.rho:.2f} | {r_.mae:.3g} | {r_.mae_state_median:.3g} | {r_.mae_national:.3g} | {r_.pct_knn:.0%} |")
L += ["", "Read: rho well above 0 and MAE below the baselines = neighbours carry information (nutrition, rainfed share, groundwater); rho near 0 / no gain over the state median = the layer is spatially noisy (price indices, yield CV, top-crop share) - those imputations are close to a regional median and should be read as 'typical for the area', not as local estimates.", ""]
if wp_cross:
    L += ["### 2. Population: WorldPop 2020 (Earth Engine `WorldPop/GP/100m/pop`, sum per polygon)", "",
          f"Cross-check on {wp_cross['n']} districts (not split parents/children; census 2011 x state factor^(9/15) = census-based 2020): Pearson r = {wp_cross['pearson_linear']:.3f} (log-log {wp_cross['pearson_log']:.3f}); "
          f"vs census-based 2026 (WorldPop x state factor^(6/15)): log-log r = {wp_cross['pearson_log_pop26']:.3f}; median ratio WorldPop-2020 / census-2020 = {wp_cross['median_ratio_wp_over_census']:.3f} "
          f"(p10 {wp_cross['p10']:.2f}, p90 {wp_cross['p90']:.2f}); median ratio WorldPop-2026 / census-2026 = {wp_cross['median_ratio_wp26_over_census26']:.3f}. "
          f"All-India WorldPop sum {wp_cross['total_wp_M']} M (polygons incl. split children; PoK excluded).",
          "", f"{len(pop_targets)} districts had no census population (22 post-2011 districts): population_2011 = WorldPop / g^(9/15), population_2026 = WorldPop x g^(6/15) with g = state 2026/2011 factor. "
          f"WorldPop is scaled by the state median census/WorldPop ratio (national {wp_cross['national_calibration']:.3f} where a state has < 5 comparable districts) before use: median WorldPop/census after calibration {wp_cross['median_ratio_after_calibration']:.3f}. "
          "Columns `worldpop_2020` (raw) and `worldpop_2020_calibrated` are in `imputed_district.parquet` for ALL districts.", ""]
    if STATS.get("pop_split_all") is not None and len(STATS["pop_split_all"]):
        t_ = STATS["pop_split_all"].copy(); t_["ratio_areashare_over_wp"] = t_.parent_area_share_2026 / t_.worldpop_2026
        L += ["Validation of the parent area-share split (method 2) against WorldPop for the split children (parent census 2026 x area share vs WorldPop 2026):", "",
              "| district | parent | WorldPop 2026 | parent x area share | census 2026 (if any) | area-share / WorldPop |", "|---|---|---|---|---|---|"]
        for r_ in t_.itertuples():
            L.append(f"| {r_.district} | {r_.parent} | {r_.worldpop_2026:,.0f} | {r_.parent_area_share_2026:,.0f} | {'' if pd.isna(r_.census_2026) else f'{r_.census_2026:,.0f}'} | {r_.ratio_areashare_over_wp:.2f} |")
        L += ["", f"Median area-share / WorldPop = {t_.ratio_areashare_over_wp.median():.2f} (spread p10-p90 {t_.ratio_areashare_over_wp.quantile(.1):.2f}-{t_.ratio_areashare_over_wp.quantile(.9):.2f}): area share is a poor proxy for population share "
              "(hill vs plain split), which is why WorldPop is preferred for population and the area-share rule is used only for crop quantities.", ""]
if STATS.get("rabi_cal"):
    rc = STATS["rabi_cal"]
    L += ["### 3. Rabi cropping intensity (MODIS MOD13Q1 NDVI x WorldCover v200 cropland)", "",
          f"Index = mean over winters 2021-22..2024-25 of [Dec-Feb mean NDVI - Sep-Oct minimum NDVI], cropland-fraction weighted per district, rescaled to 0-1 between the 2nd and 98th percentile (`rabi_ndvi_intensity`, all districts). "
          f"Linear map `rabi area share = {rc['a']:.3f} + {rc['b']:.3f} x intensity` fitted on {rc['n']} districts with trustworthy APY rabi shares (= the rabi-eligible set): **R2 = {rc['r2']:.2f}** (5-fold CV R2 {rc['r2_cv5']:.2f}, "
          f"RMSE {rc['rmse']:.3f}, Spearman {rc['rho']:.2f}); winter-mean-only index R2 {rc['r2_winter_only']:.2f} (CV {rc['r2_cv5_winter_only']:.2f}).", ""]
    rs = STATS["rabi_summary"]
    if len(rs):
        L += [f"Imputed rabi structure: {int((rs.kind == 'label_gap').sum())} season-label-gap districts get max(APY share, NDVI estimate) (APY under-reports rabi where the season labels are missing); "
              f"the {int((rs.kind == 'negligible').sum())} negligible-rabi districts keep their small but measured APY rabi area (an R2 of {rc['r2']:.2f} cannot overrule it; the map's intercept alone gives {rc['a']:.0%}); their NDVI intensity is stored for reference. "
              "Rabi production share is set equal to the area share (rabi/kharif yields are not separable for these districts).", "",
              "Season-label-gap districts:", "", "| district | state | APY rabi share | NDVI intensity | imputed share | method |", "|---|---|---|---|---|---|"]
        for r_ in rs[rs.kind == "label_gap"].itertuples():
            L.append(f"| {r_.district} | {r_.state} | {'' if pd.isna(r_.apy_share) else f'{r_.apy_share:.2f}'} | {r_.ndvi_intensity:.2f} | {r_.est_share:.2f} | {r_.how} |")
        L += [""]
cv_ = STATS.get("chirps_val")
if len(no_clim):
    L += ["### 4. Island climate (CHIRPS v2 daily, JJAS and OND sums 2000-2025, polygons buffered 0.1 deg)", "",
          "Districts without IMD cells: " + ", ".join(NAME[l] for l in no_clim) + (". CHIRPS" if CHIRPS else ". CHIRPS NOT available") + " normal = 2000-2024 mean, anomalies as in 02_climate; temperature layers stay null (rabi terminal-heat term dropped for them).", ""]
    if cv_ is not None and len(cv_):
        L += [f"CHIRPS vs IMD, yearly JJAS anomaly over {len(cv_)} sample districts: mean r = {cv_.r.mean():.2f} (median {cv_.r.median():.2f}), mean abs diff {cv_.mae_pp.mean():.1f} pp (IMD vs CHIRPS differ most for the small-polygon / mountain districts).", ""]
L += ["### 5. Parent inheritance (post-2011 splits; polygons are post-split, parents shrank, nothing overlaps)", "",
      "| child | parent | area share of pre-split territory |", "|---|---|---|"]
for c_, p_ in SPLIT_PARENT.items():
    L.append(f"| {NAME[c_]} | {NAME[p_]} | {SHARE[c_]:.2f} |")
L += ["", "Ratio fields (NFHS, shares, prices, groundwater) are inherited; absolute fields (foodgrain production / area, gross cropped area, rabi structure) = parent x area share and only for the split children that have no crop data of their own. "
      "Parents are NOT reduced: their census population / crop totals remain the pre-split values (known caveat, unchanged).", "",
      "### 6. Consumption side (declared here, scored in 04_risk.py)", "",
      f"{len(cons)} districts: " + ", ".join(sorted(NAME[l] for l in cons)) + ". Crop-structure fields are NOT imputed for them (no cropping to describe); exposure comes from the surrounding districts, sensitivity from supply and PDS dependency only.", ""]
(ART / "reports").mkdir(exist_ok=True)
(ART / "reports" / "03c_impute_report.md").write_text("\n".join(L) + "\n\n<!-- 06_export -->\n")
log("report written; done")
