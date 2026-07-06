## 1. Package scaffold

- [ ] 1.1 Create `backend/tracing/__init__.py` re-exporting `configure_tracing`, `new_thread_id` (from `setup.py`) and `observe`, `update_current_span`, `update_current_trace` (from `spans.py`); confirm importing the package triggers no `trace_manager.configure(...)` call
- [ ] 1.2 Confirm `deepeval` resolves from the existing `backend/requirements-eval.txt` (P0) — do NOT create or modify any requirements file

## 2. Setup module (`backend/tracing/setup.py`)

- [ ] 2.1 Implement `mask_pii(data)` redacting emails, 10-digit mobile numbers, and JWT tokens; recurse into `dict`/`list`, pass non-str scalars through
- [ ] 2.2 Implement `configure_tracing() -> None` guarded by a module-level `_CONFIGURED` flag; call `trace_manager.configure(anthropic_client=..., openai_client=..., confident_api_key=settings.confident_api_key, environment=os.getenv("TRACING_ENVIRONMENT", "development"), sampling_rate=1.0, mask=mask_pii)`; idempotent, no import-time side effects
- [ ] 2.3 Implement `new_thread_id() -> str` returning `str(uuid.uuid4())`

## 3. Span primitives (`backend/tracing/spans.py`)

- [ ] 3.1 Re-export `observe`, `update_current_span`, `update_current_trace` from `deepeval.tracing` with an `__all__`
- [ ] 3.2 Add a module docstring documenting the span-type convention (`agent` root, `retriever`, `llm`, `tool`), the `retrieval_context`/`tools_called`/`thread_id` attach points, and the `CONFIDENT_TRACE_FLUSH=1` note for short-lived eval scripts

## 4. Verification

- [ ] 4.1 `pytest backend/tests/test_tracing.py` — asserts: `configure_tracing()` runs; a sample `@observe`-decorated function produces a span retrievable via `trace_manager.get_all_traces_dict()`; a second `configure_tracing()` call is a no-op; `mask_pii` redacts email/mobile/JWT (incl. nested); `new_thread_id()` returns distinct UUID strings; importing `backend.tracing` has no configure side effect
