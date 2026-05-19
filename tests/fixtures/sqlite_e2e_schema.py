"""SQLite schema + seed data for Phase 5.4 end-to-end integration tests."""

from __future__ import annotations

import json

from sqlalchemy import Engine, text

# SQLite-compatible version of classroom aggregate (no TOP).
CLASSROOM_SQL_SQLITE = (  # noqa: E501
    "SELECT c.id AS classroom_id, c.name AS classroom_name, COUNT(cc.id) AS child_count "
    "FROM school_classroom c "
    "INNER JOIN school_classroomchild cc ON cc.classroom_id = c.id "
    "INNER JOIN accounts_user u ON u.id = cc.child_id "
    "GROUP BY c.id, c.name "
    "ORDER BY c.id"
)

CLASSROOM_SQLITE_LLM_JSON = json.dumps(
    {
        "sql": CLASSROOM_SQL_SQLITE,
        "explanation": "Counts children per classroom using classroomchild enrollments.",
        "confidence": "high",
        "tables_used": ["school_classroom", "school_classroomchild", "accounts_user"],
    }
)


def seed_classroom_sqlite(engine: Engine) -> None:
    """Create minimal CampusMetrics-like tables and rows for classroom count queries."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE accounts_user (
                    id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL,
                    first_name TEXT,
                    last_name TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE school_classroom (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    school_id INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE school_classroomchild (
                    id INTEGER PRIMARY KEY,
                    child_id INTEGER NOT NULL,
                    classroom_id INTEGER NOT NULL,
                    term_id INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO accounts_user (id, email, first_name, last_name) VALUES
                (1, 'child1@test.com', 'Ada', 'Lovelace'),
                (2, 'child2@test.com', 'Grace', 'Hopper'),
                (3, 'child3@test.com', 'Alan', 'Turing')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO school_classroom (id, name, school_id) VALUES
                (10, 'Room A', 1),
                (20, 'Room B', 1)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO school_classroomchild (id, child_id, classroom_id, term_id) VALUES
                (100, 1, 10, 1),
                (101, 2, 10, 1),
                (102, 3, 20, 1)
                """
            )
        )
