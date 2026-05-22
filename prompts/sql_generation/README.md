# SQL generation prompts (Phase 3)

File-based templates loaded by `insightai.infrastructure.prompts.loader` — not embedded in Python.

| File | Role |
|------|------|
| `system.md` | **Generic** system instructions: SELECT-only, dialect rules, JSON output shape |
| `user.md` | Per-request template with schema context, optional knowledge, and question |

## Design

- **No deployment-specific table or column names** in `system.md`. Those come from `schema/database_schema.md` (per install) and from **`Knowledge/`** (domain rules, synced via RAG).
- When `INSIGHTAI_RAG_ENABLED=true` and `INSIGHTAI_SQL_KNOWLEDGE_CONTEXT_ENABLED=true`, SQL generation retrieves top-k Knowledge chunks and adds a **Domain guidance** section to the user prompt.

## Placeholders (`user.md` and `system.md`)

| Placeholder | Source |
|-------------|--------|
| `{question}` | User natural language question |
| `{schema_context}` | `SchemaContextResult.context_markdown` (Phase 2) |
| `{domain_context_section}` | Retrieved Knowledge excerpts (empty when disabled) |
| `{sql_dialect}` | Human-readable dialect label from `DatabaseKind` |
| `{max_rows}` | `Settings.sql_max_rows` |

`system.md` also uses `{sql_dialect}` and `{max_rows}` so limits stay consistent in both messages.

## Output contract

The model must return JSON with: `sql`, `explanation`, `confidence`, `uncertainty_notes`, `tables_used`.

Post-processing (Phase 3.4) will extract and validate SQL before execution.
