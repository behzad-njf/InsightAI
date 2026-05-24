# SQL generation: never guess — use schema and Knowledge

> **InsightAI:** Indexed from `Knowledge/`. Applies to **every** NL→SQL question when this chunk is in the SQL prompt (`INSIGHTAI_SQL_KNOWLEDGE_CONTEXT_ENABLED=true`).

## Non-negotiable rule

**Do not guess** table names, column names, join keys, or enum values.

- Wrong: inventing `ag.name`, `ag.age_group_name`, `school_school.name`, `accounts_user.birth_date`, `cp.campus_id` because they “sound right”.
- Right: use only identifiers that appear in the **schema context** supplied with the prompt and/or in **retrieved Knowledge** `.md` files.

If a column is not listed for that table in schema context and no Knowledge doc names it for that entity, **do not use it**. Pick a documented alternative or return SQL that uses only confirmed columns.

## Sources of truth (in order)

1. **Schema markdown** — `schema/database_schema.md` (loaded as table/column context for SQL generation). Every table and column in the final SQL must be traceable here unless step 2 overrides with an explicit UVIMS rule. Check **per-table column lists** and **§2.3 join patterns** — do not copy `ag.name` from memory; the live column is `reference_information_agegroup.title`.

2. **Knowledge/** domain files — product-specific joins, renames, and anti-patterns. When Knowledge contradicts a generic name (e.g. “use `title` not `name`”), **Knowledge wins** for this database. These files are **always injected** for SQL (pinned): `sql_never_guess_schema.md`, `campus_age_groups.md`, `campus_name_matching.md`, plus similar-chunk retrieval.

3. **Never** rely on training-data assumptions about “typical” school/CRM schemas.

## Before writing SQL — checklist

1. Identify which **tables** are needed; confirm each exists in schema context.
2. For each table, list **columns** you will reference; confirm each exists on that table in schema context.
3. Search mentally against retrieved Knowledge for the question type (campus, student, classroom, age group, incident, etc.).
4. Use **`dbo.`** prefix on MSSQL when the schema uses `dbo`.
5. Prefer **explicit JOINs** documented in Knowledge over inventing FK column names.

## High-frequency hallucinations (use Knowledge instead)

| Topic | Do not guess | Read |
|--------|----------------|------|
| Campus / school name | `school_school.name`, `= N'Nido Campus'` | [campus_name_matching.md](campus_name_matching.md) — **`school_school.title`**, `LIKE N'%Nido%'` |
| Students at campus | `accounts_childprofile.campus_id` | [campus_student_counts.md](campus_student_counts.md) — `school_childschool` |
| Age group label | `ag.name`, `ag.age_group_name` | [campus_age_groups.md](campus_age_groups.md) — **`ag.title`** |
| Student birthdate | `birth_date`, `date_of_birth` | [student_queries.md](student_queries.md) — **`accounts_user.birthday`** |
| Classroom headcount | `general_post_classrooms` | [classroom_enrollment_counts.md](classroom_enrollment_counts.md) — `school_classroomchild` |
| Classroom roster | direct `accounts_childprofile` only | [classroom_roster_queries.md](classroom_roster_queries.md) |
| Closures / holidays | `school_term.school_id` | [campus_closures_and_calendars.md](campus_closures_and_calendars.md) |
| Student status labels | raw integers only | [student_status_reference.md](student_status_reference.md) |
| Observations | annual verification tables | [classroom_observations.md](classroom_observations.md) |
| Incidents | generic activity only | [student_incident_reports.md](student_incident_reports.md) |

## M2M and FK naming

Django/MSSQL names are **not** uniform. Examples:

| Table | Column | Not |
|--------|--------|-----|
| `school_school_age_groups` | `agegroup_id` | `age_group_id` |
| `school_classroom` | `age_group_id` | `agegroup_id` |

Always take FK column names from **schema context**, not from a sibling table’s pattern.

## When schema context is incomplete

- Use **fewer** columns (e.g. `id` + one known label column) rather than adding guessed display fields.
- Join only through keys that appear in schema or Knowledge.
- Do **not** substitute “logical” names (`name`, `label`, `description`) without verification.

## Agent behavior summary

1. **Never guess** — schema + Knowledge only.
2. **Check Knowledge** for the question domain (campus, student, age group, tuition, etc.) before emitting SQL.
3. **Match UVIMS naming** (`title` vs `name`, `birthday` vs `birth_date`, `LIKE` for campuses).
4. On conflict between intuition and a Knowledge file, follow **Knowledge**.
5. Prefer a correct, minimal query over a rich query with invented columns.

After new error patterns appear in logs, add or update a focused `.md` under `Knowledge/` and run `insightai-knowledge-sync --force`.
