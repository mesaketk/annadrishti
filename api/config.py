"""Environment-driven configuration. Values are read lazily so tests can monkeypatch os.environ."""
from __future__ import annotations

import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
except Exception:
    pass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def artifacts_dir() -> Path:
    return Path(env("ARTIFACTS_DIR", str(ROOT / "artifacts")))


def mock_dir() -> Path:
    return Path(env("WEB_MOCK_DIR", str(ROOT / "web" / "public" / "mock")))


def dist_dir() -> Path:
    return Path(env("WEB_DIST_DIR", str(ROOT / "web" / "dist")))


def gemini_model() -> str:
    return env("GEMINI_MODEL", "gemini-2.5-flash")  # type: ignore[return-value]


def mock_llm() -> bool:
    return env("MOCK_LLM", "0") in ("1", "true", "True", "yes")


def use_vertex() -> bool:
    return env("USE_VERTEX", "0") in ("1", "true", "True", "yes")
