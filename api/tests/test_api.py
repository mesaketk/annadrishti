import json

import pytest
from fastapi.testclient import TestClient

from api import data, ratelimit, tools
from api.main import advisory_cache, app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Hermetic: empty artifacts dir, no web mock dir -> built-in mock data, MOCK_LLM on."""
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("WEB_MOCK_DIR", str(tmp_path / "nomock"))
    monkeypatch.setenv("WEB_DIST_DIR", str(tmp_path / "dist"))
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("USE_VERTEX", raising=False)
    monkeypatch.delenv("ARTIFACTS_GCS_URI", raising=False)
    for v in ("RATE_LIMIT_BYPASS_TOKEN", "XFF_POSITION", "LLM_DAILY_CAP", "TTS_DAILY_CAP", "LLM_PER_MIN_CAP"):
        monkeypatch.delenv(v, raising=False)
    ratelimit.limiter.reset()
    advisory_cache._mem.clear()
    advisory_cache._loaded_from = None
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok" and j["data_mode"] == "mock" and j["llm"]["mock"] is True
    assert r.headers["x-data-mode"] == "mock"


def test_districts_kpis_mock(client):
    r = client.get("/api/districts")
    assert r.status_code == 200 and r.headers["x-data-mode"] == "mock"
    assert {d["lgd"] for d in r.json()} >= {486}
    k = client.get("/api/kpis").json()
    assert k["enso"]["state"] == "El Niño"


def test_timeseries(client):
    assert client.get("/api/timeseries/486").status_code == 200
    r = client.get("/api/timeseries/123456789")
    assert r.status_code == 404 and "error" in r.json()


def test_real_artifacts_take_precedence(client, tmp_path):
    art = tmp_path / "artifacts"
    (art / "timeseries").mkdir(parents=True)
    d = dict(data.BUILTIN_DISTRICTS[0], lgd=7, district="Realpur")
    (art / "districts.json").write_text(json.dumps([d]))
    (art / "timeseries" / "7.json").write_text(json.dumps({"yield": {}}))
    r = client.get("/api/districts")
    assert r.headers["x-data-mode"] == "real" and r.json()[0]["district"] == "Realpur"
    assert client.get("/api/timeseries/7").json() == {"yield": {}}


@pytest.mark.parametrize("audience,language", [("official", "en"), ("farmer", "hi"), ("farmer", "mr")])
def test_advisory_mock(client, audience, language):
    r = client.post("/api/advisory/486", json={"audience": audience, "language": language, "scenario": "elnino"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["markdown"] and j["model"] == "mock-llm"
    assert j["grounding"]["lgd"] == 486 and "risk.elnino.score" in j["grounding"]["fields_used"]
    # second call is served from cache
    assert client.post("/api/advisory/486", json={"audience": audience, "language": language,
                                                  "scenario": "elnino"}).json()["cached"] is True


def test_advisory_errors(client):
    assert client.post("/api/advisory/1", json={}).status_code == 404
    assert client.post("/api/advisory/486", json={"language": "xx"}).status_code == 422


def test_chat_mock(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Which districts in Maharashtra are riskiest?"}],
                                       "scenario": "elnino"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["reply"] and 486 in j["citations"]
    r = client.post("/api/chat", json={"messages": [{"role": "assistant", "content": "hi"}]})
    assert r.status_code == 422


def test_no_credentials_returns_503(client, monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "0")
    r = client.post("/api/advisory/486", json={})
    assert r.status_code == 503 and r.json() == {"error": "GEMINI_API_KEY not set"}
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503 and r.json()["error"] == "GEMINI_API_KEY not set"


def test_spa_fallback(client, tmp_path):
    assert client.get("/").status_code == 404  # dist not built
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>")
    (dist / "assets" / "a.js").write_text("x=1")
    assert client.get("/").text == "<html>spa</html>"
    assert client.get("/some/client/route").text == "<html>spa</html>"
    assert client.get("/assets/a.js").text == "x=1"
    assert client.get("/../secret").status_code in (200, 404)
    assert client.get("/api/nope").status_code == 404
    assert client.get("/api/nope").json()["error"]


def test_tools(client):
    r = tools.rank_districts("risk_score", "elnino", None, 2)
    assert r["results"][0]["value"] >= r["results"][1]["value"]
    assert tools.rank_districts("nonsense")["error"]
    assert tools.get_district("nandurbar")["lgd"] == 486
    assert tools.get_district("nowhere")["error"]
    cmp = tools.compare_scenarios("486")
    assert cmp["delta_elnino_vs_neutral"] == 47
    ns = tools.national_summary()
    assert ns["bands"]["elnino"]["high"] >= 1
    lg: list[int] = []
    tools.collect_lgds(r, lg)
    assert lg


def test_gemini_tool_loop_with_fake_client(client, monkeypatch):
    """Exercises the real (non-mock) code path: function-call round, then final text."""
    from google.genai import types

    from api import llm

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    calls = []

    class Resp:
        def __init__(self, fc=None, text=None):
            self.function_calls = fc
            self.text = text
            self.candidates = [types.Candidate(content=types.Content(role="model", parts=[
                types.Part(function_call=fc[0]) if fc else types.Part.from_text(text=text)]))]

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append((model, config))
            if len(calls) == 1:
                assert config.tools and config.system_instruction
                return Resp(fc=[types.FunctionCall(name="rank_districts", args={"metric": "risk_score", "top_n": 2})])
            last = contents[-1]
            assert last.role == "user" and last.parts[0].function_response.name == "rank_districts"
            return Resp(text="Nandurbar is highest.")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(llm, "get_client", lambda: FakeClient())
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "top districts?"}]})
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "Nandurbar is highest." and 486 in r.json()["citations"]

    calls.clear()

    class FakeModels2:
        def generate_content(self, model, contents, config):
            assert "DISTRICT EVIDENCE" in contents and config.system_instruction
            return type("R", (), {"text": "## advisory"})()

    class FakeClient2:
        models = FakeModels2()

    monkeypatch.setattr(llm, "get_client", lambda: FakeClient2())
    r = client.post("/api/advisory/486", json={"audience": "official", "language": "en", "scenario": "elnino"})
    assert r.status_code == 200 and r.json()["markdown"] == "## advisory"
    assert r.json()["model"] == "gemini-2.5-flash"


def test_gcs_sync_downloads_json(client, tmp_path, monkeypatch):
    import sys
    import types as pytypes

    class Blob:
        def __init__(self, name):
            self.name = name

        def download_to_filename(self, fn):
            open(fn, "w").write("[]" if self.name.endswith("districts.json") else "{}")

    class Client:
        def list_blobs(self, bucket, prefix=None):
            assert bucket == "b" and prefix == "v1/"
            return [Blob("v1/districts.json"), Blob("v1/timeseries/5.json"), Blob("v1/_advisory_cache.json"),
                    Blob("v1/x.parquet")]

    storage = pytypes.SimpleNamespace(Client=Client)
    gc = pytypes.ModuleType("google.cloud")
    gc.storage = storage
    monkeypatch.setitem(sys.modules, "google.cloud", gc)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", storage)
    monkeypatch.setenv("ARTIFACTS_GCS_URI", "gs://b/v1")
    assert data.sync_from_gcs() == 2
    art = tmp_path / "artifacts"
    assert (art / "districts.json").exists() and (art / "timeseries" / "5.json").exists()
    assert not (art / "_advisory_cache.json").exists()


def test_actions_json_csv_filters(client, tmp_path):
    j = client.get("/api/actions?scenario=elnino").json()
    assert j["n"] == 3 and j["rows"][0]["score"] >= j["rows"][1]["score"]
    assert j["actions_total"]["grain_preposition_t"] > 0
    j = client.get("/api/actions?scenario=elnino&state=maharashtra&band=high").json()
    assert [r["lgd"] for r in j["rows"]] == [486]
    assert client.get("/api/actions?scenario=neutral").json()["rows"] == []  # no actions block -> []
    r = client.get("/api/actions?scenario=elnino&format=csv")
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("state,district,lgd,score,band") and len(lines) == 4
    assert client.get("/api/actions?scenario=bogus").status_code == 422
    # CSV artifact takes precedence over derivation
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    (tmp_path / "artifacts" / "actions_elnino.csv").write_text(
        "state,district,lgd,score,band,grain_preposition_t,fodder_flag\nX,Y,1,90,high,5,True\n")
    j = client.get("/api/actions?scenario=elnino").json()
    assert j["rows"][0]["district"] == "Y" and j["rows"][0]["fodder_flag"] is True
    assert j["actions_total"]["grain_preposition_t"] == 5


def test_state_brief_mock(client):
    r = client.post("/api/state_brief", json={"state": "Maharashtra", "scenario": "elnino"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert "Nandurbar" in j["markdown"] and j["grounding"]["top_districts"][0]["lgd"] == 486
    assert client.post("/api/state_brief", json={"state": "Maharashtra", "scenario": "elnino"}).json()["cached"] is True
    assert client.post("/api/state_brief", json={"state": "Atlantis"}).status_code == 404


def test_state_brief_503_without_key(client, monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "0")
    r = client.post("/api/state_brief", json={"state": "Maharashtra"})
    assert r.status_code == 503 and r.json()["error"] == "GEMINI_API_KEY not set"


def test_audio_mock_wav(client):
    import io
    import wave

    r = client.post("/api/advisory/486/audio", json={"language": "hi", "scenario": "elnino"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(r.content)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.getnframes() == 24000
    assert client.post("/api/advisory/1/audio", json={}).status_code == 404


def test_audio_503_without_key_and_real_path(client, monkeypatch, tmp_path):
    from google.genai import types

    from api import llm

    monkeypatch.setenv("MOCK_LLM", "0")
    r = client.post("/api/advisory/486/audio", json={})
    assert r.status_code == 503 and r.json()["error"] == "GEMINI_API_KEY not set"

    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    seen = {}

    class Models:
        def generate_content(self, model, contents, config):
            if config.response_modalities:  # TTS call
                seen["tts_model"], seen["text"] = model, contents
                assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Kore"
                part = types.Part(inline_data=types.Blob(data=b"\x01\x00" * 2400,
                                                         mime_type="audio/L16;codec=pcm;rate=24000"))
                return type("R", (), {"candidates": [types.Candidate(content=types.Content(parts=[part]))]})()
            return type("R", (), {"text": "### Title\n- **Sow** late\n- Enrol in PMFBY"})()

    monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"models": Models()})())
    r = client.post("/api/advisory/486/audio", json={"language": "en", "scenario": "elnino"})
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    assert seen["tts_model"] == "gemini-2.5-flash-preview-tts"
    assert "*" not in seen["text"] and "#" not in seen["text"] and "Sow late" in seen["text"]
    assert (tmp_path / "artifacts" / "_audio_cache" / "486_en_elnino.wav").exists()
    assert client.post("/api/advisory/486/audio", json={"language": "en"}).headers["x-audio-cache"] == "hit"


# ------------------------------------------------------------------ Addendum C: profile / department
def _adv(client, **body):
    body.setdefault("scenario", "elnino")
    return client.post("/api/advisory/486", json=body)


def _title(md: str) -> str:
    return next(line for line in md.splitlines() if line.startswith("###"))


def test_profile_department_validation(client):
    for bad in ({"profile": {"holding": "huge"}}, {"profile": {"water": "flooded"}},
                {"profile": {"livestock": "maybe"}}, {"profile": {"crop": "<script>x</script>"}},
                {"profile": {"crop": "x" * 41}}, {"department": "finance"}, {"profile": "small"}):
        assert _adv(client, audience="farmer", **bad).status_code == 422, bad
    ok = _adv(client, audience="farmer", profile={"holding": "marginal", "water": "partial", "crop": "Paddy",
                                                  "livestock": True, "tenant": True})
    assert ok.status_code == 200, ok.text
    assert _adv(client, audience="official", department="health").status_code == 200
    # extra / unknown keys are ignored (forward compatible) and old bodies still work
    assert _adv(client, audience="farmer", profile={"holding": "small", "foo": 1}).status_code == 200
    assert _adv(client, audience="farmer", profile=None).status_code == 200


def test_profile_defaults_and_grounding(client):
    d = data.district_by_lgd(486)
    top = d["crops"]["top"][0]["crop"]
    g = _adv(client, audience="farmer").json()["grounding"]
    assert g["profile"] == {"holding": "small", "water": "rainfed", "crop": top, "livestock": False, "tenant": False}
    assert g["department"] is None
    g = _adv(client, audience="farmer", profile={"crop": top.upper(), "holding": "medium_large"}).json()["grounding"]
    assert g["profile"]["crop"] == top and g["profile"]["holding"] == "medium_large"  # canonicalised to district's name
    assert _adv(client, audience="farmer", profile={"crop": "other"}).json()["grounding"]["profile"]["crop"] == "other"
    g = _adv(client, audience="official").json()["grounding"]
    assert g["department"] == "collector" and g["profile"] is None


def test_cache_key_separation(client):
    a = {"audience": "farmer", "profile": {"holding": "marginal", "water": "rainfed"}}
    b = {"audience": "farmer", "profile": {"holding": "medium_large", "water": "irrigated"}}
    assert _adv(client, **a).json()["cached"] is False
    assert _adv(client, **b).json()["cached"] is False       # different profile: not served from a's entry
    assert _adv(client, **a).json()["cached"] is True
    assert _adv(client, **b).json()["cached"] is True
    # each profile flag separates entries
    for flag in ({"livestock": True}, {"tenant": True}, {"crop": "Wheat"}):
        assert _adv(client, audience="farmer", profile={**a["profile"], **flag}).json()["cached"] is False
    # departments separate; an irrelevant field (profile on official, department on farmer) does not
    assert _adv(client, audience="official", department="health").json()["cached"] is False
    assert _adv(client, audience="official", department="agriculture").json()["cached"] is False
    assert _adv(client, audience="official", department="health").json()["cached"] is True
    assert _adv(client, audience="official", department="health", profile={"holding": "marginal"}).json()["cached"] is True
    assert _adv(client, **a, department="health").json()["cached"] is True
    # default == explicit default
    assert _adv(client, audience="official").json()["cached"] is False
    assert _adv(client, audience="official", department="collector").json()["cached"] is True


def test_mock_output_differs_by_department(client):
    depts = ["collector", "food_civil_supplies", "agriculture", "wcd_icds", "rural_development", "health",
             "animal_husbandry"]
    out = {x: _adv(client, audience="official", department=x).json()["markdown"] for x in depts}
    assert len({_title(m) for m in out.values()}) == 7
    assert len(set(out.values())) == 7
    assert "DSO + FPS inspectors" in out["food_civil_supplies"] and "CDPO + AWWs" in out["wcd_icds"]
    assert "BDO + MGNREGA PO" in out["rural_development"] and "KVK + ATMA" in out["agriculture"]
    assert "CMO + ASHAs" in out["health"] and "Dy Director AH" in out["animal_husbandry"]
    assert "| Action | Department | By when |" in out["collector"] and "| Action |" not in out["health"]
    for m in out.values():
        assert "## What to tell the public" in m and "## 3. Five pre-positioning actions" in m
        assert "## 1. Why this district is flagged" in m and "## Confidence and caveats" in m


def test_mock_output_differs_by_profile(client):
    def md(lang="en", **profile):
        return _adv(client, audience="farmer", language=lang, profile=profile).json()["markdown"]

    m1 = md(holding="marginal", water="rainfed", crop="Paddy")
    m2 = md(holding="medium_large", water="irrigated", crop="Paddy", livestock=True, tenant=True)
    assert _title(m1) != _title(m2)
    assert "marginal rainfed" in _title(m1) and "medium/large irrigated" in _title(m2)
    assert "Zero-cost" in m1 and "water budget" in m2 and "MGNREGA" in m1 and "MGNREGA" not in m2
    assert "Animals" in m2 and "Animals" not in m1
    assert "landowner" in m2 and "landowner" not in m1 and "PMFBY" in m1
    assert "SRI" in m1 or "short-duration" in m1.lower()
    assert "heat-tolerant" in md(crop="Wheat").lower() and "15 November" in md(crop="Wheat")
    h1, h2 = md("hi", holding="marginal", water="rainfed"), md("hi", holding="medium_large", water="irrigated")
    assert "सीमांत वर्षा-आधारित किसान के लिए" in _title(h1) and "मध्यम/बड़े सिंचित किसान के लिए" in _title(h2)
    assert len(h1.split()) < 220


def test_crop_playbook_matching():
    from api import personalize as pz

    key = lambda c: (pz.crop_playbook(c) or {}).get("key")  # noqa: E731
    assert key("Paddy") == "paddy" and key("Rice") == "paddy" and key("Cotton") == "cotton"
    assert key("Soyabean") == "soybean" and key("Maize") == "maize" and key("Groundnut") == "groundnut"
    assert key("Wheat") == "wheat" and key("Gram") == "gram" and key("Bengal Gram") == "gram"
    assert key("Green Gram") is None and key("Horse gram") is None and key("Arhar/Tur") == "tur"
    assert key("Jowar") == "millets" and key("other") is None and key("") is None


def test_prompt_contains_profile_and_department_blocks(client):
    from api import llm

    d = json.loads(json.dumps(data.district_by_lgd(486)))
    base_p, _ = llm.build_advisory_prompt(d, "farmer", "hi", "elnino")  # old signature still works
    assert "FARMER PROFILE" in base_p and "CROP ECONOMICS: not available" in base_p
    d["crops"]["economics"] = {"Paddy": {"cost_rs_ha": 52000, "value_rs_ha": 71000}}
    d["markets"] = {"price_elnino_spike_pct": 12.5, "price_series_json": "[1,2,3]"}
    d["groundwater"] = {"gw_stress_idx": 0.8}
    p, fields = llm.build_advisory_prompt(d, "farmer", "en", "elnino", {
        "holding": "marginal", "water": "rainfed", "crop": "Paddy", "livestock": True, "tenant": True})
    assert "marginal farmer" in p and "tenant" in p.lower() and "WBCIS" in p and "LIVESTOCK" in p
    assert "CROP PLAYBOOK for the main crop (Paddy" in p and "52000" in p
    assert any(f.startswith("crops.economics") for f in fields) and "markets.price_elnino_spike_pct" in fields
    assert "price_series_json" not in p and "groundwater.gw_stress_idx" in fields
    o, _ = llm.build_advisory_prompt(d, "official", "en", "elnino", None, "food_civil_supplies")
    assert "DEPARTMENT FOCUS: food_civil_supplies" in o and "DSO + FPS inspectors" in o
    assert "markets=PRESENT" in o and "nutrition.poshan_live=absent" in o and "FARMER PROFILE" not in o
    c, _ = llm.build_advisory_prompt(d, "official", "en", "elnino", None, "collector")
    assert "Cross-department timeline" in c
    # system prompts: audience-specific, profile + department rules present
    sf, so = llm.advisory_system("farmer"), llm.advisory_system("official")
    assert "220 words" in sf and "WBCIS" in sf and "15 November" in sf and "What to tell the public" in so
    assert "Dy Director AH" in so and "AUDIENCE = official" not in sf


def test_real_path_sends_profile_to_gemini_and_caches_separately(client, monkeypatch):
    from api import llm

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    seen: list[dict] = []

    class Models:
        def generate_content(self, model, contents, config):
            seen.append({"contents": contents, "system": config.system_instruction})
            return type("R", (), {"text": "## ok"})()

    monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"models": Models()})())
    r1 = _adv(client, audience="farmer", profile={"holding": "marginal", "tenant": True})
    r2 = _adv(client, audience="farmer", profile={"holding": "medium_large", "water": "irrigated"})
    r3 = _adv(client, audience="official", department="wcd_icds")
    assert [r.status_code for r in (r1, r2, r3)] == [200, 200, 200] and len(seen) == 3
    assert "marginal farmer" in seen[0]["contents"] and "medium/large" in seen[1]["contents"]
    assert "DEPARTMENT FOCUS: wcd_icds" in seen[2]["contents"] and "AUDIENCE = official" in seen[2]["system"]
    assert r1.json()["grounding"]["profile"]["tenant"] is True
    assert _adv(client, audience="farmer", profile={"holding": "marginal", "tenant": True}).json()["cached"] is True
    assert len(seen) == 3


def test_audio_accepts_profile(client, monkeypatch, tmp_path):
    from google.genai import types

    from api import llm

    prof = {"holding": "marginal", "water": "rainfed", "crop": "Paddy", "livestock": True, "tenant": False}
    r = client.post("/api/advisory/486/audio", json={"language": "hi", "scenario": "elnino", "profile": prof})
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    assert client.post("/api/advisory/486/audio", json={"profile": {"holding": "huge"}}).status_code == 422

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    seen = {"adv": [], "tts": []}

    class Models:
        def generate_content(self, model, contents, config):
            if config.response_modalities:
                seen["tts"].append(contents)
                part = types.Part(inline_data=types.Blob(data=b"\x01\x00" * 100, mime_type="audio/L16;rate=24000"))
                return type("R", (), {"candidates": [types.Candidate(content=types.Content(parts=[part]))]})()
            seen["adv"].append(contents)
            return type("R", (), {"text": "### T\n- profile-specific line"})()

    monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"models": Models()})())
    cache_dir = tmp_path / "artifacts" / "_audio_cache"
    body = {"language": "en", "scenario": "elnino", "profile": prof}
    assert client.post("/api/advisory/486/audio", json=body).headers["x-audio-cache"] == "miss"
    assert "marginal farmer" in seen["adv"][0] and "LIVESTOCK" in seen["adv"][0]
    assert client.post("/api/advisory/486/audio", json=body).headers["x-audio-cache"] == "hit"
    other = {**body, "profile": {**prof, "holding": "medium_large", "water": "irrigated"}}
    assert client.post("/api/advisory/486/audio", json=other).headers["x-audio-cache"] == "miss"
    assert len(seen["adv"]) == 2 and len(list(cache_dir.glob("486_en_elnino_*.wav"))) == 2
    # the audio narrates the same cached advisory the text endpoint serves for that profile
    assert _adv(client, audience="farmer", profile=prof).json()["cached"] is True


# ------------------------------------------------------------------ Addendum F: seasons
OUTLOOK = {
    "as_of": "2026-10-17",
    "seasons": [
        {"id": "rabi_2026_27", "label": "Rabi 2026-27", "sowing": "2026-10-15..2026-12-15",
         "harvest": "2027-03..2027-04", "status": "sowing_now"},
        {"id": "kharif_2027", "label": "Kharif 2027", "sowing": "2027-06..2027-07",
         "harvest": "2027-10..2027-11", "status": "upcoming"}],
    "enso": {"state": "El Niño", "p_by_season": {
        "rabi_2026_27": {"elnino": 1.0, "neutral": 0.0, "lanina": 0.0},
        "kharif_2027": {"elnino": 0.61, "neutral": 0.33, "lanina": 0.06}}},
    "default_scenario": {"rabi_2026_27": "elnino", "kharif_2027": "elnino"},
}


def _season_artifacts(tmp_path, legacy=True):
    """districts.json whose district 486 carries season-qualified risk keys (and optionally legacy aliases)."""
    d = json.loads(json.dumps(data.BUILTIN_DISTRICTS[0]))
    base = d["risk"]["elnino"]
    risk = {}
    for season, bump in (("rabi_2026_27", 5), ("kharif_2027", 0)):
        for phase, delta in (("lanina", -30), ("neutral", -45), ("elnino", 0), ("elnino_strong", 10)):
            e = json.loads(json.dumps(base))
            e["score"] = base["score"] + delta + bump
            e["actions"]["lead"] = {season: "by 2026-11-15"}
            risk[f"{season}:{phase}"] = e
    risk["rabi_2026_27:current"] = dict(risk["rabi_2026_27:elnino"], score=77)
    if legacy:
        risk.update({k: d["risk"][k] for k in ("neutral", "elnino", "elnino_strong")})
    d["risk"] = risk
    art = tmp_path / "artifacts"
    art.mkdir(exist_ok=True)
    (art / "districts.json").write_text(json.dumps([d]))
    kp = dict(data.BUILTIN_KPIS, outlook=OUTLOOK, by_season_scenario={"rabi_2026_27": {"elnino": {"n_high": 1}}})
    (art / "kpis.json").write_text(json.dumps(kp))
    return d


def test_scenario_validation_new_and_legacy_keys(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "LLM_WINDOWS", ((1000, 60),))   # this test makes >10 distinct cache misses
    monkeypatch.setattr(ratelimit, "GENERAL_BURST", 1000)          # ... and >40 requests
    ok = ["neutral", "elnino", "elnino_strong", "kharif_2027:elnino", "rabi_2026_27:current",
          "rabi_2026_27:neutral", "kharif_2027:elnino_strong", "kharif_2027:neutral"]
    for sc in ok:
        r = client.post("/api/advisory/486", json={"scenario": sc})
        assert r.status_code == 200, (sc, r.text)  # falls back to the legacy alias on mock data
        assert client.get("/api/actions", params={"scenario": sc}).status_code == 200, sc
        assert client.post("/api/chat", json={"messages": [{"role": "user", "content": "top risk?"}],
                                              "scenario": sc}).status_code == 200, sc
    # valid key but no data for it (legacy data has no La Nina entry and no alias for it) -> 404, not 422/500
    r = client.post("/api/advisory/486", json={"scenario": "kharif_2027:lanina"})
    assert r.status_code == 404 and "no risk entry" in r.json()["error"]
    assert client.get("/api/actions", params={"scenario": "kharif_2027:lanina"}).json()["rows"] == []
    for bad in ["bogus", "kharif:elnino", "winter_2026:elnino", "rabi_2026_27:hot", "rabi_2026_27:", ":elnino",
                "rabi_26_27:elnino", "Rabi_2026_27:elnino", "elnino:rabi_2026_27"]:
        assert client.post("/api/advisory/486", json={"scenario": bad}).status_code == 422, bad
        assert client.get("/api/actions", params={"scenario": bad}).status_code == 422, bad
        assert client.post("/api/advisory/486/audio", json={"scenario": bad}).status_code == 422, bad
        assert client.post("/api/state_brief", json={"state": "Maharashtra", "scenario": bad}).status_code == 422, bad
        assert client.post("/api/chat", json={"messages": [{"role": "user", "content": "x"}],
                                              "scenario": bad}).status_code == 422, bad


def test_new_keys_resolve_to_district_risk_entry(client, tmp_path):
    _season_artifacts(tmp_path)
    d = data.district_by_lgd(486)
    base = d["risk"]["kharif_2027:elnino"]["score"]
    j = client.post("/api/advisory/486", json={"scenario": "rabi_2026_27:lanina"}).json()
    g = j["grounding"]
    assert g["resolved_scenario"] == "rabi_2026_27:lanina" and g["season"] == "rabi_2026_27"
    assert "risk.rabi_2026_27:lanina.score" in g["fields_used"]
    assert str(d["risk"]["rabi_2026_27:lanina"]["score"]) in j["markdown"]
    assert "Rabi 2026-27" in j["markdown"]  # mock output names the season
    # `current` missing a key for kharif resolves via default phase; unknown-everything gives a 404-style error
    g = client.post("/api/advisory/486", json={"scenario": "kharif_2027:current"}).json()["grounding"]
    assert g["resolved_scenario"] == "kharif_2027:elnino"
    d2 = json.loads((tmp_path / "artifacts" / "districts.json").read_text())
    d2[0]["risk"] = {}
    (tmp_path / "artifacts" / "districts.json").write_text(json.dumps(d2))
    r = client.post("/api/advisory/486", json={"scenario": "rabi_2026_27:elnino"})
    assert r.status_code == 404 and "no risk entry" in r.json()["error"]
    assert client.post("/api/advisory/486/audio", json={"scenario": "elnino"}).status_code == 404
    assert base is not None


def test_legacy_alias_resolution(client, tmp_path):
    # legacy key on legacy data: exact
    d = data.district_by_lgd(486)
    assert client.post("/api/advisory/486", json={"scenario": "elnino"}).json()["grounding"]["resolved_scenario"] == "elnino"
    # season key on legacy-only data: alias of the phase
    g = client.post("/api/advisory/486", json={"scenario": "rabi_2026_27:elnino"}).json()["grounding"]
    assert g["resolved_scenario"] == "elnino" and "risk.elnino.score" in g["fields_used"]
    # legacy key on season-only data: alias of the default kharif season
    _season_artifacts(tmp_path, legacy=False)
    advisory_cache._mem.clear()
    g = client.post("/api/advisory/486", json={"scenario": "elnino"}).json()["grounding"]
    assert g["resolved_scenario"] == "kharif_2027:elnino"
    assert d["risk"]["elnino"]["score"] is not None


def test_actions_csv_naming_and_fallback(client, tmp_path):
    art = _season_artifacts(tmp_path)  # noqa: F841
    j = client.get("/api/actions?scenario=rabi_2026_27:elnino").json()
    assert j["n"] == 1 and j["season"] == "rabi_2026_27" and j["rows"][0]["lgd"] == 486
    assert j["rows"][0]["lead_rabi_2026_27"] == "by 2026-11-15"        # derived from districts.json
    assert client.get("/api/actions?scenario=rabi_2026_27:lanina").json()["rows"][0]["score"] == \
        data.district_by_lgd(486)["risk"]["rabi_2026_27:lanina"]["score"]
    r = client.get("/api/actions?scenario=rabi_2026_27:elnino&format=csv")
    assert 'filename="actions_rabi_2026_27_elnino.csv"' in r.headers["content-disposition"]
    # actions_<season>_<phase>.csv wins when present
    (tmp_path / "artifacts" / "actions_rabi_2026_27_elnino.csv").write_text(
        "state,district,lgd,score,band,grain_preposition_t\nX,FromCsv,1,90,high,7\n")
    j = client.get("/api/actions?scenario=rabi_2026_27:elnino").json()
    assert j["rows"][0]["district"] == "FromCsv" and j["actions_total"]["grain_preposition_t"] == 7
    # other phase has no CSV -> still derived; legacy csv name is unaffected
    assert client.get("/api/actions?scenario=rabi_2026_27:neutral").json()["rows"][0]["district"] != "FromCsv"
    (tmp_path / "artifacts" / "actions_elnino.csv").write_text("state,district,lgd,score,band\nL,Legacy,2,50,medium\n")
    assert client.get("/api/actions?scenario=elnino").json()["rows"][0]["district"] == "Legacy"
    assert client.get("/api/actions?scenario=kharif_2027:elnino").json()["rows"][0]["district"] == "Nandurbar"
    from api import actions as am
    assert am.csv_path("rabi_2026_27:current").name == "actions_rabi_2026_27_current.csv"


def test_season_context_in_prompt(client, tmp_path):
    from api import llm

    _season_artifacts(tmp_path)
    d = data.district_by_lgd(486)
    p, _ = llm.build_advisory_prompt(d, "official", "en", "rabi_2026_27:elnino", None, "agriculture")
    assert "SEASON CONTEXT" in p and "Rabi 2026-27" in p and "2026-10-15..2026-12-15" in p
    assert "sowing window is open NOW" in p and "El Niño 100%" in p
    assert "DEFICIT / HEAT" in p and "terminal heat" in p
    assert "Timely-sowing campaign" in p and "heat-tolerant" in p     # rabi agriculture menu
    assert "Focus the risk narrative on risk.rabi_2026_27:elnino" in p
    # La Nina = flood framing + phase adaptation; kharif upcoming; probabilities from outlook
    p, _ = llm.build_advisory_prompt(d, "official", "en", "kharif_2027:lanina", None, "agriculture")
    assert "EXCESS-RAIN / FLOOD" in p and "upcoming season" in p and "La Niña 6%" in p
    assert "PHASE ADAPTATION (La Nina)" in p and "Timely-sowing campaign" not in p
    # neutral = climatology / structural
    p, _ = llm.build_advisory_prompt(d, "official", "en", "kharif_2027:neutral", None, "collector")
    assert "CLIMATOLOGY framing" in p and "STRUCTURAL" in p and "PHASE ADAPTATION (Neutral)" in p
    # legacy key still carries a season block (default kharif) ; fallback caveat when data come from an alias
    p, _ = llm.build_advisory_prompt(d, "farmer", "en", "elnino")
    assert "Kharif 2027" in p and "legacy key" in p
    legacy = data.BUILTIN_DISTRICTS[0]
    p, _ = llm.build_advisory_prompt(legacy, "official", "en", "rabi_2026_27:neutral", None, "collector")
    assert "DATA CAVEAT" in p and "risk.neutral" in p
    # real path sends it to Gemini; separate cache entries per season key
    import os
    os.environ["MOCK_LLM"] = "0"
    os.environ["GEMINI_API_KEY"] = "fake"
    seen = []

    class Models:
        def generate_content(self, model, contents, config):
            seen.append(contents)
            return type("R", (), {"text": "## ok"})()

    orig = llm.get_client
    llm.get_client = lambda: type("C", (), {"models": Models()})()
    try:
        a = client.post("/api/advisory/486", json={"scenario": "rabi_2026_27:elnino"}).json()
        b = client.post("/api/advisory/486", json={"scenario": "kharif_2027:elnino"}).json()
        c = client.post("/api/advisory/486", json={"scenario": "rabi_2026_27:elnino"}).json()
    finally:
        llm.get_client = orig
        os.environ["MOCK_LLM"] = "1"
        os.environ.pop("GEMINI_API_KEY", None)
    assert (a["cached"], b["cached"], c["cached"]) == (False, False, True) and len(seen) == 2
    assert "Rabi 2026-27" in seen[0] and "Kharif 2027" in seen[1]


def test_season_context_without_outlook(client):
    from api import seasons

    c = seasons.season_context("rabi_2026_27:lanina", {})
    assert c["label"] == "Rabi 2026-27" and c["is_lanina"] and c["status"] == "sowing_now"
    c = seasons.season_context("kharif_2028:current", None)
    assert c["label"] == "Kharif 2028" and c["enso_probabilities"] is None
    assert "not available" in seasons.season_block(c)


def test_rabi_and_lanina_playbook(client):
    from api import llm, personalize as pz

    w = pz.crop_playbook("Wheat", "rabi", "elnino")["advice"]
    assert "15 November" in w and "heat-tolerant" in w and "crown-root" in w and "grain filling" in w
    assert "heat-tolerant" not in pz.crop_playbook("Wheat", "rabi", "lanina")["advice"]
    assert pz.crop_playbook("Wheat")["key"] == "wheat"                       # old signature intact
    assert "moisture" in pz.crop_playbook("Gram", "rabi", "neutral")["advice"].lower()
    m = pz.crop_playbook("Mustard", "rabi", "elnino")
    assert m and m["key"] == "mustard" and "moisture" in m["advice"] and "early" in m["advice"].lower()
    assert pz.crop_playbook("Rapeseed & Mustard")["key"] == "mustard"
    assert "groundwater budget" in pz.crop_playbook("Rice", "rabi", "elnino")["advice"]
    assert "groundwater budget" not in pz.crop_playbook("Rice", "kharif", "elnino")["advice"]
    k = pz.crop_playbook("Paddy", "kharif", "lanina")["advice"]
    assert "Swarna-Sub1" in k and "drain" in k and "delay sowing" in k and "short-duration pulses" in k
    assert "drain" in pz.crop_playbook("Cotton", "kharif", "lanina")["advice"]
    assert "drain" not in pz.crop_playbook("Cotton", "kharif", "elnino")["advice"]
    assert "Swarna-Sub1" in llm.advisory_system("farmer") and "mustard" in llm.advisory_system("farmer").lower()
    # rabi department menus exist for the four named departments, and differ from kharif
    for dept, needle in (("food_civil_supplies", "wheat procurement"), ("agriculture", "Timely-sowing"),
                         ("rural_development", "Irrigation works"), ("animal_husbandry", "rabi straw")):
        assert needle.lower() in str(pz.dept_menu(dept, "rabi")).lower()
        assert pz.dept_menu(dept, "kharif") == pz.DEPT_CATALOG[dept]["menu"] and pz.dept_menu(dept) == pz.dept_menu(dept, "kharif")
    assert pz.dept_menu("health", "rabi") == pz.DEPT_CATALOG["health"]["menu"]
    # a rabi farmer advisory (mock) picks the rabi playbook
    r = client.post("/api/advisory/486", json={"audience": "farmer", "scenario": "rabi_2026_27:elnino",
                                               "profile": {"crop": "Wheat"}}).json()["markdown"]
    assert "Rabi 2026-27" in r and "15 November" in r
    r = client.post("/api/advisory/486", json={"audience": "official", "scenario": "rabi_2026_27:elnino",
                                               "department": "food_civil_supplies"}).json()["markdown"]
    assert "wheat procurement" in r.lower() and "Rabi 2026-27" in r


def test_tools_with_season_keys(client, tmp_path):
    _season_artifacts(tmp_path)
    d = data.district_by_lgd(486)
    r = tools.rank_districts("risk_score", "rabi_2026_27:lanina", None, 3)
    assert r["scenario"] == "rabi_2026_27:lanina" and r["season"] == "Rabi 2026-27"
    assert r["results"][0]["value"] == d["risk"]["rabi_2026_27:lanina"]["score"]
    assert tools.rank_districts("risk_score", "rabi_2026_27:current")["results"][0]["value"] == 77
    bad = tools.rank_districts("risk_score", "nonsense")
    assert bad["scenario"] == "elnino" and "invalid scenario" in bad["note"]
    cmp = tools.compare_scenarios("486")
    assert set(cmp["by_season"]) == {"rabi_2026_27", "kharif_2027"}
    assert list(cmp["by_season"]["rabi_2026_27"]["phases"])[:4] == ["lanina", "neutral", "elnino", "elnino_strong"]
    assert "current" in cmp["by_season"]["rabi_2026_27"]["phases"]
    assert cmp["by_season"]["kharif_2027"]["label"] == "Kharif 2027"
    assert cmp["by_season"]["rabi_2026_27"]["delta_elnino_vs_neutral"] == 45
    assert "kharif_2027:elnino" in cmp["scenarios"] and "elnino" in cmp["scenarios"]  # flat view keeps aliases
    assert cmp["delta_elnino_vs_neutral"] == 47                                       # legacy delta unchanged
    ns = tools.national_summary()
    assert ns["by_season_scenario"] == {"rabi_2026_27": {"elnino": {"n_high": 1}}}
    assert ns["bands"]["rabi_2026_27:lanina"] and ns["outlook"]["seasons"][0]["id"] == "rabi_2026_27"
    ctx = tools.district_context(d, "rabi_2026_27:lanina")[0]
    assert "actions" in ctx["risk"]["rabi_2026_27:lanina"] and "actions" not in ctx["risk"]["rabi_2026_27:elnino"]
    assert all(k.startswith("rabi_2026_27") for k in ctx["risk"])
    assert tools.get_district(486, "kharif_2027:neutral")["risk"]["kharif_2027:neutral"]["score"]
    # season-only data: chat tool shape without a scenario still works (every key sent)
    only = json.loads((tmp_path / "artifacts" / "districts.json").read_text())
    for k in ("neutral", "elnino", "elnino_strong"):
        only[0]["risk"].pop(k)
    (tmp_path / "artifacts" / "districts.json").write_text(json.dumps(only))
    assert tools.rank_districts("risk_score", "elnino", None, 1)["results"][0]["value"] == \
        d["risk"]["kharif_2027:elnino"]["score"]
    assert "kharif_2027:elnino" in tools.get_district(486)["risk"]


def test_state_brief_and_chat_with_season_key(client):
    r = client.post("/api/state_brief", json={"state": "Maharashtra", "scenario": "rabi_2026_27:elnino"})
    assert r.status_code == 200 and "Rabi 2026-27" in r.json()["markdown"]
    assert r.json()["grounding"]["season"] == "rabi_2026_27"
    c = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Tell me about Nandurbar"}],
                                       "scenario": "kharif_2027:lanina"}).json()
    assert 486 in c["citations"]


def test_history_endpoints(client, tmp_path):
    hist = tmp_path / "artifacts" / "history"
    hist.mkdir(parents=True)
    enso = {"phase": "El Niño", "oni_jja_son": 1.9, "all_india_jjas_anom_pct": -13.6, "headline": "Deficit monsoon"}
    (hist / "index.json").write_text(json.dumps({"years": [2015], "enso": {"2015": enso}}))
    (hist / "2015.json").write_text(json.dumps({"year": 2015, "enso": enso, "districts": {"486": {"tool_band": "high", "warned": True}}}))
    idx = client.get("/api/history")
    assert idx.status_code == 200 and idx.json()["years"] == [2015]
    y = client.get("/api/history/2015")
    assert y.status_code == 200 and y.json()["districts"]["486"]["warned"] is True
    # mtime-aware reload: rewriting the file is picked up
    (hist / "2015.json").write_text(json.dumps({"year": 2015, "enso": enso, "districts": {}}))
    import os
    st = (hist / "2015.json").stat()
    os.utime(hist / "2015.json", (st.st_atime, st.st_mtime + 5))
    assert client.get("/api/history/2015").json()["districts"] == {}


def test_history_missing_404(client):
    r = client.get("/api/history/1999")
    assert r.status_code == 404 and "error" in r.json()
    assert client.get("/api/history").status_code == 404
    assert client.get("/api/history/abc").status_code == 422


# ------------------------------------------------------------------ abuse protection (api/ratelimit.py)
def _miss(client, i, **kw):
    """i-th distinct advisory request: every one is a cache miss."""
    langs = ["en", "hi", "mr", "te", "bn", "ta", "kn", "gu", "or"]
    return client.post("/api/advisory/486", json={"audience": "farmer", "language": langs[i % 9],
                                                  "scenario": "elnino", "profile": {"crop": f"c{i // 9}"}}, **kw)


def test_per_ip_llm_limit_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "LLM_WINDOWS", ((3, 60), (60, 3600)))
    assert [_miss(client, i).status_code for i in range(3)] == [200, 200, 200]
    r = _miss(client, 3)
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limited" and r.json()["retry_after_s"] >= 1
    assert int(r.headers["retry-after"]) == r.json()["retry_after_s"]
    # another IP is unaffected
    assert _miss(client, 4, headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 200
    # general token bucket: burst then 429
    monkeypatch.setattr(ratelimit, "GENERAL_BURST", 5)
    ratelimit.limiter.reset()
    codes = [client.get("/api/kpis").status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_cache_hit_does_not_consume_llm_tokens(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "LLM_WINDOWS", ((2, 60), (60, 3600)))
    assert _miss(client, 0).json()["cached"] is False
    for _ in range(10):
        r = _miss(client, 0)
        assert r.status_code == 200 and r.json()["cached"] is True
    assert ratelimit.limiter.snapshot()["llm_calls_today"] == 1
    assert _miss(client, 1).status_code == 200      # 2nd and last token still available
    assert _miss(client, 2).status_code == 429


def test_budget_breaker_503_and_cache_fallback(client, monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CAP", "2")
    assert _miss(client, 0).status_code == 200 and _miss(client, 1).status_code == 200
    r = _miss(client, 2)
    assert r.status_code == 503
    assert r.json() == {"error": "budget_reached",
                        "message": "Daily AI budget reached; cached advisories still available."}
    assert _miss(client, 0).json()["cached"] is True                       # cache still served
    assert client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 503
    h = client.get("/api/health").json()
    assert h["llm_calls_today"] == 2 and h["tts_calls_today"] == 0 and h["caps"]["llm_daily"] == 2
    # counters reset at UTC midnight
    monkeypatch.setattr(ratelimit, "_time", lambda: __import__("time").time() + 86400)
    assert client.get("/api/health").json()["llm_calls_today"] == 0


def test_tts_and_per_minute_caps(client, monkeypatch):
    monkeypatch.setenv("TTS_DAILY_CAP", "1")
    assert client.post("/api/advisory/486/audio", json={"language": "hi"}).status_code == 200
    assert client.post("/api/advisory/486/audio", json={"language": "hi"}).status_code == 503
    assert client.get("/api/health").json()["tts_calls_today"] == 1
    monkeypatch.setenv("LLM_PER_MIN_CAP", "1")
    assert _miss(client, 0).status_code == 200
    r = _miss(client, 1)
    assert r.status_code == 503 and r.json()["error"] == "budget_reached" and "retry-after" in r.headers


def test_audio_per_ip_limit(client):
    codes = [client.post("/api/advisory/486/audio", json={"language": "hi"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_chat_size_caps_413(client):
    def post(msgs):
        return client.post("/api/chat", json={"messages": msgs})

    u = {"role": "user", "content": "hi"}
    assert post([u] * 13).status_code == 413
    assert post([{"role": "user", "content": "x" * 2001}]).status_code == 413
    assert post([{"role": "user", "content": "x" * 1500}] * 9).status_code == 413     # 13 500 total
    assert post([{"role": "assistant", "content": "x"}, u] * 6).status_code == 200    # 12 msgs: boundary ok
    r = client.post("/api/chat", content=b"{" + b" " * 70_000 + b"}", headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"] == "payload_too_large"
    # chunked body without Content-Length is capped too
    r = client.post("/api/chat", content=(b"x" * 20_000 for _ in range(5)), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert client.post("/api/advisory/486", json={"scenario": "elnino" + "x" * 60}).status_code == 422


def test_security_headers_and_robots(client):
    for path in ("/api/health", "/api/nope", "/robots.txt"):
        h = client.get(path).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "strict-origin-when-cross-origin"
        assert h["permissions-policy"] == "geolocation=(self)"
        csp = h["content-security-policy"]
        assert "default-src 'self'" in csp and "https://fonts.gstatic.com" in csp and "basemaps.cartocdn.com" in csp
        assert "frame-ancestors 'none'" in csp
    r = client.get("/robots.txt")
    assert r.text == "User-agent: *\nDisallow: /api/\n" and r.headers["content-type"].startswith("text/plain")


def test_bypass_token(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "LLM_WINDOWS", ((1, 60), (60, 3600)))
    monkeypatch.setenv("RATE_LIMIT_BYPASS_TOKEN", "s3cret")
    assert _miss(client, 0).status_code == 200 and _miss(client, 1).status_code == 429
    assert _miss(client, 2, headers={"X-Admin-Token": "wrong"}).status_code == 429
    assert [_miss(client, i, headers={"X-Admin-Token": "s3cret"}).status_code for i in range(3, 8)] == [200] * 5
    monkeypatch.delenv("RATE_LIMIT_BYPASS_TOKEN")   # unset token never matches an empty/any header
    assert _miss(client, 8, headers={"X-Admin-Token": ""}).status_code == 429


def test_x_forwarded_for_parsing(client, monkeypatch):
    from starlette.requests import Request

    def ip(xff=None, peer=("10.0.0.1", 1)):
        hdrs = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
        return ratelimit.client_ip(Request({"type": "http", "headers": hdrs, "client": peer}))

    assert ip("198.51.100.7, 35.191.0.1") == "198.51.100.7"          # first value
    assert ip("  2001:db8::1 ,35.191.0.1") == "2001:db8::1"
    assert ip("not-an-ip, 1.2.3.4") == "10.0.0.1"                    # garbage -> socket peer
    assert ip(None) == "10.0.0.1" and ip("") == "10.0.0.1"
    monkeypatch.setenv("XFF_POSITION", "last")
    assert ip("198.51.100.7, 35.191.0.1") == "35.191.0.1"
    monkeypatch.delenv("XFF_POSITION")
    # limits are keyed on that IP
    monkeypatch.setattr(ratelimit, "GENERAL_BURST", 2)
    h = {"X-Forwarded-For": "198.51.100.7, 35.191.0.1"}
    assert [client.get("/api/kpis", headers=h).status_code for _ in range(3)] == [200, 200, 429]
    assert client.get("/api/kpis", headers={"X-Forwarded-For": "198.51.100.8"}).status_code == 200


def test_limiter_prunes_stale_entries(client, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(ratelimit, "_time", lambda: now[0])
    ratelimit.limiter.reset()
    for i in range(50):
        ratelimit.limiter.check_general(f"1.1.1.{i}")
        ratelimit.limiter.acquire("tts", ratelimit.Caller(f"1.1.1.{i}", False))
    now[0] += 4000
    ratelimit.limiter.check_general("9.9.9.9")
    assert len(ratelimit.limiter._buckets) == 1 and not ratelimit.limiter._logs
