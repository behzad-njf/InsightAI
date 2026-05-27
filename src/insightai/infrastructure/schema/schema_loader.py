"""Load SchemaDocument from configured JSON and/or markdown paths."""

from __future__ import annotations

from pathlib import Path

from insightai.domain.exceptions import SchemaNotFoundError
from insightai.domain.models.schema import SchemaDocument
from insightai.infrastructure.config.settings import Settings, get_settings
from insightai.infrastructure.schema.json_parser import SchemaJsonParser
from insightai.infrastructure.schema.markdown_parser import SchemaMarkdownParser


def resolve_schema_cache_path(settings: Settings | None = None) -> Path:
    """Path used for schema context cache fingerprints (JSON preferred when configured)."""
    settings = settings or get_settings()
    if settings.schema_uses_json():
        path = settings.schema_json_absolute
        if path.is_file():
            return path
    path = settings.schema_markdown_absolute
    if path.is_file():
        return path
    msg = (
        "No schema source found. Set INSIGHTAI_SCHEMA_JSON_PATH and/or "
        "INSIGHTAI_SCHEMA_MARKDOWN_PATH to files from django-db-schema-doc."
    )
    raise SchemaNotFoundError(msg)


def load_schema_document(settings: Settings | None = None) -> SchemaDocument:
    """Load schema from JSON (preferred) or markdown according to settings."""
    settings = settings or get_settings()

    if settings.schema_uses_json():
        json_path = settings.schema_json_absolute
        if json_path.is_file():
            document = SchemaJsonParser().parse_file(json_path)
            examples_path = settings.schema_examples_json_absolute
            if examples_path is not None and examples_path.is_file():
                document = SchemaJsonParser().merge_examples_file(document, examples_path)
            return document
        if settings.schema_source == "json":
            msg = f"Schema JSON not found: {json_path}"
            raise SchemaNotFoundError(msg)

    markdown_path = settings.schema_markdown_absolute
    if not markdown_path.is_file():
        msg = f"Schema markdown not found: {markdown_path}"
        raise SchemaNotFoundError(msg)
    return SchemaMarkdownParser().parse_file(markdown_path)
