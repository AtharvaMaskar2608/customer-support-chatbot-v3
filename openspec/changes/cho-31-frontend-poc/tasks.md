## 1. Scaffolding & theme

- [ ] 1.1 Create `frontend/index.html` (login) and `frontend/chat.html` (chat) shells with Tailwind CDN `<script src="https://cdn.tailwindcss.com">`, minimal white & blue theme, both loading `frontend/app.js` (type=module)
- [ ] 1.2 Create `frontend/styles.css` for the few custom rules Tailwind utilities cannot express (e.g. streaming caret); keep near-empty if unused
- [ ] 1.3 Add `API_BASE` config constant at the top of `frontend/app.js` (empty string for same-origin)

## 2. Login page (`qa-login`)

- [ ] 2.1 Build the login form with Client code + Session token inputs, submit button, and an inline error slot (`#login-error`)
- [ ] 2.2 On submit: `trim()` both inputs, block submit if either is empty, `POST /api/session` with `{client_code, session_token}`
- [ ] 2.3 On `{ok:true}`: store the session token in `sessionStorage` and `location.assign("chat.html")`; on failure show inline error, stay on page
- [ ] 2.4 In the chat controller, redirect to `index.html` when no stored session token is present

## 3. Streaming core (`chat-streaming-ui`)

- [ ] 3.1 Implement `streamChat(message, threadId, handlers)` using `fetch` + `res.body.getReader()` + `TextDecoder`, buffering and splitting on `\n\n`
- [ ] 3.2 Implement `parseFrame(rawFrame)` (strip `data:` prefix, join multi-line data, `JSON.parse` → `SSEEvent` or null) and `dispatchEvent(evt, handlers)` routing on `evt.type`
- [ ] 3.3 Wire the composer: trim input, disable while streaming, append user bubble, create assistant message node, call `streamChat`, re-enable on `done`/`error`

## 4. Event → UI mapping (`chat-streaming-ui`)

- [ ] 4.1 `StepEvent` → `setStatus()` transient status line; cleared on first token
- [ ] 4.2 `TokenEvent` → `appendToken()` streaming append; clears status on first token
- [ ] 4.3 `CitationsEvent` → `renderCitations()` hoverable card at end of message (only when non-empty), values via `textContent`, section/topic fallback "—"
- [ ] 4.4 `DoneEvent` → `renderMessageCost()` per-message ₹cost/latency row + `updateCostCard()` cumulative INR + re-enable composer
- [ ] 4.5 `ErrorEvent` → inline error in message body + finalize, no cost row

## 5. Cost UI (`chat-streaming-ui`)

- [ ] 5.1 Add the top-left fixed cumulative cost card (`#cost-card`, `hidden sm:block`), formatted `₹` + `toFixed(4)` from `cumulative_cost_inr`
- [ ] 5.2 Add the per-message cost/latency row (`₹cost_inr.toFixed(4) · latency_ms ms`) below every finalized assistant message, visible on all widths

## 6. Verification

- [ ] 6.1 Manual `/qa` browser pass (manual; no unit test harness exists for this POC): serve `frontend/` statically with the P4 API reachable, then log in (verify inputs are trimmed and `/api/session` succeeds), ask a question, and confirm: transient step status → streamed tokens → hoverable citation card → `done` finalizes with per-message ₹cost/latency and the top-left cumulative INR card updates
- [ ] 6.2 Manual responsive check: at a mobile viewport the layout reflows with no horizontal scroll and the cumulative cost card is hidden while per-message cost rows remain visible
- [ ] 6.3 Manual failure check: a failed `/api/session` shows an inline error without navigating; direct `chat.html` access with no session redirects to `index.html`
