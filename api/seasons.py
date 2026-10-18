"""Season-aware scenario keys (docs/SCHEMA.md Addendum F).

Scenario ids are `"<season>:<phase>"` (e.g. `kharif_2027:elnino`, `rabi_2026_27:current`); the legacy ids
`neutral | elnino | elnino_strong` stay valid as aliases of the default kharif season. Everything here is defensive:
the data pipeline may emit either key form (or both) and `kpis.outlook` may be missing on older artifacts.
Pure functions, no network.
"""
from __future__ import annotations

import re
from typing import Any

LEGACY_KEYS = ("neutral", "elnino", "elnino_strong")
PHASES = ("lanina", "neutral", "elnino", "elnino_strong", "current")
SCENARIO_RE = re.compile(r"^(kharif|rabi)_\d{4}(_\d{2})?:(lanina|neutral|elnino|elnino_strong|current)$")
DEFAULT_SCENARIO = "elnino"

# used when kpis.outlook is absent (older artifacts / mock data); values mirror Addendum F
_FALLBACK_SEASONS = {
    "rabi_2026_27": {"id": "rabi_2026_27", "label": "Rabi 2026-27", "sowing": "2026-10-15..2026-12-15",
                     "harvest": "2027-03..2027-04", "status": "sowing_now"},
    "kharif_2027": {"id": "kharif_2027", "label": "Kharif 2027", "sowing": "2027-06..2027-07",
                    "harvest": "2027-10..2027-11", "status": "upcoming"},
}
_KIND_DEFAULT_WINDOW = {"kharif": ("June-July", "October-November"), "rabi": ("mid-October to mid-December",
                                                                              "March-April")}
_STATUS_TEXT = {"sowing_now": "sowing window is open NOW", "upcoming": "upcoming season (pre-positioning window)",
                "harvest": "crop is in the field / harvest approaching", "past": "season is over"}

PHASE_LABEL = {"lanina": "La Niña", "neutral": "Neutral (ENSO-neutral)", "elnino": "El Niño",
               "elnino_strong": "Strong El Niño", "current": "Current outlook (ENSO-probability-weighted)"}


# ------------------------------------------------------------------ keys
def is_valid(s: Any) -> bool:
    return isinstance(s, str) and (s in LEGACY_KEYS or bool(SCENARIO_RE.match(s)))


def validate(s: str) -> str:
    """Pydantic/FastAPI validator: returns the key unchanged or raises ValueError (-> HTTP 422)."""
    if not is_valid(s):
        raise ValueError("scenario must be neutral|elnino|elnino_strong or '<kharif|rabi>_<year>[_yy]:"
                         "<lanina|neutral|elnino|elnino_strong|current>' (e.g. rabi_2026_27:current)")
    return s


def split(s: str) -> tuple[str | None, str]:
    """'kharif_2027:elnino' -> ('kharif_2027', 'elnino'); legacy 'elnino' -> (None, 'elnino')."""
    if ":" in s:
        season, phase = s.split(":", 1)
        return season, phase
    return None, s


def season_kind(season: str | None) -> str | None:
    if not season:
        return None
    m = re.match(r"^(kharif|rabi)_", season)
    return m.group(1) if m else None


def slug(s: str) -> str:
    """Filesystem-safe form: 'kharif_2027:elnino' -> 'kharif_2027_elnino' (legacy keys unchanged)."""
    return s.replace(":", "_")


# ------------------------------------------------------------------ outlook
def outlook(kpis: dict | None) -> dict:
    o = (kpis or {}).get("outlook")
    return o if isinstance(o, dict) else {}


def outlook_seasons(kpis: dict | None) -> list[dict]:
    s = outlook(kpis).get("seasons")
    if isinstance(s, list) and s:
        return [x for x in s if isinstance(x, dict) and x.get("id")]
    return list(_FALLBACK_SEASONS.values())


def season_ids(kpis: dict | None) -> list[str]:
    return [s["id"] for s in outlook_seasons(kpis)]


def default_season(kpis: dict | None, kind: str = "kharif") -> str:
    """The season legacy keys alias to: first outlook season of `kind` (kharif)."""
    for s in outlook_seasons(kpis):
        if season_kind(s["id"]) == kind:
            return s["id"]
    return "kharif_2027"


def default_phase(kpis: dict | None, season: str | None) -> str:
    ds = outlook(kpis).get("default_scenario")
    if isinstance(ds, dict) and season and ds.get(season) in PHASES:
        return ds[season]
    return DEFAULT_SCENARIO


def _season_entry(kpis: dict | None, season: str) -> dict:
    for s in outlook_seasons(kpis):
        if s["id"] == season:
            return s
    if season in _FALLBACK_SEASONS:
        return _FALLBACK_SEASONS[season]
    kind = season_kind(season) or "kharif"
    yrs = re.sub(r"^(kharif|rabi)_", "", season).replace("_", "-")
    sow, har = _KIND_DEFAULT_WINDOW.get(kind, ("data not available", "data not available"))
    return {"id": season, "label": f"{kind.capitalize()} {yrs}", "sowing": sow, "harvest": har, "status": None}


# ------------------------------------------------------------------ risk resolution
def risk_keys(d: dict) -> list[str]:
    return [k for k, v in (d.get("risk") or {}).items() if isinstance(v, dict) and v]


def resolve_risk(d: dict, scenario: str, kpis: dict | None = None) -> tuple[dict | None, str | None]:
    """Find the district's risk entry for `scenario`: exact key, else a sensible alias.

    new key  -> exact; `current` -> outlook default phase for that season; then the legacy alias of the phase
    legacy   -> exact; then `<default kharif season>:<key>`
    Returns (entry, resolved_key) or (None, None).
    """
    risk = d.get("risk") or {}

    def get(k: str) -> dict | None:
        v = risk.get(k)
        return v if isinstance(v, dict) and v else None

    if get(scenario):
        return risk[scenario], scenario
    season, phase = split(scenario)
    if season is None:  # legacy key requested but only season keys present
        k = f"{default_season(kpis)}:{phase}"
        return (risk[k], k) if get(k) else (None, None)
    if phase == "current":
        phase = default_phase(kpis, season)
        k = f"{season}:{phase}"
        if get(k):
            return risk[k], k
    return (risk[phase], phase) if get(phase) else (None, None)


# ------------------------------------------------------------------ season context for prompts
_RAIN = {
    "lanina": "EXCESS-RAIN / FLOOD framing: the hazard is too much water (floods, waterlogging, delayed or "
              "re-sown crops, pest/disease pressure, post-flood seed and income loss), not drought",
    "neutral": "CLIMATOLOGY framing: no ENSO-driven anomaly is assumed; risk is STRUCTURAL vulnerability "
               "(rainfed share, yield variability, food balance, malnutrition, capacity), so describe what makes "
               "the district fragile in an ordinary year",
    "elnino": "DEFICIT / HEAT framing: the hazard is below-normal rain, dry spells and heat stress on crops and "
              "water",
    "elnino_strong": "STRONG DEFICIT / HEAT framing (stress test of the 2002/2009/2015 analog years): severe "
                     "rain deficit, long dry spells and heat; not the central expectation",
    "current": "ENSO-PROBABILITY-WEIGHTED framing: the score blends the La Niña, neutral and El Niño analogs by "
               "their outlook probabilities; say which phase dominates and that the mix, not one event, is shown",
}


def _framing(kind: str | None, phase: str) -> str:
    text = _RAIN[phase]
    if kind == "rabi":
        extra = {
            "elnino": " For rabi this means a warm, dry winter: low residual soil moisture, terminal heat in "
                      "Feb-Mar at grain filling, groundwater-dependent irrigation",
            "elnino_strong": " For rabi this means a severely warm, dry winter: terminal heat at grain filling and "
                             "stressed groundwater",
            "lanina": " For rabi, the excess-water risk is residual waterlogging, delayed sowing after a wet "
                      "monsoon and disease pressure",
            "neutral": " For rabi the structural issues are groundwater dependence and sowing-date discipline",
        }.get(phase, "")
    else:
        extra = {
            "elnino": " For kharif this is a weak or late monsoon: late onset, dry spells in JJAS",
            "elnino_strong": " For kharif this is a severe monsoon deficit",
            "lanina": " For kharif this is an above-normal monsoon: flood-prone districts, drainage and "
                      "submergence-tolerant seed matter",
        }.get(phase, "")
    return text + "." + extra + ("." if extra else "")


def season_context(scenario: str, kpis: dict | None = None, resolved_key: str | None = None) -> dict:
    """Structured season context for one scenario key (legacy keys -> default kharif season)."""
    season, phase = split(scenario)
    legacy = season is None
    if legacy:
        season = default_season(kpis)
    entry = _season_entry(kpis, season)
    kind = season_kind(season)
    enso = outlook(kpis).get("enso") or {}
    probs = ((enso.get("p_by_season") or {}).get(season)) or None
    fallback_note = None
    if resolved_key and resolved_key != scenario:
        fallback_note = (f"no risk entry for '{scenario}' in this district; the model values shown come from "
                         f"risk.{resolved_key} (alias) and may not be calibrated for this season; say so")
    return {
        "scenario": scenario, "season": season, "kind": kind, "label": entry.get("label") or season,
        "sowing": entry.get("sowing"), "harvest": entry.get("harvest"), "status": entry.get("status"),
        "phase": phase, "phase_label": PHASE_LABEL.get(phase, phase), "legacy_alias": legacy,
        "enso_state": enso.get("state"), "enso_probabilities": probs,
        "is_lanina": phase == "lanina", "is_neutral": phase == "neutral",
        "is_elnino": phase in ("elnino", "elnino_strong"),
        "framing": _framing(kind, phase), "resolved_key": resolved_key, "fallback_note": fallback_note,
    }


def season_block(ctx: dict) -> str:
    """Prompt text for a season context dict (from `season_context`)."""
    st = ctx.get("status")
    status = _STATUS_TEXT.get(st, st) if st else "not stated"
    probs = ctx.get("enso_probabilities")
    p_txt = (", ".join(f"{PHASE_LABEL.get(k, k).split(' (')[0]} {round(float(v) * 100)}%"
                       for k, v in probs.items() if isinstance(v, (int, float))) if probs
             else "not available (do not quote probabilities)")
    lines = [
        f"SEASON CONTEXT (this advisory is for ONE season; it overrides any El Niño-only wording elsewhere):",
        f"- Season: {ctx['label']} ({ctx['season']}); status: {status}",
        f"- Sowing window: {ctx.get('sowing') or 'data not available'}; harvest: "
        f"{ctx.get('harvest') or 'data not available'}",
        f"- Scenario: {ctx['scenario']} -> ENSO phase: {ctx['phase_label']}"
        + (" (legacy key = default kharif season)" if ctx.get("legacy_alias") else ""),
        f"- ENSO phase probabilities for this season (outlook, "
        f"{ctx.get('enso_state') or 'current ENSO state not stated'}): {p_txt}",
        f"- Framing: {ctx['framing']}",
    ]
    if ctx.get("fallback_note"):
        lines.append(f"- DATA CAVEAT: {ctx['fallback_note']}")
    return "\n".join(lines)


# ------------------------------------------------------------------ per-district season outlook (Addendum I)
def season_kind_of(scenario: str, kpis: dict | None = None) -> str | None:
    """'kharif' | 'rabi' for any scenario key (legacy keys -> default kharif season)."""
    season, _ = split(scenario)
    return season_kind(season or default_season(kpis))


def district_outlook(d: dict | None, scenario: str, kpis: dict | None = None) -> dict | None:
    """`d.season_outlook[season][phase]` for a scenario key, or None when absent (older artifacts).

    `current` falls back to the outlook's default phase for the season; legacy keys use the default kharif season.
    """
    so = (d or {}).get("season_outlook")
    if not isinstance(so, dict):
        return None
    season, phase = split(scenario)
    season = season or default_season(kpis)
    per = so.get(season)
    if not isinstance(per, dict):
        return None
    cand = [phase] + ([default_phase(kpis, season)] if phase == "current" else [])
    for p in cand:
        e = per.get(p)
        if isinstance(e, dict) and e:
            return e
    return None


def phase_probability(scenario: str, kpis: dict | None = None) -> float | None:
    """ENSO probability (0-1) of the scenario's phase for its season, from kpis.outlook; None if unknown."""
    season, phase = split(scenario)
    season = season or default_season(kpis)
    probs = ((outlook(kpis).get("enso") or {}).get("p_by_season") or {}).get(season)
    if not isinstance(probs, dict):
        return None
    v = probs.get("elnino" if phase == "elnino_strong" else phase)
    return float(v) if isinstance(v, (int, float)) else None


def likelihood_word(p: float | None) -> str:
    """Farmer-facing wording: >= 0.8 very likely, 0.5-0.8 likely, else possible."""
    if p is None:
        return "possible"
    return "very likely" if p >= 0.8 else "likely" if p >= 0.5 else "possible"


_PLAIN_EVENT = {
    ("elnino", "kharif"): "a weak monsoon", ("elnino_strong", "kharif"): "a very weak monsoon",
    ("elnino", "rabi"): "a dry, warm winter", ("elnino_strong", "rabi"): "a very dry, warm winter",
    ("lanina", "kharif"): "heavy rain and flooding", ("lanina", "rabi"): "a wetter-than-usual winter",
    ("neutral", "kharif"): "a near-normal season", ("neutral", "rabi"): "a near-normal season",
}


def plain_outlook(d: dict | None, scenario: str, kpis: dict | None = None) -> str:
    """One plain sentence about the season's climate: `season_outlook[...].plain` when present, else built from
    the phase and its probability ('A weak monsoon is likely')."""
    e = district_outlook(d, scenario, kpis)
    if e and isinstance(e.get("plain"), str) and e["plain"].strip():
        return e["plain"].strip()
    kind = season_kind_of(scenario, kpis) or "kharif"
    phase = split(scenario)[1]
    if phase == "current":
        season = split(scenario)[0] or default_season(kpis)
        probs = ((outlook(kpis).get("enso") or {}).get("p_by_season") or {}).get(season)
        nums = {k: v for k, v in (probs or {}).items() if isinstance(v, (int, float)) and k in PHASES}
        if not nums:
            return "The season outlook is mixed; no single outcome stands out"
        phase = max(nums, key=nums.get)
        p = float(nums[phase])
    else:
        p = phase_probability(scenario, kpis)
    event = _PLAIN_EVENT.get((phase, kind), "a near-normal season")
    return f"{event[0].upper() + event[1:]} is {likelihood_word(p)}"
