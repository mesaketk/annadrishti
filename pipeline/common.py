"""Shared helpers for the AnnaDrishti pipeline. All scripts import from here.

Join key everywhere is the LGD district code (`lgd`, int) = `Dist_LGD` in INDIA_DISTRICTS.geojson
= `district_code` in every India Data Portal CSV (APY, UPAG, NFHS, PDS, census PCA, climate vulnerability).
"""
from __future__ import annotations
import json, os, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "datasets"
ART = ROOT / "artifacts"
GEOJSON = ROOT / "INDIA_DISTRICTS.geojson"
ART.mkdir(exist_ok=True); (ART / "timeseries").mkdir(exist_ok=True)

# ── district master ────────────────────────────────────────────────────────────
def districts() -> pd.DataFrame:
    """One row per polygon: lgd, district, state, census11, centroid_lon, centroid_lat.
    Two PoK polygons (Mirpur, Muzaffarabad) share Dist_LGD=0 and are dropped."""
    cache = ART / "_districts_master.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    from shapely.geometry import shape
    g = json.load(open(GEOJSON))
    rows = []
    for f in g["features"]:
        p = f["properties"]
        if not p.get("Dist_LGD"):
            continue
        c = shape(f["geometry"]).representative_point()
        rows.append(dict(lgd=int(p["Dist_LGD"]), district=p["dtname"], state=p["stname"].title(),
                         state_lgd=int(p["State_LGD"]), census11=str(p["dtcode11"]),
                         centroid_lon=round(c.x, 3), centroid_lat=round(c.y, 3)))
    df = pd.DataFrame(rows).drop_duplicates("lgd").sort_values("lgd").reset_index(drop=True)
    df.to_parquet(cache)
    return df

def read_idp(path: str | Path, **kw) -> pd.DataFrame:
    """Read an India Data Portal CSV and coerce district_code → lgd int."""
    df = pd.read_csv(path, low_memory=False, **kw)
    if "district_code" in df.columns:
        df["lgd"] = pd.to_numeric(df["district_code"], errors="coerce").astype("Int64")
    return df

# ── crop groups ───────────────────────────────────────────────────────────────
CROP_GROUPS = {
    "cereals": ["Rice", "Wheat", "Maize", "Barley", "Paddy"],
    "millets": ["Jowar", "Bajra", "Ragi", "Small Millets", "Small millets", "Other Cereals", "Kodo", "Kutki", "Sorghum", "Pearl Millet", "Finger Millet"],
    "pulses":  ["Arhar/Tur", "Gram", "Urad", "Moong(Green Gram)", "Masoor", "Horse-Gram", "Peas & Beans (Pulses)", "Other Kharif pulses", "Other Rabi pulses", "Khesari", "Moth", "Cowpea(Lobia)", "Other Pulses", "Tur", "Moong", "Lentil", "Peas"],
    "oilseeds": ["Groundnut", "Rapeseed &Mustard", "Soyabean", "Sunflower", "Sesamum", "Castor Seed", "Linseed", "Safflower", "Niger Seed", "Other Oilseeds", "Rapeseed & Mustard", "Soybean"],
    "cash": ["Sugarcane", "Cotton(Lint)", "Jute", "Tobacco", "Mesta", "Cotton"],
}
FOODGRAIN_GROUPS = ("cereals", "millets", "pulses")

def crop_group(name: str) -> str:
    n = str(name).strip()
    for g, names in CROP_GROUPS.items():
        if n in names:
            return g
    low = n.lower()
    if "millet" in low: return "millets"
    if any(k in low for k in ("pulse", "gram", "bean", "pea", "lentil")): return "pulses"
    if any(k in low for k in ("seed", "oil", "mustard", "soya")): return "oilseeds"
    return "other"

# ── ENSO phases from NOAA ONI ─────────────────────────────────────────────────
def oni() -> pd.DataFrame:
    """Returns columns: seas, yr, total, anom from datasets/05_weather_drought_imd/enso/noaa_cpc_oni.txt"""
    p = RAW / "05_weather_drought_imd" / "enso" / "noaa_cpc_oni.txt"
    df = pd.read_csv(p, sep=r"\s+")
    df.columns = ["seas", "yr", "total", "anom"]
    return df

def enso_phase_by_monsoon_year() -> dict[int, str]:
    """Phase for the kharif season of each year: mean ONI over JJA..OND of that year.
    >= +0.5 El Niño, <= -0.5 La Niña, else Neutral. Matches how IMD/literature classify monsoon‑year ENSO."""
    df = oni()
    out = {}
    for yr, g in df.groupby("yr"):
        s = g[g.seas.isin(["JJA", "JAS", "ASO", "SON", "OND"])]["anom"]
        if s.empty: continue
        m = s.mean()
        out[int(yr)] = "El Niño" if m >= 0.5 else ("La Niña" if m <= -0.5 else "Neutral")
    return out

def crop_year_to_int(y: str) -> int:
    """'2015-2016' / '2015-16' / 2015 → 2015 (the kharif/calendar year)."""
    return int(str(y)[:4])

def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), default=_default)

def _default(o):
    import numpy as np, math
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)):
        return None if math.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp,)): return o.isoformat()
    if hasattr(o, "item"): return o.item()
    raise TypeError(str(type(o)))
