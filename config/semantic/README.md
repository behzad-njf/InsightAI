# Trusted semantic layer (`config/semantic/`)

> **Phase 11** — per-deployment approved SQL. Not shared across customers; each InsightAI instance has its own `config/semantic/` directory.

## Purpose

Reduce LLM use and increase analyst trust by defining:

1. **Trusted metrics** — canonical SQL for KPIs (counts, rates, standard reports).
2. **Example queries** — golden natural-language questions with approved SQL.

When a user question matches an asset, InsightAI can return SQL from YAML (labeled `generation_source: trusted_metric` or `trusted_example`) instead of generating SQL from scratch.

**Trusted ≠ bypass safety.** Matched SQL still runs through read-only validation (Phase 4) and future governance (Phase 12).

## Files in this directory

| File | Required | Description |
|------|----------|-------------|
| `trusted_metrics.yaml` | Recommended | List of `metrics[]` (see schema below) |
| `example_queries.yaml` | Recommended | List of `example_queries[]` |
| `examples/<vertical>/` | Optional | Starter packs to **copy** into the files above — never loaded automatically unless you merge them |

## YAML schema

### `trusted_metrics.yaml`

```yaml
metrics:
  - id: unique_snake_case_id          # required
    title: Human-readable name        # required
    sql: |                            # required — read-only SELECT
      SELECT COUNT(*) AS metric_value
      FROM dbo.some_table
    description: When analysts should use this metric
    question_hints:                   # optional — NL phrases for rule-based match (step 11.4+)
      - how many active records
    tags: [enrollment, daily]       # optional — documentation / future UI
    enabled: true                     # optional, default true
    dialect: mssql                    # optional — mssql | postgres | sqlite
```

### `example_queries.yaml`

```yaml
example_queries:
  - id: unique_snake_case_id
    question: Canonical question text?
    sql: |
      SELECT ...
    description: Notes for operators
    question_aliases:                 # optional alternate phrasings
      - same question different words?
    tags: []
    enabled: true
    dialect: mssql
```

Field names map to domain models in `insightai.domain.models.semantic` (`TrustedMetric`, `ExampleQuery`).

## Authoring guidelines (any industry)

1. **Use real table/column names** from this instance’s `schema/database_schema.md`.
2. **Read-only SQL only** — same rules as the AI layer (`SELECT`; no writes).
3. **Prefer stable SQL** — avoid `GETDATE()` in trusted assets unless the metric is explicitly “as of today”; document time semantics in `description`.
4. **One clear id per asset** — ids appear in audit logs and API responses (`trusted_asset_id`).
5. **Question hints / aliases** — add common phrasings your users ask; matching is rule-based (normalized text / SQL), not fuzzy LLM similarity.
6. **Do not put secrets** in YAML (connection strings, API keys).
7. **No PII in descriptions** — use role names (“student”, “staff”) not real person names in examples.

## Vertical starter packs

Optional copies under `examples/` (e.g. `examples/education/`) illustrate one deployment shape. **Copy** rows into `trusted_metrics.yaml` / `example_queries.yaml` and edit for your schema — the runtime does not hardcode “education” or “campus” in Python.

## Enablement

| Step | Feature | Status |
|------|---------|--------|
| 11.3 | YAML loader (`YamlSemanticCatalogLoader`) | ✅ |
| 11.4 | SQL normalizer + matcher (`TrustedSQLMatcher`) | ✅ |
| 11.5 | Wire into generate-SQL / chat | ✅ (`GenerateSQLUseCase`; chat fields in 11.6–11.7) |

Environment (loader available; pipeline wiring in 11.5):

```bash
INSIGHTAI_SEMANTIC_ENABLED=false   # default — matcher not wired yet
INSIGHTAI_SEMANTIC_PATH=config/semantic
```

Set `INSIGHTAI_SEMANTIC_ENABLED=true` and populate YAML to use trusted matching on `/api/v1/sql/generate` and the ask pipeline (when semantic is enabled in deps). Chat-specific `dry_run` / response fields: steps 11.6–11.7.

## Validation (upcoming CLI)

```bash
insightai-semantic-validate    # schema + SQL parse check (step 11.9)
insightai-semantic-test-match  # try a question against the catalog
```

## See also

- [docs/PHASE_11_TRUSTED_SEMANTIC.md](../../docs/PHASE_11_TRUSTED_SEMANTIC.md) — implementation checklist
- [FUTURE_PHASES.md](../../FUTURE_PHASES.md) — Phase 11 acceptance criteria
- [Knowledge/README.md](../../Knowledge/README.md) — narrative rules (RAG); semantic layer is **structured SQL assets**
