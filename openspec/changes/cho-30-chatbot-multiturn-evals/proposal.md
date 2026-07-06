## Why

The Choice FinX support chatbot (P3 agentic loop) succeeds or fails across a whole conversation, not a single turn: it must retain facts (mobile number, client code) across turns, stay in its support-agent role, refuse SEBI-regulated investment advice, keep clarifying questions capped, offer a support ticket at the message cap, and pick the right FinX tool. None of that is measurable with single-turn RAG evals (P6). This change adds an end-to-end multi-turn benchmark that simulates realistic conversations against the real agent and scores them with DeepEval conversation metrics, exporting every thread to Confident AI.

## What Changes

- Add `backend/evals/chatbot/goldens.py` — `build_goldens() -> list[ConversationalGolden]`: >=20 diverse scenarios (personas + guardrail probes: SEBI advice-seeking, off-topic, clarifying-question cap, ticket-offer at cap).
- Add `backend/evals/chatbot/simulate.py` — async `model_callback(input, turns, thread_id) -> Turn`: an adapter that calls the frozen P3 `agent_reply(...)` and maps the returned `AgentReply` onto a DeepEval `Turn` (`content=reply.text`, `retrieval_context=reply.retrieval_context` raw chunk texts, `tools_called` from `reply.tools_called`), grouping each conversation under `thread_id` for Confident AI.
- Add `backend/evals/chatbot/run_eval.py` — `main()`: wires `ConversationSimulator(model_callback, simulator_model)` -> `simulate(...)` -> `evaluate(test_cases, metrics)` over the seven prescribed conversation metrics, logging threads to Confident AI.
- Consume (do not modify): P3 `backend.agent.loop.agent_reply`, P8 `backend.tracing.setup.configure_tracing`, the `deepeval` dependency provided by P0's `requirements-eval.txt`, and the shared schemas (`Citation`, `SessionContext`, `MessageCost`) plus tool definitions from P0.

Non-goals: no changes to `requirements*.txt`, migrations, or root config; no agent/retrieval/tool logic (owned by P1–P3); no single-turn RAG evals (owned by P6).

## Capabilities

### New Capabilities
- `chatbot-multiturn-evaluation`: Scenario-driven multi-turn evaluation of the support agent via the DeepEval `ConversationSimulator` and conversation metrics, with Confident AI thread logging.

### Modified Capabilities
<!-- None — greenfield; consumes frozen P3/P8 contracts. -->

## Impact

- **New code:** `backend/evals/chatbot/{goldens.py,simulate.py,run_eval.py}` (and `__init__.py`). No other files touched.
- **Dependencies:** `deepeval` only, already declared by P0's `backend/requirements-eval.txt`. This change adds nothing to any requirements file.
- **Upstream deps:** P0 (schemas, settings, `deepeval`), P3 (`agent_reply`), P8 (`configure_tracing`). Blocks nothing downstream.
- **External:** requires `CONFIDENT_API_KEY` (`deepeval login`) and a multi-turn metric collection created in the Confident AI UI for async production thread scoring.
