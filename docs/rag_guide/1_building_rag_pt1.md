> **Purpose of this document:** A step-by-step reference for building the foundation of a Hybrid RAG (Retrieval-Augmented Generation) system on PostgreSQL. Each section is self-contained and can be applied independently. Decision rules are stated explicitly so they can be followed programmatically.

**Terminology used throughout this series:**

*   **Chunk** — the unit of a single queryable entry in the database. All retrievable content lives inside a chunk.
    
*   **Hybrid RAG** — a retrieval system that runs both Full-Text Search (FTS) and Vector Search over one or more columns.
    
*   **TAT** — Turnaround Time (a field in our example knowledge base).
    

* * *

## Step 1 — Setup Requirements

**Prerequisite:** A PostgreSQL server with the `pgvector` extension installed.

Installation guide: https://github.com/pgvector/pgvector

Nothing else is required before proceeding.

* * *

## Step 2 — Data Cleaning

**Goal:** Transform a messy knowledge base into a list of chunks ready for ingestion.

**Rule:** In a Hybrid RAG system, FTS and Vector Search run over a defined set of columns — one column or several, depending on project complexity. Everything you want retrievable must be present in those queryable columns.

**Our design decision:** Use a **single queryable column named** `chunk`. Each chunk concatenates the fields we want to retrieve together, in this case:

```plaintext
Query -> Solution -> TAT
```

**Action:** Write a cleaning script that outputs one chunk per knowledge-base entry, with all retrievable fields merged into the `chunk` column.

* * *

## Step 3 — Data Analysis (Token Statistics)

**Goal:** Measure the token distribution of your chunks to decide the minimum context size your embedding model must support.

**Metrics to compute across all chunks:**

1.  Maximum token count
    
2.  Mean token count
    

**Our measured values:**

| Metric | Value |
| --- | --- |
| Max tokens | 653 |
| Mean tokens | 58.68 |

**Decision rule:**

*   IF `max_tokens` ≤ the input limit of common embedding models → proceed directly; most embedding models that accept ≥ 653 tokens will work.
    
*   IF `max_tokens` is much larger than typical embedding model limits → do ONE of the following before ingestion:
    
    1.  Split oversized chunks further (sub-chunking), OR
        
    2.  Summarize them, OR
        
    3.  Rewrite them into shorter versions.
        

* * *

## Step 4 — Matryoshka Embeddings (Optional Dimension Reduction)

**Definition:** Matryoshka embeddings, based on Matryoshka Representation Learning (MRL), are vectors trained so that prefixes of the dimensions are themselves meaningful representations. Like nested Russian dolls, a full-dimensional vector (e.g., 3072-d) can be truncated to a smaller size (e.g., 256-d or 128-d) without major loss of semantic quality.

**Why it matters:** Smaller vectors → less storage, faster search — useful at scale.

**Example (OpenAI API):**

```python
response = client.embeddings.create(
    input="Matryoshka embeddings are great for scale",
    model="text-embedding-3-large",
    dimensions=256  # Truncate the 3072-dimension vector to 256 (Matryoshka)
)
```

* * *

## Step 5 — Creating the Table and Choosing a Vector Search Strategy

For simple use cases, Steps 1–4 are sufficient to make design decisions and start a POC/MVP. A reasonable default is an OpenAI embedding model (`text-embedding-3-large` or `-small`).

pgvector offers **three vector search options**:

| Option | How it works | Trade-offs |
| --- | --- | --- |
| **Sequential scan (no index)** | Brute-force distance calculation against every row | Exact results (100% recall), but O(n). Fine for small tables (~<100k rows) or when a `WHERE` filter narrows the candidate set significantly. |
| **IVFFlat** | Clusters vectors into `lists` partitions via k-means; a query probes only the nearest `probes` clusters | Faster and cheaper to build than HNSW, lower memory. Requires data to be present BEFORE building. Needs `REINDEX` if the table grows substantially. Recall is tunable but generally slightly lower than HNSW at equal speed. |
| **HNSW** | Graph-based approximate nearest-neighbor structure | Usually the best speed/recall trade-off. Can be built on an empty table; no training step. Downsides: slower to build, higher memory (holds the full graph). |

**Selection heuristic (rule of thumb):**

*   Small tables → Sequential scan.
    
*   Very large tables → HNSW.
    
*   The most robust method is to run experiments and evaluate which performs best on YOUR data (see Step 6).
    

### 5a. Sequential Scan (no index)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id bigserial PRIMARY KEY,
    content text NOT NULL,
    embedding vector(1536)
);
```

No index is created; queries compute exact distances over all rows.

### 5b. IVFFlat

**Ordering constraint: load data FIRST, then build the index.**

```sql
-- 1. Load your data first
INSERT INTO documents (content, embedding) VALUES (...), (...), ...;

-- 2. Then build the index
CREATE INDEX documents_embedding_ivfflat_idx
ON documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 3. Set probes at query time (session-level or per-query)
SET ivfflat.probes = 10;

SELECT id, content
FROM documents
ORDER BY embedding <=> '[...]'
LIMIT 10;
```

**Parameter selection rules:**

*   `lists`: use `rows / 1000` for tables up to ~1M rows; use `sqrt(rows)` for larger tables. Example: 100k rows → `lists = 100`.
    
*   `probes`: start at `lists / 10`, then tune. More probes = more clusters checked = slower but higher recall.
    
*   **Maintenance rule:** after bulk-loading significantly more data, rebuild the index so cluster centers reflect the new distribution:
    

```sql
REINDEX INDEX documents_embedding_ivfflat_idx;
```

### 5c. HNSW

```sql
CREATE INDEX documents_embedding_hnsw_idx
ON documents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Tune search-time accuracy/speed
SET hnsw.ef_search = 100;

SELECT id, content
FROM documents
ORDER BY embedding <=> '[...]'
LIMIT 10;
```

**Key parameters:**

| Parameter | Default | Effect |
| --- | --- | --- |
| `m` | 16 | Max connections per graph node. Higher → better recall, more memory and build time. Typical range: 16–48. |
| `ef_construction` | 64 | Candidate list size during index build. Higher → better index quality, slower build. |
| `ef_search` | 40 (session-settable) | Candidate list size during query. Higher → better recall, slower query. **Constraint: must be ≥ your** `LIMIT`**.** |

Note : If you are using HNSW or IVFFLAT you can only store embeddings with dimensions upto 2000. While for sequential the cap is 16000.

* * *

## Step 6 — Designing Experiments

In most cases, the rules of thumb above are enough to build a well-working RAG system. To PROVE which technique or model works best for your workload, design controlled experiments (e.g., grid search over configurations).

**Experiment axes to compare:**

1.  **Embedding strategy:** large embedding model truncated via Matryoshka vs. a small model at full dimensions.
    
2.  **Index type:** HNSW vs. IVFFlat vs. Sequential scan.
    
3.  **Trade-off measurement:** accuracy (recall) vs. latency for each configuration.
    

Evaluate each configuration against the same query set and pick the winner based on your recall and latency requirements.

* * *

**Summary of the pipeline:** Install pgvector → clean data into a single `chunk` column → measure token stats to validate embedding model fit → (optionally) truncate with Matryoshka embeddings → choose Sequential / IVFFlat / HNSW based on table size or experiments → tune index parameters → validate with grid-search experiments.