"""CLI: validate and test-match trusted semantic YAML (Phase 11)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from insightai.application.use_cases.match_trusted_sql import MatchTrustedSQLUseCase
from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.semantic import TrustedSQLMatchRequest
from insightai.infrastructure.config.settings import get_settings
from insightai.infrastructure.logging.setup import configure_logging
from insightai.infrastructure.security.sqlglot_integration import SqlglotParseError, parse_sql
from insightai.infrastructure.semantic.trusted_matcher import TrustedSQLMatcher
from insightai.infrastructure.semantic.yaml_loader import YamlSemanticCatalogLoader


def _resolve_semantic_dir(path: str | None) -> Path:
    settings = get_settings()
    if path:
        candidate = Path(path)
        return candidate.resolve() if candidate.is_absolute() else (settings.project_root / candidate).resolve()
    return settings.resolved_semantic_path()


def validate_semantic_catalog(semantic_dir: Path, *, dialect: DatabaseKind) -> list[str]:
    """
    Load YAML and verify each asset SQL parses for the dialect.

    Returns a list of human-readable error lines (empty if valid).
    """
    errors: list[str] = []
    loader = YamlSemanticCatalogLoader(semantic_dir)
    try:
        catalog = loader.load()
    except Exception as exc:
        return [f"Failed to load catalog: {exc}"]

    for metric in catalog.metrics:
        label = f"metrics[{metric.id!r}]"
        kind = metric.dialect or dialect
        try:
            parse_sql(metric.sql, kind=kind)
        except (SqlglotParseError, ValueError) as exc:
            errors.append(f"{label}: {exc}")

    for example in catalog.example_queries:
        label = f"example_queries[{example.id!r}]"
        kind = example.dialect or dialect
        try:
            parse_sql(example.sql, kind=kind)
        except (SqlglotParseError, ValueError) as exc:
            errors.append(f"{label}: {exc}")

    return errors


def build_validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insightai-semantic-validate",
        description="Validate trusted_metrics.yaml and example_queries.yaml (syntax + SQL parse).",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Semantic config directory (default: INSIGHTAI_SEMANTIC_PATH).",
    )
    parser.add_argument(
        "--dialect",
        type=str,
        default=None,
        choices=[k.value for k in DatabaseKind],
        help="SQL dialect for parse check (default: INSIGHTAI_DATABASE_KIND).",
    )
    return parser


def build_test_match_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insightai-semantic-test-match",
        description="Test rule-based matching for a question and optional SQL string.",
    )
    parser.add_argument("--path", type=str, default=None, help="Semantic config directory.")
    parser.add_argument("--question", type=str, required=True, help="Natural language question.")
    parser.add_argument("--sql", type=str, default=None, help="Optional SQL to match against catalog.")
    parser.add_argument(
        "--dialect",
        type=str,
        default=None,
        choices=[k.value for k in DatabaseKind],
        help="SQL dialect (default: INSIGHTAI_DATABASE_KIND).",
    )
    return parser


def main_validate(argv: list[str] | None = None) -> int:
    args = build_validate_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    semantic_dir = _resolve_semantic_dir(args.path)
    dialect = DatabaseKind(args.dialect) if args.dialect else settings.database_kind

    if not semantic_dir.is_dir():
        print(f"semantic-validate: directory not found: {semantic_dir}", file=sys.stderr)
        return 1

    errors = validate_semantic_catalog(semantic_dir, dialect=dialect)
    if errors:
        print(f"semantic-validate: {len(errors)} error(s) in {semantic_dir}", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1

    loader = YamlSemanticCatalogLoader(semantic_dir)
    catalog = loader.load()
    print(
        f"semantic-validate: OK — {len(catalog.metrics)} metric(s), "
        f"{len(catalog.example_queries)} example query(ies) in {semantic_dir}",
    )
    return 0


def main_test_match(argv: list[str] | None = None) -> int:
    args = build_test_match_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    semantic_dir = _resolve_semantic_dir(args.path)
    dialect = DatabaseKind(args.dialect) if args.dialect else settings.database_kind

    if not semantic_dir.is_dir():
        print(f"semantic-test-match: directory not found: {semantic_dir}", file=sys.stderr)
        return 1

    loader = YamlSemanticCatalogLoader(semantic_dir)
    matcher = TrustedSQLMatcher()
    use_case = MatchTrustedSQLUseCase(
        loader,
        matcher,
        settings=settings.model_copy(update={"semantic_enabled": True}),
    )
    result = use_case.execute(
        TrustedSQLMatchRequest(
            question=args.question,
            sql=args.sql,
            database_kind=dialect,
        ),
    )

    print(f"matched: {result.matched}")
    print(f"generation_source: {result.generation_source.value}")
    print(f"confidence: {result.confidence.value}")
    if result.asset_id:
        print(f"trusted_asset_id: {result.asset_id}")
    if result.sql:
        print(f"sql: {result.sql[:200]}{'...' if len(result.sql) > 200 else ''}")
    return 0 if result.matched else 2


def main() -> int:
    """Default entry when invoked as ``insightai-semantic`` (validate)."""
    return main_validate()


if __name__ == "__main__":
    raise SystemExit(main())
