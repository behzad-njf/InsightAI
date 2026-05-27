"""Unit tests for Phase 11 trusted semantic domain models."""

from __future__ import annotations

import pytest

from insightai.domain.models.semantic import (
    ExampleQuery,
    GenerationSource,
    SemanticCatalog,
    TrustedMatchConfidence,
    TrustedMetric,
    TrustedSQLMatchResult,
)


def test_trusted_metric_frozen_and_strips_sql() -> None:
    metric = TrustedMetric(
        id=" active_students ",
        title=" Active students ",
        sql="  SELECT COUNT(*) FROM dbo.accounts_user  ",
        question_hints=["how many students"],
    )
    assert metric.id == "active_students"
    assert metric.sql.startswith("SELECT")
    assert metric.enabled is True


def test_example_query_all_question_phrases_dedupes() -> None:
    example = ExampleQuery(
        id="classroom_headcount",
        question="How many kids are in ABC?",
        question_aliases=[
            "How many kids are in ABC?",
            "  headcount abc  ",
        ],
        sql="SELECT COUNT(*) FROM dbo.school_classroomchild",
    )
    phrases = example.all_question_phrases()
    assert phrases[0] == "how many kids are in ABC"
    assert len(phrases) == 2


def test_trusted_sql_match_from_metric() -> None:
    metric = TrustedMetric(
        id="active_student_count",
        title="Active students",
        sql="SELECT COUNT(*) AS n FROM dbo.accounts_user WHERE is_active = 1",
        description="Count of active user accounts.",
    )
    result = TrustedSQLMatchResult.from_metric(
        metric,
        confidence=TrustedMatchConfidence.QUESTION_MATCH,
    )
    assert result.matched is True
    assert result.generation_source == GenerationSource.TRUSTED_METRIC
    assert result.trusted_asset_id == "active_student_count"
    assert result.confidence == TrustedMatchConfidence.QUESTION_MATCH


def test_semantic_catalog_enabled_filters() -> None:
    catalog = SemanticCatalog(
        metrics=[
            TrustedMetric(id="a", title="A", sql="SELECT 1", enabled=False),
            TrustedMetric(id="b", title="B", sql="SELECT 2"),
        ],
        example_queries=[
            ExampleQuery(
                id="x",
                question="Q?",
                sql="SELECT 3",
                enabled=False,
            ),
        ],
    )
    assert [m.id for m in catalog.enabled_metrics] == ["b"]
    assert catalog.enabled_example_queries == []


def test_empty_sql_rejected() -> None:
    with pytest.raises(ValueError, match="sql must not be empty"):
        TrustedMetric(id="bad", title="Bad", sql="   ")


def test_no_match_factory() -> None:
    result = TrustedSQLMatchResult.no_match()
    assert not result.matched
    assert result.generation_source == GenerationSource.LLM
    assert result.confidence == TrustedMatchConfidence.NONE
