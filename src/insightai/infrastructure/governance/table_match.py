"""Table name glob matching for governance policies."""

from __future__ import annotations

import fnmatch


def normalize_table_name(name: str | None) -> str:
    """Compare tables by bare name (last segment), lowercased."""
    if not name:
        return ""
    return name.split(".")[-1].strip().lower()


def table_matches_pattern(table_name: str, pattern: str) -> bool:
    """Match ``school_school`` against ``*``, ``school_*``, or ``dbo.school_*``."""
    bare = normalize_table_name(table_name)
    pat = pattern.strip().lower()
    if pat in {"*", ""}:
        return True
    pat_bare = normalize_table_name(pat)
    return fnmatch.fnmatchcase(bare, pat_bare) or fnmatch.fnmatchcase(bare, pat)


def is_table_allowed(table_name: str, *, allowed: list[str], denied: list[str]) -> bool:
    if any(table_matches_pattern(table_name, p) for p in denied):
        return False
    if not allowed:
        return False
    if any(p.strip() == "*" for p in allowed):
        return True
    return any(table_matches_pattern(table_name, p) for p in allowed)
