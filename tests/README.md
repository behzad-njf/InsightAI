# Tests

## Layout

| Directory | Purpose |
|-----------|---------|
| `tests/unit/` | Fast, isolated tests (no network) |
| `tests/integration/` | FastAPI TestClient, SQLite, mocked LLM |

## Run

```bash
# Full gate (ruff + mypy + pytest + coverage)
./scripts/test.sh

# Pytest only
pytest tests -q
pytest tests/unit -q
pytest tests/integration -q
pytest -m integration -q
```

## Fixtures

| Location | Purpose |
|----------|---------|
| `conftest.py` | `make_settings()`, `api_client`, mocked AI/DB |
| `fixtures/sql_generation_samples.py` | Classroom NL→SQL scenario, unsafe SQL cases |

### Phase 6 answer generation prompts

`tests/unit/test_answer_prompt_loader.py` — prompt files, `render_answer_generation_messages()`, `format_query_result_for_prompt()`.

`tests/unit/test_answer_generator.py`, `test_generate_answer_use_case.py` — mocked LLM answer pipeline (Phase 6.2).

`tests/unit/test_result_sampling.py` — head/tail/spread sampling for large `QueryResult` sets (Phase 6.3).

`tests/unit/test_ask_use_case.py`, `tests/integration/test_ask_e2e.py` — full ask pipeline (Phase 6.4).

### Phase 3 SQL generation tests

`tests/unit/test_sql_generation_acceptance.py` — mocked LLM responses, read-only enforcement, token usage, prompt files. No network or live Groq calls.

`tests/integration/test_sql_generate_api.py` — `POST /api/v1/sql/generate` with mocked LLM + real schema file.

`tests/integration/test_ask_api.py` — `POST /api/v1/ask` full pipeline (SQLite + mocked LLM).

## Fixtures (`conftest.py`)

- `make_settings()` — ignores repo `.env`
- `api_client` — app with mocked AI + healthy DB
- `api_client_no_database` — DB startup fails gracefully

## CI

GitHub Actions workflow: `.github/workflows/ci.yml` (Python 3.11 + 3.12).

## Smoke (manual)

```bash
uvicorn insightai.main:create_app --factory --reload
./scripts/smoke_api.sh
INSIGHTAI_SMOKE_REQUIRE_LLM=true ./scripts/smoke_api.sh
./scripts/smoke_docker.sh
```
