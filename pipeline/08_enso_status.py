"""08_enso_status.py - monthly ENSO refresh for the AnnaDrishti early-warning product (SCHEMA Addendum F).

What it does (all steps independent; any failure keeps the current value and is logged):
  1. NOAA CPC ONI table (https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt) -> data/raw/datasets/05_weather_drought_imd/enso/noaa_cpc_oni.txt
     Only replaced when the download parses, has at least as many rows as the current file, ends no earlier, and its 2000-2025
     values agree with the current file within +/-0.30 C (NOAA re-bases the ONI every 5 years; a large shift would silently
     change the El Nino / La Nina analog years used everywhere, so it is refused and logged instead).
  2. NOAA CPC ENSO Diagnostic Discussion (status, Nino-3.4/3/1+2, historic-event chances, next update) - regex on the HTML text.
  3. CCSR/IRI ENSO Quick Look / Technical Update (the plume probabilities are only published as figures; the text gives the
     El Nino probability by season) -> `iri_plume_<published date>` block and `p_by_season`.
  4. Rewrites artifacts/enso_status.json with
       p_by_season  {season_id: {elnino, neutral, lanina}}  (rabi = mean of NDJ, DJF, JFM; kharif = MJJ of the next year)
       outlook_seasons [{id, label, sowing, harvest, status, lead}]  (consumed by 04_risk.py / 06_export.py)
     When the text gives no neutral / La Nina split for a season, the non-El-Nino remainder is split with the ratio of the
     previous p_by_season (default 85 / 15, the climatological neutral : La Nina ratio of the previous IRI release).

Safe offline: with no network (or unparsable pages) nothing changes, except that a missing `p_by_season` is derived once from
the plume already stored in enso_status.json. The file is only rewritten when its content (ignoring timestamps) changes.
All downloaded text is treated as data: only numbers matched by the regexes below are used.

Run: python3 pipeline/08_enso_status.py [--offline]
"""
from __future__ import annotations
import argparse, datetime as dt, html, json, os, re, sys, tempfile, urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ART, RAW, save_json

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
CPC_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"
IRI_URL = "https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/"
ONI_PATH = RAW / "05_weather_drought_imd" / "enso" / "noaa_cpc_oni.txt"
STATUS_PATH = ART / "enso_status.json"
TIMEOUT = 25
SEAS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]   # index k has centre month k+1
RABI_PLUME = ["NDJ", "DJF", "JFM"]          # rabi crop growth window (Nov-Mar)
KHARIF_PLUME = ["MJJ"]                      # kharif sowing window (convention of the v3 model: IRI MJJ El Nino probability)
DEFAULT_NEUTRAL_SHARE = 0.85                # neutral share of the non-El-Nino remainder (IRI Sep-2026 MJJ: 0.33 / (0.33 + 0.06) = 0.85)
ONI_TOL = 0.30
OFFLINE = False


def log(*a):
    print("[08_enso]", *a, flush=True)


def fetch(url: str) -> str | None:
    if OFFLINE:
        log(f"offline mode, skip {url}")
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AnnaDrishti enso refresh)"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("cp1252", errors="replace")
    except Exception as e:                      # noqa: BLE001
        log(f"fetch failed {url}: {type(e).__name__}: {e}")
        return None


def page_text(t: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", t, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t)).replace("\xa0", " ")
    return re.sub(r"\n\s*\n+", "\n", t)


# ── 1. ONI ──────────────────────────────────────────────────────────────────────
def parse_oni(txt: str) -> pd.DataFrame | None:
    rows = []
    for ln in txt.splitlines()[1:]:
        p = ln.split()
        if len(p) == 4 and p[0] in SEAS:
            try:
                rows.append((p[0], int(p[1]), float(p[2]), float(p[3])))
            except ValueError:
                return None
    if len(rows) < 800:
        return None
    return pd.DataFrame(rows, columns=["seas", "yr", "total", "anom"])


def refresh_oni() -> str:
    txt = fetch(ONI_URL)
    if txt is None:
        return "failed (no download)"
    new = parse_oni(txt)
    if new is None:
        return "failed (parse)"
    old = pd.read_csv(ONI_PATH, sep=r"\s+"); old.columns = ["seas", "yr", "total", "anom"]
    m = old.merge(new, on=["seas", "yr"], suffixes=("_o", "_n"))
    m = m[(m.yr >= 2000) & (m.yr <= 2025)]
    last_o, last_n = (old.yr * 12 + old.seas.map(SEAS.index)).max(), (new.yr * 12 + new.seas.map(SEAS.index)).max()
    if len(new) < len(old) or last_n < last_o:
        return f"refused (download has {len(new)} rows vs {len(old)} current / ends earlier)"
    d = float((m.anom_o - m.anom_n).abs().max())
    if not np.isfinite(d) or d > ONI_TOL:
        return f"refused (2000-2025 values differ from current file by up to {d:.2f} C > {ONI_TOL}; re-base? check manually)"
    if txt.strip() == ONI_PATH.read_text().strip():
        return "unchanged"
    tmp = ONI_PATH.with_suffix(".tmp")
    tmp.write_text(txt if txt.endswith("\n") else txt + "\n")
    os.replace(tmp, ONI_PATH)
    return f"updated ({len(old)} -> {len(new)} rows; max |diff| 2000-25 = {d:.2f} C; latest {new.iloc[-1].seas} {new.iloc[-1].yr} = {new.iloc[-1].anom:+.2f})"


# ── 2. CPC diagnostic discussion ──────────────────────────────────────────────────
MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}


def parse_date(s: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})", s)
    if m and m.group(2) in MONTHS:
        return dt.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).isoformat()
    m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", s)
    if m and m.group(1) in MONTHS:
        return dt.date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2))).isoformat()
    return None


def parse_cpc(raw: str) -> dict:
    t = page_text(raw)
    out = {}
    m = re.search(r"issued by.*?(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", t, flags=re.S)
    if m and parse_date(m.group(1)):
        out["as_of"] = parse_date(m.group(1))
    m = re.search(r"ENSO Alert System Status:\s*\n?\s*([A-Za-z ñÑ.]+?(?:Advisory|Watch|Not Active))", t)
    if m:
        adv = re.sub(r"\s+", " ", m.group(1)).strip()
        out["advisory"] = adv
        out["state"] = "El Niño" if re.search(r"El Ni.o", adv) and "Advisory" in adv else ("La Niña" if re.search(r"La Ni.a", adv) and "Advisory" in adv else "Neutral")
    for key, pat in (("nino34_c", r"([+-]?\d+\.\d)\s*°?C in Ni.o-3\.4"), ("nino3_c", r"([+-]?\d+\.\d)\s*°?C in Ni.o-3\b(?!\.)"),
                     ("nino12_c", r"([+-]?\d+\.\d)\s*°?C in Ni.o-1\+2")):
        m = re.search(pat, t)
        if m:
            out[key] = float(m.group(1))
    m = re.search(r"Synopsis:\s*\n(.+?)\n", t)
    if m:
        out["cpc_text"] = re.sub(r"\s+", " ", m.group(1)).strip()
    m = re.search(r"chance is (\d+)% for September-November, (\d+)% for October-December, and (\d+)% for November-January", t)
    if m:
        out["p_historic_event_vals"] = {"SON": int(m.group(1)) / 100, "OND": int(m.group(2)) / 100, "NDJ": int(m.group(3)) / 100}
    m = re.search(r"next ENSO Diagnostics? Discussion is scheduled for (\d{1,2} [A-Z][a-z]+ \d{4})", t)
    if m and parse_date(m.group(1)):
        out["next_update"] = parse_date(m.group(1))
    return out


# ── 3. IRI ──────────────────────────────────────────────────────────────────────
def expand(s1: str, y1: int, s2: str, y2: int) -> list[tuple[str, int]]:
    """SON 2026 .. FMA 2027 -> [(SON,2026),(OND,2026),(NDJ,2026),(DJF,2027),...]; year = year of the centre month."""
    k, y, out = SEAS.index(s1), y1, [(s1, y1)]
    for _ in range(14):
        if (SEAS[k], y) == (s2, y2):
            return out
        k = (k + 1) % 12
        if k == 0:
            y += 1
        out.append((SEAS[k], y))
    return [(s1, y1), (s2, y2)]


def parse_iri(raw: str) -> dict:
    t = page_text(raw)
    out = {}
    m = re.search(r"Published:\s*([A-Z][a-z]+ \d{1,2}, \d{4})", t)
    if m and parse_date(m.group(1)):
        out["published"] = parse_date(m.group(1))
    p, pn = {}, {}      # p[(seas, year)] = El Nino probability; pn = (neutral, lanina) when stated
    m = re.search(r"El Ni.o probabilit\w* remain at (\d+)% from ([A-Z]{3}) (\d{4}) through ([A-Z]{3}) (\d{4})", t)
    if m:
        for s, y in expand(m.group(2), int(m.group(3)), m.group(4), int(m.group(5))):
            p[(s, y)] = int(m.group(1)) / 100
        # the rest of that paragraph: "followed by 99% in MAM 2027 and 90% in AMJ, before declining to 61% in MJJ 2027"
        line = next((ln for ln in t.splitlines() if m.group(0) in ln), "")
        tail = line[line.find(m.group(0)) + len(m.group(0)):]
        yr = int(m.group(5))
        for pm in re.finditer(r"(\d{1,3})%\s+in\s+([A-Z]{3})(?:\s+(\d{4}))?", tail):
            if pm.group(2) in SEAS:
                yr = int(pm.group(3)) if pm.group(3) else yr
                p[(pm.group(2), yr)] = int(pm.group(1)) / 100
        m2 = re.search(r"no probability is assigned to either La Ni.a or ENSO-neutral conditions from ([A-Z]{3}) (\d{4}) through ([A-Z]{3}) (\d{4})", t)
        if m2:
            for s, y in expand(m2.group(1), int(m2.group(2)), m2.group(3), int(m2.group(4))):
                pn[(s, y)] = (0.0, 0.0)
    out["p_elnino"] = p
    out["p_zero_other"] = pn
    return out


# ── 4. assemble ──────────────────────────────────────────────────────────────────
def split_rest(rest: float, ratio_neutral: float) -> tuple[float, float]:
    n = round(rest * ratio_neutral, 2)
    return n, round(rest - n, 2)


def season_p(plume: dict[str, dict], names: list[str], ratio_neutral: float) -> dict | None:
    """Mean over the plume seasons `names` of {elnino, neutral, lanina}; plume = {'NDJ2026': {'elnino':..,'neutral':..,'lanina':..}}."""
    vals = []
    for nm in names:
        key = next((k for k in plume if k.startswith(nm)), None)
        if key is None or plume[key].get("elnino") is None:
            return None
        v = plume[key]
        e = float(v["elnino"])
        if v.get("neutral") is None or v.get("lanina") is None:
            n, l = split_rest(max(0.0, 1 - e), ratio_neutral)
        else:
            n, l = float(v["neutral"]), float(v["lanina"])
        vals.append((e, n, l))
    e, n, l = np.mean(vals, 0)
    e, n = round(float(e), 2), round(float(n), 2)
    return {"elnino": e, "neutral": n, "lanina": round(max(0.0, 1 - e - n), 2)}


def outlook_seasons(asof: dt.date) -> list[dict]:
    y = asof.year if asof.month >= 7 else asof.year - 1          # autumn-sown rabi that is current / next
    rid = f"rabi_{y}_{(y + 1) % 100:02d}"; kid = f"kharif_{y + 1}"
    r_open, r_close = dt.date(y, 10, 15), dt.date(y, 12, 15)
    k_open, k_close = dt.date(y + 1, 6, 1), dt.date(y + 1, 7, 31)
    rs = "sowing_now" if r_open <= asof <= r_close else ("upcoming" if asof < r_open else "harvest")
    ks = "upcoming" if asof < k_open else ("sowing_now" if asof <= k_close else "harvest")
    return [{"id": rid, "label": f"Rabi {y}-{(y + 1) % 100:02d}", "sowing": f"{y}-10-15..{y}-12-15", "harvest": f"{y + 1}-03..{y + 1}-04",
             "status": rs, "lead": f"by {y}-11-15"},
            {"id": kid, "label": f"Kharif {y + 1}", "sowing": f"{y + 1}-06..{y + 1}-07", "harvest": f"{y + 1}-10..{y + 1}-11",
             "status": ks, "lead": f"by {y + 1}-05-15"}]


def stable(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("updated_at", "fetch_status")}


def main():
    global OFFLINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    OFFLINE = ap.parse_args().offline
    old = json.load(open(STATUS_PATH))
    new = json.loads(json.dumps(old))
    status = {}

    # 1. ONI
    try:
        status["oni"] = refresh_oni()
    except Exception as e:                      # noqa: BLE001
        status["oni"] = f"failed ({type(e).__name__}: {e})"
    log("ONI:", status["oni"])

    # 2. CPC
    cpc = {}
    raw = fetch(CPC_URL)
    if raw:
        try:
            cpc = parse_cpc(raw)
        except Exception as e:                  # noqa: BLE001
            log("CPC parse error:", e)
    need = {"as_of", "state", "nino34_c"}
    if need <= set(cpc):
        for k in ("as_of", "state", "advisory", "nino34_c", "nino3_c", "nino12_c", "cpc_text", "next_update"):
            if k in cpc:
                new[k] = cpc[k]
        if "p_historic_event_vals" in cpc:
            v = cpc["p_historic_event_vals"]
            ph = dict(new.get("p_historic_event", {}))
            ph.update({"SON2026"[:3] + str(new["as_of"][:4]): v["SON"], "OND" + new["as_of"][:4]: v["OND"], "NDJ%s-%02d" % (new["as_of"][:4], (int(new["as_of"][:4]) + 1) % 100): v["NDJ"]})
            new["p_historic_event"] = ph
        new["sources"] = [s for s in new.get("sources", []) if not s.startswith("NOAA CPC ENSO Diagnostic")] + [f"NOAA CPC ENSO Diagnostic Discussion {new['as_of']}"]
        status["cpc"] = f"ok ({new['as_of']}, {new['state']}, Nino3.4 {new['nino34_c']:+.1f})"
    else:
        status["cpc"] = f"failed (missing {sorted(need - set(cpc))})" if raw else "failed (no download)"
    log("CPC:", status["cpc"])

    # 3. IRI plume probabilities
    prev_p = old.get("p_by_season") or {}
    ratio = DEFAULT_NEUTRAL_SHARE
    for v in prev_p.values():
        if v.get("neutral") is not None and v.get("lanina") is not None and (v["neutral"] + v["lanina"]) > 0:
            ratio = v["neutral"] / (v["neutral"] + v["lanina"]); break
    iri = {}
    raw = fetch(IRI_URL)
    if raw:
        try:
            iri = parse_iri(raw)
        except Exception as e:                  # noqa: BLE001
            log("IRI parse error:", e)
    plume_key = next((k for k in sorted(new) if k.startswith("iri_plume_")), None)
    plume = dict(new.get(plume_key, {})) if plume_key else {}
    if iri.get("published") and len(iri.get("p_elnino", {})) >= 6:
        plume = {}
        for (s, y), pe in sorted(iri["p_elnino"].items(), key=lambda kv: (kv[0][1], SEAS.index(kv[0][0]) if kv[0][0] != "NDJ" else 11)):
            e = {"elnino": pe}
            if (s, y) in iri["p_zero_other"]:
                e.update(neutral=0.0, lanina=0.0)
            plume[f"{s}{y}"] = e
        for k in [k for k in new if k.startswith("iri_plume_")]:
            del new[k]
        plume_key = f"iri_plume_{iri['published']}"
        new[plume_key] = plume
        new["sources"] = [s for s in new.get("sources", []) if not s.startswith("IRI ENSO forecast plume")] + [f"IRI ENSO forecast plume {iri['published']}"]
        status["iri"] = f"ok (published {iri['published']}; {len(plume)} seasons, El Nino {min(v['elnino'] for v in plume.values()):.2f}-{max(v['elnino'] for v in plume.values()):.2f})"
    else:
        status["iri"] = "failed (parse: no probabilities found)" if raw else "failed (no download)"
    log("IRI:", status["iri"], "-> plume source:", plume_key)

    # 4. p_by_season + outlook seasons
    asof = dt.date.fromisoformat(new.get("as_of") or dt.date.today().isoformat())
    # seasons follow the calendar date of the run, not the date of the CPC discussion (which can lag by days)
    seasons = outlook_seasons(max(asof, dt.date.today()))
    if (prev_p and not (iri.get("published") and len(iri.get("p_elnino", {})) >= 6)):
        # keep current values when the plume was not refreshed and the season ids did not roll over
        if all(s["id"] in prev_p for s in seasons):
            status["p_by_season"] = "kept current values"
    p_new = {}
    # plume keys are '<SEAS><year>' (new) or '<SEAS>' / '<SEAS><year>' (old hand-written block): match by prefix, kharif MJJ uses the year of the season id
    for s in seasons:
        names = RABI_PLUME if s["id"].startswith("rabi") else KHARIF_PLUME
        yr = int(re.search(r"(\d{4})", s["id"]).group(1))
        want = []
        for nm in names:
            yy = yr + 1 if (s["id"].startswith("rabi") and nm in ("DJF", "JFM")) else yr
            want.append(f"{nm}{yy}")
        # exact '<SEAS><year>' first, then bare '<SEAS>' (legacy block)
        pl = {}
        for w_ in want:
            if w_ in plume:
                pl[w_] = plume[w_]
            elif w_[:3] in plume:
                pl[w_] = plume[w_[:3]]
        got = season_p(pl, want, ratio) if len(pl) == len(want) else None
        if got is not None:
            p_new[s["id"]] = got
        elif s["id"] in prev_p:
            p_new[s["id"]] = prev_p[s["id"]]
            log(f"no plume probabilities for {s['id']} ({want}); kept previous p_by_season")
    new["p_by_season"] = p_new
    new["p_by_season_note"] = ("El Nino probability = mean of the IRI plume probabilities over NDJ/DJF/JFM (rabi) or MJJ (kharif); neutral / La Nina split from the plume where "
                               f"stated, else the non-El-Nino remainder split {ratio:.2f} : {1 - ratio:.2f}. Source: {plume_key}.")
    new["outlook_seasons"] = seasons
    if not new.get("india_implication") or (iri.get("published") and cpc):
        pk = (p_new.get(seasons[1]["id"]) or {}).get("elnino")
        new["india_implication"] = (f"{seasons[0]['label']} sowing under {new.get('state', 'ENSO')} conditions (risk: warm Feb-Mar, weak western disturbances); "
                                    f"{seasons[1]['label']} monsoon onset / June-July rainfall at elevated deficit risk if El Niño persists into MJJ ({pk:.0%})." if pk is not None else new.get("india_implication"))
    status.setdefault("p_by_season", "updated" if p_new != prev_p else "unchanged")

    changed = stable(new) != stable(old)
    new["fetch_status"] = status
    if changed:
        new["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
        save_json(new, STATUS_PATH)
        log("enso_status.json rewritten;", {k: v for k, v in p_new.items()})
    else:
        log("no change to enso_status.json (current values retained);", status)
    print(json.dumps({"fetch_status": status, "p_by_season": p_new, "state": new.get("state"), "nino34_c": new.get("nino34_c"), "as_of": new.get("as_of")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
