"""SSE event contract.

Every SSE ``data:`` frame is exactly one of these models serialized to JSON,
discriminated on ``type``. The backend streams them; the frontend consumes them.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from pydantic import BaseModel

from .cost import MessageCost
from .rag import Citation


class StepEvent(BaseModel):  # intermediate-step notice
    type: Literal["step"] = "step"
    message: str  # e.g. "Looking up the knowledge base…"


class TokenEvent(BaseModel):  # incremental output token(s)
    type: Literal["token"] = "token"
    text: str


class CitationsEvent(BaseModel):
    type: Literal["citations"] = "citations"
    citations: list[Citation]


class DoneEvent(BaseModel):  # exactly one terminal done event per turn
    type: Literal["done"] = "done"
    cost: MessageCost
    cumulative_cost_inr: float


class ErrorEvent(BaseModel):  # terminates the stream; no done event follows
    type: Literal["error"] = "error"
    message: str


# Discriminated union of every SSE frame.
SSEEvent = Annotated[
    Union[StepEvent, TokenEvent, CitationsEvent, DoneEvent, ErrorEvent],
    Field(discriminator="type"),
]
