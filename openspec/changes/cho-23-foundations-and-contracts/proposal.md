## Why

V3 is a greenfield rebuild with no application code. Every downstream module (RAG retrieval, agent loop, report tools, API/SSE, evals, tracing) depends on the same handful of contracts — the database schema, configuration, and the shared data shapes exchanged between backend, tools, and frontend. Per the project's parallel-workflow rules, these shared contracts must land in `main` **before** any module fans out to a parallel agent. This change establishes that foundation and nothing else.

## What Changes

- Introduce a single **configuration module** sourcing all settings from `.env` via `DATABASE_URL` and discrete API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CONFIDENT_API_KEY`), the pinned Anthropic model id (thinking disabled), embedding model id, and the INR token-cost table used for cost accounting. Ships `.env.example`.
- Add the one and only **database migration**: a full-text `tsvector` column plus GIN index on the existing, already-populated `qa_chunks` table (1,102 rows). No data loading — data and embeddings are already in Postgres. This module is the sole owner of migrations; no other change may add or modify DDL.
- Define the **shared contracts** as typed schemas (concrete field-level definitions live in the spec files and design.md) that every other module imports rather than re-declares:
  - RAG-tool return schema (retrieved chunks + citations).
  - SSE event schema (intermediate-step events, output-token events, terminal done/error).
  - Anthropic tool definitions for the RAG tool and the two FinX report tools (CML + Contract Note), including the shared reports request headers (`Authorization`, `authType: jwt`, `source: FINX_WEB`).
  - Citation format, session context (client code + session token), and the per-message / cumulative cost + latency accounting shape (INR).
- Establish Python dependency management (backend `requirements`) as owned by this change, so parallel modules never contend on it. Adds `anthropic`, `fastapi`, `uvicorn`, `psycopg2-binary`, `openai`, `pydantic`, `python-dotenv` here; eval/tracing deps (`deepeval`) are added by their own changes.

Non-goals (explicitly NOT in this change): retrieval logic, the agent loop, HTTP/SSE endpoint handlers, tool HTTP clients, evals, tracing instrumentation, or any frontend. Those consume these contracts in later changes.

## Capabilities

### New Capabilities
- `configuration`: Centralized, env-sourced settings and secrets (DB URL, API keys, pinned model ids, INR cost table) with an `.env.example` template and fail-fast validation.
- `knowledge-base-schema`: Canonical `qa_chunks` table contract plus the full-text search `tsvector` column and GIN index migration that the hybrid retriever depends on.
- `shared-contracts`: Versioned, typed data shapes shared across modules — RAG-tool return, SSE events, tool definitions (RAG + reports), citation format, session context, and cost/latency accounting.

### Modified Capabilities
<!-- None — this is the first change; no existing specs. -->

## Impact

- **New code:** `backend/config/`, `backend/db/` (migration + connection helper), `backend/schemas/`, `.env.example`, backend `requirements`.
- **Database:** additive migration on `qa_chunks` (new `tsvector` column + GIN index); no row changes, no destructive DDL.
- **Dependencies:** pins core backend libraries; other changes extend only their own dependency scope.
- **Downstream:** unblocks P1 (retrieval), P2 (report tools), P3 (agent), P4 (API/SSE), P5 (frontend), P6/P7 (evals), P8 (tracing) — all import these contracts. Breaking any contract here is a breaking change for every dependent module.
