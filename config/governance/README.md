# Governance policies (Phase 12)

> **Status:** Models (12.1) ✅, enforcer (12.2) ✅, validator CLI (12.3) ✅ — run `insightai-governance-validate` before enabling in production.  
> **Implementation log:** [docs/PHASE_12_GOVERNANCE.md](../../docs/PHASE_12_GOVERNANCE.md)

Per-deployment **row scope**, **table access**, and **column masks** — no hardcoded business concepts in Python. You define scope dimension names (e.g. `campus`, `store`, `region`) in [`policies.yaml`](policies.yaml).

**Operator guide:** [docs/GOVERNANCE.md](../../docs/GOVERNANCE.md) — how to author policies for any vertical.

## Files

| File | Purpose |
|------|---------|
| [`policies.yaml`](policies.yaml) | Active policy (`enabled: false` until you turn it on) |
| [`examples/education/`](examples/education/) | Copy-only education starter — see [examples/education/README.md](examples/education/README.md) |

## Principal attribute contract (Phase 12.5)

API keys (Phase 16) carry scope via CLI. Attribute **names** must match `sql_bindings[].attribute` in this file (e.g. `campus_ids`).

| Role in YAML | Attributes required (when `missing_attribute_action: deny`) |
|--------------|---------------------------------------------------------------|
| `analyst` | `campus_ids` (example education pack) |
| `admin` | none |

```bash
# JSON
insightai-keys create --label "Campus A analyst" --roles analyst \
  --attributes '{"campus_ids":["1","2"]}'

# Key=value pairs
insightai-keys create --label "Campus B analyst" --roles analyst \
  --attributes campus_ids=1,2
```

With `INSIGHTAI_GOVERNANCE_ENABLED=true`, `insightai-keys create` validates attributes against this policy.

JWT callers may send the same shape in claims: `roles`, `attributes` (see [docs/PHASE_12_GOVERNANCE.md](../../docs/PHASE_12_GOVERNANCE.md) § 12.5).

## Validate locally

```bash
insightai-governance-validate --path config/governance
```

## Related

- [FUTURE_PHASES.md](../../FUTURE_PHASES.md) — Phase 12 acceptance criteria
- [docs/PHASE_16_APP_DB_AUTH.md](../../docs/PHASE_16_APP_DB_AUTH.md) — API keys and roles
- [SECURITY.md](../../SECURITY.md) — production governance security checklist
