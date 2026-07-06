## ADDED Requirements

### Requirement: Streaming agentic turn runner
The system SHALL expose `backend/agent/loop.py::run_agent_turn(user_message: str, history: list[dict], session: SessionContext, thread_id: str) -> AsyncIterator[SSEEvent]`. It SHALL drive the Anthropic Messages API with `tools = [RAG_TOOL, CML_REPORT_TOOL, CONTRACT_NOTE_TOOL]`, execute every `tool_use` block via P2 `execute_tool(name, tool_input, session) -> str`, feed the `tool_result`s back, and loop call→tools→feed-back until the model returns final text. Per turn it MUST yield, in order: one or more `StepEvent`s (including "Looking up the knowledge base…" and "Generating the answer…"), a stream of `TokenEvent`s for the final text, a `CitationsEvent` when the RAG tool was used, and exactly one terminal `DoneEvent` carrying a `MessageCost` and cumulative INR.

#### Scenario: KB query streams steps, tokens, citations, then done
- **WHEN** `run_agent_turn` handles a Choice-FinX question that the model answers using `search_knowledge_base`
- **THEN** it yields at least one `StepEvent`, then one or more `TokenEvent`s, then a `CitationsEvent` whose `citations` are non-empty, then exactly one `DoneEvent` whose `cost` is a `MessageCost` and whose `cumulative_cost_inr` is set

#### Scenario: Tool-use loop feeds results back until final text
- **WHEN** the model returns `tool_use` blocks in a turn
- **THEN** each block is executed via `execute_tool` and its `tool_result` is fed back in a follow-up model call, repeating until the model returns final assistant text with no further `tool_use`

#### Scenario: Error yields a single error event and no done
- **WHEN** an exception occurs mid-turn
- **THEN** the runner yields exactly one `ErrorEvent` and no `DoneEvent` for that turn

### Requirement: Non-streaming eval helper
The system SHALL expose `backend/agent/loop.py::agent_reply(user_message: str, history: list[dict], session: SessionContext) -> AgentReply` that runs the same loop non-streaming and returns an `AgentReply` populating `text` (final assistant text), `citations` (empty when RAG was not used), `retrieval_context` (the RAW retrieved chunk texts gathered this turn), `tools_called` (every tool invoked this turn, in order, as `ToolInvocation`), and `cost` (the turn's `MessageCost`).

#### Scenario: Returns an AgentReply with text, citations, and cost
- **WHEN** `agent_reply` is called with a KB question
- **THEN** it returns an `AgentReply` whose `text` is a non-empty string, whose `citations` is a non-empty `list[Citation]` (because RAG was used), and whose `cost` is a `MessageCost` with `input_tokens`, `output_tokens`, `cost_inr`, and `latency_ms` populated

#### Scenario: Populates tools_called and raw retrieval_context
- **WHEN** `agent_reply` handles a turn in which the agent invokes `search_knowledge_base`
- **THEN** the returned `AgentReply.tools_called` lists every invoked tool in order as `ToolInvocation` (with `name`, `input`, and `output`) and `AgentReply.retrieval_context` holds the RAW retrieved chunk texts (`RetrievedChunk.text`) fed to the model, not citation metadata

### Requirement: Thinking disabled and pinned request config
The system SHALL issue every Anthropic request with `model = settings.anthropic_model`, `max_tokens = settings.anthropic_max_tokens`, the P3 tool list, the built system prompt, and `thinking = {"type": "disabled"}` (no extended or adaptive thinking).

#### Scenario: Requests disable thinking
- **WHEN** the loop builds an Anthropic request
- **THEN** the request sets `thinking` to `{"type": "disabled"}` and uses `settings.anthropic_model` and `settings.anthropic_max_tokens`

### Requirement: Cost accounting in INR
The system SHALL compute the turn's `MessageCost` by summing token usage across all model calls in the turn and calling `cost_inr(settings.anthropic_model, input_tokens, output_tokens, settings.usd_to_inr)`, and report a cumulative INR total in the terminal `DoneEvent`.

#### Scenario: Cost derives from usage via cost_inr
- **WHEN** a turn completes after N model calls
- **THEN** `MessageCost.input_tokens`/`output_tokens` equal the summed usage across those calls and `MessageCost.cost_inr` equals `cost_inr(model, input_tokens, output_tokens, usd_to_inr)`

### Requirement: Clarifying-question and message-cap state machine
The system SHALL ask at most 2 clarifying questions per conversation and SHALL cap the conversation at 10 total messages. When a cap is reached without resolution, the final assistant text MUST offer to raise a support ticket instead of continuing.

#### Scenario: At most two clarifying questions
- **WHEN** the conversation history already contains two prior clarifying questions from the agent
- **THEN** the agent does not ask a third clarifying question and instead attempts a best-effort answer or offers a support ticket

#### Scenario: Support-ticket offer at the message cap
- **WHEN** the message count reaches 10 and the query is still unresolved
- **THEN** the final assistant text includes an offer to raise a support ticket

### Requirement: System prompt lists tools and KB categories
The system SHALL build the system prompt via `backend/agent/prompt.py::build_system_prompt()`, which MUST include (1) the list of available tools (`search_knowledge_base`, `get_cml_report`, `get_contract_note`) and (2) the list of knowledge-base question categories derived at build time from the distinct `topic` values in `qa_chunks` via `backend/agent/categories.py::get_kb_categories()`.

#### Scenario: Prompt includes tools and derived categories
- **WHEN** `build_system_prompt()` is called
- **THEN** the returned prompt contains all three tool names and each category returned by `get_kb_categories()` (the distinct non-null `topic` values of `qa_chunks`)
