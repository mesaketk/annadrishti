"""Simplify INDIA_DISTRICTS.geojson -> web/public/districts.geojson + states.geojson.
Props kept: {lgd:int, district, state}. Drops Dist_LGD == 0 (PoK polygons)."""
import json
from pathlib import Path
import geopandas as gpd
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public"
OUT.mkdir(parents=True, exist_ok=True)

gdf = gpd.read_file(ROOT / "INDIA_DISTRICTS.geojson")
gdf = gdf[gdf["Dist_LGD"].fillna(0).astype(int) != 0].copy()
gdf["lgd"] = gdf["Dist_LGD"].astype(int)
gdf["district"] = gdf["dtname"]
gdf["state"] = gdf["stname"].str.title()
gdf = gdf.drop_duplicates("lgd")[["lgd", "district", "state", "geometry"]]
gdf["geometry"] = gdf.geometry.make_valid()
full = gdf.copy()  # unsimplified, used for the state dissolve (simplified rings can leave slivers)
gdf["geometry"] = gdf.geometry.simplify(0.01, preserve_topology=True)
gdf = gdf[~gdf.geometry.is_empty]


def round_coords(obj, nd=3):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], nd), round(obj[1], nd)]
        return [round_coords(o, nd) for o in obj]
    return obj


def write(df, path, props):
    feats = []
    for _, r in df.iterrows():
        g = mapping(r.geometry)
        feats.append({"type": "Feature",
                      "properties": {k: (int(r[k]) if k == "lgd" else r[k]) for k in props},
                      "geometry": {"type": g["type"], "coordinates": round_coords(g["coordinates"])}})
    with open(path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, separators=(",", ":"))
    print(path, f"{path.stat().st_size/1e6:.2f} MB", len(feats), "features")


write(gdf, OUT / "districts.geojson", ["lgd", "district", "state"])

states = full.dissolve(by="state", as_index=False)[["state", "geometry"]]
states["geometry"] = states.geometry.make_valid()
states["geometry"] = states.geometry.simplify(0.01, preserve_topology=True)
write(states, OUT / "states.geojson", ["state"])
