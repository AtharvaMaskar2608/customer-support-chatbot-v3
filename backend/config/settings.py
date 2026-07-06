"""Centralized, env-sourced configuration.

The single source of settings/secrets for the whole backend. No other module may
read ``os.environ`` for these values — import ``get_settings()`` instead.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from .fx import fetch_usd_to_inr

# Load .env once at import so get_settings() sees it. Real env vars still win.
load_dotenv()

_MISSING = object()


class Settings(BaseModel):
    """Immutable, validated application settings.

    Construct via :func:`get_settings`, which sources every field from the
    environment and fails fast (naming the variable) when a required one is
    absent.
    """

    model_config = ConfigDict(frozen=True)

    # --- Database ---
    database_url: str  # env DATABASE_URL (required)

    # --- Anthropic (agent) ---
    anthropic_api_key: str  # env ANTHROPIC_API_KEY (required)
    anthropic_model: str  # env ANTHROPIC_MODEL, pinned model id; thinking disabled
    anthropic_max_tokens: int = 1024  # env ANTHROPIC_MAX_TOKENS (optional)

    # --- OpenAI (embeddings + default eval judge) ---
    openai_api_key: str  # env OPENAI_API_KEY (required)
    embedding_model: str = "text-embedding-3-large"  # full 3072-dim, no truncation
    embedding_dim: int = 3072

    # --- Confident AI / DeepEval ---
    confident_api_key: str | None = None  # env CONFIDENT_API_KEY (optional)

    # --- FinX Reports API ---
    finx_base_url: str = "https://finx.choiceindia.com"

    # --- Cost accounting (INR) ---
    # Live USD->INR rate, fetched once per process (see fx.fetch_usd_to_inr).
    # Falls back to the USD_TO_INR env var when the FX API is unreachable.
    usd_to_inr: float


def _require(name: str) -> str:
    value = os.environ.get(name, _MISSING)
    if value is _MISSING or value == "":
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return value  # type: ignore[return-value]


def _optional(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _optional_float(name: str) -> float | None:
    value = _optional(name)
    return float(value) if value is not None else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton.

    Raises ``RuntimeError`` naming the first missing required variable, so no
    partially-initialized settings object is ever returned.
    """

    return Settings(
        database_url=_require("DATABASE_URL"),
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        anthropic_model=_require("ANTHROPIC_MODEL"),
        anthropic_max_tokens=int(_optional("ANTHROPIC_MAX_TOKENS", "1024")),
        openai_api_key=_require("OPENAI_API_KEY"),
        embedding_model=_optional("EMBEDDING_MODEL", "text-embedding-3-large"),
        embedding_dim=int(_optional("EMBEDDING_DIM", "3072")),
        confident_api_key=_optional("CONFIDENT_API_KEY"),
        finx_base_url=_optional("FINX_BASE_URL", "https://finx.choiceindia.com"),
        # Fetched live; USD_TO_INR (if set) is the offline/CI fallback.
        usd_to_inr=fetch_usd_to_inr(fallback=_optional_float("USD_TO_INR")),
    )
