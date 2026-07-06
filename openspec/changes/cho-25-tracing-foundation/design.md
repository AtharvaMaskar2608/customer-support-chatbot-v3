## Context

DeepEval traces an application by decorating functions with `@observe`; it builds a parent-child span tree from the call stack, auto-patches the Anthropic/OpenAI clients to capture model + token counts, and (optionally) exports traces to Confident AI. All of that is switched on by a single global call: `trace_manager.configure(...)`. If every backend module made that call itself, tracing would be a cross-cutting edit and a parallel-agent contention point. This change centralizes the one-time configuration and re-exports the span primitives so downstream modules only ever do `from backend.tracing.spans import observe, update_current_span, update_current_trace` and decorate their own functions.

`deepeval` is already available via P0's `backend/requirements-eval.txt`; this change adds no dependency and touches no requirements file. Config is consumed from P0's `get_settings()` (`settings.confident_api_key`). Everything here is import-safe: importing `backend.tracing` must never call `trace_manager.configure(...)` as a side effect — configuration happens only when a process explicitly calls `configure_tracing()` at startup.

## Goals / Non-Goals

**Goals:**
- One idempotent `configure_tracing()` that wires DeepEval once per process (Anthropic + OpenAI auto-patch, Confident key, environment tag, PII mask).
- One `new_thread_id()` UUID helper for conversation-thread stitching.
- One import site (`backend/tracing/spans.py`) for the span primitives + a documented span-type convention (`agent`=root, `retriever`, `llm`, `tool`).
- Document the downstream contract for attaching `retrieval_context`, `tools_called`, and `thread_id`, plus the `CONFIDENT_TRACE_FLUSH=1` note for short-lived scripts.

**Non-Goals:**
- Instrumenting any concrete module (retriever/agent/tools/evals decorate themselves).
- Defining metrics, metric collections, or sampling policy beyond the default `sampling_rate=1.0`.
- Persisting or exporting traces to any custom store (Confident AI export is opt-in via key).

## Decisions

### D1. `configure_tracing() -> None` — one idempotent global setup

```python
# backend/tracing/setup.py
from typing import Any

def configure_tracing() -> None:
    """Wire DeepEval's global trace_manager once per process. Idempotent:
    subsequent calls are no-ops. Import-safe — never called at import time."""
```

Behaviour:
- Guarded by a module-level `_CONFIGURED: bool` flag; the second and later calls return immediately without re-invoking `trace_manager.configure(...)`.
- Builds the Anthropic and OpenAI clients from P0 settings and passes them for auto-patching (captures model name + input/output token counts on `messages.create` / `chat.completions.create` with zero manual instrumentation).
- Reads the environment tag from `TRACING_ENVIRONMENT` env var, defaulting to `"development"`.
- Passes `confident_api_key=settings.confident_api_key`. When `None`, DeepEval collects traces in-memory only (retrievable via `trace_manager.get_all_traces_dict()`); when set, traces also export to Confident AI in a background thread.
- Passes a PII `mask` callable (D3) applied to every span input/output before serialization.

Exact call made inside `configure_tracing()`:
```python
from anthropic import Anthropic
from openai import OpenAI
from deepeval.tracing import trace_manager
from backend.config.settings import get_settings

settings = get_settings()
trace_manager.configure(
    anthropic_client=Anthropic(api_key=settings.anthropic_api_key),
    openai_client=OpenAI(api_key=settings.openai_api_key),
    confident_api_key=settings.confident_api_key,   # optional; None => local-only
    environment=os.getenv("TRACING_ENVIRONMENT", "development"),  # "development"|"staging"|"production"
    sampling_rate=1.0,                              # capture everything; tune per-env later
    mask=mask_pii,                                  # D3
)
```

### D2. `new_thread_id() -> str` — conversation thread id

```python
# backend/tracing/setup.py
import uuid

def new_thread_id() -> str:
    """Return a fresh UUID4 string to use as a conversation thread_id.
    Generated once per user session and reused across all turns so
    per-turn traces stitch into one thread."""
    return str(uuid.uuid4())
```

Rationale: DeepEval performs no session management; the thread is just a shared string tag. Matches the P3 signature `run_agent_turn(..., thread_id: str)` — the API layer (P4) mints one `new_thread_id()` per new session and passes the same value on every turn.

### D3. PII mask callable

```python
# backend/tracing/setup.py
import re
from typing import Any

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MOBILE_RE = re.compile(r"\b\d{10}\b")          # 10-digit mobile (FinX report inputs)
_JWT_RE = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b")  # JWT session tokens

def mask_pii(data: Any) -> Any:
    """Redact emails, 10-digit mobile numbers, and JWT session tokens from any
    span input/output before it is serialized/exported. Recurses into dict/list;
    non-str scalars pass through unchanged."""
    if isinstance(data, str):
        s = _JWT_RE.sub("[JWT REDACTED]", data)
        s = _EMAIL_RE.sub("[EMAIL REDACTED]", s)
        s = _MOBILE_RE.sub("[MOBILE REDACTED]", s)
        return s
    if isinstance(data, dict):
        return {k: mask_pii(v) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_pii(v) for v in data]
    return data
```

DeepEval applies `mask` to all span inputs and outputs before they leave the process, so customer emails, mobile numbers, and raw JWT session tokens never reach Confident AI or the raw trace dicts.

### D4. `backend/tracing/spans.py` — one import site + span-type convention

The module thinly re-exports the DeepEval primitives so no module imports `deepeval.tracing` directly:
```python
# backend/tracing/spans.py
from deepeval.tracing import (
    observe,                # @observe(type=...) decorator
    update_current_span,    # attach dynamic per-span data (retrieval_context, tools_called, …)
    update_current_trace,   # attach trace-level data (thread_id, tags, metadata)
)

__all__ = ["observe", "update_current_span", "update_current_trace"]
```

**Span-type convention (fixed for every module):**

| `@observe(type=...)` | Applied to | Owner |
| --- | --- | --- |
| `agent` | the root turn function (the top orchestrator) — no `type` also allowed for root | P3 `run_agent_turn` / `agent_reply` |
| `retriever` | hybrid retrieval | P1 `retrieve()` |
| `llm` | Anthropic generation calls | P3 agent loop |
| `tool` | FinX report tool calls | P2 `get_cml_report`, `get_contract_note` |

Typed-span usage pattern (what downstream modules write — NOT part of this module's code, documented as the contract):
```python
from backend.tracing.spans import observe, update_current_span, update_current_trace

@observe(type="retriever")
def retrieve(query: str, k: int = 10) -> RagToolResult:
    result = ...  # hybrid RRF
    update_current_span(retrieval_context=[c.text for c in result.chunks])
    return result

@observe(type="tool")
def get_cml_report(mobile_number: str, session: SessionContext) -> dict:
    ...  # tools_called attached at the agent level, see below

@observe(type="agent")   # root span for one turn
async def run_agent_turn(user_message, history, session, thread_id):
    update_current_trace(thread_id=thread_id, tags=["customer-support"])
    ...
```

### D5. `update_current_span` / `update_current_trace` attribute set used by this project

Downstream modules attach exactly these fields (all are native DeepEval params; documented here so every module uses the same names):

- On a `retriever` span, via `update_current_span(...)`:
  - `retrieval_context: list[str]` — the retrieved chunk texts (required for RAG contextual metrics in P6).
- On the `agent` root span/trace:
  - `tools_called: list[ToolCall]` — tools actually invoked this turn, via `update_current_span(tools_called=...)` or `update_current_trace(tools_called=...)`.
  - `thread_id: str` — via `update_current_trace(thread_id=...)`; the same value across all turns of one conversation (from `new_thread_id()`).
- Optional trace-level: `tags: list[str]`, `metadata: dict`, `user_id: str` — free per module.

### D6. `CONFIDENT_TRACE_FLUSH=1` for short-lived eval scripts

DeepEval exports traces asynchronously on a background worker thread. Short-lived scripts (the P6/P7 eval runners) may exit before that worker flushes. Documented rule: **eval scripts that export to Confident AI set `CONFIDENT_TRACE_FLUSH=1` in their environment** so all traces are flushed before the process exits. Long-running servers (the P4 FastAPI app) do NOT need it. This module does not read the variable itself — DeepEval honours it directly — but the requirement is documented as part of the tracing contract.

### D7. Public surface

`backend/tracing/__init__.py` re-exports the four names so callers can `from backend.tracing import configure_tracing, new_thread_id, observe, update_current_span, update_current_trace`:
```python
from backend.tracing.setup import configure_tracing, new_thread_id
from backend.tracing.spans import observe, update_current_span, update_current_trace
```

## Risks / Trade-offs

- **[Import-time side effects]** → if `configure_tracing()` ran at import, tests and tools that merely import `backend.tracing` would open SDK clients and mutate global state. Mitigation: configuration is an explicit call guarded by a module flag; imports are pure.
- **[Mask false positives]** → the 10-digit regex could redact a legitimate 10-digit non-PII number in trace text. Acceptable: over-redaction is the safe failure mode for a support chatbot handling client data.
- **[Auto-patch client identity]** → auto-patching keys off the exact client instances passed to `configure`. Modules that construct their own Anthropic/OpenAI clients still get token capture only if they use clients of the same patched classes; DeepEval patches at the class/method level, so any client works. Documented so P3 does not assume it must reuse the configured instance.
- **[Idempotency across event loops]** → the module-level flag makes `configure_tracing()` process-global; calling it from both the FastAPI startup and an eval import in the same process is safe (second call is a no-op).

## Migration Plan

Not applicable — additive, new module only. No DB, no requirements, no config-key additions beyond the optional `TRACING_ENVIRONMENT` env var (defaulted).

## Open Questions

- Whether to expose `sampling_rate` as an env-tunable knob now vs. hardcode `1.0` until a production change needs it — deferred; `1.0` is correct for dev + evals.
- Exact DeepEval kwarg name for the Anthropic client (`anthropic_client`) — confirmed against the P0-pinned `deepeval` version at implementation; the RAG guide shows `openai_client`, the multi-turn/agent guides confirm the Anthropic equivalent.
