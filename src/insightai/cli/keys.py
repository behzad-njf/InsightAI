"""CLI: create, list, and revoke platform API keys (Phase 16.3)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta

from insightai.domain.exceptions import ApiKeyNotFoundError
from insightai.domain.models.api_key import (
    CreateApiKeyRequest,
    parse_attributes_arg,
    parse_roles_arg,
)
from insightai.infrastructure.app_db.bootstrap import build_app_database_components
from insightai.infrastructure.config.settings import get_settings
from insightai.infrastructure.governance.attribute_contract import (
    validate_key_attributes_for_catalog,
)
from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader
from insightai.infrastructure.logging.setup import configure_logging


def cmd_create(args: argparse.Namespace) -> int:
    settings = get_settings()
    components = build_app_database_components(settings)
    expires_at = None
    if args.expires_days and args.expires_days > 0:
        expires_at = datetime.now(UTC) + timedelta(days=args.expires_days)

    roles = parse_roles_arg(args.roles)
    attributes = parse_attributes_arg(args.attributes)
    if settings.governance_enabled:
        catalog = YamlGovernancePolicyLoader(settings.resolved_governance_path()).load()
        attr_errors = validate_key_attributes_for_catalog(roles, attributes, catalog)
        if attr_errors:
            print("insightai-keys create: attribute contract errors:", file=sys.stderr)
            for line in attr_errors:
                print(f"  - {line}", file=sys.stderr)
            return 1

    request = CreateApiKeyRequest(
        label=args.label,
        roles=roles,
        attributes=attributes,
        expires_at=expires_at,
    )
    result = components.api_key_store.create(request)
    print("API key created (save the secret now — it cannot be shown again):\n")
    print(result.secret)
    print()
    print(f"id:          {result.api_key.id}")
    print(f"label:       {result.api_key.label}")
    print(f"prefix:      {result.api_key.key_prefix}")
    print(f"roles:       {', '.join(result.api_key.roles) or '(none)'}")
    if result.api_key.attributes:
        print(f"attributes:  {json.dumps(result.api_key.attributes)}")
    if result.api_key.expires_at:
        print(f"expires_at:  {result.api_key.expires_at.isoformat()}")
    print()
    print("Use in requests:")
    print(f"  X-API-Key: {result.secret}")
    print(f"  Authorization: Bearer {result.secret}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    settings = get_settings()
    components = build_app_database_components(settings)
    keys = components.api_key_store.list_keys(include_revoked=args.include_revoked)
    if not keys:
        print("No API keys found.")
        return 0
    for key in keys:
        status = "active"
        if key.is_revoked:
            status = "revoked"
        elif key.is_expired:
            status = "expired"
        roles = ",".join(key.roles) or "-"
        print(
            f"{key.id}  prefix={key.key_prefix}  label={key.label!r}  "
            f"roles={roles}  status={status}  created={key.created_at.isoformat()}",
        )
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    settings = get_settings()
    components = build_app_database_components(settings)
    key_id = args.id
    key_prefix = args.prefix
    if not key_id and not key_prefix:
        print("revoke requires --id or --prefix", file=sys.stderr)
        return 1
    ok = components.api_key_store.revoke(key_id=key_id, key_prefix=key_prefix)
    if not ok:
        raise ApiKeyNotFoundError("API key not found.")
    target = key_id or key_prefix
    print(f"revoked: {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage InsightAI platform API keys (stored hashed in app DB).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create", help="Generate a new API key (secret shown once)")
    create_p.add_argument(
        "--label",
        "-l",
        required=True,
        help="Human label, e.g. 'CRM integration'",
    )
    create_p.add_argument(
        "--roles",
        default=None,
        help="Comma-separated roles (default: analyst). Common: analyst, admin",
    )
    create_p.add_argument(
        "--attributes",
        default=None,
        help=(
            "Scope attributes for governance: JSON "
            '\'{"campus_ids":["1","2"]}\' or key=value pairs campus_ids=1,2'
        ),
    )
    create_p.add_argument(
        "--expires-days",
        type=int,
        default=None,
        help="Optional expiry in days from now",
    )
    create_p.set_defaults(func=cmd_create)

    list_p = sub.add_parser("list", help="List keys (no secrets)")
    list_p.add_argument(
        "--include-revoked",
        action="store_true",
        help="Include revoked keys",
    )
    list_p.set_defaults(func=cmd_list)

    revoke_p = sub.add_parser("revoke", help="Revoke a key immediately")
    revoke_p.add_argument("--id", help="Key UUID")
    revoke_p.add_argument("--prefix", help="Key prefix (from list output)")
    revoke_p.set_defaults(func=cmd_revoke)

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging(get_settings())
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ApiKeyNotFoundError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
