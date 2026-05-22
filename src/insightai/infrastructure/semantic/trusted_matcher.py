"""Rule-based trusted SQL matcher (Phase 11)."""

from __future__ import annotations

from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.semantic import (
    ExampleQuery,
    SemanticCatalog,
    TrustedMatchConfidence,
    TrustedMetric,
    TrustedSQLMatchRequest,
    TrustedSQLMatchResult,
)
from insightai.domain.ports.trusted_sql_matcher import ITrustedSQLMatcher
from insightai.infrastructure.semantic.sql_normalizer import normalize_question, normalize_sql


class TrustedSQLMatcher(ITrustedSQLMatcher):
    """
    Match approved metrics and example queries without LLM similarity.

    Priority when ``request.sql`` is set:
    1. Exact stripped SQL string
    2. sqlglot-canonical SQL (dialect-aware)
    Then question phrase match on examples, then metric ``question_hints``.
    """

    def match(
        self,
        request: TrustedSQLMatchRequest,
        catalog: SemanticCatalog,
    ) -> TrustedSQLMatchResult:
        if request.sql and request.sql.strip():
            sql_match = self._match_by_sql(
                request.sql,
                catalog=catalog,
                default_kind=request.database_kind,
            )
            if sql_match.matched:
                return sql_match

        return self._match_by_question(request.question, catalog=catalog)

    def _match_by_sql(
        self,
        sql: str,
        *,
        catalog: SemanticCatalog,
        default_kind: DatabaseKind,
    ) -> TrustedSQLMatchResult:
        incoming_stripped = sql.strip()
        incoming_normalized = normalize_sql(incoming_stripped, kind=default_kind)

        for example in catalog.enabled_example_queries:
            result = self._compare_sql_to_asset(
                example.sql,
                asset=example,
                incoming_stripped=incoming_stripped,
                incoming_normalized=incoming_normalized,
                default_kind=default_kind,
                from_example=True,
            )
            if result.matched:
                return result

        for metric in catalog.enabled_metrics:
            result = self._compare_sql_to_asset(
                metric.sql,
                asset=metric,
                incoming_stripped=incoming_stripped,
                incoming_normalized=incoming_normalized,
                default_kind=default_kind,
                from_example=False,
            )
            if result.matched:
                return result

        return TrustedSQLMatchResult.no_match()

    def _compare_sql_to_asset(
        self,
        asset_sql: str,
        *,
        asset: TrustedMetric | ExampleQuery,
        incoming_stripped: str,
        incoming_normalized: str | None,
        default_kind: DatabaseKind,
        from_example: bool,
    ) -> TrustedSQLMatchResult:
        asset_stripped = asset_sql.strip()
        if asset_stripped == incoming_stripped:
            confidence = TrustedMatchConfidence.EXACT_SQL
            if from_example:
                assert isinstance(asset, ExampleQuery)
                return TrustedSQLMatchResult.from_example(asset, confidence=confidence)
            assert isinstance(asset, TrustedMetric)
            return TrustedSQLMatchResult.from_metric(asset, confidence=confidence)

        asset_kind = asset.dialect or default_kind
        asset_normalized = normalize_sql(asset_stripped, kind=asset_kind)
        if (
            incoming_normalized
            and asset_normalized
            and incoming_normalized == asset_normalized
        ):
            confidence = TrustedMatchConfidence.NORMALIZED_SQL
            if from_example:
                assert isinstance(asset, ExampleQuery)
                return TrustedSQLMatchResult.from_example(asset, confidence=confidence)
            assert isinstance(asset, TrustedMetric)
            return TrustedSQLMatchResult.from_metric(asset, confidence=confidence)

        return TrustedSQLMatchResult.no_match()

    def _match_by_question(
        self,
        question: str,
        *,
        catalog: SemanticCatalog,
    ) -> TrustedSQLMatchResult:
        normalized = normalize_question(question)
        if not normalized:
            return TrustedSQLMatchResult.no_match()

        for example in catalog.enabled_example_queries:
            if normalized in example.all_question_phrases():
                return TrustedSQLMatchResult.from_example(
                    example,
                    confidence=TrustedMatchConfidence.QUESTION_MATCH,
                )

        for metric in catalog.enabled_metrics:
            for hint in metric.question_hints:
                if normalize_question(hint) == normalized:
                    return TrustedSQLMatchResult.from_metric(
                        metric,
                        confidence=TrustedMatchConfidence.QUESTION_MATCH,
                    )

        return TrustedSQLMatchResult.no_match()
