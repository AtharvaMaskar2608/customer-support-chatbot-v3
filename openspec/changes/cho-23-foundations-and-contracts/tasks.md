## 1. Dependencies & environment

- [ ] 1.1 Create `backend/requirements.txt` pinning `anthropic`, `fastapi`, `uvicorn`, `psycopg2-binary`, `openai`, `pydantic`, `python-dotenv`; create `backend/requirements-eval.txt` pinning `deepeval` (consumed by tracing + eval changes, not modified by them)
- [ ] 1.2 Create `.env.example` with every config key (required + optional) and placeholder values, no real secrets

## 2. Configuration module

- [ ] 2.1 Implement `backend/config/settings.py` with the `Settings` fields and `get_settings()` cached singleton; fail fast on missing required env vars
- [ ] 2.2 Implement `backend/config/pricing.py` with `MODEL_PRICING`, `EMBEDDING_PRICING`, and `cost_inr(model, input_tokens, output_tokens, usd_to_inr) -> float`
- [ ] 2.3 Set real published per-token rates for the pinned `ANTHROPIC_MODEL` (confirm model id against Anthropic docs; thinking disabled)

## 3. Database schema & migration

- [ ] 3.1 Write `backend/db/migrations/001_add_fts.sql` (idempotent `fts` generated column + `qa_chunks_fts_gin` GIN index)
- [ ] 3.2 Implement `backend/db/connection.py` with `get_connection()` and `run_migrations()` (applies `migrations/*.sql` in order, idempotently)
- [ ] 3.3 Apply the migration to the local DB and verify `fts` is populated for all 1,102 rows and the GIN index exists

## 4. Shared contracts

- [ ] 4.1 Implement `backend/schemas/rag.py` (`Citation`, `RetrievedChunk`, `RagToolResult`)
- [ ] 4.2 Implement `backend/schemas/session.py` (`SessionContext` with trimming)
- [ ] 4.3 Implement `backend/schemas/cost.py` (`MessageCost`, `ConversationCost`)
- [ ] 4.4 Implement `backend/schemas/sse.py` (`StepEvent`, `TokenEvent`, `CitationsEvent`, `DoneEvent`, `ErrorEvent`, `SSEEvent` union)
- [ ] 4.5 Implement `backend/schemas/tools.py` (`RAG_TOOL`, `CML_REPORT_TOOL`, `CONTRACT_NOTE_TOOL` definitions + documented FinX request contracts/headers)
- [ ] 4.6 Implement `backend/schemas/agent.py` (`ToolInvocation`, `AgentReply`)

## 5. Verification

- [ ] 5.1 `pytest backend/tests/test_schemas.py` — all shared models validate example payloads round-trip
- [ ] 5.2 `pytest backend/tests/test_config.py` — required-var-missing raises; present-vars load; `cost_inr` math correct
- [ ] 5.3 Migration smoke test: run `run_migrations()` twice, assert idempotent and `fts`/GIN index present
