## 1. Shared FinX HTTP helper
- [ ] 1.1 Create `backend/tools/http.py` with `FINX_TIMEOUT_SECONDS = 20.0`, `FinxError`, `finx_headers(session)` (raw JWT `Authorization`, `authType: jwt`, `source: FINX_WEB`, `Content-Type: application/json`), and `finx_post(path, body, session)` that POSTs `{settings.finx_base_url}{path}` with the timeout and raises `FinxError` (JWT-free message) on timeout/connection/non-2xx/non-JSON.
- [ ] 1.2 Confirm the base URL is read from `get_settings().finx_base_url` (P0) and no config/schema is re-declared.

## 2. Report clients
- [ ] 2.1 Create `backend/tools/cml.py::get_cml_report(mobile_number, session) -> dict` calling `finx_post("/mis/v2/reports/v2/generate", {"reportType":"cml","searchBy":"mobile-number","searchValue":mobile_number}, session)`.
- [ ] 2.2 Create `backend/tools/contract_note.py::get_contract_note(mobile_number, contract_date, session) -> dict` calling `finx_post("/mis/v2/contract-note/generate", {"mobileNo":mobile_number,"contractDate":contract_date}, session)`.
- [ ] 2.3 Ensure both return the decoded JSON `dict` unmodified (provider-defined shape).

## 3. Tool dispatcher
- [ ] 3.1 Create `backend/tools/dispatch.py::execute_tool(name, tool_input, session) -> str` with the routing table (`search_knowledge_base`→P1 `retrieve`, `get_cml_report`, `get_contract_note`, else unknown-tool string).
- [ ] 3.2 Add input validation: `mobile_number` `^\d{10}$`, `contract_date` `^\d{2}-\d{2}-\d{4}$` and `strptime("%d-%m-%Y")`, missing-key handling — all before any FinX call.
- [ ] 3.3 Add error-to-string handling: catch `FinxError`, validation failures, and unexpected exceptions (log the latter); never raise; never leak the JWT/stack trace/HTML.
- [ ] 3.4 Format `RagToolResult` from `retrieve()` into a chunks+citations string; empty-result fallback string. Serialize report `dict`s via `json.dumps(..., ensure_ascii=False, default=str)`.

## 4. Verification
- [ ] 4.1 Write `backend/tests/test_tools.py` (HTTP fully mocked): assert CML and Contract Note request URL/body/headers; assert dispatch routes all three tool names; assert every error branch (unknown tool, bad mobile, bad date, missing key, `FinxError`, unexpected exception) returns the specified `"Error:"` string and does not raise; assert no error string contains the session token.
- [ ] 4.2 Run the test command: `pytest backend/tests/test_tools.py` — all pass with HTTP mocked.
- [ ] 4.3 Manual smoke: CML and Contract Note callable against a test session token; `execute_tool` routes all 3 tool names end-to-end. (Done condition met.)
