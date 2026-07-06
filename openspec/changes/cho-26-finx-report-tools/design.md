## Context

The agent (P3) exposes three tools to the Anthropic model — `search_knowledge_base`, `get_cml_report`, `get_contract_note` (definitions fixed in P0 `backend/schemas/tools.py`). When the model emits a `tool_use` block, the loop needs one function that turns `(name, tool_input, session)` into a single string `tool_result`. Two of those tools are HTTP calls to Choice's FinX MIS reports API, authenticated with the customer's session JWT; the third is the P1 hybrid retriever. This change owns `backend/tools/` and nothing else: it imports P0 contracts and the P1 `retrieve()` function and declares no new schemas, config, or migrations.

The read-only FinX calls carry customer-identifying input (mobile number, contract date) and a raw JWT, so input validation and total error containment are first-class requirements: an exception must never escape into the agent loop — every failure is returned to the model as a readable string so it can recover or offer a support ticket.

## Goals / Non-Goals

**Goals:**
- Exact, importable clients for the CML and Contract Note reports with the fixed endpoints, bodies, and headers from P0.
- A single `execute_tool` router with a fixed name→handler table, input validation, HTTP timeout, and error-to-string handling.
- Deterministic, fully HTTP-mocked tests (`pytest backend/tests/test_tools.py`).

**Non-Goals:**
- No parsing/typing of FinX response bodies — they are provider-defined and pass through as `dict`.
- No new pydantic schemas, config keys, migrations, or lockfile/root-config edits.
- No agent-loop, retrieval, or streaming logic (owned by P3/P1).
- No writes to FinX — both report calls are read-only report generation.

## Decisions

### D1. Shared FinX HTTP helper (`backend/tools/http.py`)
All FinX calls go through one helper so the header set, timeout, and error normalization are defined once.

```python
# backend/tools/http.py
from backend.schemas.session import SessionContext

FINX_TIMEOUT_SECONDS: float = 20.0

class FinxError(Exception):
    """Raised internally on transport/HTTP failure; never propagates past dispatch."""

def finx_headers(session: SessionContext) -> dict[str, str]:
    """Fixed FinX auth headers. Authorization is the raw JWT (no 'Bearer' prefix)."""
    return {
        "Authorization": session.session_token,
        "authType": "jwt",
        "source": "FINX_WEB",
        "Content-Type": "application/json",
    }

def finx_post(path: str, body: dict, session: SessionContext) -> dict:
    """POST {settings.finx_base_url}{path} with finx_headers, JSON body, FINX_TIMEOUT_SECONDS.
    Returns the parsed JSON dict on 2xx. Raises FinxError on timeout, connection error,
    non-2xx status, or non-JSON body (message includes status/reason, never the JWT)."""
```

- `path` is a leading-slash path (e.g. `/mis/v2/reports/v2/generate`); the base URL comes from `get_settings().finx_base_url`.
- Timeout is a fixed constant (`FINX_TIMEOUT_SECONDS = 20.0`); a timeout surfaces as `FinxError`.
- `FinxError` messages MUST NOT include the `Authorization` value.

### D2. CML report client (`backend/tools/cml.py`)
```python
def get_cml_report(mobile_number: str, session: SessionContext) -> dict:
    """POST {finx_base_url}/mis/v2/reports/v2/generate
    body: {"reportType": "cml", "searchBy": "mobile-number", "searchValue": mobile_number}
    Returns the FinX JSON response as a dict (provider-defined shape)."""
```
- Endpoint: `POST {settings.finx_base_url}/mis/v2/reports/v2/generate`
- Request body: `{"reportType": "cml", "searchBy": "mobile-number", "searchValue": mobile_number}`
- Headers: `finx_headers(session)` (D1).
- Return: parsed JSON `dict`. Raises `FinxError` on failure (caught by dispatch).

### D3. Contract Note client (`backend/tools/contract_note.py`)
```python
def get_contract_note(mobile_number: str, contract_date: str, session: SessionContext) -> dict:
    """POST {finx_base_url}/mis/v2/contract-note/generate
    body: {"mobileNo": mobile_number, "contractDate": contract_date}   # contract_date is DD-MM-YYYY
    Returns the FinX JSON response as a dict (provider-defined shape)."""
```
- Endpoint: `POST {settings.finx_base_url}/mis/v2/contract-note/generate`
- Request body: `{"mobileNo": mobile_number, "contractDate": contract_date}`
- `contract_date` MUST be `DD-MM-YYYY`.
- Headers: `finx_headers(session)` (D1).
- Return: parsed JSON `dict`. Raises `FinxError` on failure (caught by dispatch).

### D4. Input validation (in dispatch, before any client call)
Validation lives in `dispatch.py` so both clients stay thin and every model-supplied argument is checked at one boundary.

```python
import re
MOBILE_RE = re.compile(r"^\d{10}$")          # exactly 10 digits
DATE_RE   = re.compile(r"^\d{2}-\d{2}-\d{4}$")  # DD-MM-YYYY shape
```
- Mobile number: after `str(...).strip()`, MUST match `^\d{10}$`.
- Contract date: after `str(...).strip()`, MUST match `^\d{2}-\d{2}-\d{4}$` **and** parse as a real calendar date via `datetime.strptime(value, "%d-%m-%Y")`.
- Missing required key in `tool_input` → validation failure.
- A validation failure returns a descriptive string to the model (D6); it does NOT raise and does NOT call FinX.

### D5. `execute_tool` router (`backend/tools/dispatch.py`)
```python
def execute_tool(name: str, tool_input: dict, session: SessionContext) -> str:
    """Route a model tool_use block to its handler and return a string tool_result.
    Never raises: all validation/transport/handler errors are returned as strings."""
```

Routing table:

| `name`                  | Handler                                   | Required `tool_input` keys        | Result string built from |
|-------------------------|-------------------------------------------|-----------------------------------|--------------------------|
| `search_knowledge_base` | `backend.rag.retriever.retrieve(query)`   | `query: str`                      | formatted chunks + citations (D7) |
| `get_cml_report`        | `cml.get_cml_report(mobile, session)`     | `mobile_number: str` (10 digits)  | JSON-stringified `dict` |
| `get_contract_note`     | `contract_note.get_contract_note(...)`    | `mobile_number` (10 digits), `contract_date` (DD-MM-YYYY) | JSON-stringified `dict` |
| anything else           | —                                         | —                                 | `"Error: unknown tool '<name>'."` |

- The FinX report result `dict` is serialized with `json.dumps(result, ensure_ascii=False, default=str)` so the model receives a readable, complete string.
- `execute_tool` returns a non-empty `str` for every input, including every error path.

### D6. Error-to-string contract (never raise into the agent loop)
Every failure path returns a human-readable, model-actionable string prefixed with `"Error:"` — the function signature return type is `str`, never an exception:

| Failure | Returned string (shape) |
|---|---|
| Unknown tool name | `"Error: unknown tool '<name>'."` |
| Missing/invalid mobile | `"Error: 'mobile_number' must be a 10-digit number."` |
| Missing/invalid date | `"Error: 'contract_date' must be a valid date in DD-MM-YYYY format."` |
| `FinxError` (timeout/HTTP/non-JSON) | `"Error: the FinX report service is currently unavailable. Please try again or raise a support ticket."` |
| Any unexpected exception | `"Error: could not complete the '<name>' request."` |

Error strings MUST NOT leak the session JWT, stack traces, or raw upstream HTML.

### D7. RAG result formatting (for `search_knowledge_base`)
`retrieve(query)` returns a P1 `RagToolResult{chunks: list[RetrievedChunk], query}`. Dispatch formats it into a single string: each chunk as its `text` followed by a citation line built from the chunk's `Citation` (`source`, optional `section`, optional `topic`). If `chunks` is empty, return `"No relevant knowledge-base entries found for that query."`. The formatted string is the tool_result; the P3 loop separately surfaces `Citation` objects for the UI.

### D8. HTTP client library
Uses the HTTP client already pinned by P0 (`requests`-style sync API). All network I/O is confined to `backend/tools/http.py`, so tests mock exactly one seam (`finx_post` or the underlying client) and never hit the network.

## Risks / Trade-offs

- **[Provider response is an opaque `dict`]** → the model receives a JSON-stringified blob it must summarize; acceptable until FinX response schemas are pinned (P0 Open Question). Serialization uses `default=str` so non-JSON-native values never crash the tool.
- **[Validation regex only checks shape, not existence]** → a well-formed but non-existent mobile/date reaches FinX and returns a provider "not found"; the model relays that. Acceptable — we validate format, FinX validates identity.
- **[Swallowing all exceptions]** → a real bug could be masked as a generic error string; mitigation: unexpected exceptions are logged (module logger) before the generic string is returned, and tests assert each specific error branch.
- **[JWT in headers]** → the raw session JWT is an auth header; `FinxError`/error strings are constructed to never echo it.

## Migration Plan

Additive, `backend/tools/` only. No DB, config, or dependency-file changes (HTTP client already pinned by P0). Implementation order: `http.py` → `cml.py` + `contract_note.py` → `dispatch.py` → `backend/tests/test_tools.py`. No rollback concerns (new files, no shared state).

## Open Questions

- FinX report **response** body schemas (P0 open question) — until pinned, results pass through as JSON-stringified `dict`; if/when pinned, dispatch can summarize specific fields without changing the routing table.
- Whether `search_knowledge_base` should cap the number of chunks in the formatted string — deferred to P3 tuning; default is all returned chunks.
