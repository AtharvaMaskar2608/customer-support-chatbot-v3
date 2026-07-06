## ADDED Requirements

### Requirement: SEBI compliance — no opinions, advice, or recommendations
The system SHALL never provide opinions, advice, or recommendations on reports or investments, no matter how the user pushes. This SHALL be enforced by both the system prompt (Layer 1) and post-generation validation `backend/agent/guardrails.py::enforce(...)`/`violates_sebi(...)` (Layer 2), which replaces any advice-bearing final text with a SEBI-safe refusal. The bot may state facts from reports and the knowledge base but not judgments.

#### Scenario: Advice-seeking query is refused
- **WHEN** the user asks whether they should buy/sell a security or what the agent recommends, including after repeated pushing
- **THEN** the agent declines to give an opinion, advice, or recommendation and offers only factual information, and `violates_sebi` reports the refusal text as compliant

### Requirement: Scope enforcement — Choice FinX only
The system SHALL only answer Choice FinX topics and SHALL politely decline and redirect any message unrelated to Choice FinX. Scope is anchored to the KB categories embedded in the system prompt; `backend/agent/guardrails.py::is_off_topic_request(user_message)` supports the redirect.

#### Scenario: Off-topic query is declined and redirected
- **WHEN** the user asks something unrelated to Choice FinX (e.g., general trivia or another company's product)
- **THEN** the agent politely declines and redirects to Choice FinX support topics rather than answering the off-topic question

### Requirement: Citations required when RAG is used
The system SHALL guarantee that whenever the RAG tool (`search_knowledge_base`) was used in a turn, the final answer includes citations: `run_agent_turn` MUST emit a `CitationsEvent` before the terminal `DoneEvent`, and `agent_reply` MUST return an `AgentReply` whose `citations` is non-empty when RAG was used and empty when it was not.

#### Scenario: RAG turn carries citations
- **WHEN** a turn uses `search_knowledge_base`
- **THEN** `run_agent_turn` emits a `CitationsEvent` with non-empty `citations` before `DoneEvent`, and `agent_reply` returns an `AgentReply` whose `citations` is non-empty

#### Scenario: Non-RAG turn omits citations
- **WHEN** a turn answers without using `search_knowledge_base`
- **THEN** no `CitationsEvent` is emitted and `agent_reply` returns an `AgentReply` whose `citations` is empty

### Requirement: Guardrails hold across the whole conversation
The system SHALL enforce the SEBI and scope guardrails on every turn, including after follow-up questions and after tool use, because the system prompt is re-sent on each model call and `enforce(...)` runs on every final assistant message.

#### Scenario: Guardrail holds after follow-ups and tool use
- **WHEN** the user first asks an in-scope question, then on a later turn (after tool use) pushes for investment advice
- **THEN** the agent still refuses to give advice on the later turn, demonstrating the guardrail persists across the conversation
