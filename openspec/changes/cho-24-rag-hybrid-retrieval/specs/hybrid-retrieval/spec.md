## ADDED Requirements

### Requirement: Public hybrid-retrieval entry point
The system SHALL expose `backend/rag/retriever.py::retrieve(query: str, k: int = 10) -> RagToolResult` as the single public retrieval API. It SHALL return `RagToolResult(chunks=list[RetrievedChunk], query=<original query>)` where `chunks` is sorted by descending fused RRF score and has length `<= k`. It SHALL NOT be bound as an Anthropic tool in this change.

#### Scenario: Returns top-k cited chunks for a query
- **WHEN** `retrieve("how do I open a demat account", k=5)` is called against the populated `qa_chunks` database
- **THEN** it returns a `RagToolResult` whose `chunks` has length `<= 5`, is ordered by descending `score`, and where every `RetrievedChunk.citation` is non-null with a populated `source`

#### Scenario: Empty query short-circuits
- **WHEN** `retrieve("   ", k=10)` is called with a blank/whitespace-only query
- **THEN** it returns `RagToolResult(chunks=[], query="   ")` without calling the embedding API or issuing any SQL

### Requirement: Full-dimension query embedding
The system SHALL embed the query with OpenAI `text-embedding-3-large` at full 3072 dimensions (no `dimensions` truncation argument), matching `settings.embedding_model` and `settings.embedding_dim`, so the query vector is comparable to the stored `qa_chunks.embedding`. The embedding call SHALL be `client.embeddings.create(model=settings.embedding_model, input=query)` and return a `list[float]` of length 3072.

#### Scenario: Query embedding matches corpus dimensionality
- **WHEN** `embed_query("margin trading facility")` is called
- **THEN** it returns a list of exactly 3072 floats produced by `text-embedding-3-large` with no truncation

### Requirement: Exact vector cosine search
The system SHALL rank candidates by exact cosine distance using a sequential scan with the `pgvector` `<=>` operator and NO ANN index. The SQL SHALL be:
```sql
SELECT id, chunk, answer_source, section, topic
FROM qa_chunks
ORDER BY embedding <=> %(query_vec)s::vector
LIMIT %(n)s;
```
Rank SHALL be the 1-based position in this ordered result (rank 1 = smallest cosine distance).

#### Scenario: Vector search returns nearest chunks first
- **WHEN** `vector_search(conn, query_vec, n=50)` runs with a 3072-dim `query_vec`
- **THEN** it returns up to 50 rows `(id, chunk, answer_source, section, topic)` ordered by ascending cosine distance (most similar first), using no ANN index

### Requirement: Postgres full-text search
The system SHALL run keyword search over the `fts` column using `websearch_to_tsquery('english', query)` ranked by `ts_rank`, leveraging the `qa_chunks_fts_gin` index. The SQL SHALL be:
```sql
SELECT id, chunk, answer_source, section, topic,
       ts_rank(fts, websearch_to_tsquery('english', %(query)s)) AS rank
FROM qa_chunks
WHERE fts @@ websearch_to_tsquery('english', %(query)s)
ORDER BY rank DESC
LIMIT %(n)s;
```
Rank SHALL be the 1-based position in this ordered result (rank 1 = highest `ts_rank`). When no lexemes match, this list SHALL be empty and retrieval SHALL degrade to vector-only.

#### Scenario: FTS ranks keyword matches
- **WHEN** `fts_search(conn, "contract note", n=50)` runs
- **THEN** it returns rows whose `fts` matches `websearch_to_tsquery('english', 'contract note')`, ordered by descending `ts_rank`

#### Scenario: No FTS match degrades gracefully
- **WHEN** the query produces no matching lexemes
- **THEN** `fts_search` returns an empty list and `retrieve` still returns vector-ranked results

### Requirement: Reciprocal Rank Fusion
The system SHALL fuse the vector-ranked and FTS-ranked id lists with Reciprocal Rank Fusion using constant `K = 60` and NO cross-encoder reranker. For each document `d`, the fused score SHALL be the sum over the lists in which `d` appears of `1 / (K + rank_L(d))`, with 1-based ranks. Results SHALL be sorted by descending fused score (ties broken by ascending id) and truncated to the top `k`.

#### Scenario: Document in both lists scores higher
- **WHEN** id `A` appears at rank 1 in the vector list and rank 1 in the FTS list, and id `B` appears at rank 1 in only the vector list
- **THEN** `rrf_fuse` assigns `A` score `1/61 + 1/61` and `B` score `1/61`, ranking `A` above `B`

#### Scenario: Single-list document still scored
- **WHEN** an id appears in only one of the two ranked lists
- **THEN** it receives a fused score of `1/(60 + rank)` and remains eligible for the top-k

### Requirement: Citation mapping from qa_chunks
The system SHALL map each fused row to a `RetrievedChunk` with `id = "qa-{id:05d}"`, `text = chunk`, `score = <fused RRF score>`, and `citation = Citation(source=answer_source, section=section or None, topic=topic or None)`. `Citation.source` SHALL always be populated from `answer_source`, guaranteeing a non-null citation per chunk.

#### Scenario: Every returned chunk has a non-null citation
- **WHEN** `retrieve` maps a fused row with `answer_source="FinX FAQ"`, `section="Demat"`, `topic="Onboarding"`
- **THEN** the resulting `RetrievedChunk` has `id="qa-..."`, `citation.source="FinX FAQ"`, `citation.section="Demat"`, `citation.topic="Onboarding"`, and the `citation` is non-null
