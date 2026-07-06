## ADDED Requirements

### Requirement: Centralized environment-sourced configuration
The system SHALL expose a single `Settings` object loaded from `.env`, providing all connection strings, API keys, model ids, and cost parameters. Required settings MUST fail fast (raise on load) when absent. No module may read `os.environ` directly for these values.

The `Settings` contract SHALL include exactly these fields:
- `database_url: str` (required, env `DATABASE_URL`)
- `anthropic_api_key: str` (required, env `ANTHROPIC_API_KEY`)
- `anthropic_model: str` (required, env `ANTHROPIC_MODEL`) — thinking always disabled by callers
- `anthropic_max_tokens: int = 1024`
- `openai_api_key: str` (required, env `OPENAI_API_KEY`)
- `embedding_model: str = "text-embedding-3-large"`, `embedding_dim: int = 3072`
- `confident_api_key: str | None` (optional, env `CONFIDENT_API_KEY`)
- `finx_base_url: str = "https://finx.choiceindia.com"`
- `usd_to_inr: float` (fetched live per process; `USD_TO_INR` env is the offline/CI fallback)

Accessor: `get_settings() -> Settings` returns a cached singleton.

The required env vars are `DATABASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, and `OPENAI_API_KEY`. `USD_TO_INR` is optional (see the live-rate requirement below).

#### Scenario: All required env vars present
- **WHEN** `get_settings()` is called with `DATABASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, and `OPENAI_API_KEY` set
- **THEN** it returns a `Settings` object populated from the environment (with `usd_to_inr` fetched live) and defaults applied for unset optional fields

#### Scenario: Required env var missing
- **WHEN** `get_settings()` is called and a required env var (e.g. `DATABASE_URL`) is absent
- **THEN** it raises an error naming the missing variable, and no partially-initialized settings are returned

### Requirement: Live USD→INR rate with env fallback
The system SHALL source `usd_to_inr` from a live exchange-rate fetch (`open.er-api.com`, `GET https://open.er-api.com/v6/latest/USD` → `rates.INR`) performed once per process and cached, via `fetch_usd_to_inr(fallback: float | None) -> float`. On any fetch/parse failure it MUST fall back to the `USD_TO_INR` env var when set; if the fetch fails and no fallback is set, it MUST raise. `USD_TO_INR` is therefore an optional fallback, not a required variable.

#### Scenario: Live rate fetched
- **WHEN** `get_settings()` is called and the FX API is reachable
- **THEN** `settings.usd_to_inr` holds the current live USD→INR rate, fetched at most once for the process lifetime

#### Scenario: FX API unreachable, fallback set
- **WHEN** the live fetch fails and `USD_TO_INR` is set in the environment
- **THEN** `settings.usd_to_inr` equals the `USD_TO_INR` value

#### Scenario: FX API unreachable, no fallback
- **WHEN** the live fetch fails and `USD_TO_INR` is unset
- **THEN** settings loading raises an error rather than returning a stale or zero rate

### Requirement: `.env.example` template
The repository SHALL contain `.env.example` listing every configuration key (required and optional) with placeholder values and inline comments, and no real secrets.

#### Scenario: Example covers all keys
- **WHEN** a developer copies `.env.example` to `.env` and fills values
- **THEN** every key read by `Settings` is present in the example, including `DATABASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OPENAI_API_KEY`, `CONFIDENT_API_KEY`, `FINX_BASE_URL`, and `USD_TO_INR`

### Requirement: INR cost derivation from a single pricing table
The system SHALL derive all monetary costs from one pricing table (USD per 1M tokens per model) and a single `usd_to_inr` rate, via `cost_inr(model, input_tokens, output_tokens, usd_to_inr) -> float`. No cost may be computed from constants defined elsewhere.

#### Scenario: Compute a model-call cost in INR
- **WHEN** `cost_inr(model, input_tokens=1000, output_tokens=500, usd_to_inr=83.0)` is called for a model present in the pricing table
- **THEN** it returns the INR cost = (input_tokens/1e6 · input_rate + output_tokens/1e6 · output_rate) · 83.0
