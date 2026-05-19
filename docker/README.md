# Docker — InsightAI

## Services (`docker compose`)

| Service | Purpose |
|---------|---------|
| `api` | FastAPI app (port 8000) |
| `postgres` | Local PostgreSQL with read-only role |
| `redis` | Reserved for Phase 9 caching (no usage in Phase 1) |

## Quick start

```bash
cp .env.example .env
# Set GROQ_API_KEY in .env (required for /api/v1/ai/complete)

docker compose up --build
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

## Environment

Compose overrides database settings for the `api` service:

- `INSIGHTAI_DATABASE_KIND=postgresql`
- `INSIGHTAI_DATABASE_READONLY_URL=postgresql+psycopg2://insightai_readonly:insightai_readonly@postgres:5432/insightai`

Pass secrets via `.env` (`GROQ_API_KEY`, etc.).

See `.env.docker.example` for a Docker-focused template.

## PostgreSQL init scripts

Executed **once** on first volume creation (`docker/postgres/init/`):

1. `01-readonly-role.sql` — creates `insightai_readonly`, SELECT grants, default privileges
2. `02-sample-schema.sql` — demo `accounts_user` table + seed rows

Reset database:

```bash
docker compose down -v
docker compose up --build
```

## MSSQL in Docker (CampusMetrics / `sa`)

The default `docker compose` stack uses **Postgres** for the `api` service. That is fine for local demos; it does **not** point at your MSSQL container unless you change env.

| How you run the API | `DB_HOST` / URL host |
|---------------------|----------------------|
| `uvicorn` on your machine, MSSQL container publishes `1433` | `localhost` |
| `api` in Docker Compose, MSSQL on the host | `host.docker.internal` (add `extra_hosts: host.docker.internal:host-gateway` on Linux if needed) |
| Both in Compose on the same network | MSSQL service name (e.g. `mssql`) |

**Credentials:** use `DB_READONLY_USER=sa` and `DB_READONLY_PASSWORD=...` in `.env` instead of embedding the password in `INSIGHTAI_DATABASE_READONLY_URL`. Special characters (`@`, `#`, `&`) break manual URLs; component vars are URL-encoded automatically.

**Compose override:** remove or comment the Postgres overrides in `docker-compose.yml` for the `api` service when you want MSSQL:

```yaml
# INSIGHTAI_DATABASE_KIND=postgresql
# INSIGHTAI_DATABASE_READONLY_URL=postgresql+...
```

Set `INSIGHTAI_DATABASE_KIND=mssql` and `DB_*` in `.env` instead.

**ODBC:** the API process needs `pyodbc` and **ODBC Driver 17 for SQL Server** on the machine (or in the API image). The stock Compose image targets Postgres only.

**TrustServerCertificate:** added automatically for MSSQL URLs built from `DB_*` or normalized explicit URLs (typical for dev SQL Server in Docker).

Production notes: `docker/postgres/init/03-mssql-readonly-notes.md`.

## Commands

```bash
docker compose logs -f api
docker compose exec api curl -s http://localhost:8000/api/v1/health
docker compose exec postgres psql -U insightai -d insightai -c "SELECT * FROM accounts_user;"
```
