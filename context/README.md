# Deployment context (optional)

InsightAI ships one **schema-driven** context builder in
`src/insightai/infrastructure/schema/context_builder.py`. It works for any database
described by your schema files (Budget, education, ERP, etc.) — you only replace:

- `schema/schema.json` and/or `schema/database_schema.md`
- `Knowledge/` for business rules

You do **not** need a separate context builder per customer.

## Optional extended plugin

Some deployments need extra table boosts, exclusions, or SQL notes beyond what the
schema export provides. Put that code here (not in `src/`), and enable it with:

```bash
INSIGHTAI_SCHEMA_CONTEXT_PLUGIN=context.plugins.schema_context_extended:ExtendedSchemaContextBuilder
```

See `context/plugins/README.md`. Plugin modules under `context/plugins/` are
**gitignored** except `*.example` files — keep customer-specific logic private.

## Layout

```
context/
  README.md           ← this file (committed)
  plugins/
    README.md
    *.example         ← committed templates
    *.py              ← local only (gitignored)
```
