"""05_gee_live.py - Earth Engine "live signals" per district for AnnaDrishti.

Output: artifacts/gee_live.json
  {"as_of", "sources", "districts": {lgd: {ndvi_anom, chirps_30d_mm, chirps_30d_anom_pct,
                                           soilm_anom, wn_10d_rain_mm, wn_10d_tmax_c, wn_init}}}

Each layer is computed by reduceRegions per state chunk (inline FeatureCollection, geometries simplified)
and cached in artifacts/_gee_cache/{layer}_{as_of}.json, so reruns on the same day are instant.
Values that cannot be computed are null; nothing is imputed.

Usage: python3 pipeline/05_gee_live.py [--refresh] [--wn-members N]
"""
from __future__ import annotations
import argparse, datetime as dt, json, sys, time, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ee
import geopandas as gpd
from common import districts, GEOJSON, ART, save_json

EE_PROJECT = "ee-chvi"
CACHE = ART / "_gee_cache"
WN2 = "projects/gcp-public-data-weathernext/assets/weathernext_2_0_0"       # WeatherNext 2 (64-member, 6-hourly)
WN_GEN = "projects/gcp-public-data-weathernext/assets/126478713_1_0"        # WeatherNext Gen (deprecated, ends 2026-07-29)
WN_GRAPH = "projects/gcp-public-data-weathernext/assets/59572747_4_0"       # WeatherNext Graph (deprecated)
SIMPLIFY_DEG = 0.005
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


# ── geometry ──────────────────────────────────────────────────────────────────
def build_state_chunks() -> dict[int, list[dict]]:
    """{state_lgd: [geojson Feature with only lgd]} using simplified geometries."""
    master = districts()
    gdf = gpd.read_file(GEOJSON)
    gdf = gdf[gdf["Dist_LGD"].fillna(0).astype(int) > 0].drop_duplicates("Dist_LGD")
    gdf["lgd"] = gdf["Dist_LGD"].astype(int)
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_DEG, preserve_topology=True)
    gdf = gdf[~gdf.geometry.is_empty]
    st = dict(zip(master.lgd, master.state_lgd))
    chunks: dict[int, list[dict]] = {}
    for lgd, geom in zip(gdf["lgd"], gdf.geometry):
        feat = {"type": "Feature", "properties": {"lgd": int(lgd)}, "geometry": json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]}
        chunks.setdefault(int(st[lgd]), []).append(feat)
    # split big states so each request stays small
    out, k = {}, 0
    for s, feats in chunks.items():
        for i in range(0, len(feats), 40):
            out[k] = feats[i:i + 40]; k += 1
    return out


def to_fc(feats):
    return ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"], None, False), f["properties"]) for f in feats])


def retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1) ** 2)
            log("  retry after:", str(e)[:120])


def reduce_all(image, chunks, scale, reducer=None, workers=4, tile_scale=4):
    """reduceRegions per chunk -> {lgd: {band: value}}."""
    reducer = reducer or ee.Reducer.mean()

    def one(feats):
        def go():
            fc = image.reduceRegions(collection=to_fc(feats), reducer=reducer, scale=scale, tileScale=tile_scale)
            return fc.getInfo()["features"]
        return retry(go)

    res = {}
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(one, f): i for i, f in chunks.items()}
        for n, fu in enumerate(as_completed(futs), 1):
            for f in fu.result():
                p = f["properties"]
                res[int(p["lgd"])] = {k: v for k, v in p.items() if k != "lgd"}
            if n % 10 == 0 or n == len(futs):
                log(f"  chunks {n}/{len(futs)}")
    return res


def cached(layer, as_of, fn, refresh):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{layer}_{as_of}.json"
    if p.exists() and not refresh:
        log(f"{layer}: cache hit")
        return json.load(open(p))
    log(f"{layer}: computing")
    save_json(fn(), p)
    return json.load(open(p))   # round-trip so int keys are str, same as on a cache hit


def _date(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).replace(tzinfo=None)


def latest(coll_id, since):
    t = ee.ImageCollection(coll_id).filterDate(since, "2100-01-01").aggregate_max("system:time_start").getInfo()
    return _date(t)


def shift_years(d: dt.datetime, y: int) -> dt.datetime:
    try:
        return d.replace(year=d.year + y)
    except ValueError:  # Feb 29
        return d.replace(year=d.year + y, day=28)


def window_climatology(coll, start: dt.datetime, end: dt.datetime, years, agg):
    """Mean over `years` of agg(window) where window = [start,end) shifted to that year."""
    ims = []
    for y in years:
        off = y - start.year
        s, e = shift_years(start, off), shift_years(end, off)
        ims.append(agg(coll.filterDate(s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"))))
    return ee.ImageCollection(ims).mean()


# ── layers ────────────────────────────────────────────────────────────────────
def layer_ndvi(chunks):
    d = latest("MODIS/061/MOD13Q1", "2026-01-01")
    end = d + dt.timedelta(days=1)
    start = end - dt.timedelta(days=32)
    coll = ee.ImageCollection("MODIS/061/MOD13Q1").select("NDVI")
    cur = coll.filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")).mean().rename("cur")
    clim = window_climatology(coll, start, end, range(2015, 2025), lambda c: c.mean()).rename("clim")
    res = reduce_all(cur.addBands(clim), chunks, 1000)
    out = {}
    for lgd, v in res.items():
        c, m = v.get("cur"), v.get("clim")
        out[lgd] = (c - m) / m if (c is not None and m is not None and m > 500) else None  # NDVI x10000; m>0.05
    meta = {"latest_composite": d.strftime("%Y-%m-%d"), "window": [start.strftime("%Y-%m-%d"), (end - dt.timedelta(days=1)).strftime("%Y-%m-%d")], "clim_years": "2015-2024"}
    return {"meta": meta, "values": out}


def layer_chirps(chunks):
    d = latest("UCSB-CHG/CHIRPS/DAILY", "2026-01-01")
    end = d + dt.timedelta(days=1)
    start = end - dt.timedelta(days=30)
    coll = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
    cur = coll.filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")).sum().rename("cur")
    clim = window_climatology(coll, start, end, range(2001, 2025), lambda c: c.sum()).rename("clim")
    res = reduce_all(cur.addBands(clim), chunks, 5566)
    out = {}
    for lgd, v in res.items():
        c, m = v.get("cur"), v.get("clim")
        out[lgd] = {"mm": c,
                    "anom_pct": (c - m) / m * 100 if (c is not None and m is not None and m >= 5) else None}  # m<5 mm: % meaningless
    meta = {"window": [start.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")], "clim_years": "2001-2024"}
    return {"meta": meta, "values": out}


def layer_soilm(chunks):
    d = latest("ECMWF/ERA5_LAND/MONTHLY_AGGR", "2026-01-01")
    coll = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").select("volumetric_soil_water_layer_1")
    cur = coll.filterDate(d.strftime("%Y-%m-%d"), (d + dt.timedelta(days=1)).strftime("%Y-%m-%d")).first()
    hist = ee.ImageCollection([coll.filterDate(f"{y}-{d.month:02d}-01", f"{y}-{d.month:02d}-02").first() for y in range(2001, 2025)]).mean()
    img = cur.rename("cur").addBands(hist.rename("clim"))
    res = reduce_all(img, chunks, 11132)
    out = {lgd: (v["cur"] - v["clim"] if v.get("cur") is not None and v.get("clim") is not None else None) for lgd, v in res.items()}
    return {"meta": {"month": d.strftime("%Y-%m"), "clim_years": "2001-2024", "units": "m3/m3 (absolute anomaly)"}, "values": out}


def pick_wn_init(asset, lead_hours, step):
    """Latest init time (from the last ~5 days) for which every lead 0<h<=lead_hours is present (complete run)."""
    coll = ee.ImageCollection(asset)
    now = dt.datetime.utcnow()
    recent = coll.filterDate((now - dt.timedelta(days=6)).strftime("%Y-%m-%d"), (now + dt.timedelta(days=1)).strftime("%Y-%m-%d"))
    inits = sorted(set(recent.aggregate_array("start_time").getInfo()), reverse=True)
    need = lead_hours // step
    for init in inits:
        fh = ee.ImageCollection(asset).filter(ee.Filter.eq("start_time", init)).aggregate_array("forecast_hour").distinct().getInfo()
        if sum(1 for h in fh if 0 < h <= lead_hours) >= need:
            return init
    return None


def layer_wn(chunks, n_members):
    # try WeatherNext 2 first (the only non-deprecated asset with current data), then Gen, then Graph
    for name, asset, pband, step in (("WeatherNext 2", WN2, "total_precipitation_6hr", 6),
                                      ("WeatherNext Gen", WN_GEN, "total_precipitation_12hr", 12),
                                      ("WeatherNext Graph", WN_GRAPH, "total_precipitation_6hr", 6)):
        init = retry(lambda: pick_wn_init(asset, 240, step))
        if init:
            break
    else:
        raise RuntimeError("no WeatherNext init available")
    log(f"WeatherNext: using {name} init {init}")
    base = ee.ImageCollection(asset).filter(ee.Filter.eq("start_time", init)).filter(ee.Filter.And(ee.Filter.gt("forecast_hour", 0), ee.Filter.lte("forecast_hour", 240)))
    has_members = name != "WeatherNext Graph"
    if has_members:
        allm = sorted(base.aggregate_array("ensemble_member").distinct().getInfo(), key=int)
        k = len(allm) if n_members <= 0 else min(n_members, len(allm))
        # evenly spread subset of members
        members = [allm[int(i * len(allm) / k)] for i in range(k)]
    else:
        members = [None]
    log(f"  members used: {len(members)}")
    rain_sum = ee.ImageCollection([base.filter(ee.Filter.eq("ensemble_member", m)).select(pband).sum() for m in members]).mean() if has_members \
        else base.select(pband).sum()
    tmax = ee.ImageCollection([base.filter(ee.Filter.eq("ensemble_member", m)).select("2m_temperature").max() for m in members]).mean() if has_members \
        else base.select("2m_temperature").max()
    img = rain_sum.multiply(1000).rename("rain_mm").addBands(tmax.subtract(273.15).rename("tmax_c"))   # precip in metres, T in K
    res = reduce_all(img, chunks, 27830, workers=3)
    out = {lgd: {"rain_mm": v.get("rain_mm"), "tmax_c": v.get("tmax_c")} for lgd, v in res.items()}
    meta = {"model": name, "asset": asset, "init": init, "lead_hours": [step, 240], "members_used": len(members),
            "aggregation": "mean over members of per-member (sum of precip leads<=240h; max of 6h-instantaneous 2m T)" if has_members else "deterministic"}
    return {"meta": meta, "values": out}


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--wn-members", type=int, default=0, help="0 = all members")
    a = ap.parse_args()
    as_of = dt.date.today().isoformat()
    ee.Initialize(project=EE_PROJECT)
    log("as_of", as_of)
    chunks = build_state_chunks()
    master = districts()
    all_lgd = [int(x) for x in master.lgd]
    log(f"chunks={len(chunks)}, features={sum(len(v) for v in chunks.values())}, payload~{len(json.dumps(chunks)) / 1e6:.1f} MB total")

    ndvi = cached("ndvi", as_of, lambda: layer_ndvi(chunks), a.refresh)
    chirps = cached("chirps", as_of, lambda: layer_chirps(chunks), a.refresh)
    soil = cached("soilm", as_of, lambda: layer_soilm(chunks), a.refresh)
    wn = cached("weathernext", as_of, lambda: layer_wn(chunks, a.wn_members), a.refresh)

    g = lambda d, k: d["values"].get(str(k))
    rnd = lambda x, n: None if x is None else round(float(x), n)
    dist = {}
    for lgd in all_lgd:
        w = g(wn, lgd) or {}
        c = g(chirps, lgd) or {}
        dist[str(lgd)] = {
            "ndvi_anom": rnd(g(ndvi, lgd), 4),
            "chirps_30d_mm": rnd(c.get("mm"), 1),
            "chirps_30d_anom_pct": rnd(c.get("anom_pct"), 1),
            "soilm_anom": rnd(g(soil, lgd), 4),
            "wn_10d_rain_mm": rnd(w.get("rain_mm"), 1),
            "wn_10d_tmax_c": rnd(w.get("tmax_c"), 1),
            "wn_init": wn["meta"]["init"] if w.get("rain_mm") is not None or w.get("tmax_c") is not None else None,
        }
    out = {
        "as_of": as_of,
        "sources": {
            "ndvi_anom": {"dataset": "MODIS/061/MOD13Q1 NDVI", "units": "fraction vs mean", **ndvi["meta"],
                          "note": "(latest 32-day mean - same-window mean 2015-2024)/same-window mean; 1 km reduce"},
            "chirps_30d": {"dataset": "UCSB-CHG/CHIRPS/DAILY precipitation", **chirps["meta"],
                           "note": "30-day sum (mm) and % anomaly vs same window mean 2001-2024; anom null where climatology < 5 mm"},
            "soilm_anom": {"dataset": "ECMWF/ERA5_LAND/MONTHLY_AGGR volumetric_soil_water_layer_1", **soil["meta"],
                           "note": "SMAP SPL4SMGP/007 deprecated/empty; ERA5-Land used instead"},
            "weathernext": {"dataset": wn["meta"]["asset"], **wn["meta"]},
        },
        "districts": dist,
    }
    save_json(out, ART / "gee_live.json")
    write_report(out, all_lgd, master)
    log("wrote", ART / "gee_live.json")


def write_report(out, all_lgd, master):
    import numpy as np
    fields = ["ndvi_anom", "chirps_30d_mm", "chirps_30d_anom_pct", "soilm_anom", "wn_10d_rain_mm", "wn_10d_tmax_c", "wn_init"]
    d = out["districts"]
    rows = []
    for f in fields[:-1]:
        v = np.array([d[str(l)][f] for l in all_lgd if d[str(l)][f] is not None], dtype=float)
        rows.append(f"| {f} | {len(v)}/{len(all_lgd)} | {v.mean():.3f} | {np.median(v):.3f} | {v.min():.3f} | {v.max():.3f} |" if len(v) else f"| {f} | 0/{len(all_lgd)} | - | - | - | - |")
    nn = sum(1 for l in all_lgd if d[str(l)]["wn_init"])
    names = master.set_index("lgd")
    samp = [486, 673, 191, 502, 441]
    srows = []
    for l in samp:
        if str(l) in d:
            v = d[str(l)]
            srows.append(f"| {l} | {names.loc[l,'district']} ({names.loc[l,'state']}) | " + " | ".join(str(v[f]) for f in fields[:-1]) + " |")
    rt = time.time() - T0
    md = f"""# 05_gee_live report

Generated {dt.datetime.now().isoformat(timespec='seconds')} - as_of {out['as_of']} - runtime of this invocation {rt:.0f}s (cached layers make reruns near-instant).

## Coverage and India-wide (unweighted district) stats
| field | non-null | mean | median | min | max |
|---|---|---|---|---|---|
{chr(10).join(rows)}
| wn_init | {nn}/{len(all_lgd)} | - | - | - | - |

## WeatherNext
{json.dumps(out['sources']['weathernext'], indent=2)}

## Other sources
```
{json.dumps({k: v for k, v in out['sources'].items() if k != 'weathernext'}, indent=2)}
```

## Sample districts
| lgd | district | {' | '.join(fields[:-1])} |
|---|---|{'---|' * (len(fields) - 1)}
{chr(10).join(srows)}
"""
    p = ART / "reports" / "05_gee_report.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md)


if __name__ == "__main__":
    main()
