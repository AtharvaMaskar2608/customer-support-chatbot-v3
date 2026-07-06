# **Customer Support Chatbot — Phase 1 Technical Documentation**

## **1\. Overview**

The Customer Support Chatbot is an agentic AI chatbot for **Choice FinX** that independently resolves user queries answerable from the knowledge base or via simple APIs, freeing human agents to focus on complex queries.

### **Phase 1 Scope**

1. **Hybrid RAG** over the existing knowledge base, exposed as a tool.  
2. **Simple agentic loop** using the Anthropic API, with access to the RAG tool and the Reports APIs (Reports APIs only for now).  
3. **POC frontend** for QA testers (Pritam, Ajay, Ankit Sir, Atharva — each with their own API key).

### **Out of Scope (Phase 1\)**

* Any APIs beyond the Reports APIs.  
* Production-grade auth/user management (POC uses client code \+ session token entry).

---

## **2\. Architecture Summary**

\[POC Frontend\] ──SSE──\> \[Backend: Agentic Loop (Anthropic)\] ──\> \[RAG Tool: Postgres \+ pgvector\]  
                                                            ──\> \[Reports APIs: CML Report, Contract Note\]

---

## **3\. Modules**

### **3.1 Frontend (POC for QA Testers)**

**Design**

* Minimal white & blue theme.  
* Mobile compatible (responsive).  
* Chat box for entering messages.

**Entry / Login Page**

* Tester first lands on a page with two inputs:  
  1. **Client code**  
  2. **Session token** — stored and used for downstream API calls when needed.  
* ⚠️ **Trim/strip whitespace** on all inputs before use.

**Chat View**

* **Web view only:** a card in the **top-left corner** showing cumulative conversation cost so far, in **INR**.  
* **Below every message:** show that message's cost and latency.

**Streaming (SSE)**

* Backend maintains an SSE HTTP connection.  
* While the agent works, stream **intermediate step messages**, e.g.:  
  * `Looking up the knowledge base…`  
  * `Generating the answer…`  
* Once the final output is ready, **stream the output tokens**.  
* Follow the Anthropic API streaming documentation for event structure.

**Citations**

* When a response involves retrieval, display citations.  
* Render citations at the end of the message as a **hoverable card** the tester can inspect.

---

### **3.2 RAG System**

**Storage**

* PostgreSQL \+ **pgvector**.  
* Knowledge base is already dumped into the DB (\~1,200 entries).

**Local DB connection**

| Setting | Value |
| ----- | ----- |
| Host | `localhost` |
| Port | `5433` |
| Database | `customer_support_chatbot` |
| User | `atharva` |

* Configuration must come from a **`.env` file**. In production, only the **host** will change — the `.env` will be updated accordingly. Do not hardcode connection details.

**Retrieval requirements**

* Embeddings: **`text-embedding-3-large`** ("large v3"), **no truncation / full dimensions**.  
* Search: **sequential (exact) scan** — no ANN index needed since the corpus is only \~1,200 entries.  
* Hybrid retrieval (vector \+ keyword) per the RAG guide in `docs/rag_guide/`.  
* Must **return citations** with retrieved chunks.

**Reference:** follow the RAG build guide for implementation details:

* [`docs/rag_guide/1_building_rag_pt1.md`](rag_guide/1_building_rag_pt1.md) — step-by-step Hybrid RAG on PostgreSQL (chunking, embeddings, hybrid retrieval).

---

### **3.3 RAG Evals**

Refer to the RAG evaluation guides in `docs/rag_guide/`:

* [`docs/rag_guide/2_rag_eval_synthetic_data.md`](rag_guide/2_rag_eval_synthetic_data.md) — generating synthetic test data for the RAG eval set.  
* [`docs/rag_guide/3_rag_eval.md`](rag_guide/3_rag_eval.md) — evaluating retrieval + generation quality.

---

### **3.4 Agentic Loop**

**Model**

* Anthropic Sonnet, **thinking disabled**.  
* ⚠️ **Confirm model string.** "Sonnet 3.6" is a community nickname, not an official Anthropic model name. The intended model is most likely `claude-3-5-sonnet-20241022`. Verify against current Anthropic docs before implementation.

**Loop behavior**

* Simple agentic loop (call model → execute tool calls → feed results back → repeat until final answer).  
* If the user's query is unclear, the agent may ask **follow-up questions**, capped at **2 per conversation**.  
* Max conversation length: **10 messages** total (to-and-fro).  
* If the caps are reached without resolution: ask the user **whether they'd like to raise a support query/ticket**.  
* When the RAG tool is used, the final answer must **include citations**.

**System prompt requirements** The system prompt must include:

1. The **list of tools** available to the agent.  
2. A **list of question categories** the knowledge base can answer, so the agent knows what's in scope.

---

### **3.5 Chatbot Evals**

Beyond RAG-level evals (3.3), the end-to-end agentic chatbot must be evaluated over **full multi-turn conversations** — capturing context retention, goal completion, guardrail adherence, and behavioral consistency across every turn, not just single input/output pairs.

**Approach**

* **Multi-turn simulation:** automatically generate realistic conversations between a simulated user and the chatbot, so scenarios can be tested without manual chatting. This is the foundation of the multi-turn eval set.  
* **Multi-turn metrics:** score the whole conversation (context retention, relevance, goal completion, consistency), not isolated turns.

**Reference:** follow the chatbot eval guides in `docs/chatbot_eval/`:

* [`docs/chatbot_eval/1_multi_turn_eval.md`](chatbot_eval/1_multi_turn_eval.md) — multi-turn evaluation overview.  
* [`docs/chatbot_eval/2_multi_turn_eval_metrics.md`](chatbot_eval/2_multi_turn_eval_metrics.md) — the multi-turn metrics to measure.  
* [`docs/chatbot_eval/3_multi_turn_simulation.md`](chatbot_eval/3_multi_turn_simulation.md) — simulating conversations to build the eval set.

---

### **3.6 Tracing & Observability**

Both the RAG retrieval path and the multi-turn agentic loop must be **traced** so runs can be inspected end-to-end — spans for retrieval, tool calls, model calls, and per-turn agent behavior — feeding both debugging and the eval workflows above.

**Reference:** follow the tracing guides in `docs/tracing/`:

* [`docs/tracing/1_rag_tracing.md`](tracing/1_rag_tracing.md) — tracing the RAG application (retrieval + generation spans).  
* [`docs/tracing/2_multi_turn_chat_tracing.md`](tracing/2_multi_turn_chat_tracing.md) — tracing the multi-turn agentic chat.

---

## **4\. Tools**

### **4.1 CML Report API**

**TODO — incomplete in source doc.** Fill in:

* Endpoint URL  
* Request body schema  
* Response schema  
* Auth header requirements (presumably same auth token as Contract Note)

### **4.2 RAG Tool**

| Field | Details |
| ----- | ----- |
| Parameters | `query` (string) |
| Returns | Retrieved chunks \+ citations |

**TODO:** Finalize the return schema. Suggested starting point:

{  
  "chunks": \[  
    {  
      "id": "kb-00123",  
      "text": "…chunk content…",  
      "score": 0.87,  
      "citation": {  
        "source": "document title / URL",  
        "section": "optional section heading"  
      }  
    }  
  \]  
}

### **4.3 Contract Note API**

* **Endpoint:** `POST https://finx.choiceindia.com/mis/v2/contract-note/generate`  
* **Headers:** same auth token header as other Reports APIs (session token from login page).  
* **Request body:**

{  
  "mobileNo": "9920885615",  
  "contractDate": "01-07-2024"  
}

* `contractDate` format: `DD-MM-YYYY`.  
* The `mobileNo` above is a **test value only**.

**Generating an auth token for testing**

**TODO — commands missing from source doc.** Add the commands required to generate the auth token for local testing.

---

## **5\. Guardrails**

1. **SEBI compliance:** the bot must **never provide opinions, advice, or recommendations** on reports or investments — no matter how much the user pushes.  
2. **Scope enforcement:** do not respond to messages unrelated to **Choice FinX**; politely redirect.  
3. Guardrails must hold across the entire conversation, including after follow-up questions and tool use.

---

## **6\. Configuration (`.env`)**

\# Anthropic  
ANTHROPIC\_API\_KEY=            \# per-tester keys: Pritam, Ajay, Ankit Sir, Atharva  
ANTHROPIC\_MODEL=              \# confirm exact Sonnet model string

\# Embeddings  
EMBEDDING\_MODEL=text-embedding-3-large  
EMBEDDING\_API\_KEY=

\# Postgres (local defaults; only DB\_HOST changes in production)  
DB\_HOST=localhost  
DB\_PORT=5433  
DB\_NAME=customer\_support\_chatbot  
DB\_USER=atharva  
DB\_PASSWORD=

\# Reports API  
FINX\_BASE\_URL=https://finx.choiceindia.com

---

## **7\. Suggested Repo Structure**

.  
├── docs/                  \# RAG blog reference, RAG evals doc, agentic loop doc  
├── backend/  
│   ├── agent/             \# agentic loop, system prompt, tool definitions  
│   ├── rag/               \# embedding, retrieval, citation formatting  
│   ├── tools/             \# CML report, contract note API clients  
│   ├── api/               \# SSE endpoints, session handling  
│   └── evals/             \# RAG evaluation harness  
├── frontend/              \# POC chat UI (white/blue, mobile compatible)  
└── .env.example

---

## **8\. Acceptance Criteria (Phase 1\)**

* \[ \] Tester can log in with client code \+ session token (inputs trimmed).  
* \[ \] Chat streams intermediate agent steps and final output via SSE.  
* \[ \] Cumulative INR cost card visible (web); per-message cost \+ latency shown under each message.  
* \[ \] RAG retrieval works over pgvector with large-v3 embeddings, sequential scan, and returns citations.  
* \[ \] Citations render as hoverable cards.  
* \[ \] Agent asks at most 2 clarifying questions; conversation capped at 10 messages; offers to raise a query at cap.  
* \[ \] Contract Note API callable with session token.  
* \[ \] Guardrails: no opinions on reports (SEBI); off-topic messages declined.

---

## **9\. Open Items**

| \# | Item | Owner |
| ----- | ----- | ----- |
| 1 | Complete CML Report API spec (endpoint, schemas, auth) | Atharva |
| 2 | Auth token generation commands for local testing | Atharva |
| 3 | Finalize RAG tool return schema | Team |
| 4 | Confirm exact Anthropic model string | Team |
| 5 | Link exact filenames of docs in `docs/` folder | Atharva |
