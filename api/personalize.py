"""Personalisation layer for advisories (docs/SCHEMA.md Addendum C).

Holds the enums, profile resolution/normalisation, the per-department catalogue (lens, named responsible units,
action menu with lead times), the crop substitution playbook, and the helpers that turn a profile into prompt text.
Pure data + string building: no network, no Gemini; used by llm.py (prompts + MOCK_LLM) and main.py (cache keys).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

HOLDINGS = ("marginal", "small", "medium_large")
WATERS = ("rainfed", "partial", "irrigated")
DEPARTMENTS = ("collector", "food_civil_supplies", "agriculture", "wcd_icds", "rural_development", "health",
               "animal_husbandry")
DEFAULT_HOLDING, DEFAULT_WATER, DEFAULT_DEPARTMENT = "small", "rainfed", "collector"

HOLDING_TEXT = {"marginal": "marginal farmer, holding under 1 ha", "small": "small farmer, holding 1-2 ha",
                "medium_large": "medium/large farmer, holding over 2 ha"}
WATER_TEXT = {"rainfed": "fully rainfed (no assured irrigation)",
              "partial": "partly irrigated (limited / unreliable irrigation source)",
              "irrigated": "assured irrigation (canal / tubewell / well)"}


# ------------------------------------------------------------------ profile
PROMPT_VERSION = "p2"  # bump when advisory prompts change materially: part of every cache/audio variant key


def season_top(d: dict, kind: str | None) -> tuple[list[dict], str]:
    """The district's top crops for a season kind (Addendum I): `crops.by_season[kind].top` when present and
    non-empty, else the all-year `crops.top`. Returns (rows, source) with source 'season' | 'all_year'."""
    crops = d.get("crops") or {}
    bs = crops.get("by_season")
    if kind and isinstance(bs, dict) and isinstance(bs.get(kind), dict):
        top = [c for c in (bs[kind].get("top") or []) if isinstance(c, dict) and c.get("crop")]
        if top:
            return top, "season"
    return [c for c in (crops.get("top") or []) if isinstance(c, dict) and c.get("crop")], "all_year"


def district_top_crops(d: dict, kind: str | None = None) -> list[str]:
    return [str(c.get("crop")) for c in season_top(d, kind)[0]]


def resolve_profile(raw: dict | None, d: dict, kind: str | None = None) -> dict:
    """Fill defaults. crop: the district's top crop for the season `kind` (crops.by_season[kind].top[0], else
    crops.top[0]) when absent; case-insensitive match against those top crops is canonicalised; 'other' and
    unknown crops are kept as given."""
    raw = {k: v for k, v in (raw or {}).items() if v is not None}
    tops = district_top_crops(d, kind)
    crop = str(raw.get("crop") or "").strip()
    if not crop:
        crop = tops[0] if tops else "other"
    else:
        crop = next((t for t in tops if t.lower() == crop.lower()), "other" if crop.lower() == "other" else crop)
    return {"holding": raw.get("holding") or DEFAULT_HOLDING, "water": raw.get("water") or DEFAULT_WATER,
            "crop": crop, "livestock": bool(raw.get("livestock", False)), "tenant": bool(raw.get("tenant", False))}


def profile_variant(p: dict) -> str:
    """Stable cache-key fragment (no '|')."""
    return (f"{PROMPT_VERSION};h={p['holding']};w={p['water']};c={str(p['crop']).lower()};"
            f"l={int(bool(p['livestock']))};t={int(bool(p['tenant']))}")


def variant_for(audience: str, profile: dict | None, department: str | None) -> str:
    return f"{PROMPT_VERSION};dept={department or DEFAULT_DEPARTMENT}" if audience == "official" else profile_variant(profile or {
        "holding": DEFAULT_HOLDING, "water": DEFAULT_WATER, "crop": "other", "livestock": False, "tenant": False})


def variant_slug(variant: str) -> str:
    return hashlib.sha1(variant.encode()).hexdigest()[:10]


def farmer_type_label(p: dict) -> str:
    """English farmer-type label, e.g. 'small rainfed farmer'."""
    h = {"marginal": "marginal", "small": "small", "medium_large": "medium/large"}[p["holding"]]
    w = {"rainfed": "rainfed", "partial": "partly irrigated", "irrigated": "irrigated"}[p["water"]]
    return f"{h} {w} farmer"


# ------------------------------------------------------------------ crop playbook (general agronomy, not district facts)
# (key, regex, season, label, advice)
_CROPS: list[tuple[str, str, str, str, str]] = [
    ("tur", r"\b(tur|arhar|pigeon ?pea|red gram)\b", "kharif", "Tur / arhar",
     "Already hardy. Keep it as an intercrop with jowar/bajra/soybean, sow on ridges, and give one protective "
     "irrigation at flowering only if water exists."),
    ("gram", r"(?<!green )(?<!black )(?<!horse )(?<!red )\b(gram|chickpea|chana)\b", "rabi", "Gram (chana)",
     "Sow EARLY (October to first fortnight of November) on residual moisture; conserve moisture (mulch, avoid "
     "deep tillage, seed treatment); choose wilt-resistant short-duration varieties; one protective irrigation at "
     "pod-filling if available."),
    ("paddy", r"\b(paddy|rice|dhan)\b", "kharif", "Paddy",
     "Short-duration varieties (about 100-120 days) with SRI or alternate wetting and drying to cut water use; shift "
     "part of the area (upland or uneven plots) to millets (ragi, bajra, jowar) or pulses (tur, moong, urad); keep "
     "spare nursery seed for re-sowing."),
    ("cotton", r"\b(cotton|kapas)\b", "kharif", "Cotton",
     "Intercrop pulses (moong/urad/soybean) between cotton rows to spread risk; avoid late sowing (late sowing "
     "lowers yield and raises pest pressure); sow only on adequate soil moisture and stagger sowing; mulch and use "
     "ridge-furrow to hold moisture."),
    ("soybean", r"\b(soya ?bean|soybean|soya)\b", "kharif", "Soybean",
     "If monsoon onset is late or weak, shift to moong/urad (shorter, lighter on water) or tur intercrop; use "
     "short-duration varieties; broad-bed-furrow for moisture; sow only after a good soaking rain."),
    ("maize", r"\b(maize|corn|makka)\b", "kharif", "Maize",
     "In rainfed plots move part or all of the area to bajra or jowar (more drought-hardy); if keeping maize, use "
     "early short-duration hybrids, mulch, and save any irrigation for tasselling/silking."),
    ("groundnut", r"\b(groundnut|peanut)\b", "kharif", "Groundnut",
     "Where dry spells are likely shift part of the area to castor or horse gram (kulthi), or use short-duration "
     "bunch varieties with mulching; intercropping with tur or castor spreads risk."),
    ("wheat", r"\bwheat\b", "rabi", "Wheat",
     "Under a warm El Niño winter use heat-tolerant, early-sown varieties and sow on time, before 15 November; "
     "irrigate at crown-root initiation and grain filling; if water is short, prioritise those two stages or move "
     "part of the area to gram or mustard."),
    ("mustard", r"\b(mustard|rapeseed|sarson|toria|rai)\b", "rabi", "Mustard / rapeseed",
     "Sow EARLY (early to mid October) on stored soil moisture; conserve moisture (mulch, "
     "avoid deep tillage, line sowing with thinning); one protective irrigation at flowering/pod-filling only if "
     "water exists; choose early-maturing varieties to escape terminal heat and aphid build-up."),
    ("millets", r"\b(jowar|sorghum|bajra|pearl millet|ragi|finger millet|millet|millets)\b", "kharif",
     "Jowar / bajra / ragi",
     "Already drought-tolerant: keep and protect them. Intercrop with tur or moong, sow on proper moisture, gap-fill "
     "early, and keep the stover (dual-purpose fodder) for animals."),
    ("sugarcane", r"\b(sugarcane|sugar cane)\b", "annual", "Sugarcane",
     "Water-hungry: do not expand area; use trash mulching, alternate-furrow or drip irrigation, and avoid fresh "
     "planting where water is uncertain; short-duration pulses can be intercropped early."),
]


# season/phase-specific variants of the playbook: (crop key or "*", season kind, phase or None) -> advice.
# Lookup order: exact phase, then phase None, then "*" generic for that kind+phase, else the base advice above.
_OVERLAYS: dict[tuple[str, str, str | None], str] = {
    # ---- rabi
    ("wheat", "rabi", None):
        "Sow wheat on time, by 15 November (each week of delay after that costs yield); choose heat-tolerant, "
        "early/timely-sown varieties; give protective irrigation at crown-root initiation (about 21 days) and at "
        "grain filling; if water is short, prioritise those two stages or move part of the area to gram or mustard.",
    ("wheat", "rabi", "lanina"):
        "Sow wheat on time, by 15 November, once fields are workable after the monsoon (drain waterlogged plots "
        "first); choose timely-sown varieties; keep protective irrigation for crown-root initiation and grain "
        "filling only if the soil is dry then.",
    ("gram", "rabi", None):
        "Sow gram EARLY (October to first fortnight of November) on residual moisture; conserve moisture (mulch, no "
        "deep tillage, seed treatment); choose wilt-resistant short-duration varieties; one protective irrigation "
        "at pod-filling if water exists.",
    ("paddy", "rabi", None):
        "Rabi (boro/summer) rice in the east depends on groundwater: make a groundwater budget before nursery "
        "sowing, plant only the area the tubewell/canal can finish, use short-duration varieties with alternate "
        "wetting and drying (AWD) or SRI, and move part of the area to pulses, mustard or maize if the pre-monsoon "
        "water table is falling.",
    ("*", "rabi", "elnino"):
        "Warm, dry winter: sow on time, prefer early/short-duration and heat-tolerant varieties, conserve moisture "
        "and keep protective irrigation for the critical stages.",
    # ---- kharif, La Nina (excess rain / flood)
    ("paddy", "kharif", "lanina"):
        "Excess-rain year: prepare field drains and keep bunds high and sound; use flood/submergence-tolerant "
        "varieties (e.g. Swarna-Sub1) in flood-prone low-lying plots; stagger nurseries and keep spare seed; if "
        "floods hit, re-transplant from reserve nursery or delay sowing until water recedes; on residual moisture "
        "after the flood, short-duration pulses (moong/urad) or lathyrus fit.",
    ("*", "kharif", "lanina"):
        "Excess-rain year: make drainage first (field drains, ridge-and-furrow or broad-bed-and-furrow, raised "
        "beds); delay sowing or re-sow once floodwater recedes, keeping seed in reserve; choose short-duration "
        "varieties and, on residual moisture after the flood, short-duration pulses (moong/urad); watch for "
        "waterlogging, pest and disease build-up.",
}


def crop_playbook(crop: str, season_kind: str | None = None, phase: str | None = None) -> dict | None:
    """Playbook row for a crop; `season_kind` (kharif|rabi) and `phase` (lanina|neutral|elnino|...) pick the
    season-specific variant when one exists (backward compatible: both None = the base advice)."""
    name = (crop or "").lower().strip()
    if not name or name == "other":
        return None
    for key, rx, season, label, advice in _CROPS:
        if re.search(rx, name):
            if season_kind:
                ov = _OVERLAYS.get((key, season_kind, phase)) or _OVERLAYS.get((key, season_kind, None))
                if ov is None and season == season_kind:  # generic row only for crops of that season
                    ov = _OVERLAYS.get(("*", season_kind, phase))
                advice = ov or advice
            return {"key": key, "season": season, "label": label, "advice": advice}
    return None


def crop_substitution_table() -> str:
    lines = [f"- {label} ({season}): {advice}" for _, _, season, label, advice in _CROPS]
    lines += [f"- {('any crop' if k == '*' else k)} ({kind}{', ' + ph + ' phase' if ph else ''}): {a}"
              for (k, kind, ph), a in _OVERLAYS.items()]
    return "\n".join(lines)


# ------------------------------------------------------------------ profile rules (deterministic emphasis)
def profile_emphasis(p: dict) -> list[str]:
    h, w = p["holding"], p["water"]
    out: list[str] = []
    if h == "marginal" and w == "rainfed":
        out.append("ZERO/LOW-COST FIRST: residue mulching, field bunds and contour furrows, seed treatment, staggered "
                   "sowing, intercropping (cereal + pulse); nothing that needs borrowing. Link to safety nets: ration "
                   "card/PDS entitlement and a NREGA job card (ask the Gram Panchayat / Rozgar Sevak; individual "
                   "bund or farm-pond works on own land can be eligible for small and marginal farmers).")
    elif h in ("marginal", "small") and w == "rainfed":
        out.append("LOW-COST FIRST: mulching, bunds, seed treatment, intercropping (cereal + pulse), staggered sowing; "
                   "spend cash only on short-duration seed; keep NREGA job card and PDS linkage ready as a fallback.")
    elif h == "medium_large" and w == "irrigated":
        out.append("WATER BUDGETING: fix a seasonal water budget per plot, schedule PROTECTIVE irrigation only at "
                   "critical stages (not calendar-based), consider drip/sprinkler and a farm pond for storage, and "
                   "DIVERSIFY a share of the area to pulses/millets/oilseeds instead of the water-hungry main crop.")
    elif h == "medium_large":
        out.append("DIVERSIFY and build a buffer: put part of the area under drought-hardy pulses/millets/oilseeds, "
                   "dig or desilt a farm pond for supplementary irrigation, hold contingency seed, and insure "
                   "the whole cropped area.")
    elif w == "irrigated":
        out.append("SPEND WATER WHERE IT PAYS: protective irrigation at critical stages only, mulch to cut "
                   "evaporation, and put a part of the area under a lighter-water pulse/millet.")
    else:
        out.append("MIX: use the limited water for critical stages of the main crop; pair it with intercropped "
                   "pulses/millets, mulching and bunds on the unirrigated part.")
    if p["livestock"]:
        out.append("LIVESTOCK: secure fodder early (store crop residue/stover, grow fodder sorghum/bajra, prefer "
                   "dual-purpose jowar/bajra over single-purpose grain crops); avoid distress sale of animals; "
                   "vaccinate before the lean season; ask the Animal Husbandry office about fodder banks/cattle camps.")
    if p["tenant"]:
        out.append("TENANT/SHARECROPPER: PMFBY enrolment normally needs a land record or the landowner's consent, "
                   "so say so plainly and tell the farmer to ask the bank/CSC what the state accepts; mention the "
                   "alternatives: WBCIS (weather-based insurance, where notified) and group insurance or credit "
                   "through an FPO or a joint liability group; keep a written record of the lease/crop-share; "
                   "avoid costly long-term investments on leased land.")
    else:
        out.append("INSURANCE: owner-cultivator, so PMFBY enrolment through the bank, CSC or portal before the "
                   "notified cut-off applies directly (do not state a date).")
    return out


# ------------------------------------------------------------------ department catalogue
DEPT_LABEL = {
    "collector": "District Collector (whole-district coordination)",
    "food_civil_supplies": "Food, Civil Supplies & Consumer Affairs",
    "agriculture": "Agriculture",
    "wcd_icds": "Women & Child Development / ICDS",
    "rural_development": "Rural Development / NREGA",
    "health": "Health & Family Welfare",
    "animal_husbandry": "Animal Husbandry",
}
DEPT_SHORT = {
    "collector": "District Collector", "food_civil_supplies": "Food & Civil Supplies", "agriculture": "Agriculture",
    "wcd_icds": "WCD / ICDS", "rural_development": "Rural Development", "health": "Health",
    "animal_husbandry": "Animal Husbandry",
}

# action menu entries: (action, responsible unit, lead time)
DEPT_CATALOG: dict[str, dict[str, Any]] = {
    "collector": {
        "reader": "the District Collector and the District Disaster/Drought Management Group",
        "lens": "whole picture: coordination across departments, sequencing, a single timeline, escalation to the state",
        "focus": "Section 1: the overall risk score/band, the top drivers and the single biggest exposure. Section 2: "
                 "the three most exposed groups across departments (children, women, rainfed farmers, livestock "
                 "keepers) with one number each.",
        "evidence": "risk.<scenario> (score, band, drivers, actions), food_balance, crops.rainfed_share, nutrition, "
                    "markets, groundwater, nutrition.poshan_live, hindcast",
        "units": "Collector + DRDA PD; nodal officers per department",
        "menu": [
            ("Convene the District Drought/El Nino Management Group and fix a weekly review with one named nodal "
             "officer per department", "Collector + ADM + DRDA PD", "within 1 week"),
            ("Advance lifting and block-godown pre-positioning of grain (target grain_preposition_t)",
             "DSO + FPS inspectors", "start within 2 weeks; complete before the lean months"),
            ("Seed banks of short-duration varieties and a PMFBY enrolment drive before Rabi sowing",
             "District Agriculture Officer + KVK + ATMA", "by 15 Nov 2026 (Rabi) / by 15 May 2027 (Kharif)"),
            ("Front-load take-home rations and run SAM screening for the target children (anganwadi_children)",
             "CDPO + AWWs", "within 3 weeks"),
            ("NREGA work-demand surge on water-conservation and drought-proofing works",
             "BDO + NREGA PO", "shelf of works ready in 4 weeks"),
            ("Fodder banks and cattle-camp readiness where fodder_flag is true", "Dy Director AH + veterinary officers",
             "4-6 weeks"),
            ("IFA/deworming camps, ORS-zinc stock check and heat/water advisories", "CMO + ASHAs", "within 4 weeks"),
            ("Price and market monitoring with OMSS trigger rules", "DSO + Tahsildars", "weekly from now"),
        ],
        "public": "One line from the Collector: what will be done, where to go (ration shop, anganwadi, GP office, "
                  "KVK) and that this is an early precaution, not an emergency declaration.",
        "extra": "Section 3 must pick five actions from at least four DIFFERENT departments, prioritised. After "
                 "Section 3 add `## 4. Cross-department timeline` as a Markdown table with the columns "
                 "`Action | Department | By when` (8-10 rows covering every department; dates anchored on the lead "
                 "times in the evidence if present, else relative).",
    },
    "food_civil_supplies": {
        "reader": "the District Supply Officer (DSO), FCI/State Civil Supplies depot managers and FPS inspectors",
        "lens": "PDS allocation and offtake, PDS dependency, grain pre-positioning, OMSS, godown storage, prices",
        "focus": "Section 1: self-sufficiency, pds_dependency and the grain gap (grain_preposition_t), plus price-spike "
                 "risk if a markets block exists. Section 2: PDS-dependent households and the lean-month access gap "
                 "(availability is not access).",
        "evidence": "food_balance (self_sufficiency, pds_dependency, deficit), risk.<scenario>.actions."
                    "grain_preposition_t and pulses_preposition_t, markets (price_elnino_spike_pct, "
                    "price_volatility_idx)",
        "units": "DSO + FPS inspectors; FCI District Manager; Civil Supplies Corporation godown managers",
        "menu": [
            ("Advance lifting of NFSA rice/wheat for the lean months, sized to grain_preposition_t",
             "DSO + FCI District Manager", "start within 2 weeks; complete 2-3 months before the lean season"),
            ("Physical stock verification and e-PoS uptime audit at fair price shops", "DSO + FPS inspectors",
             "within 3 weeks, then monthly"),
            ("Inter-district / depot-to-block movement so that block godowns hold the buffer",
             "DSO + Civil Supplies Corporation godown managers", "4-6 weeks"),
            ("Weekly price monitoring in mandis and retail, with OMSS (domestic) release triggers agreed in advance "
             "(cite price_elnino_spike_pct if present)", "DSO + Tahsildars + district price-monitoring cell",
             "weekly from now"),
            ("Pulses/millet add-on or substitution in PDS where state policy allows (use pulses_preposition_t)",
             "DSO + state Civil Supplies Corporation", "plan by 15 Nov 2026, deliver by 15 May 2027"),
            ("Grievance helpline and ration-portability publicity for migrant households",
             "DSO + FPS inspectors + Rozgar Sevaks", "within 4 weeks"),
        ],
        "public": "Ration will be lifted early and stocked locally; collect your entitlement at your fair price shop "
                  "and report shortages to the DSO helpline.",
        "extra": "Never state stock, offtake or price figures that are not in the evidence.",
    },
    "agriculture": {
        "reader": "the District Agriculture Officer, KVK Programme Coordinator and ATMA Project Director",
        "lens": "crop mix, rainfed share, yield sensitivity (beta), seed availability, PMFBY gap, contingency crop plan, "
                "groundwater for irrigation",
        "focus": "Section 1: the expected yield shock, yield sensitivity of the main crops, rainfed share and, if a "
                 "groundwater block exists, whether irrigation can buffer. Section 2: rainfed small/marginal farmers "
                 "and the named top crops most exposed.",
        "evidence": "crops (top, rainfed_share, small_marginal_share, irrigated_share), yield_sensitivity, "
                    "risk.<scenario>.actions (seed_bank_ha, pmfby_gap_farmers), groundwater (gw_stress_idx, "
                    "gw_decline_10y_m_per_yr), crops.economics",
        "units": "KVK + ATMA; District Agriculture Officer; block agriculture officers; lead bank manager",
        "menu": [
            ("Seed banks / minikits of short-duration and drought-tolerant varieties sized to seed_bank_ha",
             "District Agriculture Officer + State Seeds Corporation", "by 15 Nov 2026 (Rabi) / by 15 May 2027 (Kharif)"),
            ("Activate the ICAR-CRIDA district contingency crop plan and issue sowing advisories",
             "KVK + ATMA", "within 2 weeks, then fortnightly"),
            ("PMFBY enrolment drive to close pmfby_gap_farmers (bank, CSC, portal), including tenant guidance",
             "DAO + lead bank manager + CSC VLEs", "before the notified cut-off, start within 2 weeks"),
            ("Front-line demonstrations: short-duration paddy/SRI, millet and pulse intercropping, moisture "
             "conservation", "KVK + ATMA", "demos in place by sowing"),
            ("Protective-irrigation schedule and micro-irrigation push where groundwater is stressed",
             "DAO + Horticulture/PMKSY officer", "4-6 weeks"),
            ("Input-supply watch: certified seed, fertiliser and agro-chemical availability at dealers",
             "DAO + block agriculture officers", "weekly from now"),
        ],
        "public": "Choose short-duration seed, do not sow on the first shower, enrol in PMFBY before the cut-off and "
                  "ask your KVK/agriculture office for the contingency plan.",
        "extra": "If crops.economics exists, cite one margin comparison for the main crop and a substitute.",
    },
    "wcd_icds": {
        "reader": "the District Programme Officer (ICDS), CDPOs and Anganwadi Workers (AWWs)",
        "lens": "stunting/wasting/underweight, Poshan Tracker live malnutrition, take-home ration (THR), growth "
                "monitoring, SAM/MAM, hot-cooked meals, VHSND",
        "focus": "Section 1: stunting/wasting/underweight against the El Nino income-and-food shock; use "
                 "nutrition.poshan_live underweight (with its as-of month) if present. Section 2: children under 5 "
                 "(anganwadi_children target), pregnant/lactating women, anaemic women.",
        "evidence": "nutrition (nfhs5/nfhs6, poshan_live), children_u5_est, risk.<scenario>.actions "
                    "(anganwadi_children, women_anaemia_target)",
        "units": "CDPO + AWWs; Lady Supervisors; DPO-ICDS",
        "menu": [
            ("Front-load take-home rations (THR) to cover the lean months for the target children "
             "(anganwadi_children)", "CDPO + AWWs", "within 3 weeks"),
            ("Growth-monitoring drive and SAM/MAM screening of all under-5s, starting with the poorest blocks",
             "AWWs + Lady Supervisors + ANMs", "within 3 weeks, then monthly"),
            ("Guarantee hot-cooked meal continuity and add millets/eggs/pulses where the state menu allows",
             "CDPO + Anganwadi Supervisors", "start within 2 weeks"),
            ("VHSND sessions focused on SAM referral, anaemia and counselling of pregnant/lactating women",
             "CDPO + ANMs + ASHAs", "monthly from now"),
            ("Refer SAM children with complications to the NRC and track recovery", "CDPO + CMO + NRC in-charge",
             "ongoing, review in 4 weeks"),
            ("Reconcile Poshan Tracker data weekly to catch worsening underweight early", "DPO-ICDS + CDPOs",
             "weekly from now"),
        ],
        "public": "Collect your child's take-home ration on time, get your child weighed at the anganwadi every month, "
                  "and report any child who looks very thin or swollen.",
        "extra": "Prefer nutrition.poshan_live over NFHS for 'current' wording and always give the as-of month.",
    },
    "rural_development": {
        "reader": "the Block Development Officers (BDOs), NREGA Programme Officers and the DRDA Project Director",
        "lens": "NREGA person-days and work demand, water conservation and drought-proofing works, wage timeliness, "
                "migration risk, SHG/NRLM livelihoods, groundwater",
        "focus": "Section 1: the income shock to agricultural labour and marginal farmers (rainfed share, yield shock) "
                 "and the NREGA person-day target; groundwater stress if the block exists. Section 2: agricultural "
                 "workers, landless and migration-prone households.",
        "evidence": "risk.<scenario>.actions (mgnrega_persondays), crops (rainfed_share, small_marginal_share), "
                    "groundwater (gw_decline_10y_m_per_yr, gw_stress_idx), population_2026",
        "units": "BDO + NREGA PO; DRDA PD; Gram Panchayats and Rozgar Sevaks",
        "menu": [
            ("Surge work demand: pre-approve a shelf of works and open demand registration camps "
             "(target mgnrega_persondays)", "BDO + NREGA PO + Gram Rozgar Sevaks", "shelf ready in 4 weeks"),
            ("Prioritise farm ponds, field bunds, check dams and percolation tanks for drought-proofing",
             "BDO + NREGA PO + block agriculture and watershed officers", "start before Rabi, finish before pre-monsoon"),
            ("Ensure wages are paid within the 15-day norm (FTO, bank/post-office agent readiness)",
             "NREGA PO + banking correspondents", "from now, audit fortnightly"),
            ("Target migration-prone Gram Panchayats with job-card updating and 100-day guarantee awareness",
             "BDO + Sarpanch + Rozgar Sevaks", "within 3 weeks"),
            ("Secure drinking-water sources (handpump/borewell repair, tanker plan) in groundwater-stressed GPs",
             "BDO + rural water supply engineers", "within 4 weeks"),
            ("Lean-season credit and livelihood support through SHGs/NRLM", "DRDA PD + DMMU + SHG federations",
             "by 15 Nov 2026"),
        ],
        "public": "Register for work at your Gram Panchayat now; wages are due within 15 days; farm ponds and bunds "
                  "on your land may be possible under NREGA.",
        "extra": "Do not promise person-days beyond the evidence target.",
    },
    "health": {
        "reader": "the Chief Medical Officer (CMO), Medical Officers of PHCs, ANMs and ASHAs",
        "lens": "child and women anaemia, low BMI, SAM referral, diarrhoea and heat-season illness, drug/ORS stock",
        "focus": "Section 1: anaemia and low-BMI burden plus the heat/water-stress season, with Poshan Tracker live "
                 "underweight if present. Section 2: anaemic women (women_anaemia_target), children with anaemia or "
                 "wasting, pregnant women, the elderly in heat.",
        "evidence": "nutrition (child_anaemia, women_anaemia, women_bmi_low, wasting, poshan_live), "
                    "risk.<scenario>.actions (women_anaemia_target), climate (tmax_anomaly_c)",
        "units": "CMO + ASHAs; MO-PHC; ANMs; District Drug Warehouse",
        "menu": [
            ("IFA supplementation and deworming camps for children and women (Anaemia Mukt Bharat), sized to "
             "women_anaemia_target", "CMO + MO-PHC + ASHAs", "camps within 4 weeks"),
            ("Identify and refer SAM/wasted children and anaemic pregnant women through ASHA home visits",
             "ASHAs + ANMs + RBSK teams", "within 3 weeks"),
            ("Heat and safe-water advisories; pre-position ORS and zinc at PHCs/sub-centres",
             "CMO + ASHAs + District Drug Warehouse", "before the next hot season; stock check within 2 weeks"),
            ("Heat-illness and diarrhoea surveillance with weekly reporting", "District Surveillance Officer + MO-PHC",
             "weekly from now"),
            ("High-risk pregnancy tracking and ANC reinforcement in the worst blocks", "ANMs + ASHAs + MO-PHC",
             "within 4 weeks"),
            ("Joint SAM referral protocol with ICDS to the NRC", "CMO + CDPO + NRC in-charge", "within 3 weeks"),
        ],
        "public": "Take your iron-folic-acid tablets, keep ORS and clean water at home, and go to your ASHA or sub-centre "
                  "early if a child has diarrhoea, fever or stops eating.",
        "extra": "Do not cite disease-incidence numbers unless they are in the evidence.",
    },
    "animal_husbandry": {
        "reader": "the Deputy Director of Animal Husbandry (Dy Director AH) and veterinary officers",
        "lens": "fodder availability, millet/cash-crop share, fodder_flag, livestock density if known, cattle camps, "
                "vaccination, livestock water",
        "focus": "Section 1: fodder risk (fodder_flag, millet vs cash-crop share, expected yield shock to stover/"
                 "residue). Section 2: livestock-keeping smallholders, landless herders and, if livestock density is "
                 "in the data, the most exposed blocks (otherwise say it is not available).",
        "evidence": "risk.<scenario>.actions (fodder_flag), crops (groups, top, rainfed_share), "
                    "yield_sensitivity, groundwater",
        "units": "Dy Director AH + veterinary officers; livestock inspectors; Gram Panchayats",
        "menu": [
            ("Fodder banks and fodder-seed minikits (jowar/bajra/maize fodder) at block level",
             "Dy Director AH + KVK", "within 3 weeks"),
            ("Identify cattle-camp sites and trigger rules; keep fodder/water/vet cover ready",
             "Dy Director AH + Tahsildars + NGOs", "sites identified in 4 weeks"),
            ("Procure and store straw/stover/silage and regulate fodder movement out of the district",
             "Dy Director AH + Revenue officials", "start within 4 weeks, before the lean season"),
            ("Vaccination (FMD, HS/BQ) and deworming drive ahead of the lean season", "veterinary officers + "
             "livestock inspectors", "within 6 weeks"),
            ("Livestock drinking-water points and troughs in drought-prone villages", "Dy Director AH + Gram Panchayats "
             "+ PHED", "within 4 weeks"),
            ("Awareness against distress sale of animals and linkage to fodder/credit support",
             "Dy Director AH + veterinary officers + SHGs", "ongoing, review monthly"),
        ],
        "public": "Store crop residue and fodder now, vaccinate your animals, avoid selling animals in distress, and "
                  "contact the veterinary officer about fodder banks.",
        "extra": "If fodder_flag is false or absent say fodder risk is not flagged by the model and focus on "
                 "vaccination and water.",
    },
}


# Rabi variants of the department action menus (same shape as DEPT_CATALOG[x]["menu"]); used when the season is rabi.
RABI_MENUS: dict[str, list[tuple[str, str, str]]] = {
    "food_civil_supplies": [
        ("Plan wheat procurement for the coming rabi marketing season: mandi/purchase-centre readiness, gunny and "
         "storage capacity, and farmer registration", "DSO + State Civil Supplies Corporation + FCI District "
         "Manager", "plan before harvest; centres open by the notified date"),
        ("Advance lifting of NFSA wheat/rice for the lean months, sized to grain_preposition_t",
         "DSO + FCI District Manager", "start within 2 weeks; complete before the lean season"),
        ("Physical stock verification and e-PoS uptime audit at fair price shops", "DSO + FPS inspectors",
         "within 3 weeks, then monthly"),
        ("Depot-to-block movement so block godowns hold the wheat/rice buffer through winter",
         "DSO + Civil Supplies Corporation godown managers", "4-6 weeks"),
        ("Weekly wheat/flour price monitoring with OMSS (domestic) wheat release triggers agreed in advance (cite "
         "price_elnino_spike_pct if present)", "DSO + Tahsildars + district price-monitoring cell",
         "weekly from now"),
        ("Pulses/millet add-on or substitution in PDS where state policy allows (use pulses_preposition_t)",
         "DSO + state Civil Supplies Corporation", "plan within 4 weeks"),
    ],
    "agriculture": [
        ("Timely-sowing campaign: wheat sown before 15 November, gram and mustard early, with block-level sowing "
         "progress tracking", "District Agriculture Officer + KVK + ATMA", "campaign live now; sowing by 15 Nov"),
        ("Seed of heat-tolerant, early/timely wheat varieties (plus gram and mustard minikits) sized to seed_bank_ha",
         "District Agriculture Officer + State Seeds Corporation", "stock at block outlets within 2 weeks"),
        ("Protective-irrigation advisory: irrigation at crown-root initiation and grain filling, rationed where "
         "groundwater is stressed", "KVK + ATMA + PMKSY/micro-irrigation officer", "advisory now; reminders at "
         "21 days after sowing and at grain filling"),
        ("Moisture-conservation demonstrations (mulch, zero/minimum tillage, seed treatment) on gram and mustard",
         "KVK + ATMA", "demos in place by sowing"),
        ("PMFBY rabi enrolment drive to close pmfby_gap_farmers (bank, CSC, portal), including tenant guidance",
         "DAO + lead bank manager + CSC VLEs", "before the notified rabi cut-off, start within 2 weeks"),
        ("Input-supply watch: certified seed, DAP/urea and agro-chemical availability at dealers",
         "DAO + block agriculture officers", "weekly from now"),
    ],
    "rural_development": [
        ("Irrigation works under NREGA/PMKSY-WDC: field channels, farm ponds, check dams, desilting of minor "
         "irrigation tanks so rabi crops get protective irrigation", "BDO + NREGA PO + minor-irrigation and "
         "watershed officers", "shelf approved in 3 weeks; works complete before grain filling (Feb-Mar)"),
        ("Surge work demand: pre-approve a shelf of works and open demand-registration camps "
         "(target mgnrega_persondays)", "BDO + NREGA PO + Gram Rozgar Sevaks", "shelf ready in 4 weeks"),
        ("Ensure wages are paid within the 15-day norm (FTO, bank/post-office agent readiness)",
         "NREGA PO + banking correspondents", "from now, audit fortnightly"),
        ("Target migration-prone Gram Panchayats (post-kharif outmigration) with job-card updating and 100-day "
         "guarantee awareness", "BDO + Sarpanch + Rozgar Sevaks", "within 3 weeks"),
        ("Secure drinking-water sources and irrigation pumps (handpump/borewell repair, pump-set power supply) in "
         "groundwater-stressed GPs", "BDO + rural water supply engineers", "within 4 weeks"),
        ("Rabi-season credit and livelihood support through SHGs/NRLM", "DRDA PD + DMMU + SHG federations",
         "within 4 weeks"),
    ],
    "animal_husbandry": [
        ("Fodder from rabi straw: procure and store wheat bhusa/straw and gram/mustard residue at block bhusa "
         "banks, and regulate fodder movement out of the district", "Dy Director AH + Revenue officials + "
         "Gram Panchayats", "start at harvest (Mar-Apr), stocks verified by May"),
        ("Green-fodder minikits for the winter (berseem, oats, fodder maize) at block level",
         "Dy Director AH + KVK", "within 3 weeks"),
        ("Identify cattle-camp sites and trigger rules for the summer lean period; keep fodder/water/vet cover ready",
         "Dy Director AH + Tahsildars + NGOs", "sites identified in 6 weeks"),
        ("Vaccination (FMD, HS/BQ) and deworming drive before the hot season", "veterinary officers + "
         "livestock inspectors", "within 6 weeks"),
        ("Livestock drinking-water points and troughs in drought-prone villages", "Dy Director AH + Gram Panchayats "
         "+ PHED", "before March"),
        ("Awareness against distress sale of animals and linkage to fodder/credit support",
         "Dy Director AH + veterinary officers + SHGs", "ongoing, review monthly"),
    ],
}


def dept_menu(department: str, season_kind: str | None = None) -> list[tuple[str, str, str]]:
    """Action menu for a department; the rabi variant when the season is rabi and one is defined."""
    if season_kind == "rabi" and department in RABI_MENUS:
        return RABI_MENUS[department]
    return DEPT_CATALOG[department]["menu"]


def optional_blocks_present(ctx: dict) -> dict[str, bool]:
    return {"markets": bool(ctx.get("markets")), "groundwater": bool(ctx.get("groundwater")),
            "nutrition.poshan_live": bool((ctx.get("nutrition") or {}).get("poshan_live")),
            "crops.economics": bool((ctx.get("crops") or {}).get("economics"))}


def department_block(department: str, ctx: dict, scenario: str, season_kind: str | None = None,
                     phase: str | None = None) -> str:
    c = DEPT_CATALOG[department]
    menu = "\n".join(f" {i}. {a} | unit: {u} | lead: {t}"
                     for i, (a, u, t) in enumerate(dept_menu(department, season_kind), 1))
    phase_note = ""
    if phase == "lanina":
        phase_note = ("\nPHASE ADAPTATION (La Nina): the hazard is excess rain/flood, not drought. Keep the unit and "
                      "lead-time format, but word each menu action for flood/waterlogging preparedness (drainage "
                      "and embankment checks, flood-tolerant seed, post-flood re-sowing, stock above flood level, "
                      "waterborne-disease readiness); do not describe drought effects.")
    elif phase == "neutral":
        phase_note = ("\nPHASE ADAPTATION (Neutral): no ENSO anomaly is assumed; frame actions as strengthening "
                      "structural resilience (what makes this district fragile in an ordinary year), not event "
                      "response.")
    present = optional_blocks_present(ctx)
    pres = ", ".join(f"{k}={'PRESENT' if v else 'absent'}" for k, v in present.items())
    ev = c["evidence"].replace("<scenario>", scenario)
    return (f"DEPARTMENT FOCUS: {department} ({DEPT_LABEL[department]})\n"
            f"READER: {c['reader']}\nLENS: {c['lens']}\nSECTION FOCUS: {c['focus']}\n"
            f"EVIDENCE TO LEAN ON (cite where present; 'data not available' where null/absent): {ev}\n"
            f"OPTIONAL EVIDENCE BLOCKS: {pres} (use a block only if PRESENT; never imply data that is absent)\n"
            f"RESPONSIBLE UNITS: {c['units']}\n"
            f"ACTION MENU (the five actions MUST come from this menu, adapted to this district's numbers; list the "
            f"unit and the lead time for each; do not add actions from other departments' menus"
            f"{' except as coordination asks' if department != 'collector' else ''}):\n{menu}\n"
            f"PUBLIC MESSAGE GUIDE: {c['public']}\nDEPARTMENT RULES: {c['extra']}{phase_note}")


def profile_block(p: dict, d: dict, ctx: dict, season_kind: str | None = None, phase: str | None = None) -> str:
    tops = district_top_crops(d, season_kind)
    crop = p["crop"]
    if crop == "other":
        crop_line = "other (not one of the district's main crops) - give general advice only"
    elif crop in tops:
        share = next((c.get("share") for c in season_top(d, season_kind)[0] if c.get("crop") == crop), None)
        crop_line = f"{crop} (district top-crop #{tops.index(crop) + 1}" + \
                    (f", about {round(share * 100)}% of cropped area)" if isinstance(share, (int, float)) else ")")
    else:
        crop_line = f"{crop} (named by the farmer; not among the district's top crops for this season)"
    pb = crop_playbook(crop, season_kind, phase)
    srows, src = season_top(d, season_kind)
    names = [str(c["crop"]) for c in srows[:5]]
    if season_kind in ("kharif", "rabi"):
        other = "rabi" if season_kind == "kharif" else "kharif"
        crop_rule = (f"SEASON CROPS ({season_kind.upper()} only; from the district's "
                     f"{'season-specific list' if src == 'season' else 'all-year list, season split not available'}): "
                     f"{', '.join(names) or 'data not available'}. Every crop you recommend or mention as a choice MUST "
                     f"come from this list or the playbook for a {season_kind} crop. NEVER suggest a {other} crop for "
                     f"{season_kind} (kharif = rain-fed monsoon crops such as cotton, soybean, paddy, tur, jowar, "
                     f"bajra, maize, groundnut; rabi = wheat, gram, mustard, winter jowar, rabi rice).")
    else:
        crop_rule = f"SEASON CROPS (season kind unknown; district list): {', '.join(names) or 'data not available'}."
    lines = [
        "FARMER PROFILE (facts about the reader; speak to them as 'you', never list the fields mechanically):",
        f"- Farmer type: {farmer_type_label(p)}",
        f"- Holding: {HOLDING_TEXT[p['holding']]}",
        f"- Water: {WATER_TEXT[p['water']]}",
        f"- Main crop: {crop_line}",
        f"- Livestock: {'yes, keeps animals' if p['livestock'] else 'no'}",
        f"- Tenure: {'tenant / sharecropper (no own land record)' if p['tenant'] else 'owner-cultivator'}",
        "PROFILE-DERIVED EMPHASIS (these decide which bullets you write):",
        *[f"  * {e}" for e in profile_emphasis(p)],
    ]
    lines.insert(1, crop_rule)
    if pb and season_kind in ("kharif", "rabi") and pb["season"] not in (season_kind, "annual"):
        lines += [f"NOTE: the farmer's named crop ({pb['label']}) is a {pb['season']} crop and the season is "
                  f"{season_kind}; give no sowing advice for it now, say so in one short clause and advise from the "
                  f"SEASON CROPS instead."]
    elif pb:
        lines += [f"CROP PLAYBOOK for the main crop ({pb['label']}, {pb['season']} crop; general agronomy, not a "
                  f"district fact; phrase as 'consider'): {pb['advice']}"]
    else:
        lines += ["CROP PLAYBOOK: no specific row for this crop; give a general drought-tolerant substitution using "
                  "the crops actually listed for the district."]
    econ = (ctx.get("crops") or {}).get("economics")
    if econ:
        lines += ["CROP ECONOMICS: present. Use AT MOST ONE simple sentence comparing which crop earned more per "
                  "acre last year (e.g. \"Last year soybean earned more per acre than cotton here\"). No rupee "
                  "figures, no costs, no percentages, never a table; skip the sentence if the evidence does not "
                  "clearly support it."]
    else:
        lines += ["CROP ECONOMICS: not available - do not mention costs, prices or margins."]
    return "\n".join(lines)
