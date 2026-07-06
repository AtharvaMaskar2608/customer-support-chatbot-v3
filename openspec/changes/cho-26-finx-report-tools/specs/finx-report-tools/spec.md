## ADDED Requirements

### Requirement: Shared FinX HTTP helper
The system SHALL provide `backend/tools/http.py` with `finx_headers(session: SessionContext) -> dict[str, str]` and `finx_post(path: str, body: dict, session: SessionContext) -> dict`. `finx_headers` MUST return exactly `Authorization: session.session_token` (the raw JWT, with no `Bearer` prefix), `authType: jwt`, `source: FINX_WEB`, and `Content-Type: application/json`. `finx_post` MUST POST `{get_settings().finx_base_url}{path}` with those headers and the JSON `body`, using a fixed timeout `FINX_TIMEOUT_SECONDS = 20.0`, return the parsed JSON `dict` on a 2xx response, and raise `FinxError` on timeout, connection failure, non-2xx status, or non-JSON body. `FinxError` messages MUST NOT contain the `Authorization` value.

#### Scenario: Headers carry the raw session JWT
- **WHEN** `finx_headers(session)` is called with a `SessionContext` whose `session_token` is a JWT string
- **THEN** the returned dict has `Authorization` equal to that JWT verbatim (no `Bearer ` prefix), `authType` = `jwt`, and `source` = `FINX_WEB`

#### Scenario: Successful POST returns parsed JSON
- **WHEN** `finx_post(path, body, session)` receives a 2xx response with a JSON body
- **THEN** it returns that body as a `dict` and does not raise

#### Scenario: Transport failure raises a JWT-safe FinxError
- **WHEN** the underlying request times out, fails to connect, or returns a non-2xx status
- **THEN** `finx_post` raises `FinxError` whose message does not include the session token

### Requirement: CML report client
The system SHALL provide `backend/tools/cml.py::get_cml_report(mobile_number: str, session: SessionContext) -> dict`. It MUST issue `POST {get_settings().finx_base_url}/mis/v2/reports/v2/generate` via the shared HTTP helper with JSON body `{"reportType": "cml", "searchBy": "mobile-number", "searchValue": mobile_number}` and the shared FinX headers, and MUST return the FinX JSON response as a `dict` (provider-defined shape, not re-typed). Transport/HTTP failures propagate as `FinxError` for the dispatcher to convert.

#### Scenario: CML request is well-formed
- **WHEN** `get_cml_report("9876543210", session)` is called
- **THEN** it POSTs to `{finx_base_url}/mis/v2/reports/v2/generate` with body `{"reportType":"cml","searchBy":"mobile-number","searchValue":"9876543210"}` and the FinX auth headers, and returns the response JSON as a `dict`

### Requirement: Contract Note report client
The system SHALL provide `backend/tools/contract_note.py::get_contract_note(mobile_number: str, contract_date: str, session: SessionContext) -> dict`. It MUST issue `POST {get_settings().finx_base_url}/mis/v2/contract-note/generate` via the shared HTTP helper with JSON body `{"mobileNo": mobile_number, "contractDate": contract_date}` (where `contract_date` is `DD-MM-YYYY`) and the shared FinX headers, and MUST return the FinX JSON response as a `dict`. Transport/HTTP failures propagate as `FinxError` for the dispatcher to convert.

#### Scenario: Contract Note request is well-formed
- **WHEN** `get_contract_note("9876543210", "05-07-2026", session)` is called
- **THEN** it POSTs to `{finx_base_url}/mis/v2/contract-note/generate` with body `{"mobileNo":"9876543210","contractDate":"05-07-2026"}` and the FinX auth headers, and returns the response JSON as a `dict`

### Requirement: Report clients are read-only and provider-typed
Both report clients SHALL perform only report-generation `POST` calls (no mutation of customer data) and SHALL NOT parse, re-type, or reshape the FinX response beyond returning the decoded JSON `dict`.

#### Scenario: Response passes through untyped
- **WHEN** either client receives an arbitrary JSON object from FinX
- **THEN** the exact decoded object is returned as a `dict` with no field filtering or renaming
