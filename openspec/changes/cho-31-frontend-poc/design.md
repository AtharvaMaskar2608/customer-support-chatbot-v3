## Context

The POC frontend is a QA harness for the agent. It is intentionally build-free: two static HTML pages plus one JS module, styled with Tailwind loaded from CDN. It consumes exactly two backend endpoints from P4 `api-sse-session` and the shared event/citation/cost contracts from P0 `foundations-and-contracts`. It owns only files under `frontend/` and touches no backend code.

The one non-trivial technical decision is how to consume the chat stream. The endpoint is `POST /api/chat` returning `text/event-stream`. The browser's native `EventSource` API only issues `GET` requests and cannot set a request body, so it cannot be used here. Instead we use `fetch()` with a `ReadableStream` reader and parse SSE frames manually.

The fixed upstream contracts (do not re-declare):
- `POST /api/session` — body `{client_code, session_token}` → `{"ok": true}`.
- `POST /api/chat` — body `{message, thread_id?}` → `text/event-stream` of `SSEEvent` frames.
- `SSEEvent = StepEvent | TokenEvent | CitationsEvent | DoneEvent | ErrorEvent`, discriminated on `type`.
- `Citation{source, section?, topic?}`; `MessageCost{input_tokens, output_tokens, cost_inr, latency_ms}`; `DoneEvent{type:"done", cost: MessageCost, cumulative_cost_inr}`.

## Goals / Non-Goals

**Goals:**
- Runnable with no build step: open `frontend/index.html` (served statically) and go.
- Correct SSE consumption for a POST endpoint via `fetch` + `ReadableStream`.
- Exact, documented event→UI mapping for all five `SSEEvent` types.
- Visible cost transparency: top-left cumulative INR card + per-message cost/latency.
- Minimal white & blue theme, mobile responsive.

**Non-Goals:**
- No `EventSource` (POST unsupported), no WebSocket, no polling.
- No framework, bundler, npm dependency, or lockfile.
- No persistence of conversation history beyond the live page (a page reload starts fresh; only `thread_id` and the session token are held).
- No auth logic beyond passing the token through to the backend.

## Decisions

### D1. SSE consumption via `fetch` + `ReadableStream` (not `EventSource`)

`EventSource` only performs `GET` and cannot send a JSON body, so it cannot call `POST /api/chat`. We stream the response body manually:

```js
// frontend/app.js  — core streaming reader
async function streamChat(message, threadId, handlers) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
    body: JSON.stringify({ message, thread_id: threadId ?? undefined }),
  });
  if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line (\n\n). Parse complete frames only.
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawFrame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const evt = parseFrame(rawFrame);      // -> SSEEvent object or null
      if (evt) dispatchEvent(evt, handlers);  // routes by evt.type (see D3)
    }
  }
}

// Extract the JSON payload from one SSE frame's `data:` line(s).
function parseFrame(rawFrame) {
  const dataLines = rawFrame
    .split("\n")
    .filter((l) => l.startsWith("data:"))
    .map((l) => l.slice(5).trimStart());
  if (dataLines.length === 0) return null;
  try { return JSON.parse(dataLines.join("\n")); } catch { return null; }
}
```

Rationale: this is the only cross-browser way to read a streamed POST response body incrementally. `\n\n` frame boundaries and `data:` prefix stripping match the SSE wire format the P4 endpoint emits. Partial frames stay in `buffer` until their terminating blank line arrives.

`API_BASE` is empty string when the frontend is served from the same origin as the API; otherwise a configurable constant at the top of `app.js`.

### D2. Request payloads

`POST /api/session` (from the login page):
```json
{ "client_code": "<trimmed>", "session_token": "<trimmed>" }
```
Both values are passed through `String.prototype.trim()` before the request. Expected response `{ "ok": true }`. On non-ok or network error, the login page shows an inline error and does not navigate.

`POST /api/chat` (from the chat page, per user message):
```json
{ "message": "<trimmed user text>", "thread_id": "<from a prior DoneEvent flow, if any>" }
```
`thread_id` is omitted on the first message of a conversation. The backend owns thread identity; the frontend simply echoes back whatever `thread_id` it has been given for continuity. (Note: the P0 `DoneEvent` contract carries cost, not `thread_id`; if the backend does not surface a `thread_id` to the client, the field is simply omitted on every request and the backend derives continuity from the session — the frontend does not invent one.)

### D3. Event → UI mapping (all five `SSEEvent` types)

Each assistant turn owns one message DOM node. `dispatchEvent(evt, handlers)` routes on `evt.type`:

| `evt.type` | Payload used | UI effect |
|------------|--------------|-----------|
| `step` | `message` | Show/replace a transient **status line** in the active message bubble (e.g. "Looking up the knowledge base…", "Generating the answer…"). Not part of the final text; cleared when the first `token` arrives. |
| `token` | `text` | On first token, clear the status line. Append `text` to the message's text node (streamed in place). |
| `citations` | `citations: Citation[]` | Render a **hoverable citation card** appended at the end of the message body (see D5). Only rendered when the array is non-empty. |
| `done` | `cost: MessageCost`, `cumulative_cost_inr` | Finalize the message: remove any status line, render the **per-message cost/latency** row below the bubble from `cost.cost_inr` + `cost.latency_ms`, update the **top-left cumulative cost card** to `cumulative_cost_inr`, re-enable the composer. |
| `error` | `message` | Replace the active message body with an inline error style block showing `message`; finalize (re-enable composer). No cost row. |

Ordering assumption (from P3/P4): `step*` → `token*` → optional `citations` → `done` (or a terminal `error` at any point). The reader tolerates interleaving because each type mutates an independent part of the message node.

### D4. JS module structure (`frontend/app.js`)

Single ES module, no imports. Logical sections:
- **config**: `API_BASE`.
- **session store**: `saveSession(clientCode, token)` / `getToken()` using `sessionStorage`; login page writes, chat page reads (and redirects to `index.html` if absent).
- **login controller** (guarded to run only on `index.html`): wires the form submit → trims both inputs → `postSession()` → on `{ok:true}` `location.assign("chat.html")`, else inline error.
- **chat controller** (guarded to run only on `chat.html`): manages `threadId`, `cumulativeInr`, composer submit → append user bubble → create assistant bubble → `streamChat()` with `handlers`.
- **streaming core**: `streamChat`, `parseFrame`, `dispatchEvent` (D1/D3).
- **render helpers**: `appendUserMessage`, `createAssistantMessage`, `setStatus`, `appendToken`, `renderCitations`, `renderMessageCost`, `updateCostCard` (D5).

Page detection: each controller checks for its root element id (`#login-form` vs `#chat-root`) and no-ops if absent, so one `app.js` serves both pages.

### D5. Citation-card and cost-card DOM structure

**Cumulative cost card** (top-left, web only; `frontend/chat.html`, fixed position, hidden below `sm` breakpoint via Tailwind `hidden sm:block`):
```html
<aside id="cost-card"
       class="fixed top-4 left-4 z-20 hidden sm:block rounded-lg border border-blue-200 bg-white/90 px-4 py-3 shadow">
  <div class="text-xs uppercase tracking-wide text-blue-500">Conversation cost</div>
  <div id="cost-card-value" class="text-lg font-semibold text-blue-700">₹0.0000</div>
</aside>
```
`updateCostCard(inr)` sets `#cost-card-value` to `₹` + `inr.toFixed(4)`.

**Per-message cost/latency row** (appended below each finalized assistant bubble):
```html
<div class="mt-1 text-xs text-slate-400">
  ₹<span data-cost>0.0000</span> · <span data-latency>0</span> ms
</div>
```
`renderMessageCost(node, cost)` fills `cost.cost_inr.toFixed(4)` and `cost.latency_ms`.

**Hoverable citation card** (appended at end of message body). Each `Citation` renders a chip; hovering reveals the full source/section/topic via a CSS-driven popover (Tailwind `group`/`group-hover`, no JS):
```html
<div class="citations mt-2 flex flex-wrap gap-2">
  <!-- one per Citation -->
  <span class="group relative inline-flex cursor-help items-center rounded-full
               border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
    <span data-source>Source title</span>
    <div class="pointer-events-none absolute bottom-full left-0 z-30 mb-2 hidden w-64
                rounded-md border border-slate-200 bg-white p-3 text-left text-xs
                shadow-lg group-hover:block">
      <div><span class="font-semibold">Source:</span> <span data-source></span></div>
      <div><span class="font-semibold">Section:</span> <span data-section>—</span></div>
      <div><span class="font-semibold">Topic:</span> <span data-topic>—</span></div>
    </div>
  </span>
</div>
```
`renderCitations(node, citations)` builds one chip per `Citation`, filling `source` (required) and `section`/`topic` (falling back to "—" when null/absent). The tester hovers a chip to inspect the full citation. Values are inserted via `textContent` (never `innerHTML`) to avoid injection from KB content.

### D6. Theme & responsiveness

- White background, blue accents (Tailwind `blue-*` / `slate-*`), matching the "minimal white & blue" spec.
- Chat column is `max-w-2xl mx-auto`; composer is a bottom-docked bar. On mobile (`< sm`) the cumulative cost card is hidden (per "web view only"); per-message cost rows remain visible on all widths.
- All Tailwind via CDN `<script src="https://cdn.tailwindcss.com">`; `frontend/styles.css` holds only rules Tailwind utilities cannot express (e.g. streaming caret animation), if any.

## Risks / Trade-offs

- **[Tailwind via CDN]** → requires network at load and is not production-optimized. Acceptable: this is a QA-only POC, explicitly build-free per scope.
- **[Manual SSE parsing]** → hand-rolled frame splitting can mis-handle exotic framing (comments, multi-line data). Mitigated by only acting on complete `\n\n`-terminated frames and joining multiple `data:` lines; matches the P4 emitter's format.
- **[`thread_id` continuity]** → the P0 `DoneEvent` contract does not carry a `thread_id`, so multi-turn continuity relies on the backend deriving it from the session; the frontend omits `thread_id` unless the backend gives it one. Called out as an Open Question.
- **[No history persistence]** → a reload loses the visible conversation. Acceptable for QA; the backend still owns real thread state.

## Migration Plan

No migration — additive static files under `frontend/` only. To run: serve `frontend/` statically (e.g. `python -m http.server` from `frontend/` or any static host) with the P4 API reachable at `API_BASE`. Removal is deleting the directory.

## Open Questions

- Does the backend surface a `thread_id` to the client for multi-turn continuity, or derive it entirely from the session? If the former, P4 should document the field the client echoes; until then the frontend omits `thread_id`.
- Exact `step` message strings emitted by P3 (the UI renders whatever `message` arrives; the doc examples are "Looking up the knowledge base…" and "Generating the answer…").
- Same-origin vs cross-origin serving (sets whether `API_BASE` is empty and whether CORS must be enabled by P4).
