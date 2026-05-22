# Instance configuration (`config/`)

Per-deployment YAML and policy files for **this** InsightAI instance (one customer / one business).

| Directory | Phase | Purpose |
|-----------|-------|---------|
| [`semantic/`](semantic/README.md) | 11 | Trusted metrics & example queries |
| [`governance/`](governance/README.md) | 12 (in progress) | Scope dimensions, row filters, column masks |
| `semantic_spaces/` | 19 (planned) | Domain-scoped table allowlists |

Secrets and connection strings stay in **environment variables** (`.env`), not in this tree.

See [FUTURE_PHASES.md](../FUTURE_PHASES.md) for the full platform roadmap.
