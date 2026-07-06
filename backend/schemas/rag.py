"""RAG-tool return contract: citations + retrieved chunks.

Authoritative cross-module shape for knowledge-base retrieval. Every retrieved
chunk MUST carry a citation.
"""

from __future__ import annotations

from pydantic import BaseModel


class Citation(BaseModel):
    source: str  # answer_source or document title
    section: str | None = None  # section heading if present
    topic: str | None = None


class RetrievedChunk(BaseModel):
    id: str  # e.g. "qa-00123" (str form of qa_chunks.id)
    text: str  # the chunk content
    score: float  # fused RRF score
    citation: Citation


class RagToolResult(BaseModel):
    chunks: list[RetrievedChunk]
    query: str
