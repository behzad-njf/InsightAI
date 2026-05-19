# Integration tests

## Phase 7 product E2E (`test_chat_product_e2e.py`)

Full product flow against **SQLite** + **mocked LLM** (no Groq/MSSQL required):

- `POST /api/v1/chat/sessions` → `POST /api/v1/chat` → `GET .../messages`
- API key auth and rate limiting (429 + `Retry-After`)
- Health remains public

```bash
pytest tests/integration/test_chat_product_e2e.py -m integration
```

## Chat streaming SSE (`test_chat_stream_e2e.py`)

- `POST /api/v1/chat/stream` — status → token → done events
- Auth (401 without key), rate limit (429), session history on `done`
- Disable flag: `INSIGHTAI_CHAT_STREAMING_ENABLED=false` → 404 (in `test_chat_product_e2e.py`)

```bash
pytest tests/integration/test_chat_stream_e2e.py -m streaming
pytest tests/integration/ -m "integration or streaming"
```

SSE parsing helper: `sse_helpers.py`. Shared client factory: `chat_product_fixtures.py`.
