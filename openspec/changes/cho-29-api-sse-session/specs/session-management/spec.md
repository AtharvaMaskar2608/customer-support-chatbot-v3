## ADDED Requirements

### Requirement: Create-session endpoint
The system SHALL expose `POST /api/session` accepting `SessionRequest{client_code: str, session_token: str}` and returning `200 SessionResponse{ok: true, thread_id: str}`. The handler `async def create_session(req: SessionRequest) -> SessionResponse` SHALL trim (`.strip()`) both fields, construct `SessionContext(client_code, session_token)` from the trimmed values, mint `thread_id = new_thread_id()` (P8), store the `SessionContext` in the in-memory `SessionStore` keyed by `thread_id`, and return the `thread_id`.

#### Scenario: Valid inputs create a session and return a thread id
- **WHEN** `POST /api/session` receives `{"client_code":"  CL01 ","session_token":" jwt.abc "}`
- **THEN** the response is `200` with `{"ok": true, "thread_id": "<non-empty str>"}`, and the store holds a `SessionContext` for that `thread_id` with `client_code == "CL01"` and `session_token == "jwt.abc"`

#### Scenario: Empty-after-trim inputs are rejected
- **WHEN** `POST /api/session` receives `client_code` or `session_token` that is empty or whitespace-only after trimming
- **THEN** the response is `400` with body `{"error": "client_code and session_token are required"}` and no session is stored

### Requirement: In-memory thread-keyed session store
The system SHALL provide `backend/api/state.py` with a module-level `store: SessionStore` singleton holding one `ThreadState{session: SessionContext, history: list[dict], cost: ConversationCost}` per `thread_id`. `SessionStore` SHALL expose `create(thread_id, session) -> None`, `exists(thread_id) -> bool`, `get_session(thread_id) -> SessionContext`, `get_history(thread_id) -> list[dict]`, `append_turn(thread_id, user_message, assistant_message) -> None`, and `record_turn(thread_id, cost: MessageCost) -> float`. `history` entries SHALL be Anthropic-style `{"role": "user"|"assistant", "content": str}` dicts.

#### Scenario: Session is retrievable by thread id after creation
- **WHEN** `create(thread_id, ctx)` has run
- **THEN** `exists(thread_id)` is `True`, `get_session(thread_id)` returns `ctx`, and `get_history(thread_id)` returns an empty list

#### Scenario: Unknown thread id has no state
- **WHEN** a `thread_id` that was never created is queried
- **THEN** `exists(thread_id)` is `False` and `get_session(thread_id)` raises `KeyError`
