"""Python tools over the districts array, exposed to Gemini via function calling."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable

from . import data, personalize, seasons

SCENARIOS = seasons.LEGACY_KEYS  # legacy aliases; season-qualified keys are resolved through api.seasons


def _g(d: Any, *path: str) -> Any:
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _risk(d: dict, scenario: str) -> dict:
    """The district's risk entry for any scenario key (legacy, `<season>:<phase>`, `current`), {} if none."""
    return seasons.resolve_risk(d, scenario, data.get_kpis()[0])[0] or {}


def _nfhs(d: dict, key: str) -> Any:
    """Latest NFHS round that has the value (NFHS-6 preferred, else NFHS-5)."""
    for rnd in ("nfhs6", "nfhs5"):
        v = _g(d, "nutrition", rnd, key)
        if v is not None:
            return v
    return None


METRICS: dict[str, Callable[[dict, str], Any]] = {
    "risk_score": lambda d, s: _risk(d, s).get("score"),
    "expected_yield_shock_pct": lambda d, s: _risk(d, s).get("expected_yield_shock_pct"),
    "self_sufficiency": lambda d, s: _g(d, "food_balance", "self_sufficiency"),
    "pds_dependency": lambda d, s: _g(d, "food_balance", "pds_dependency"),
    "stunting": lambda d, s: _nfhs(d, "stunting"),
    "wasting": lambda d, s: _nfhs(d, "wasting"),
    "underweight": lambda d, s: _nfhs(d, "underweight"),
    "child_anaemia": lambda d, s: _nfhs(d, "child_anaemia"),
    "women_anaemia": lambda d, s: _nfhs(d, "women_anaemia"),
    "women_bmi_low": lambda d, s: _nfhs(d, "women_bmi_low"),
    "elnino_mean_anomaly_pct": lambda d, s: _g(d, "climate", "elnino_mean_anomaly_pct"),
    "lanina_mean_anomaly_pct": lambda d, s: _g(d, "climate", "lanina_mean_anomaly_pct"),
    "foodgrain_elnino_pct": lambda d, s: _g(d, "yield_sensitivity", "foodgrain_elnino_pct"),
    "population_2026": lambda d, s: d.get("population_2026"),
    "children_u5_est": lambda d, s: d.get("children_u5_est"),
    "rainfed_share": lambda d, s: _g(d, "crops", "rainfed_share"),
    "irrigated_share": lambda d, s: _g(d, "crops", "irrigated_share"),
    "yield_cv10": lambda d, s: _g(d, "crops", "yield_cv10"),
    "clim_vuln_index": lambda d, s: _g(d, "climate", "clim_vuln_index"),
}
ALIASES = {"risk": "risk_score", "score": "risk_score", "yield_shock": "expected_yield_shock_pct",
           "population": "population_2026", "child_anemia": "child_anaemia",
           "women_anemia": "women_anaemia", "anaemia": "child_anaemia"}


# ------------------------------------------------------------------ grounding context
def _flatten(prefix: str, obj: Any, out: list[str], depth: int = 0) -> None:
    if isinstance(obj, dict) and depth < 3:
        for k, v in obj.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, out, depth + 1)
    elif obj not in (None, [], {}):
        out.append(prefix)


def district_context(d: dict, scenario: str | None = None) -> tuple[dict, list[str]]:
    """Compact, LLM-sized slice of a district record plus the list of non-null field paths included.

    `scenario=None` keeps the legacy shape (the three legacy risk keys, each with actions). With a scenario key the
    risk block holds that scenario's entry (resolved through aliases, under the key it was found at, with actions)
    plus the other phases of the same season for contrast (without actions, to keep the prompt small).
    """
    crops = d.get("crops") or {}
    risk = d.get("risk") or {}
    kpis0 = data.get_kpis()[0]
    kind = seasons.season_kind_of(scenario, kpis0) if scenario is not None else None
    season_outlook = seasons.district_outlook(d, scenario, kpis0) if scenario is not None else None

    def risk_slice(s: str, with_actions: bool = True) -> dict | None:
        r = risk.get(s)
        if not r:
            return None
        out = {k: r.get(k) for k in ("score", "band", "exposure", "sensitivity", "capacity",
                                     "expected_yield_shock_pct")}
        out["drivers"] = (r.get("drivers") or [])[:5]
        if with_actions:
            out["actions"] = r.get("actions")
        return out

    if scenario is None:
        risk_keys = [k for k in SCENARIOS if k in risk] or list(risk)  # new-key-only data: send every key
        primary = None
    else:
        _, primary = seasons.resolve_risk(d, scenario, data.get_kpis()[0])
        season = seasons.split(primary)[0] if primary else seasons.split(scenario)[0]
        same = [k for k in risk if seasons.split(k)[0] == season and k != primary] if season else \
            [k for k in SCENARIOS if k != primary]
        risk_keys = ([primary] if primary else []) + same

    clim = dict(d.get("climate") or {})
    anomalies = clim.get("jjas_anomaly_pct")
    if isinstance(anomalies, dict):  # keep El Nino analog years only, not all 26 years
        clim["jjas_anomaly_pct"] = {y: anomalies[y] for y in ("2002", "2009", "2014", "2015", "2023")
                                    if y in anomalies}
    if isinstance(clim.get("tmax_anomaly_c"), dict):
        clim["tmax_anomaly_c"] = {y: v for y, v in clim["tmax_anomaly_c"].items()
                                  if y in ("2009", "2014", "2015", "2023")}
    ctx = {
        "lgd": d.get("lgd"), "district": d.get("district"), "state": d.get("state"),
        "population_2026": d.get("population_2026"), "children_u5_est": d.get("children_u5_est"),
        "crops": {**{k: crops.get(k) for k in ("year", "foodgrain_prod_t", "top_crop_share", "simpson_div",
                                               "yield_cv10", "irrigated_share", "rainfed_share",
                                               "small_marginal_share", "kharif_rabi_ratio")},
                  "top": personalize.season_top(d, kind)[0][:5], "groups": crops.get("groups")},
        "food_balance": d.get("food_balance"),
        "nutrition": d.get("nutrition"),
        "climate": clim,
        "yield_sensitivity": d.get("yield_sensitivity"),
        "risk": {s: risk_slice(s, primary is None or s == primary) for s in risk_keys if risk.get(s)},
        "hindcast": d.get("hindcast"),
    }
    if kind and personalize.season_top(d, kind)[1] == "season":
        ctx["crops"]["top_is_for_season"] = kind  # crops.top above is the {kind}-season list (Addendum I)
    if season_outlook:
        # season-specific rain/heat framing (Addendum I); the JJAS-only climate numbers would misdescribe rabi
        ctx["season_outlook"] = {"season": seasons.split(scenario)[0] or seasons.default_season(kpis0),
                                 "kind": kind, **season_outlook}
        if kind == "rabi":
            for k in ("jjas_anomaly_pct", "tmax_anomaly_c", "elnino_mean_anomaly_pct", "lanina_mean_anomaly_pct"):
                ctx["climate"].pop(k, None)
    # optional blocks added by the extra-sources pipeline (Addendum D); absent on older artifacts
    if (crops.get("economics")):
        ctx["crops"]["economics"] = crops["economics"]
    for block in ("markets", "groundwater"):
        v = d.get(block)
        if isinstance(v, dict) and v:  # drop bulky raw series, keep the scalar indicators
            ctx[block] = {k: x for k, x in v.items() if "series" not in k}
    fields: list[str] = []
    _flatten("", ctx, fields)
    return ctx, fields


# ------------------------------------------------------------------ tools
def _brief(d: dict, scenario: str = "elnino") -> dict:
    r = _risk(d, scenario)
    return {"lgd": d.get("lgd"), "district": d.get("district"), "state": d.get("state"),
            "risk_score": r.get("score"), "band": r.get("band")}


def _find(name_or_lgd: Any) -> list[dict]:
    districts, _ = data.get_districts()
    s = str(name_or_lgd).strip()
    if s.isdigit():
        return [d for d in districts if d.get("lgd") == int(s)]
    state = None
    if "," in s:
        s, state = [p.strip() for p in s.split(",", 1)]
    low = s.lower()
    exact = [d for d in districts if str(d.get("district", "")).lower() == low]
    found = exact or [d for d in districts if low and low in str(d.get("district", "")).lower()]
    if state:
        found = [d for d in found if state.lower() in str(d.get("state", "")).lower()] or found
    return found


def get_district(name_or_lgd: Any, scenario: str | None = None) -> dict:
    found = _find(name_or_lgd)
    if not found:
        return {"error": f"no district matching {name_or_lgd!r}"}
    sc = scenario if seasons.is_valid(scenario) else None
    if len(found) > 1:
        return {"ambiguous": True, "matches": [_brief(d, sc or "elnino") for d in found[:8]],
                "hint": "call again with the numeric lgd"}
    ctx, _ = district_context(found[0], sc)
    return ctx


def rank_districts(metric: str, scenario: str = "elnino", state: str | None = None,
                   top_n: int = 10, ascending: bool = False) -> dict:
    metric = ALIASES.get(metric, metric)
    if metric not in METRICS:
        return {"error": f"unknown metric {metric!r}", "valid_metrics": sorted(METRICS)}
    note = None
    if not seasons.is_valid(scenario):
        note = f"invalid scenario {scenario!r}; used {seasons.DEFAULT_SCENARIO!r}"
        scenario = seasons.DEFAULT_SCENARIO
    try:
        top_n = max(1, min(int(top_n), 25))
    except (TypeError, ValueError):
        top_n = 10
    rows = []
    for d in data.get_districts()[0]:
        if state and state.lower() not in str(d.get("state", "")).lower():
            continue
        v = METRICS[metric](d, scenario)
        if isinstance(v, (int, float)):
            rows.append((v, d))
    rows.sort(key=lambda r: r[0], reverse=not ascending)
    out = {"metric": metric, "scenario": scenario, "state": state, "ascending": ascending,
           "n_candidates": len(rows),
           "results": [{"lgd": d.get("lgd"), "district": d.get("district"), "state": d.get("state"),
                        "value": v} for v, d in rows[:top_n]]}
    if metric in ("risk_score", "expected_yield_shock_pct"):
        out["season"] = seasons.season_context(scenario, data.get_kpis()[0])["label"]
    if note:
        out["note"] = note
    return out


_PHASE_ORDER = {p: i for i, p in enumerate(seasons.PHASES)}


def _risk_row(r: dict) -> dict:
    return {k: r.get(k) for k in ("score", "band", "expected_yield_shock_pct")} | {
        "top_drivers": (r.get("drivers") or [])[:3]}


def compare_scenarios(lgd: Any) -> dict:
    found = _find(lgd)
    if len(found) != 1:
        return get_district(lgd) if not found else {"ambiguous": True,
                                                    "matches": [_brief(d) for d in found[:8]]}
    d = found[0]
    kpis = data.get_kpis()[0]
    risk = {k: v for k, v in (d.get("risk") or {}).items() if isinstance(v, dict) and v}
    ds = seasons.default_season(kpis)
    # flat view (legacy keys first, then season keys) + view grouped by season
    scen = {k: _risk_row(risk[k]) for k in sorted(risk, key=lambda k: (":" in k, k))}
    by_season: dict[str, dict] = {}
    for k in sorted(risk, key=lambda k: _PHASE_ORDER.get(seasons.split(k)[1], 99)):
        season, phase = seasons.split(k)
        if season is None:
            if f"{ds}:{phase}" in risk:  # alias duplicated by the season-qualified key
                continue
            season = ds
        by_season.setdefault(season, {})[phase] = scen[k]
    order = {s: i for i, s in enumerate(seasons.season_ids(kpis))}
    by_season = {s: by_season[s] for s in sorted(by_season, key=lambda s: order.get(s, 99))}

    def delta(rk: dict) -> int | float | None:
        e, n = (rk.get("elnino") or {}).get("score"), (rk.get("neutral") or {}).get("score")
        return (e - n) if isinstance(n, (int, float)) and isinstance(e, (int, float)) else None

    legacy = {k: scen[k] for k in scen if ":" not in k}
    return {"lgd": d.get("lgd"), "district": d.get("district"), "state": d.get("state"),
            "scenarios": scen,
            "by_season": {s: {"label": seasons.season_context(f"{s}:neutral", kpis)["label"], "phases": ph,
                              "delta_elnino_vs_neutral": delta(ph)} for s, ph in by_season.items()},
            "delta_elnino_vs_neutral": delta(legacy) if delta(legacy) is not None else delta(by_season.get(ds, {}))}


def national_summary() -> dict:
    districts, is_mock = data.get_districts()
    kpis, _ = data.get_kpis()
    out: dict[str, Any] = {"n_districts": len(districts), "data_is_mock": is_mock,
                           "enso": kpis.get("enso"), "central_pool": kpis.get("central_pool"),
                           "bands": {}, "population_in_high_risk_elnino": 0,
                           "children_u5_in_high_risk_elnino": 0}
    if seasons.outlook(kpis):
        out["outlook"] = {k: v for k, v in seasons.outlook(kpis).items() if k in ("as_of", "seasons", "default_scenario")}
    bss = kpis.get("by_season_scenario")
    if isinstance(bss, dict) and bss:
        out["by_season_scenario"] = bss  # per season x phase: counts, people, children, shock
    keys: list[str] = []
    for d in districts:
        for k in (d.get("risk") or {}):
            if k not in keys:
                keys.append(k)
    for s in keys:
        out["bands"][s] = dict(Counter(_risk(d, s).get("band") for d in districts if _g(d, "risk", s, "band")))
    by_state: dict[str, int] = defaultdict(int)
    for d in districts:
        if _risk(d, "elnino").get("band") == "high":
            out["population_in_high_risk_elnino"] += d.get("population_2026") or 0
            out["children_u5_in_high_risk_elnino"] += d.get("children_u5_est") or 0
            by_state[d.get("state") or "?"] += 1
    out["states_by_high_risk_districts_elnino"] = sorted(by_state.items(), key=lambda kv: -kv[1])[:8]
    return out


# farmer_advice needs the cached advisory builder that lives in main.py (it owns the cache + rate limits);
# main registers it here at import time to avoid a circular import. Signature: fn(lgd, scenario, language, profile)
# -> advisory dict {"markdown", "model", "grounding", ...}; it may raise (HTTPException etc.).
_advisory_provider: Callable[..., dict] | None = None


def set_advisory_provider(fn: Callable[..., dict] | None) -> None:
    global _advisory_provider
    _advisory_provider = fn


_HOLDINGS, _WATERS = personalize.HOLDINGS, personalize.WATERS
_LANGS = ("en", "hi", "mr", "te", "bn", "ta", "kn", "gu", "or")


def _truthy(v: Any) -> bool:
    return v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "y")


def farmer_advice(lgd: Any, season_scenario: str | None = None, holding: str | None = None,
                  water: str | None = None, crop: str | None = None, livestock: Any = None, tenant: Any = None,
                  language: str | None = None) -> dict:
    """Farmer advisory markdown (sowing / crop choice / water / insurance / schemes) for one district and season,
    through the same cached builder as POST /api/advisory/{lgd} (audience=farmer)."""
    if _advisory_provider is None:
        return {"error": "farmer advisory builder is not available"}
    try:
        code = int(str(lgd).strip())
    except (TypeError, ValueError):
        found = _find(lgd) if lgd not in (None, "") else []
        if len(found) != 1:
            return {"error": f"need one district (numeric lgd or an unambiguous name); got {lgd!r}"}
        code = found[0]["lgd"]
    d = data.district_by_lgd(code)
    if d is None:
        return {"error": f"unknown district lgd {code}"}
    notes = []
    sc = season_scenario
    if not seasons.is_valid(sc):
        if sc:
            notes.append(f"invalid season_scenario {sc!r}; used {seasons.DEFAULT_SCENARIO!r}")
        sc = seasons.DEFAULT_SCENARIO
    h = holding if holding in _HOLDINGS else None
    w = water if water in _WATERS else None
    if holding and not h:
        notes.append(f"holding must be one of {list(_HOLDINGS)}; ignored")
    if water and not w:
        notes.append(f"water must be one of {list(_WATERS)}; ignored")
    lang = language if language in _LANGS else "en"
    profile = {"holding": h, "water": w, "crop": (str(crop).strip() or None) if crop else None,
               "livestock": _truthy(livestock) if livestock is not None else None,
               "tenant": _truthy(tenant) if tenant is not None else None}
    adv = _advisory_provider(code, sc, lang, {k: v for k, v in profile.items() if v is not None})
    g = adv.get("grounding") or {}
    out = {"lgd": code, "district": d.get("district"), "state": d.get("state"), "scenario": sc,
           "season": g.get("season"), "language": lang, "profile": g.get("profile"),
           "advisory_markdown": adv.get("markdown"), "model": adv.get("model")}
    if notes:
        out["notes"] = notes
    return out


TOOL_IMPLS: dict[str, Callable[..., dict]] = {
    "get_district": get_district, "rank_districts": rank_districts,
    "compare_scenarios": compare_scenarios, "national_summary": national_summary,
    "farmer_advice": farmer_advice,
}

_SCEN = {"type": "string", "description": "Scenario id: legacy neutral|elnino|elnino_strong, or "
         "'<season>:<phase>' such as kharif_2027:lanina or rabi_2026_27:current (phases: lanina, neutral, elnino, "
         "elnino_strong, current)"}
TOOL_SPECS: list[dict] = [
    {"name": "get_district",
     "description": "Fetch the full evidence record (risk by scenario, drivers, crops, food balance, NFHS "
                    "nutrition, climate analogs, yield sensitivity) for one district by name or LGD code. "
                    "Use 'Name, State' to disambiguate.",
     "parameters_json_schema": {"type": "object", "properties": {
         "name_or_lgd": {"type": "string", "description": "District name or numeric LGD code"},
         "scenario": _SCEN},
         "required": ["name_or_lgd"]}},
    {"name": "rank_districts",
     "description": "Rank districts by a metric, optionally within a state. Metrics: "
                    + ", ".join(sorted(METRICS)) + ". Descending by default (highest first).",
     "parameters_json_schema": {"type": "object", "properties": {
         "metric": {"type": "string", "enum": sorted(METRICS)},
         "scenario": {**_SCEN, "description": _SCEN["description"] + ". Used for risk_score and "
                      "expected_yield_shock_pct"},
         "state": {"type": "string", "description": "Optional state name filter"},
         "top_n": {"type": "integer", "description": "1-25, default 10"},
         "ascending": {"type": "boolean"}}, "required": ["metric"]}},
    {"name": "compare_scenarios",
     "description": "Risk score, band, expected yield shock and top drivers for one district under every "
                    "scenario it has, grouped by season (e.g. Rabi 2026-27 and Kharif 2027, each with La Nina, "
                    "neutral, El Nino, strong El Nino phases) plus the El Nino-minus-neutral delta per season.",
     "parameters_json_schema": {"type": "object", "properties": {
         "lgd": {"type": "string", "description": "LGD code or district name"}}, "required": ["lgd"]}},
    {"name": "farmer_advice",
     "description": "Farmer advisory for ONE district and season: what to sow / which crop or variety, sowing "
                    "window, water, crop insurance (PMFBY) and scheme pointers, in plain words. Use it for ANY "
                    "farmer-style question (what to sow, which crop, seed, insurance, schemes). Needs the district "
                    "LGD (use the SELECTED DISTRICT if the user has not named one). Returns markdown; base your "
                    "answer on it and keep it short.",
     "parameters_json_schema": {"type": "object", "properties": {
         "lgd": {"type": "string", "description": "District LGD code (or unambiguous district name)"},
         "season_scenario": {**_SCEN, "description": _SCEN["description"] + ". Default: the selected scenario"},
         "holding": {"type": "string", "enum": list(_HOLDINGS), "description": "marginal <1ha, small 1-2ha, medium_large >2ha"},
         "water": {"type": "string", "enum": list(_WATERS)},
         "crop": {"type": "string", "description": "Farmer's main crop, if stated"},
         "livestock": {"type": "boolean"}, "tenant": {"type": "boolean"},
         "language": {"type": "string", "enum": list(_LANGS), "description": "Reply language code"}},
         "required": ["lgd", "season_scenario"]}},
    {"name": "national_summary",
     "description": "National picture: districts per risk band by scenario, per-season/phase counts, people and "
                    "children under 5 in high-risk districts, states with most high-risk districts, ENSO state "
                    "and season outlook, central pool stock.",
     "parameters_json_schema": {"type": "object", "properties": {}}},
]


def run_tool(name: str, args: dict) -> dict:
    fn = TOOL_IMPLS.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}
    except Exception as e:  # never let a tool crash the chat loop
        return {"error": f"tool failed: {e}"}


def collect_lgds(obj: Any, acc: list[int]) -> None:
    """Walk a tool result and collect district LGD codes in first-seen order."""
    if isinstance(obj, dict):
        v = obj.get("lgd")
        if isinstance(v, int) and v not in acc:
            acc.append(v)
        for x in obj.values():
            collect_lgds(x, acc)
    elif isinstance(obj, list):
        for x in obj:
            collect_lgds(x, acc)
