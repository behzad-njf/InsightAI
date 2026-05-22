# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| `0.1.x` | Yes (best effort) |

Security fixes are applied on the default branch. There is no separate LTS release yet.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

1. Open a **private** security advisory on GitHub:  
   **Repository → Security → Advisories → Report a vulnerability**  
   (after you publish the repo), or
2. Contact the maintainer through a private channel listed in the repository profile.

Include:

- Description and impact
- Steps to reproduce
- Affected versions / commits
- Suggested fix (if any)

We aim to acknowledge reports within **7 days** and share a remediation plan when possible.

## Scope

In scope:

- InsightAI application code under `src/insightai/`
- Default API behavior (auth, rate limiting, SQL safety, read-only execution)
- Official Docker / Compose configuration in this repository

Out of scope:

- Misconfiguration of your own `.env`, database credentials, or network exposure
- Vulnerabilities in third-party dependencies (report upstream; we will bump versions)
- Issues in forked or modified deployments that removed safety controls

## Security model (summary)

InsightAI is designed as a **read-only analytics** layer:

- Generated SQL is validated (AST + policy) before execution.
- **Governance** (Phase 12) can rewrite SELECTs with scope filters and column masks from `config/governance/policies.yaml` before execution.
- Production should use a **read-only** database role with **SELECT** only.
- Product routes should use **API key or JWT** and **rate limiting** (`INSIGHTAI_ENV=production` enforces several checks).

Public endpoints by design (no auth on the default router):

- `GET /api/v1/health`
- `POST /api/v1/ai/complete` and `/api/v1/ai/complete/stream` (LLM smoke tests)

Do not expose an internet-facing instance with `INSIGHTAI_API_AUTH_MODE=none`.

## Secrets and publishing

**Never commit:**

- `.env` files with real API keys or database passwords
- `*.pem`, `*.key`, `credentials.json`, or production connection strings

This repository’s `.gitignore` excludes `.env`. Verify with `git status` before every push.

If a secret was committed, **rotate it immediately** and purge history (e.g. `git filter-repo` or GitHub secret scanning remediation)—treating the secret as compromised.

## Deployment checklist (operators)

Before exposing InsightAI to a network:

- [ ] `INSIGHTAI_ENV=production`
- [ ] `INSIGHTAI_DEBUG=false`
- [ ] `INSIGHTAI_API_AUTH_MODE=api_key` or `jwt` (not `none`)
- [ ] `INSIGHTAI_RATE_LIMIT_ENABLED=true`
- [ ] Read-only DB user; no `sa` / admin account
- [ ] TLS termination in front of the API (reverse proxy)
- [ ] Do not mount write-capable DB credentials
- [ ] Review `schema/database_schema.md` exposure if the repo is public (business metadata)
- [ ] If multi-tenant or scoped data: governance enabled — see [Governance checklist](#governance--data-policy-phase-12) below

## Governance & data policy (Phase 12)

When row-level scope or column-level PII controls matter, governance is **required** in production — not optional hardening. Full runbook: [docs/GOVERNANCE.md](docs/GOVERNANCE.md).

### Threat model (what governance addresses)

| Risk | Mitigation |
|------|------------|
| Analyst sees rows outside their campus / store / region | Scope dimensions + principal attributes → `WHERE` injection |
| Analyst queries payroll or raw PII tables | `denied_table_patterns` / tight `allowed_tables` per role |
| PII columns (`email`, `phone`) in result sets | `column_masks` on restricted roles |
| API key without scope attributes sees all rows | `missing_attribute_action: deny` (default) |
| Tampered SQL bypasses LLM guardrails | Phase 4 validator runs on SQL **before and after** governance |
| Leak of governed SQL in error responses | `GovernanceDeniedError` returns safe message only (403, no SQL body) |

Governance does **not** replace database grants: still use a readonly DB user with least privilege. YAML policy is the **application-layer** filter on generated SELECTs.

### Pre-production checklist

Policy and config:

- [ ] `config/governance/policies.yaml` reviewed for your vertical (not the default `enabled: false` template left as-is by mistake)
- [ ] `enabled: true` in `policies.yaml` when policies should apply
- [ ] `INSIGHTAI_GOVERNANCE_ENABLED=true` in production `.env`
- [ ] `insightai-governance-validate --path config/governance` passes with **zero errors** in CI or release gate
- [ ] Scope dimension ids in roles match `scope_dimensions` keys (no typos)
- [ ] `sql_bindings[].attribute` names match API key / JWT attribute keys exactly
- [ ] Sensitive tables listed under `denied_table_patterns` or excluded from `allowed_tables` for non-admin roles
- [ ] `admin` (or equivalent) role is limited to break-glass operators; not issued to integrations

API keys and principals (Phase 16):

- [ ] Production uses **database-backed** API keys (`INSIGHTAI_API_KEY_AUTH_SOURCE=database` or `both`), not env-only keys, when scope attributes are required
- [ ] Every integration key has the **minimum role** (`analyst`, not `admin`, unless required)
- [ ] Scoped keys include required attributes (e.g. `campus_ids=1,2`) — verified at `insightai-keys create` when governance is enabled
- [ ] JWT mode (if used): tokens include `roles` and `attributes` claims consistent with YAML; short TTL and rotation
- [ ] Admin keys (`roles admin`) stored separately; used only for `/api/v1/admin/*`, not embedded in customer apps
- [ ] Key rotation procedure documented; revoked keys tested (`insightai-keys revoke`)

Runtime verification:

- [ ] `POST /api/v1/ask` or `/api/v1/chat` with `mode: dry_run` and a **scoped** key returns SQL containing expected `WHERE` filters
- [ ] Same request with a key **missing** scope attributes returns **403** `GOVERNANCE_DENIED` (not empty data)
- [ ] Masked columns do not appear in `query_result` columns for restricted roles on real queries
- [ ] Trusted semantic SQL (Phase 11) is still subject to governance when enabled — no bypass path
- [ ] Audit logs: failures set `governance_denied=true`; successes log `governance_applied` / `dimensions_applied` where observability is enabled

Operational:

- [ ] `policies.yaml` changes go through review (PR) like application code; no hot-edit in prod without validation
- [ ] No real student/customer names in committed example YAML (placeholders only in `examples/`)
- [ ] Operators trained on [docs/GOVERNANCE.md](docs/GOVERNANCE.md) attribute contract

### Anti-patterns (do not)

- Rely on `INSIGHTAI_API_KEYS` env list for scoped access — env keys carry **no** roles or attributes.
- Set `INSIGHTAI_API_AUTH_MODE=none` on any network-facing deployment.
- Disable governance while exposing multi-tenant or campus-scoped data (“we trust the LLM”).
- Grant `admin` role to automated integrations or embed admin keys in front-end apps.
- Use `missing_attribute_action: empty_safe` unless you explicitly accept “no rows” semantics for missing scope (still prefer `deny` for production).
- Log full governed SQL in production without a PII review (`INSIGHTAI_OBSERVABILITY_LOG_SQL=false` by default).

### Incident response hints

| Event | Action |
|-------|--------|
| Suspected scope bypass | Capture `request_id`, key id, governed vs raw SQL from audit; compare to `policies.yaml`; rotate key |
| Over-broad `allowed_tables: ["*"]` | Tighten role patterns; re-validate; redeploy policy file |
| Policy deny spike after YAML change | Roll back `policies.yaml`; run `insightai-governance-validate` on previous revision |

## Dependency updates

Run tests after upgrading LLM, database, or framework dependencies:

```bash
pip install -e ".[dev]"
./scripts/test.sh
```

## Attribution

Use of this software is subject to the [MIT License](LICENSE) and [NOTICE](NOTICE) attribution requirements.
