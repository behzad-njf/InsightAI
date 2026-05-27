"""Build explainability payloads from observable pipeline artifacts (Phase 13.2)."""

from __future__ import annotations

import re

from insightai.domain.models.explainability import (
    ExplainabilityBuildRequest,
    ExplainabilityGovernanceSummary,
    ExplainabilityPayload,
    ExplainabilityTrustedSource,
    ExplainabilityValidationSummary,
    ExplainabilityWarning,
    ExplainabilityWarningSeverity,
)
from insightai.domain.models.hybrid import QueryRouteKind
from insightai.domain.models.semantic import GenerationSource
from insightai.domain.ports.explainability_builder import IExplainabilityBuilder

_WARNING_SANITIZE_RE = re.compile(
    r"(traceback|exception|stack trace|password|secret|token|apikey|api_key|odbc_connect)",
    re.IGNORECASE,
)


class ExplainabilityBuilder(IExplainabilityBuilder):
    """Default implementation for Phase 13.2 explainability assembly."""

    def build(self, request: ExplainabilityBuildRequest) -> ExplainabilityPayload:
        route = request.route.route if request.route else _infer_route(request)
        route_rationale = request.route.rationale if request.route else ""
        route_confidence = request.route.confidence if request.route else None

        schema_selection = (
            ExplainabilityPayload.schema_selection_from_context(request.schema_context)
            if request.schema_context is not None
            else []
        )
        join_pattern_titles = (
            [pattern.title for pattern in request.schema_context.join_patterns]
            if request.schema_context is not None
            else []
        )
        referenced_tables = _referenced_tables_for(request)
        generation_source = (
            request.sql_generation.generation_source
            if request.sql_generation is not None
            else GenerationSource.LLM
        )
        trusted = (
            ExplainabilityTrustedSource.from_sql_generation(request.sql_generation)
            if request.sql_generation is not None
            else None
        )
        validation = (
            ExplainabilityValidationSummary.from_validation(request.validation)
            if request.validation is not None
            else None
        )
        governance = (
            ExplainabilityGovernanceSummary.from_governance(request.governance)
            if request.governance is not None
            else None
        )
        rag_citations = (
            ExplainabilityPayload.rag_citations_from_retrieval(request.rag_retrieval)
            if request.rag_retrieval is not None
            else []
        )

        warnings = _collect_warnings(request, governance)

        return ExplainabilityPayload(
            question=request.question,
            route=route,
            route_rationale=route_rationale,
            route_confidence=route_confidence,
            referenced_tables=referenced_tables,
            schema_selection=schema_selection,
            excluded_tables=list(request.excluded_tables),
            join_pattern_titles=join_pattern_titles,
            generation_source=generation_source,
            trusted=trusted,
            validation=validation,
            governance=governance,
            warnings=warnings,
            rag_citations=rag_citations,
            follow_up_questions=_clean_follow_ups(request.follow_up_questions),
            dry_run=request.dry_run,
            sql_executed=request.sql_executed,
        )


def _infer_route(request: ExplainabilityBuildRequest) -> QueryRouteKind:
    if request.rag_retrieval is not None and request.sql_generation is not None:
        return QueryRouteKind.BOTH
    if request.rag_retrieval is not None:
        return QueryRouteKind.RAG
    return QueryRouteKind.SQL


def _referenced_tables_for(request: ExplainabilityBuildRequest) -> list[str]:
    candidates: list[str] = []
    if request.referenced_tables:
        candidates.extend(request.referenced_tables)
    if request.sql_generation is not None and request.sql_generation.tables_used:
        candidates.extend(request.sql_generation.tables_used)
    if request.schema_context is not None and request.schema_context.table_names:
        candidates.extend(request.schema_context.table_names)
    return _dedupe_strings(candidates)


def _collect_warnings(
    request: ExplainabilityBuildRequest,
    governance: ExplainabilityGovernanceSummary | None,
) -> list[ExplainabilityWarning]:
    warnings: list[ExplainabilityWarning] = []
    for warning in request.extra_warnings:
        if warning.message.strip():
            warnings.append(
                warning.model_copy(update={"message": _sanitize_warning_message(warning.message)}),
            )

    if request.validation is not None:
        for violation in request.validation.violations:
            warnings.append(
                ExplainabilityWarning(
                    code="SQL_VALIDATION",
                    message=_sanitize_warning_message(violation),
                    severity=ExplainabilityWarningSeverity.ERROR,
                ),
            )
        for warning in request.validation.warnings:
            warnings.append(
                ExplainabilityWarning(
                    code="SQL_VALIDATION",
                    message=_sanitize_warning_message(warning),
                    severity=ExplainabilityWarningSeverity.WARNING,
                ),
            )

    if governance is not None and governance.denied:
        warnings.append(
            ExplainabilityWarning(
                code=governance.policy_reason_code or "GOVERNANCE_DENIED",
                message=_sanitize_warning_message(
                    governance.deny_message or "Access denied by data policy.",
                ),
                severity=ExplainabilityWarningSeverity.ERROR,
            ),
        )

    deduped: list[ExplainabilityWarning] = []
    seen: set[tuple[str, str, str]] = set()
    for warning in warnings:
        key = (warning.code, warning.severity.value, warning.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped


def _clean_follow_ups(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        text = item.strip()
        if not text:
            continue
        if text not in cleaned:
            cleaned.append(text)
    return cleaned


def _sanitize_warning_message(message: str) -> str:
    text = message.strip()
    if not text:
        return "A warning occurred."
    if _WARNING_SANITIZE_RE.search(text):
        return "A system warning occurred while processing this request."
    return text


def _dedupe_strings(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in items:
        value = raw.strip()
        if not value:
            continue
        if value not in cleaned:
            cleaned.append(value)
    return cleaned
