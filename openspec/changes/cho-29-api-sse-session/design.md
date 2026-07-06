## Context

This is P4, the HTTP layer. It owns `backend/api/` and the server entrypoint only. It imports the P0 shared contracts (do not re-declare): `SessionContext` (`backend/schemas/session.py`), the `SSEEvent` union and its members (`backend/schemas/sse.py`), `MessageCost`/`ConversationCost` (`backend/schemas/cost.py`), and `Citation` (`backend/schemas/rag.py`). It consumes P3 `backend/agent/loop.py::run_agent_turn(...)` (an `AsyncIterator[SSEEvent]`) and P8 `backend/tracing/setup.py::configure_tracing()` + `new_thread_id()`. It does not implement retrieval, agent, or tool logic.

The frontend (P5) is the sole consumer: it POSTs login inputs to `/api/session`, receives a `thread_id`, then POSTs each user message to `/api/chat` and renders the SSE frames (step messages, streamed tokens, citations card, and a terminal done frame carrying per-message cost/latency and the cumulative INR card value).

## Goals / Non-Goals

**Goals:**
- Two endpoints with fully concrete request/response schemas and status codes.
- A single deterministic mapping from agent `SSEEvent`s to SSE wire frames.
- Per-`thread_id` server-side session, conversation history, and cumulative cost, so the agent gets prior context and the frontend gets running INR totals.
- Testable end-to-end with the agent mocked (`pytest backend/tests/test_api.py`).

**Non-Goals:**
- Durable/shared session storage (in-memory dict; process-local; POC-acceptable).
- Auth beyond client-code + session-token capture.
- Backpressure, rate limiting, reconnection/resume of SSE streams.

## Decisions

### D1. FastAPI app + entrypoint

`backend/api/app.py` exposes a module-level `app: FastAPI` (`create_app() -> FastAPI` factory called at import). Responsibilities:
- On startup (`@app.on_event("startup")` or lifespan), call `configure_tracing()` once.
- Add `CORSMiddleware` allowing the POC frontend origin(s) (`allow_origins=["*"]` for the POC), methods `["POST"]`, all headers.
- Include the two routers from `routes_session.py` and `routes_chat.py`.

Server entrypoint `backend/api/__main__.py` (runnable as `python -m backend.api`) calls `uvicorn.run("backend.api.app:app", host="0.0.0.0", port=8000)`.

### D2. Request/response models (Pydantic v2, local to the API layer)

Declared in the route modules (these are HTTP DTOs, not cross-module contracts):

```python
# routes_session.py
class SessionRequest(BaseModel):
    client_code: str
    session_token: str

class SessionResponse(BaseModel):
    ok: bool = True
    thread_id: str

class ErrorResponse(BaseModel):
    error: str

# routes_chat.py
class ChatRequest(BaseModel):
    message: str
    thread_id: str
```

### D3. `POST /api/session`

- **Method / path:** `POST /api/session`
- **Request body:** `SessionRequest` — `{client_code: str, session_token: str}`.
- **Handler contract:** `async def create_session(req: SessionRequest) -> SessionResponse`.
- **Behavior:** trim both fields (`.strip()`); if either is empty after trim, return `400` with `ErrorResponse{error: "client_code and session_token are required"}`. Otherwise build `SessionContext(client_code=<trimmed>, session_token=<trimmed>)`, mint `thread_id = new_thread_id()` (P8), store via `store.create(thread_id, ctx)`, and return `200 SessionResponse{ok: true, thread_id}`.
- **Responses:**
  - `200` → `{"ok": true, "thread_id": "<str>"}`
  - `400` → `{"error": "<message>"}`

### D4. `POST /api/chat`

- **Method / path:** `POST /api/chat`
- **Request body:** `ChatRequest` — `{message: str, thread_id: str}`.
- **Handler contract:** `async def chat(req: ChatRequest) -> StreamingResponse`.
- **Response media type:** `text/event-stream`.
- **Response headers:** `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` (disable proxy buffering).
- **Validation:** trim `message`; if empty → the stream emits a single `ErrorEvent{message:"message is required"}` frame then closes. If `thread_id` is unknown to the store → the stream emits a single `ErrorEvent{message:"unknown thread_id"}` frame then closes. (Errors are surfaced as SSE `error` frames, not HTTP status codes, because the response has already committed to `text/event-stream`; a request-shape failure — malformed JSON / missing field — still yields FastAPI's `422`.)
- **Streaming body:** an async generator (`_chat_stream`) that:
  1. Looks up `session = store.get_session(thread_id)` and `history = store.get_history(thread_id)`.
  2. Iterates `async for event in run_agent_turn(user_message=message, history=history, session=session, thread_id=thread_id)` (P3).
  3. For each `event`, `yield format_sse(event)`.
  4. Accumulates the assistant's answer text from `TokenEvent.text` and citations from `CitationsEvent.citations`.
  5. On the `DoneEvent`: record cost via `store.record_turn(...)` (see D6) — the `DoneEvent.cost` is the message `MessageCost` and `DoneEvent.cumulative_cost_inr` is the store's cumulative INR **after** this turn. If the incoming `DoneEvent.cumulative_cost_inr` from the agent is unset/zero, the API overwrites it with the store's cumulative value before framing (the API is the authority on cumulative cost).
  6. After the stream ends, append the user turn and the assembled assistant turn to `history`.

### D5. SSE framing — `backend/api/sse.py`

```python
def format_sse(event: SSEEvent) -> str:
    """Serialize one agent SSE event to a single wire frame."""
    payload = event.model_dump()            # pydantic v2; includes discriminator "type"
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
```

- Frame format is exactly `data: <compact-json>\n\n` (one blank line terminates the frame). No `event:` line — the discriminator lives inside the JSON `type` field, matching the P0 contract.
- The generator yields these `str` frames; `StreamingResponse(_chat_stream(...), media_type="text/event-stream", headers=SSE_HEADERS)` writes them.

### D6. Session / history / cost store — `backend/api/state.py`

Process-local, in-memory, thread-keyed. One record per `thread_id`:

```python
@dataclass
class ThreadState:
    session: SessionContext
    history: list[dict]          # Anthropic-style messages: {"role": "user"|"assistant", "content": str}
    cost: ConversationCost       # cumulative_cost_inr + messages: list[MessageCost]

class SessionStore:
    _threads: dict[str, ThreadState]

    def create(self, thread_id: str, session: SessionContext) -> None: ...
    def exists(self, thread_id: str) -> bool: ...
    def get_session(self, thread_id: str) -> SessionContext: ...      # raises KeyError if unknown
    def get_history(self, thread_id: str) -> list[dict]: ...
    def append_turn(self, thread_id: str, user_message: str, assistant_message: str) -> None: ...
    def record_turn(self, thread_id: str, cost: MessageCost) -> float: ...
        # appends cost to cost.messages, adds cost.cost_inr to cost.cumulative_cost_inr,
        # returns the new cumulative_cost_inr

store = SessionStore()   # module-level singleton imported by both routers
```

- **History model:** ordered list of `{"role", "content"}` dicts, the shape P3 `run_agent_turn(history=...)` expects. The API passes the current history *before* the new user message (P3 receives `user_message` separately), then appends both the user message and the assembled assistant answer after the turn completes.
- **Cost model:** `record_turn` is the single source of truth for cumulative INR; `cumulative_cost_inr` always equals `sum(m.cost_inr for m in cost.messages)`.

### D7. Wire mapping (agent SSEEvent → frame)

| Agent event (P0) | Wire frame emitted | API side effect |
|---|---|---|
| `StepEvent{message}` | `data: {"type":"step","message":...}\n\n` | none |
| `TokenEvent{text}` | `data: {"type":"token","text":...}\n\n` | append `text` to assistant buffer |
| `CitationsEvent{citations}` | `data: {"type":"citations","citations":[...]}\n\n` | capture citations |
| `DoneEvent{cost, cumulative_cost_inr}` | `data: {"type":"done","cost":{...},"cumulative_cost_inr":<store total>}\n\n` | `record_turn(cost)`; overwrite cumulative with store total |
| `ErrorEvent{message}` | `data: {"type":"error","message":...}\n\n` | terminate stream; no history/cost mutation |

Ordering over a normal turn: one-or-more `step` → zero-or-more `token` → optional `citations` → exactly one `done`. On failure: exactly one `error`, no `done`.

## Risks / Trade-offs

- **[In-memory store]** → sessions and history are lost on process restart and not shared across workers. Mitigation: POC runs single-process; the `SessionStore` interface is swappable for Redis/DB later without changing routes.
- **[Cumulative-cost authority split]** → both the agent (`DoneEvent.cumulative_cost_inr`) and the API track cumulative INR. Decision: the API store is authoritative and overwrites the frame's cumulative value, so the frontend card is always consistent with server-side accounting.
- **[Errors as SSE frames, not HTTP codes]** → once `text/event-stream` is committed, mid-turn failures cannot change the HTTP status; the frontend must treat an `error` frame as terminal. Request-shape errors still surface as `422`/`400` before streaming starts.
- **[No SSE resume]** → a dropped connection loses the in-flight turn; acceptable for the POC.

## Migration Plan

Greenfield module; no data migration. Requires P0 (schemas + FastAPI/uvicorn in requirements), P3 (`run_agent_turn`), and P8 (`configure_tracing`, `new_thread_id`) merged to `main` first. Tests mock `run_agent_turn` so P4 can be verified before P3 lands.

## Open Questions

- Exact CORS origin(s) for the deployed POC frontend (currently `*`).
- Whether `history` should be capped at the P3 10-message limit inside the store or left to P3's guardrail (current decision: P3 owns the cap; the store retains full history).
