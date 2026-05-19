"""AST-based read-only SQL validation via sqlglot (Phase 4, step 4.2)."""

from __future__ import annotations

from sqlglot import exp

from insightai.domain.models.database import DatabaseKind
from insightai.domain.models.sql import SQLStatementKind, SQLValidationResult
from insightai.domain.ports.sql_safety import ISQLSafetyValidator
from insightai.infrastructure.security.sqlglot_integration import (
    SqlglotParseError,
    canonicalize_sql,
    parse_sql,
)

# sqlglot expression types that must never appear in read-only AI SQL.
_FORBIDDEN_EXPRESSION_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Merge,
    exp.Replace,
    exp.Alter,
    exp.Grant,
    exp.Revoke,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Copy,
    exp.Into,
    exp.Execute,
)

_BLOCKED_CATALOGS: frozenset[str] = frozenset(
    {
        "information_schema",
        "pg_catalog",
        "mysql",
        "performance_schema",
    }
)

_BLOCKED_DATABASES: frozenset[str] = frozenset({"sys", "master", "msdb", "tempdb"})

_BLOCKED_TABLE_NAMES: frozenset[str] = frozenset(
    {
        "sqlite_master",
        "sqlite_schema",
        "sqlite_temp_master",
    }
)


class SQLParseValidator(ISQLSafetyValidator):
    """
    Validates SQL using sqlglot AST analysis for the configured database dialect.

    Allows read-only ``SELECT`` / ``WITH ... SELECT`` / ``UNION`` selects and
    ``EXPLAIN`` diagnostics. Rejects DML/DDL, ``SELECT INTO``, locking reads,
    write CTEs, and common system-catalog references.
    """

    def __init__(self, kind: DatabaseKind = DatabaseKind.MSSQL) -> None:
        self._kind = kind

    @property
    def database_kind(self) -> DatabaseKind:
        return self._kind

    def validate(self, sql: str) -> SQLValidationResult:
        violations: list[str] = []
        warnings: list[str] = []

        try:
            expression = parse_sql(sql, kind=self._kind)
        except SqlglotParseError as exc:
            return SQLValidationResult(
                is_valid=False,
                statement_kind=SQLStatementKind.FORBIDDEN,
                violations=[f"parse_error: {exc}"],
            )

        violations.extend(self._check_root(expression))
        violations.extend(self._check_forbidden_nodes(expression))
        violations.extend(self._check_locking_reads(expression))
        violations.extend(self._check_system_catalog_tables(expression))

        is_explain = self._is_explain(expression)
        if is_explain:
            warnings.append("EXPLAIN queries are allowed but may not return business data.")

        is_valid = len(violations) == 0
        statement_kind = SQLStatementKind.FORBIDDEN
        normalized: str | None = None

        if is_valid and (is_explain or self._is_read_query(expression)):
            statement_kind = SQLStatementKind.SELECT
            normalized = canonicalize_sql(expression, kind=self._kind)
        elif is_valid:
            violations.append(
                "forbidden_statement: Only SELECT, WITH ... SELECT, UNION, or EXPLAIN "
                "queries are allowed."
            )
            is_valid = False

        return SQLValidationResult(
            is_valid=is_valid,
            statement_kind=statement_kind,
            normalized_sql=normalized,
            violations=violations,
            warnings=warnings,
        )

    def _check_root(self, expression: exp.Expression) -> list[str]:
        if self._is_explain(expression):
            return []
        if isinstance(expression, (exp.Select, exp.Union)):
            return []
        root = type(expression).__name__
        return [
            "forbidden_statement: Only SELECT, WITH ... SELECT, UNION, or EXPLAIN "
            f"queries are allowed (got {root})."
        ]

    def _check_forbidden_nodes(self, expression: exp.Expression) -> list[str]:
        violations: list[str] = []
        for node in expression.walk():
            for forbidden_type in _FORBIDDEN_EXPRESSION_TYPES:
                if isinstance(node, forbidden_type):
                    violations.append(
                        f"forbidden_ast:{forbidden_type.__name__}: "
                        f"Disallowed SQL construct ({forbidden_type.__name__})."
                    )
            if isinstance(node, exp.Command) and not self._is_explain_command(node):
                violations.append(
                    "forbidden_ast:Command: Disallowed SQL command "
                    f"({node.name or node.this})."
                )
        return violations

    @staticmethod
    def _check_locking_reads(expression: exp.Expression) -> list[str]:
        violations: list[str] = []
        for select in expression.find_all(exp.Select):
            locks = select.args.get("locks") or []
            for lock in locks:
                if getattr(lock, "args", {}).get("update") or getattr(lock, "update", False):
                    violations.append(
                        "for_update: SELECT ... FOR UPDATE / locking reads are not allowed."
                    )
                    break
        return violations

    @staticmethod
    def _check_system_catalog_tables(expression: exp.Expression) -> list[str]:
        violations: list[str] = []
        for table in expression.find_all(exp.Table):
            catalog = (table.catalog or "").lower()
            db = (table.db or "").lower()
            name = (table.name or "").lower()

            if catalog in _BLOCKED_CATALOGS or db in _BLOCKED_CATALOGS:
                violations.append(
                    f"system_catalog: Access to system catalog '{catalog or db}' is not allowed."
                )
            elif db in _BLOCKED_DATABASES:
                violations.append(
                    f"system_catalog: Access to system database '{db}' is not allowed."
                )
            elif name in _BLOCKED_TABLE_NAMES:
                violations.append(
                    f"system_catalog: Access to system table '{name}' is not allowed."
                )
        return violations

    def _is_explain(self, expression: exp.Expression) -> bool:
        return isinstance(expression, exp.Command) and self._is_explain_command(expression)

    @staticmethod
    def _is_explain_command(command: exp.Command) -> bool:
        label = (command.name or command.this or "").upper()
        return label == "EXPLAIN" or str(label).startswith("EXPLAIN")

    @staticmethod
    def _is_read_query(expression: exp.Expression) -> bool:
        return isinstance(expression, (exp.Select, exp.Union))
