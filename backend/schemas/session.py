"""Session context contract.

``session_token`` is the JWT passed as the ``Authorization`` header to the FinX
reports APIs. Both fields are trimmed of surrounding whitespace before use.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class SessionContext(BaseModel):
    client_code: str  # trimmed
    session_token: str  # trimmed; JWT used as Authorization header for reports APIs

    @field_validator("client_code", "session_token")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()
