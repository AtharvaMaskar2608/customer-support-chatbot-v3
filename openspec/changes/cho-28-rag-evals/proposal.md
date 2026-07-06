## Why

The hybrid retriever (P1 `retrieve`) is the ground truth the whole chatbot stands on: if retrieval is wrong or the generator hallucinates off it, every answer is wrong. We need an automated, reproducible way to score retrieval and generation quality over a representative test set so hyperparameter changes (chunk depth, RRF, top-K) can be measured rather than guessed. This change builds that eval harness with DeepEval's prescribed RAG methodology (synthetic goldens + component-level metrics) and logs results to Confident AI.

## What Changes

- Add a **synthetic golden generator** (`backend/evals/rag/synthesize_goldens.py`) that uses DeepEval's `Synthesizer` to turn the `qa_chunks` knowledge base into a set of `Golden`s (input query + `expected_output` + source context), evolved for complexity, and persists them to disk as an `EvaluationDataset`.
- Add a **RAG quality eval runner** (`backend/evals/rag/run_eval.py`) that, for each golden, calls P1 `retrieve()` to build the `retrieval_context`, generates an answer, assembles an `LLMTestCase`, and scores it with the three DeepEval **retrieval** metrics (`ContextualPrecision`, `ContextualRecall`, `ContextualRelevancy`) plus the two **generation** metrics (`AnswerRelevancy`, `Faithfulness`).
- Add a **`deepeval test run`-compatible test file** (`backend/evals/rag/test_rag.py`) that parametrizes over the golden dataset and `assert_test`s each case against the metrics, so RAG regressions can break CI.
- Add an optional **chunk-id `recall@k`** check that verifies P1 `retrieve()` returns the source `qa_chunks` row each golden was generated from.
- Make the **eval judge/generation model** a config knob (Claude or OpenAI) and log every run to a **single-turn metric collection** in Confident AI.

This change owns `backend/evals/rag/` only. It does not touch `requirements` files (`deepeval` is provided by P0's `requirements-eval.txt`), migrations, retrieval logic, the agent, or config schema — it consumes them.

## Capabilities

### New Capabilities
- `rag-golden-generation`: Synthesize and persist a versioned `EvaluationDataset` of RAG `Golden`s from the `qa_chunks` knowledge base using DeepEval's `Synthesizer`, with configurable chunking, evolutions, and generation model.
- `rag-quality-eval`: Score retrieval and generation quality of the P1 `retrieve()` pipeline over the golden set with DeepEval's five component metrics (+ optional chunk-id `recall@k`), producing a scored report and logging to Confident AI.

### Modified Capabilities
<!-- None — greenfield; consumes P0 + P1 contracts only. -->

## Impact

- **New code:** `backend/evals/rag/` — `synthesize_goldens.py`, `run_eval.py`, `judge.py`, `test_rag.py`, and a `dataset/` directory for the persisted golden set.
- **Dependencies:** `deepeval` (already declared by P0 in `requirements-eval.txt`; this change adds no deps). Consumes `backend.rag.retriever.retrieve` (P1), `backend.config.settings.get_settings`, `backend.db.connection.get_connection`, and `backend.schemas.rag` (P0). Optionally consumes `backend.agent.loop.agent_reply` (P3) for a richer generation path when available.
- **External:** requires `CONFIDENT_API_KEY` (from P0 settings) and a **single-turn metric collection** created in the Confident AI UI to receive logged runs.
- **Downstream:** none — this is a leaf verification module. Blocked by P0 (config/db/schemas) and P1 (`retrieve`).
