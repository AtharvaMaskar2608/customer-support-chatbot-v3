## Context

RAG evaluation must be split into two components — retrieval and generation — so failures can be pinpointed at the component level (DeepEval's prescribed methodology, `docs/rag_guide/3_rag_eval.md`). This change builds both halves of the harness plus the data they run on. It owns `backend/evals/rag/` exclusively and consumes fixed contracts: P0 (`get_settings`, `get_connection`, `backend/schemas/rag.py`, `CONFIDENT_API_KEY`, `deepeval` in `requirements-eval.txt`) and P1 (`backend/rag/retriever.py::retrieve`). It does not modify any `requirements` file, migration, or shared schema.

The knowledge base is `qa_chunks` in Postgres (1,102 rows, each with a `chunk` text column). Goldens are synthesized from that KB, persisted once, then reused across eval runs so scoring is reproducible and comparable across hyperparameter changes.

## Goals / Non-Goals

**Goals:**
- Deterministic, on-disk `EvaluationDataset` of RAG goldens generated from `qa_chunks`.
- Component-level scoring of P1 `retrieve()` with the exact five DeepEval metrics and explicit thresholds.
- `input` to every `LLMTestCase` is the **raw user query only**; `retrieval_context` comes **only** from `retrieve()`.
- One config knob selects the judge/generation model (Claude or OpenAI) for both synthesis and metrics.
- `deepeval test run backend/evals/rag/` (and `pytest`) produce a scored report; runs log to a Confident AI single-turn metric collection.

**Non-Goals:**
- No changes to retrieval logic, agent, config schema, migrations, or `requirements`.
- No multi-turn / conversational eval (owned by P7 `chatbot-multiturn-evals`).
- No ANN tuning or reranker experiments (this measures; it does not change the retriever).

## Decisions

### D1. Judge / generation model config knob — `backend/evals/rag/judge.py`

A single knob selects the LLM used both as the `Synthesizer` model and as every metric's judge. Read from the environment (this module may read env directly; it must not modify P0's `Settings`). Default is OpenAI so the harness runs without an Anthropic wrapper.

```python
# backend/evals/rag/judge.py
import os
from typing import Union
from deepeval.models import DeepEvalBaseLLM

# env EVAL_JUDGE_MODEL; e.g. "gpt-4o", "gpt-4o-mini", or "claude" / a pinned claude-* id.
JUDGE_MODEL_ENV = "EVAL_JUDGE_MODEL"
DEFAULT_JUDGE_MODEL = "gpt-4o"

def get_judge_model() -> Union[str, DeepEvalBaseLLM]:
    """Return the model to pass to Synthesizer(model=...) and every metric(model=...).

    - If EVAL_JUDGE_MODEL is unset or names an OpenAI model -> return the string
      (DeepEval uses OPENAI_API_KEY from the environment / settings.openai_api_key).
    - If it starts with "claude" -> return a ClaudeJudge wrapper built from
      settings.anthropic_api_key (thinking disabled), so metrics run on Claude.
    """

class ClaudeJudge(DeepEvalBaseLLM):
    """Minimal DeepEvalBaseLLM adapter over the anthropic SDK; thinking disabled.
    Model id from EVAL_JUDGE_MODEL (or settings.anthropic_model); key from
    settings.anthropic_api_key."""
    def load_model(self): ...
    def generate(self, prompt: str) -> str: ...
    async def a_generate(self, prompt: str) -> str: ...
    def get_model_name(self) -> str: ...
```

Rationale: metrics and synthesis must use the *same* configurable judge for comparability; OpenAI-string vs Claude-wrapper is DeepEval's native dispatch.

### D2. Golden generation — `backend/evals/rag/synthesize_goldens.py`

```python
# backend/evals/rag/synthesize_goldens.py
from deepeval.dataset import EvaluationDataset, Golden

DATASET_DIR = "backend/evals/rag/dataset"
DATASET_FILE = "rag_goldens.json"          # persisted EvaluationDataset

def load_kb_contexts(limit: int | None = None) -> list[tuple[str, str]]:
    """Read qa_chunks from Postgres via get_connection().
    Returns list of (chunk_id, chunk_text) where chunk_id == str(qa_chunks.id).
    Ordered by id; `limit` caps rows for a smaller/faster golden set."""

def generate_goldens(
    max_goldens: int = 50,
    chunk_size: int = 1024,      # tokens; from_docs path only (matches P0/P1 chunking)
    chunk_overlap: int = 0,      # tokens; from_docs path only
    num_evolutions: int = 2,     # evolution steps applied per input
    kb_limit: int | None = None,
) -> list[Golden]:
    """Synthesize RAG goldens from the qa_chunks KB and persist them to disk.

    Primary path — from_contexts (KB is already chunked as qa_chunks.chunk):
        synthesizer = Synthesizer(model=get_judge_model())
        goldens = synthesizer.generate_goldens_from_contexts(
            contexts=[[text] for _id, text in load_kb_contexts(kb_limit)],
            max_goldens_per_context=1,
            evolutions={Evolution.REASONING: 0.2, Evolution.CONCRETIZING: 0.2,
                        Evolution.CONSTRAINED: 0.2, Evolution.COMPARATIVE: 0.2,
                        Evolution.IN_BREADTH: 0.2},
            num_evolutions=num_evolutions,
        )
    Each golden's additional_metadata is stamped with source_chunk_id (the qa_chunks.id
    the context came from) so recall@k can check retrieval hit the source row.

    Alternative path — from_docs over a dumped dataset/kb_corpus.md, exercising
    chunk_size/chunk_overlap (used when re-chunking end-to-end is desired):
        synthesizer.generate_goldens_from_docs(
            document_paths=["backend/evals/rag/dataset/kb_corpus.md"],
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            max_goldens_per_context=1)

    Persistence:
        dataset = EvaluationDataset(goldens=goldens)
        dataset.save_as(file_type="json", directory=DATASET_DIR, file_name="rag_goldens")
    Returns the list of goldens (also written to DATASET_DIR/DATASET_FILE).
    """

def load_goldens() -> list[Golden]:
    """Load persisted goldens: EvaluationDataset().add_goldens_from_json_file(
    file_path=f"{DATASET_DIR}/{DATASET_FILE}") -> dataset.goldens."""
```

- Generation + judge model = `get_judge_model()` (D1). A `Golden` has `input` and `expected_output` but no `actual_output`/`retrieval_context` (filled at eval time).
- `max_goldens` caps dataset size; default 50 keeps a run fast and cheap while covering varied topics via `IN_BREADTH`.

### D3. Building test cases — `backend/evals/rag/run_eval.py`

```python
# backend/evals/rag/run_eval.py
from deepeval.test_case import LLMTestCase
from backend.rag.retriever import retrieve   # P1

def generate_answer(query: str, retrieval_context: list[str]) -> str:
    """Produce actual_output for a test case.
    Preferred: if backend.agent.loop.agent_reply (P3) is importable, use it with an
      empty history + a stub SessionContext -> its answer string.
    Fallback (P3 absent): prompt get_judge_model() with query + retrieval_context to
      synthesize a grounded answer. Used to fill LLMTestCase.actual_output."""

def build_test_case(golden, k: int = 10) -> LLMTestCase:
    """Field mapping (DeepEval RAG contract):
        input            = golden.input                 # RAW user query ONLY (no prompt template)
        expected_output  = golden.expected_output       # ground truth from synthesizer
        retrieval_context = [c.text for c in retrieve(golden.input, k).chunks]  # ONLY from retrieve()
        actual_output    = generate_answer(golden.input, retrieval_context)
    Also carries additional_metadata={'source_chunk_id': golden.additional_metadata['source_chunk_id'],
        'retrieved_ids': [c.id for c in retrieve(...).chunks]} for recall@k.
    """

def build_test_cases(goldens: list, k: int = 10) -> list[LLMTestCase]: ...
```

`k=10` matches P1 `retrieve`'s default top-K. `input` is the raw query per DeepEval's caution: the prompt template is a variable being optimized and must not pollute the metric input.

### D4. Metrics + thresholds — `backend/evals/rag/run_eval.py::rag_metrics`

```python
from deepeval.metrics import (
    ContextualPrecisionMetric, ContextualRecallMetric, ContextualRelevancyMetric,
    AnswerRelevancyMetric, FaithfulnessMetric,
)

def rag_metrics(include_generation: bool = True) -> list:
    m = get_judge_model()
    retrieval = [
        ContextualPrecisionMetric(threshold=0.7, model=m, include_reason=True),  # reranker/order
        ContextualRecallMetric(threshold=0.7, model=m, include_reason=True),     # embedding recall
        ContextualRelevancyMetric(threshold=0.5, model=m, include_reason=True),  # chunk size / top-K
    ]
    generation = [
        AnswerRelevancyMetric(threshold=0.7, model=m, include_reason=True),      # prompt template
        FaithfulnessMetric(threshold=0.8, model=m, include_reason=True),         # no hallucination
    ]
    return retrieval + (generation if include_generation else [])
```

Threshold rationale: retrieval precision/recall 0.7; relevancy 0.5 (strict metric, penalizes any off-topic chunk in a 10-chunk context); answer relevancy 0.7; faithfulness 0.8 (hallucination is the highest-severity failure for a support bot). Every metric uses the same judge model (D1) and `include_reason=True` so failures are explainable in the report and Confident AI.

### D5. Runner entrypoint — `backend/evals/rag/run_eval.py::main`

```python
def main() -> None:
    """1. goldens = load_goldens() (synthesize_goldens.generate_goldens() if none on disk).
       2. test_cases = build_test_cases(goldens, k=10).
       3. evaluate(test_cases=test_cases, metrics=rag_metrics(),
                   hyperparameters={"embedding_model": settings.embedding_model,
                                    "k": 10, "retriever": "hybrid-rrf", "judge": <model name>})
          -> prints per-case scores + reasons and pass/fail per metric.
       4. If settings.confident_api_key is set, evaluate() uploads the run to the
          Confident AI single-turn metric collection (see D7).
       5. Optionally print recall_at_k(goldens, k=10)."""
```

`evaluate(...)` returns an `EvaluationResult`; `main()` prints an aggregate table (metric -> mean score, pass rate). Exit code is non-zero if any metric's pass rate is below 100% only under `deepeval test run` (D6); `main()` itself always reports.

### D6. CI test file — `backend/evals/rag/test_rag.py`

```python
import pytest
from deepeval import assert_test
from .synthesize_goldens import load_goldens
from .run_eval import build_test_case, rag_metrics

_goldens = load_goldens()

@pytest.mark.parametrize("golden", _goldens)
def test_rag(golden):
    assert_test(build_test_case(golden, k=10), rag_metrics())
```

Run with `deepeval test run backend/evals/rag/` (native DeepEval runner, parallelizable/cacheable) or `pytest backend/evals/rag/`. A case fails when any metric scores below its threshold.

### D7. Optional chunk-id recall@k — `backend/evals/rag/run_eval.py::recall_at_k`

```python
def recall_at_k(goldens: list, k: int = 10) -> float:
    """Non-LLM sanity check independent of the judge model.
    For each golden with additional_metadata['source_chunk_id'] = sid,
    hit if sid in [c.id for c in retrieve(golden.input, k).chunks].
    Returns hits / len(goldens). Complements ContextualRecall with a cheap,
    deterministic 'did we retrieve the exact source row?' signal."""
```

### D8. Confident AI single-turn metric collection dependency

Logging to Confident AI requires (a) `CONFIDENT_API_KEY` present in the environment/settings (P0 provides the knob) and (b) a **single-turn metric collection created in the Confident AI UI** whose metrics match `rag_metrics()`. `evaluate()` (and `deepeval test run`) upload results to that collection automatically once authenticated (`deepeval login` or `CONFIDENT_API_KEY`). Without the collection, runs still print locally but are not persisted server-side. This is an external, human-performed setup step, documented in tasks.

## Risks / Trade-offs

- **[Judge-model cost/nondeterminism]** LLM-as-judge metrics cost tokens and vary run-to-run. Mitigation: cap `max_goldens` (default 50), `include_reason` for auditability, and the deterministic `recall_at_k` as a cheap cross-check.
- **[Synthetic golden quality]** Auto-generated `expected_output` can be noisy. Mitigation: DeepEval's built-in context+input quality filtering (0.5 threshold, 3 retries) and reviewable persisted dataset; goldens are a committed artifact that a human can prune.
- **[Generation path coupling]** `AnswerRelevancy`/`Faithfulness` need an `actual_output`. Without P3 the harness self-generates a grounded answer, which measures the retrieval-conditioned generator, not the production agent. Mitigation: `generate_answer` prefers P3 `agent_reply` when importable; generation metrics are toggleable via `include_generation`.
- **[Metric ↔ collection drift]** If the Confident AI collection's metrics diverge from `rag_metrics()`, uploads may mismatch. Mitigation: collection name + metric list documented in tasks; keep them in sync.

## Migration Plan

1. Land P0 + P1 (config, db, `backend/schemas/rag.py`, `retrieve`) in `main`.
2. Human: create the single-turn metric collection in the Confident AI UI; set `CONFIDENT_API_KEY` and (optionally) `EVAL_JUDGE_MODEL` in `.env`.
3. `generate_goldens()` once → commit `backend/evals/rag/dataset/rag_goldens.json`.
4. Run `deepeval test run backend/evals/rag/` (or `python -m backend.evals.rag.run_eval`).

## Open Questions

- Default golden-set size (50) — may raise for broader coverage once judge cost is measured.
- Exact Confident AI metric-collection name (proposed: `RAG Retrieval Quality`) — confirmed at setup time.
- Whether to pin the generation path to P3 `agent_reply` once P3 lands, or keep the self-generated grounded answer for retriever-isolated scoring.
