# Phase 11 — Trusted semantic layer (implementation log)

> **Roadmap:** [FUTURE_PHASES.md](../FUTURE_PHASES.md) § Phase 11  
> **Status:** ✅ Complete (2026-05-22)  
> **Workflow:** Steps 11.1–11.9 done; next global phase per [FUTURE_PHASES.md](../FUTURE_PHASES.md) is **Phase 16** (API key auth) unless you choose **Phase 12** (governance) first.

---

## Goal

Label answers **trusted** when SQL matches approved metrics or example queries in `config/semantic/`. Support `dry_run` (generate + validate, no DB) and `generation_source` on API responses.

---

## Step checklist

| Step | Task | Status | Notes |
|------|------|--------|-------|
| **11.1** | Domain models (`TrustedMetric`, `ExampleQuery`, `GenerationSource`, …) | ✅ Done | `domain/models/semantic.py`, `tests/unit/test_semantic_models.py` |
| **11.2** | `config/semantic/` layout + README template | ✅ Done | `config/semantic/*.yaml`, `config/README.md` |
| **11.3** | YAML loader (`infrastructure/semantic/`) | ✅ Done | `YamlSemanticCatalogLoader`, settings, tests |
| **11.4** | SQL normalizer + `ITrustedSQLMatcher` | ✅ Done | `TrustedSQLMatcher`, `MatchTrustedSQLUseCase` |
| **11.5** | Wire `GenerateSQLUseCase` (trusted before LLM) | ✅ Done | bootstrap, deps, `/sql/generate` fields |
| **11.6** | `ChatRequest`: `mode`, `use_llm` | ✅ Done | `dry_run` validates only; chat + `/ask` fields |
| **11.7** | Response schemas: `generation_source`, `trusted_asset_id` | ✅ Done | On `/chat`, `/ask`, `/sql/generate` (structured audit extension optional later) |
| **11.8** | Example pack `config/semantic/examples/education/` | ✅ Done | 3 metrics, 4 example queries; copy-only |
| **11.9** | Unit tests, CLI, README | ✅ Done | `insightai-semantic-validate`, `insightai-semantic-test-match` |

---

## Step 11.1 — Domain models (complete)

### Types (`insightai.domain.models.semantic`)

| Type | Purpose |
|------|---------|
| `GenerationSource` | `llm`, `trusted_metric`, `trusted_example`, `rule_template` |
| `TrustedAssetKind` | `metric`, `example_query` |
| `TrustedMatchConfidence` | `exact_sql`, `normalized_sql`, `question_match`, `none` |
| `TrustedMetric` | Approved metric id, title, sql, optional `question_hints` |
| `ExampleQuery` | Approved question + sql + optional `question_aliases` |
| `SemanticCatalog` | Loaded metrics + examples for one instance |
| `TrustedSQLMatchRequest` | Input for matcher (question, optional sql, dialect) |
| `TrustedSQLMatchResult` | Match outcome with `trusted_asset_id` property alias |

### Design notes

- Models are **frozen** Pydantic v2 (same as other domain models).
- **No** industry-specific fields — education examples live only in YAML (step 11.8).
- `TrustedSQLMatchResult.no_match()` defaults to `GenerationSource.LLM` for downstream fallthrough.
- Ports (`ISemanticCatalogLoader`, `ITrustedSQLMatcher`) come in step **11.3–11.4**.

### Verify

```bash
.venv/bin/python -m pytest tests/unit/test_semantic_models.py -q
```

---

## Step 11.2 — Config layout (complete)

```text
config/
  README.md                           # index of instance config dirs
  semantic/
    README.md                           # authoring guide + YAML schema
    trusted_metrics.yaml                # metrics: [] (templates in comments)
    example_queries.yaml                # example_queries: [] (templates in comments)
    examples/education/                   # starter pack (step 11.8) — copy-only
```

- Active runtime files are **`trusted_metrics.yaml`** and **`example_queries.yaml`** at the semantic root.
- **`examples/<vertical>/`** is copy-only; education pack is under **`examples/education/`** (step 11.8).

Env (step 11.3): `INSIGHTAI_SEMANTIC_ENABLED` (default `false`), `INSIGHTAI_SEMANTIC_PATH` (default `config/semantic`). Wiring into chat/SQL is step **11.5**.

## Step 11.3 — YAML loader (complete)

| Piece | Location |
|-------|----------|
| Port | `domain/ports/semantic_catalog_loader.py` — `ISemanticCatalogLoader` |
| Loader | `infrastructure/semantic/yaml_loader.py` — `YamlSemanticCatalogLoader` |
| Settings | `semantic_enabled`, `semantic_path`, `resolved_semantic_path()` |
| Exception | `SemanticConfigError` |
| Dependency | `PyYAML>=6.0.2` in `pyproject.toml` |

```python
from insightai.infrastructure.config.settings import get_settings
from insightai.infrastructure.semantic import YamlSemanticCatalogLoader

settings = get_settings()
loader = YamlSemanticCatalogLoader(settings.resolved_semantic_path())
catalog = loader.load()
```

### Verify

```bash
uv pip install -e ".[dev]"   # or pip install PyYAML
.venv/bin/python -m pytest tests/unit/test_semantic_yaml_loader.py -q
```

---

## Document history

| Date | Change |
|------|--------|
| 2026-05-21 | Step 11.1 complete — domain models + unit tests |
| 2026-05-21 | Step 11.2 complete — `config/semantic/` layout + README + empty YAML templates |
| 2026-05-21 | Step 11.3 complete — YAML loader, settings, `tests/fixtures/semantic/` |
| 2026-05-21 | Step 11.4 complete — SQL normalizer, `TrustedSQLMatcher`, `MatchTrustedSQLUseCase` |
| 2026-05-21 | Step 11.5 complete — `GenerateSQLUseCase` + `app.state.semantic` + API fields |
| 2026-05-21 | Step 11.6 complete — chat/ask `mode` dry_run, `use_llm`, response trust fields |
| 2026-05-22 | Steps 11.8–11.9 complete — education starter pack, semantic CLIs, tests |

## Step 11.8 — Education starter pack (complete)

| File | Purpose |
|------|---------|
| `config/semantic/examples/education/trusted_metrics.yaml` | `active_student_count`, campus A LIKE filter, top-5 classrooms |
| `config/semantic/examples/education/example_queries.yaml` | Classroom headcount, campus count, last incident (+ image UNION) |
| `config/semantic/examples/education/README.md` | Copy workflow, CLI examples, links to `Knowledge/` |

Not auto-loaded — merge into active `config/semantic/*.yaml` or point `INSIGHTAI_SEMANTIC_PATH` at a copied tree.

### Verify

```bash
insightai-semantic-validate --path config/semantic/examples/education
```

## Step 11.9 — CLI + tests (complete)

| CLI | Entry point | Purpose |
|-----|-------------|---------|
| `insightai-semantic-validate` | `insightai.cli.semantic:main_validate` | Load YAML, validate schema + SQL parse (exit 0/1) |
| `insightai-semantic-test-match` | `insightai.cli.semantic:main_test_match` | Match a `--question` (exit 0 match, 2 no match) |

Implementation: `src/insightai/cli/semantic.py`. Tests: `tests/unit/test_semantic_cli.py` (fixture + education pack).

### Verify

```bash
pip install -e .
insightai-semantic-validate --path config/semantic/examples/education
insightai-semantic-test-match \
  --path config/semantic/examples/education \
  --question "How many kids are in the Example classroom?"
.venv/bin/python -m pytest tests/unit/test_semantic_*.py tests/unit/test_generate_sql_trusted.py tests/unit/test_ask_dry_run.py tests/unit/test_semantic_cli.py -q
```

## Step 11.5 — Pipeline wiring (complete)

| Piece | Location |
|-------|----------|
| Bootstrap | `infrastructure/semantic/bootstrap.py` → `app.state.semantic` in `main.py` |
| Orchestration | `GenerateSQLUseCase` — question match + `use_llm=false` skips LLM; post-LLM SQL verify |
| SQL result fields | `SQLGenerationResult.generation_source`, `trusted_asset_id`, `trusted_match_confidence` |
| API | `POST /api/v1/sql/generate` — `use_llm`, response `generation_source`, `trusted_asset_id` |
| Deps | `get_generate_sql_use_case` passes matcher when `INSIGHTAI_SEMANTIC_ENABLED=true` |

**Enable**

```bash
INSIGHTAI_SEMANTIC_ENABLED=true
INSIGHTAI_SEMANTIC_PATH=config/semantic
# Copy or author metrics/examples in trusted_metrics.yaml / example_queries.yaml
```

### Verify

```bash
.venv/bin/python -m pytest tests/unit/test_generate_sql_trusted.py -q
```

## Step 11.6 — Chat `mode` + `use_llm` (complete)

| API | New fields |
|-----|------------|
| `POST /api/v1/chat`, `/chat/stream` | `mode`: `execute` \| `dry_run`, `use_llm` (default `true`) |
| `POST /api/v1/ask` | Same domain fields on `AskRequest` |
| Responses | `mode`, `dry_run`, `generation_source`, `trusted_asset_id`, `trusted_match_confidence` |

**`dry_run`:** SQL is generated (or trusted-matched), validated by Phase 4 composite validator, **not** executed. Answer is generated with **zero rows** and `dry_run: true`. Stream phase: `validating_sql` instead of `executing_query`.

### Verify

```bash
.venv/bin/python -m pytest tests/unit/test_ask_dry_run.py tests/unit/test_ask_use_case.py -q
```

## Step 11.4 — Matcher (complete)

| Piece | Location |
|-------|----------|
| Port | `domain/ports/trusted_sql_matcher.py` — `ITrustedSQLMatcher` |
| Normalizer | `infrastructure/semantic/sql_normalizer.py` — reuses Phase 4 `parse_sql` / `canonicalize_sql` |
| Matcher | `infrastructure/semantic/trusted_matcher.py` — `TrustedSQLMatcher` |
| Use case | `application/use_cases/match_trusted_sql.py` — respects `semantic_enabled` |

**Match order**

1. If `sql` provided: exact string → sqlglot-canonical compare (examples, then metrics)
2. Else: normalized question vs `example_queries` phrases / metric `question_hints`

**Confidence:** `exact_sql`, `normalized_sql`, `question_match`, or `none` (LLM fallthrough).

### Verify

```bash
.venv/bin/python -m pytest tests/unit/test_semantic_trusted_matcher.py tests/unit/test_match_trusted_sql_use_case.py -q
```
