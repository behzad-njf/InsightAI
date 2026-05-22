"""Unit tests for governance validate CLI (Phase 12.3)."""

from __future__ import annotations

from pathlib import Path

from insightai.cli.governance import main_validate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "governance"
CONFIG_DIR = PROJECT_ROOT / "config" / "governance"
EDUCATION_DIR = PROJECT_ROOT / "config" / "governance" / "examples" / "education"


def test_main_validate_fixture_exit_zero() -> None:
    assert main_validate(["--path", str(FIXTURE_DIR)]) == 0


def test_main_validate_config_dir_exit_zero() -> None:
    assert main_validate(["--path", str(CONFIG_DIR)]) == 0


def test_main_validate_education_example_exit_zero() -> None:
    assert main_validate(["--path", str(EDUCATION_DIR)]) == 0


def test_main_validate_invalid_exit_one(tmp_path: Path) -> None:
    (tmp_path / "policies.yaml").write_text("roles: not_a_map\n", encoding="utf-8")
    assert main_validate(["--path", str(tmp_path)]) == 1
