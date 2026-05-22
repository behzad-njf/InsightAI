"""Bootstrap app database revision chain (Phase 16.1).

Revision ID: 001_bootstrap
Revises:
Create Date: 2026-05-22

ORM tables (api_keys, feedback, …) are added in later Phase 16 steps.
"""

from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "001_bootstrap"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: establishes Alembic history before 16.2+ tables."""


def downgrade() -> None:
    """No-op."""
