## ADDED Requirements

### Requirement: Synthesize RAG goldens from the knowledge base
The system SHALL provide `backend/evals/rag/synthesize_goldens.py::generate_goldens(max_goldens: int = 50, chunk_size: int = 1024, chunk_overlap: int = 0, num_evolutions: int = 2, kb_limit: int | None = None) -> list[Golden]` that uses DeepEval's `Synthesizer` to produce synthetic `Golden`s from the `qa_chunks` knowledge base. The primary path SHALL call `Synthesizer(model=get_judge_model()).generate_goldens_from_contexts(contexts=[[text] for _id, text in load_kb_contexts(kb_limit)], max_goldens_per_context=1, num_evolutions=num_evolutions, evolutions={...})`, where each context is one `qa_chunks.chunk`. The `chunk_size`/`chunk_overlap` parameters SHALL apply to the alternative `generate_goldens_from_docs(document_paths=[...], chunk_size=chunk_size, chunk_overlap=chunk_overlap)` path over a dumped KB corpus. Each returned `Golden` SHALL have `input` and `expected_output` set and SHALL NOT require `actual_output` or `retrieval_context`.

#### Scenario: Goldens generated from qa_chunks contexts
- **WHEN** `generate_goldens()` is called against a populated `qa_chunks` table
- **THEN** it returns a non-empty `list[Golden]` of length `<= max_goldens`, each with a non-empty `input` query and an `expected_output`

#### Scenario: Evolutions increase input complexity
- **WHEN** `generate_goldens(num_evolutions=2)` runs
- **THEN** each golden input is evolved `num_evolutions` steps using the configured `evolutions` distribution (reasoning, concretizing, constrained, comparative, in-breadth)

### Requirement: Load knowledge-base contexts from Postgres
The system SHALL provide `backend/evals/rag/synthesize_goldens.py::load_kb_contexts(limit: int | None = None) -> list[tuple[str, str]]` that reads rows from `qa_chunks` via `backend.db.connection.get_connection`, returning `(chunk_id, chunk_text)` tuples where `chunk_id == str(qa_chunks.id)`, ordered by `id`, capped to `limit` rows when provided.

#### Scenario: Contexts include source chunk id
- **WHEN** `load_kb_contexts(limit=10)` is called
- **THEN** it returns at most 10 `(chunk_id, chunk_text)` tuples, each `chunk_id` being the string form of the corresponding `qa_chunks.id`

### Requirement: Stamp source chunk id onto each golden
The system SHALL record, in each generated golden's `additional_metadata`, the key `source_chunk_id` equal to the `qa_chunks.id` string of the context it was generated from, so the retrieval `recall@k` check can verify the source row is retrieved.

#### Scenario: Source id available for recall check
- **WHEN** a golden produced by `generate_goldens()` is inspected
- **THEN** `golden.additional_metadata["source_chunk_id"]` is a string matching a real `qa_chunks.id`

### Requirement: Persist and reload the golden set as an EvaluationDataset
The system SHALL persist generated goldens to disk as a DeepEval `EvaluationDataset` at `backend/evals/rag/dataset/rag_goldens.json` via `EvaluationDataset(goldens=goldens).save_as(file_type="json", directory="backend/evals/rag/dataset", file_name="rag_goldens")`, and SHALL provide `load_goldens() -> list[Golden]` that reloads that dataset from disk. The persisted dataset is a committed artifact reused across eval runs for reproducibility.

#### Scenario: Goldens survive a round trip
- **WHEN** `generate_goldens()` writes the dataset and `load_goldens()` is then called
- **THEN** `load_goldens()` returns the same set of goldens (same inputs and expected outputs) read from `backend/evals/rag/dataset/rag_goldens.json`

### Requirement: Configurable generation model
The generation (and judge) model SHALL be selected by `backend/evals/rag/judge.py::get_judge_model()`, driven by the `EVAL_JUDGE_MODEL` environment variable (default `"gpt-4o"`); a value beginning with `"claude"` SHALL return a `ClaudeJudge(DeepEvalBaseLLM)` adapter built from `settings.anthropic_api_key` with thinking disabled, and any other value SHALL return the model-name string used natively by DeepEval with `settings.openai_api_key`. `generate_goldens()` SHALL pass this model to `Synthesizer(model=...)`. This module MUST NOT modify P0's `Settings` or any `requirements` file.

#### Scenario: Claude selected as generation model
- **WHEN** `EVAL_JUDGE_MODEL="claude-..."` and `generate_goldens()` runs
- **THEN** the `Synthesizer` is constructed with a `ClaudeJudge` instance rather than an OpenAI model string
