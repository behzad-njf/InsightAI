"""Schema-driven context selection — no hardcoded table or domain names."""

from __future__ import annotations

import re
from collections import defaultdict

from insightai.domain.models.schema import (
    JoinPatternMetadata,
    QueryExampleMetadata,
    SchemaContextRequest,
    SchemaContextResult,
    SchemaTableContext,
    TableMetadata,
)
from insightai.infrastructure.schema.registry import SchemaRegistry

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "what",
        "which",
        "how",
        "many",
        "show",
        "list",
        "all",
        "are",
        "was",
        "were",
        "have",
        "has",
        "into",
        "about",
        "when",
        "where",
        "each",
        "per",
    },
)


class SchemaContextBuilder:
    """
    Select tables and join patterns using only parsed ``SchemaDocument`` metadata.

    Works with any schema export (django-db-schema-doc JSON/markdown or hand-written
    markdown). Swap ``schema.json`` / ``database_schema.md`` per deployment — no code changes.

    Optional extended heuristics: set ``INSIGHTAI_SCHEMA_CONTEXT_PLUGIN`` to a class in
    ``context/plugins/`` (see ``context/README.md``).
    """

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry
        self._domain_names = {domain.name.lower() for domain in registry.document.domains}
        self._token_to_tables = self._build_token_index()

    def build(self, request: SchemaContextRequest) -> SchemaContextResult:
        question = request.question.strip()
        tokens = self._tokenize(question)
        scores: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}

        for table in self._registry.list_tables():
            score, table_reasons = self._score_table(table, tokens, question)
            if score > 0:
                scores[table.name] = score
                reasons[table.name] = table_reasons

        self._boost_hub_tables(scores, reasons)
        self._boost_domains_from_registry(tokens, scores, reasons)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        selected_names = [name for name, _ in ranked[: request.max_tables]]

        if not selected_names:
            selected_names = [table.name for table in self._registry.list_hub_tables()[:5]]

        selected_names = self._expand_fk_neighbors(
            selected_names,
            max_tables=request.max_tables,
            scores=scores,
            reasons=reasons,
        )

        selected_tables: list[SchemaTableContext] = []
        for name in selected_names:
            table = self._registry.get_table(name)
            if table is None:
                continue
            selected_tables.append(
                SchemaTableContext(
                    table=table,
                    relevance_score=scores.get(name, 0.0),
                    match_reasons=reasons.get(name, []),
                )
            )

        join_patterns = self._match_join_patterns(question, selected_names)
        context_markdown = self._render_markdown(
            question=question,
            tables=selected_tables,
            join_patterns=join_patterns,
        )

        return SchemaContextResult(
            question=question,
            tables=selected_tables,
            join_patterns=join_patterns,
            context_markdown=context_markdown,
            table_names=[ctx.table.name for ctx in selected_tables],
        )

    def _build_token_index(self) -> dict[str, set[str]]:
        index: dict[str, set[str]] = defaultdict(set)
        for table in self._registry.list_tables():
            for token in self._table_name_tokens(table.name):
                index[token].add(table.name)
            if table.domain:
                index[table.domain.lower()].add(table.name)
            for column in table.columns:
                if len(column.name) > 2:
                    index[column.name.lower()].add(table.name)
            if table.description:
                for token in self._tokenize(table.description):
                    index[token].add(table.name)
            for example in table.query_examples:
                for related in example.related_tables:
                    for token in self._table_name_tokens(related):
                        index[token].add(table.name)
        return index

    def _score_table(
        self,
        table: TableMetadata,
        tokens: set[str],
        question: str,
    ) -> tuple[float, list[str]]:
        score = 0.0
        table_reasons: list[str] = []
        name_lower = table.name.lower()
        question_lower = question.lower()

        if table.name in question_lower or name_lower in question_lower:
            score += 10.0
            table_reasons.append("table name in question")

        for token in tokens:
            if token in self._token_to_tables and table.name in self._token_to_tables[token]:
                score += 2.5
                table_reasons.append(f"token index: {token}")

        name_parts = name_lower.replace("_", " ").split()
        for part in name_parts:
            if len(part) > 2 and part in tokens:
                score += 3.0
                table_reasons.append(f"name part: {part}")

        for token in tokens:
            if len(token) > 3 and token in name_lower:
                score += 2.0
                table_reasons.append(f"substring: {token}")

        if table.domain and table.domain.lower() in tokens:
            score += 2.0
            table_reasons.append(f"domain token: {table.domain}")

        if table.is_hub:
            score += 1.5
            table_reasons.append("hub table")

        if table.incoming_fk_count and table.incoming_fk_count >= 5:
            score += 0.5
            table_reasons.append("high FK in-degree")

        return score, table_reasons

    def _boost_hub_tables(
        self,
        scores: dict[str, float],
        reasons: dict[str, list[str]],
    ) -> None:
        for table in self._registry.list_hub_tables()[:8]:
            if table.name not in scores:
                scores[table.name] = 1.5
                reasons[table.name] = ["hub table default"]

    def _boost_domains_from_registry(
        self,
        tokens: set[str],
        scores: dict[str, float],
        reasons: dict[str, list[str]],
    ) -> None:
        for token in tokens:
            if token not in self._domain_names:
                continue
            for table in self._registry.list_tables_by_domain(token):
                scores[table.name] = scores.get(table.name, 0.0) + 1.5
                reasons.setdefault(table.name, []).append(f"domain match: {token}")

    def _expand_fk_neighbors(
        self,
        selected_names: list[str],
        *,
        max_tables: int,
        scores: dict[str, float],
        reasons: dict[str, list[str]],
    ) -> list[str]:
        """Add one-hop FK parents for top-scoring tables so joins are possible."""
        names = list(selected_names)
        seed = names[: min(5, len(names))]
        for table_name in seed:
            table = self._registry.get_table(table_name)
            if table is None:
                continue
            for fk in table.foreign_keys:
                parent = fk.parent_table
                if parent not in names and self._registry.get_table(parent) is not None:
                    names.append(parent)
                    scores[parent] = max(scores.get(parent, 0.0), 1.0)
                    reasons.setdefault(parent, []).append(
                        f"FK neighbor: {table_name}.{fk.column}",
                    )
        deduped: list[str] = []
        for name in names:
            if name not in deduped:
                deduped.append(name)
        return deduped[:max_tables]

    def _match_join_patterns(
        self,
        question: str,
        selected_table_names: list[str],
    ) -> list[JoinPatternMetadata]:
        question_lower = question.lower()
        tokens = self._tokenize(question)
        selected_lower = {name.lower() for name in selected_table_names}
        matched: list[tuple[float, JoinPatternMetadata]] = []

        for pattern in self._registry.document.join_patterns:
            title_lower = pattern.title.lower()
            sql_lower = pattern.sql.lower()
            score = 0.0
            if any(token in title_lower or token in sql_lower for token in tokens if len(token) > 3):
                score += 2.0
            if any(table in title_lower or table in sql_lower for table in selected_lower):
                score += 3.0
            if "join" in question_lower and "join" in title_lower:
                score += 2.0
            if score > 0:
                matched.append((score, pattern))

        matched.sort(key=lambda item: item[0], reverse=True)
        return [pattern for _, pattern in matched[:3]]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        raw = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())
        return {token for token in raw if len(token) > 2 and token not in _STOPWORDS}

    @staticmethod
    def _table_name_tokens(table_name: str) -> set[str]:
        parts = table_name.lower().replace("_", " ").split()
        return {part for part in parts if len(part) > 2}

    @staticmethod
    def _render_markdown(
        *,
        question: str,
        tables: list[SchemaTableContext],
        join_patterns: list[JoinPatternMetadata],
    ) -> str:
        doc_format = "database"
        lines = [
            "## Schema context (read-only)",
            f"Source format: `{doc_format}` — use only tables and columns listed below.",
            f"User question: {question}",
            "",
            "### Relevant tables",
        ]

        hub_tables = [ctx for ctx in tables if ctx.table.is_hub]
        other_tables = [ctx for ctx in tables if not ctx.table.is_hub]

        if hub_tables:
            lines.append("")
            lines.append("#### Hub tables (referenced by many FKs)")
            for ctx in hub_tables:
                lines.extend(_format_table(ctx))

        if other_tables:
            lines.append("")
            lines.append("#### Other tables")
            for ctx in other_tables:
                lines.extend(_format_table(ctx))

        if join_patterns:
            lines.append("")
            lines.append("### Suggested join patterns")
            for pattern in join_patterns:
                lines.append(f"**{pattern.title}**")
                lines.append("```sql")
                lines.append(pattern.sql)
                lines.append("```")

        lines.append("")
        lines.append(
            "_Use exact table and column names from this context. "
            "Domain-specific rules may also appear in Knowledge/ when configured._"
        )
        return "\n".join(lines)


def _format_table(ctx: SchemaTableContext) -> list[str]:
    table = ctx.table
    lines = [f"- **{table.name}** (domain: `{table.domain}`, schema: `{table.schema_name}`)"]
    if table.django_model:
        lines.append(f"  - Django model: `{table.django_model}`")
    if table.description:
        snippet = table.description.replace("\n", " ").strip()
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        lines.append(f"  - Description: {snippet}")
    if table.primary_key:
        lines.append(f"  - PK: `{table.primary_key}`")
    if ctx.match_reasons:
        lines.append(f"  - Matched because: {', '.join(ctx.match_reasons)}")

    if table.columns:
        preview = [column.name for column in table.columns[:12]]
        col_text = ", ".join(f"`{name}`" for name in preview)
        if len(table.columns) > len(preview):
            col_text += f", ... (+{len(table.columns) - len(preview)} more)"
        lines.append(f"  - Columns: {col_text}")

    sql_examples = [ex for ex in table.query_examples if ex.kind == "sql"][:2]
    if sql_examples:
        lines.append("  - Example SQL:")
        for example in sql_examples:
            lines.extend(_format_query_example(example))

    if table.foreign_keys:
        for fk in table.foreign_keys[:6]:
            lines.append(f"  - FK: `{fk.column}` → `{fk.parent_table}.{fk.parent_column}`")
        if len(table.foreign_keys) > 6:
            lines.append(f"  - ... (+{len(table.foreign_keys) - 6} more FKs)")

    return lines


def _format_query_example(example: QueryExampleMetadata) -> list[str]:
    code = example.code.strip()
    if not code:
        return []
    return [
        f"    - *{example.title}*:",
        "    ```sql",
        *[f"    {line}" for line in code.splitlines()],
        "    ```",
    ]
