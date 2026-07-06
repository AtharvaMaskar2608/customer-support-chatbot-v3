## 1. Preconditions

- [ ] 1.1 Confirm P0 `foundations-and-contracts` is in `main`: `backend.config.settings.get_settings`, `backend.db.connection.get_connection`, `backend.schemas.rag.{Citation, RetrievedChunk, RagToolResult}` importable, and `qa_chunks.fts` + `qa_chunks_fts_gin` present in the local DB

## 2. Query embedding

- [ ] 2.1 Implement `backend/rag/embedder.py::embed_query(query: str) -> list[float]` using `OpenAI(...).embeddings.create(model=settings.embedding_model, input=query)`, no `dimensions` arg; assert `len(vec) == settings.embedding_dim` (3072)

## 3. Search primitives

- [ ] 3.1 Implement `backend/rag/search.py::vector_search(conn, query_vec, n) -> list[tuple[int,str,str,str,str]]` with the exact cosine `ORDER BY embedding <=> %(query_vec)s::vector LIMIT n` SQL (no ANN index); format `query_vec` as a `"[...]"` pgvector literal
- [ ] 3.2 Implement `backend/rag/search.py::fts_search(conn, query, n) -> list[tuple[int,str,str,str,str]]` with the `websearch_to_tsquery('english', query)` + `ts_rank` SQL over the `fts` column

## 4. Fusion

- [ ] 4.1 Implement `backend/rag/fusion.py` with `RRF_K = 60` and `rrf_fuse(vector_ranked, fts_ranked, k) -> list[tuple[int,float]]`: `score = Σ 1/(RRF_K + rank)`, ties by ascending id, truncate to top-k; no reranker

## 5. Retriever orchestration

- [ ] 5.1 Implement `backend/rag/retriever.py::retrieve(query, k=10) -> RagToolResult`: trim + empty-query short-circuit; embed; open one `get_connection()`; run `vector_search` + `fts_search` with `n = max(k, 50)`; fuse; map rows to `RetrievedChunk` + `Citation` (`id="qa-{id:05d}"`, `source=answer_source`, `section`/`topic` nullable); return `RagToolResult(chunks, query)`

## 6. Verification

- [ ] 6.1 `pytest backend/tests/test_retrieval.py` — for a sample query, `retrieve()` returns `<= k` chunks ordered by descending score, each with a non-null `citation` whose `source` is populated
- [ ] 6.2 `pytest backend/tests/test_retrieval.py` — empty/whitespace query returns `RagToolResult(chunks=[], query=...)` with no embedding call or SQL (mocked assertion)
- [ ] 6.3 `pytest backend/tests/test_retrieval.py` — unit test `rrf_fuse`: doc in both lists outranks doc in one; single-list doc still scored; K=60 arithmetic exact
