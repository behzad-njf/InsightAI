"""SQL safety test payloads for Phase 4 acceptance (4.4)."""

from __future__ import annotations

from dataclasses import dataclass

from insightai.domain.models.database import DatabaseKind


@dataclass(frozen=True)
class SafetyPayload:
    """Single SQL string and expected composite-validator outcome."""

    sql: str
    kind: DatabaseKind
    should_accept: bool
    label: str
    violation_contains: tuple[str, ...] = ()


# --- Must reject (Phase 4 acceptance + Phase 1 parity) ---

REJECTED_PAYLOADS: tuple[SafetyPayload, ...] = (
    SafetyPayload(
        sql="DELETE FROM accounts_user WHERE id = 1",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="delete",
        violation_contains=("forbidden_ast:Delete",),
    ),
    SafetyPayload(
        sql="INSERT INTO accounts_user (email) VALUES ('a@b.c')",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="insert",
        violation_contains=("Insert",),
    ),
    SafetyPayload(
        sql="UPDATE accounts_user SET email = 'x' WHERE id = 1",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="update",
        violation_contains=("Update",),
    ),
    SafetyPayload(
        sql="DROP TABLE accounts_user",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="drop",
        violation_contains=("Drop",),
    ),
    SafetyPayload(
        sql="TRUNCATE TABLE accounts_user",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="truncate",
        violation_contains=("forbidden",),
    ),
    SafetyPayload(
        sql="SELECT 1; SELECT 2",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="stacked_select",
        violation_contains=("parse_error:", "Multiple"),
    ),
    SafetyPayload(
        sql="SELECT 1; DELETE FROM accounts_user",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="stacked_delete",
        violation_contains=("parse_error:", "Multiple"),
    ),
    SafetyPayload(
        sql="SELECT 1 WHERE 1=1; DROP TABLE accounts_user--",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="stacked_drop_inline_comment",
        violation_contains=("parse_error:", "Multiple"),
    ),
    SafetyPayload(
        sql="SELECT * INTO #tmp FROM accounts_user",
        kind=DatabaseKind.MSSQL,
        should_accept=False,
        label="select_into_mssql",
        violation_contains=("Into",),
    ),
    SafetyPayload(
        sql=(
            "WITH staged AS (INSERT INTO accounts_user (email) VALUES ('x')) "
            "SELECT 1"
        ),
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="write_cte",
        violation_contains=("Insert",),
    ),
    SafetyPayload(
        sql="SELECT id FROM accounts_user FOR UPDATE",
        kind=DatabaseKind.POSTGRESQL,
        should_accept=False,
        label="for_update",
        violation_contains=("for_update:",),
    ),
    SafetyPayload(
        sql="SELECT table_name FROM information_schema.tables",
        kind=DatabaseKind.POSTGRESQL,
        should_accept=False,
        label="information_schema",
        violation_contains=("system_catalog:",),
    ),
    SafetyPayload(
        sql="SELECT name FROM sys.objects",
        kind=DatabaseKind.MSSQL,
        should_accept=False,
        label="sys_objects",
        violation_contains=("system_catalog:",),
    ),
    SafetyPayload(
        sql="EXEC sp_help",
        kind=DatabaseKind.MSSQL,
        should_accept=False,
        label="exec_mssql",
        violation_contains=("Execute", "forbidden_statement", "forbidden_ast"),
    ),
    SafetyPayload(
        sql="CALL proc()",
        kind=DatabaseKind.POSTGRESQL,
        should_accept=False,
        label="call_procedure",
        violation_contains=("Command",),
    ),
    SafetyPayload(
        sql="SELECT 1;;",
        kind=DatabaseKind.SQLITE,
        should_accept=False,
        label="double_semicolon",
        violation_contains=("parse_error:", "Multiple", "forbidden"),
    ),
)

# --- Must accept ---

ACCEPTED_PAYLOADS: tuple[SafetyPayload, ...] = (
    SafetyPayload(
        sql="SELECT id, email FROM accounts_user WHERE is_active = 1",
        kind=DatabaseKind.SQLITE,
        should_accept=True,
        label="simple_select",
    ),
    SafetyPayload(
        sql=(
            "WITH active AS (SELECT id FROM accounts_user WHERE is_active = 1) "
            "SELECT TOP 10 id FROM active"
        ),
        kind=DatabaseKind.MSSQL,
        should_accept=True,
        label="mssql_with_cte_top",
    ),
    SafetyPayload(
        sql="SELECT 1 AS n UNION ALL SELECT 2 AS n",
        kind=DatabaseKind.SQLITE,
        should_accept=True,
        label="union_all",
    ),
    SafetyPayload(
        sql="EXPLAIN SELECT 1",
        kind=DatabaseKind.POSTGRESQL,
        should_accept=True,
        label="explain",
    ),
    SafetyPayload(
        sql="SELECT 'DELETE' AS label, 'DROP TABLE' AS hint FROM accounts_user",
        kind=DatabaseKind.SQLITE,
        should_accept=True,
        label="keywords_in_string_literals",
    ),
    SafetyPayload(
        sql="SELECT 'active' AS status FROM accounts_user WHERE note LIKE '%DELETE%'",
        kind=DatabaseKind.SQLITE,
        should_accept=True,
        label="delete_substring_in_string_and_like",
    ),
    SafetyPayload(
        sql="SELECT 1 /*; DELETE FROM accounts_user */",
        kind=DatabaseKind.SQLITE,
        should_accept=True,
        label="block_comment_with_delete_text",
    ),
    SafetyPayload(
        sql="-- leading comment\nSELECT id FROM accounts_user",
        kind=DatabaseKind.SQLITE,
        should_accept=True,
        label="leading_line_comment",
    ),
)

# Keyword layer false-positives that composite must accept (4.4 regression).

KEYWORD_FALSE_POSITIVE_PAYLOADS: tuple[SafetyPayload, ...] = (
    SafetyPayload(
        sql="SELECT 'DELETE' AS label FROM accounts_user",
        kind=DatabaseKind.SQLITE,
        should_accept=True,
        label="string_delete",
    ),
    SafetyPayload(
        sql="SELECT id FROM accounts_user WHERE status = 'INSERT'",
        kind=DatabaseKind.SQLITE,
        should_accept=True,
        label="string_insert",
    ),
)
