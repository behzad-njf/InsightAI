# Schema context plugins (optional)

## Default (recommended)

Leave `INSIGHTAI_SCHEMA_CONTEXT_PLUGIN` unset. InsightAI uses the built-in
`SchemaContextBuilder`, which scores tables from your schema export only.

## When to use a plugin

- Extra boosts/exclusions that are awkward to express in Knowledge/
- Temporary tuning before schema/doc exports catch up

## How to add one

1. Copy `schema_context_plugin.py.example` to e.g. `schema_context_mydeployment.py`
2. Implement a class with `def __init__(self, registry: SchemaRegistry)` and
   `def build(self, request: SchemaContextRequest) -> SchemaContextResult`
3. Set in `.env`:

   ```bash
   INSIGHTAI_SCHEMA_CONTEXT_PLUGIN=context.plugins.schema_context_mydeployment:MyContextBuilder
   ```

4. Restart the API.

The repository may include a local `schema_context_extended.py` on your machine
(gitignored). Do not commit customer-specific plugins to the public InsightAI repo.
