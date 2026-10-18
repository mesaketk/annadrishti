"""AnnaDrishti API: serves artifacts, Gemini advisories + chat, and the built frontend.

Run from project root:  uvicorn api.main:app --reload --port 8080
"""
from __future__ import annotations

import logging
import mimetypes
import contextvars
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import orjson
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi import Query
from fastapi.responses import FileResponse, JSONResponse, ORJSONResponse, Response
from pydantic import AfterValidator, BaseModel, Field, StringConstraints, ValidationError

from . import actions as actions_mod
from . import config, data, llm, personalize, ratelimit, seasons, tools

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("annadrishti.api")

# legacy neutral|elnino|elnino_strong, or "<kharif|rabi>_<year>[_yy]:<lanina|neutral|elnino|elnino_strong|current>"
Scenario = Annotated[str, StringConstraints(max_length=48), AfterValidator(seasons.validate)]
Language = Literal["en", "hi", "mr", "te", "bn", "ta", "kn", "gu", "or"]
Holding = Literal["marginal", "small", "medium_large"]
Water = Literal["rainfed", "partial", "irrigated"]
Department = Literal["collector", "food_civil_supplies", "agriculture", "wcd_icds", "rural_development",
                     "health", "animal_husbandry"]


# ------------------------------------------------------------------ advisory cache
class AdvisoryCache:
    """In-memory cache persisted to ARTIFACTS_DIR/_advisory_cache.json. Mock responses are never persisted."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mem: dict[str, dict] = {}
        self._loaded_from: Path | None = None

    @staticmethod
    def key(lgd: int, audience: str, language: str, scenario: str, model: str, variant: str = "") -> str:
        # `model` stays last: persistence skips keys whose last segment starts with "mock"
        return f"{lgd}|{audience}|{language}|{scenario}|{variant}|{model}"

    def _path(self) -> Path:
        return config.artifacts_dir() / "_advisory_cache.json"

    def _ensure_loaded(self) -> None:
        p = self._path()
        if self._loaded_from == p:
            return
        self._loaded_from = p
        if p.is_file():
            try:
                self._mem.update(orjson.loads(p.read_bytes()))
            except Exception:
                log.exception("could not read advisory cache %s", p)

    def get(self, k: str) -> dict | None:
        with self._lock:
            self._ensure_loaded()
            return self._mem.get(k)

    def put(self, k: str, value: dict, persist: bool) -> None:
        with self._lock:
            self._ensure_loaded()
            self._mem[k] = value
            if not persist:
                return
            p = self._path()
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                persisted = {kk: vv for kk, vv in self._mem.items() if not kk.split("|")[-1].startswith("mock")}
                tmp = p.with_suffix(".json.tmp")
                tmp.write_bytes(orjson.dumps(persisted))
                tmp.replace(p)
            except Exception:
                log.exception("could not persist advisory cache")


advisory_cache = AdvisoryCache()


# ------------------------------------------------------------------ app
@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        data.sync_from_gcs()
    except Exception:
        log.exception("ARTIFACTS_GCS_URI sync failed; continuing with local artifacts")
    d, mock = data.get_districts()
    log.info("districts loaded: %d (%s); llm=%s", len(d), "MOCK" if mock else "real", llm.effective_model())
    yield


app = FastAPI(title="AnnaDrishti API", version="0.1.0", default_response_class=ORJSONResponse,
              lifespan=lifespan)
# Stack, innermost first: body cap -> abuse guard (general rate limit + security headers) -> gzip -> CORS -> data-mode.
app.add_middleware(ratelimit.BodyLimitMiddleware)


@app.middleware("http")
async def abuse_guard(request: Request, call_next):
    path = request.url.path
    response = None
    if (path == "/api" or path.startswith("/api/")) and request.method != "OPTIONS":
        who = ratelimit.caller(request)
        if not who.bypass:
            try:
                ratelimit.limiter.check_general(who.ip)
            except ratelimit.RateLimited as e:
                response = ratelimit.rate_limited_response(e)
    if response is None:
        response = await call_next(request)
    for k, v in ratelimit.SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Data-Mode", "Retry-After"])


@app.middleware("http")
async def data_mode_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        try:
            response.headers["X-Data-Mode"] = "mock" if data.get_districts()[1] else "real"
        except Exception:
            pass
    return response


@app.exception_handler(llm.LLMUnavailable)
async def _llm_unavailable(_: Request, exc: llm.LLMUnavailable):
    return JSONResponse(status_code=503, content={"error": str(exc)})


@app.exception_handler(ratelimit.RateLimited)
async def _rate_limited(_: Request, exc: ratelimit.RateLimited):
    return ratelimit.rate_limited_response(exc)


@app.exception_handler(ratelimit.BudgetReached)
async def _budget_reached(_: Request, exc: ratelimit.BudgetReached):
    return ratelimit.budget_response(exc)


def _llm_failure(e: Exception) -> HTTPException:
    log.exception("Gemini call failed")
    return HTTPException(status_code=502, detail={"error": f"Gemini request failed: {type(e).__name__}: {e}"})


@app.exception_handler(HTTPException)
async def _http_exc(_: Request, exc: HTTPException):
    detail = exc.detail
    content = detail if isinstance(detail, dict) and "error" in detail else {"error": detail}
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


# ------------------------------------------------------------------ data endpoints
@app.get("/api/health")
def health():
    districts, mock = data.get_districts()
    return {"status": "ok", "data_mode": "mock" if mock else "real", "n_districts": len(districts),
            **ratelimit.limiter.snapshot(),
            "llm": {"ready": llm.llm_ready(), "mock": config.mock_llm(), "model": llm.effective_model(),
                    "backend": "vertex-ai" if config.use_vertex() else "gemini-api" if config.env("GEMINI_API_KEY")
                    else "vertex" if config.use_vertex() else "none"}}


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return Response("User-agent: *\nDisallow: /api/\n", media_type="text/plain")


@app.get("/api/districts")
def districts():
    return data.get_districts()[0]


@app.get("/api/kpis")
def kpis():
    return data.get_kpis()[0]


@app.get("/api/timeseries/{lgd}")
def timeseries(lgd: int):
    ts, _ = data.get_timeseries(lgd)
    if ts is None:
        raise HTTPException(status_code=404, detail=f"no timeseries for lgd {lgd}")
    return ts


@app.get("/api/history")
def history_index():
    """History mode: years + per-year all-India ENSO / monsoon / harvest headline (docs/SCHEMA.md Addendum H)."""
    idx = data.get_history_index()
    if idx is None:
        raise HTTPException(status_code=404, detail="history artifacts not built (run pipeline/06b_history.py)")
    return idx


@app.get("/api/history/{year}")
def history_year(year: int):
    obj = data.get_history_year(year)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"no history for year {year}")
    return obj


# ------------------------------------------------------------------ Gemini endpoints
class FarmerProfile(BaseModel):
    """Farmer profile (docs/SCHEMA.md Addendum C). All optional; crop defaults to the district's top crop."""
    holding: Holding = personalize.DEFAULT_HOLDING
    water: Water = personalize.DEFAULT_WATER
    crop: str | None = Field(default=None, max_length=40, pattern=r"^[\w][\w ()/&.,'-]*$")
    livestock: bool = False
    tenant: bool = False


class AdvisoryRequest(BaseModel):
    audience: Literal["official", "farmer"] = "official"
    language: Language = "en"
    scenario: Scenario = "elnino"
    profile: FarmerProfile | None = None      # used when audience == "farmer"
    department: Department = personalize.DEFAULT_DEPARTMENT  # used when audience == "official"


def _resolve_scenario(d: dict, scenario: str) -> str:
    """The risk key this district actually has for `scenario` (exact, else alias); 404-style error if none."""
    entry, key = seasons.resolve_risk(d, scenario, data.get_kpis()[0])
    if entry is None or key is None:
        raise HTTPException(status_code=404, detail=f"district {d.get('lgd')} has no risk entry for scenario "
                                                    f"{scenario!r} (available: {seasons.risk_keys(d)})")
    return key


def _get_advisory(lgd: int, audience: str, language: str, scenario: str,
                  profile: FarmerProfile | None = None, department: str | None = None,
                  who: ratelimit.Caller | None = None) -> dict:
    d = data.district_by_lgd(lgd)
    if d is None:
        raise HTTPException(status_code=404, detail=f"unknown district lgd {lgd}")
    resolved = _resolve_scenario(d, scenario)
    # normalise: only the field that applies to the audience takes part in the cache key / prompt / grounding
    kind = seasons.season_kind_of(scenario, data.get_kpis()[0])
    prof = personalize.resolve_profile(profile.model_dump() if profile else None, d, kind) \
        if audience == "farmer" else None
    dept = (department or personalize.DEFAULT_DEPARTMENT) if audience == "official" else None
    model = llm.effective_model()
    key = advisory_cache.key(lgd, audience, language, scenario, model, personalize.variant_for(audience, prof, dept))
    hit = advisory_cache.get(key)
    if hit:
        return {**hit, "cached": True}
    if not llm.llm_ready():
        raise llm.LLMUnavailable("GEMINI_API_KEY not set")
    ratelimit.limiter.acquire("llm", who or ratelimit.Caller("internal", True))  # cache miss: per-IP + budget
    try:
        markdown, fields, used_model = llm.generate_advisory(d, audience, language, scenario, prof, dept)
    except llm.LLMUnavailable:
        raise
    except Exception as e:
        raise _llm_failure(e)
    out = {"markdown": markdown, "model": used_model,
           "grounding": {"lgd": lgd, "district": d.get("district"), "fields_used": fields,
                         "scenario": scenario, "resolved_scenario": resolved,
                         "season": seasons.season_context(scenario, data.get_kpis()[0], resolved)["season"],
                         "profile": prof, "department": dept},
           "cached": False}
    advisory_cache.put(key, out, persist=not config.mock_llm())
    return out


@app.post("/api/advisory/{lgd}")
def advisory(lgd: int, body: AdvisoryRequest, request: Request):
    return _get_advisory(lgd, body.audience, body.language, body.scenario, body.profile, body.department,
                         ratelimit.caller(request))


class AudioRequest(BaseModel):
    language: Language = "en"
    scenario: Scenario = "elnino"
    profile: FarmerProfile | None = None


@app.post("/api/advisory/{lgd}/audio")
def advisory_audio(lgd: int, body: AudioRequest, request: Request):
    """WAV narration of the (cached) farmer advisory for this profile via Gemini TTS."""
    d = data.district_by_lgd(lgd)
    if d is None:
        raise HTTPException(status_code=404, detail=f"unknown district lgd {lgd}")
    _resolve_scenario(d, body.scenario)
    who = ratelimit.caller(request)
    if config.mock_llm():
        ratelimit.limiter.acquire("tts", who)
        return Response(llm.silent_wav(1.0), media_type="audio/wav", headers={"X-Audio-Mode": "mock"})
    # no profile -> legacy file name (backward compatible); with a profile the file is keyed by its resolved variant
    suffix = "" if body.profile is None else "_" + personalize.variant_slug(personalize.profile_variant(
        personalize.resolve_profile(body.profile.model_dump(), d,
                                    seasons.season_kind_of(body.scenario, data.get_kpis()[0]))))
    path = config.artifacts_dir() / "_audio_cache" / f"{lgd}_{body.language}_{seasons.slug(body.scenario)}{suffix}.wav"
    if path.is_file():
        return Response(path.read_bytes(), media_type="audio/wav", headers={"X-Audio-Cache": "hit"})
    if not llm.llm_ready():
        raise llm.LLMUnavailable("GEMINI_API_KEY not set")
    adv = _get_advisory(lgd, "farmer", body.language, body.scenario, body.profile, who=who)  # llm token on miss only
    ratelimit.limiter.acquire("tts", who)  # audio file cache miss
    text = llm.strip_markdown(adv["markdown"])
    try:
        wav = llm.synthesize_speech(text)
    except llm.LLMUnavailable:
        raise
    except Exception as e:
        raise _llm_failure(e)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".wav.tmp")
        tmp.write_bytes(wav)
        tmp.replace(path)
    except Exception:
        log.exception("could not cache audio")
    return Response(wav, media_type="audio/wav", headers={"X-Audio-Cache": "miss"})


# ------------------------------------------------------------------ actions + state brief
@app.get("/api/actions")
def actions(scenario: Scenario = "elnino", state: str | None = None, band: Literal["low", "medium", "high"] | None = None,
            format: Literal["json", "csv"] = "json"):
    rows = actions_mod.get_rows(scenario, state, band)
    if format == "csv":
        return Response(actions_mod.to_csv(rows), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="actions_{seasons.slug(scenario)}.csv"'})
    return {"scenario": scenario, "season": seasons.season_context(scenario, data.get_kpis()[0])["season"],
            "state": state, "band": band, "n": len(rows),
            "actions_total": actions_mod.actions_total(scenario, rows, bool(state or band)), "rows": rows}


class StateBriefRequest(BaseModel):
    state: str | None = Field(default=None, max_length=80)  # required, checked in the handler for a clear 422
    scenario: Scenario = "elnino"


@app.post("/api/state_brief")
def state_brief(body: StateBriefRequest, request: Request):
    if not body.state or not body.state.strip():
        raise HTTPException(status_code=422, detail="state is required: choose a state to generate the state brief")
    body.state = body.state.strip()
    rows = actions_mod.get_rows(body.scenario, body.state)
    if not rows:
        raise HTTPException(status_code=404, detail=f"no action rows for state {body.state!r} in scenario {body.scenario}")
    state = str(rows[0]["state"])
    totals = actions_mod.totals(rows)
    model = llm.effective_model()
    key = f"brief|{state}|{body.scenario}|{personalize.PROMPT_VERSION}|{model}"
    hit = advisory_cache.get(key)
    if hit:
        return {**hit, "cached": True}
    if not llm.llm_ready():
        raise llm.LLMUnavailable("GEMINI_API_KEY not set")
    ratelimit.limiter.acquire("llm", ratelimit.caller(request))  # cache miss
    try:
        markdown, used_model = llm.generate_state_brief(state, body.scenario, rows, totals)
    except llm.LLMUnavailable:
        raise
    except Exception as e:
        raise _llm_failure(e)
    out = {"markdown": markdown, "model": used_model,
           "grounding": {"state": state, "scenario": body.scenario, "n_districts": len(rows),
                         "season": seasons.season_context(body.scenario, data.get_kpis()[0])["season"],
                         "top_districts": [{"lgd": r.get("lgd"), "district": r.get("district"), "score": r.get("score")}
                                           for r in rows[:10]], "totals": totals},
           "cached": False}
    advisory_cache.put(key, out, persist=not config.mock_llm())
    return out


CHAT_MAX_MESSAGES = 12
CHAT_MAX_MESSAGE_CHARS = 2000
CHAT_MAX_TOTAL_CHARS = 12000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str  # length enforced in chat() -> 413 (the 64 KB body cap bounds it before parsing)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    scenario: Scenario = "elnino"
    lgd: int | None = Field(default=None, ge=1, le=10**7)  # selected district (used by default)
    role: Literal["farmer", "officer", "planner"] | None = None
    language: Language | None = None  # reply language (farmers)


_chat_caller: contextvars.ContextVar[ratelimit.Caller | None] = contextvars.ContextVar("chat_caller", default=None)


def _farmer_advice_provider(lgd: int, scenario: str, language: str, profile: dict) -> dict:
    """The `farmer_advice` chat tool: same cached builder as POST /api/advisory/{lgd} (audience=farmer)."""
    try:
        prof = FarmerProfile(**profile)
    except ValidationError as e:
        raise ValueError(f"invalid farmer profile: {e.errors()[0].get('loc')}") from e
    return _get_advisory(lgd, "farmer", language, scenario, prof, who=_chat_caller.get())


tools.set_advisory_provider(_farmer_advice_provider)


def _chat_too_large(msg: str) -> HTTPException:
    return HTTPException(status_code=413, detail={"error": "payload_too_large", "message": msg})


@app.post("/api/chat")
def chat(body: ChatRequest, request: Request):
    if len(body.messages) > CHAT_MAX_MESSAGES:
        raise _chat_too_large(f"at most {CHAT_MAX_MESSAGES} messages per request")
    if any(len(m.content) > CHAT_MAX_MESSAGE_CHARS for m in body.messages):
        raise _chat_too_large(f"each message must be at most {CHAT_MAX_MESSAGE_CHARS} characters")
    if sum(len(m.content) for m in body.messages) > CHAT_MAX_TOTAL_CHARS:
        raise _chat_too_large(f"total conversation must be at most {CHAT_MAX_TOTAL_CHARS} characters")
    if body.messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="last message must have role 'user'")
    if not llm.llm_ready():
        raise llm.LLMUnavailable("GEMINI_API_KEY not set")
    if body.lgd is not None and data.district_by_lgd(body.lgd) is None:
        raise HTTPException(status_code=404, detail=f"unknown district lgd {body.lgd}")
    who = ratelimit.caller(request)
    ratelimit.limiter.acquire("llm", who)  # chat is never cached: always counts
    token = _chat_caller.set(who)  # lets the farmer_advice tool bill its cache misses to this caller
    try:
        reply, lgds = llm.run_chat([m.model_dump() for m in body.messages], body.scenario, body.lgd, body.role,
                                   body.language)
    except llm.LLMUnavailable:
        raise
    except Exception as e:
        raise _llm_failure(e)
    finally:
        _chat_caller.reset(token)
    return {"reply": reply, "citations": lgds, "model": llm.effective_model()}


# ------------------------------------------------------------------ frontend (SPA)
@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")
    dist = config.dist_dir().resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="frontend not built (run `npm run build` in web/)")
    if full_path:
        target = (dist / full_path).resolve()
        if target.is_file() and dist in target.parents:
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} \
                if full_path.startswith("assets/") else {}
            return FileResponse(target, media_type=mimetypes.guess_type(target.name)[0], headers=headers)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=int(config.env("PORT", "8080")))
