"""Infer business domain from table name (django-db-schema-doc convention)."""

from __future__ import annotations

FRAMEWORK_PREFIXES = (
    "django_",
    "auth_",
    "django_celery_beat_",
    "jet_",
    "south_",
)


def infer_domain(table_name: str) -> str:
    lowered = table_name.lower()
    for prefix in FRAMEWORK_PREFIXES:
        if lowered.startswith(prefix):
            return "django_system"
    if "_" in lowered:
        return lowered.split("_", 1)[0]
    return "other"
