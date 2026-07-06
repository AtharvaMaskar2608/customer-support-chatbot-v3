## 1. Package scaffold
- [ ] 1.1 Create `backend/evals/chatbot/__init__.py` (and `backend/evals/__init__.py` if absent). Do NOT touch any `requirements*.txt`.
- [ ] 1.2 Confirm upstream deps import: `from backend.agent.loop import agent_reply`, `from backend.tracing.setup import configure_tracing`, `from backend.schemas.tools import RAG_TOOL, CML_REPORT_TOOL, CONTRACT_NOTE_TOOL`, `from backend.config.settings import get_settings`.

## 2. Goldens
- [ ] 2.1 Implement `goldens.py::build_goldens() -> list[ConversationalGolden]` with >=20 goldens; export `CHATBOT_ROLE: str` and `RELEVANT_TOPICS: list[str]`.
- [ ] 2.2 Cover personas: new/non-technical, frustrated repeat-contact, verbose, multi-topic, retention (early-given mobile number).
- [ ] 2.3 Include tool-use goldens: valid CML request, contract-note with date, invalid-then-corrected number, missing-date clarify, CML-vs-contract-note disambiguation.
- [ ] 2.4 Include the four guardrail probes: SEBI advice-seeking (x>=2 personas), off-topic/out-of-scope (incl. persistent rephrase), <=2 clarifying-question cap, ticket-offer at <=10 message cap.
- [ ] 2.5 Done: `python -c "from backend.evals.chatbot.goldens import build_goldens; g=build_goldens(); assert len(g)>=20 and all(x.scenario and x.expected_outcome and x.user_description for x in g)"`.

## 3. Model callback adapter
- [ ] 3.1 Implement `simulate.py::model_callback(input, turns, thread_id) -> Turn` (async): build `list[dict]` history from `turns`, call `agent_reply(input, history, EVAL_SESSION)`.
- [ ] 3.2 Map the `AgentReply` return onto the `Turn`: `content=reply.text`, `retrieval_context=reply.retrieval_context` (RAW chunk texts), `tools_called=[ToolCall(name=t.name, input_parameters=t.input, output=t.output) for t in reply.tools_called]`, `role="assistant"`.
- [ ] 3.3 Group the conversation into a Confident AI thread using `thread_id` (verify the trace-thread setter against installed deepeval — OQ4).
- [ ] 3.5 Wire the eval `SessionContext` token (OQ3): env-gated real FinX token or mock; ensure non-tool goldens run without it.

## 4. Runner
- [ ] 4.1 Implement `run_eval.py::main()`: `configure_tracing()`, build `ConversationSimulator(model_callback, simulator_model="gpt-4.1")`, call `simulate(...)` with bounded turns.
- [ ] 4.2 Reconcile `simulate()` kwargs against installed deepeval (OQ1: `conversational_goldens=` / `max_user_simulations=`).
- [ ] 4.3 Set `chatbot_role = CHATBOT_ROLE` on each `ConversationalTestCase`.
- [ ] 4.4 Build the seven metrics with thresholds (0.7; RoleAdherence 0.8); pass `RELEVANT_TOPICS` to `TopicAdherenceMetric` and the three shared tool defs to `ToolUseMetric.available_tools`.
- [ ] 4.5 Call `evaluate(test_cases=..., metrics=...)`; add a `pytest`-discoverable entry (e.g. `test_multiturn_eval`) wrapping `main()`.

## 5. Confident AI
- [ ] 5.1 Ensure `CONFIDENT_API_KEY` is set (`deepeval login`); confirm threads appear keyed by `thread_id`.
- [ ] 5.2 Create a multi-turn metric collection in the Confident AI UI containing the seven conversation metrics for async production thread scoring.

## 6. Verification
- [ ] 6.1 Run `deepeval test run backend/evals/chatbot/` (or `pytest backend/evals/chatbot/`) and confirm a scored multi-turn run over all goldens.
- [ ] 6.2 Confirm every conversation is scored by all seven metrics and each simulation appears as a distinct Confident AI thread.
- [ ] 6.3 Run `openspec validate chatbot-multiturn-evals` and confirm it is valid.
