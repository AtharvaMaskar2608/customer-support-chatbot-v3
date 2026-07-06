"""Anthropic tool definitions + documented FinX reports request contracts.

The ``input_schema`` dicts below are the exact schemas each tool advertises to
the model — the frozen cross-module contract. The FinX request contracts are
documented here for the tool-client change (P2) to implement; the clients
themselves live in P2, not this module.
"""

from __future__ import annotations

RAG_TOOL = {
    "name": "search_knowledge_base",
    "description": (
        "Search the Choice FinX knowledge base for answers to product/support "
        "questions. Returns chunks with citations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language search query",
            }
        },
        "required": ["query"],
    },
}

CML_REPORT_TOOL = {
    "name": "get_cml_report",
    "description": (
        "Fetch a customer's CML (Client Master List) report from FinX by mobile "
        "number."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mobile_number": {
                "type": "string",
                "description": "10-digit mobile number",
            }
        },
        "required": ["mobile_number"],
    },
}

CONTRACT_NOTE_TOOL = {
    "name": "get_contract_note",
    "description": (
        "Fetch a customer's contract note from FinX by mobile number and "
        "contract date."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mobile_number": {
                "type": "string",
                "description": "10-digit mobile number",
            },
            "contract_date": {
                "type": "string",
                "description": "Contract date in DD-MM-YYYY format",
            },
        },
        "required": ["mobile_number", "contract_date"],
    },
}

# All tool definitions the agent advertises, in a single importable list.
ALL_TOOLS = [RAG_TOOL, CML_REPORT_TOOL, CONTRACT_NOTE_TOOL]

# --- FinX reports request contracts (documented for P2; clients live in P2) ---
#
# CML report:
#   POST {finx_base_url}/mis/v2/reports/v2/generate
#   body: {"reportType": "cml", "searchBy": "mobile-number", "searchValue": "<mobile>"}
#
# Contract note:
#   POST {finx_base_url}/mis/v2/contract-note/generate
#   body: {"mobileNo": "<mobile>", "contractDate": "DD-MM-YYYY"}
#
# Shared headers on both requests:
#   Authorization: <session_token JWT>   (raw JWT, no "Bearer" prefix)
#   authType: jwt
#   source: FINX_WEB
#
# Response bodies are provider-defined; tools pass through / summarize (typed as
# dict until schemas are pinned).

FINX_CML_ENDPOINT = "/mis/v2/reports/v2/generate"
FINX_CONTRACT_NOTE_ENDPOINT = "/mis/v2/contract-note/generate"

# Header keys shared by both reports requests. Authorization is filled per-request
# with the SessionContext.session_token JWT (raw, no "Bearer" prefix).
FINX_SHARED_HEADERS = {
    "authType": "jwt",
    "source": "FINX_WEB",
}
