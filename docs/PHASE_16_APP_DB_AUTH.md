# Phase 16 — App database & API key auth (implementation log)

> **Roadmap:** [FUTURE_PHASES.md](../FUTURE_PHASES.md) § Phase 16  
> **Status:** ✅ Complete (2026-05-22)  
> **Workflow:** Complete one step → update this file and [README.md](../README.md) → confirm → next step.

---

## Goal

Persistent **platform** data (API keys, roles, attributes, feedback, SQL reviews) in a dedicated **app database**, separate from the customer **readonly analytics** database. **Primary auth: API keys** stored hashed in the app DB, with a simple CLI to create keys for integrators.

---

## Two-database model

| Database | Env | Purpose |
|----------|-----|---------|
| **Customer readonly** | `INSIGHTAI_DATABASE_READONLY_URL`, `DB_READONLY_*` | NL→SQL analytics — your operational schema |
| **Platform app** | `INSIGHTAI_APP_DATABASE_URL` | InsightAI-owned tables — keys, audit extensions, feedback (later phases) |

Never store customer DB credentials in the app database.

---

## Step checklist

| Step | Task | Status | Notes |
|------|------|--------|-------|
| **16.1** | `INSIGHTAI_APP_DATABASE_URL` + Alembic bootstrap | ✅ Done | Default SQLite `data/insightai_app.db`; `insightai-app-db` CLI |
| **16.2** | Domain: `ApiKey`, `Principal`, roles | ✅ Done | `domain/models/api_key.py` |
| **16.3** | `IApiKeyStore` + bcrypt; **`insightai-keys`** CLI | ✅ Done | `SqlApiKeyStore`, migration `002_api_keys` |
| **16.4** | HTTP auth: app DB + env fallback | ✅ Done | `INSIGHTAI_API_KEY_AUTH_SOURCE` |
| **16.5** | Principal → governance pipeline + admin routes | ✅ Done | `GovernanceContext`, `/api/v1/admin/keys` |
| **16.6** | Rate limits by `api_key_id` | ✅ Done | `api_key:{uuid}` bucket |
| **16.7** | README / production runbook | ✅ Done | See [README.md](../README.md) |

---

## Step 16.1 — App DB + migrations (complete)

### Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `INSIGHTAI_APP_DATABASE_URL` | *(unset)* | SQLAlchemy URL; when unset → `sqlite:///<project>/data/insightai_app.db` |

**Production:** use PostgreSQL, e.g.  
`postgresql+psycopg2://insightai_app:PASSWORD@postgres:5432/insightai_app`

### Layout

```text
src/insightai/infrastructure/app_db/
  base.py              # AppBase declarative metadata
  engine.py            # Engine factory + SQLite dir creation
  bootstrap.py         # build_app_database_components()
  models/              # ORM tables (16.2+)
alembic/
  env.py               # Reads resolved_app_database_url()
  versions/001_bootstrap_app_db.py
```

### Migrations (production)

```bash
# After pip install -e .
export INSIGHTAI_APP_DATABASE_URL='postgresql+psycopg2://user:pass@host:5432/insightai_app'
insightai-app-db upgrade
insightai-app-db current
```

API lifespan wires `app.state.app_database` (engine disposed on shutdown).

### Verify

```bash
.venv/bin/pip install -e .
insightai-app-db upgrade
.venv/bin/python -m pytest tests/unit/test_app_database_settings.py tests/unit/test_app_db_alembic.py -q
```

---

## Step 16.2 — Domain models (complete)

| Type | Purpose |
|------|---------|
| `PlatformRole` | Common roles: `analyst`, `admin` (custom strings allowed) |
| `ApiKey` | Metadata: id, prefix, label, roles, attributes, expiry, revoke |
| `Principal` | Governance-ready caller (`from_api_key`) |
| `CreateApiKeyRequest` / `CreateApiKeyResult` | Issue keys; secret returned once |

## Step 16.3 — Store + CLI (complete)

| Piece | Location |
|-------|----------|
| Port | `domain/ports/api_key_store.py` — `IApiKeyStore` |
| ORM | `infrastructure/app_db/models/api_keys.py` |
| Store | `infrastructure/app_db/api_key_store.py` — bcrypt at rest |
| Token format | `iai_<prefix>_<secret>` — `key_format.py` |
| CLI | `insightai-keys create \| list \| revoke` |

### Create a key (production)

```bash
insightai-app-db upgrade
insightai-keys create --label "Example integration" --roles analyst
# Optional scope for governance (Phase 12):
insightai-keys create --label "Campus A" --roles analyst \
  --attributes '{"campus_ids":["1","2"]}' --expires-days 90
```

Copy the printed secret immediately. Use:

```bash
curl -H "X-API-Key: iai_..." http://localhost:8000/api/v1/health
```

List / revoke:

```bash
insightai-keys list
insightai-keys revoke --prefix <prefix_from_list>
insightai-keys revoke --id <uuid>
```

### Verify

```bash
.venv/bin/python -m pytest tests/unit/test_api_key_models.py tests/unit/test_api_key_store.py tests/unit/test_keys_cli.py tests/unit/test_key_format.py -q
```

## Step 16.4 — HTTP auth wired to app DB (complete)

| Setting | Values | Behavior |
|---------|--------|----------|
| `INSIGHTAI_API_AUTH_MODE` | `api_key` | Protected routes require a valid key |
| `INSIGHTAI_API_KEY_AUTH_SOURCE` | `env` \| `database` \| `both` (default **`both`**) | Where keys are checked |

**Validation order (when `both` or `database`):**

1. App DB (`app.state.app_database.api_key_store.verify`)
2. Env `INSIGHTAI_API_KEYS` (when `both` or `env`)

**Authenticated principal** includes `api_key_id`, `roles`, `attributes` for DB keys; env keys keep legacy `api_key_N` subjects.

**Production without env keys:**

```bash
INSIGHTAI_API_AUTH_MODE=api_key
INSIGHTAI_API_KEY_AUTH_SOURCE=database
insightai-app-db upgrade
insightai-keys create --label "Production integration" --roles analyst
```

Use the printed `iai_...` token on `/api/v1/chat`, `/ask`, etc.

### Verify

```bash
.venv/bin/python -m pytest tests/unit/test_api_auth.py tests/integration/test_auth_api_db_keys.py -q
```

## API keys: env vs database

| Source | How |
|--------|-----|
| **database** | `insightai-keys create` → use `iai_...` on requests |
| **env** | `INSIGHTAI_API_KEYS=key1,key2` |
| **both** (default) | DB keys first, then env fallback |

---

## Document history

| Date | Change |
|------|--------|
| 2026-05-22 | Step 16.1 — app DB settings, Alembic, `insightai-app-db`, lifespan wire |
| 2026-05-22 | Steps 16.2–16.3 — domain models, `SqlApiKeyStore`, `insightai-keys` CLI |
| 2026-05-22 | Step 16.4 — HTTP auth via app DB + `INSIGHTAI_API_KEY_AUTH_SOURCE` |
| 2026-05-22 | Steps 16.5–16.7 — governance plumbing, admin API, rate limits, docs |

## Step 16.5 — Governance context (complete)

- `GovernanceContext` on each authenticated request (`request.state.governance_context`)
- Passed into `AskRequest` → `AskUseCase` → `IGovernanceEnforcer` (Phase 12.2+)
- Attribute contract: [PHASE_12_GOVERNANCE.md](PHASE_12_GOVERNANCE.md) § 12.5
- Audit logs include `auth_api_key_id` and `auth_roles`
- **Admin API:** `GET /api/v1/admin/keys` requires `admin` role on the API key

## Step 16.6 — Rate limits (complete)

Authenticated DB keys use bucket `api_key:{uuid}` (not shared by label).

## Production quick reference

```bash
# 1. App DB
export INSIGHTAI_APP_DATABASE_URL='postgresql+psycopg2://...'
insightai-app-db upgrade

# 2. Auth
export INSIGHTAI_API_AUTH_MODE=api_key
export INSIGHTAI_API_KEY_AUTH_SOURCE=database   # or both

# 3. Create keys
insightai-keys create --label "Integration" --roles analyst \
  --attributes '{"campus_ids":["1"]}'
insightai-keys create --label "Ops admin" --roles admin

# 4. Call API
curl -H "X-API-Key: iai_..." https://your-host/api/v1/chat ...

# 5. Admin list (admin key only)
curl -H "X-API-Key: iai_..." https://your-host/api/v1/admin/keys
```

**Security:** Customer readonly DB credentials live only in env (`INSIGHTAI_DATABASE_*`). The app DB stores platform keys (hashed), never customer warehouse passwords.
