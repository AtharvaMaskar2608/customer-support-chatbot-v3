## Why

The agent needs a knowledge-base search tool that returns accurate, citable answers from the already-populated `qa_chunks` table. Pure vector search misses exact-keyword/ID matches and pure keyword search misses paraphrases; hybrid retrieval (dense vector + Postgres full-text, fused with Reciprocal Rank Fusion) covers both and is the retrieval half the agent and the RAG evals both consume.

## What Changes

- Add `backend/rag/` implementing hybrid retrieval over `qa_chunks` (already populated: 1,102 rows, embeddings loaded, `fts` column + GIN index provided by P0).
- Expose `backend/rag/retriever.py::retrieve(query: str, k: int = 10) -> RagToolResult` — the single public entry point consumed by P3 (agent) and P6 (RAG evals).
- Query embedding via OpenAI `text-embedding-3-large` at full 3072-dim (no truncation).
- Vector search: exact/sequential cosine scan (`ORDER BY embedding <=> query_vec`, NO ANN index).
- Keyword search: Postgres full-text over the `fts` column via `websearch_to_tsquery('english', query)` ranked by `ts_rank`.
- Fusion: Reciprocal Rank Fusion (RRF), `score = Σ 1/(K + rank)`, `K = 60`, NO cross-encoder reranker.
- Each surviving row mapped to `RetrievedChunk` with a `Citation` built from `answer_source` (source), `section`, `topic`.

Non-goals (explicitly NOT in this change): binding this as an Anthropic tool (that is P3 agent); the agent loop; any change to config/DB/schemas (imported from P0); ANN/vector index; a reranker.

## Capabilities

### New Capabilities
- `hybrid-retrieval`: Dense vector + Postgres full-text search over `qa_chunks`, fused with RRF, exposed as `retrieve(query, k) -> RagToolResult` with a non-null `Citation` per chunk.

### Modified Capabilities
<!-- None — greenfield module consuming P0 contracts. -->

## Impact

- **New code:** `backend/rag/` only — `embedder.py`, `search.py`, `fusion.py`, `retriever.py`; tests in `backend/tests/test_retrieval.py`.
- **Imports (do not modify):** `backend.config.settings.get_settings`, `backend.db.connection.get_connection`, `backend.schemas.rag.{Citation, RetrievedChunk, RagToolResult}`.
- **Dependencies:** none added (uses `openai`, `psycopg2-binary`, `pydantic` already pinned by P0).
- **Downstream:** unblocks P3 (agent binds this behind `search_knowledge_base`) and P6 (RAG evals call `retrieve()` directly).
- **Depends on:** P0 `foundations-and-contracts` (config, DB connection + `fts` migration, `backend/schemas/rag.py`) must be in `main` first.
