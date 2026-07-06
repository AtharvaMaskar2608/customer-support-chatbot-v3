## 1. Package scaffold & imports

- [ ] 1.1 Create `backend/agent/__init__.py`; confirm imports of P0 contracts (`get_settings`, `cost_inr`, `SessionContext`, `MessageCost`, `Citation`, SSE events, `RAG_TOOL`/`CML_REPORT_TOOL`/`CONTRACT_NOTE_TOOL`), P2 `execute_tool`, and P8 `backend.tracing` resolve
- [ ] 1.2 Add the `anthropic` SDK usage (client construction from `settings.anthropic_api_key`; async client for streaming)

## 2. KB categories & system prompt

- [ ] 2.1 Implement `backend/agent/categories.py::get_kb_categories()` — `SELECT DISTINCT topic FROM qa_chunks WHERE topic IS NOT NULL ORDER BY topic` via `backend.db.connection.get_connection`, cached after first call
- [ ] 2.2 Implement `backend/agent/prompt.py::build_system_prompt()` including the three tool names + purposes, the derived KB categories, the SEBI rule, the scope rule, and the ≤2-clarifying / ≤10-message + support-ticket-at-cap behavior

## 3. Guardrails module

- [ ] 3.1 Implement `backend/agent/guardrails.py`: `is_clarifying_question`, `clarifying_count`, `message_count`, `at_message_cap(cap=10)`, `support_ticket_offer`
- [ ] 3.2 Implement `is_off_topic_request`, `violates_sebi`, and `enforce(text, *, rag_used, citations, at_cap) -> str` (SEBI-safe refusal, citations-required repair, ticket-offer at cap)

## 4. Agent loop

- [ ] 4.1 Implement `backend/agent/loop.py::run_agent_turn(...)` — build messages from `history + user_message`, stream with `thinking={"type":"disabled"}`, tools = P3 list; emit `StepEvent` → `TokenEvent`s → `CitationsEvent` (when RAG used) → one `DoneEvent`; single `ErrorEvent` on failure
- [ ] 4.2 Wire the tool-use loop: route each `tool_use` to `execute_tool(name, input, session)`, feed `tool_result`s back, repeat until final text; set `rag_used` and collect `Citation`s from the RAG result
- [ ] 4.3 Compute `MessageCost` via `cost_inr(settings.anthropic_model, in, out, settings.usd_to_inr)` summed over all model calls + wall-clock `latency_ms`; report cumulative INR in `DoneEvent`
- [ ] 4.4 Apply the clarifying/message-cap state machine and `enforce(...)` before terminal frame
- [ ] 4.5 Implement `agent_reply(...)` non-streaming helper returning an `AgentReply` populating `text`, `citations`, `retrieval_context` (raw chunk texts), `tools_called` (each invoked tool as `ToolInvocation`), and `cost`; allocate its own `thread_id` via `new_thread_id()`
- [ ] 4.6 Self-instrument with P8 `@observe` on `run_agent_turn`/`agent_reply` and bind `thread_id`

## 5. Verification — `pytest backend/tests/test_agent.py`

- [ ] 5.1 KB query: `run_agent_turn` emits steps → tokens → `CitationsEvent` (non-empty) → one `DoneEvent`; `agent_reply` returns text + non-empty citations + `MessageCost` (Done condition: resolves a KB query returning citations)
- [ ] 5.2 Off-topic query: agent declines and redirects, no answer to the off-topic question (Done condition: refuses an off-topic query)
- [ ] 5.3 Advice-seeking query: agent refuses SEBI-restricted advice even under pushing; `violates_sebi` passes the refusal (Done condition: refuses an advice-seeking query)
- [ ] 5.4 Caps: ≤2 clarifying questions; at 10 messages the final text offers a support ticket
- [ ] 5.5 Request config: assert `thinking={"type":"disabled"}`, `settings.anthropic_model`, `settings.anthropic_max_tokens`, and tools = `[RAG_TOOL, CML_REPORT_TOOL, CONTRACT_NOTE_TOOL]`
