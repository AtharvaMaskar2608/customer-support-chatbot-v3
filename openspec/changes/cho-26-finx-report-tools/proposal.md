## Why

The agent must answer account-specific questions ("what's on my CML?", "show my contract note for that date") by calling Choice's FinX MIS reports API on the customer's behalf, and it must route every model `tool_use` block (knowledge-base search + the two report calls) through a single, safe entry point. These read-only FinX clients and the tool dispatcher are that layer: they turn a model tool request into a validated HTTP call (or RAG lookup) and return a plain string result the model can read, never raising into the agent loop.

## What Changes

- Add `backend/tools/cml.py::get_cml_report(mobile_number, session)` — a read-only client for the FinX CML (Client Master List) report.
- Add `backend/tools/contract_note.py::get_contract_note(mobile_number, contract_date, session)` — a read-only client for the FinX Contract Note report (date in `DD-MM-YYYY`).
- Add `backend/tools/http.py` — a shared FinX HTTP helper: builds the fixed auth headers from `SessionContext`, issues the `POST` with a timeout, and normalizes transport/HTTP errors.
- Add `backend/tools/dispatch.py::execute_tool(name, tool_input, session)` — routes the three tool names (`search_knowledge_base`, `get_cml_report`, `get_contract_note`) to their implementations and returns a single string `tool_result` for the model. `search_knowledge_base` delegates to the P1 retriever; validation and error-to-string handling live here so the agent loop never sees an exception.
- Import-only dependency on P0 contracts (`SessionContext`, tool definitions, `settings.finx_base_url`) and the P1 retriever; this change declares no new schemas, config, or migrations.

## Capabilities

### New Capabilities
- `finx-report-tools`: Read-only FinX MIS report clients (CML + Contract Note) that POST to the FinX reports API with session-JWT auth headers and return the provider response as a `dict`.
- `tool-dispatch`: A single `execute_tool` router that validates input, dispatches the model's `tool_use` blocks to RAG / CML / Contract Note, and returns a string `tool_result`, converting all errors to strings rather than raising.

### Modified Capabilities
<!-- None — new capabilities only. -->

## Impact

- **New code:** `backend/tools/` only — `cml.py`, `contract_note.py`, `http.py`, `dispatch.py` (plus `backend/tests/test_tools.py`).
- **Dependencies:** P0 `foundations-and-contracts` (`SessionContext`, `settings.finx_base_url`, tool definitions) and P1 `rag-hybrid-retrieval` (`backend.rag.retriever.retrieve`). Uses an HTTP client library already pinned by P0.
- **Downstream:** P3 `agentic-loop` calls `execute_tool` for every tool turn; it depends on the exact routing table and the never-raise contract defined here.
- **Out of scope:** no schema/config/migration/lockfile changes; response bodies stay provider-defined (`dict`).
