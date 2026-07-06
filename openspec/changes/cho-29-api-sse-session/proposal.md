## Why

The POC frontend and QA testers need one HTTP surface to start a session and stream agent answers. This change adds the FastAPI layer that turns the P0 SSE contracts and the P3 `run_agent_turn` async stream into a live `text/event-stream`, while owning session state, per-thread conversation history, and cumulative INR cost accounting. It is the only module that binds the agent to the wire.

## What Changes

- Add a FastAPI application (`backend/api/app.py`) and a server entrypoint that mounts two routes, applies CORS for the POC frontend, and configures tracing at startup via P8 `configure_tracing()`.
- Add `POST /api/session`: validates trimmed `{client_code, session_token}`, mints/returns a server-side `thread_id` (via P8 `new_thread_id()`), and stores the `SessionContext` in an in-memory store. Empty-after-trim inputs return `400`.
- Add `POST /api/chat`: for a known `thread_id`, streams the `SSEEvent` frames yielded by P3 `run_agent_turn(...)` as `data: <json>\n\n` with SSE headers. Appends the user turn and the assistant turn to per-thread history, and updates the per-thread `ConversationCost`; each `DoneEvent` carries the message `MessageCost` and the updated cumulative INR.
- Add `backend/api/sse.py::format_sse(event: SSEEvent) -> str` (frame serializer) and `backend/api/state.py` (thread-keyed in-memory session + history + cost store).
- Do NOT implement agent logic, retrieval, tools, or frontend — those are consumed from P3/P0 and consumed by P5.

Non-goals: persistence/durability of sessions (in-memory only for the POC), auth beyond client-code + session-token entry, rate limiting.

## Capabilities

### New Capabilities
- `chat-sse-api`: The `POST /api/chat` streaming endpoint plus SSE framing helper — maps agent `SSEEvent`s to the wire and maintains per-thread history and cumulative cost.
- `session-management`: The `POST /api/session` endpoint plus the in-memory thread-keyed store holding each thread's `SessionContext`, history, and `ConversationCost`.

### Modified Capabilities
<!-- None — greenfield module consuming P0 contracts. -->

## Impact

- **New code:** `backend/api/` (`app.py`, `routes_session.py`, `routes_chat.py`, `sse.py`, `state.py`), server entrypoint, `backend/tests/test_api.py`.
- **Dependencies:** consumes P0 schemas (`SessionContext`, `SSEEvent` union, `MessageCost`, `ConversationCost`, `Citation`), P3 `run_agent_turn`, P8 `configure_tracing`/`new_thread_id`. Adds no new libraries (FastAPI/uvicorn owned by P0 requirements).
- **Downstream:** unblocks P5 frontend, which consumes `/api/session` and `/api/chat` SSE exactly as specified here.
