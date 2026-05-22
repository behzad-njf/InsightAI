# Governance operator guide

> **Audience:** Platform operators and customer admins who deploy InsightAI per tenant.  
> **Implementation log:** [PHASE_12_GOVERNANCE.md](PHASE_12_GOVERNANCE.md)  
> **Config directory:** [`config/governance/`](../config/governance/)

InsightAI governance enforces **who can see what** on every read-only SQL query: row scope, table access, and column masks. Rules live in YAML — not in Python. Dimension names like `campus` or `store` are **your** vocabulary; the engine only understands generic bindings.

---

## What governance does

| Control | YAML mechanism | Runtime effect |
|---------|----------------|----------------|
| **Row scope** | `scope_dimensions` + `sql_bindings` | Injects `AND table.column IN (...)` from API key attributes |
| **Table access** | `roles.*.allowed_tables` / `denied_table_patterns` | Denies SELECTs that reference forbidden tables |
| **Column masks** | `roles.*.column_masks` | Removes or replaces columns in the SELECT list |
| **Missing scope** | `missing_attribute_action` | Deny request or apply empty-safe filter (`FALSE`) |

Governance runs **after** SQL generation and **before** the database executes the query. The readonly validator runs on SQL **before and after** governance rewrites it.

---

## Concepts (any vertical)

| Concept | You define | Education example | Retail example |
|---------|------------|-------------------|----------------|
| **Scope dimension** | Named axis in YAML | `campus` | `store` |
| **SQL binding** | Table + column + attribute key | `school_school.id` ← `campus_ids` | `dim_store.store_id` ← `store_ids` |
| **Role** | Named policy bundle | `analyst`, `admin` | `store_manager`, `regional_manager` |
| **Principal attribute** | Values on API key / JWT | `campus_ids: ["1","2"]` | `store_ids: ["101"]` |

The platform never hardcodes `campus` or `store` in code — only in your `policies.yaml`.

---

## Files and settings

| Path | Purpose |
|------|---------|
| [`config/governance/policies.yaml`](../config/governance/policies.yaml) | Active policy for this deployment |
| [`config/governance/examples/education/`](../config/governance/examples/education/) | Copy-only education starter (not loaded automatically) |

| Environment variable | Default | Meaning |
|---------------------|---------|---------|
| `INSIGHTAI_GOVERNANCE_ENABLED` | `false` | Wire SQL enforcer at API startup |
| `INSIGHTAI_GOVERNANCE_PATH` | `config/governance` | Directory containing `policies.yaml` |

Both `INSIGHTAI_GOVERNANCE_ENABLED=true` **and** `enabled: true` in `policies.yaml` are required for rules to apply.

---

## Authoring workflow

### 1. Map your data model

For each scope axis (campus, region, brand, etc.):

1. Pick a **dimension id** (lowercase, stable): e.g. `campus`.
2. Identify the **filter column** analysts should be limited to: e.g. `school_school.id`.
3. Choose an **attribute name** for API keys: e.g. `campus_ids` (list of allowed ids).

Use the **bare table name** as it appears in generated SQL (`school_school`, not `dbo.school_school`). Glob patterns are supported for table allow/deny (`school_*`, `*`).

### 2. Edit `policies.yaml`

Start from the template or copy [`examples/education/policies.yaml`](../config/governance/examples/education/policies.yaml).

```yaml
enabled: true

scope_dimensions:
  campus:
    description: "School-site scope (your label)"
    sql_bindings:
      - table: school_school
        column: id
        operator: in_principal_attribute
        attribute: campus_ids

roles:
  analyst:
    allowed_tables: ["*"]
    apply_scope_dimensions: [campus]   # or shorthand: apply_scope: [campus]
    column_masks:
      - column: email
        strategy: exclude
      - column: phone
        strategy: exclude
    missing_attribute_action: deny
  admin:
    allowed_tables: ["*"]
    apply_scope_dimensions: []
    column_masks: []

default_missing_attribute_action: deny
```

**Aliases supported:** `apply_scope` = `apply_scope_dimensions`; `column_masks: [email, phone]` = exclude shorthand.

### 3. Validate

```bash
insightai-governance-validate --path config/governance
```

Fix all reported errors before enabling in production.

### 4. Issue API keys with matching roles and attributes

Requires Phase 16 app DB and `INSIGHTAI_API_AUTH_MODE=api_key`. See [PHASE_16_APP_DB_AUTH.md](PHASE_16_APP_DB_AUTH.md).

```bash
insightai-app-db upgrade

# Scoped analyst — attribute names must match sql_bindings[].attribute
insightai-keys create --label "Campus A analyst" --roles analyst \
  --attributes campus_ids=1,2

# Admin — no scope attributes when apply_scope_dimensions is empty
insightai-keys create --label "Platform admin" --roles admin
```

When `INSIGHTAI_GOVERNANCE_ENABLED=true`, `insightai-keys create` **rejects** keys that omit required attributes for their roles.

### 5. Enable and restart

```bash
# .env
INSIGHTAI_GOVERNANCE_ENABLED=true
INSIGHTAI_GOVERNANCE_PATH=config/governance
```

Set `enabled: true` in `policies.yaml`, restart the API, and test with `mode: dry_run` on `/api/v1/ask` or `/api/v1/chat` to inspect governed SQL without returning rows.

---

## YAML reference

### Top level

| Key | Required | Description |
|-----|----------|-------------|
| `enabled` | No (default `true` in loader) | Master switch inside the catalog |
| `scope_dimensions` | No | Map of dimension id → bindings |
| `roles` | Yes when enabled | Map of role name → policy |
| `default_missing_attribute_action` | No | `deny` (default) or `empty_safe` |

### `scope_dimensions.<id>`

| Key | Required | Description |
|-----|----------|-------------|
| `description` | No | Operator notes |
| `sql_bindings` | Yes (non-empty if dimension is used) | List of bindings |

### `sql_bindings[]`

| Key | Required | Description |
|-----|----------|-------------|
| `table` | Yes | Bare table name referenced in SELECT |
| `column` | Yes | Column to filter |
| `operator` | No | Only `in_principal_attribute` today |
| `attribute` | Yes | Key on principal / API key (e.g. `campus_ids`) |

### `roles.<name>`

| Key | Required | Description |
|-----|----------|-------------|
| `allowed_tables` | No (default `["*"]`) | Glob allow list |
| `denied_table_patterns` | No | Glob deny list (evaluated first) |
| `apply_scope_dimensions` | No | Dimension ids to enforce |
| `column_masks` | No | List of mask rules or column name strings |
| `missing_attribute_action` | No | Per-role override for missing attributes |

### `column_masks[]`

| Key | Required | Description |
|-----|----------|-------------|
| `column` | Yes | Column name or alias in SELECT |
| `strategy` | No | `exclude` (default), `null_literal`, `hash` |

### Mask strategies

| Strategy | Result in SELECT |
|----------|------------------|
| `exclude` | Column dropped from output |
| `null_literal` | Replaced with `NULL` |
| `hash` | Replaced with literal `***` |

---

## Principal attribute contract

| Source | Roles | Attributes |
|--------|-------|------------|
| **DB API key** | `--roles analyst,admin` | `--attributes campus_ids=1,2` or JSON |
| **JWT** | Claim `roles` (string or array) | Claim `attributes` (object of string → string or array) |
| **Env API key** | Not supported | Not supported — use DB keys for governance |
| **Auth disabled** | N/A | Governance context is empty; rules do not apply |

Attribute **names** must match `sql_bindings[].attribute` exactly. Values are string lists (campus id `1` and `2`, not integers in YAML).

---

## Request pipeline (order)

1. Authenticate → build `GovernanceContext` (roles + attributes).
2. Generate SQL (LLM or trusted semantic).
3. **Validate** generated SQL (Phase 4).
4. **Governance** rewrite or deny (Phase 12).
5. **Validate** governed SQL again (Phase 4).
6. Execute readonly query (Phase 5).

Streaming clients may see SSE phase `applying_governance` between `generating_sql` and `validating_sql`.

### Denials

- HTTP **403**, error code `GOVERNANCE_DENIED`.
- Safe message only (no governed SQL in the response).
- Audit: `governance_denied=true` on failure events; `governance_applied` / `governance_dimensions_applied` on success.

---

## Vertical examples

### Education (campus scope)

Copy pack: [`config/governance/examples/education/`](../config/governance/examples/education/).

- Dimension `campus` → `school_school.id` filtered by `campus_ids`.
- Role `analyst`: scope + mask `email`, `phone`.
- Role `admin`: full access (no scope dimensions).

Placeholder ids (`1`, `2`) and labels (`Campus A`) are samples only — replace with your warehouse values.

### Retail (store scope) — sketch

```yaml
scope_dimensions:
  store:
    description: "Store-level access"
    sql_bindings:
      - table: fact_sales
        column: store_id
        operator: in_principal_attribute
        attribute: store_ids

roles:
  store_manager:
    allowed_tables: ["fact_*", "dim_store"]
    apply_scope: [store]
    column_masks: [customer_email]
  regional_manager:
    allowed_tables: ["*"]
    apply_scope: [store]
    column_masks: []
```

Issue keys: `insightai-keys create --roles store_manager --attributes store_ids=101,102`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Governance never applies | `INSIGHTAI_GOVERNANCE_ENABLED=false` or `enabled: false` in YAML | Enable both |
| 403 “Missing required scope attributes” | API key missing attribute for role | Add `--attributes` or use `admin` role |
| 403 “table not permitted” | Table not in `allowed_tables` or matches `denied_*` | Adjust role `allowed_tables` / deny patterns |
| Scope filter missing in SQL | Table in query does not match binding `table` name | Align binding `table` with SQL aliases/names |
| `insightai-keys create` fails validation | Role requires attributes per policy | Pass attributes or change role |
| Env API key bypasses scope | Env keys have no roles/attributes | Use DB-backed keys |

### Debug with dry run

```bash
curl -s -X POST http://localhost:8000/api/v1/ask \
  -H "X-API-Key: iai_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "How many schools?", "mode": "dry_run"}' | jq '.sql'
```

Inspect the returned SQL for injected `WHERE` clauses and masked columns.

---

## Related documentation

| Doc | Topic |
|-----|--------|
| [PHASE_12_GOVERNANCE.md](PHASE_12_GOVERNANCE.md) | Implementation steps 12.1–12.7 |
| [PHASE_16_APP_DB_AUTH.md](PHASE_16_APP_DB_AUTH.md) | API keys, app DB, admin routes |
| [config/governance/README.md](../config/governance/README.md) | Config directory quick reference |
| [FUTURE_PHASES.md](../FUTURE_PHASES.md) | Roadmap and acceptance criteria |
| [SECURITY.md](../SECURITY.md) | Production security + governance review checklist |
