## Why

QA testers need a runnable UI to exercise the agent end-to-end: log in with a client code + session token, ask questions, and watch the streamed answer, citations, and cost/latency. This is a throwaway POC (vanilla HTML/CSS/JS + Tailwind CDN, no build step) that consumes the P4 endpoints only and ships nothing the backend depends on.

## What Changes

- Add a static **login page** (`frontend/index.html`) with two inputs — Client code and Session token — that trims/strips whitespace on all inputs, `POST`s `/api/session`, and on success navigates to the chat view. The session token is retained (in-memory/`sessionStorage`) for the chat page.
- Add a **chat view** (`frontend/chat.html` + `frontend/app.js`) with a message composer that `POST`s `/api/chat` and consumes the response as an **SSE stream over `fetch` + `ReadableStream`** (not `EventSource`, which only supports `GET`), mapping each `SSEEvent` to UI: `StepEvent` → transient status line, `TokenEvent` → streamed message text, `CitationsEvent` → hoverable citation card at the end of the message, `DoneEvent` → finalize + costs, `ErrorEvent` → inline error.
- Add a **cost card** fixed in the top-left corner (web view) showing cumulative conversation cost in INR, updated from `DoneEvent.cumulative_cost_inr`.
- Show **per-message cost (INR) and latency (ms)** below every assistant message, from `DoneEvent.cost` (`MessageCost`).
- Minimal white & blue theme, mobile responsive, via Tailwind CDN (`frontend/styles.css` for the handful of custom rules Tailwind utilities cannot express).
- No backend, schema, or dependency changes. Frontend consumes the P0 SSE/citation contracts and the P4 live endpoints.

Non-goals: authentication beyond passing the token through; message persistence/history storage; any build tooling or npm dependency; production hardening. This is a manual-QA POC.

## Capabilities

### New Capabilities
- `qa-login`: Static login page that trims inputs, calls `POST /api/session`, retains the session token, and routes to chat on success.
- `chat-streaming-ui`: Chat view that streams `POST /api/chat` via `fetch`+`ReadableStream`, maps each `SSEEvent` type to UI (status, token, citations, done, error), renders a hoverable citation card, a top-left cumulative INR cost card, and per-message cost/latency.

### Modified Capabilities
<!-- None — greenfield frontend; consumes existing P0/P4 contracts, declares no new backend spec. -->

## Impact

- **New code (owned):** `frontend/index.html`, `frontend/chat.html`, `frontend/app.js`, `frontend/styles.css`. No files outside `frontend/` are touched.
- **Dependencies:** none installed — Tailwind is loaded from CDN at runtime; no lockfile, no build step.
- **Upstream deps:** P0 `foundations-and-contracts` (SSE event + `Citation` + `MessageCost` shapes) and P4 `api-sse-session` (live `POST /api/session` and `POST /api/chat` endpoints). Both must be in `main` for the manual flow to pass.
- **Downstream:** none — no other module imports the frontend.
