## Context

The knowledge base lives in Postgres as `qa_chunks` (1,102 rows), already populated by an offline loader: each row has `chunk` text, a 3072-dim `embedding` (`pgvector`), and — provided by P0's migration — a generated `fts tsvector` column with a `qa_chunks_fts_gin` GIN index. This change builds the retrieval layer only. It consumes fixed P0 contracts (`get_settings`, `get_connection`, and `backend/schemas/rag.py`) and owns `backend/rag/` exclusively. The output feeds two consumers unchanged: the agent (P3), which binds `retrieve` behind the `search_knowledge_base` tool, and the RAG evals (P6), which call `retrieve` directly to score contextual precision/recall/relevancy.

Hybrid retrieval is chosen because dense vectors capture paraphrase/semantic similarity while Postgres full-text captures exact keywords, product names, and IDs that embeddings blur. The two ranked lists are combined with Reciprocal Rank Fusion (RRF), a rank-only fusion that needs no score normalization and no learned reranker — appropriate for a ~1.1k-row corpus where an exact cosine scan is fast.

## Goals / Non-Goals

**Goals:**
- One public entry point: `retrieve(query, k) -> RagToolResult`, deterministic given the DB and the embedding.
- Exact (not approximate) vector cosine ranking; correct at ~1.1k rows.
- Keyword recall via Postgres FTS fused with vectors through RRF (`K = 60`).
- Every returned chunk carries a non-null `Citation` derived from `answer_source`/`section`/`topic`.

**Non-Goals:**
- No ANN/vector index (sequential scan is correct and fast here).
- No cross-encoder / LLM reranker (RRF only).
- No tool binding, agent loop, HTTP, config, DB migration, or schema changes.
- No `chunk`-column re-generation or weighting changes (owned by P0).

## Decisions

### D1. Public API: `retrieve(query, k=10) -> RagToolResult`

`backend/rag/retriever.py`:
```python
from backend.schemas.rag import Citation, RetrievedChunk, RagToolResult

def retrieve(query: str, k: int = 10) -> RagToolResult:
    """Hybrid (vector + FTS, RRF-fused) retrieval over qa_chunks.

    Returns the top-k chunks by fused RRF score, each with a non-null Citation.
    `query` is used verbatim for both the embedding and websearch_to_tsquery.
    """
```
- Returns `RagToolResult(chunks=[RetrievedChunk, ...], query=<original query>)`, `chunks` sorted by descending fused score, length `<= k`.
- Empty/whitespace `query` → `RagToolResult(chunks=[], query=query)` (no embedding call, no SQL).
- Internal candidate depth per list: `n = max(k, 50)` (fetch 50 candidates from each retriever before fusion so fusion has enough overlap to matter). Documented so P6 can reason about recall.

### D2. Query embedding — `backend/rag/embedder.py`

Full 3072-dim `text-embedding-3-large`, no truncation (matches the stored embeddings and `settings.embedding_dim`).
```python
from openai import OpenAI
from backend.config.settings import get_settings

def embed_query(query: str) -> list[float]:
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(
        model=settings.embedding_model,   # "text-embedding-3-large"
        input=query,
        # no `dimensions` arg → full 3072-dim, must match qa_chunks.embedding
    )
    return resp.data[0].embedding          # len == 3072
```
Rationale: the corpus embeddings were written at full dimensionality; passing `dimensions=` (truncation) would make cosine distances incomparable. The 3072-float list is formatted as a `pgvector` literal `"[f1,f2,...]"` for the SQL bind.

### D3. Vector search (exact cosine scan) — `backend/rag/search.py::vector_search`

```python
def vector_search(conn, query_vec: list[float], n: int) -> list[tuple[int, str, str, str, str]]:
    # returns rows ranked best-first: (id, chunk, answer_source, section, topic)
```
Exact SQL (cosine distance operator `<=>`, NO ANN index, sequential scan):
```sql
SELECT id, chunk, answer_source, section, topic
FROM qa_chunks
ORDER BY embedding <=> %(query_vec)s::vector
LIMIT %(n)s;
```
`%(query_vec)s` binds the `"[...]"` pgvector literal from D2. Rank is the 1-based row position in this result (rank 1 = smallest cosine distance = most similar).

### D4. Full-text search — `backend/rag/search.py::fts_search`

```python
def fts_search(conn, query: str, n: int) -> list[tuple[int, str, str, str, str]]:
    # returns rows ranked best-first: (id, chunk, answer_source, section, topic)
```
Exact SQL (uses the P0 `fts` column + GIN index; `websearch_to_tsquery` for user-friendly query syntax; `ts_rank` for ordering):
```sql
SELECT id, chunk, answer_source, section, topic,
       ts_rank(fts, websearch_to_tsquery('english', %(query)s)) AS rank
FROM qa_chunks
WHERE fts @@ websearch_to_tsquery('english', %(query)s)
ORDER BY rank DESC
LIMIT %(n)s;
```
Rank is the 1-based row position (rank 1 = highest `ts_rank`). When `websearch_to_tsquery` yields no lexemes or nothing matches, this list is empty and fusion degrades gracefully to vector-only.

### D5. Reciprocal Rank Fusion — `backend/rag/fusion.py`

```python
RRF_K = 60

def rrf_fuse(
    vector_ranked: list[int],   # qa_chunks.id in vector rank order (best first)
    fts_ranked: list[int],      # qa_chunks.id in FTS rank order (best first)
    k: int,
) -> list[tuple[int, float]]:
    """Return [(id, fused_score), ...] sorted by fused_score desc, length <= k."""
```
Formula — for each document `d`, summed over the lists in which it appears:
```
score(d) = Σ_{list L}  1 / (RRF_K + rank_L(d))          RRF_K = 60,  rank is 1-based
```
A document present in only one list still scores (single `1/(60+rank)` term). Ties broken by ascending id for determinism. Only the top `k` ids are kept. No cross-encoder, no score normalization — RRF operates on ranks alone.

### D6. Row → `RetrievedChunk` + `Citation` mapping — in `retriever.py`

After fusion, each surviving id is looked up in a `dict[id -> row]` union built from both search result sets, and mapped:
```python
RetrievedChunk(
    id=f"qa-{row_id:05d}",          # str form of qa_chunks.id, e.g. "qa-00123"
    text=chunk,                      # qa_chunks.chunk
    score=fused_score,               # RRF score from D5
    citation=Citation(
        source=answer_source,        # qa_chunks.answer_source (never None → non-null citation)
        section=section or None,     # qa_chunks.section (nullable)
        topic=topic or None,         # qa_chunks.topic (nullable)
    ),
)
```
`Citation.source` is always populated from `answer_source`; `section`/`topic` are optional per the P0 `Citation` schema. This guarantees the done-condition: every returned chunk has a non-null citation.

### D7. Orchestration in `retrieve`

1. Trim `query`; if empty → return `RagToolResult(chunks=[], query=query)`.
2. `query_vec = embed_query(query)` (D2).
3. Open one connection via `get_connection()`; run `vector_search` and `fts_search` (D3, D4) with `n = max(k, 50)`; close.
4. Build id-ordered lists and the id→row union dict.
5. `fused = rrf_fuse(vector_ids, fts_ids, k)` (D5).
6. Map each `(id, score)` to `RetrievedChunk` via the row dict (D6).
7. Return `RagToolResult(chunks=chunks, query=query)`.

## Risks / Trade-offs

- **[Exact cosine scan cost]** → O(rows) per query; fine at 1,102 rows (single-digit ms). If the corpus grows large, add an ANN index in a future change (out of scope; P0 deliberately excludes it).
- **[FTS over `chunk` only]** → the `fts` column is generated from `chunk` (P0 decision); question/answer-weighted FTS would need a P0 follow-up migration. Acceptable for the keyword half of RRF.
- **[RRF over raw scores]** → discards magnitude information, but avoids fragile cross-list score normalization and needs no reranker; standard, robust default.
- **[Embedding dim mismatch]** → if a caller ever truncated the query embedding, cosine distances would be meaningless; mitigated by never passing `dimensions=` and asserting `len(vec) == settings.embedding_dim`.

## Migration Plan

No DB migration in this change (the `fts` column + GIN index ship in P0). Rollout: land after P0 is in `main`; implement `backend/rag/`; verify against the local populated DB with `pytest backend/tests/test_retrieval.py`.

## Open Questions

- Optimal internal candidate depth `n` (currently `max(k, 50)`) — may be tuned once P6 RAG evals produce recall numbers; does not change the public contract.
