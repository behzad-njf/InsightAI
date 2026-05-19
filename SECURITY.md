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

## Dependency updates

Run tests after upgrading LLM, database, or framework dependencies:

```bash
pip install -e ".[dev]"
./scripts/test.sh
```

## Attribution

Use of this software is subject to the [MIT License](LICENSE) and [NOTICE](NOTICE) attribution requirements.
