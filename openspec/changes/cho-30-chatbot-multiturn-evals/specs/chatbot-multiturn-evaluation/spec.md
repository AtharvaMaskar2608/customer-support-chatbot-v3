## ADDED Requirements

### Requirement: Conversational goldens dataset

The module SHALL expose `backend/evals/chatbot/goldens.py::build_goldens() -> list[deepeval.dataset.ConversationalGolden]` returning at least 20 goldens. Every `ConversationalGolden` MUST set all three fields — `scenario`, `expected_outcome`, and `user_description`. The set MUST include persona-driven support scenarios and MUST include at least one golden for each of the four guardrail probes: (a) SEBI investment-advice seeking, (b) off-topic / out-of-scope requests, (c) the clarifying-question cap (<=2), and (d) the support-ticket offer at the message cap (<=10 messages). The module SHALL also expose `CHATBOT_ROLE: str` (the support-agent persona/scope) and `RELEVANT_TOPICS: list[str]` (the in-scope support topics) for use by the role- and topic-adherence metrics.

#### Scenario: At least twenty complete goldens
- **WHEN** `build_goldens()` is called
- **THEN** it returns a list of length >= 20 where every element is a `ConversationalGolden` with non-empty `scenario`, `expected_outcome`, and `user_description`

#### Scenario: All four guardrail probes present
- **WHEN** the returned goldens are inspected
- **THEN** at least one golden targets SEBI advice-seeking, at least one targets an off-topic/out-of-scope request, at least one targets the <=2 clarifying-question cap, and at least one targets the support-ticket offer at the <=10 message cap

#### Scenario: Role and topic constants exported
- **WHEN** `goldens.py` is imported
- **THEN** `CHATBOT_ROLE` is a non-empty string describing the FinX support role and `RELEVANT_TOPICS` is a non-empty `list[str]` of in-scope support topics

### Requirement: Model callback adapter over agent_reply

The module SHALL expose `backend/evals/chatbot/simulate.py::model_callback(input: str, turns: list[Turn], thread_id: str) -> Turn` as an async function. It MUST convert `turns` into the `list[dict]` history shape (`{"role", "content"}`) expected by the frozen P3 helper and call `backend.agent.loop.agent_reply(user_message, history, session)` with a fixed evaluation `SessionContext`, receiving an `AgentReply`. It MUST return a `deepeval.test_case.Turn` with `role="assistant"`, `content = reply.text`, `retrieval_context = reply.retrieval_context` (the RAW retrieved chunk texts), and `tools_called = [ToolCall(name=t.name, input_parameters=t.input, output=t.output) for t in reply.tools_called]`. It MUST associate the call with the provided `thread_id` so that each simulated conversation becomes a distinct Confident AI thread. The adapter MUST NOT modify `agent_reply` or any frozen contract.

#### Scenario: Callback returns an assistant Turn
- **WHEN** `model_callback("What are the brokerage charges?", turns, thread_id)` is awaited
- **THEN** it calls `agent_reply` with a `list[dict]` history and the eval `SessionContext`, and returns a `Turn` whose `role == "assistant"` and whose `content` equals `reply.text` returned by `agent_reply`

#### Scenario: Retrieval context and tools mapped from AgentReply
- **WHEN** `agent_reply` returns an `AgentReply` with a non-empty `retrieval_context` and `tools_called`
- **THEN** the returned `Turn.retrieval_context` is that list of RAW retrieved chunk texts and `Turn.tools_called` is a list of `ToolCall`s built from `reply.tools_called` (each carrying `name`, `input_parameters`, and `output`)

#### Scenario: Thread grouping for Confident AI
- **WHEN** `model_callback` is invoked with a `thread_id`
- **THEN** the resulting trace is tagged with that `thread_id` so all turns of one simulation are grouped into a single Confident AI thread

### Requirement: Simulation and evaluation runner

The module SHALL expose `backend/evals/chatbot/run_eval.py::main() -> None`. It MUST call P8 `configure_tracing()` before simulating, construct a `ConversationSimulator(model_callback=model_callback, simulator_model=...)`, call `simulate(...)` over `build_goldens()` with a bounded per-conversation turn limit, set `chatbot_role = CHATBOT_ROLE` on each resulting `ConversationalTestCase`, and pass the test cases to `deepeval.evaluate(test_cases=..., metrics=...)`. The runner SHALL be invocable via `deepeval test run backend/evals/chatbot/` or `pytest backend/evals/chatbot/`.

#### Scenario: End-to-end simulate then evaluate
- **WHEN** `main()` runs
- **THEN** it enables tracing, simulates a conversation per golden through `model_callback`, and evaluates the resulting `ConversationalTestCase`s with the configured metric list, producing a scored test run

#### Scenario: Chatbot role attached before scoring
- **WHEN** the runner prepares test cases for evaluation
- **THEN** every `ConversationalTestCase` has `chatbot_role` set to `CHATBOT_ROLE` so `RoleAdherenceMetric` can score it

### Requirement: Conversation metric coverage

The runner SHALL evaluate every simulated conversation against exactly these seven DeepEval conversation metrics: `ConversationCompletenessMetric`, `KnowledgeRetentionMetric`, `TurnRelevancyMetric`, `RoleAdherenceMetric`, `TopicAdherenceMetric`, `ToolUseMetric`, and `GoalAccuracyMetric`. `TopicAdherenceMetric` MUST be constructed with `relevant_topics=RELEVANT_TOPICS`. `ToolUseMetric` MUST be constructed with `available_tools` derived from the shared `RAG_TOOL`, `CML_REPORT_TOOL`, and `CONTRACT_NOTE_TOOL` definitions. Each metric MUST carry an explicit `threshold` (0.7, with `RoleAdherenceMetric` at 0.8 as the guardrail bar).

#### Scenario: All seven metrics present with thresholds
- **WHEN** the metric list is built
- **THEN** it contains the seven named metrics, each with an explicit `threshold`, `TopicAdherenceMetric` carries `RELEVANT_TOPICS`, and `ToolUseMetric` carries the three shared tool definitions as `available_tools`

### Requirement: Confident AI thread logging and metric collection

The evaluation SHALL export conversation threads to Confident AI via the P8 tracing configuration (using `settings.confident_api_key`). The change documentation SHALL instruct operators to create a multi-turn metric collection in the Confident AI UI containing the seven conversation metrics for asynchronous scoring of production threads.

#### Scenario: Threads exported when Confident AI is configured
- **WHEN** `main()` runs with `CONFIDENT_API_KEY` configured
- **THEN** each simulated conversation is logged to Confident AI as a distinct thread keyed by its `thread_id`

#### Scenario: Metric collection documented
- **WHEN** an operator follows the change's tasks
- **THEN** they are instructed to create a multi-turn metric collection in the Confident AI UI holding the seven conversation metrics
