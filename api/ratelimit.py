"""Abuse protection: per-IP limits, a global AI-spend breaker, a body-size cap and security headers.

Dependency-free and in-memory. Cloud Run runs up to 5 instances, so every limit here is PER INSTANCE
(worst case x5 across the service). The global budget is a cost safety net, not exact accounting.

Layers (all in this module so they stay testable):
  * `Limiter.check_general`      token bucket per IP for every /api/* request (HTTP middleware in main.py)
  * `Limiter.acquire("llm"|"tts")` sliding windows per IP + global budget; call it ONLY on a cache miss,
                                 right before the paid Gemini call
  * `BodyLimitMiddleware`        generic request body cap (413)
  * `SECURITY_HEADERS`           applied to every response by main.py
Requests carrying `X-Admin-Token == RATE_LIMIT_BYPASS_TOKEN` skip the per-IP limits (global caps still apply).
The token is never logged.
"""
from __future__ import annotations

import hmac
import ipaddress
import math
import threading
import time
from collections import deque
from typing import NamedTuple

from starlette.responses import JSONResponse

from . import config

# ------------------------------------------------------------------ tunables (monkeypatched in tests)
GENERAL_PER_MIN = 120          # sustained /api/* rate per IP
GENERAL_BURST = 40             # bucket capacity
LLM_WINDOWS = ((10, 60), (60, 3600))     # (max calls, window seconds) per IP, text LLM (advisory/brief/chat)
TTS_WINDOWS = ((3, 60), (20, 3600))      # per IP, audio synthesis
MAX_BODY_BYTES = 64 * 1024
MAX_KEYS = 50_000              # hard cap per store (spoofed-IP floods); oldest entries are evicted
PRUNE_EVERY_S = 60.0

DEFAULT_LLM_DAILY_CAP = 1500
DEFAULT_TTS_DAILY_CAP = 150
DEFAULT_LLM_PER_MIN_CAP = 30

DAILY_BUDGET_MESSAGE = "Daily AI budget reached; cached advisories still available."

_time = time.time              # indirection so tests can fake the clock


# ------------------------------------------------------------------ errors
class RateLimited(Exception):
    def __init__(self, retry_after_s: int):
        super().__init__("rate_limited")
        self.retry_after_s = max(1, int(retry_after_s))


class BudgetReached(Exception):
    def __init__(self, message: str, retry_after_s: int):
        super().__init__("budget_reached")
        self.message = message
        self.retry_after_s = max(1, int(retry_after_s))


def rate_limited_response(exc: RateLimited) -> JSONResponse:
    return JSONResponse({"error": "rate_limited", "retry_after_s": exc.retry_after_s}, status_code=429,
                        headers={"Retry-After": str(exc.retry_after_s)})


def budget_response(exc: BudgetReached) -> JSONResponse:
    return JSONResponse({"error": "budget_reached", "message": exc.message}, status_code=503,
                        headers={"Retry-After": str(exc.retry_after_s)})


# ------------------------------------------------------------------ caller identity
class Caller(NamedTuple):
    ip: str
    bypass: bool


def _first_valid_ip(header: str | None) -> str | None:
    """XFF = 'client, proxy1, ...'. Position is XFF_POSITION=first (default) or last (see README)."""
    if not header:
        return None
    parts = [p.strip() for p in header.split(",") if p.strip()]
    if not parts:
        return None
    pick = parts[-1] if (config.env("XFF_POSITION", "first") or "first").lower() == "last" else parts[0]
    try:
        return str(ipaddress.ip_address(pick))
    except ValueError:
        return None


def client_ip(request) -> str:
    """Client IP: `X-Forwarded-For` (Cloud Run's front end sets it), else the socket peer."""
    ip = _first_valid_ip(request.headers.get("x-forwarded-for"))
    if ip:
        return ip
    return request.client.host if request.client else "unknown"


def is_bypass(request) -> bool:
    expected = config.env("RATE_LIMIT_BYPASS_TOKEN")
    given = request.headers.get("x-admin-token")
    if not expected or not given:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


def caller(request) -> Caller:
    return Caller(client_ip(request), is_bypass(request))


# ------------------------------------------------------------------ limiter state
def _int_env(name: str, default: int) -> int:
    try:
        v = int(config.env(name, str(default)) or default)
        return v if v >= 0 else default
    except ValueError:
        return default


def caps() -> dict[str, int]:
    return {"llm_daily": _int_env("LLM_DAILY_CAP", DEFAULT_LLM_DAILY_CAP),
            "tts_daily": _int_env("TTS_DAILY_CAP", DEFAULT_TTS_DAILY_CAP),
            "llm_per_min": _int_env("LLM_PER_MIN_CAP", DEFAULT_LLM_PER_MIN_CAP)}


def _window_retry(stamps: deque, now: float, windows: tuple[tuple[int, int], ...]) -> int:
    """0 if one more call fits every window, else seconds until it would."""
    worst = 0.0
    for limit, win in windows:
        recent = [t for t in stamps if t > now - win]
        if len(recent) >= limit:
            if limit == 0:
                worst = max(worst, win)
            else:
                worst = max(worst, recent[len(recent) - limit] + win - now)
    return math.ceil(worst) if worst > 0 else 0


class Limiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._buckets: dict[str, list[float]] = {}                 # ip -> [tokens, last_ts]
            self._logs: dict[tuple[str, str], deque] = {}              # (kind, ip) -> call timestamps
            self._day = int(_time() // 86400)
            self._llm_today = 0
            self._tts_today = 0
            self._llm_minute: deque = deque()
            self._last_prune = _time()

    # -- housekeeping (caller holds the lock)
    def _maybe_prune(self, now: float) -> None:
        if now - self._last_prune >= PRUNE_EVERY_S:
            self._last_prune = now
            for ip in [k for k, (_, ts) in self._buckets.items() if now - ts > 120]:
                del self._buckets[ip]
            for k in [k for k, dq in self._logs.items() if not dq or dq[-1] <= now - 3600]:
                del self._logs[k]
        for store in (self._buckets, self._logs):
            while len(store) > MAX_KEYS:
                del store[next(iter(store))]

    def _roll_day(self, now: float) -> None:
        day = int(now // 86400)
        if day != self._day:
            self._day, self._llm_today, self._tts_today = day, 0, 0

    # -- general per-IP token bucket
    def check_general(self, ip: str) -> None:
        now = _time()
        rate = GENERAL_PER_MIN / 60.0
        with self._lock:
            self._maybe_prune(now)
            tokens, last = self._buckets.get(ip, (float(GENERAL_BURST), now))
            tokens = min(float(GENERAL_BURST), tokens + (now - last) * rate)
            if tokens < 1.0:
                self._buckets[ip] = [tokens, now]
                raise RateLimited(math.ceil((1.0 - tokens) / rate))
            self._buckets[ip] = [tokens - 1.0, now]

    # -- paid calls: per-IP windows + global budget. Call ONLY on a cache miss.
    def acquire(self, kind: str, who: Caller) -> None:
        """kind: 'llm' (text generation, chat) or 'tts' (audio). Raises RateLimited / BudgetReached."""
        windows = LLM_WINDOWS if kind == "llm" else TTS_WINDOWS
        cap = caps()
        now = _time()
        with self._lock:
            self._maybe_prune(now)
            self._roll_day(now)
            log = self._logs.setdefault((kind, who.ip), deque())
            while log and log[0] <= now - 3600:
                log.popleft()
            if not who.bypass:
                wait = _window_retry(log, now, windows)
                if wait:
                    raise RateLimited(wait)
            to_midnight = int((self._day + 1) * 86400 - now) + 1
            if kind == "llm":
                if self._llm_today >= cap["llm_daily"]:
                    raise BudgetReached(DAILY_BUDGET_MESSAGE, to_midnight)
                while self._llm_minute and self._llm_minute[0] <= now - 60:
                    self._llm_minute.popleft()
                if len(self._llm_minute) >= cap["llm_per_min"]:
                    wait = math.ceil(self._llm_minute[0] + 60 - now) if self._llm_minute else 60
                    raise BudgetReached("AI service is busy; cached advisories still available. Retry shortly.", wait)
                self._llm_today += 1
                self._llm_minute.append(now)
            else:
                if self._tts_today >= cap["tts_daily"]:
                    raise BudgetReached(DAILY_BUDGET_MESSAGE, to_midnight)
                self._tts_today += 1
            log.append(now)

    def snapshot(self) -> dict:
        with self._lock:
            self._roll_day(_time())
            return {"llm_calls_today": self._llm_today, "tts_calls_today": self._tts_today, "caps": caps()}


limiter = Limiter()


# ------------------------------------------------------------------ request body cap (pure ASGI)
class BodyLimitMiddleware:
    """413 when a request body exceeds `max_bytes`. Buffers bodies of POST/PUT/PATCH (<= max_bytes) and replays
    them, so chunked uploads without Content-Length are capped too."""

    def __init__(self, app, max_bytes: int | None = None) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        limit = self.max_bytes or MAX_BODY_BYTES
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        too_big = JSONResponse({"error": "payload_too_large", "max_bytes": limit}, status_code=413)
        for k, v in scope["headers"]:
            if k == b"content-length" and v.isdigit() and int(v) > limit:
                return await too_big(scope, receive, send)
        chunks: list[bytes] = []
        total = 0
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            body = msg.get("body", b"")
            total += len(body)
            if total > limit:
                return await too_big(scope, receive, send)
            chunks.append(body)
            if not msg.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


# ------------------------------------------------------------------ security headers
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com data:",
    "img-src 'self' data: blob: https://basemaps.cartocdn.com https://*.basemaps.cartocdn.com",
    "media-src 'self' blob: data:",
    "connect-src 'self' https://basemaps.cartocdn.com https://*.basemaps.cartocdn.com",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self)",
    "Content-Security-Policy": CSP,
}
