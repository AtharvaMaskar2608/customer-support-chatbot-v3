## ADDED Requirements

### Requirement: RAG-tool return contract
The system SHALL define `RagToolResult` as the return shape of knowledge-base retrieval, with `chunks: list[RetrievedChunk]` and `query: str`, where each `RetrievedChunk` has `id: str`, `text: str`, `score: float`, and `citation: Citation`, and `Citation` has `source: str`, `section: str | None`, `topic: str | None`. Every retrieved chunk MUST carry a citation.

#### Scenario: Retrieval result serializes to the contract
- **WHEN** the retriever produces results
- **THEN** each item validates against `RetrievedChunk` with a non-null `citation.source`, and the whole result validates against `RagToolResult`

### Requirement: SSE event contract
The system SHALL define the SSE frame types the backend streams and the frontend consumes, discriminated on `type`: `StepEvent{type:"step", message}`, `TokenEvent{type:"token", text}`, `CitationsEvent{type:"citations", citations: list[Citation]}`, `DoneEvent{type:"done", cost: MessageCost, cumulative_cost_inr: float}`, and `ErrorEvent{type:"error", message}`. Each SSE `data:` payload MUST be exactly one of these serialized to JSON.

#### Scenario: Intermediate step then tokens then done
- **WHEN** the agent runs a turn that retrieves and answers
- **THEN** the stream emits one or more `step` events, then `token` events, then a `citations` event, then exactly one terminal `done` event carrying the message cost and cumulative INR

#### Scenario: Error terminates the stream
- **WHEN** the backend encounters an error mid-turn
- **THEN** it emits exactly one `error` event and no `done` event for that turn

### Requirement: Session context contract
The system SHALL define `SessionContext{client_code: str, session_token: str}` with both fields trimmed of surrounding whitespace before use. The `session_token` is the JWT passed as the `Authorization` header to FinX reports APIs.

#### Scenario: Inputs are trimmed
- **WHEN** a `SessionContext` is constructed from raw login inputs containing leading/trailing whitespace
- **THEN** the stored `client_code` and `session_token` contain no surrounding whitespace

### Requirement: Cost and latency accounting contract
The system SHALL define `MessageCost{input_tokens:int, output_tokens:int, cost_inr:float, latency_ms:int}` and `ConversationCost{cumulative_cost_inr:float, messages: list[MessageCost]}` as the shared shapes for per-message and cumulative cost/latency reporting.

#### Scenario: Cumulative cost equals the sum of message costs
- **WHEN** a conversation has produced N message costs
- **THEN** `ConversationCost.cumulative_cost_inr` equals the sum of each `MessageCost.cost_inr`

### Requirement: Agent reply contract
The system SHALL define `AgentReply` (in `backend/schemas/agent.py`) as the structured return of the agent's non-streaming turn helper, with fields `text: str` (final assistant text), `citations: list[Citation]` (empty when the RAG tool was not used), `retrieval_context: list[str]` (the RAW retrieved chunk texts — `RetrievedChunk.text` — gathered during the turn, for DeepEval RAG turn metrics), `tools_called: list[ToolInvocation]` (every tool the agent invoked this turn, in order), and `cost: MessageCost`. It SHALL also define `ToolInvocation` with `name: str` (`search_knowledge_base` | `get_cml_report` | `get_contract_note`), `input: dict` (the arguments the model passed to the tool), and `output: str` (the stringified `tool_result` fed back to the model).

#### Scenario: Agent reply serializes to the contract
- **WHEN** the agent produces a non-streaming reply for a turn that used the RAG tool
- **THEN** the result validates against `AgentReply` with a non-empty `citations`, a `retrieval_context` holding the raw retrieved chunk texts, and a `tools_called` list where every invoked tool appears in order as a `ToolInvocation` with `name`, `input`, and `output`

### Requirement: Anthropic tool-definition contract
The system SHALL define the tool schemas advertised to the model: `search_knowledge_base(query: string)`, `get_cml_report(mobile_number: string)`, and `get_contract_note(mobile_number: string, contract_date: string)`, with the exact `name`, `description`, and JSON `input_schema` (including `required` fields) fixed as the cross-module contract. The FinX reports request contracts (endpoints, bodies, and shared headers `Authorization`/`authType: jwt`/`source: FINX_WEB`) SHALL be documented alongside for the tool-client change to implement.

#### Scenario: Tool schemas are importable and valid
- **WHEN** the agent module loads the tool definitions
- **THEN** each has a unique `name`, a `description`, and an `input_schema` whose `required` matches its documented parameters (`query`; `mobile_number`; `mobile_number` + `contract_date`)
