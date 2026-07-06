"""Live USD->INR exchange rate.

Fetched once per process from a free FX API and cached. On any failure (network
down, bad response) we fall back to the ``USD_TO_INR`` env var so cost accounting
stays deterministic offline and in CI. Uses stdlib ``urllib`` only — no new deps.
"""

from __future__ import annotations

import json
import urllib.request
from functools import lru_cache

# Free, no API key. Response shape: {"result": "success", "rates": {"INR": 83.4, ...}}
FX_RATE_URL = "https://open.er-api.com/v6/latest/USD"

_TIMEOUT_SECONDS = 10


@lru_cache(maxsize=1)
def fetch_usd_to_inr(fallback: float | None = None) -> float:
    """Return the current USD->INR rate, fetched live and cached for the process.

    On any fetch/parse failure, return ``fallback`` if provided; otherwise raise
    ``RuntimeError``. The result is cached, so the network is hit at most once.
    """

    try:
        with urllib.request.urlopen(FX_RATE_URL, timeout=_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        rate = float(payload["rates"]["INR"])
        if rate <= 0:
            raise ValueError(f"non-positive rate {rate!r}")
        return rate
    except Exception as exc:  # noqa: BLE001 - any failure falls back
        if fallback is not None:
            return fallback
        raise RuntimeError(
            "Could not fetch live USD->INR rate and no USD_TO_INR fallback is set"
        ) from exc
