"""Agent reply contract.

The single structured return of the agent's non-streaming turn helper
(``agent_reply``), consumed by the eval change (P7).
"""

from __future__ import annotations

from pydantic import BaseModel

from .cost import MessageCost
from .rag import Citation


class ToolInvocation(BaseModel):
    name: str  # search_knowledge_base | get_cml_report | get_contract_note
    input: dict  # arguments the model passed to the tool
    output: str  # stringified tool_result fed back to the model


class AgentReply(BaseModel):
    text: str  # final assistant text
    citations: list[Citation]  # empty when RAG not used
    # RAW retrieved chunk texts (RetrievedChunk.text) gathered this turn; for
    # DeepEval RAG turn metrics.
    retrieval_context: list[str]
    tools_called: list[ToolInvocation]  # every tool invoked this turn, in order
    cost: MessageCost
