"""Pre-positioning action rows (Addendum A): from artifacts/actions_{scenario}.csv, else derived from districts.json."""
from __future__ import annotations

import csv
import io
from typing import Any

from . import config, data, seasons

SCENARIOS = seasons.LEGACY_KEYS
LEAD_COLS = ("lead_rabi_2026_27", "lead_kharif_2027")
BASE_COLS = ["state", "district", "lgd", "score", "band"]
ACTION_COLS = ["grain_preposition_t", "pulses_preposition_t", "anganwadi_children", "women_anaemia_target",
               "seed_bank_ha", "mgnrega_persondays", "pmfby_gap_farmers", "fodder_flag",
               "priority_rank_state", "priority_rank_national"]
SUM_COLS = ["grain_preposition_t", "pulses_preposition_t", "anganwadi_children", "women_anaemia_target",
            "seed_bank_ha", "mgnrega_persondays", "pmfby_gap_farmers"]
DEFAULT_LEAD = {"rabi_2026_27": "by 2026-11-15", "kharif_2027": "by 2027-05-15"}


def _coerce(v: str | None) -> Any:
    if v is None or v == "":
        return None
    low = v.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in v and "e" not in low else f
    except ValueError:
        return v


def csv_path(scenario: str):
    """artifacts/actions_<season>_<phase>.csv for season keys (':' -> '_'); actions_<legacy>.csv for legacy keys."""
    return config.artifacts_dir() / f"actions_{seasons.slug(scenario)}.csv"


def _from_csv(scenario: str) -> list[dict] | None:
    p = csv_path(scenario)
    if not p.is_file():
        return None
    try:
        with p.open(newline="", encoding="utf-8") as f:
            return [{k: _coerce(v) for k, v in row.items()} for row in csv.DictReader(f)]
    except Exception:
        return None


def _from_districts(scenario: str) -> list[dict]:
    kpis = data.get_kpis()[0]
    rows = []
    for d in data.get_districts()[0]:
        r, _ = seasons.resolve_risk(d, scenario, kpis)
        r = r or {}
        a = r.get("actions")
        if not a:
            continue
        lead = a.get("lead") or {}
        row = {"state": d.get("state"), "district": d.get("district"), "lgd": d.get("lgd"),
               "score": r.get("score"), "band": r.get("band")}
        row.update({k: a.get(k) for k in ACTION_COLS})
        row["lead_rabi_2026_27"] = lead.get("rabi_2026_27")
        row["lead_kharif_2027"] = lead.get("kharif_2027")
        for k, v in lead.items():  # any other season's lead time
            row.setdefault(f"lead_{k}", v)
        rows.append(row)
    return rows


def get_rows(scenario: str, state: str | None = None, band: str | None = None) -> list[dict]:
    """CSV artifact for exactly this scenario key if present, else derived from districts.json risk[key].actions
    (with legacy/season alias resolution)."""
    rows = _from_csv(scenario)
    if rows is None:
        rows = _from_districts(scenario)
    if state:
        rows = [r for r in rows if str(r.get("state") or "").lower() == state.strip().lower()]
    if band:
        rows = [r for r in rows if str(r.get("band") or "").lower() == band.strip().lower()]
    return sorted(rows, key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))


def totals(rows: list[dict]) -> dict:
    return {c: sum(r[c] for r in rows if isinstance(r.get(c), (int, float)) and not isinstance(r.get(c), bool))
            for c in SUM_COLS}


def to_csv(rows: list[dict]) -> str:
    cols = BASE_COLS + ACTION_COLS + list(LEAD_COLS)
    extra = [k for r in rows for k in r if k not in cols]
    cols += list(dict.fromkeys(extra))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return buf.getvalue()


def actions_total(scenario: str, rows: list[dict], filtered: bool) -> dict:
    if not filtered:
        kt = (data.get_kpis()[0] or {}).get("actions_total")
        if isinstance(kt, dict):
            season, phase = seasons.split(scenario)
            nested = kt.get(season) if season else None  # tolerate actions_total[season][phase]
            for cand in (kt.get(scenario), kt.get(seasons.slug(scenario)),
                         nested.get(phase) if isinstance(nested, dict) else None):
                if isinstance(cand, dict):
                    return cand
    return totals(rows)
