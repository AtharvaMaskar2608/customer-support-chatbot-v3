"""Config loading, live FX rate + fallback, and INR cost derivation."""

from __future__ import annotations

import pytest

import backend.config.settings as settings_mod
from backend.config import cost_inr, get_settings
from backend.config.fx import fetch_usd_to_inr
from backend.config.pricing import MODEL_PRICING
from backend.config.settings import Settings

_REQUIRED = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "ANTHROPIC_MODEL": "claude-sonnet-4-6",
    "OPENAI_API_KEY": "sk-openai-test",
}

_OPTIONAL_KEYS = [
    "ANTHROPIC_MAX_TOKENS",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "CONFIDENT_API_KEY",
    "FINX_BASE_URL",
    "USD_TO_INR",
]

_ALL_KEYS = list(_REQUIRED) + _OPTIONAL_KEYS


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Known-empty slate so .env-loaded values don't leak into tests.
    for key in _ALL_KEYS:
        monkeypatch.delenv(key, raising=False)
    # Never hit the network from settings tests: stub the live FX fetch to echo
    # its fallback (or a fixed rate when no fallback is provided).
    monkeypatch.setattr(
        settings_mod,
        "fetch_usd_to_inr",
        lambda fallback=None: fallback if fallback is not None else 83.0,
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _set_required(monkeypatch):
    for key, value in _REQUIRED.items():
        monkeypatch.setenv(key, value)


def test_all_required_present_loads_with_defaults(monkeypatch):
    _set_required(monkeypatch)
    settings = get_settings()

    assert isinstance(settings, Settings)
    assert settings.database_url == _REQUIRED["DATABASE_URL"]
    assert settings.anthropic_model == "claude-sonnet-4-6"
    # Live-fetched (stubbed here); no fallback env set -> stub returns 83.0.
    assert settings.usd_to_inr == 83.0
    # Defaults applied for unset optional fields.
    assert settings.anthropic_max_tokens == 1024
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.embedding_dim == 3072
    assert settings.confident_api_key is None
    assert settings.finx_base_url == "https://finx.choiceindia.com"


@pytest.mark.parametrize("missing", list(_REQUIRED))
def test_missing_required_var_raises_naming_it(monkeypatch, missing):
    _set_required(monkeypatch)
    monkeypatch.delenv(missing, raising=False)

    with pytest.raises(RuntimeError) as exc:
        get_settings()
    assert missing in str(exc.value)


def test_usd_to_inr_env_is_fallback_not_required(monkeypatch):
    # USD_TO_INR unset is fine — the live fetch (stubbed) supplies the rate.
    _set_required(monkeypatch)
    assert get_settings().usd_to_inr == 83.0


def test_usd_to_inr_env_used_as_fallback(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.setenv("USD_TO_INR", "90.5")
    # Stub echoes the fallback, mimicking a failed live fetch.
    assert get_settings().usd_to_inr == 90.5


def test_settings_is_cached_singleton(monkeypatch):
    _set_required(monkeypatch)
    assert get_settings() is get_settings()


def test_settings_is_frozen(monkeypatch):
    _set_required(monkeypatch)
    settings = get_settings()
    with pytest.raises(Exception):
        settings.usd_to_inr = 90.0  # frozen model rejects mutation


# --- Live FX fetch (fx.fetch_usd_to_inr) with real network stubbed ---


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_usd_to_inr_parses_live_rate(monkeypatch):
    fetch_usd_to_inr.cache_clear()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda url, timeout=10: _FakeResponse(b'{"result":"success","rates":{"INR":84.25}}'),
    )
    assert fetch_usd_to_inr(fallback=83.0) == 84.25
    fetch_usd_to_inr.cache_clear()


def test_fetch_usd_to_inr_falls_back_on_failure(monkeypatch):
    fetch_usd_to_inr.cache_clear()

    def _boom(url, timeout=10):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    assert fetch_usd_to_inr(fallback=83.0) == 83.0
    fetch_usd_to_inr.cache_clear()


def test_fetch_usd_to_inr_raises_without_fallback(monkeypatch):
    fetch_usd_to_inr.cache_clear()

    def _boom(url, timeout=10):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    with pytest.raises(RuntimeError):
        fetch_usd_to_inr(fallback=None)
    fetch_usd_to_inr.cache_clear()


# --- INR cost derivation ---


def test_cost_inr_math():
    model = "claude-sonnet-4-6"
    rates = MODEL_PRICING[model]
    expected = (1000 / 1e6 * rates["input"] + 500 / 1e6 * rates["output"]) * 83.0
    assert cost_inr(model, 1000, 500, 83.0) == pytest.approx(expected)
    # Concrete value: (0.001*3 + 0.0005*15) * 83 = (0.003 + 0.0075) * 83 = 0.8715
    assert cost_inr(model, 1000, 500, 83.0) == pytest.approx(0.8715)


def test_cost_inr_zero_tokens_is_zero():
    assert cost_inr("claude-sonnet-4-6", 0, 0, 83.0) == 0.0


def test_cost_inr_unknown_model_raises():
    with pytest.raises(KeyError):
        cost_inr("nonexistent-model", 10, 10, 83.0)
