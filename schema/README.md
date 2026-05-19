# Schema directory

## Source of truth

**`database_schema.md`** — full CampusMetrics MSSQL schema reference (~8,700 lines).

Agents and SQL generation **must** use table and column names exactly as documented there.

## Contents (high level)

| Section | Description |
|---------|-------------|
| §1 | Purpose and conventions |
| §2 | Domain overview, hub tables (`accounts_user`), join patterns |
| §3 | Table of contents by domain |
| §4 | Foreign key relationship index |
| §5+ | Per-table definitions (columns, types, FKs) |

## Phase 2

A parser will build structured metadata (JSON/Python models) from this markdown for:

- Relevant table retrieval
- Schema context injection into prompts
- Relationship-aware JOIN suggestions

Until Phase 2 ships, read this file directly or grep by table name.
