"""Unit tests for Phase 11 trusted SQL matcher."""

from __future__ import annotations

from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.semantic import (
    ExampleQuery,
    GenerationSource,
    SemanticCatalog,
    TrustedMatchConfidence,
    TrustedMetric,
    TrustedSQLMatchRequest,
)
from insightai.infrastructure.semantic.trusted_matcher import TrustedSQLMatcher


def _catalog() -> SemanticCatalog:
    return SemanticCatalog(
        metrics=[
            TrustedMetric(
                id="active_users",
                title="Active users",
                sql="SELECT COUNT(*) AS n FROM dbo.accounts_user WHERE is_active = 1",
                question_hints=["how many active users"],
            ),
        ],
        example_queries=[
            ExampleQuery(
                id="classroom_count",
                question="How many kids are in the Example classroom?",
                sql=(
                    "SELECT COUNT(DISTINCT cc.child_id) AS kid_count "
                    "FROM dbo.school_classroomchild AS cc "
                    "INNER JOIN dbo.school_classroom AS c ON c.id = cc.classroom_id "
                    "WHERE c.classroom_name = N'Example'"
                ),
                question_aliases=["headcount Example classroom"],
            ),
        ],
    )


def test_question_match_example_query() -> None:
    matcher = TrustedSQLMatcher()
    result = matcher.match(
        TrustedSQLMatchRequest(
            question="headcount Example classroom",
            database_kind=DatabaseKind.MSSQL,
        ),
        _catalog(),
    )
    assert result.matched
    assert result.generation_source == GenerationSource.TRUSTED_EXAMPLE
    assert result.asset_id == "classroom_count"
    assert result.confidence == TrustedMatchConfidence.QUESTION_MATCH


def test_question_match_metric_hint() -> None:
    matcher = TrustedSQLMatcher()
    result = matcher.match(
        TrustedSQLMatchRequest(
            question="How many active users?",
            database_kind=DatabaseKind.MSSQL,
        ),
        _catalog(),
    )
    assert result.matched
    assert result.generation_source == GenerationSource.TRUSTED_METRIC
    assert result.asset_id == "active_users"


def test_exact_sql_match_example() -> None:
    catalog = _catalog()
    sql = catalog.example_queries[0].sql
    matcher = TrustedSQLMatcher()
    result = matcher.match(
        TrustedSQLMatchRequest(
            question="ignored when sql matches",
            sql=sql,
            database_kind=DatabaseKind.MSSQL,
        ),
        catalog,
    )
    assert result.matched
    assert result.confidence == TrustedMatchConfidence.EXACT_SQL
    assert result.asset_id == "classroom_count"


def test_normalized_sql_match_whitespace() -> None:
    catalog = _catalog()
    base = catalog.metrics[0].sql
    spaced = base.replace("SELECT", "SELECT  ")
    matcher = TrustedSQLMatcher()
    result = matcher.match(
        TrustedSQLMatchRequest(
            question="q",
            sql=spaced,
            database_kind=DatabaseKind.MSSQL,
        ),
        catalog,
    )
    assert result.matched
    assert result.confidence == TrustedMatchConfidence.NORMALIZED_SQL
    assert result.asset_id == "active_users"


def test_sql_match_precedes_weaker_question_signal() -> None:
    catalog = _catalog()
    metric_sql = catalog.metrics[0].sql
    matcher = TrustedSQLMatcher()
    result = matcher.match(
        TrustedSQLMatchRequest(
            question="How many kids are in the Example classroom?",
            sql=metric_sql,
            database_kind=DatabaseKind.MSSQL,
        ),
        catalog,
    )
    assert result.asset_id == "active_users"
    assert result.confidence == TrustedMatchConfidence.EXACT_SQL


def test_no_match_returns_llm_default() -> None:
    matcher = TrustedSQLMatcher()
    result = matcher.match(
        TrustedSQLMatchRequest(
            question="totally unrelated question",
            database_kind=DatabaseKind.MSSQL,
        ),
        _catalog(),
    )
    assert not result.matched
    assert result.generation_source == GenerationSource.LLM


def test_disabled_assets_skipped() -> None:
    catalog = SemanticCatalog(
        metrics=[
            TrustedMetric(
                id="hidden",
                title="Hidden",
                sql="SELECT 1",
                question_hints=["secret hint"],
                enabled=False,
            ),
        ],
    )
    matcher = TrustedSQLMatcher()
    result = matcher.match(
        TrustedSQLMatchRequest(question="secret hint", database_kind=DatabaseKind.MSSQL),
        catalog,
    )
    assert not result.matched
