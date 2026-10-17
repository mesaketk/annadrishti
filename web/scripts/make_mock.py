"""Generate plausible MOCK data following docs/SCHEMA.md for every lgd in public/districts.geojson.
Output: public/mock/districts.json, kpis.json, timeseries/{lgd}.json  (random but spatially coherent).
Run: python3 web/scripts/make_mock.py
"""
import json, math, random
from pathlib import Path
import numpy as np
from shapely.geometry import shape

WEB = Path(__file__).resolve().parents[1]
OUT = WEB / "public" / "mock"
(OUT / "timeseries").mkdir(parents=True, exist_ok=True)
gj = json.load(open(WEB / "public" / "districts.geojson"))

# (lon, lat, radius_deg, strength) -- drought-/El Nino-prone belts get higher hazard + vulnerability
HOT = [(76.4, 19.1, 1.7, 1.0),   # Marathwada
       (79.1, 20.9, 1.6, 0.95),  # Vidarbha
       (79.5, 25.0, 1.6, 0.95),  # Bundelkhand
       (78.3, 14.5, 1.5, 0.95),  # Rayalaseema
       (83.1, 20.0, 1.3, 0.95),  # Kalahandi / KBK
       (76.6, 16.0, 1.3, 0.7),   # N Karnataka
       (72.0, 26.5, 2.2, 0.6),   # W Rajasthan
       (85.5, 23.5, 1.4, 0.6)]   # Jharkhand plateau
EL_YEARS = [2002, 2004, 2006, 2009, 2014, 2015, 2018, 2023]
LA_YEARS = [2000, 2007, 2008, 2010, 2011, 2020, 2021, 2022, 2024, 2025]
YEAR_SHOCK = {2002: -20, 2004: -11, 2006: -6, 2009: -23, 2014: -13, 2015: -15, 2018: -9, 2023: -7, 2012: -5, 2017: -2}
YEARS = list(range(2000, 2026))
YIELD_YEARS = list(range(2000, 2024))
rng_np = np.random.default_rng(7)


def hot(lon, lat):
    h = 0.0
    for x, y, r, s in HOT:
        d = math.hypot(lon - x, (lat - y) * 1.1)
        h = max(h, s * math.exp(-(d / r) ** 2))
    return h


def regime(lon, lat):
    if 28 <= lat <= 32.5 and 73.5 <= lon <= 80: return "nw_irrigated"
    if 24 <= lat < 28 and 80 <= lon <= 88.5: return "igp"
    if lon > 91 or (lat > 26 and lon > 88): return "ne"
    if lat < 13: return "south"
    if lat > 30: return "hill"
    if lon < 73.5 and 20 < lat < 25: return "gujarat"
    if lat < 19.5 and lon > 76: return "deccan_south"
    if 19.5 <= lat <= 24 and lon > 75: return "central"
    return "peninsular"


CROPS = {
    "nw_irrigated": [("Wheat", 3.0, .34), ("Rice", 3.8, .30), ("Cotton", 0.5, .1), ("Sugarcane", 70, .06), ("Maize", 2.8, .05)],
    "igp": [("Rice", 2.5, .38), ("Wheat", 2.9, .35), ("Sugarcane", 60, .07), ("Maize", 2.4, .06), ("Mustard", 1.1, .05)],
    "ne": [("Rice", 2.2, .6), ("Maize", 1.8, .08), ("Jute", 2.0, .06), ("Pulses", 0.7, .05), ("Potato", 14, .04)],
    "south": [("Rice", 3.4, .35), ("Coconut", 8, .2), ("Groundnut", 1.4, .1), ("Ragi", 1.8, .07), ("Maize", 3.2, .05)],
    "hill": [("Wheat", 1.6, .3), ("Maize", 1.9, .28), ("Rice", 1.8, .2), ("Pulses", 0.6, .06), ("Millets", 1.1, .05)],
    "gujarat": [("Cotton", 0.55, .26), ("Groundnut", 1.7, .2), ("Bajra", 1.5, .12), ("Wheat", 3.0, .14), ("Castor", 1.9, .06)],
    "deccan_south": [("Jowar", 0.9, .18), ("Cotton", 0.45, .2), ("Tur", 0.7, .13), ("Bajra", 0.9, .1), ("Groundnut", 1.0, .1)],
    "central": [("Soybean", 0.95, .3), ("Wheat", 2.6, .2), ("Gram", 1.0, .12), ("Rice", 1.6, .1), ("Cotton", 0.4, .08)],
    "peninsular": [("Jowar", 0.9, .22), ("Cotton", 0.45, .16), ("Soybean", 0.95, .15), ("Tur", 0.7, .12), ("Bajra", 0.9, .1)],
}
GROUP_OF = {"Wheat": "cereals", "Rice": "cereals", "Maize": "cereals", "Jowar": "millets", "Bajra": "millets", "Ragi": "millets",
            "Millets": "millets", "Tur": "pulses", "Gram": "pulses", "Pulses": "pulses", "Soybean": "oilseeds", "Groundnut": "oilseeds",
            "Mustard": "oilseeds", "Castor": "oilseeds", "Cotton": "cash", "Sugarcane": "cash", "Jute": "cash", "Coconut": "cash", "Potato": "cash"}

# ---------------------------------------------------------------- per-district static attributes
D = []
for f in gj["features"]:
    p = f["properties"]
    pt = shape(f["geometry"]).representative_point()
    lon, lat = round(pt.x, 3), round(pt.y, 3)
    r = random.Random(p["lgd"])
    reg = regime(lon, lat)
    h = hot(lon, lat)
    noise = 0.12 * math.sin(lon * 1.7 + 0.5) * math.cos(lat * 1.3) + r.uniform(-0.07, 0.07)
    hz = min(1, max(0, h + noise))
    irr_base = {"nw_irrigated": .88, "igp": .72, "ne": .25, "south": .55, "hill": .35, "gujarat": .45, "deccan_south": .22, "central": .4, "peninsular": .25}[reg]
    irr = min(.97, max(.04, irr_base - 0.35 * h + r.uniform(-.08, .08)))
    D.append(dict(p=p, lon=lon, lat=lat, r=r, reg=reg, hz=hz, irr=irr))

# ---------------------------------------------------------------- build records
recs, raws = [], {"neutral": [], "elnino": [], "elnino_strong": []}
for d in D:
    p, r, hz, irr, reg = d["p"], d["r"], d["hz"], d["irr"], d["reg"]
    pop11 = int(math.exp(r.gauss(14.0, 0.55)))
    pop11 = max(60000, min(pop11, 5_200_000))
    if p["state"] in ("Lakshadweep", "Chandigarh"): pop11 = 64000 if p["state"] == "Lakshadweep" else 1055000
    pop26 = int(pop11 * r.uniform(1.12, 1.22))
    u5 = int(pop26 * r.uniform(.085, .105))

    # --- climate
    eln_mean = -(6 + 20 * hz + r.uniform(-3, 3)) * (0.5 if reg in ("ne", "hill") else 1)
    eln_mean = max(-36, min(2, eln_mean))
    neu_mean = r.uniform(-1, 4) - 3 * hz * 0.3
    la_mean = r.uniform(3, 12)
    normal = {"ne": 1900, "south": 900, "hill": 1000, "igp": 1000, "nw_irrigated": 560}.get(reg, 820) * r.uniform(.8, 1.25)
    if hz > .7: normal *= 0.85
    normal = int(normal)
    scale = 0.55 + 0.9 * hz * 0.8 + (0 if reg != "ne" else -0.3)
    anom = {}
    for y in YEARS:
        base = YEAR_SHOCK.get(y)
        if base is None:
            base = r.uniform(2, 8) if y in LA_YEARS else r.uniform(-3, 5)
        v = base * (scale if base < 0 else 0.8 + r.uniform(0, .5)) + r.gauss(0, 4.5)
        anom[str(y)] = round(max(-60, min(60, v)))
    tmax = {str(y): round((0.7 if y in (2015, 2009, 2002, 2023) else 0.0) + r.gauss(0.1, 0.35), 1) for y in YEARS}
    live = None
    live = {"ndvi_anom": round(-0.02 - 0.16 * hz + r.gauss(0, .035), 3),
            "chirps_30d_anom_pct": round(-8 - 30 * hz + r.gauss(0, 12)),
            "wn_10d_rain_mm": round(max(0, (55 if reg in ("ne", "south") else 18) * (1.2 - hz) + r.gauss(0, 12)), 1),
            "as_of": "2026-10-17"}
    climate = {"jjas_normal_mm": normal, "jjas_anomaly_pct": anom, "elnino_mean_anomaly_pct": round(eln_mean),
               "neutral_mean_anomaly_pct": round(neu_mean), "lanina_mean_anomaly_pct": round(la_mean),
               "tmax_anomaly_c": tmax, "clim_vuln_index": round(min(1, max(0, .25 + .6 * hz + r.uniform(-.1, .1))), 2),
               "live": live}

    # --- crops
    base_t = CROPS[reg]
    area = int(pop11 * r.uniform(.12, .35) * (1.0 if reg != "hill" else 0.5))
    jit = [r.uniform(.8, 1.2) for _ in base_t]
    tot = sum(s * j for (_, _, s), j in zip(base_t, jit))
    top, groups = [], {k: {"area_ha": 0, "prod_t": 0} for k in ("cereals", "pulses", "oilseeds", "millets", "cash")}
    irr_boost = 0.6 + 0.9 * irr
    for (c, y0, s), j in zip(base_t, jit):
        share = round(min(.85, s * j / tot * 0.92), 3)
        yld = round(y0 * irr_boost * r.uniform(.85, 1.15), 2) if c not in ("Sugarcane", "Potato", "Coconut") else round(y0 * r.uniform(.8, 1.1), 1)
        top.append({"crop": c, "share": share, "yield_t_ha": yld})
        g = groups[GROUP_OF[c]]
        g["area_ha"] += int(area * share); g["prod_t"] += int(area * share * yld)
    top.sort(key=lambda t: -t["share"])
    fg = sum(groups[k]["prod_t"] for k in ("cereals", "pulses", "oilseeds", "millets"))
    fg = int(fg * 0.75)  # not all oilseed tonnage is foodgrain
    shares = [t["share"] for t in top]
    simpson = round(1 - sum(s * s for s in shares) - 0.05, 2)
    ycv = round(0.12 + 0.25 * hz + r.uniform(-.03, .05) - 0.1 * irr, 2)
    crops = {"year": "2022-23", "gross_cropped_area_ha": area, "top": top, "groups": groups, "foodgrain_prod_t": fg,
             "simpson_div": max(.1, simpson), "top_crop_share": top[0]["share"], "kharif_rabi_ratio": round(r.uniform(.6, 2.6), 1),
             "yield_cv10": max(.06, ycv), "irrigated_share": round(irr, 2), "rainfed_share": round(1 - irr, 2),
             "small_marginal_share": round(min(.95, max(.2, .45 + .2 * hz + r.uniform(-.15, .2))), 2)}

    # --- food balance
    req = int(pop26 * 180 / 1000)
    edible = int(fg * 0.875)
    ss = edible / req
    pds = round(min(.9, max(.04, .25 + .3 * hz - .15 * irr + r.uniform(-.08, .12))), 2)
    fb = {"requirement_t": req, "edible_prod_t": edible, "self_sufficiency": round(ss, 2), "pds_dependency": pds}

    # --- nutrition
    poor = 0.5 * hz + 0.25 * (reg in ("igp", "central")) + r.uniform(0, .25)
    if reg in ("south", "ne", "hill"): poor -= 0.12
    st5 = round(max(8, min(55, 18 + 30 * poor + r.gauss(0, 2.5))), 1)
    n5 = {"year": "2019-21", "stunting": st5, "wasting": round(max(3, min(30, 8 + 14 * poor + r.gauss(0, 2))), 1),
          "underweight": round(max(8, min(55, st5 * .9 + r.gauss(0, 3))), 1),
          "child_anaemia": round(max(30, min(85, 52 + 22 * poor + r.gauss(0, 4))), 1),
          "women_anaemia": round(max(30, min(80, 48 + 20 * poor + r.gauss(0, 4))), 1),
          "women_bmi_low": round(max(5, min(40, 10 + 16 * poor + r.gauss(0, 2.5))), 1)}
    n6 = None
    if r.random() > .07:
        n6 = {"year": "2023-24", "stunting": round(max(5, n5["stunting"] - r.uniform(-1.5, 5)), 1),
              "wasting": round(max(2, n5["wasting"] - r.uniform(-2, 3)), 1),
              "underweight": round(max(5, n5["underweight"] - r.uniform(-1.5, 4)), 1),
              "child_anaemia": round(min(88, max(28, n5["child_anaemia"] + r.uniform(-4, 6))), 1),
              "women_anaemia": round(min(85, max(28, n5["women_anaemia"] + r.uniform(-3, 5))), 1),
              "women_bmi_low": round(max(4, n5["women_bmi_low"] - r.uniform(-1, 3)), 1)}

    # --- yield sensitivity
    fg_el = -(4 + 22 * hz * (1.15 - .6 * irr) + r.uniform(-3, 3))
    fg_el = round(max(-38, min(1, fg_el)))
    ys = {"foodgrain_elnino_pct": fg_el, "n_elnino_years": len(EL_YEARS),
          "by_group": {"cereals": round(fg_el * r.uniform(.65, .95)), "pulses": round(fg_el * r.uniform(1.1, 1.6)),
                       "oilseeds": round(fg_el * r.uniform(1.0, 1.45)), "millets": round(fg_el * r.uniform(.3, .7))}}

    # --- risk raw components
    sens = min(1, max(0, .30 * crops["rainfed_share"] + .20 * min(1, crops["yield_cv10"] / .45) + .15 * crops["small_marginal_share"]
                      + .20 * min(1, n5["stunting"] / 50) + .15 * min(1, max(0, (1 - min(ss, 1.5)))) + r.uniform(-.03, .03)))
    cap = min(1, max(0, .45 * irr + .25 * (1 - pds) + .15 * crops["simpson_div"] + .15 * (1 - climate["clim_vuln_index"]) + r.uniform(-.03, .03)))
    expo = {"neutral": min(1, max(0.02, .1 + .02 * hz + r.uniform(0, .04))),
            "elnino": min(1, max(.05, -eln_mean / 34)),
            "elnino_strong": min(1, max(.08, -eln_mean * 1.3 / 34))}
    shock = {"neutral": round(max(-8, min(2, fg_el * .12 + r.gauss(0, .8)))),
             "elnino": round(fg_el * .8 + r.gauss(0, 1.2)),
             "elnino_strong": round(fg_el * 1.25 + r.gauss(0, 1.5))}
    risk = {}
    for sc in raws:
        raw = expo[sc] ** 0.9 * (.3 + .7 * sens) * (1.05 - cap)
        raws[sc].append(raw)
        comps = {"elnino_rain_deficit": expo[sc] * .9, "rainfed_share": crops["rainfed_share"] * .55, "yield_cv": crops["yield_cv10"] * 1.2,
                 "child_stunting": n5["stunting"] / 100 * 1.1, "small_marginal_share": crops["small_marginal_share"] * .4,
                 "low_irrigation": (1 - irr) * .35, "pds_dependency": pds * .3, "food_deficit": max(0, 1 - min(ss, 1)) * .5}
        s_ = sum(comps.values())
        drivers = sorted(({"name": k, "contrib": round(v / s_, 3)} for k, v in comps.items()), key=lambda x: -x["contrib"])[:6]
        risk[sc] = {"score": None, "band": None, "exposure": round(expo[sc], 2), "sensitivity": round(sens, 2), "capacity": round(cap, 2),
                    "expected_yield_shock_pct": shock[sc], "drivers": drivers}

    # --- hindcast (filled after timeseries)
    # --- timeseries
    y0 = max(.5, (fg / max(1, area)) * r.uniform(.6, .8) + .3)
    ylds, devs = {}, {}
    gsc = {"cereals": 1.0, "pulses": .35, "oilseeds": .5, "millets": .55}
    by_group = {g: {} for g in gsc}
    for y in YIELD_YEARS:
        trend = y0 * (1 + 0.017 * (y - 2000))
        a = anom[str(y)]
        dev = (0.0 if a > 0 else 0.0) + 0.0
        effect = (a / 100) * (abs(fg_el) / max(1, abs(eln_mean)) if eln_mean else 0.5) * (1.0 if a < 0 else 0.25)
        effect = max(-.6, min(.25, effect + r.gauss(0, .05 + .08 * hz)))
        ylds[str(y)] = round(trend * (1 + effect), 3)
        devs[y] = round(effect * 100)
        for g, k in gsc.items():
            by_group[g][str(y)] = round(trend * k * (1 + effect * r.uniform(.8, 1.3)) , 3)
    hind = {}
    for y in (2009, 2014, 2015, 2023):
        hind[str(y)] = {"predicted_score": None, "actual_foodgrain_yield_dev_pct": devs[y], "_raw": expo["elnino"] * (1 + (-anom[str(y)]) / 60 * .5) * (.3 + .7 * sens) * (1.05 - cap)}
    ts = {"yield": {"foodgrain_t_ha": ylds, "by_group": by_group},
          "rain_jjas_mm": {str(y): round(normal * (1 + anom[str(y)] / 100)) for y in YEARS},
          "oni_phase": {str(y): ("El Niño" if y in EL_YEARS else "La Niña" if y in LA_YEARS else "Neutral") for y in YEARS},
          "nfhs": [dict(round="NFHS-5", **n5)] + ([dict(round="NFHS-6", **n6)] if n6 else []),
          "pds_monthly": [{"date": f"{2024 + (m // 12)}-{(m % 12) + 1:02d}-01",
                           "rice_t": int(pop26 * .0017 * pds * r.uniform(.85, 1.15)), "wheat_t": int(pop26 * .0006 * pds * r.uniform(.7, 1.3))}
                          for m in range(24)]}
    recs.append({"lgd": p["lgd"], "district": p["district"], "state": p["state"], "census11": str(p["lgd"] + 11),
                 "centroid": [d["lon"], d["lat"]], "population_2011": pop11, "population_2026": pop26, "children_u5_est": u5,
                 "crops": crops, "food_balance": fb, "nutrition": {"nfhs5": n5, "nfhs6": n6}, "climate": climate,
                 "yield_sensitivity": ys, "risk": risk, "hindcast": hind, "_ts": ts})

# rank-normalise on the El Nino distribution so bands are comparable across scenarios
ref = np.sort(np.array(raws["elnino"]))
def to_score(raw):
    pct = np.searchsorted(ref, raw) / len(ref)
    return int(round(100 * min(1, pct) ** 1.3))
def band(s): return "high" if s >= 67 else "medium" if s >= 34 else "low"
def _add_actions(rec):
    r = random.Random(rec["lgd"] * 7 + 1)
    c, fb, nut = rec["crops"], rec["food_balance"], rec["nutrition"]
    stunt = (nut["nfhs6"] or nut["nfhs5"])["stunting"]
    neutral_def = max(0, fb["requirement_t"] - fb["edible_prod_t"] * (1 + rec["risk"]["neutral"]["expected_yield_shock_pct"] / 100))
    for sc, blk in rec["risk"].items():
        shock = blk["expected_yield_shock_pct"]
        deficit = max(0, fb["requirement_t"] - fb["edible_prod_t"] * (1 + shock / 100))
        grain = int(round(max(0, deficit - neutral_def), -2))
        pulses = int(round(c["groups"]["pulses"]["prod_t"] * abs(rec["yield_sensitivity"]["by_group"]["pulses"] * (0.6 if sc == "neutral" else 1.0 if sc == "elnino" else 1.4)) / 100 * .875, -1))
        band = blk["band"]
        agri = rec["population_2026"] * r.uniform(.3, .6) * .4
        out = {"grain_preposition_t": grain, "pulses_preposition_t": pulses,
               "anganwadi_children": int(round(rec["children_u5_est"] * stunt / 100, -2)),
               "women_anaemia_target": int(round(rec["population_2026"] * .26 * (nut["nfhs6"] or nut["nfhs5"])["women_anaemia"] / 100, -2)),
               "seed_bank_ha": int(round(.2 * c["rainfed_share"] * c["gross_cropped_area_ha"], -2)) if band != "low" else None,
               "mgnrega_persondays": int(round(agri * 50 * c["rainfed_share"], -3)) if band == "high" else None,
               "pmfby_gap_farmers": int(round(max(0, c["gross_cropped_area_ha"] / 1.4 * r.uniform(.4, .9) - c["gross_cropped_area_ha"] / 1.4 * r.uniform(.1, .4)), -2)) if r.random() > .06 else None,
               "fodder_flag": band == "high" and (sum(t["share"] for t in c["top"] if t["crop"] in ("Jowar", "Bajra", "Ragi", "Millets", "Cotton", "Sugarcane", "Jute")) > .3),
               "lead": {"rabi_2026_27": "by 2026-11-15", "kharif_2027": "by 2027-05-15"}}
        blk["actions"] = out
    return rec


for i, rec in enumerate(recs):
    for sc in raws:
        s = to_score(raws[sc][i]); rec["risk"][sc]["score"] = s; rec["risk"][sc]["band"] = band(s)
    for y, h in rec["hindcast"].items():
        h.pop("_raw")
        k = {"2009": 1.0, "2015": .97, "2014": .85, "2023": .65}[y]
        rr = random.Random(rec["lgd"] * 13 + int(y))
        h["predicted_score"] = int(max(0, min(100, round(rec["risk"]["elnino"]["score"] * k + rr.uniform(-7, 7)))))
    _add_actions(rec)
    ts = rec.pop("_ts")
    json.dump(ts, open(OUT / "timeseries" / f"{rec['lgd']}.json", "w"), separators=(",", ":"))

for sc in raws:
    order = sorted(recs, key=lambda r_: (-r_["risk"][sc]["score"], -(r_["risk"][sc]["actions"]["grain_preposition_t"] or 0)))
    seen = {}
    for n, r_ in enumerate(order, 1):
        seen[r_["state"]] = seen.get(r_["state"], 0) + 1
        r_["risk"][sc]["actions"]["priority_rank_national"] = n
        r_["risk"][sc]["actions"]["priority_rank_state"] = seen[r_["state"]]
json.dump(recs, open(OUT / "districts.json", "w"), separators=(",", ":"))
cnt = {sc: {b: sum(1 for r_ in recs if r_["risk"][sc]["band"] == b) for b in ("high", "medium", "low")} for sc in raws}
hi = [r_ for r_ in recs if r_["risk"]["elnino"]["band"] == "high"]
kpis = {"as_of": "2026-10-17",
        "enso": {"state": "El Niño", "nino34": 2.1, "p_historic_ond": 0.83, "source": "NOAA CPC 2026-10-08"},
        "central_pool": {"date": "2026-10-01", "rice_lmt": 214.0, "wheat_lmt": 350.0, "total_lmt": 564.0, "norm_lmt": 307.7, "months_of_offtake": 13.9},
        "scenario_counts": cnt,
        "people_in_high_risk": sum(r_["population_2026"] for r_ in hi),
        "children_u5_in_high_risk": sum(r_["children_u5_est"] for r_ in hi)}
def tot(sc, k): return int(sum((r_["risk"][sc]["actions"][k] or 0) for r_ in recs))
kpis["actions_total"] = {sc: {"grain_preposition_t": tot(sc, "grain_preposition_t"), "pulses_preposition_t": tot(sc, "pulses_preposition_t"),
                              "anganwadi_children": tot(sc, "anganwadi_children"), "women_anaemia_target": tot(sc, "women_anaemia_target"),
                              "seed_bank_ha": tot(sc, "seed_bank_ha"), "mgnrega_persondays": tot(sc, "mgnrega_persondays"),
                              "pmfby_gap_farmers": tot(sc, "pmfby_gap_farmers")} for sc in raws}
by_state = {}
for r_ in recs: by_state[r_["state"]] = by_state.get(r_["state"], 0) + (r_["risk"]["elnino"]["actions"]["grain_preposition_t"] or 0)
kpis["top_states"] = [{"state": k, "grain_preposition_t": v} for k, v in sorted(by_state.items(), key=lambda kv: -kv[1])[:10]]
json.dump(kpis, open(OUT / "kpis.json", "w"), indent=1)
print(len(recs), "districts", cnt)
