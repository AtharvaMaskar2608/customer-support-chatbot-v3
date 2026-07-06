## Why

Every backend module (retrieval, agent loop, report tools, evals) needs to emit DeepEval traces, but tracing must NOT become a cross-cutting file edit that forces every module to re-implement `trace_manager.configure(...)` or contend on a shared file. This change provides one small, importable tracing-foundation module so downstream modules self-instrument with `@observe` against a single, already-wired setup.

## What Changes

- Introduce `backend/tracing/setup.py` exposing `configure_tracing() -> None` — a single idempotent call that wires DeepEval's global `trace_manager` with the Anthropic + OpenAI clients (for auto-patching token/model capture), `confident_api_key` from settings, an `environment` tag (from env, default `"development"`), and a PII `mask` callable.
- Add `backend/tracing/setup.py::new_thread_id() -> str` returning a fresh UUID string used as the conversation `thread_id` that stitches per-turn traces into one thread.
- Introduce `backend/tracing/spans.py` — thin re-exports / helper wrappers over DeepEval's `@observe(type=...)`, `update_current_span`, and `update_current_trace`, so every module imports these span primitives from one place and follows one span-type convention (`agent`=root, `retriever`, `llm`, `tool`).
- Document the downstream self-instrumentation contract: how modules attach `retrieval_context`, `tools_called`, and `thread_id`, and the `CONFIDENT_TRACE_FLUSH=1` note for short-lived eval scripts.

Non-goals (explicitly NOT in this change): instrumenting the retriever, agent, tools, or eval scripts (each module applies `@observe` itself using these primitives); defining metrics or metric collections; creating or modifying any `requirements` file (`deepeval` is already provided by P0's `backend/requirements-eval.txt`); any Confident AI dashboard/collection setup.

## Capabilities

### New Capabilities
- `tracing`: A shared DeepEval tracing setup + span-primitive module (`configure_tracing`, `new_thread_id`, and re-exported `observe`/`update_current_span`/`update_current_trace`) that every other backend module self-instruments against, plus the documented span-type and dynamic-context conventions.

### Modified Capabilities
<!-- None — greenfield; consumes P0 `foundations-and-contracts` contracts only. -->

## Impact

- **New code:** `backend/tracing/setup.py`, `backend/tracing/spans.py`, `backend/tracing/__init__.py`, and `backend/tests/test_tracing.py`.
- **Dependencies:** none added — relies on `deepeval` already pinned in `backend/requirements-eval.txt` (owned by P0). This change creates/modifies NO requirements file.
- **Config consumed:** `settings.confident_api_key` (optional), plus `TRACING_ENVIRONMENT` env var (optional, default `"development"`) and the `CONFIDENT_TRACE_FLUSH` env var honoured by DeepEval directly.
- **Downstream:** P1 (retriever `retriever` span + `retrieval_context`), P2 (tool `tool` spans + `tools_called`), P3 (agent root `agent` span + `thread_id`), P6/P7 (eval scripts call `configure_tracing()` at startup). All import span primitives from `backend/tracing/spans.py`; none re-declare `trace_manager.configure(...)`.
