## 1. Preconditions (external / other changes)
- [ ] 1.1 Confirm P0 landed: `get_settings`, `get_connection`, `backend/schemas/rag.py`, `CONFIDENT_API_KEY`, and `deepeval` in `requirements-eval.txt` are importable. (Do NOT modify any `requirements` file.)
- [ ] 1.2 Confirm P1 landed: `backend/rag/retriever.py::retrieve(query, k=10) -> RagToolResult` is importable.
- [ ] 1.3 Human: create a **single-turn metric collection** in the Confident AI UI (proposed name `RAG Retrieval Quality`) whose metrics match `rag_metrics()`; set `CONFIDENT_API_KEY` and optionally `EVAL_JUDGE_MODEL` in `.env`.

## 2. Judge / generation model knob
- [ ] 2.1 Create `backend/evals/rag/judge.py` with `get_judge_model()` reading `EVAL_JUDGE_MODEL` (default `"gpt-4o"`) and a `ClaudeJudge(DeepEvalBaseLLM)` adapter (thinking disabled) built from `settings.anthropic_api_key`.
- [ ] 2.2 Done: `get_judge_model()` returns an OpenAI model string by default and a `ClaudeJudge` when `EVAL_JUDGE_MODEL` starts with `"claude"`.

## 3. Golden generation
- [ ] 3.1 Create `backend/evals/rag/synthesize_goldens.py::load_kb_contexts(limit) -> list[tuple[str, str]]` reading `qa_chunks` via `get_connection()`.
- [ ] 3.2 Implement `generate_goldens(max_goldens=50, chunk_size=1024, chunk_overlap=0, num_evolutions=2, kb_limit=None) -> list[Golden]` using `Synthesizer(model=get_judge_model()).generate_goldens_from_contexts(...)`; stamp `additional_metadata["source_chunk_id"]` on each golden.
- [ ] 3.3 Persist via `EvaluationDataset(goldens=...).save_as(file_type="json", directory="backend/evals/rag/dataset", file_name="rag_goldens")`; implement `load_goldens()`.
- [ ] 3.4 Done: `generate_goldens()` writes `backend/evals/rag/dataset/rag_goldens.json` and `load_goldens()` reloads it; each golden has a non-empty `input`, `expected_output`, and a `source_chunk_id`.

## 4. Test-case assembly + metrics
- [ ] 4.1 Create `backend/evals/rag/run_eval.py::generate_answer(query, retrieval_context)` (prefer P3 `agent_reply` when importable; else judge-model grounded answer).
- [ ] 4.2 Implement `build_test_case(golden, k=10) -> LLMTestCase` with the exact field mapping (input=raw query, retrieval_context from `retrieve()` only, expected_output from golden, actual_output from `generate_answer`) and `build_test_cases(goldens, k=10)`.
- [ ] 4.3 Implement `rag_metrics(include_generation=True)` returning ContextualPrecision(0.7), ContextualRecall(0.7), ContextualRelevancy(0.5), AnswerRelevancy(0.7), Faithfulness(0.8), all with `model=get_judge_model()`, `include_reason=True`.
- [ ] 4.4 Done: `build_test_case` returns a valid `LLMTestCase`; `rag_metrics()` returns the five metrics (three when `include_generation=False`).

## 5. Runner + recall@k + Confident AI
- [ ] 5.1 Implement `main()` that loads/synthesizes goldens, builds test cases, runs `evaluate(test_cases, rag_metrics(), hyperparameters={embedding_model, k, retriever, judge})`, and prints per-case + aggregate scores.
- [ ] 5.2 Implement `recall_at_k(goldens, k=10) -> float` using `source_chunk_id` vs `retrieve()` ids.
- [ ] 5.3 Ensure runs upload to the Confident AI single-turn metric collection when `settings.confident_api_key` is set, and print-only otherwise.
- [ ] 5.4 Done: `python -m backend.evals.rag.run_eval` prints a scored report over the golden set and (when configured) logs to Confident AI.

## 6. CI test file
- [ ] 6.1 Create `backend/evals/rag/test_rag.py` parametrizing `load_goldens()` with `assert_test(build_test_case(golden, k=10), rag_metrics())`.
- [ ] 6.2 Done: below-threshold cases fail the run with metric name/score/threshold/reason.

## 7. Verification
- [ ] 7.1 Run `generate_goldens()` once and commit `backend/evals/rag/dataset/rag_goldens.json`.
- [ ] 7.2 Run the eval: `deepeval test run backend/evals/rag/` (or `pytest backend/evals/rag/`) — produces a scored report over the golden set with retrieval + generation metric scores per case.
- [ ] 7.3 Run `python -m backend.evals.rag.run_eval` and confirm the aggregate per-metric pass rate and `recall_at_k` print.
