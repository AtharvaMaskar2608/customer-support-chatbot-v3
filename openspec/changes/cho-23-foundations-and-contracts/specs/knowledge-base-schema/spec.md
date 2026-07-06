## ADDED Requirements

### Requirement: Canonical `qa_chunks` table contract
The system SHALL treat `qa_chunks` as the single knowledge-base table with this column contract, which downstream modules read but MUST NOT alter:
`id bigint PRIMARY KEY`, `topic text`, `section text`, `question text`, `answer text`, `answer_source text`, `tat text`, `source_sheet text`, `source_row integer`, `chunk text`, `embedding vector(3072)`, and (added by this change) `fts tsvector`.

#### Scenario: Schema matches contract
- **WHEN** a module introspects `qa_chunks`
- **THEN** the columns and types match the contract above, with `embedding` being a 3072-dimension `pgvector` column

### Requirement: Full-text search column and index migration
The system SHALL add a stored generated `tsvector` column `fts` over `chunk` and a GIN index on it, via an idempotent migration that is safe to re-run.

The migration SHALL be:
```sql
ALTER TABLE qa_chunks
  ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(chunk, ''))) STORED;
CREATE INDEX IF NOT EXISTS qa_chunks_fts_gin ON qa_chunks USING gin (fts);
```

#### Scenario: Migration applied to fresh database
- **WHEN** `run_migrations()` executes against a database where `qa_chunks` lacks `fts`
- **THEN** the `fts` generated column and `qa_chunks_fts_gin` GIN index exist afterward, and every existing row has a populated `fts` value

#### Scenario: Migration re-run is a no-op
- **WHEN** `run_migrations()` executes a second time
- **THEN** it completes without error and makes no schema changes

### Requirement: Database connection helper
The system SHALL provide `get_connection() -> connection` that connects using `settings.database_url`, and `run_migrations() -> None` that applies `backend/db/migrations/*.sql` in filename order. No module may hardcode connection details.

#### Scenario: Connection uses configured URL
- **WHEN** `get_connection()` is called
- **THEN** it returns a live Postgres connection opened from `settings.database_url`
