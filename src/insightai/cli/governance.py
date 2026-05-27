"""CLI: validate governance policy YAML (Phase 12.3)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from insightai.infrastructure.config.settings import get_settings
from insightai.infrastructure.governance.validator import validate_governance_catalog
from insightai.infrastructure.logging.setup import configure_logging


def _resolve_governance_dir(path: str | None) -> Path:
    settings = get_settings()
    if path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate.resolve()
        return (settings.project_root / candidate).resolve()
    return settings.resolved_governance_path()


def build_validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insightai-governance-validate",
        description="Validate config/governance/policies.yaml (schema + semantic checks).",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Governance config directory (default: INSIGHTAI_GOVERNANCE_PATH).",
    )
    return parser


def main_validate(argv: list[str] | None = None) -> int:
    args = build_validate_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    governance_dir = _resolve_governance_dir(args.path)

    errors = validate_governance_catalog(governance_dir)
    if errors:
        print(f"governance-validate: {len(errors)} error(s) in {governance_dir}", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1

    from insightai.infrastructure.governance.yaml_loader import YamlGovernancePolicyLoader

    catalog = YamlGovernancePolicyLoader(governance_dir).load()
    print(
        f"governance-validate: OK — {len(catalog.scope_dimensions)} scope dimension(s), "
        f"{len(catalog.roles)} role(s), enabled={catalog.enabled} in {governance_dir}",
    )
    return 0


def main() -> int:
    return main_validate()


if __name__ == "__main__":
    raise SystemExit(main())
