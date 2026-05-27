"""Schema metadata models — from markdown or django-db-schema-doc JSON exports."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryExampleMetadata(BaseModel):
    """SQL or ORM example bundled with a table (django-db-schema-doc)."""

    kind: str = Field(description="sql or orm")
    title: str
    code: str
    related_tables: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class ColumnMetadata(BaseModel):
    """Column definition from per-table section."""

    name: str
    data_type: str
    nullable: bool | None = None
    is_primary_key: bool = False
    default: str | None = None
    ordinal: int | None = None

    model_config = {"frozen": True}


class ForeignKeyMetadata(BaseModel):
    """Outgoing foreign key on a table."""

    column: str
    parent_table: str
    parent_column: str
    on_delete: str | None = None
    on_update: str | None = None

    model_config = {"frozen": True}


class TableMetadata(BaseModel):
    """Single table in the customer database schema."""

    name: str
    schema_name: str = "dbo"
    domain: str | None = None
    primary_key: str | None = None
    description: str | None = None
    django_model: str | None = Field(
        default=None,
        description="Django app_label.model_name when exported from django-db-schema-doc.",
    )
    columns: list[ColumnMetadata] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyMetadata] = Field(default_factory=list)
    query_examples: list[QueryExampleMetadata] = Field(default_factory=list)
    incoming_fk_count: int | None = None
    approx_row_count: int | None = None
    is_hub: bool = False
    hub_role: str | None = None

    model_config = {"frozen": True}

    @property
    def column_names(self) -> list[str]:
        return [column.name for column in self.columns]


class DomainMetadata(BaseModel):
    """Business domain grouping (school, accounts, ...)."""

    name: str
    table_count: int | None = None
    description: str | None = None

    model_config = {"frozen": True}


class JoinPatternMetadata(BaseModel):
    """Documented SQL join pattern from schema doc §2.3."""

    title: str
    sql: str

    model_config = {"frozen": True}


class SchemaDocument(BaseModel):
    """Full parsed schema artifact."""

    source_path: str
    format: str = Field(
        default="legacy_markdown",
        description="legacy_markdown | django_db_schema_doc_markdown | django_db_schema_doc_json",
    )
    domains: list[DomainMetadata] = Field(default_factory=list)
    tables: list[TableMetadata] = Field(default_factory=list)
    join_patterns: list[JoinPatternMetadata] = Field(default_factory=list)
    hub_table_names: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}

    @property
    def table_count(self) -> int:
        return len(self.tables)


class SchemaContextRequest(BaseModel):
    """Input for schema context retrieval."""

    question: str = Field(min_length=1)
    max_tables: int = Field(default=12, ge=1, le=50)

    model_config = {"frozen": True}


class SchemaTableContext(BaseModel):
    """One table included in generated context."""

    table: TableMetadata
    relevance_score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class SchemaContextResult(BaseModel):
    """Output of schema context building for LLM prompts (Phase 3)."""

    question: str
    tables: list[SchemaTableContext]
    join_patterns: list[JoinPatternMetadata]
    context_markdown: str
    table_names: list[str]

    model_config = {"frozen": True}
