"""Shared fixtures for SQL generation tests (Phase 3.6)."""

from __future__ import annotations

import json

# --- Classroom / children scenario (matches Phase 2 acceptance examples) ---

CLASSROOM_QUESTION = "How many children are enrolled in each classroom?"

CLASSROOM_SCHEMA_CONTEXT = """## Schema context (CampusMetrics / MSSQL — read-only)
User question: How many children are enrolled in each classroom?

### Relevant tables

#### Hub tables (join here first)
- **accounts_user** (domain: `accounts`, schema: `dbo`)
  - PK: `id`
  - Columns: `id`, `email`, `first_name`, `last_name`

#### Related tables
- **school_classroom** (domain: `school`, schema: `dbo`)
  - PK: `id`
  - Columns: `id`, `name`, `school_id`
  - FK: `school_id` → `school_school.id`
- **school_classroomchild** (domain: `school`, schema: `dbo`)
  - PK: `id`
  - Columns: `id`, `child_id`, `classroom_id`, `term_id`
  - FK: `child_id` → `accounts_user.id`
  - FK: `classroom_id` → `school_classroom.id`

### Documented join patterns
#### Child in classroom
```sql
SELECT ...
FROM school_classroomchild cc
INNER JOIN accounts_user u ON u.id = cc.child_id
INNER JOIN school_classroom c ON c.id = cc.classroom_id
```

_Use exact table/column names above. Only generate SELECT queries._
"""

CLASSROOM_TABLE_NAMES = [
    "accounts_user",
    "school_classroom",
    "school_classroomchild",
]

CLASSROOM_SQL = (
    "SELECT TOP 100 c.id AS classroom_id, COUNT(cc.id) AS child_count "
    "FROM school_classroom c "
    "INNER JOIN school_classroomchild cc ON cc.classroom_id = c.id "
    "INNER JOIN accounts_user u ON u.id = cc.child_id "
    "GROUP BY c.id"
)

CLASSROOM_LLM_PAYLOAD = {
    "sql": CLASSROOM_SQL,
    "explanation": "Counts children per classroom using classroomchild enrollments.",
    "confidence": "high",
    "uncertainty_notes": None,
    "tables_used": ["school_classroom", "school_classroomchild", "accounts_user"],
}

CLASSROOM_LLM_JSON = json.dumps(CLASSROOM_LLM_PAYLOAD)

# --- Insufficient schema (model refuses with empty SQL) ---

INSUFFICIENT_SCHEMA_CONTEXT = """## Schema context (CampusMetrics / MSSQL — read-only)
### Relevant tables
- **reference_information_country** (domain: `reference`, schema: `dbo`)
  - Columns: `id`, `name`
"""

INSUFFICIENT_LLM_JSON = json.dumps(
    {
        "sql": "",
        "explanation": "The provided schema does not include weather tables.",
        "confidence": "low",
        "uncertainty_notes": "No weather or forecast tables in context.",
        "tables_used": [],
    }
)

# --- Invalid / unsafe SQL (must be rejected by post-processor) ---

NON_SELECT_SQL_CASES: list[tuple[str, str]] = [
    ("delete", "DELETE FROM accounts_user WHERE id = 1"),
    ("insert", "INSERT INTO accounts_user (email) VALUES ('x@y.z')"),
    ("drop", "DROP TABLE accounts_user"),
    ("multi_statement", "SELECT 1; DELETE FROM accounts_user"),
]
