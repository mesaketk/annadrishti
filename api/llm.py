"""Gemini integration: grounded advisories + function-calling chat, with a MOCK_LLM mode."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import config, data, personalize, seasons, tools

log = logging.getLogger("annadrishti.llm")

LANGUAGES = {
    "en": "English", "hi": "Hindi (हिन्दी, Devanagari script)", "mr": "Marathi (मराठी, Devanagari script)",
    "te": "Telugu (తెలుగు, Telugu script)", "bn": "Bengali (বাংলা, Bengali script)",
    "ta": "Tamil (தமிழ், Tamil script)", "kn": "Kannada (ಕನ್ನಡ, Kannada script)",
    "gu": "Gujarati (ગુજરાતી, Gujarati script)", "or": "Odia (ଓଡ଼ିଆ, Odia script)",
}
SCENARIO_TEXT = {
    "neutral": "NEUTRAL YEAR: climatological baseline, no ENSO-driven rainfall anomaly assumed.",
    "lanina": "LA NIÑA: district's historical La Niña-year mean rainfall anomaly (2000/07/10/11/20/21/22 analogs). "
              "For flood-prone districts the exposure is excess rain; elsewhere it is benign. An analog-based "
              "estimate, not a deterministic forecast.",
    "elnino": "EL NIÑO (current NOAA CPC outlook): district's historical El Niño-year mean JJAS rainfall "
              "anomaly, weighted by CPC event probabilities. An analog-based estimate, not a deterministic forecast.",
    "elnino_strong": "STRONG EL NIÑO ANALOG: mean of the 2002, 2009 and 2015 El Niño years for this district. "
                     "A stress-test scenario, not the central expectation.",
    "current": "CURRENT OUTLOOK: ENSO-probability-weighted mix of the La Niña, neutral and El Niño analogs for the "
               "season. An analog-based estimate, not a deterministic forecast.",
}


def scenario_text(scenario: str) -> str:
    """Description of a scenario key; season-qualified keys use their phase's text."""
    return SCENARIO_TEXT[seasons.split(scenario)[1]]


def season_block_for(scenario: str, d: dict | None = None) -> tuple[str, str | None]:
    """(SEASON CONTEXT prompt text, resolved risk key) for a scenario, optionally for one district."""
    kpis, _ = data.get_kpis()
    rkey = seasons.resolve_risk(d, scenario, kpis)[1] if d is not None else None
    return seasons.season_block(seasons.season_context(scenario, kpis, rkey)), rkey


class LLMUnavailable(Exception):
    """No Gemini credentials configured (maps to HTTP 503)."""


# ------------------------------------------------------------------ client
_client_cache: dict[tuple, Any] = {}


def get_client():
    from google import genai

    # Vertex AI takes precedence when explicitly enabled (project billing, no API key needed).
    if config.use_vertex():
        project = config.env("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise LLMUnavailable("USE_VERTEX=1 but GOOGLE_CLOUD_PROJECT is not set")
        loc = config.env("VERTEX_LOCATION", "global")
        ck = ("vertex", project, loc)
        if ck not in _client_cache:
            _client_cache[ck] = genai.Client(vertexai=True, project=project, location=loc)
        return _client_cache[ck]
    key = config.env("GEMINI_API_KEY")
    if key:
        ck = ("key", key)
        if ck not in _client_cache:
            _client_cache[ck] = genai.Client(api_key=key)
        return _client_cache[ck]
    raise LLMUnavailable("GEMINI_API_KEY not set")


def llm_ready() -> bool:
    return bool(config.mock_llm() or config.env("GEMINI_API_KEY")
                or (config.use_vertex() and config.env("GOOGLE_CLOUD_PROJECT")))


def effective_model() -> str:
    return "mock-llm" if config.mock_llm() else config.gemini_model()


# ------------------------------------------------------------------ prompts
ADVISORY_COMMON = """You are AnnaDrishti, a senior agri-food-security analyst advising Indian state agriculture, \
food & civil supplies, women & child development, rural development, health and animal husbandry departments, and \
— through them — smallholder farmers, season by season through the ENSO cycle (La Niña, neutral, El Niño). The SEASON CONTEXT \
block in the user turn tells you which season (kharif or rabi), its sowing window, status and ENSO phase; it \
overrides any El Niño-specific wording below. You write only from the structured district \
evidence supplied in the user turn.

GROUNDING RULES (non-negotiable)
1. Use ONLY facts present in the DISTRICT EVIDENCE JSON and the ENSO STATUS block. Never invent district-specific \
facts (crop areas, yields, scheme coverage, dates, stock levels, prices). If a field you would need is null or \
absent, write "data not available" for it instead of guessing. General agronomy and scheme rules given in the \
PROFILE / DEPARTMENT blocks are standing guidance, not district facts: phrase them as "consider" or "ask your KVK".
2. CITE THE NUMBERS you rely on, inline, with the unit and the scenario/year they refer to — e.g. "El Niño-scenario \
risk score 78/100 (high)", "rainfed share 86%", "foodgrain yield −14% in past El Niño-deficit years (n=5)", \
"stunting 40.1% (NFHS-5, 2019-21)". Officials: prefer 6-12 distinct cited figures over vague adjectives. Farmers: \
2-3 numbers at most, in simple words.
3. EXPRESS UNCERTAINTY honestly. The scenarios are ANALOG-BASED (historical years of the same ENSO phase), not a \
forecast of this season's rainfall. Use probability language ("likely", "roughly", "in past El Niño years this district saw…", \
"if 2015 repeats…"). State that food balance measures availability, not household access, and that risk scores \
are relative rankings. Cite the CPC probability of a historic event if given. Do not claim certainty or precision \
beyond what the data supports.
4. Distinguish evidence ("the data show") from judgement ("we recommend"). Keep recommendations realistic for a \
district administration or a smallholder with a few acres.
5. OPTIONAL EVIDENCE BLOCKS: `markets` (price_elnino_spike_pct, price_volatility_idx = how much food prices rose in \
past El Niño years), `groundwater` (gw_stress_idx, gw_premonsoon_depth_m, gw_decline_10y_m_per_yr), \
`nutrition.poshan_live` (live Poshan Tracker underweight/stunting/wasting with an as-of month) and \
`crops.economics` (cost of cultivation vs value of output) may or may not exist. Use them where relevant to the \
reader (see below) ONLY when the user turn says they are PRESENT; never mention one that is absent. A \
`season_outlook` block (rain/heat/onset for THIS season) may also be present: it is the authority for the season's \
climate; `crops.top` is already the list for this season's kind (kharif or rabi) when `crops.top_is_for_season` is set. Prefer \
poshan_live over NFHS when you describe CURRENT child malnutrition, and always give its as-of month.
6. SEASON FRAMING. Name the season and its status (sowing now / upcoming) up front and anchor timing on its sowing \
window. Follow the framing for the ENSO phase: LA NIÑA = excess rain / flood exposure (drainage, flood-tolerant seed, \
post-flood re-sowing), NEUTRAL = climatology, so focus on structural vulnerability (not an event), EL NIÑO = rain \
deficit / heat. Quote the ENSO phase probabilities for the season when given. KHARIF = monsoon-sown crops; RABI = \
winter crops (wheat, gram, mustard, rabi rice) driven by residual soil moisture, terminal heat and groundwater.
7. Output Markdown only, no preamble, no closing disclaimer paragraph beyond the required uncertainty note. Write in \
the REQUESTED LANGUAGE and script (keep scheme and unit acronyms such as PMFBY, NREGA, PDS, KVK, CDPO, ASHA as is)."""

ADVISORY_OFFICIAL = """AUDIENCE = official  (the DEPARTMENT FOCUS block in the user turn names the reader's role)
CLIMATE FRAMING: take the season's climate ONLY from the SEASON OUTLOOK block (and `season_outlook` in the evidence). \
KHARIF: monsoon rain anomaly (Jun-Sep), onset delay, heat. RABI: Oct-Dec rain and Feb-Mar heat. Never describe kharif \
with rabi numbers or rabi with kharif numbers. `climate.jjas_*` and the El Niño/La Niña mean anomaly fields are \
monsoon-season (kharif) history: do not quote them for a rabi briefing. If the SEASON OUTLOOK is absent: kharif may use \
`climate`; for rabi say the winter rain/heat outlook is not available.
Write for the named department head and field units. The department decides the CONTENT of every section and the \
FIVE ACTIONS; the structure stays fixed. Start with one title line `### <Department role> briefing: <District>` and \
then exactly these sections (## headings):
## 1. Why this district is flagged
 Explain the risk score and band under the chosen scenario and season, the top drivers (name them with their \
contribution) and how the phase's rainfall/heat anomaly and yield sensitivity become an expected yield shock \
(for neutral: what makes the district structurally vulnerable), THEN follow the department's \
SECTION FOCUS and lens (e.g. food/civil supplies: self-sufficiency, PDS dependency and the grain gap; agriculture: \
crop mix, rainfed share, yield sensitivity; WCD/Health: malnutrition and anaemia; rural development: income shock and \
NREGA demand; animal husbandry: fodder). Note hindcast evidence (e.g. 2015) if present. Where relevant use the \
optional blocks: price-spike risk (markets) for food & civil supplies and the Collector; groundwater stress \
(groundwater) for agriculture, rural development and the Collector; Poshan Tracker live underweight for WCD/ICDS, \
health and the Collector.
## 2. Who is most at risk
 The groups relevant to the department (use SECTION FOCUS), with numbers; say what cannot be determined from the data.
## 3. Five pre-positioning actions
 Exactly five numbered actions. EACH must be chosen from the department's ACTION MENU in the user turn (adapted to \
this district's numbers) and written as: **action** — responsible unit (use the named unit from the menu, e.g. \
"DSO + FPS inspectors", "CDPO + AWWs", "BDO + NREGA PO", "KVK + ATMA", "CMO + ASHAs", "Dy Director AH") — LEAD TIME \
(start/finish, anchored on the lead dates in risk.<scenario>.actions.lead if present, else on the season's sowing \
window, else relative like "within 2 weeks") — the district evidence that justifies it. Pick the five best supported by THIS district's data; do not \
recommend actions the evidence gives no basis for. Follow any DEPARTMENT RULES (the Collector also gets the \
cross-department timeline table as Section 4).
## What to tell the public
 ONE line, in the requested language, that the department could broadcast or print (follow the PUBLIC MESSAGE GUIDE).
## Confidence and caveats
 2-3 sentences: analog basis, scenario meaning, what would change the picture (actual monsoon onset/breaks or winter rain and \
temperature, reservoir and groundwater levels, sowing dates).
LENGTH: about 450 words (Collector: about 600 including the table)."""

ADVISORY_FARMER = """AUDIENCE = farmer  (the FARMER PROFILE block in the user turn describes the reader)
Write for THIS farmer, in plain, warm, simple language, in the REQUESTED LANGUAGE and script (Devanagari for \
Hindi/Marathi; Telugu, Bengali, Tamil, Kannada, Gujarati and Odia scripts likewise). Keep crop names in the local name. \
MAXIMUM 220 words total. Speak to the farmer as "you"; never recite the profile fields.
FORMAT: a title line `### <title>` that NAMES THE FARMER TYPE in the requested language (Hindi examples: \
"छोटे वर्षा-आधारित किसान के लिए", "मध्यम/बड़े सिंचित किसान के लिए"; English: "For small rainfed farmers"), then 5-7 \
short bullets.
HARD RULES
- CROPS: every crop you recommend or offer as a choice must come from the SEASON CROPS line of the farmer profile \
(the district's kharif list for kharif, rabi list for rabi) or from the crop playbook of the right season. NEVER \
suggest a rabi crop (wheat, gram, mustard...) for kharif or a kharif crop (cotton, soybean, paddy...) for rabi.
- WHY = CLIMATE ONLY: the reason for your advice is the season's weather (rain outlook, heat, monsoon onset) and \
nothing else. NO nutrition, stunting, anaemia, PDS, self-sufficiency or other statistics.
- OUTLOOK WORDING: use the PLAIN OUTLOOK sentence from the user turn for the climate bullet (translated into the \
requested language, same meaning). NEVER write phrases like "El Niño (100 %)", ENSO probabilities or percentages \
of event chance; only "very likely / likely / possible" wording as in that sentence.
- MONEY: at most ONE simple sentence, no rupee figures, no cost table, no percentages (e.g. "Last year soybean earned \
more per acre than cotton here"), only if CROP ECONOMICS is present in the profile; otherwise say nothing about money.
CONTENT, in this order (skip a bullet only if the profile makes it irrelevant):
1. The season and the climate in one bullet: name the season (e.g. "Kharif 2027") and give the PLAIN OUTLOOK sentence.
2. The main crop move: use the CROP PLAYBOOK for the farmer's main crop (reduce / replace / change variety / \
intercrop / sowing time), choosing substitutes from SEASON CROPS. Use the SEASON CONTEXT: if the season is rabi and \
sowing is open, talk about THIS winter's sowing (wheat by 15 November, gram/mustard early, protective irrigation, \
rabi rice water budget); if kharif and upcoming, talk about next kharif's planning and seed arrangement now; in a \
La Niña phase lead with drainage, flood-tolerant seed and re-sowing, not drought measures. Substitution table for \
reference when the playbook is missing or the crop is "other" (use only the rows of this season's kind):
{crop_table}
3. Sowing window and water: do not sow on the first shower; sow after adequate soil moisture; keep seed for re-sowing; \
mulching, bunds, farm ponds; protective irrigation at critical stages only.
4. PROFILE-DERIVED EMPHASIS: follow every item in the block. Marginal/small + rainfed: zero- or low-cost practices, \
PDS and NREGA linkage, intercropping. Medium/large + irrigated: protective-irrigation scheduling, water budgeting, \
diversification of part of the area. Livestock: fodder security and dual-purpose jowar/bajra. Tenant: say that PMFBY \
needs a land record or the landowner's consent and name the alternatives (WBCIS, group insurance or credit through an \
FPO/JLG). Owner: enrol in PMFBY before the notified cut-off (never state a date).
5. If `groundwater` is PRESENT and stressed (high gw_stress_idx or falling water table) and the farmer has any \
irrigation: one clause on rationing water. If `markets` is PRESENT with a price spike in past El Niño years and the \
farmer may have grain to sell or store: one clause on not selling in distress at harvest. Both only if the word limit \
allows.
6. Help: the district contingency plan from ICAR-CRIDA through the Krishi Vigyan Kendra / agriculture office.
Close with one short honest line that this is an early warning from past years, not a certain forecast. Never invent \
facts not in the evidence; if a needed field is null, say the information is not available."""

ADVISORY_SYSTEM = f"{ADVISORY_COMMON}\n\n{ADVISORY_OFFICIAL}\n\n" + ADVISORY_FARMER.replace(
    "{crop_table}", personalize.crop_substitution_table())


def advisory_system(audience: str) -> str:
    """System prompt for one audience (the shared grounding rules + that audience's section only)."""
    if audience == "farmer":
        return f"{ADVISORY_COMMON}\n\n" + ADVISORY_FARMER.replace("{crop_table}", personalize.crop_substitution_table())
    return f"{ADVISORY_COMMON}\n\n{ADVISORY_OFFICIAL}"

CHAT_SYSTEM = """You are AnnaDrishti's "Ask the map" assistant for Indian districts, season by season (Rabi 2026-27 \
and Kharif 2027, each under La Niña, neutral, El Niño or the ENSO-weighted "current" outlook). Scenario ids are \
"<season>:<phase>" (e.g. kharif_2027:lanina) or legacy neutral|elnino|elnino_strong. La Niña = excess-rain/flood \
framing; neutral = structural vulnerability; El Niño = deficit/heat. You serve FARMERS, district/state OFFICERS and \
PLANNERS. Tools over the dataset: get_district, rank_districts, compare_scenarios, national_summary, farmer_advice. \
ALWAYS call tools to get facts: never answer district-specific questions from memory. If the user asks about a place \
not in the data, say so.

FARMER QUESTIONS ARE IN SCOPE. What to sow this season, which crop or variety, sowing time, water, seed, crop \
insurance (PMFBY), schemes (NREGA, PDS linkage), fodder, what to do if rain fails: never refuse these. Call \
farmer_advice for the district and season (add get_district only if you need more district data) and answer from its \
advisory_markdown plus the district data: plain words, concrete steps, crops only from the season's own list (kharif \
crops for kharif, rabi crops for rabi). If the farmer states holding size, irrigation, crop, livestock or tenancy, \
pass them to farmer_advice. If a REPLY LANGUAGE is given, answer in that language and script.
DISTRICT: when a SELECTED DISTRICT is given, use it by default whenever the user names no other district. If a \
farmer-type question arrives and there is NO selected or named district, do not refuse and do not guess: ask ONE \
short clarifying question ("Which district are you in?") and nothing else.
Decline only what is genuinely outside the dataset (non-agriculture topics, places not in the data) and say what you \
can help with instead.

OFFICER / PLANNER STYLE: concise (usually under 180 words), Markdown, lead with the answer. ALWAYS name districts \
(with state) and quote the numbers you used (risk score, band, yield shock %, self-sufficiency, stunting %, etc.) with \
the scenario. End with 1-3 concrete suggested actions where relevant (PDS top-up, fodder, NREGA, short-duration seed \
banks, pulses/millet promotion, PMFBY enrolment, anganwadi nutrition).
GROUNDING AND UNCERTAINTY (all users): scenarios are analog-based (past years of the same ENSO phase), not forecasts; \
food balance is availability, not access; risk scores are relative rankings. If a value is null or a tool returns an \
error, say data is not available: never invent figures. Default to the scenario/season selected by the user unless \
they ask otherwise; always name the season in your answer."""

ROLE_TEXT = {
    "farmer": "USER ROLE: farmer. Answer in AT MOST 120 words, in plain everyday words, a few short bullets, no tables "
              "and no risk scores or jargon unless the farmer asks. Climate reasons only (rain, heat, onset), no "
              "nutrition or PDS statistics. Include one short honest line that this is an early warning, not a "
              "forecast.",
    "officer": "USER ROLE: officer. Use the officer/planner style: districts named with numbers, concrete actions.",
    "planner": "USER ROLE: planner. Use the officer/planner style: districts named with numbers, concrete actions.",
}


def chat_system(scenario: str, lgd: int | None = None, role: str | None = None,
                language: str | None = None) -> str:
    """Full chat system prompt: base + selected scenario/season + SELECTED DISTRICT + role + language."""
    kpis, _ = data.get_kpis()
    parts = [CHAT_SYSTEM, f"Selected scenario: {scenario}\n{season_block_for(scenario)[0]}\n"
                          f"ENSO STATUS: {_enso_block(kpis)}"]
    d = data.district_by_lgd(lgd) if lgd is not None else None
    if d is not None:
        parts.append(f"SELECTED DISTRICT: {d.get('district')} ({d.get('lgd')}), {d.get('state')}. Use it by default "
                     f"for 'my district', 'here' and any question that names no district; pass lgd={d.get('lgd')} to "
                     f"farmer_advice. Climate for the selected season: {seasons.plain_outlook(d, scenario, kpis)}.")
    if role in ROLE_TEXT:
        parts.append(ROLE_TEXT[role])
    if language and language != "en" and language in LANGUAGES:
        parts.append(f"REPLY LANGUAGE: {LANGUAGES[language]}. Write the whole answer in it.")
    return "\n\n".join(parts)


def _enso_block(kpis: dict) -> str:
    enso = kpis.get("enso") or {}
    cp = kpis.get("central_pool") or {}
    return json.dumps({"enso": enso, "central_pool": cp or None, "as_of": kpis.get("as_of")},
                      ensure_ascii=False)


FARMER_DROP = ("nutrition", "food_balance", "children_u5_est", "population_2026")  # not part of a farmer's "why"


def outlook_block(d: dict, scenario: str, audience: str) -> str:
    """SEASON OUTLOOK prompt block (Addendum I): the district's rain/heat/onset entry for the season, plus for
    farmers the one-sentence plain wording (entry.plain, else built from the phase probability)."""
    kpis, _ = data.get_kpis()
    sctx = seasons.season_context(scenario, kpis)
    entry = seasons.district_outlook(d, scenario, kpis)
    head = f"SEASON OUTLOOK ({sctx['label']}, {sctx['kind']}; this season's climate, use ONLY this for rain/heat framing):"
    if audience == "farmer":
        return (f"{head}\nPLAIN OUTLOOK SENTENCE (use this for the climate bullet, translated; do not write ENSO "
                f"percentages): {seasons.plain_outlook(d, scenario, kpis)}")
    if entry:
        body = {k: v for k, v in entry.items() if k != "plain"}
        return f"{head}\n{json.dumps(body, ensure_ascii=False, separators=(',', ':'))}\nPlain: {entry.get('plain') or '-'}"
    return (f"{head}\nnot available for this district: for kharif use `climate`; for rabi say the winter rain/heat "
            f"outlook is not available.")


def build_advisory_prompt(d: dict, audience: str, language: str, scenario: str, profile: dict | None = None,
                          department: str | None = None) -> tuple[str, list[str]]:
    kpis, _ = data.get_kpis()
    ctx, fields = tools.district_context(d, scenario)
    sblock, rkey = season_block_for(scenario, d)
    sctx = seasons.season_context(scenario, kpis, rkey)
    kind, phase = sctx["kind"], sctx["phase"]
    if audience == "farmer":
        for k in FARMER_DROP:
            ctx.pop(k, None)
        fields = []
        tools._flatten("", ctx, fields)
        focus = personalize.profile_block(personalize.resolve_profile(profile, d, kind), d, ctx, kind, phase)
        task = "Write the farmer advisory for THIS farmer now"
    else:
        focus = personalize.department_block(department or personalize.DEFAULT_DEPARTMENT, ctx, rkey or scenario,
                                             kind, phase)
        task = "Write the department advisory now"
    prompt = (
        f"AUDIENCE: {audience}\nREQUESTED LANGUAGE: {LANGUAGES[language]}\n"
        f"SCENARIO: {scenario} — {scenario_text(scenario)}\n"
        f"{sblock}\n{outlook_block(d, scenario, audience)}\n"
        f"Focus the risk narrative on risk.{rkey or scenario}; mention the other phases only for contrast.\n\n"
        f"{focus}\n\n"
        f"ENSO STATUS (national):\n{_enso_block(kpis)}\n\n"
        f"DISTRICT EVIDENCE (JSON; null/absent = data not available):\n"
        f"{json.dumps(ctx, ensure_ascii=False, separators=(',', ':'))}\n\n"
        f"{task}, following the system instructions exactly."
    )
    return prompt, fields


# ------------------------------------------------------------------ generation
def _transient(err: Exception) -> bool:
    msg = str(err)
    return any(code in msg for code in ("429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "overloaded"))


def generate_with_fallback(client, model: str, *, allow_fallback: bool = True, **kwargs):
    """generate_content with retry/backoff on transient errors and a fallback model.

    Returns (response, model_used). Fallback model: GEMINI_FALLBACK_MODEL (default gemini-2.5-flash).
    """
    import time
    fallback = config.env("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
    models = [model] + ([fallback] if allow_fallback and fallback and fallback != model else [])
    last: Exception | None = None
    for m in models:
        for delay in (0, 2, 5, 10):
            if delay:
                time.sleep(delay)
            try:
                return client.models.generate_content(model=m, **kwargs), m
            except Exception as e:  # noqa: BLE001
                last = e
                if not _transient(e):
                    break  # e.g. 404/400 -> try fallback model right away
    raise RuntimeError(f"Gemini request failed on {models}: {last}")


def generate_advisory(d: dict, audience: str, language: str, scenario: str, profile: dict | None = None,
                      department: str | None = None) -> tuple[str, list[str], str]:
    """Returns (markdown, fields_used, model). `profile` (farmer) / `department` (official) per Addendum C."""
    prompt, fields = build_advisory_prompt(d, audience, language, scenario, profile, department)
    if config.mock_llm():
        return mock_advisory(d, audience, language, scenario, profile, department), fields, "mock-llm"
    from google.genai import types

    client = get_client()
    model = config.gemini_model()
    resp, model = generate_with_fallback(
        client, model, contents=prompt,
        config=types.GenerateContentConfig(system_instruction=advisory_system(audience), temperature=0.3))
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response (possibly blocked by safety filters)")
    return text, fields, model


def run_chat(messages: list[dict], scenario: str, lgd: int | None = None, role: str | None = None,
             language: str | None = None) -> tuple[str, list[int]]:
    if config.mock_llm():
        return mock_chat(messages, scenario, lgd, role, language)
    from google.genai import types

    client = get_client()
    model = config.gemini_model()
    system = chat_system(scenario, lgd, role, language)
    contents = [types.Content(role="user" if m["role"] == "user" else "model",
                              parts=[types.Part.from_text(text=m["content"])]) for m in messages]
    tool_cfg = [types.Tool(function_declarations=[types.FunctionDeclaration(**s) for s in tools.TOOL_SPECS])]
    cfg_tools = types.GenerateContentConfig(
        system_instruction=system, temperature=0.2, tools=tool_cfg,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    cfg_plain = types.GenerateContentConfig(system_instruction=system, temperature=0.2)
    lgds: list[int] = []
    max_rounds = 4
    resp = None
    for rnd in range(max_rounds + 1):
        # after max_rounds tool rounds, force a plain-text answer
        resp, model = generate_with_fallback(client, model, allow_fallback=(rnd == 0), contents=contents,
                                             config=cfg_tools if rnd < max_rounds else cfg_plain)
        calls = resp.function_calls if rnd < max_rounds else None
        if not calls:
            break
        # echo the model turn verbatim (keeps thought signatures intact for Gemini 3)
        contents.append(resp.candidates[0].content)
        parts = []
        for c in calls:
            args = dict(c.args or {})
            if c.name in ("rank_districts", "get_district"):
                args.setdefault("scenario", scenario)
            elif c.name == "farmer_advice":
                args.setdefault("season_scenario", scenario)
                if lgd is not None:
                    args.setdefault("lgd", lgd)
                if language:
                    args.setdefault("language", language)
            result = tools.run_tool(c.name, args)
            tools.collect_lgds(result, lgds)
            parts.append(types.Part.from_function_response(name=c.name, response={"result": result}))
        contents.append(types.Content(role="user", parts=parts))
    reply = ((resp.text if resp else None) or "").strip() or \
        "I could not produce an answer for that question. Please try rephrasing."
    return reply, lgds[:15]


# ------------------------------------------------------------------ MOCK_LLM
def _fmt(v: Any, suffix: str = "") -> str:
    return "data not available" if v is None else f"{v}{suffix}"


_HI_HOLDING = {"marginal": "सीमांत", "small": "छोटे", "medium_large": "मध्यम/बड़े"}
_HI_WATER = {"rainfed": "वर्षा-आधारित", "partial": "आंशिक सिंचित", "irrigated": "सिंचित"}
_HI_CROP = {
    "paddy": "धान: कम अवधि (100-120 दिन) की किस्में या SRI अपनाएँ; ऊँची/असमतल ज़मीन पर रागी, बाजरा, मूँग या तुअर बोएँ।",
    "cotton": "कपास: कतारों के बीच मूँग/उड़द की अंतर-फसल लें; देर से बुवाई न करें।",
    "soybean": "सोयाबीन: मानसून देर से आए तो मूँग/उड़द बोएँ; कम अवधि की किस्म चुनें।",
    "maize": "मक्का: असिंचित खेत में बाजरा या ज्वार बेहतर है; मक्का रखें तो जल्दी पकने वाली किस्म चुनें।",
    "groundnut": "मूँगफली: सूखे का डर हो तो कुछ खेत में अरंडी या कुल्थी बोएँ।",
    "wheat": "गेहूँ: गर्मी सहने वाली किस्म चुनें और 15 नवंबर से पहले समय पर बुवाई करें।",
    "gram": "चना: अक्टूबर में जल्दी बुवाई करें, नमी बचाएँ (मल्चिंग), बीज उपचार करें।",
}
_HI_EVENT = {("elnino", "kharif"): "कमज़ोर मानसून", ("elnino_strong", "kharif"): "बहुत कमज़ोर मानसून",
             ("elnino", "rabi"): "सूखी, गर्म सर्दी", ("elnino_strong", "rabi"): "बहुत सूखी, गर्म सर्दी",
             ("lanina", "kharif"): "भारी बारिश और बाढ़", ("lanina", "rabi"): "सामान्य से अधिक नमी वाली सर्दी",
             ("neutral", "kharif"): "सामान्य मौसम", ("neutral", "rabi"): "सामान्य मौसम"}
_HI_LIKELY = {"very likely": "की संभावना बहुत अधिक है", "likely": "की संभावना अधिक है", "possible": "संभव है"}
_EN_FLAGS = {
    "zero_cost": "Zero-cost steps first: mulch with crop residue, make field bunds, intercrop a pulse with the cereal. "
                 "Keep your ration card and NREGA job card ready (ask the Gram Panchayat).",
    "irrigated_big": "Make a water budget for the season, irrigate only at critical stages, and put part of the area "
                     "under pulses or millets instead of the thirsty crop.",
    "mixed": "Use your limited water at the critical stage of the main crop; mulch and bund the dry part.",
    "livestock": "Animals: store stover and grow fodder jowar/bajra (dual-purpose); do not sell animals in distress.",
    "tenant": "PMFBY needs a land record or the landowner's consent; ask your bank/CSC, or look at WBCIS or group "
              "insurance through an FPO.",
    "owner": "Enrol in PMFBY before the notified cut-off date (check locally).",
}


def mock_advisory(d: dict, audience: str, language: str, scenario: str, profile: dict | None = None,
                  department: str | None = None) -> str:
    ctx, _ = tools.district_context(d, scenario)
    kpis, _ = data.get_kpis()
    rkey = seasons.resolve_risk(d, scenario, kpis)[1]
    sctx = seasons.season_context(scenario, kpis, rkey)
    kind, phase, season_label = sctx["kind"], sctx["phase"], sctx["label"]
    r = (ctx.get("risk") or {}).get(rkey or scenario) or {}
    name, state = ctx["district"], ctx["state"]
    crops = ctx["crops"]
    top = ", ".join(c["crop"] for c in crops.get("top", [])[:3]) or "data not available"
    nf = tools._nfhs(d, "stunting")
    tag = "*[MOCK_LLM — canned response, not generated by Gemini]*\n\n"
    if audience == "farmer":
        p = personalize.resolve_profile(profile, d, kind)
        pb = personalize.crop_playbook(p["crop"], kind, phase)
        plain = seasons.plain_outlook(d, scenario, kpis)
        sow = sctx.get("sowing") or "data not available"
        season_en = f"{season_label} ({sctx.get('status') or 'status n/a'}; sowing {sow})"
        if language == "hi":
            title = f"### {_HI_HOLDING[p['holding']]} {_HI_WATER[p['water']]} किसान के लिए"
            lk = _HI_LIKELY[seasons.likelihood_word(seasons.phase_probability(scenario, kpis))]
            rain_hi = f"- मौसम का अनुमान: {_HI_EVENT.get((phase, kind or 'kharif'), 'सामान्य मौसम')} {lk}।"
            if phase == "lanina":
                rain_hi += " जल-निकासी और बाढ़-सहनशील बीज पर ध्यान दें।"
            b = [f"- मौसम: {season_en}।", rain_hi,
                 "- " + _HI_CROP.get(pb["key"] if pb else "", f"मुख्य फसल {p['crop']}: कम पानी वाली फसल और कम अवधि की किस्में चुनें।"),
                 "- पहली बारिश पर बुवाई न करें; मिट्टी में नमी आने पर बोएँ, बीज बचाकर रखें।"]
            if p["holding"] in ("marginal", "small") and p["water"] == "rainfed":
                b.append("- बिना खर्च के उपाय: फसल अवशेष की मल्चिंग, मेड़बंदी, अनाज के साथ दलहन की अंतर-फसल; राशन कार्ड और मनरेगा जॉब कार्ड तैयार रखें।")
            elif p["holding"] == "medium_large" and p["water"] == "irrigated":
                b.append("- पानी का बजट बनाएँ, सिंचाई केवल नाज़ुक अवस्थाओं पर करें और कुछ खेत में दलहन/मोटा अनाज लगाएँ।")
            else:
                b.append("- सीमित पानी फसल की नाज़ुक अवस्था में दें; बाकी खेत में मल्चिंग और मेड़बंदी करें।")
            if p["livestock"]:
                b.append("- पशु: भूसा/चारा जमा करें, चारे के लिए ज्वार-बाजरा बोएँ; संकट में पशु न बेचें।")
            b.append("- बीमा: ज़मीन के कागज़ या मालिक की सहमति के बिना PMFBY नहीं मिलता; बैंक/CSC से WBCIS या FPO के समूह बीमा के बारे में पूछें।"
                     if p["tenant"] else "- फसल बीमा (PMFBY) की अंतिम तिथि से पहले नामांकन करें (तिथि स्थानीय रूप से देखें)।")
            b.append("- योजना: ICAR-CRIDA जिला आकस्मिक योजना, कृषि विज्ञान केंद्र से लें।")
            b.append("_यह पिछले वर्षों पर आधारित पूर्व-चेतावनी है, निश्चित पूर्वानुमान नहीं।_")
            return tag + title + "\n" + "\n".join(b)
        note = "" if language == "en" else f"_(Mock: {LANGUAGES[language]} translation not available in mock mode.)_\n"
        title = f"### For {personalize.farmer_type_label(p).replace('farmer', 'farmers')}"
        crop_line = (f"Your {pb['label']}: {pb['advice']}" if pb else
                     f"Your crop ({p['crop']}): prefer short-duration, drought-tolerant choices (bajra, jowar, ragi, moong, horse gram).")
        rain_en = f"{plain}. Main crops this season: {top}."
        b = [f"- Season: {season_en}.", f"- {rain_en}",
             f"- {crop_line}",
             "- Do not sow on the first shower; wait for soil moisture and keep seed for re-sowing."]
        if p["holding"] in ("marginal", "small") and p["water"] == "rainfed":
            b.append("- " + _EN_FLAGS["zero_cost"])
        elif p["holding"] == "medium_large" and p["water"] == "irrigated":
            b.append("- " + _EN_FLAGS["irrigated_big"])
        else:
            b.append("- " + _EN_FLAGS["mixed"])
        if p["livestock"]:
            b.append("- " + _EN_FLAGS["livestock"])
        b.append("- " + _EN_FLAGS["tenant" if p["tenant"] else "owner"])
        b.append("- Contingency plan: ICAR-CRIDA district contingency plan (ask your KVK).")
        b.append(f"_Early warning for {season_label} based on past years, not a certain forecast._")
        return tag + note + title + "\n" + "\n".join(b)
    # ---- official, by department
    dept = department or personalize.DEFAULT_DEPARTMENT
    cat = personalize.DEPT_CATALOG[dept]
    menu = personalize.dept_menu(dept, kind)
    actions = "\n".join(f"{i}. **{a}** — {u} — {t}" for i, (a, u, t) in enumerate(menu[:5], 1))
    timeline = ""
    if dept == "collector":
        rows = "\n".join(f"| {a} | {u} | {t} |" for a, u, t in menu)
        timeline = f"\n\n## 4. Cross-department timeline\n| Action | Department | By when |\n|---|---|---|\n{rows}"
    return (tag + f"### {personalize.DEPT_SHORT[dept]} briefing: {name}\n\n## 1. Why this district is flagged\n"
            f"{name}, {state} scores **{_fmt(r.get('score'))}/100 ({_fmt(r.get('band'))})** for **{season_label}** "
            f"({sctx.get('status') or 'status n/a'}; sowing {sctx.get('sowing') or 'data not available'}) under the "
            f"*{scenario}* scenario ({sctx['phase_label']}), with an expected foodgrain yield shock of {_fmt(r.get('expected_yield_shock_pct'), '%')}. "
            f"Rainfed share is {_fmt(crops.get('rainfed_share'))}; self-sufficiency is "
            f"{_fmt((ctx.get('food_balance') or {}).get('self_sufficiency'))}. Lens for this department: {cat['lens']}.\n\n"
            "## 2. Who is most at risk\n"
            f"Children under 5 (~{_fmt(ctx.get('children_u5_est'))}; stunting {_fmt(nf, '%')}), women with anaemia "
            f"({_fmt(tools._nfhs(d, 'women_anaemia'), '%')}), and rainfed smallholders growing {top}. "
            f"Reader: {cat['reader']}.\n\n"
            f"## 3. Five pre-positioning actions\n{actions}{timeline}\n\n"
            f"## What to tell the public\n{cat['public']}\n\n"
            f"## Confidence and caveats\nAnalog-based (past years of the {sctx['phase_label']} phase) for {season_label}, "
            "not a forecast; availability, not access.")


_METRIC_WORDS = [("stunting", "stunting"), ("anaemi", "child_anaemia"), ("anemi", "child_anaemia"),
                 ("wasting", "wasting"), ("self-suff", "self_sufficiency"), ("sufficien", "self_sufficiency"),
                 ("yield", "expected_yield_shock_pct"), ("population", "population_2026"),
                 ("rainfed", "rainfed_share"), ("pulse", "risk_score"), ("risk", "risk_score")]


_FARMER_RX = re.compile(r"\b(sow\w*|plant\w*|crops?|seeds?|variet\w+|farm\w*|kisan|insur\w+|pmfby|schemes?|irrigat\w*|"
                        r"fertili[sz]\w+|harvest\w*|acres?|hectares?|bigha|my (field|land|crop)s?)\b")
CLARIFY_DISTRICT = "Which district are you in?"


def is_farmer_question(text: str) -> bool:
    return bool(_FARMER_RX.search(text.lower()))


def mock_chat(messages: list[dict], scenario: str, lgd: int | None = None, role: str | None = None,
              language: str | None = None) -> tuple[str, list[int]]:
    q = (messages[-1]["content"] if messages else "").lower()
    districts, _ = data.get_districts()
    lgds: list[int] = []
    named = next((d for d in districts if str(d.get("district", "")).strip()
                  and re.search(rf"\b{re.escape(str(d['district']).lower())}\b", q)), None)
    # farmer-style question (what to sow, insurance, schemes...): answer from farmer_advice, never refuse
    if role != "officer" and role != "planner" and is_farmer_question(q) and \
            (role == "farmer" or not any(w in q for w in ("rank", "highest", "lowest", "which districts", "compare"))):
        target = named["lgd"] if named else lgd
        if target is None:
            return CLARIFY_DISTRICT, []
        res = tools.run_tool("farmer_advice", {"lgd": target, "season_scenario": scenario,
                                               "language": language or "en"})
        tools.collect_lgds(res, lgds)
        if res.get("advisory_markdown"):
            return "*[MOCK_LLM]* " + res["advisory_markdown"].split("\n\n", 1)[-1], lgds
        return f"*[MOCK_LLM]* Farmer advice is not available right now ({res.get('error')}).", lgds
    # a specific district mentioned?
    if named:
        d = named
        cmp = tools.compare_scenarios(d["lgd"])
        tools.collect_lgds(cmp, lgds)
        sc = cmp.get("scenarios", {})
        lines = [f"- {s}: score {v.get('score')} ({v.get('band')}), yield shock {v.get('expected_yield_shock_pct')}%"
                 for s, v in sc.items()]
        if cmp.get("by_season"):
            lines.append("Seasons: " + ", ".join(b["label"] for b in cmp["by_season"].values()))
        return (f"*[MOCK_LLM]* **{d['district']}, {d['state']}** across scenarios:\n" + "\n".join(lines)
                + "\n\nAnalog-based estimate, not a forecast. Suggested: PDS top-up, short-duration seed bank, PMFBY enrolment.",
                lgds)
    state = next((s for s in {d.get("state") for d in districts if d.get("state")} if s.lower() in q), None)
    metric = next((m for w, m in _METRIC_WORDS if w in q), "risk_score")
    asc = any(w in q for w in ("lowest", "least", "best"))
    res = tools.rank_districts(metric, scenario, state, 5, asc)
    tools.collect_lgds(res, lgds)
    rows = "\n".join(f"{i+1}. **{r['district']}, {r['state']}**: {r['value']}"
                     for i, r in enumerate(res.get("results", [])))
    where = f" in {state}" if state else ""
    label = seasons.season_context(scenario, data.get_kpis()[0])["label"]
    return (f"*[MOCK_LLM]* Top districts{where} by `{metric}` ({scenario} scenario, {label}):\n{rows}\n\n"
            "Scenarios are analog-based (past years of the same ENSO phase), not forecasts. Consider PDS top-up and "
            "pulses/millet seed pre-positioning where scores are highest.", lgds)


# ------------------------------------------------------------------ state brief
STATE_BRIEF_SYSTEM = """You are AnnaDrishti, a senior food-security planner writing a state-level pre-positioning \
brief for the Chief Secretary's climate-preparedness cell, for ONE season and ENSO phase (see SEASON CONTEXT; La Niña = \
flood/excess-rain framing, neutral = structural vulnerability, El Niño = deficit/heat). You are given the ACTUAL planner rows for the \
state's districts (computed deterministically from the risk model) plus state totals and the ENSO status.

RULES: write large quantities readably (e.g. '1.86 lakh tonnes', '24.1 lakh children', '25.7 crore person-days'), never raw floats like 186026.0; use ONLY numbers present in the rows/totals; cite them (district name, score, tonnes, children, hectares, \
person-days) inline; the row/total key `mgnrega_persondays` is the NREGA person-day target: always write "NREGA" and label it "NREGA person-days"; never invent stock levels, prices, budgets or scheme coverage. null = "data not available". \
The scenario is ANALOG-BASED (past years of that ENSO phase), not a forecast; quantities are planning targets, not \
entitlements; food balance measures availability, not access. Use probability language and say what would change \
the plan. Output Markdown only, concise (about 450-650 words), with these sections:
## Situation (3-4 sentences: ENSO status with CPC probability, scenario, state totals, how many districts are high band)
## Priority districts (a Markdown table of the top 10 rows by score: district, score/band, grain_preposition_t, \
pulses_preposition_t, anganwadi_children, seed_bank_ha, NREGA person-days; dash for null) followed by 2-3 sentences \
on what stands out
## Timeline (anchor on the selected season's sowing window and the lead times in the rows; Rabi: sow by 15 Nov, \
Kharif: pre-position by mid-May; say which actions fall in which window)
## Who does what (bullets per department with quantified asks: Food & Civil Supplies, WCD/ICDS, Agriculture, \
Rural Development/NREGA, Health)
## Confidence and caveats (2-3 sentences)"""


def build_state_brief_prompt(state: str, scenario: str, rows: list[dict], totals: dict, n_high: int) -> str:
    kpis, _ = data.get_kpis()
    top = [{k: v for k, v in r.items() if not str(k).startswith("lead_")} for r in rows[:10]]
    leads = {"rabi_2026_27": next((r.get("lead_rabi_2026_27") for r in rows if r.get("lead_rabi_2026_27")), None) or "by 2026-11-15",
             "kharif_2027": next((r.get("lead_kharif_2027") for r in rows if r.get("lead_kharif_2027")), None) or "by 2027-05-15"}
    for r in rows:  # lead times of any further season columns
        for k, v in r.items():
            if str(k).startswith("lead_") and v and k[5:] not in leads:
                leads[k[5:]] = v
    def _round(o):
        if isinstance(o, float):
            return int(round(o)) if abs(o) >= 100 else round(o, 1)
        if isinstance(o, dict):
            return {k: _round(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_round(v) for v in o]
        return o
    totals = _round(totals); top = _round(top)
    return (f"STATE: {state}\nSCENARIO: {scenario} — {scenario_text(scenario)}\n{season_block_for(scenario)[0]}\n"
            f"ENSO STATUS:\n{_enso_block(kpis)}\n\n"
            f"STATE TOTALS (sum over all {len(rows)} districts with action rows; {n_high} in high band):\n"
            f"{json.dumps(totals)}\n\nLEAD TIMES: {json.dumps(leads)}\n\n"
            f"TOP 10 DISTRICTS BY RISK SCORE (JSON rows):\n{json.dumps(top, ensure_ascii=False, separators=(',', ':'))}\n\n"
            "Write the state brief now, following the system instructions exactly.")


def generate_state_brief(state: str, scenario: str, rows: list[dict], totals: dict) -> tuple[str, str]:
    n_high = sum(1 for r in rows if r.get("band") == "high")
    if config.mock_llm():
        return mock_state_brief(state, scenario, rows, totals, n_high), "mock-llm"
    from google.genai import types

    client = get_client()
    model = config.gemini_model()
    resp, model = generate_with_fallback(
        client, model, contents=build_state_brief_prompt(state, scenario, rows, totals, n_high),
        config=types.GenerateContentConfig(system_instruction=STATE_BRIEF_SYSTEM, temperature=0.3))
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response (possibly blocked by safety filters)")
    return text, model


def mock_state_brief(state: str, scenario: str, rows: list[dict], totals: dict, n_high: int) -> str:
    def v(x):
        return "-" if x is None else f"{x:,}" if isinstance(x, (int, float)) else str(x)

    table = "\n".join(f"| {r['district']} | {v(r.get('score'))} ({v(r.get('band'))}) | {v(r.get('grain_preposition_t'))} | "
                      f"{v(r.get('pulses_preposition_t'))} | {v(r.get('anganwadi_children'))} | {v(r.get('seed_bank_ha'))} | "
                      f"{v(r.get('mgnrega_persondays'))} |" for r in rows[:10])
    return ("*[MOCK_LLM — canned response, not generated by Gemini]*\n\n"
            f"## Situation\n{state}, {seasons.season_context(scenario, data.get_kpis()[0])['label']}, *{scenario}* scenario: {n_high} of {len(rows)} districts are high band. "
            f"Total grain pre-positioning target {v(totals.get('grain_preposition_t'))} t.\n\n"
            "## Priority districts\n| District | Score | Grain (t) | Pulses (t) | Anganwadi children | Seed bank (ha) | NREGA person-days |\n"
            f"|---|---|---|---|---|---|---|\n{table}\n\n"
            "## Timeline\n- Rabi 2026-27: sow by 15 Nov 2026 (heat-tolerant wheat seed, protective irrigation, PMFBY, wheat lifting).\n"
            "- Kharif 2027: by 15 May 2027 (grain and pulses stock, NREGA works, drainage works where flood-prone).\n\n"
            "## Who does what\n- **Food & Civil Supplies**: pre-position grain.\n- **WCD/ICDS**: anganwadi supplementary nutrition.\n"
            "- **Agriculture**: short-duration seed banks, PMFBY.\n- **Rural Development**: NREGA work-demand surge.\n"
            "- **Health**: anaemia screening and IFA supplementation.\n\n"
            "## Confidence and caveats\nAnalog-based planning targets, not a forecast.")


# ------------------------------------------------------------------ audio (TTS)
def strip_markdown(md: str) -> str:
    t = re.sub(r"^\s*\*\[MOCK_LLM[^\n]*\n", "", md)
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*+•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.M)
    t = re.sub(r"[*_`>|]+", "", t)
    return re.sub(r"\n{2,}", "\n", t).strip()


def pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def silent_wav(seconds: float = 1.0, rate: int = 24000) -> bytes:
    return pcm_to_wav(b"\x00\x00" * int(rate * seconds), rate)


def synthesize_speech(text: str) -> bytes:
    """Gemini TTS -> WAV bytes (24 kHz, 16-bit, mono).

    Tries the configured TTS model, then a fallback model; retries with backoff on 429/5xx so
    a temporarily exhausted quota on a new model does not break the voice feature.
    """
    import time
    from google.genai import types

    client = get_client()
    primary = config.env("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
    fallback = config.env("GEMINI_TTS_FALLBACK_MODEL", "gemini-2.5-flash-preview-tts")
    voice = config.env("TTS_VOICE", "Kore")
    models = [primary] + ([fallback] if fallback and fallback != primary else [])
    cfg = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))))
    last_err: Exception | None = None
    for model in models:
        for attempt, delay in enumerate((0, 3, 8)):
            if delay:
                time.sleep(delay)
            try:
                resp = client.models.generate_content(model=model, contents=text, config=cfg)
                part = resp.candidates[0].content.parts[0]
                inline = part.inline_data
                if inline is None or not inline.data:
                    raise RuntimeError("Gemini TTS returned no audio")
                rate = 24000
                m = re.search(r"rate=(\d+)", inline.mime_type or "")
                if m:
                    rate = int(m.group(1))
                if (inline.mime_type or "").startswith("audio/wav"):
                    return inline.data
                return pcm_to_wav(inline.data, rate)
            except Exception as e:  # noqa: BLE001 - retry on quota/transient, fall through to next model
                last_err = e
                msg = str(e)
                transient = any(code in msg for code in ("429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE"))
                if not transient:
                    break  # e.g. 404 model not found -> try the fallback model immediately
    raise RuntimeError(f"Gemini TTS failed on {models}: {last_err}")
