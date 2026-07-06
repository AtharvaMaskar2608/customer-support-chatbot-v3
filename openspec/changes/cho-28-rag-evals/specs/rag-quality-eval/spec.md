## ADDED Requirements

### Requirement: Build LLMTestCase from a golden with retrieval-sourced context
The system SHALL provide `backend/evals/rag/run_eval.py::build_test_case(golden, k: int = 10) -> LLMTestCase` that maps each golden to a DeepEval `LLMTestCase` with EXACTLY this field mapping: `input = golden.input` (the raw user query only, never a prompt template); `expected_output = golden.expected_output`; `retrieval_context = [c.text for c in retrieve(golden.input, k).chunks]` where `retrieve` is `backend.rag.retriever.retrieve` (P1) and is the ONLY source of `retrieval_context`; `actual_output = generate_answer(golden.input, retrieval_context)`. The test case's `additional_metadata` SHALL carry `source_chunk_id` and the retrieved chunk ids for the `recall@k` check.

#### Scenario: retrieval_context comes only from retrieve()
- **WHEN** `build_test_case(golden, k=10)` runs
- **THEN** the resulting `LLMTestCase.retrieval_context` equals the `.text` of the chunks returned by `retrieve(golden.input, 10)`, and `LLMTestCase.input` equals `golden.input` verbatim with no prompt template prepended

#### Scenario: Answer generation fills actual_output
- **WHEN** `build_test_case` produces a test case
- **THEN** `actual_output` is a non-empty string produced by `generate_answer(query, retrieval_context)` — using P3 `agent_reply` if importable, otherwise a judge-model answer grounded in `retrieval_context`

### Requirement: Score retrieval and generation with the DeepEval metric set
The system SHALL provide `backend/evals/rag/run_eval.py::rag_metrics(include_generation: bool = True) -> list` returning the retrieval metrics `ContextualPrecisionMetric(threshold=0.7)`, `ContextualRecallMetric(threshold=0.7)`, `ContextualRelevancyMetric(threshold=0.5)`, and, when `include_generation` is true, the generation metrics `AnswerRelevancyMetric(threshold=0.7)` and `FaithfulnessMetric(threshold=0.8)`. Every metric SHALL be constructed with `model=get_judge_model()` and `include_reason=True`.

#### Scenario: Full metric set returned by default
- **WHEN** `rag_metrics()` is called with defaults
- **THEN** it returns exactly the five metrics — `ContextualPrecision` (0.7), `ContextualRecall` (0.7), `ContextualRelevancy` (0.5), `AnswerRelevancy` (0.7), `Faithfulness` (0.8) — each using the configured judge model with reasons enabled

#### Scenario: Generation metrics can be excluded
- **WHEN** `rag_metrics(include_generation=False)` is called
- **THEN** it returns only the three retrieval metrics

### Requirement: Eval runner produces a scored report over the golden set
The system SHALL provide `backend/evals/rag/run_eval.py::main() -> None` that loads the goldens (`load_goldens()`, synthesizing them if none are on disk), builds test cases via `build_test_cases(goldens, k=10)`, runs `evaluate(test_cases=test_cases, metrics=rag_metrics(), hyperparameters={...})`, and prints per-case scores with reasons and an aggregate per-metric pass rate. `k=10` SHALL match the P1 `retrieve` default top-K.

#### Scenario: Scored report emitted
- **WHEN** `main()` runs against a persisted golden set
- **THEN** it prints, for every test case, each metric's score, pass/fail against its threshold, and reason, plus an aggregate mean score and pass rate per metric

### Requirement: CI-runnable DeepEval test file
The system SHALL provide `backend/evals/rag/test_rag.py` that parametrizes over `load_goldens()` and calls `assert_test(build_test_case(golden, k=10), rag_metrics())` per golden, so the suite runs under `deepeval test run backend/evals/rag/` and `pytest backend/evals/rag/`, failing any case whose metric scores fall below threshold.

#### Scenario: Test run fails on a below-threshold case
- **WHEN** `deepeval test run backend/evals/rag/` executes and a golden's retrieval or generation metric scores below its threshold
- **THEN** that parametrized test case fails, surfacing the metric name, score, threshold, and reason

### Requirement: Optional chunk-id recall@k check
The system SHALL provide `backend/evals/rag/run_eval.py::recall_at_k(goldens: list, k: int = 10) -> float` that, for each golden, counts a hit when `golden.additional_metadata["source_chunk_id"]` appears among `[c.id for c in retrieve(golden.input, k).chunks]`, and returns `hits / len(goldens)`. This is a deterministic, non-LLM cross-check complementing `ContextualRecallMetric`.

#### Scenario: Recall@k reflects source-row retrieval
- **WHEN** `recall_at_k(goldens, k=10)` runs and every golden's `source_chunk_id` is returned by `retrieve` within the top 10
- **THEN** the function returns `1.0`

### Requirement: Log runs to a Confident AI single-turn metric collection
When `settings.confident_api_key` is present, the eval run SHALL upload its results to a **single-turn metric collection created in the Confident AI UI** whose metrics correspond to `rag_metrics()`. `evaluate()` and `deepeval test run` SHALL perform this upload automatically once authenticated (`deepeval login` or `CONFIDENT_API_KEY`); absence of the collection or the key SHALL still allow the run to print results locally.

#### Scenario: Results appear in Confident AI
- **WHEN** `CONFIDENT_API_KEY` is set, the single-turn metric collection exists, and `main()` (or `deepeval test run`) runs
- **THEN** the scored results are logged to that Confident AI metric collection in addition to local output

#### Scenario: Runs locally without Confident AI
- **WHEN** `settings.confident_api_key` is unset
- **THEN** the eval run still completes and prints scores locally without attempting an upload
