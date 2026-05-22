"""Unit tests for semantic CLI helpers (Phase 11.9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from insightai.cli.semantic import main_test_match, main_validate, validate_semantic_catalog
from insightai.domain.models.database import DatabaseKind

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SEMANTIC_DIR = PROJECT_ROOT / "tests" / "fixtures" / "semantic"
EDUCATION_DIR = PROJECT_ROOT / "config" / "semantic" / "examples" / "education"


def test_validate_semantic_catalog_fixture_ok() -> None:
    errors = validate_semantic_catalog(FIXTURE_SEMANTIC_DIR, dialect=DatabaseKind.MSSQL)
    assert errors == []


def test_education_examples_validate_ok() -> None:
    errors = validate_semantic_catalog(EDUCATION_DIR, dialect=DatabaseKind.MSSQL)
    assert errors == []


def test_main_validate_education_exit_zero() -> None:
    assert main_validate(["--path", str(EDUCATION_DIR)]) == 0


def test_main_test_match_education_classroom_question() -> None:
    code = main_test_match(
        [
            "--path",
            str(EDUCATION_DIR),
            "--question",
            "How many kids are in the Example classroom?",
        ],
    )
    assert code == 0


def test_main_test_match_no_match_exit_two() -> None:
    code = main_test_match(
        [
            "--path",
            str(EDUCATION_DIR),
            "--question",
            "totally unrelated inventory question",
        ],
    )
    assert code == 2


def test_validate_reports_invalid_sql(tmp_path: Path) -> None:
    (tmp_path / "trusted_metrics.yaml").write_text(
        "metrics:\n  - id: bad\n    title: Bad\n    sql: SELECT FROM\n",
        encoding="utf-8",
    )
    (tmp_path / "example_queries.yaml").write_text("example_queries: []\n", encoding="utf-8")
    errors = validate_semantic_catalog(tmp_path, dialect=DatabaseKind.MSSQL)
    assert errors
    assert main_validate(["--path", str(tmp_path)]) == 1
