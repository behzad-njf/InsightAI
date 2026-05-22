# Education vertical — governance starter pack

> **Example only** — not loaded automatically. Copy into [`../../policies.yaml`](../../policies.yaml) or merge sections.  
> **Operator guide:** [docs/GOVERNANCE.md](../../../docs/GOVERNANCE.md)

## Contents

| File | Purpose |
|------|---------|
| [`policies.yaml`](policies.yaml) | Campus scope + analyst masks + admin bypass |

## What this pack models

| Piece | Example value |
|-------|----------------|
| Scope dimension | `campus` |
| SQL filter | `school_school.id IN (principal.campus_ids)` |
| Analyst attributes | `campus_ids: ["1", "2"]` (placeholder campus ids) |
| Masked columns | `email`, `phone` excluded for `analyst` |
| Admin role | No scope, no masks |

## Quick start

```bash
# Validate the example pack (parse + schema)
insightai-governance-validate --path config/governance/examples/education

# Copy to active config, then validate again
cp config/governance/examples/education/policies.yaml config/governance/policies.yaml
insightai-governance-validate --path config/governance

# Issue a scoped key (requires app DB + governance enabled in .env)
insightai-keys create --label "Campus A analyst" --roles analyst \
  --attributes campus_ids=1,2
```

## Copy workflow

1. Copy `policies.yaml` to `config/governance/policies.yaml` (or merge `scope_dimensions` / `roles`).
2. Replace placeholder campus ids with real `school_school.id` values from your database.
3. Run `insightai-governance-validate`.
4. Set `enabled: true`, `INSIGHTAI_GOVERNANCE_ENABLED=true`, restart API.
5. Test with `POST /api/v1/ask` and `mode: dry_run` to inspect governed SQL.

## Alignment with semantic layer

If you use the education semantic pack ([`config/semantic/examples/education/`](../../semantic/examples/education/README.md)), keep table/column names consistent between trusted SQL and governance bindings (`school_school`, `school_classroom`, etc.).
