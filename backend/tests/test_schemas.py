"""Round-trip validation of every shared contract against example payloads."""

from __future__ import annotations

from pydantic import TypeAdapter

from backend.schemas import (
    AgentReply,
    Citation,
    CitationsEvent,
    ConversationCost,
    DoneEvent,
    ErrorEvent,
    MessageCost,
    RagToolResult,
    RetrievedChunk,
    SSEEvent,
    SessionContext,
    StepEvent,
    TokenEvent,
    ToolInvocation,
)
from backend.schemas.tools import (
    ALL_TOOLS,
    CML_REPORT_TOOL,
    CONTRACT_NOTE_TOOL,
    RAG_TOOL,
)


def _roundtrip(model):
    """Assert the model survives a JSON serialize -> validate round-trip."""
    restored = type(model).model_validate_json(model.model_dump_json())
    assert restored == model
    return restored


def test_citation_and_rag_result_roundtrip():
    citation = Citation(source="FAQ.xlsx", section="Onboarding", topic="KYC")
    chunk = RetrievedChunk(id="qa-00123", text="You can...", score=0.87, citation=citation)
    result = RagToolResult(chunks=[chunk], query="how do I complete KYC?")
    _roundtrip(result)
    assert result.chunks[0].citation.source == "FAQ.xlsx"


def test_citation_optional_fields_default_none():
    citation = Citation(source="doc")
    assert citation.section is None and citation.topic is None
    _roundtrip(citation)


def test_session_context_trims_whitespace():
    ctx = SessionContext(client_code="  ABC123 \n", session_token="\t jwt.token.here  ")
    assert ctx.client_code == "ABC123"
    assert ctx.session_token == "jwt.token.here"
    _roundtrip(ctx)


def test_cost_models_roundtrip():
    m1 = MessageCost(input_tokens=1000, output_tokens=500, cost_inr=0.9, latency_ms=1200)
    m2 = MessageCost(input_tokens=200, output_tokens=100, cost_inr=0.2, latency_ms=800)
    convo = ConversationCost(cumulative_cost_inr=1.1, messages=[m1, m2])
    _roundtrip(convo)
    assert convo.cumulative_cost_inr == sum(m.cost_inr for m in convo.messages)


def test_sse_events_roundtrip():
    cost = MessageCost(input_tokens=1, output_tokens=1, cost_inr=0.1, latency_ms=10)
    events = [
        StepEvent(message="Looking up the knowledge base…"),
        TokenEvent(text="Hello"),
        CitationsEvent(citations=[Citation(source="doc")]),
        DoneEvent(cost=cost, cumulative_cost_inr=0.1),
        ErrorEvent(message="boom"),
    ]
    for ev in events:
        _roundtrip(ev)


def test_sse_union_discriminates_on_type():
    adapter = TypeAdapter(SSEEvent)
    assert isinstance(adapter.validate_python({"type": "step", "message": "x"}), StepEvent)
    assert isinstance(adapter.validate_python({"type": "token", "text": "x"}), TokenEvent)
    assert isinstance(adapter.validate_python({"type": "error", "message": "x"}), ErrorEvent)
    done = adapter.validate_python(
        {
            "type": "done",
            "cost": {"input_tokens": 1, "output_tokens": 1, "cost_inr": 0.1, "latency_ms": 5},
            "cumulative_cost_inr": 0.1,
        }
    )
    assert isinstance(done, DoneEvent)


def test_agent_reply_roundtrip():
    reply = AgentReply(
        text="Here is the answer.",
        citations=[Citation(source="FAQ.xlsx", section="KYC")],
        retrieval_context=["chunk text one", "chunk text two"],
        tools_called=[
            ToolInvocation(
                name="search_knowledge_base",
                input={"query": "kyc"},
                output="[...]",
            )
        ],
        cost=MessageCost(input_tokens=10, output_tokens=5, cost_inr=0.1, latency_ms=100),
    )
    restored = _roundtrip(reply)
    assert restored.tools_called[0].name == "search_knowledge_base"
    assert restored.retrieval_context == ["chunk text one", "chunk text two"]


def test_tool_definitions_valid_and_unique():
    names = [t["name"] for t in ALL_TOOLS]
    assert names == ["search_knowledge_base", "get_cml_report", "get_contract_note"]
    assert len(set(names)) == len(names)
    for tool in ALL_TOOLS:
        assert tool["description"]
        assert tool["input_schema"]["type"] == "object"

    assert RAG_TOOL["input_schema"]["required"] == ["query"]
    assert CML_REPORT_TOOL["input_schema"]["required"] == ["mobile_number"]
    assert CONTRACT_NOTE_TOOL["input_schema"]["required"] == ["mobile_number", "contract_date"]
