-- Add full-text search over qa_chunks.chunk for the hybrid retriever.
-- Idempotent and additive: safe to re-run, no data loss, no destructive DDL.
-- This change is the sole owner of migrations; no other change may add DDL.

ALTER TABLE qa_chunks
    ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(chunk, ''))) STORED;

CREATE INDEX IF NOT EXISTS qa_chunks_fts_gin ON qa_chunks USING gin (fts);
