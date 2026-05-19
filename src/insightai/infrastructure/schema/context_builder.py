"""Build LLM-ready schema context from a user question."""

from __future__ import annotations

import re

from insightai.domain.models.schema import (
    JoinPatternMetadata,
    SchemaContextRequest,
    SchemaContextResult,
    SchemaTableContext,
    TableMetadata,
)
from insightai.infrastructure.schema.registry import SchemaRegistry

# Business terms → domain prefixes (heuristic v1)
_TERM_DOMAIN_MAP: dict[str, list[str]] = {
    "child": ["accounts", "school"],
    "children": ["accounts", "school"],
    "parent": ["accounts"],
    "staff": ["accounts", "staff"],
    "classroom": ["school"],
    "class": ["school"],
    "school": ["school"],
    "attendance": ["school"],
    "invoice": ["financial"],
    "payment": ["financial"],
    "billing": ["financial"],
    "chat": ["chat"],
    "message": ["chat"],
    "health": ["health"],
    "medical": ["health"],
    "learning": ["learning"],
    "curriculum": ["learning"],
    "subscription": ["subscriptions"],
    "user": ["accounts"],
    "enrollment": ["school", "financial"],
    "term": ["school"],
}

# Map terms → likely table name substrings
_TERM_TABLE_HINTS: dict[str, list[str]] = {
    "child": ["childprofile", "classroomchild", "childschool"],
    "classroom": ["classroom"],
    "attendance": ["attendance"],
    "invoice": ["invoice"],
    "staff": ["staff", "schoolstaff", "classroomstaff"],
}


class SchemaContextBuilder:
    """Select relevant tables and join patterns for a natural language question."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry

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
        self._boost_domain_tables(tokens, scores, reasons)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        selected_names = [name for name, _ in ranked[: request.max_tables]]

        if not selected_names:
            selected_names = [table.name for table in self._registry.list_hub_tables()[:5]]

        selected_tables: list[SchemaTableContext] = []
        for name in selected_names:
            selected = self._registry.get_table(name)
            if selected is None:
                continue
            selected_tables.append(
                SchemaTableContext(
                    table=selected,
                    relevance_score=scores.get(name, 0.0),
                    match_reasons=reasons.get(name, []),
                )
            )

        join_patterns = self._match_join_patterns(question)
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

        if table.name in question_lower:
            score += 10.0
            table_reasons.append("table name in question")

        name_parts = name_lower.replace("_", " ").split()
        for part in name_parts:
            if len(part) > 2 and part in tokens:
                score += 3.0
                table_reasons.append(f"token match: {part}")

        for token in tokens:
            if len(token) > 3 and token in name_lower:
                score += 2.0
                table_reasons.append(f"substring match: {token}")

        if table.is_hub:
            score += 1.5
            table_reasons.append("hub table")

        if table.incoming_fk_count and table.incoming_fk_count >= 10:
            score += 0.5

        return score, table_reasons

    def _boost_hub_tables(
        self,
        scores: dict[str, float],
        reasons: dict[str, list[str]],
    ) -> None:
        for table in self._registry.list_hub_tables():
            if table.name not in scores:
                scores[table.name] = 2.0
                reasons[table.name] = ["included as hub table"]

    def _boost_domain_tables(
        self,
        tokens: set[str],
        scores: dict[str, float],
        reasons: dict[str, list[str]],
    ) -> None:
        active_domains: set[str] = set()
        for token in tokens:
            for term, domains in _TERM_DOMAIN_MAP.items():
                if term in token or token in term:
                    active_domains.update(domains)

        for domain in active_domains:
            for table in self._registry.list_tables_by_domain(domain):
                scores[table.name] = scores.get(table.name, 0.0) + 1.0
                reasons.setdefault(table.name, []).append(f"domain boost: {domain}")

        for token in tokens:
            hints = _TERM_TABLE_HINTS.get(token, [])
            for table in self._registry.list_tables():
                if any(hint in table.name for hint in hints):
                    scores[table.name] = scores.get(table.name, 0.0) + 2.5
                    reasons.setdefault(table.name, []).append(f"hint match: {token}")

    def _match_join_patterns(self, question: str) -> list[JoinPatternMetadata]:
        question_lower = question.lower()
        matched: list[JoinPatternMetadata] = []
        for pattern in self._registry.document.join_patterns:
            title_lower = pattern.title.lower()
            if any(word in question_lower for word in title_lower.split() if len(word) > 3):
                matched.append(pattern)
        if (
            not matched
            and self._registry.document.join_patterns
            and ("child" in question_lower or "classroom" in question_lower)
        ):
            # Default: child in classroom pattern for school/child questions
            for pattern in self._registry.document.join_patterns:
                if "classroom" in pattern.title.lower():
                    matched.append(pattern)
                    break
        return matched[:3]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        raw = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())
        return {token for token in raw if len(token) > 2}

    @staticmethod
    def _render_markdown(
        *,
        question: str,
        tables: list[SchemaTableContext],
        join_patterns: list[JoinPatternMetadata],
    ) -> str:
        lines = [
            "## Schema context (CampusMetrics / MSSQL — read-only)",
            f"User question: {question}",
            "",
            "### Relevant tables",
        ]

        hub_tables = [ctx for ctx in tables if ctx.table.is_hub]
        other_tables = [ctx for ctx in tables if not ctx.table.is_hub]

        if hub_tables:
            lines.append("")
            lines.append("#### Hub tables (join here first)")
            for ctx in hub_tables:
                lines.extend(_format_table(ctx))

        if other_tables:
            lines.append("")
            lines.append("#### Related tables")
            for ctx in other_tables:
                lines.extend(_format_table(ctx))

        if join_patterns:
            lines.append("")
            lines.append("### Documented join patterns")
            for pattern in join_patterns:
                lines.append(f"#### {pattern.title}")
                lines.append("```sql")
                lines.append(pattern.sql)
                lines.append("```")

        lines.append("")
        lines.append("_Use exact table/column names above. Only generate SELECT queries._")
        return "\n".join(lines)


def _format_table(ctx: SchemaTableContext) -> list[str]:
    table = ctx.table
    lines = [f"- **{table.name}** (domain: `{table.domain}`, schema: `{table.schema_name}`)"]
    if table.hub_role:
        lines.append(f"  - Role: {table.hub_role}")
    if table.primary_key:
        lines.append(f"  - PK: `{table.primary_key}`")
    if ctx.match_reasons:
        lines.append(f"  - Matched because: {', '.join(ctx.match_reasons)}")

    if table.columns:
        col_preview = table.columns[:12]
        col_text = ", ".join(f"`{c.name}`" for c in col_preview)
        if len(table.columns) > len(col_preview):
            col_text += f", ... (+{len(table.columns) - len(col_preview)} more)"
        lines.append(f"  - Columns: {col_text}")

    if table.foreign_keys:
        fk_preview = table.foreign_keys[:6]
        for fk in fk_preview:
            lines.append(f"  - FK: `{fk.column}` → `{fk.parent_table}.{fk.parent_column}`")
        if len(table.foreign_keys) > len(fk_preview):
            lines.append(f"  - ... (+{len(table.foreign_keys) - len(fk_preview)} more FKs)")

    return lines
