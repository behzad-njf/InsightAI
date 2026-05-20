# InsightAI

**InsightAI** is a production-oriented platform that turns natural language questions into **safe, read-only SQL**, runs queries against your operational database, and returns **grounded natural-language answers** backed by real row data.

Ask in plain English — get SQL, results, and a summary you can trust. The system is designed for multi-table operational schemas (schools, classrooms, enrollments, staff, and similar domains) without exposing write access to the database.

---

## What it does

```text
Natural language question
    → Relevant schema context (from documented metadata)
    → LLM generates read-only SQL
    → Multi-layer SQL safety validation
    → Execute SELECT on a readonly connection
    → LLM summarizes results (no invented numbers)
    → JSON answer via REST API (sync chat, SSE stream, or debug endpoints)
```

Typical latency for a full question (SQL + DB + answer) is on the order of **2–30 seconds**, depending on schema size, query complexity, and LLM provider.

---

## Current status

| Phase | Capability | Status |
|-------|------------|--------|
| 1 | Foundation — FastAPI, config, LLM providers, DB layer, Docker | Complete |
| 2 | Schema intelligence — markdown schema → context for the LLM | Complete |
| 3 | SQL generation — NL → SQL with Groq/OpenAI | Complete |
| 4 | SQL safety — sqlglot AST + composite validator | Complete |
| 5 | Query execution — timeouts, row caps, MSSQL/Postgres/SQLite | Complete |
| 6 | Answer generation — grounded summaries from query results | Complete |
| 7 | Product API — chat, sessions, auth, rate limits, **SSE streaming** | Complete |
| 8 | Observability — audit logs, LLM usage, OTEL tracing, Prometheus `/metrics` (optional) | In progress |
| 9 | Performance — Redis caching | Planned |
| 10 | Hybrid RAG — vectors + SQL | Planned |

Roadmap detail: [AGENT_PHASES.md](AGENT_PHASES.md). Maintainer guide: [AGENT.md](AGENT.md).

---

## Features

### Schema-aware SQL generation

- Loads table/column/join metadata from `schema/database_schema.md` (source of truth).
- Injects only relevant tables into the prompt (configurable cap).
- Outputs structured JSON: SQL, explanation, confidence, tables used.

### Read-only SQL safety

- **Keyword blocklist** for obvious write operations.
- **sqlglot AST** validation — only `SELECT` (and safe `WITH` … `SELECT`) accepted.
- **Composite validator** — AST is authoritative; keyword layer is fail-closed backup.
- Rejects multi-statement batches, dangerous functions, and policy violations before execution.

### Query execution

- Read-only SQLAlchemy executor with dialect support: **Microsoft SQL Server**, **PostgreSQL**, **SQLite**.
- Configurable **row cap** (`INSIGHTAI_SQL_MAX_ROWS`, default 1000).
- Per-query **timeout** (`INSIGHTAI_SQL_QUERY_TIMEOUT_SECONDS`, default 120s).
- Truncation detection when results exceed the cap.

### Grounded answer generation

- Summarizes query results in plain English.
- Prompt rules: cite real column names and row counts; do not invent data.
- Row sampling (head/tail/spread) for large result sets in the LLM prompt.
- Handles empty results and truncated sets explicitly.

### Product chat API (Phase 7)

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/chat` | Main product endpoint — one question → answer (sync JSON) |
| `POST /api/v1/chat/stream` | Same pipeline via **SSE** — status, answer tokens, then `done` |
| `POST /api/v1/chat/sessions` | Create a conversation session |
| `GET /api/v1/chat/sessions/{id}` | Session metadata |
| `GET /api/v1/chat/sessions/{id}/messages` | Conversation history |
| `DELETE /api/v1/chat/sessions/{id}` | Delete session |

**Debug / power-user:**

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/ask` | Full pipeline payload — SQL, rows, token usage, timings |
| `POST /api/v1/sql/generate` | SQL generation only |
| `GET /api/v1/schema/context` | Schema context for a question |
| `POST /api/v1/ai/complete` | Raw LLM smoke test (not the product API) |
| `POST /api/v1/ai/complete/stream` | Raw LLM SSE stream (`token` → `done`; public, no auth) |

**Public (no auth):**

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/health` | Liveness |
| `GET /api/v1/health/ready` | Readiness (includes DB check) |

### Sessions and history

- Optional `session_id` on chat requests (or `X-Session-ID` header).
- Each turn stores user + assistant messages (in-memory by default; Redis optional).
- Session TTL and message limits are configurable.

### Authentication

- `INSIGHTAI_API_AUTH_MODE`: `none` | `api_key` | `jwt`
- API keys via `X-API-Key` or `Authorization: Bearer <key>`
- **Production** requires auth mode other than `none` (settings validator).
- Protected routes: `/chat`, `/chat/stream`, `/ask`, `/sql`, `/schema`. Health and `/ai/complete` stay public.

### Response streaming (SSE)

`POST /api/v1/chat/stream` uses **Server-Sent Events** (`text/event-stream`):

| Event | When | Payload |
|-------|------|---------|
| `status` | SQL / query / answer phase starts | `{"phase": "generating_sql" \| "executing_query" \| "generating_answer"}` |
| `token` | Answer text delta | `{"text": "..."}` |
| `done` | Pipeline finished | Full chat JSON (same fields as sync `POST /chat`) |
| `error` | Failure | `{"error_message", "error_code", "request_id"}` |

- Toggle: `INSIGHTAI_CHAT_STREAMING_ENABLED` (default `true`; `false` → HTTP 404).
- Session history is written on **`done`** (not on each token).
- Auth and rate limits match sync `/chat`.

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"question": "How many active classrooms are there?"}'
```

### Rate limiting

- Sliding window per authenticated principal or client IP.
- Returns **HTTP 429** with `Retry-After` and `retry_after_seconds` in JSON.
- Configurable: `INSIGHTAI_RATE_LIMIT_ENABLED`, `_REQUESTS`, `_WINDOW_SECONDS`, `_STORE` (`memory` | `redis`).

### Observability (foundation)

- Structured logging (`structlog`) with **request ID** on every HTTP call (`X-Request-ID`).
- Pipeline timings logged: SQL generation, query execution, answer generation.

---

## Security model

InsightAI is **read-only by design**:

1. Generated SQL must pass parser + policy validation.
2. Only `SELECT` statements are executed.
3. Database credentials should use a **read-only** DB user.
4. API keys and JWT protect product endpoints in production.

Do not point the app at a write-capable database role in production.

---

## Architecture

Hexagonal (ports & adapters):

```text
api/              → FastAPI routes, schemas, auth, rate limits
application/      → Use cases (ask, chat sessions, generate SQL, run query, …)
domain/           → Models, ports, exceptions
infrastructure/   → LLM, DB, schema parser, prompts, safety validators
prompts/          → LLM system/user templates
schema/           → database_schema.md (metadata source of truth)
```

**Core use case:** `AskUseCase` orchestrates schema context → SQL → validate → execute → answer.

---

## Tech stack

- **Python 3.12+**, FastAPI, Pydantic v2, Uvicorn
- **SQLAlchemy 2** — MSSQL (pyodbc), PostgreSQL, SQLite
- **LlamaIndex** (primary AI framework adapter)
- **Groq Cloud** (default LLM), **OpenAI** (secondary)
- **sqlglot** — SQL parsing and safety
- **Redis** (optional) — sessions and rate limits
- **Docker Compose** — local API + Postgres demo DB

---

## Quick start

### Local development

```bash
cd InsightAI
python3.11 -m venv .venv
source .venv/bin/activate

cp .env.example .env
# Set GROQ_API_KEY and database settings (see Configuration)

pip install -e ".[dev]"
# MSSQL: pip install -e ".[dev,mssql]"

uvicorn insightai.main:create_app --factory --reload
# or: insightai
```

Verify:

```bash
curl http://localhost:8000/api/v1/health
open http://localhost:8000/docs
```

### Try it — simple demo clients

**CLI** (easiest):

```bash
# With the API running (see above):
python scripts/ask.py "How many active classrooms are there?"
python scripts/ask.py --stream "How many students per classroom?"
python scripts/ask.py   # interactive — type questions until you press Enter on empty line
```

**Browser UI:** `python apps/serve_demo.py` → open http://127.0.0.1:8765

See [apps/README.md](apps/README.md) for options (`--include-sql`, API key, etc.).

### Product chat (curl)

```bash
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"question": "How many active classrooms are there?"}'
```

### Session + history

```bash
SESSION=$(curl -s -X POST http://localhost:8000/api/v1/chat/sessions \
  -H 'Content-Type: application/json' \
  -d '{"title": "Enrollment questions"}' | jq -r .id)

curl -s -X POST http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d "{\"question\": \"How many students per classroom?\", \"session_id\": \"$SESSION\"}"

curl -s "http://localhost:8000/api/v1/chat/sessions/$SESSION/messages"
```

### Streaming chat (SSE)

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d "{\"question\": \"How many students per classroom?\", \"session_id\": \"$SESSION\"}"
```

You will see `event: status`, `event: token`, and a final `event: done` with the complete JSON answer.

### Docker (demo Postgres)

```bash
cp .env.example .env   # set GROQ_API_KEY
docker compose up --build
```

The Compose stack uses a **sample Postgres** database for demos. For **Microsoft SQL Server** in Docker, run the API on the host (or extend the image with ODBC) and set `DB_HOST=localhost` — see [docker/README.md](docker/README.md).

---

## Configuration

Copy `.env.example` to `.env`. Important variables:

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Groq Cloud API key (required for LLM) |
| `INSIGHTAI_DATABASE_KIND` | `mssql` \| `postgresql` \| `sqlite` |
| `DB_READONLY_USER` / `DB_READONLY_PASSWORD` | Preferred for MSSQL (auto URL-encoding) |
| `INSIGHTAI_SQL_MAX_ROWS` | Max rows per query (default 1000) |
| `INSIGHTAI_SQL_QUERY_TIMEOUT_SECONDS` | Query timeout (default 120) |
| `INSIGHTAI_API_AUTH_MODE` | `none` \| `api_key` \| `jwt` |
| `INSIGHTAI_API_KEYS` | Comma-separated API keys |
| `INSIGHTAI_RATE_LIMIT_ENABLED` | Enable rate limiting |
| `INSIGHTAI_CHAT_STREAMING_ENABLED` | Enable `POST /api/v1/chat/stream` (default true) |
| `INSIGHTAI_CHAT_SESSION_STORE` | `memory` \| `redis` |

Full list: [.env.example](.env.example).

---

## Example questions (live testing)

The examples below are adapted from real end-to-end runs against a **multi-school operational database** (classrooms, enrollments, users). Names and identifiers are **anonymized**; behavior and row counts reflect actual system responses.

### Inventory and aggregates

| Question | Typical outcome (summary) |
|----------|---------------------------|
| *How many classrooms do I have?* | Returns dozens of classrooms (e.g. ~40 rows). Answer lists sample names such as **Sunrise Room**, **Pine Studio**, **Maple Wing**, **Oak Building**, **Music Studio**. |
| *How many children are in each classroom?* | One row per classroom with counts (e.g. 19 classrooms). Example: **Building A** ~48 students, **Sunrise Room** ~1, **River Campus** ~28, **Oak Building** ~31. |

### Membership and names (precision matters)

| Question | Typical outcome (summary) |
|----------|---------------------------|
| *Who is in Sunrise Room classroom?* (extra word in name) | Often **0 rows** — classroom stored as `Sunrise Room` without the extra word. |
| *Who is in Sunrise Room?* (ambiguous) | May **0 rows** if the model searches the wrong table (e.g. activity titles instead of enrollments). |
| *Who is in Sunrise Room? It is a classroom name.* | **1 row** — e.g. user id `122`, username `student001@example.org`, classroom **Sunrise Room**. |
| *Who is in Sunrise Room? Tell me the student's name.* | **1 row** — e.g. first name **Alex**, last name **Rivera**. |

**Takeaway:** Clear questions that match exact classroom names in the schema work best. The debug `/ask` endpoint returns generated SQL so you can refine wording.

### Product vs debug API

| API | Best for |
|-----|----------|
| `POST /api/v1/chat` | Production — single JSON response when you do not need live tokens |
| `POST /api/v1/chat/stream` | Production UI — progressive status + answer text via SSE |
| `POST /api/v1/ask` | Debugging — full SQL, row payload, token usage, schema tables used |

Example chat response shape (abbreviated):

```json
{
  "question": "How many classrooms do I have?",
  "answer": "The query returned 40 rows, which means you have 40 classrooms...",
  "row_count": 40,
  "truncation_noted": false,
  "request_id": "a6f6bfdf-f684-4bbc-a50b-34051a489dd9",
  "session_id": "d8a044a4-46fc-4530-8f78-8489ed1ccab9",
  "timings": {
    "sql_generation_ms": 2435.5,
    "query_execution_ms": 56.66,
    "answer_generation_ms": 871.54,
    "total_ms": 3365.41
  }
}
```

Optional flags on chat: `include_sql`, `include_data`, `timeout_seconds`.

---

## Development

```bash
pip install -e ".[dev]"
./scripts/test.sh              # ruff + mypy + pytest
pytest tests -q                # all tests
pytest tests/unit -q           # unit only
pytest tests/integration/test_chat_product_e2e.py -m integration
pytest tests/integration/test_chat_stream_e2e.py -m streaming
```

Test layout: [tests/README.md](tests/README.md), [tests/integration/README.md](tests/integration/README.md).

### MSSQL integration tests (optional)

```bash
export INSIGHTAI_MSSQL_INTEGRATION_URL="mssql+pyodbc://..."
pytest -m mssql
```

---

## Project layout

```text
src/insightai/       Application code
schema/              Database metadata (markdown)
prompts/             LLM prompts (SQL + answer generation)
tests/               Unit and integration tests
docker/              Compose + Postgres init scripts
AGENT.md             Maintainer / agent guide
AGENT_PHASES.md      Phase roadmap
REAL_TEST.md         Raw curl transcripts (developer reference)
```

---

## Documentation maintenance

**Contributors and agents:** when you add or change user-facing behavior, API routes, configuration, or phase completion, **update this README** in the same change set. Keep [AGENT.md](AGENT.md) and [AGENT_PHASES.md](AGENT_PHASES.md) in sync for phase status.

---

## License

Copyright (c) 2025 **MrHiB**. Released under the [MIT License](LICENSE).

**Attribution:** If you use, modify, or redistribute this project (including building an app on top of it), you must credit **InsightAI by MrHiB** and link to the canonical repository. See [NOTICE](NOTICE) for details.

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities and a production deployment checklist.
