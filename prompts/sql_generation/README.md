# SQL generation prompts (Phase 3)

File-based templates loaded by `insightai.infrastructure.prompts.loader` — not embedded in Python.

| File | Role |
|------|------|
| `system.md` | System instructions: SELECT-only, dialect rules, JSON output shape |
| `user.md` | Per-request template with schema context and question |

## Placeholders (`user.md` and `system.md`)

| Placeholder | Source |
|-------------|--------|
| `{question}` | User natural language question |
| `{schema_context}` | `SchemaContextResult.context_markdown` (Phase 2) |
| `{sql_dialect}` | Human-readable dialect label from `DatabaseKind` |
| `{max_rows}` | `Settings.sql_max_rows` |

`system.md` also uses `{sql_dialect}` and `{max_rows}` so limits stay consistent in both messages.

## Output contract

The model must return JSON with: `sql`, `explanation`, `confidence`, `uncertainty_notes`, `tables_used`.

Post-processing (Phase 3.4) will extract and validate SQL before execution.
