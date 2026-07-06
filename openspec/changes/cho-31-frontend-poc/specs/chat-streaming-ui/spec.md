## ADDED Requirements

### Requirement: Chat composer posts messages to the streaming endpoint
The chat view SHALL provide a message box that, on submit, trims the input and sends `POST /api/chat` with body `{ "message": <trimmed>, "thread_id": <optional> }`, where `thread_id` is omitted on the first message of a conversation. The composer MUST be disabled while a turn is streaming and re-enabled when the turn finalizes (`done` or `error`).

#### Scenario: Send a message
- **WHEN** the tester types "How do I open an account?" and submits
- **THEN** `POST /api/chat` is called with `{"message":"How do I open an account?"}` (no `thread_id` on the first turn) and the composer is disabled until the turn finalizes

### Requirement: Consume `POST /api/chat` as SSE via fetch + ReadableStream
Because the chat endpoint is a `POST` returning `text/event-stream`, the system SHALL consume it with `fetch()` and a `ReadableStream` reader (NOT `EventSource`, which only supports `GET`). The reader MUST buffer bytes, split on the SSE frame boundary (blank line `\n\n`), strip the `data:` prefix from each frame's data line(s), `JSON.parse` the payload into an `SSEEvent`, and dispatch on `SSEEvent.type`. Partial frames MUST remain buffered until their terminating blank line arrives.

#### Scenario: Streamed frames are parsed incrementally
- **WHEN** the response body delivers `data: {"type":"token","text":"Hel"}\n\n` and later `data: {"type":"token","text":"lo"}\n\n` across separate reads
- **THEN** each complete frame is parsed as a `TokenEvent` and dispatched, while any bytes without a terminating blank line stay buffered until completed

### Requirement: Map each SSEEvent type to the correct UI update
The system SHALL map every `SSEEvent` type to a defined UI effect within the active assistant message:
- `StepEvent` (`type:"step"`): show/replace a **transient status line** (e.g. "Looking up the knowledge base…", "Generating the answer…"); it is not part of the final text and is cleared when the first token arrives.
- `TokenEvent` (`type:"token"`): clear the status line on first token, then append `text` to the message, streaming in place.
- `CitationsEvent` (`type:"citations"`): render a hoverable citation card at the end of the message when `citations` is non-empty.
- `DoneEvent` (`type:"done"`): finalize the message, render the per-message cost/latency row from `cost`, update the cumulative cost card from `cumulative_cost_inr`, and re-enable the composer.
- `ErrorEvent` (`type:"error"`): show `message` as an inline error and finalize (re-enable composer) with no cost row.

#### Scenario: Step event shown as transient status
- **WHEN** a `StepEvent{message:"Looking up the knowledge base…"}` is dispatched
- **THEN** the active message shows "Looking up the knowledge base…" as a transient status line that is removed once the first `TokenEvent` arrives

#### Scenario: Tokens stream into the message
- **WHEN** successive `TokenEvent`s with `text` "Hel" then "lo" are dispatched
- **THEN** the message body reads "Hello" with the status line cleared

#### Scenario: Error event finalizes with an inline error
- **WHEN** an `ErrorEvent{message:"upstream failed"}` is dispatched during a turn
- **THEN** the message body shows the inline error "upstream failed", no cost row is rendered, and the composer is re-enabled

### Requirement: Cumulative cost card in the top-left corner (web only)
The chat view SHALL render a card fixed in the **top-left corner** showing the cumulative conversation cost in **INR**, updated from `DoneEvent.cumulative_cost_inr` after each turn. The card SHALL be shown only in the web (non-mobile) layout and hidden on small screens.

#### Scenario: Cumulative cost updates on done
- **WHEN** a `DoneEvent{cumulative_cost_inr: 1.2345}` is received
- **THEN** the top-left cost card displays the cumulative cost as ₹1.2345 (INR)

#### Scenario: Card hidden on mobile
- **WHEN** the chat view is rendered below the small-screen breakpoint
- **THEN** the cumulative cost card is not visible

### Requirement: Per-message cost and latency below every message
Below every assistant message, the system SHALL display that message's cost (INR) and latency (ms) taken from `DoneEvent.cost` (`MessageCost{cost_inr, latency_ms}`). This row is visible on all viewport widths.

#### Scenario: Per-message cost/latency rendered
- **WHEN** a `DoneEvent{cost:{cost_inr:0.0421, latency_ms:1830, ...}}` finalizes a message
- **THEN** a row below that message shows ₹0.0421 and 1830 ms

### Requirement: Hoverable citation card at the end of a message
When a `CitationsEvent` with a non-empty list arrives, the system SHALL render the citations at the end of that message as a **hoverable card**. Each `Citation` MUST expose its `source` (required) and, on hover, its `section` and `topic` (rendering a placeholder such as "—" when null/absent). Citation values MUST be inserted as text (`textContent`), never as HTML, to prevent injection from knowledge-base content.

#### Scenario: Citation chip reveals full detail on hover
- **WHEN** a `CitationsEvent{citations:[{source:"Account Opening Guide", section:"KYC", topic:"Onboarding"}]}` is received
- **THEN** a citation chip labeled "Account Opening Guide" is appended at the end of the message, and hovering it reveals source "Account Opening Guide", section "KYC", and topic "Onboarding"

#### Scenario: Empty citations render nothing
- **WHEN** a `CitationsEvent{citations:[]}` is received
- **THEN** no citation card is rendered for that message

### Requirement: Minimal white & blue responsive theme
The chat and login views SHALL use a minimal white-and-blue theme (Tailwind via CDN, no build step) and be mobile responsive: the chat column is width-constrained and centered, the composer docks at the bottom, and layout reflows without horizontal overflow on small screens.

#### Scenario: Responsive layout without horizontal scroll
- **WHEN** the chat view is viewed at a mobile viewport width
- **THEN** content reflows to fit the width with no horizontal page scroll and the composer remains reachable at the bottom
