## 1. App & entrypoint

- [ ] 1.1 Implement `backend/api/app.py` with `create_app() -> FastAPI` + module-level `app`; add `CORSMiddleware` (POC origins), include the session + chat routers, and call P8 `configure_tracing()` on startup
- [ ] 1.2 Implement `backend/api/__main__.py` server entrypoint running `uvicorn.run("backend.api.app:app", host="0.0.0.0", port=8000)` (runnable as `python -m backend.api`)

## 2. Session store

- [ ] 2.1 Implement `backend/api/state.py`: `ThreadState` dataclass (`session`, `history`, `cost`) and `SessionStore` with `create`, `exists`, `get_session`, `get_history`, `append_turn`, `record_turn`; export module-level `store` singleton
- [ ] 2.2 Ensure `record_turn` appends the `MessageCost` and keeps `cost.cumulative_cost_inr == sum(m.cost_inr)`, returning the new cumulative

## 3. SSE framing

- [ ] 3.1 Implement `backend/api/sse.py::format_sse(event: SSEEvent) -> str` producing `data: <compact-json>\n\n` from `event.model_dump()`; define `SSE_HEADERS` (`Content-Type`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`)

## 4. Session endpoint

- [ ] 4.1 Implement `backend/api/routes_session.py` with `SessionRequest`/`SessionResponse`/`ErrorResponse` and `POST /api/session` handler: trim inputs, `400` on empty-after-trim, else build `SessionContext`, mint `new_thread_id()`, `store.create(...)`, return `{ok, thread_id}`

## 5. Chat endpoint

- [ ] 5.1 Implement `backend/api/routes_chat.py` with `ChatRequest` and `POST /api/chat` returning `StreamingResponse(..., media_type="text/event-stream", headers=SSE_HEADERS)`
- [ ] 5.2 Implement the `_chat_stream` async generator: validate message/thread_id (emit `ErrorEvent` frame + close on failure), iterate `run_agent_turn(...)`, `yield format_sse(event)` for each, accumulate assistant text + citations
- [ ] 5.3 On `DoneEvent`: `store.record_turn(cost)`, overwrite the frame's `cumulative_cost_inr` with the store total; after stream ends, `store.append_turn(user_message, assistant_text)`

## 6. Verification

- [ ] 6.1 `pytest backend/tests/test_api.py` — with `run_agent_turn` mocked to yield step→token→citations→done, an httpx SSE client against `/api/chat` receives the frames in order and the `done` frame's cumulative INR equals the summed message cost; `/api/session` trims inputs and returns a `thread_id`; empty inputs return `400`; unknown `thread_id` yields one `error` frame
- [ ] 6.2 Manual: `curl -N -X POST localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"message":"...","thread_id":"<id>"}'` streams `step`→`token`→`citations`→`done` frames end-to-end
