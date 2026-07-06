## ADDED Requirements

### Requirement: Tool dispatcher routing
The system SHALL provide `backend/tools/dispatch.py::execute_tool(name: str, tool_input: dict, session: SessionContext) -> str` that routes a model `tool_use` block to its handler and returns a single string `tool_result`. The routing table MUST be:
- `search_knowledge_base` → `backend.rag.retriever.retrieve(tool_input["query"])`, formatted to a string (chunks + citations).
- `get_cml_report` → `get_cml_report(mobile_number, session)`, result serialized to a string.
- `get_contract_note` → `get_contract_note(mobile_number, contract_date, session)`, result serialized to a string.
- any other `name` → the string `"Error: unknown tool '<name>'."`

`execute_tool` MUST return a non-empty `str` for every input.

#### Scenario: Routes each known tool name
- **WHEN** `execute_tool` is called with `search_knowledge_base`, `get_cml_report`, or `get_contract_note` and valid input
- **THEN** it invokes the corresponding handler (`retrieve`, `get_cml_report`, `get_contract_note`) and returns its result as a string

#### Scenario: Unknown tool name
- **WHEN** `execute_tool("get_pnl_statement", {...}, session)` is called
- **THEN** it returns `"Error: unknown tool 'get_pnl_statement'."` without calling any handler

### Requirement: Input validation at the dispatch boundary
`execute_tool` SHALL validate every model-supplied argument before calling a report client: `mobile_number` MUST match `^\d{10}$` (exactly 10 digits) after trimming, and `contract_date` MUST match `^\d{2}-\d{2}-\d{4}$` and parse as a real calendar date via `%d-%m-%Y`. A missing required key or a failed validation MUST return a descriptive `"Error:"` string and MUST NOT call FinX.

#### Scenario: Invalid mobile number is rejected before any HTTP call
- **WHEN** `execute_tool("get_cml_report", {"mobile_number": "12345"}, session)` is called
- **THEN** it returns `"Error: 'mobile_number' must be a 10-digit number."` and no FinX request is made

#### Scenario: Invalid contract date is rejected before any HTTP call
- **WHEN** `execute_tool("get_contract_note", {"mobile_number": "9876543210", "contract_date": "2026-07-05"}, session)` is called
- **THEN** it returns an `"Error:"` string about `DD-MM-YYYY` format and no FinX request is made

#### Scenario: Missing required key is rejected
- **WHEN** `execute_tool("get_contract_note", {"mobile_number": "9876543210"}, session)` is called with no `contract_date`
- **THEN** it returns an `"Error:"` string and does not call FinX

### Requirement: Errors never raise into the agent loop
`execute_tool` SHALL NOT propagate any exception. Every `FinxError`, validation failure, and unexpected exception MUST be caught and returned as a readable `"Error:"` string that never contains the session JWT, a stack trace, or raw upstream HTML. Unexpected exceptions SHALL be logged before the generic error string is returned.

#### Scenario: FinX failure becomes a recovery string
- **WHEN** the routed report client raises `FinxError` (timeout / non-2xx / non-JSON)
- **THEN** `execute_tool` returns a string advising retry or a support ticket, and does not raise, and the string does not contain the session token

#### Scenario: Unexpected exception is contained
- **WHEN** a handler raises an unexpected exception
- **THEN** `execute_tool` logs it and returns `"Error: could not complete the '<name>' request."` rather than raising

### Requirement: Knowledge-base result formatting
For `search_knowledge_base`, dispatch SHALL call the P1 retriever and format the `RagToolResult` into a single string containing each retrieved chunk's text plus a citation line derived from its `Citation` (`source`, optional `section`, optional `topic`). When no chunks are returned, it MUST return `"No relevant knowledge-base entries found for that query."`.

#### Scenario: Chunks are formatted with citations
- **WHEN** `execute_tool("search_knowledge_base", {"query": "how to reset my password"}, session)` returns chunks
- **THEN** the result string contains each chunk's text and a citation built from its `source`/`section`/`topic`

#### Scenario: Empty retrieval
- **WHEN** the retriever returns zero chunks
- **THEN** `execute_tool` returns `"No relevant knowledge-base entries found for that query."`
