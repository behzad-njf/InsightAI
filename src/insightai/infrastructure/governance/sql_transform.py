"""sqlglot transforms for governance (Phase 12.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlglot import exp

from insightai.domain.models.governance import ColumnMaskStrategy, MaskRule, RowFilterRule
from insightai.infrastructure.governance.table_match import (
    is_table_allowed,
    normalize_table_name,
)
from insightai.infrastructure.security.sqlglot_integration import (
    canonicalize_sql,
    is_select_expression,
    parse_sql,
)

if TYPE_CHECKING:
    from insightai.domain.models.database import DatabaseKind


def extract_query_tables(expression: exp.Expression) -> set[str]:
    """Bare table names referenced in the query."""
    names: set[str] = set()
    for table in expression.find_all(exp.Table):
        bare = normalize_table_name(table.name)
        if bare:
            names.add(bare)
    return names


def check_tables_allowed(
    expression: exp.Expression,
    *,
    allowed_tables: tuple[str, ...],
    denied_patterns: tuple[str, ...],
) -> str | None:
    """Return a safe deny message when a referenced table is not allowed."""
    tables = extract_query_tables(expression)
    if not tables:
        return None
    for table in sorted(tables):
        if not is_table_allowed(
            table,
            allowed=[*allowed_tables],
            denied=[*denied_patterns],
        ):
            return f"Access to table '{table}' is not permitted for this role."
    return None


def _table_alias_map(select: exp.Select) -> dict[str, str]:
    """Map bare table name -> SQL alias used in the query."""
    mapping: dict[str, str] = {}
    for table in select.find_all(exp.Table):
        bare = normalize_table_name(table.name)
        if not bare:
            continue
        alias = table.alias_or_name
        mapping[bare] = alias
    return mapping


def _condition_for_filter(
    rule: RowFilterRule,
    *,
    table_alias: str,
    dialect: str,
) -> exp.Expression:
    col = exp.column(rule.column, table=table_alias)
    if not rule.is_restrictive:
        return exp.false()
    literals = [exp.Literal.string(str(value)) for value in rule.values]
    return exp.In(this=col, expressions=literals)


def apply_row_filters(
    expression: exp.Expression,
    filters: tuple[RowFilterRule, ...],
    *,
    kind: DatabaseKind,
) -> exp.Expression:
    """Inject ``AND`` scope conditions on SELECT / UNION branches."""
    if not filters:
        return expression
    dialect = kind.value
    for select in expression.find_all(exp.Select):
        alias_map = _table_alias_map(select)
        extra_conditions: list[exp.Expression] = []
        for rule in filters:
            bare = normalize_table_name(rule.table)
            alias = alias_map.get(bare)
            if alias is None:
                continue
            extra_conditions.append(
                _condition_for_filter(rule, table_alias=alias, dialect=dialect),
            )
        if not extra_conditions:
            continue
        combined = extra_conditions[0]
        for cond in extra_conditions[1:]:
            combined = exp.and_(combined, cond)
        existing = select.args.get("where")
        merged = exp.and_(existing, combined) if existing else combined
        select.set("where", exp.Where(this=merged))
    return expression


def _column_name(expression: exp.Expression) -> str | None:
    if isinstance(expression, exp.Column):
        return expression.name
    if isinstance(expression, exp.Alias):
        inner = expression.this
        if isinstance(inner, exp.Column):
            return inner.name
        return expression.alias
    return None


def apply_column_masks(
    expression: exp.Expression,
    masks: tuple[MaskRule, ...],
) -> tuple[exp.Expression, tuple[str, ...]]:
    """Apply SELECT-list masks; returns applied mask column names."""
    if not masks:
        return expression, ()
    mask_by_column = {m.column.lower(): m for m in masks}
    applied: list[str] = []

    for select in expression.find_all(exp.Select):
        new_expressions: list[exp.Expression] = []
        for proj in select.expressions:
            name = _column_name(proj)
            if name is None:
                new_expressions.append(proj)
                continue
            rule = mask_by_column.get(name.lower())
            if rule is None:
                new_expressions.append(proj)
                continue
            applied.append(name.lower())
            if rule.strategy == ColumnMaskStrategy.EXCLUDE:
                continue
            if rule.strategy == ColumnMaskStrategy.NULL_LITERAL:
                alias = proj.alias if isinstance(proj, exp.Alias) else name
                new_expressions.append(exp.alias_(exp.Null(), alias or name))
                continue
            if rule.strategy == ColumnMaskStrategy.HASH:
                alias = proj.alias if isinstance(proj, exp.Alias) else name
                new_expressions.append(
                    exp.alias_(exp.Literal.string("***"), alias or name),
                )
                continue
            new_expressions.append(proj)
        if new_expressions:
            select.set("expressions", new_expressions)
    return expression, tuple(dict.fromkeys(applied))


def transform_select_sql(
    sql: str,
    *,
    kind: DatabaseKind,
    filters: tuple[RowFilterRule, ...],
    masks: tuple[MaskRule, ...],
    allowed_tables: tuple[str, ...],
    denied_patterns: tuple[str, ...],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """
    Parse, enforce table policy, inject filters, mask columns.

    Returns:
        (governed_sql, dimensions_applied, masks_applied)
    """
    expression = parse_sql(sql, kind=kind)
    if not is_select_expression(expression):
        msg = "Governance enforcement supports SELECT statements only."
        raise ValueError(msg)

    deny_msg = check_tables_allowed(
        expression,
        allowed_tables=allowed_tables,
        denied_patterns=denied_patterns,
    )
    if deny_msg:
        raise ValueError(deny_msg)

    dimension_ids = tuple({rule.dimension_id for rule in filters})
    expression = apply_row_filters(expression, filters, kind=kind)
    expression, masks_applied = apply_column_masks(expression, masks)
    return canonicalize_sql(expression, kind=kind), dimension_ids, masks_applied
