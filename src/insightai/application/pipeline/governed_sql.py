"""Governed SQL preparation — Phase 4 validate → Phase 12 govern → Phase 4 re-validate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from insightai.domain.models.governance import GovernanceContext, GovernanceDecision
from insightai.domain.models.sql_generation import GenerateSQLResult

if TYPE_CHECKING:
    from insightai.domain.ports.governance import IGovernanceEnforcer
    from insightai.domain.ports.sql_safety import ISQLSafetyValidator


@dataclass(frozen=True)
class GovernedSQLPreparation:
    """SQL ready for Phase 5 execution after governance and safety checks."""

    sql_result: GenerateSQLResult
    governance_decision: GovernanceDecision
    pre_governance_sql: str
    governed_sql: str
    validated_sql: str


def validate_readonly_sql(
    sql: str,
    validator: ISQLSafetyValidator | None,
    *,
    enforce: bool,
) -> str:
    """
    Phase 4 composite validator (SELECT-only, normalization).

    When ``enforce`` is false or no validator is configured, returns SQL unchanged.
    """
    text = sql.strip()
    if not text or not enforce or validator is None:
        return text
    from insightai.domain.exceptions import ReadOnlySQLViolationError

    validation = validator.validate(text)
    if not validation.is_valid:
        reason = "; ".join(validation.violations) or "SQL is not allowed."
        raise ReadOnlySQLViolationError(
            reason,
            sql=text,
            reason=reason,
        )
    return validation.normalized_sql or text


def prepare_governed_sql(
    sql_result: GenerateSQLResult,
    *,
    governance: IGovernanceEnforcer,
    governance_context: GovernanceContext | None,
    sql_validator: ISQLSafetyValidator | None,
    enforce_readonly: bool,
) -> GovernedSQLPreparation:
    """
    Run the governed SQL hook: validate generated SQL, apply policy, validate again.

    Order (Phase 12.4):
        1. Phase 4 — validate pre-governance SQL
        2. Phase 12 — ``IGovernanceEnforcer.enforce`` (may rewrite or deny)
        3. Phase 4 — validate post-governance SQL before execution
    """
    if not sql_result.sql.has_sql:
        msg = "Cannot prepare governed SQL: generation result has no SQL."
        raise ValueError(msg)

    pre_sql = validate_readonly_sql(
        sql_result.sql.sql,
        sql_validator,
        enforce=enforce_readonly,
    )
    pre_result = _copy_sql_result(sql_result, pre_sql)

    governance_decision = governance.enforce(pre_sql, governance_context)
    governed_sql = governance_decision.sql.strip()
    governed_result = _copy_sql_result(pre_result, governed_sql)

    validated_sql = validate_readonly_sql(
        governed_sql,
        sql_validator,
        enforce=enforce_readonly,
    )
    final_result = _copy_sql_result(governed_result, validated_sql)

    return GovernedSQLPreparation(
        sql_result=final_result,
        governance_decision=governance_decision,
        pre_governance_sql=pre_sql,
        governed_sql=governed_sql,
        validated_sql=validated_sql,
    )


def _copy_sql_result(sql_result: GenerateSQLResult, sql: str) -> GenerateSQLResult:
    updated = sql_result.sql.model_copy(update={"sql": sql})
    return sql_result.model_copy(update={"sql": updated})
