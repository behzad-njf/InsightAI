# Schema directory

InsightAI loads table/column/FK metadata for NL→SQL from files produced by
[django-db-schema-doc](https://pypi.org/project/django-db-schema-doc/).

## Export from your Django project

```bash
python manage.py generate_database_doc -o DATABASE.md --project-name "Your product"
python manage.py export_schema_json -o schema.json
python manage.py export_schema_examples -o schema_examples.json   # optional
```

## Default files in this repo (CI / local dev)

The repository ships a **small anonymized demo schema** so tests and `uvicorn` work without a customer export:

- `schema/schema.json`
- `schema/database_schema.md`

Replace these with your django-db-schema-doc exports for a real deployment.

## Copy into InsightAI

| django-db-schema-doc output | InsightAI path (default) |
|----------------------------|---------------------------|
| `DATABASE.md` | `schema/database_schema.md` |
| `schema.json` | `schema/schema.json` |
| `schema_examples.json` | `schema/schema_examples.json` |

## Configuration (`.env`)

```bash
# auto = use schema.json when the file exists, else DATABASE.md
INSIGHTAI_SCHEMA_SOURCE=auto
INSIGHTAI_SCHEMA_MARKDOWN_PATH=schema/database_schema.md
INSIGHTAI_SCHEMA_JSON_PATH=schema/schema.json
INSIGHTAI_SCHEMA_EXAMPLES_JSON_PATH=schema/schema_examples.json
```

Re-run exports after migrations. Restart the API (or clear the schema cache in tests) so
the registry reloads.

## Context builder

The built-in builder is **schema-driven** (table names, domains, columns, FKs, query examples).
Swap schema files per deployment (Budget, education, etc.) — no per-customer Python required.

Optional extended heuristics: `context/plugins/` + `INSIGHTAI_SCHEMA_CONTEXT_PLUGIN` (see `context/README.md`).

Put product-specific SQL rules in `Knowledge/`, not in plugins, when possible.

## Legacy markdown

Older InsightAI deployments may still use a hand-maintained `database_schema.md` (MSSQL-style
sections `## 2. Domain overview`, `### 2.3 Common join patterns`). The parser auto-detects
legacy vs django-db-schema-doc layout.

## Tests

Anonymized mini fixtures live under `tests/fixtures/schema/` (`django_doc_mini.json` / `.md`).
