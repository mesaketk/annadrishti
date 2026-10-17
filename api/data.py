"""Artifact loading (mtime-aware reload) with mock fallbacks, plus GCS sync."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import orjson

from . import config

log = logging.getLogger("annadrishti.data")

_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _load_json(path: Path) -> Any:
    """Load JSON, re-reading only when the file's mtime changes."""
    key = str(path)
    mtime = path.stat().st_mtime
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
    data = orjson.loads(path.read_bytes())
    with _lock:
        _cache[key] = (mtime, data)
    return data


# --------------------------------------------------------------------------- built-in mock
def _mk(lgd, name, state, score_n, score_e, score_s, pop, rainfed):
    def band(s):
        return "high" if s >= 67 else "medium" if s >= 34 else "low"

    def risk(score, shock):
        return {
            "score": score, "band": band(score), "exposure": round(score / 120, 2),
            "sensitivity": 0.6, "capacity": 0.4, "expected_yield_shock_pct": shock,
            "drivers": [{"name": "rainfed_share", "contrib": 0.18},
                        {"name": "stunting", "contrib": 0.14},
                        {"name": "yield_cv10", "contrib": 0.09}],
        }

    def acts(score, k):
        high = score >= 67
        return {"grain_preposition_t": int(pop * 0.02 * k), "pulses_preposition_t": int(pop * 0.0015 * k),
                "anganwadi_children": int(pop * 0.04), "women_anaemia_target": int(pop * 0.17),
                "seed_bank_ha": int(100000 * rainfed * k) if score >= 34 else None,
                "mgnrega_persondays": int(pop * 2 * rainfed * k) if high else None,
                "pmfby_gap_farmers": int(pop * 0.05), "fodder_flag": high,
                "lead": {"rabi_2026_27": "by 2026-11-15", "kharif_2027": "by 2027-05-15"},
                "priority_rank_state": 1, "priority_rank_national": 1}

    r = {
        "lgd": lgd, "district": name, "state": state, "census11": str(lgd),
        "centroid": [74.2, 21.4], "population_2011": int(pop * 0.86), "population_2026": pop,
        "children_u5_est": int(pop * 0.1),
        "crops": {
            "year": "2022-23", "gross_cropped_area_ha": 512000,
            "top": [{"crop": "Jowar", "share": 0.22, "yield_t_ha": 0.9},
                    {"crop": "Cotton", "share": 0.2, "yield_t_ha": 0.4},
                    {"crop": "Bajra", "share": 0.15, "yield_t_ha": 1.1}],
            "groups": {"cereals": {"area_ha": 200000, "prod_t": 220000}},
            "foodgrain_prod_t": 310000, "simpson_div": 0.71, "top_crop_share": 0.22,
            "kharif_rabi_ratio": 2.1, "yield_cv10": 0.31, "irrigated_share": round(1 - rainfed, 2),
            "rainfed_share": rainfed, "small_marginal_share": 0.62,
        },
        "food_balance": {"requirement_t": 341000, "edible_prod_t": 271000,
                         "self_sufficiency": 0.79, "pds_dependency": 0.41},
        "nutrition": {"nfhs5": {"year": "2019-21", "stunting": 40.1, "wasting": 21.2,
                                "underweight": 40.3, "child_anaemia": 76.0, "women_anaemia": 64.1,
                                "women_bmi_low": 20.0}, "nfhs6": None},
        "climate": {"jjas_normal_mm": 820, "jjas_anomaly_pct": {"2014": -18, "2015": -27, "2023": -9},
                    "elnino_mean_anomaly_pct": -16, "neutral_mean_anomaly_pct": 2,
                    "lanina_mean_anomaly_pct": 9, "tmax_anomaly_c": {"2015": 0.8},
                    "clim_vuln_index": 0.61, "live": None},
        "yield_sensitivity": {"foodgrain_elnino_pct": -14, "n_elnino_years": 5,
                              "by_group": {"cereals": -12, "pulses": -21, "oilseeds": -18, "millets": -6}},
        "risk": {"neutral": risk(score_n, -2), "elnino": risk(score_e, -14),
                 "elnino_strong": risk(score_s, -23)},
        "hindcast": {"2015": {"predicted_score": 74, "actual_foodgrain_yield_dev_pct": -23}},
    }
    r["risk"]["elnino"]["actions"] = acts(score_e, 1.0)
    r["risk"]["elnino_strong"]["actions"] = acts(score_s, 1.6)
    r["risk"]["neutral"]["actions"] = None
    return r


BUILTIN_DISTRICTS = [
    _mk(486, "Nandurbar", "Maharashtra", 31, 78, 88, 1910000, 0.86),
    _mk(999001, "Mockpur", "Karnataka", 25, 55, 70, 2400000, 0.7),
    _mk(999002, "Sampleganj", "Uttar Pradesh", 18, 30, 41, 3100000, 0.2),
]
BUILTIN_KPIS = {
    "as_of": "2026-10-17",
    "enso": {"state": "El Niño", "nino34": 2.1, "p_historic_ond": 0.83, "source": "NOAA CPC 2026-10-08"},
    "central_pool": {"date": "2026-10-01", "rice_lmt": 400, "wheat_lmt": 300, "total_lmt": 700,
                     "norm_lmt": 410, "months_of_offtake": 7.8},
    "scenario_counts": {"elnino": {"high": 1, "medium": 1, "low": 1}},
    "people_in_high_risk": 1910000, "children_u5_in_high_risk": 191000,
}
BUILTIN_TIMESERIES = {
    "yield": {"foodgrain_t_ha": {str(y): round(1.0 + 0.01 * (y - 2000), 2) for y in range(2000, 2025)},
              "by_group": {}},
    "rain_jjas_mm": {str(y): 800 for y in range(2000, 2025)},
    "oni_phase": {str(y): "Neutral" for y in range(2000, 2025)},
    "nfhs": [], "pds_monthly": [],
}


# --------------------------------------------------------------------------- resolution
def _first(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.is_file():
            return p
    return None


def get_districts() -> tuple[list[dict], bool]:
    """Returns (districts, is_mock)."""
    real = config.artifacts_dir() / "districts.json"
    if real.is_file():
        try:
            data = _load_json(real)
            if isinstance(data, list) and data:
                return data, False
        except Exception:  # half-written file while pipeline runs
            log.exception("failed to read %s, falling back to mock", real)
    mock = config.mock_dir() / "districts.json"
    if mock.is_file():
        try:
            data = _load_json(mock)
            if isinstance(data, list) and data:
                return data, True
        except Exception:
            log.exception("failed to read %s", mock)
    return BUILTIN_DISTRICTS, True


def get_kpis() -> tuple[dict, bool]:
    real = config.artifacts_dir() / "kpis.json"
    if real.is_file():
        try:
            return _load_json(real), False
        except Exception:
            log.exception("failed to read %s", real)
    mock = config.mock_dir() / "kpis.json"
    if mock.is_file():
        try:
            return _load_json(mock), True
        except Exception:
            pass
    return BUILTIN_KPIS, True


def get_timeseries(lgd: int) -> tuple[dict | None, bool]:
    real = config.artifacts_dir() / "timeseries" / f"{int(lgd)}.json"
    if real.is_file():
        try:
            return _load_json(real), False
        except Exception:
            log.exception("failed to read %s", real)
    mock = config.mock_dir() / "timeseries" / f"{int(lgd)}.json"
    if mock.is_file():
        return _load_json(mock), True
    _, districts_mock = get_districts()
    if districts_mock and int(lgd) in {d["lgd"] for d in BUILTIN_DISTRICTS} and not (config.mock_dir() / "districts.json").is_file():
        return BUILTIN_TIMESERIES, True
    return None, False


def _history_file(rel: str) -> Path | None:
    for root in (config.artifacts_dir(), config.mock_dir()):
        p = root / "history" / rel
        if p.is_file():
            return p
    return None


def get_history_index() -> dict | None:
    """artifacts/history/index.json (History mode, Addendum H); None if the pipeline step 06b has not been run."""
    p = _history_file("index.json")
    if p is None:
        return None
    try:
        return _load_json(p)
    except Exception:  # half-written file while the pipeline runs
        log.exception("failed to read %s", p)
        return None


def get_history_year(year: int) -> dict | None:
    p = _history_file(f"{int(year)}.json")
    if p is None:
        return None
    try:
        return _load_json(p)
    except Exception:
        log.exception("failed to read %s", p)
        return None


def district_by_lgd(lgd: int) -> dict | None:
    for d in get_districts()[0]:
        if d.get("lgd") == lgd:
            return d
    return None


# --------------------------------------------------------------------------- GCS sync
def sync_from_gcs() -> int:
    """If ARTIFACTS_GCS_URI (gs://bucket/prefix) is set, download all *.json into ARTIFACTS_DIR."""
    uri = config.env("ARTIFACTS_GCS_URI")
    if not uri:
        return 0
    if not uri.startswith("gs://"):
        log.error("ARTIFACTS_GCS_URI must start with gs://, got %r", uri)
        return 0
    from google.cloud import storage  # lazy: only needed when syncing

    bucket_name, _, prefix = uri[5:].partition("/")
    prefix = prefix.strip("/")
    dest = config.artifacts_dir()
    client = storage.Client()
    n = 0
    for blob in client.list_blobs(bucket_name, prefix=prefix + "/" if prefix else None):
        if not blob.name.endswith(".json"):
            continue
        rel = blob.name[len(prefix):].lstrip("/") if prefix else blob.name
        if not rel or Path(rel).name.startswith("_") or ".." in Path(rel).parts:
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        blob.download_to_filename(str(tmp))
        tmp.replace(target)
        n += 1
    log.info("synced %d artifact files from %s", n, uri)
    return n
