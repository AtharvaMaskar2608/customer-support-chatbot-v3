"""Per-message and cumulative cost + latency accounting (INR)."""

from __future__ import annotations

from pydantic import BaseModel


class MessageCost(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_inr: float
    latency_ms: int


class ConversationCost(BaseModel):
    cumulative_cost_inr: float
    messages: list[MessageCost]
