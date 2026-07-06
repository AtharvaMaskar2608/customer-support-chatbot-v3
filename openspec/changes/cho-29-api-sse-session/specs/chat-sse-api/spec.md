## ADDED Requirements

### Requirement: Chat streaming endpoint
The system SHALL expose `POST /api/chat` accepting `ChatRequest{message: str, thread_id: str}` and returning a `StreamingResponse` with media type `text/event-stream`. The handler `async def chat(req: ChatRequest) -> StreamingResponse` SHALL look up the `SessionContext` and conversation history for `thread_id` from the `SessionStore`, then stream the frames produced by iterating `run_agent_turn(user_message=message, history=history, session=session, thread_id=thread_id)` (P3). The response SHALL set headers `Content-Type: text/event-stream`, `Cache-Control: no-cache`, and `Connection: keep-alive`.

#### Scenario: Turn streams step, token, citations, then done
- **WHEN** `POST /api/chat` is called with a known `thread_id` and a message that triggers retrieval
- **THEN** the response is `text/event-stream` and emits one or more `step` frames, then `token` frames, then a `citations` frame, then exactly one terminal `done` frame, each as `data: <json>\n\n`

#### Scenario: Unknown thread id yields an error frame
- **WHEN** `POST /api/chat` is called with a `thread_id` not present in the store
- **THEN** the stream emits exactly one `error` frame with `{"type":"error","message":"unknown thread_id"}` and no `done` frame

#### Scenario: Empty message yields an error frame
- **WHEN** `POST /api/chat` is called with a `message` that is empty or whitespace-only after trimming
- **THEN** the stream emits exactly one `error` frame with `{"type":"error","message":"message is required"}` and no `done` frame

### Requirement: SSE frame serialization
The system SHALL provide `backend/api/sse.py::format_sse(event: SSEEvent) -> str` that serializes exactly one agent `SSEEvent` to a wire frame of the form `data: <compact-json>\n\n`, where the JSON is the event's `model_dump()` including its `type` discriminator, and the frame is terminated by a single blank line. No `event:` line SHALL be emitted; the type lives inside the JSON payload per the P0 SSE contract.

#### Scenario: Each event type serializes to a data frame
- **WHEN** `format_sse` is given a `StepEvent`, `TokenEvent`, `CitationsEvent`, `DoneEvent`, or `ErrorEvent`
- **THEN** it returns a string beginning with `data: ` and ending with `\n\n`, whose JSON body round-trips to the same event and carries the correct `type` value

### Requirement: Per-thread history and cumulative cost accounting
The system SHALL maintain, per `thread_id`, the conversation history and the cumulative `ConversationCost`. On each `/api/chat` turn the API SHALL accumulate the assistant answer from `TokenEvent.text` and, on the terminal `DoneEvent`, record the message `MessageCost` via `store.record_turn(...)` so that `ConversationCost.cumulative_cost_inr` equals the sum of all recorded `MessageCost.cost_inr`. The `DoneEvent` frame written to the wire SHALL carry that message's `MessageCost` and the store's updated cumulative INR (the API store is authoritative for cumulative cost). After the stream completes, the API SHALL append the user message and the assembled assistant message to the thread's history via `store.append_turn(...)`.

#### Scenario: Done frame reports message cost and updated cumulative INR
- **WHEN** a turn completes with a `DoneEvent` carrying a `MessageCost`
- **THEN** the emitted `done` frame contains that `MessageCost` and a `cumulative_cost_inr` equal to the prior cumulative plus this message's `cost_inr`

#### Scenario: History grows by one user and one assistant turn
- **WHEN** a `/api/chat` turn for a `thread_id` completes successfully
- **THEN** the thread's history has one appended `{"role":"user"}` entry with the trimmed message and one appended `{"role":"assistant"}` entry with the streamed answer text, and the next turn passes that history to `run_agent_turn`

#### Scenario: Failed turn does not mutate cost or history
- **WHEN** a turn emits an `error` frame instead of a `done` frame
- **THEN** the thread's `cumulative_cost_inr` and history are unchanged
