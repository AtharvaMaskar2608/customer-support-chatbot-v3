## Why

Phase 1 needs an Anthropic-driven agentic loop that independently resolves Choice FinX support queries by orchestrating the RAG tool and the two FinX report tools, streaming its progress to the frontend, accounting cost in INR, and holding SEBI/scope guardrails across the whole conversation. The shared contracts (P0), retrieval (P1), report tools (P2), and tracing (P8) already exist; this change wires them into the loop that the API layer (P4) and evals (P7) consume.

## What Changes

- Add `backend/agent/loop.py` exposing `run_agent_turn(...)` — an async streaming turn runner that drives the Anthropic Messages API with tools `[RAG_TOOL, CML_REPORT_TOOL, CONTRACT_NOTE_TOOL]`, executes each `tool_use` via P2 `execute_tool`, and loops call→tools→feed-back until final text. It emits `StepEvent`s ("Looking up the knowledge base…", "Generating the answer…"), a `TokenEvent` stream, a `CitationsEvent` when RAG was used, and a terminal `DoneEvent` with a `MessageCost` + cumulative INR.
- Add `backend/agent/loop.py::agent_reply(...)` — a non-streaming helper returning an `AgentReply` (text, citations, retrieval_context, tools_called, cost) for evals (P7).
- Add `backend/agent/prompt.py` — the system-prompt builder that MUST include (1) the available-tools list and (2) the knowledge-base question CATEGORIES derived at build time from the distinct `topic` values in `qa_chunks`.
- Add `backend/agent/guardrails.py` — SEBI (never opine/advise/recommend on reports or investments), scope (decline non-Choice-FinX topics and redirect), plus the clarifying-question (≤2) / message-cap (≤10, offer support ticket at cap) state machine and the citations-required-when-RAG-used validation.
- Add `backend/agent/categories.py` — build-time derivation of the distinct KB `topic` values for the system prompt.
- Configure the request with thinking DISABLED (no extended/adaptive thinking), `settings.anthropic_model`, `settings.anthropic_max_tokens`. Self-instrument via P8 `backend.tracing` (`@observe`).

## Capabilities

### New Capabilities
- `agentic-loop`: The Anthropic tool-use loop — streaming turn runner + non-streaming eval helper, tool wiring, SSE event sequence, cost accounting, and the clarifying-question/message-cap state machine.
- `agent-guardrails`: SEBI-compliance and scope enforcement (system-prompt instructions + post-generation validation) plus the citations-required-when-RAG-used rule, holding across follow-ups and tool use.

### Modified Capabilities
<!-- None — greenfield; consumes P0/P1/P2/P8 contracts already in main. -->

## Impact

- **New code:** `backend/agent/loop.py`, `backend/agent/prompt.py`, `backend/agent/guardrails.py`, `backend/agent/categories.py`, `backend/agent/__init__.py`; tests in `backend/tests/test_agent.py`.
- **Dependencies (import only, do not re-declare):** P0 `backend.config.settings.get_settings`, `backend.config.pricing.cost_inr`, `backend.schemas.*` (session, cost, sse, rag, tools); P1 `backend.rag.retriever.retrieve` (via P2 dispatch); P2 `backend.tools.dispatch.execute_tool`; P8 `backend.tracing` (`@observe`, thread id). Uses the `anthropic` SDK and reads `qa_chunks.topic` at build time via `backend.db.connection.get_connection`.
- **Downstream:** unblocks P4 (`/api/chat` streams `run_agent_turn`) and P7 (multi-turn evals call `agent_reply`).
- **Files owned:** `backend/agent/` only. Does not touch lockfiles, migrations, root config, or any other module's files.
