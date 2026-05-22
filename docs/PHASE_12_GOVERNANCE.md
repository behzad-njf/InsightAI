# Phase 12 — Governance & data policy (implementation log)

> **Roadmap:** [FUTURE_PHASES.md](../FUTURE_PHASES.md) § Phase 12  
> **Status:** ✅ Complete (steps **12.1–12.7**)  
> **Depends on:** Phase 16 (API keys → principal attributes) ✅

---

## Goal

Enforce **who can see what** at the SQL layer: scope filters, table policies, column masks — all from **YAML**, not hardcoded domain names in code.

---

## Step checklist

| Step | Task | Status |
|------|------|--------|
| **12.1** | Domain models | ✅ Done |
| **12.2** | `IGovernanceEnforcer` + sqlglot transforms | ✅ Done |
| **12.3** | YAML loader + schema validation for `config/governance/policies.yaml` | ✅ Done |
| **12.4** | Hook after Phase 4 validation, before execute | ✅ Done |
| **12.5** | Principal wiring (mostly done in Phase 16) | ✅ Done |
| **12.6** | `docs/GOVERNANCE.md` operator guide | ✅ Done |
| **12.7** | [SECURITY.md](../SECURITY.md) checklist | ✅ Done |

---

## Step 12.1 — Domain models (complete)

### Types (`insightai.domain.models.governance`)

| Type | Purpose |
|------|---------|
| `Principal` | Caller identity (`roles`, `attributes`) — same as Phase 16 `GovernanceContext` |
| `GovernanceContext` | Type alias for `Principal` (pipeline compatibility) |
| `ScopeDimension` | Customer-defined scope axis + `SqlScopeBinding` list |
| `SqlScopeBinding` | table/column → principal attribute (`in_principal_attribute`) |
| `RowFilterRule` | Resolved filter at enforcement time |
| `MaskRule` | Column mask + `ColumnMaskStrategy` (`exclude`, `null_literal`, `hash`) |
| `TablePolicy` | Allowed/denied table patterns per role |
| `RolePolicy` | Role → scopes, masks, missing-attribute behavior |
| `GovernancePolicyCatalog` | Loaded policy bundle for one instance |
| `PolicyDecision` | `allow` / `deny` with dimensions and masks applied |
| `GovernanceDecision` | Enforcer wrapper for ask pipeline (Phase 16 port) |

### Config template

- [`config/governance/policies.yaml`](../config/governance/policies.yaml) — example `campus` dimension (education sample only)
- [`config/governance/README.md`](../config/governance/README.md)

---

## Step 12.2 — SQL enforcer (complete)

### Components

| Module | Role |
|--------|------|
| `SqlGovernanceEnforcer` | `evaluate()` / `enforce()` — deny raises `GovernanceDeniedError` |
| `YamlGovernancePolicyLoader` | Load `policies.yaml` → `GovernancePolicyCatalog` |
| `policy_resolver` | Merge role policies; resolve `RowFilterRule` from principal attributes |
| `sql_transform` | sqlglot: table allow/deny, `WHERE` injection, SELECT-list masks |
| `table_match` | Glob table patterns (`*`, `school_*`) |
| `build_governance_components` | No-op when `INSIGHTAI_GOVERNANCE_ENABLED=false`; else SQL enforcer |

### Settings

| Variable | Default | Meaning |
|----------|---------|---------|
| `INSIGHTAI_GOVERNANCE_ENABLED` | `false` | Wire `SqlGovernanceEnforcer` at startup |
| `INSIGHTAI_GOVERNANCE_PATH` | `config/governance` | Directory containing `policies.yaml` |

Also set `enabled: true` in `policies.yaml` when you want the catalog to apply rules (both flags are required).

### Production usage

1. Copy/adapt [`config/governance/policies.yaml`](../config/governance/policies.yaml) for your vertical.
2. Create API keys with matching roles and scope attributes:

```bash
insightai-keys create \
  --label "Campus A analyst" \
  --roles analyst \
  --attributes campus_ids=1,2
```

3. Enable in `.env`:

```bash
INSIGHTAI_GOVERNANCE_ENABLED=true
INSIGHTAI_GOVERNANCE_PATH=config/governance
```

4. Set `enabled: true` in `policies.yaml`.
5. Restart the API. Generated SELECTs pass the governed SQL hook (validate → govern → validate) before execution.
6. Denied requests return **403** with `GOVERNANCE_DENIED` (`GovernanceDeniedError` handler).

### Behavior summary

- **Scope:** `in_principal_attribute` → `AND table.column IN (...)` on matching FROM aliases; missing attribute → deny (or `empty_safe` → `FALSE` filter).
- **Masks:** `exclude` drops column from SELECT; `null_literal` / `hash` replace projection.
- **Tables:** Deny patterns win; then allowed patterns (default `*`).
- **SELECT only:** Non-SELECT SQL is rejected at governance (defense in depth with Phase 4).

### Verify

```bash
.venv/bin/python -m pytest \
  tests/unit/test_governance_policy_models.py \
  tests/unit/test_governance_context.py \
  tests/unit/test_governance_enforcer.py \
  tests/unit/test_governance_yaml_loader.py \
  -q
```

---

## Step 12.3 — Schema validation (complete)

### Validator (`infrastructure/governance/validator.py`)

| Check | Example failure |
|-------|-----------------|
| Required `policies.yaml` | Missing file in governance dir |
| Top-level / nested unknown keys | `roles.analyst.foo` |
| Scope bindings | Missing `table`, `column`, or `attribute` |
| Role scope references | `apply_scope_dimensions: [unknown]` |
| Enum values | Invalid `missing_attribute_action`, mask `strategy` |
| Enabled catalog | `enabled: true` with empty `roles` |
| Duplicate masks | Same column masked twice on one role |

YAML aliases supported in loader + validator:

- `apply_scope` → same as `apply_scope_dimensions`
- `column_masks: [email, phone]` → shorthand for `exclude` masks

### CLI

```bash
insightai-governance-validate
insightai-governance-validate --path config/governance
```

Exit **0** when valid; **1** with error lines on stderr.

Startup: when `INSIGHTAI_GOVERNANCE_ENABLED=true`, `build_governance_components` runs the same validation and raises `ConfigurationError` if the policy is invalid.

### Verify

```bash
.venv/bin/python -m pytest \
  tests/unit/test_governance_validator.py \
  tests/unit/test_governance_cli.py \
  -q
insightai-governance-validate --path config/governance
```

---

## Step 12.4 — Pipeline hook (complete)

### Order in `AskUseCase`

| Step | Phase | Module |
|------|-------|--------|
| 1 | SQL generation | `GenerateSQLUseCase` (LLM output post-processed in Phase 4) |
| 2 | Pre-governance validate | `prepare_governed_sql` → `validate_readonly_sql` |
| 3 | Governance enforce | `IGovernanceEnforcer.enforce` |
| 4 | Post-governance validate | `prepare_governed_sql` → `validate_readonly_sql` |
| 5 | Execute | `RunQueryUseCase` (validates again, then readonly executor) |

Implementation: [`application/pipeline/governed_sql.py`](../src/insightai/application/pipeline/governed_sql.py)

### Streaming (SSE)

After `generating_sql`, clients may see:

- `applying_governance` — scope filters / masks applied
- `validating_sql` — post-governance safety check (dry_run ends here)
- `executing_query` — database round-trip (execute mode only)

### Audit

Successful asks log `governance_applied` and `governance_dimensions_applied` on `AskAuditComplete`. Failures from policy denial set `governance_denied=true` on `AskAuditFailure` with `error_code=GOVERNANCE_DENIED`.

### Verify

```bash
.venv/bin/python -m pytest tests/unit/test_governed_sql_pipeline.py tests/unit/test_ask_governance.py tests/unit/test_ask_dry_run.py -q
```

---

## Step 12.5 — Principal wiring & attribute contract (complete)

### Request flow

```
HTTP auth (require_api_auth)
  → AuthenticatedPrincipal (roles, attributes from API key or JWT claims)
  → GovernanceContext on request.state.governance_context
  → AskRequest / ChatRequest.to_domain(governance_context=...)
  → prepare_governed_sql → IGovernanceEnforcer.enforce(context)
```

| Auth source | Roles / attributes |
|-------------|-------------------|
| **App DB API key** | From `insightai-keys create --roles … --attributes …` |
| **JWT** | Optional claims `roles`, `attributes` (same shape as YAML bindings) |
| **Env API key** | No roles/attributes (governance passes through unless roles added later) |
| **Auth disabled** | `governance_context` is `None` (no scope enforcement) |

### Attribute contract

YAML `sql_bindings[].attribute` must match keys on the API key (or JWT `attributes` object).

| Policy role | Example attribute | Purpose |
|-------------|-------------------|---------|
| `analyst` | `campus_ids` | Filters `school_school.id IN (...)` when `campus` dimension is applied |

Helpers: [`attribute_contract.py`](../src/insightai/infrastructure/governance/attribute_contract.py)

- `required_attributes_for_roles(catalog)` — derive required attribute names per role
- `validate_key_attributes_for_catalog(...)` — used by `insightai-keys create` when governance is enabled

### Create keys (CLI)

```bash
# JSON
insightai-keys create --label "Campus A" --roles analyst \
  --attributes '{"campus_ids":["1","2"]}'

# Key=value (Phase 12.5)
insightai-keys create --label "Campus B" --roles analyst \
  --attributes campus_ids=1,2
```

When `INSIGHTAI_GOVERNANCE_ENABLED=true`, `create` fails fast if a role requires scope attributes that are missing.

### JWT example claims

```json
{
  "sub": "service-account-1",
  "roles": ["analyst"],
  "attributes": { "campus_ids": ["1", "2"] }
}
```

### Verify

```bash
.venv/bin/python -m pytest \
  tests/unit/test_governance_context.py \
  tests/unit/test_principal_attribute_contract.py \
  tests/integration/test_governance_principal_api.py \
  -q
```

---

## Step 12.6 — Operator guide (complete)

- **[docs/GOVERNANCE.md](GOVERNANCE.md)** — vertical-agnostic runbook: concepts, YAML reference, API keys, pipeline order, troubleshooting
- **[config/governance/examples/education/](../config/governance/examples/education/)** — copy-only education `policies.yaml` + README

### Verify

```bash
insightai-governance-validate --path config/governance/examples/education
```

---

## Step 12.7 — Security checklist (complete)

Production governance review checklist added to [SECURITY.md](../SECURITY.md) § *Governance & data policy (Phase 12)*:

- Threat model table (scope, tables, masks, denials, SQL leak)
- Pre-production checklist (policy, API keys, runtime verification, operations)
- Anti-patterns and incident response hints

Cross-linked from [docs/GOVERNANCE.md](GOVERNANCE.md).

---

## Document history

| Date | Change |
|------|--------|
| 2026-05-22 | Step 12.1 — governance policy domain models + config template |
| 2026-05-19 | Step 12.2 — SqlGovernanceEnforcer, YAML loader, bootstrap + settings |
| 2026-05-19 | Step 12.3 — policy validator, `insightai-governance-validate`, bootstrap fail-fast |
| 2026-05-19 | Step 12.4 — `prepare_governed_sql` hook, SSE phase, audit fields |
| 2026-05-19 | Step 12.5 — principal attribute contract, JWT claims, keys CLI validation |
| 2026-05-19 | Step 12.6 — docs/GOVERNANCE.md operator guide + education example pack |
| 2026-05-19 | Step 12.7 — SECURITY.md governance checklist; Phase 12 complete |
