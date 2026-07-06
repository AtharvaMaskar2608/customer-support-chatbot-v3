## ADDED Requirements

### Requirement: Login page with trimmed client code and session token
The system SHALL present a static login page (`frontend/index.html`) with exactly two text inputs — **Client code** and **Session token** — and a submit control. Before use, both values MUST be whitespace-trimmed (leading/trailing stripped via `String.prototype.trim()`). The trimmed values SHALL be sent to `POST /api/session` with request body `{ "client_code": <trimmed>, "session_token": <trimmed> }`. The page MUST NOT submit if either trimmed value is empty.

#### Scenario: Inputs are trimmed before submit
- **WHEN** the tester enters "  ABC123  " as client code and "  jwt.token.value  " as session token and submits
- **THEN** the request body sent to `POST /api/session` is `{"client_code":"ABC123","session_token":"jwt.token.value"}` with no surrounding whitespace

#### Scenario: Empty input blocks submit
- **WHEN** the tester submits with either field blank or whitespace-only
- **THEN** no request is sent and an inline validation message is shown

### Requirement: Session established then navigate to chat
On a successful `POST /api/session` response (`{ "ok": true }`), the system SHALL retain the session token (`sessionStorage`) for use by the chat page and navigate the browser to `chat.html`. On a non-ok response or network error, it SHALL show an inline error and remain on the login page without navigating.

#### Scenario: Successful session start
- **WHEN** `POST /api/session` returns `{"ok": true}`
- **THEN** the session token is stored for the chat page and the browser navigates to `chat.html`

#### Scenario: Failed session start
- **WHEN** `POST /api/session` returns a non-2xx status or the request errors
- **THEN** an inline error message is shown and the browser stays on the login page

### Requirement: Chat page requires an established session
The chat page (`chat.html`) SHALL redirect back to `index.html` when no session token is present in `sessionStorage`, so testers cannot reach the chat view without logging in.

#### Scenario: Direct chat access without a session
- **WHEN** `chat.html` is opened with no stored session token
- **THEN** the browser is redirected to `index.html`
