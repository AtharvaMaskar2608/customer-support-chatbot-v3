## Context

This change implements P3, the Anthropic agentic loop, over the frozen P0 contracts. The loop must: stream progress + tokens + citations + a terminal cost frame to the frontend (via P4), execute tool calls through P2's `execute_tool`, keep thinking disabled, enforce the ≤2 clarifying-questions / ≤10-messages caps, offer a support ticket at the cap, require citations whenever the RAG tool was used, and hold SEBI + scope guardrails across the entire conversation. It owns `backend/agent/` only and imports everything else.

Dependencies (imported, never re-declared): **P0** `get_settings`, `cost_inr`, `SessionContext`, `MessageCost`, `Citation`, `RetrievedChunk`/`RagToolResult`, `AgentReply`/`ToolInvocation`, the SSE event models, and `RAG_TOOL`/`CML_REPORT_TOOL`/`CONTRACT_NOTE_TOOL`; **P1** `retrieve` (reached via P2); **P2** `execute_tool(name, tool_input, session) -> str`; **P8** `backend.tracing` (`@observe`, `new_thread_id`). Anthropic access via the `anthropic` SDK.

## Goals / Non-Goals

**Goals:**
- Exact, importable signatures for `run_agent_turn` (streaming) and `agent_reply` (non-streaming eval helper).
- Deterministic SSE event ordering and a single terminal frame per turn.
- Cost in INR computed from real token usage via `cost_inr`.
- Guardrails + caps enforced in a way an eval can assert (system prompt + validation).

**Non-Goals:**
- No HTTP/SSE transport (P4 serializes these `SSEEvent` objects to `text/event-stream`).
- No tool HTTP clients or retrieval logic (P2/P1 own those).
- No extended/adaptive thinking (explicitly disabled).
- No persistence of conversation state (history is passed in by the caller).

## Decisions

### D1. Public signatures (`backend/agent/loop.py`)

```python
from collections.abc import AsyncIterator
from backend.schemas.session import SessionContext
from backend.schemas.sse import SSEEvent
from backend.schemas.rag import Citation
from backend.schemas.cost import MessageCost
from backend.schemas.agent import AgentReply, ToolInvocation

async def run_agent_turn(
    user_message: str,
    history: list[dict],          # prior Anthropic-format messages: [{"role","content"}, ...]
    session: SessionContext,
    thread_id: str,               # from P8 new_thread_id(); binds the trace
) -> AsyncIterator[SSEEvent]:
    """Stream StepEvent(s) -> TokenEvent(s) -> CitationsEvent (if RAG used) -> one DoneEvent.
    On failure yields exactly one ErrorEvent and stops (no DoneEvent)."""

async def agent_reply(
    user_message: str,
    history: list[dict],
    session: SessionContext,
) -> AgentReply:
    """Non-streaming helper for evals (P7). Runs the same loop and builds and returns an
    `AgentReply` populating: `text` (final assistant text), `citations` (empty if RAG not
    used), `retrieval_context` (the RAW retrieved chunk texts — `RetrievedChunk.text` — it
    fed the model this turn), `tools_called` (every tool it invoked this turn, in order, as
    `ToolInvocation`), and `cost` (the turn's `MessageCost`).
    Internally allocates its own thread_id via new_thread_id()."""
```

`history` items are Anthropic message dicts (`{"role": "user"|"assistant", "content": ...}`); the caller appends the new user turn. Both functions build the message list as `history + [{"role":"user","content":user_message}]`.

### D2. Tool-list wiring

The loop advertises exactly the three P0 tool definitions and routes every `tool_use` block through P2's single dispatcher:

```python
from backend.schemas.tools import RAG_TOOL, CML_REPORT_TOOL, CONTRACT_NOTE_TOOL
from backend.tools.dispatch import execute_tool

TOOLS = [RAG_TOOL, CML_REPORT_TOOL, CONTRACT_NOTE_TOOL]

# for each content block of type "tool_use" in the assistant message:
result_str = execute_tool(block.name, block.input, session)   # returns a str for the model
tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result_str})
# feed back as a single {"role":"user","content":[tool_result, ...]} message, then re-call the model
```

`rag_used` is set true whenever any executed `tool_use.name == RAG_TOOL["name"]` ("search_knowledge_base"). Citations are parsed from the RAG tool result: `execute_tool` returns a string, so the loop obtains structured citations by calling the retriever contract's serialized `RagToolResult` — the dispatcher returns a JSON string whose `chunks[].citation` deserialize into `Citation`. (P2 dispatch returns the JSON of `RagToolResult` for the RAG tool; the loop parses it to collect `Citation`s while also passing the string to the model.)

### D3. Anthropic request config

```python
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)   # or AsyncAnthropic for streaming
request = {
    "model": settings.anthropic_model,        # pinned id; thinking disabled
    "max_tokens": settings.anthropic_max_tokens,
    "system": build_system_prompt(),          # from prompt.py; tools + KB categories
    "tools": TOOLS,
    "messages": messages,
    "thinking": {"type": "disabled"},         # NO extended/adaptive thinking
}
```

Streaming uses `client.messages.stream(**request)` (async); token deltas (`content_block_delta` / `text_delta`) become `TokenEvent`s. Non-streaming (`agent_reply`) uses `client.messages.create(**request)` and reads `response.usage`.

### D4. Streaming event sequence (`run_agent_turn`)

Per turn, in order:
1. `StepEvent(message="Looking up the knowledge base…")` — emitted before/at the first RAG `tool_use` (or before the first model call if the model is expected to retrieve).
2. Additional `StepEvent(message="Generating the answer…")` — emitted when the model transitions from tool use to producing final text.
3. `TokenEvent(text=...)` — streamed for each text delta of the final assistant message.
4. `CitationsEvent(citations=[...])` — emitted **only when `rag_used`**, immediately before the terminal frame, carrying the collected `Citation`s.
5. `DoneEvent(cost=MessageCost(...), cumulative_cost_inr=...)` — exactly one terminal frame. `cumulative_cost_inr` = prior cumulative + this turn's `cost_inr` (prior cumulative tracked by the caller / passed via history accounting; the loop reports this turn's cost and the running total it computes).

On any exception: yield exactly one `ErrorEvent(message=...)` and stop; no `DoneEvent` for that turn.

### D5. Cost accounting

Sum `usage.input_tokens` and `usage.output_tokens` across **all** model calls in the turn (initial + every tool-feedback round-trip). Then:

```python
cost = cost_inr(settings.anthropic_model, total_input_tokens, total_output_tokens, settings.usd_to_inr)
message_cost = MessageCost(
    input_tokens=total_input_tokens,
    output_tokens=total_output_tokens,
    cost_inr=cost,
    latency_ms=<wall-clock ms for the whole turn>,
)
```

### D6. Clarifying-question / message-cap state machine

State derived from `history` (no server persistence):
- `clarifying_count` = number of prior assistant turns that were clarifying questions (marked/detected via the guardrail helper `is_clarifying_question`).
- `message_count` = total messages in `history` + this turn.

Rules:
- **Clarifying cap (≤2):** the system prompt instructs the model to ask at most 2 clarifying questions per conversation. If `clarifying_count >= 2`, the prompt/context signals it must not ask further and must attempt a best-effort answer or offer a ticket.
- **Message cap (≤10):** if `message_count >= 10` and the query is unresolved, the loop appends a directive so the final assistant text **offers to raise a support ticket** ("Would you like me to raise a support ticket?") instead of continuing.
- **At cap without resolution:** the terminal assistant text MUST contain the support-ticket offer; enforced by `guardrails.ensure_ticket_offer(text)` when `message_count >= 10`.

```python
# backend/agent/guardrails.py
def is_clarifying_question(assistant_text: str) -> bool: ...
def clarifying_count(history: list[dict]) -> int: ...
def message_count(history: list[dict], user_message: str) -> int: ...
def at_message_cap(history, user_message, cap: int = 10) -> bool: ...
def support_ticket_offer() -> str: ...   # canonical offer string appended at cap
```

### D7. Guardrail enforcement approach (system prompt + validation)

Two layers, both required:

**Layer 1 — system prompt (`prompt.py`):** `build_system_prompt()` returns a string that MUST include:
1. The list of available tools (name + one-line purpose for `search_knowledge_base`, `get_cml_report`, `get_contract_note`).
2. The list of KB question CATEGORIES (see D8).
3. SEBI rule: never give opinions/advice/recommendations on reports or investments, no matter how the user pushes; only state facts from reports/KB.
4. Scope rule: only answer Choice FinX topics; politely decline + redirect anything else.
5. The clarifying-question (≤2) and message-cap (≤10, then offer a support ticket) behavior.

**Layer 2 — post-generation validation (`guardrails.py`):**
```python
def is_off_topic_request(user_message: str) -> bool: ...        # scope pre-check / redirect helper
def violates_sebi(assistant_text: str) -> bool: ...             # detect advice/opinion/recommendation
def enforce(assistant_text: str, *, rag_used: bool, citations: list[Citation],
            at_cap: bool) -> str:
    """Final gate: if violates_sebi -> replace with SEBI-safe refusal; if rag_used and
    not citations -> raise/repair (citations required); if at_cap -> ensure ticket offer present.
    Returns the safe assistant text."""
```

Guardrails hold across the whole conversation because Layer 1 is re-sent on every turn (system prompt is stateless-per-call) and Layer 2 runs on every final assistant message, including after follow-ups and tool use.

**Citations-required rule:** if `rag_used` is true the final answer MUST include citations; `enforce` treats missing citations as a failure to repair (the loop guarantees a `CitationsEvent` precedes `DoneEvent`).

### D8. KB categories at build time (`categories.py` + `prompt.py`)

Categories are the distinct `topic` values in `qa_chunks`, computed once at build time (module import / a `get_kb_categories()` call), not per request:

```python
# backend/agent/categories.py
from backend.db.connection import get_connection

def get_kb_categories() -> list[str]:
    """SELECT DISTINCT topic FROM qa_chunks WHERE topic IS NOT NULL ORDER BY topic.
    Cached after first call; used to render the in-scope category list in the system prompt."""
```

`build_system_prompt()` embeds `get_kb_categories()` so the model knows exactly which question categories are in scope. This ties scope enforcement to real KB contents rather than a hand-maintained list.

## Risks / Trade-offs

- **[Citation parsing depends on P2 dispatch returning RAG results as JSON]** → the loop needs structured `Citation`s but `execute_tool` returns `str`; mitigation: contract is that the RAG branch returns the JSON of `RagToolResult`, which the loop deserializes; if P2 returns prose instead, citations are collected by re-serializing via the retriever contract. Test asserts citations present on a KB query.
- **[Clarifying-question detection is heuristic]** → `is_clarifying_question` may mis-count; mitigation: the cap is a soft guardrail reinforced by the system prompt; the hard cap is the 10-message limit.
- **[Guardrail validation is best-effort]** → `violates_sebi` cannot catch every phrasing; mitigation: primary enforcement is the system prompt; Layer 2 is a backstop, and multi-turn evals (P7) score guardrail adherence.
- **[Streaming step-event timing]** → step messages are heuristic markers around tool use; acceptable for a POC progress indicator.

## Migration Plan

Additive only; no schema or dependency changes (P0 owns `requirements` and migrations). Implement `backend/agent/*.py`, then wire P4 to consume `run_agent_turn` and P7 to consume `agent_reply` in their own changes.

## Open Questions

- Exact wording of the SEBI-safe refusal and the support-ticket offer (final copy at implementation; canonical strings live in `guardrails.py`).
- Whether `is_clarifying_question` should be model-signaled (e.g., a sentinel) rather than heuristic — deferred; heuristic + prompt is sufficient for Phase 1.
