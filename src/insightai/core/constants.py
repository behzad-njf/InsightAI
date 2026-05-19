"""Shared constants — security lists and application defaults."""

from __future__ import annotations

# Keywords that must never appear in AI-generated SQL (word-boundary match).
BLOCKED_SQL_KEYWORDS: frozenset[str] = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "MERGE",
        "REPLACE",
        "GRANT",
        "REVOKE",
        "EXEC",
        "EXECUTE",
        "CALL",
        "COPY",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "VACUUM",
        "REINDEX",
        "CLUSTER",
        "COMMENT",
        "RENAME",
        "LOAD",
        "UNLOAD",
        "BACKUP",
        "RESTORE",
        "KILL",
        "SHUTDOWN",
        "DBCC",
        "BULK",
        "OPENROWSET",
        "OPENQUERY",
        "OPENDATASOURCE",
    }
)

# Additional dangerous phrases (substring match).
BLOCKED_SQL_PHRASES: frozenset[str] = frozenset(
    {
        "SELECT INTO",
        "FOR UPDATE",
        "INTO OUTFILE",
        "INTO DUMPFILE",
        "XP_",
        "SP_EXECUTESQL",
        "EXECUTE IMMEDIATE",
        ";;",
    }
)

# Allowed leading statement starters after normalization.
ALLOWED_SQL_STARTERS: frozenset[str] = frozenset({"SELECT", "WITH", "EXPLAIN"})
