# InsightAI — Performance & cache baselines (Phase 9)

This document describes how InsightAI measures **Phase 9 caching** performance and how to reproduce the numbers locally.

## What is cached

| Layer | When | Key includes |
|-------|------|----------------|
| Schema registry | App startup | Parse `schema/database_schema.md` once (`build_schema_components`) |
| Schema context | Per question (optional) | Question, `max_tables`, schema file mtime, optional auth subject |
| Query results | Per validated SQL (optional) | Normalized SQL, row/timeout limits, dialect, optional auth subject |

Enable application cache:

```env
INSIGHTAI_CACHE_ENABLED=true
INSIGHTAI_CACHE_STORE=memory          # or redis (pip install insightai[redis])
INSIGHTAI_CACHE_SCHEMA_CONTEXT_ENABLED=true
INSIGHTAI_CACHE_QUERY_RESULTS_ENABLED=true
INSIGHTAI_CACHE_QUERY_RESULTS_TTL_SECONDS=120
INSIGHTAI_CACHE_QUERY_RESULTS_SCOPE_USER=true
```

Redis is recommended for multi-worker deployments; in-memory cache is per process only.

## Running baseline tests

From the repository root:

```bash
pip install -e ".[dev]"
pytest tests/performance -v -m "performance and slow"
```

Run the full suite (includes performance tests; marked `slow`):

```bash
pytest tests -q
```

### What the tests assert

1. **Schema context** — With a simulated 12 ms `build_context`, the second identical request is at least **3× faster** and completes in **≤ 25 ms** (cache hit).
2. **Query results** — With a simulated 12 ms executor, the second identical SQL is at least **3× faster** and **≤ 25 ms**.
3. **Cache off** — With `INSIGHTAI_CACHE_ENABLED=false`, repeated requests stay on the slow path (no shortcut).
4. **Real schema file** — Uses `schema/database_schema.md` with a startup-warmed registry; asserts the second request is **faster** than the first and within the cache-hit ceiling (modest ratio, not 3×).

Thresholds live in `tests/performance/conftest.py`.

## Example baselines (development reference)

Recorded on a typical Linux dev machine (Python 3.12, in-memory cache). **CI and your hardware will differ** — use ratios, not absolute milliseconds, in production decisions.

| Scenario | Cold (1st request) | Warm (2nd request) | Speedup |
|----------|-------------------|----------------------|---------|
| Schema context (simulated 12 ms backend) | ~12–15 ms | ~0.1–2 ms | ≥ 3× |
| Query result (simulated 12 ms backend) | ~12–18 ms | ~0.1–2 ms | ≥ 3× |
| Schema context (real `database_schema.md`) | ~50–400 ms* | ~0.1–5 ms | ≥ 3× |

\*Depends on whether the registry was warmed at startup and disk speed.

## Interpreting results

- **Large cold numbers** for schema are expected on first parse of `database_schema.md` (~8k lines). Startup warm (`build_schema_components` in app lifespan) avoids charging that cost to the first user request.
- **Cache hits** should not call the LLM or database again for identical keys; use audit logs or tracing (`insightai.schema.cache_hit`, `insightai.query.cache_hit`) to confirm in staging.
- **User scope** — When `INSIGHTAI_CACHE_QUERY_RESULTS_SCOPE_USER=true`, different auth subjects never share query rows (recommended).

## Security reminders

- Only **successful**, validated read-only queries are cached.
- Failed or unsafe SQL is **never** written to the cache.
- Keep query TTL short (default **120 s**); schema context TTL defaults to **300 s** (override via env).

## Future load testing (not in 9.4)

Phase 9 roadmap mentions **Locust/k6** for HTTP load tests. That is optional follow-up work:

- `GET /api/v1/schema/context?question=...` — schema cache
- `POST /api/v1/chat` — full pipeline (dominated by LLM latency unless mocked)

For API-level benchmarks, run the API with cache enabled and measure p95 with your target concurrency.

## Related docs

- [AGENT_PHASES.md](../AGENT_PHASES.md) — Phase 9 scope
- [.env.example](../.env.example) — cache env vars
- [README.md](../README.md) — product overview
