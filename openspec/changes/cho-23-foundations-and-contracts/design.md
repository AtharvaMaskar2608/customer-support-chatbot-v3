## Context

V3 is greenfield. The database (`qa_chunks`, 1,102 rows, `pgvector` installed, embeddings loaded) already exists; only a full-text index is missing. No Python application code, no config layer, and no shared schemas exist yet. Six modules will be built in parallel by separate agents, so the data shapes they exchange must be fixed and importable before any of them starts. This document defines those shapes concretely (field names, types, request/response bodies, function signatures) so downstream changes implement against an exact interface.

Stack: Python 3.12, FastAPI + SSE, `pydantic` v2 for all contracts, `psycopg2-binary` for Postgres, `anthropic` SDK for the agent, `openai` SDK for embeddings. Frontend is vanilla HTML/CSS/JS + Tailwind (consumes the SSE + citation contracts only).

## Goals / Non-Goals

**Goals:**
- One config module; all secrets/settings from `.env`; fail-fast on missing required keys.
- One additive DB migration (FTS column + GIN index) with a re-runnable, idempotent script.
- One `pydantic` module of shared contracts imported by every other module.
- Sole ownership of `requirements` and migrations to prevent parallel-agent contention.

**Non-Goals:**
- No retrieval, agent, HTTP handler, tool client, eval, tracing, or frontend logic (later changes).
- No ANN/vector index (sequential scan is correct at ~1.1k rows).
- No data loading (already loaded).

## Decisions

### D1. Config via a single `pydantic-settings`-style module reading `DATABASE_URL`
`backend/config/settings.py` exposes a frozen `Settings` object. `DATABASE_URL` is the single DB connection source (no discrete host/port vars). Rationale: matches the existing `.env` and loader; only the host changes in prod.

```python
# backend/config/settings.py
class Settings:
    # --- Database ---
    database_url: str                    # env DATABASE_URL (required)
    # --- Anthropic (agent) ---
    anthropic_api_key: str               # env ANTHROPIC_API_KEY (required)
    anthropic_model: str                 # env ANTHROPIC_MODEL, pinned model id; thinking disabled
    anthropic_max_tokens: int = 1024
    # --- OpenAI (embeddings + default eval judge) ---
    openai_api_key: str                  # env OPENAI_API_KEY (required)
    embedding_model: str = "text-embedding-3-large"   # full 3072-dim, no truncation
    embedding_dim: int = 3072
    # --- Confident AI / DeepEval ---
    confident_api_key: str | None        # env CONFIDENT_API_KEY (optional; enables export)
    # --- FinX Reports API ---
    finx_base_url: str = "https://finx.choiceindia.com"
    # --- Cost accounting (INR) ---
    usd_to_inr: float                    # live-fetched per process; USD_TO_INR env is the fallback

def get_settings() -> Settings: ...      # cached singleton; raises on missing required env
```

Model config for the agent is always `thinking: {"type": "disabled"}` (no adaptive/extended thinking). The pinned `ANTHROPIC_MODEL` is `claude-sonnet-4-6` (Sonnet 4.6; the "Sonnet 3.6" nickname in the seed docs is not an official id), confirmed against Anthropic docs and set in `.env`.

### D1a. USD→INR rate fetched live, env fallback
`backend/config/fx.py` exposes `fetch_usd_to_inr(fallback: float | None) -> float`, which fetches the current rate once per process (`GET https://open.er-api.com/v6/latest/USD` → `rates.INR`, stdlib `urllib`, `@lru_cache`). `get_settings()` sets `usd_to_inr` from this fetch, passing the `USD_TO_INR` env var (if present) as the fallback used when the FX API is unreachable (offline/CI). `USD_TO_INR` is thus an optional fallback, not a required var. Rationale: cost accounting should track the real rate rather than a manually-maintained constant, without adding a hard network dependency to every boot.

### D2. Cost table as data, not scattered constants
`backend/config/pricing.py` holds per-model per-token USD prices; cost accounting everywhere derives INR from `usd_to_inr`.

```python
# backend/config/pricing.py
# USD per 1M tokens; keyed by model id.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},   # published Sonnet 4.6 rates, USD per 1M
}
EMBEDDING_PRICING: dict[str, float] = {
    "text-embedding-3-large": 0.13,   # USD per 1M tokens
}

def cost_inr(model: str, input_tokens: int, output_tokens: int, usd_to_inr: float) -> float:
    """Return INR cost for a single model call."""
```

### D3. FTS as a generated `tsvector` column + GIN index (additive migration)
Add a stored generated column over the retrievable text so the hybrid retriever can run Postgres full-text search alongside the vector scan. Idempotent DDL.

```sql
-- backend/db/migrations/001_add_fts.sql
ALTER TABLE qa_chunks
    ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(chunk, ''))) STORED;

CREATE INDEX IF NOT EXISTS qa_chunks_fts_gin ON qa_chunks USING gin (fts);
```

Connection helper:
```python
# backend/db/connection.py
def get_connection() -> psycopg2.extensions.connection: ...   # from settings.database_url
def run_migrations() -> None: ...   # applies backend/db/migrations/*.sql in order, idempotently
```

Canonical `qa_chunks` columns (existing, do not alter): `id bigint PK, topic text, section text, question text, answer text, answer_source text, tat text, source_sheet text, source_row int, chunk text, embedding vector(3072)` + new `fts tsvector`.

### D4. Shared `pydantic` contracts in `backend/schemas/`
All shapes below are the authoritative cross-module contract.

**Citations + RAG-tool return** (`backend/schemas/rag.py`):
```python
class Citation(BaseModel):
    source: str                 # answer_source or document title
    section: str | None = None  # section heading if present
    topic: str | None = None

class RetrievedChunk(BaseModel):
    id: str                     # e.g. "qa-00123" (str form of qa_chunks.id)
    text: str                   # the chunk content
    score: float                # fused RRF score
    citation: Citation

class RagToolResult(BaseModel):
    chunks: list[RetrievedChunk]
    query: str
```

**Session context** (`backend/schemas/session.py`):
```python
class SessionContext(BaseModel):
    client_code: str            # trimmed
    session_token: str          # trimmed; JWT used as Authorization header for reports APIs
```

**Cost + latency accounting** (`backend/schemas/cost.py`):
```python
class MessageCost(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_inr: float
    latency_ms: int

class ConversationCost(BaseModel):
    cumulative_cost_inr: float
    messages: list[MessageCost]
```

**Agent reply** (`backend/schemas/agent.py`) — the single structured return of the agent's non-streaming turn helper (`agent_reply`), consumed by P7 evals:
```python
# backend/schemas/agent.py
class ToolInvocation(BaseModel):
    name: str                    # tool name: search_knowledge_base | get_cml_report | get_contract_note
    input: dict                  # arguments the model passed to the tool
    output: str                  # stringified tool_result fed back to the model

class AgentReply(BaseModel):
    text: str                          # final assistant text
    citations: list[Citation]          # empty when RAG not used
    retrieval_context: list[str]       # RAW retrieved chunk texts (RetrievedChunk.text) gathered this turn; for DeepEval RAG turn metrics
    tools_called: list[ToolInvocation] # every tool the agent invoked this turn, in order
    cost: MessageCost
```

**SSE event schema** (`backend/schemas/sse.py`) — every SSE `data:` frame is one of these, discriminated on `type`:
```python
class StepEvent(BaseModel):        # type="step"
    type: Literal["step"] = "step"
    message: str                    # e.g. "Looking up the knowledge base…"

class TokenEvent(BaseModel):       # type="token"
    type: Literal["token"] = "token"
    text: str                       # incremental output token(s)

class CitationsEvent(BaseModel):   # type="citations"
    type: Literal["citations"] = "citations"
    citations: list[Citation]

class DoneEvent(BaseModel):        # type="done"
    type: Literal["done"] = "done"
    cost: MessageCost
    cumulative_cost_inr: float

class ErrorEvent(BaseModel):       # type="error"
    type: Literal["error"] = "error"
    message: str

SSEEvent = StepEvent | TokenEvent | CitationsEvent | DoneEvent | ErrorEvent
```

**Anthropic tool definitions** (`backend/schemas/tools.py`) — the exact `input_schema` each tool advertises to the model:
```python
RAG_TOOL = {
    "name": "search_knowledge_base",
    "description": "Search the Choice FinX knowledge base for answers to product/support questions. Returns chunks with citations.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Natural-language search query"}},
        "required": ["query"],
    },
}

CML_REPORT_TOOL = {
    "name": "get_cml_report",
    "description": "Fetch a customer's CML (Client Master List) report from FinX by mobile number.",
    "input_schema": {
        "type": "object",
        "properties": {"mobile_number": {"type": "string", "description": "10-digit mobile number"}},
        "required": ["mobile_number"],
    },
}

CONTRACT_NOTE_TOOL = {
    "name": "get_contract_note",
    "description": "Fetch a customer's contract note from FinX by mobile number and contract date.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mobile_number": {"type": "string", "description": "10-digit mobile number"},
            "contract_date": {"type": "string", "description": "Contract date in DD-MM-YYYY format"},
        },
        "required": ["mobile_number", "contract_date"],
    },
}
```

**FinX reports request contracts** (documented here for P2; clients live in P2):
- CML: `POST {finx_base_url}/mis/v2/reports/v2/generate`, body `{"reportType":"cml","searchBy":"mobile-number","searchValue":"<mobile>"}`.
- Contract Note: `POST {finx_base_url}/mis/v2/contract-note/generate`, body `{"mobileNo":"<mobile>","contractDate":"DD-MM-YYYY"}`.
- Shared headers (both): `Authorization: <session_token JWT>` (raw, no `Bearer`), `authType: jwt`, `source: FINX_WEB`.
- Response bodies are provider-defined; tools pass through / summarize (typed as `dict` until schemas are pinned).

## Risks / Trade-offs

- **[Generated `tsvector` on `chunk` only]** → the retriever searches the concatenated `chunk` text; if question/answer weighting is later wanted, the column can be regenerated in a follow-up migration. Acceptable for FTS-as-keyword-half of RRF.
- **[Placeholder pricing rates]** → INR cost is only as accurate as `MODEL_PRICING`; mitigation: rates set to the pinned model's real published prices at implementation, single source of truth.
- **[Contract breakage is fan-out-wide]** → any field rename here breaks all dependents; mitigation: treat `backend/schemas/` as frozen once merged; changes require a new OpenSpec change.
- **[Model id unverified]** → `ANTHROPIC_MODEL` confirmed against live Anthropic docs before P3; kept in `.env` so it never hardcodes.

## Migration Plan

1. Add deps to `backend/requirements.txt`; add `deepeval` to `backend/requirements-eval.txt` (single owner of all dependency files so eval/tracing changes never contend); create `.env.example`.
2. Write config, pricing, schemas, connection helper.
3. Apply `001_add_fts.sql` via `run_migrations()` against local DB (idempotent; safe to re-run).
4. Rollback: `DROP INDEX IF EXISTS qa_chunks_fts_gin; ALTER TABLE qa_chunks DROP COLUMN IF EXISTS fts;` — no data loss (generated column).

## Open Questions

- ~~Exact `ANTHROPIC_MODEL` id string~~ — resolved: `claude-sonnet-4-6` (thinking disabled is fixed).
- ~~Real published per-token rates for the pinned model~~ — resolved: Sonnet 4.6 $3.00 in / $15.00 out per 1M.
- FinX report **response** schemas (optional; tools pass through until provided).
