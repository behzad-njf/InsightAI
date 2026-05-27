"""CLI for platform app database migrations (Phase 16.1)."""

from __future__ import annotations

import argparse
import sys

from alembic import command
from alembic.config import Config

from insightai.infrastructure.config.settings import get_settings


def _alembic_config() -> Config:
    root = get_settings().project_root
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        msg = f"alembic.ini not found at {ini_path}"
        raise FileNotFoundError(msg)
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(root / "src"))
    return cfg


def cmd_upgrade(_args: argparse.Namespace) -> int:
    """Apply all pending migrations (``alembic upgrade head``)."""
    command.upgrade(_alembic_config(), "head")
    settings = get_settings()
    print(
        "app-db upgrade: OK —",
        settings.resolved_app_database_url(),
    )
    return 0


def cmd_current(_args: argparse.Namespace) -> int:
    """Show current Alembic revision."""
    command.current(_alembic_config())
    return 0


def cmd_revision(args: argparse.Namespace) -> int:
    """Autogenerate a new migration (requires ORM models in 16.2+)."""
    message = args.message.strip()
    if not message:
        print("revision requires --message", file=sys.stderr)
        return 1
    command.revision(
        _alembic_config(),
        message=message,
        autogenerate=args.autogenerate,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="InsightAI platform app database (Alembic migrations).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    upgrade_parser = sub.add_parser("upgrade", help="Apply migrations (alembic upgrade head)")
    upgrade_parser.set_defaults(func=cmd_upgrade)

    current_parser = sub.add_parser("current", help="Show current revision")
    current_parser.set_defaults(func=cmd_current)

    revision_parser = sub.add_parser("revision", help="Create a new migration file")
    revision_parser.add_argument(
        "--message",
        "-m",
        required=True,
        help="Migration message slug",
    )
    revision_parser.add_argument(
        "--autogenerate",
        action="store_true",
        help="Detect ORM model changes (16.2+)",
    )
    revision_parser.set_defaults(func=cmd_revision)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
