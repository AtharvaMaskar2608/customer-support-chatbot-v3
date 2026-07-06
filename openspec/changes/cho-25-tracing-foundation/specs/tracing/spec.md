## ADDED Requirements

### Requirement: Idempotent global tracing configuration

The system SHALL provide `backend/tracing/setup.py::configure_tracing() -> None` that wires DeepEval's global `trace_manager` exactly once per process. It SHALL call `trace_manager.configure(...)` with: the Anthropic client (`anthropic_client=Anthropic(api_key=settings.anthropic_api_key)`) and the OpenAI client (`openai_client=OpenAI(api_key=settings.openai_api_key)`) for auto-patching token/model capture; `confident_api_key=settings.confident_api_key`; `environment=os.getenv("TRACING_ENVIRONMENT", "development")`; `sampling_rate=1.0`; and `mask=mask_pii`. The call SHALL be guarded by a module-level flag so second and later calls are no-ops. Importing `backend.tracing` (or its submodules) SHALL NOT call `trace_manager.configure(...)` as an import side effect. This change SHALL NOT create or modify any `requirements` file; `deepeval` is provided by `backend/requirements-eval.txt`.

#### Scenario: First call configures the trace manager

- **WHEN** `configure_tracing()` is called for the first time in a process
- **THEN** `trace_manager.configure(...)` is invoked once with the Anthropic + OpenAI clients, `confident_api_key` from settings, `environment` from `TRACING_ENVIRONMENT` (default `"development"`), `sampling_rate=1.0`, and the PII `mask`

#### Scenario: Repeated calls are no-ops

- **WHEN** `configure_tracing()` is called a second time in the same process
- **THEN** it returns without re-invoking `trace_manager.configure(...)` and raises no error

#### Scenario: Import has no side effects

- **WHEN** a module runs `import backend.tracing` without calling `configure_tracing()`
- **THEN** no `trace_manager.configure(...)` call is made and no SDK client is constructed at import time

#### Scenario: Missing Confident key falls back to local-only

- **WHEN** `configure_tracing()` runs with `settings.confident_api_key` equal to `None`
- **THEN** configuration still succeeds and traces are collected in-memory, retrievable via `trace_manager.get_all_traces_dict()`

### Requirement: Conversation thread id generator

The system SHALL provide `backend/tracing/setup.py::new_thread_id() -> str` returning a fresh UUID4 string suitable for use as a DeepEval conversation `thread_id`. The value SHALL be generated once per user session by the caller and reused across every turn of that conversation so per-turn traces stitch into one thread.

#### Scenario: Returns a unique UUID string

- **WHEN** `new_thread_id()` is called twice
- **THEN** each call returns a distinct non-empty string parseable as a UUID

### Requirement: PII masking of span data

The system SHALL provide a `mask` callable, passed to `trace_manager.configure(...)`, that redacts personally identifiable information from every span input and output before serialization/export. It SHALL redact email addresses, 10-digit mobile numbers, and JWT session tokens, and SHALL recurse into `dict` and `list` values while passing non-string scalars through unchanged.

#### Scenario: Email, mobile, and JWT are redacted

- **WHEN** the mask receives a string containing an email address, a 10-digit mobile number, or a JWT-shaped token
- **THEN** each is replaced with a redaction placeholder and no raw PII remains in the returned value

#### Scenario: Nested structures are recursed

- **WHEN** the mask receives a `dict` or `list` containing PII strings at any depth
- **THEN** the same structure is returned with every contained PII string redacted and non-string scalars unchanged

### Requirement: Single import site for span primitives

The system SHALL provide `backend/tracing/spans.py` that re-exports DeepEval's `observe`, `update_current_span`, and `update_current_trace` so downstream modules import these primitives from one place rather than from `deepeval.tracing` directly. `backend/tracing/__init__.py` SHALL additionally re-export `configure_tracing` and `new_thread_id`.

#### Scenario: Primitives importable from the shared module

- **WHEN** a module runs `from backend.tracing.spans import observe, update_current_span, update_current_trace`
- **THEN** the import succeeds and each name is the corresponding DeepEval callable

#### Scenario: Full surface importable from the package

- **WHEN** a module runs `from backend.tracing import configure_tracing, new_thread_id, observe, update_current_span, update_current_trace`
- **THEN** the import succeeds

### Requirement: Documented span-type and dynamic-context conventions

The system SHALL document the fixed span-type convention that every downstream module follows: `type="agent"` for the root turn span, `type="retriever"` for retrieval, `type="llm"` for generation, and `type="tool"` for FinX report tools. It SHALL document that modules attach `retrieval_context: list[str]` on the `retriever` span via `update_current_span(...)`, attach `tools_called` and the conversation `thread_id` on the root `agent` span/trace via `update_current_span(...)`/`update_current_trace(thread_id=...)`, and that short-lived eval scripts set `CONFIDENT_TRACE_FLUSH=1` so traces flush before process exit while long-running servers do not.

#### Scenario: A typed span is captured and retrievable

- **WHEN** a function decorated with `@observe(type="retriever")` (imported from `backend/tracing/spans.py`) is executed after `configure_tracing()`
- **THEN** a trace containing that span is retrievable via `trace_manager.get_all_traces_dict()`

#### Scenario: retrieval_context and thread_id attach to the trace

- **WHEN** a `retriever` span calls `update_current_span(retrieval_context=[...])` and the root `agent` span calls `update_current_trace(thread_id=new_thread_id())`
- **THEN** the resulting trace dictionary carries the `retrieval_context` on the retriever span and the `thread_id` on the trace
