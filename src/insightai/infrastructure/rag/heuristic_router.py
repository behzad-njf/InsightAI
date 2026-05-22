"""Heuristic SQL vs RAG query router (Phase 10.4)."""

from __future__ import annotations

import re

from insightai.domain.models.hybrid import QueryRouteKind, RouteClassification
from insightai.domain.ports.query_router import IQueryRouter

_SQL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bhow many\b",
        r"\bcount\b",
        r"\btotal\b",
        r"\bsum\b",
        r"\baverage\b",
        r"\bavg\b",
        r"\bminimum\b",
        r"\bmaximum\b",
        r"\boldest\b",
        r"\byoungest\b",
        r"\bbirthday\b",
        r"\bbirthdate\b",
        r"\bstudent(s)?\b",
        r"\btrend\b",
        r"\bover time\b",
        r"\bper (month|year|week|day|quarter)\b",
        r"\bgroup(ed)? by\b",
        r"\btop \d+\b",
        r"\bbottom \d+\b",
        r"\benrollment\b",
        r"\brevenue\b",
        r"\bmetric(s)?\b",
        r"\bcompare\b",
        r"\bbreakdown\b",
        r"\bdistribution\b",
        r"\bpercentage\b",
        r"\brate\b",
        r"\btable\b",
        r"\bquery\b",
        r"\bdata\b",
        r"\brows?\b",
        r"\bcolumn\b",
        r"\bactivity feedback\b",
        r"\bactivity\b.*\b(feedback|submitted|submission)\b",
        r"\b(feedback|submitted|submission)\b.*\bactivity\b",
        r"\b(last|latest|most recent)\b.*\b(activity|feedback|submitted)\b",
        r"\b(activity|feedback)\b.*\b(last|latest|most recent)\b",
        r"\bwhich students?\b.*\b(received|got|have)\b",
        r"\breceived\b.*\b(feedback|activity)\b",
        r"\bfor\s+[A-Za-z]+\s+[A-Za-z]+\b",  # e.g. for Jane Doe (named student lookup)
        r"\bincident(s)?\b",
        r"\bincident report(s)?\b",
        r"\bbehavioral\b",
        r"\b(last|latest)\b.*\b(incident|report)\b",
        r"\b(image|photo|picture)\b.*\b(incident|report)\b",
    )
)

_RAG_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bpolicy\b",
        r"\bpolicies\b",
        r"\bprocedure\b",
        r"\bhandbook\b",
        r"\bdocument\b",
        r"\bdocumentation\b",
        r"\bguideline(s)?\b",
        r"\bwhat is\b(?!.*\b(last|latest|most recent)\b)",
        r"\bwhat are\b(?!.*\b(last|latest|most recent)\b)",
        r"\bexplain\b",
        r"\bdescribe\b",
        r"\baccording to\b",
        r"\bin the (doc|guide|manual)\b",
        r"\bhelp text\b",
        r"\bcampus overview\b",
        r"\boverview\b",
        r"\bwhat is this\b",
        r"\bwhat is insightai\b",
        r"\bwhat does this system\b",
        r"\bpurpose of\b",
        r"\bdefinition\b",
        r"\bmean(s)?\b",
        r"\brequirement(s)?\b",
        r"\bcompliance\b",
        r"\bregulation\b",
        r"\bclosed\b",
        r"\bclosure\b",
        r"\bholiday(s)?\b",
        r"\bno school\b",
        r"\bcalendar\b",
        r"\bwhich days\b",
        r"\bwhen is\b.+\b(closed|close)\b",
        r"\bbreak\b",
    )
)

_BOTH_CONNECTORS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\band also\b",
        r"\bas well as\b",
        r"\baccording to .+ and\b",
        r"\bpolicy.+how many\b",
        r"\bhow many.+policy\b",
        r"\bdocument.+count\b",
        r"\bcount.+document\b",
    )
)


class HeuristicQueryRouter(IQueryRouter):
    """
    Fast keyword router for dev/tests and as the default when LLM routing is off.

    Defaults to SQL when signals are ambiguous (analytics-first product).
    """

    def classify(self, question: str) -> RouteClassification:
        text = question.strip()
        sql_signals = sum(1 for pattern in _SQL_PATTERNS if pattern.search(text))
        rag_signals = sum(1 for pattern in _RAG_PATTERNS if pattern.search(text))
        both_connector = any(pattern.search(text) for pattern in _BOTH_CONNECTORS)

        if both_connector or (sql_signals >= 1 and rag_signals >= 1):
            route = QueryRouteKind.BOTH
            confidence = min(0.95, 0.55 + 0.1 * (sql_signals + rag_signals))
            rationale = "Question references both analytics and document knowledge."
        elif rag_signals > sql_signals and rag_signals >= 1:
            route = QueryRouteKind.RAG
            confidence = min(0.9, 0.5 + 0.1 * rag_signals)
            rationale = "Question reads like a document or policy lookup."
        elif sql_signals >= 1:
            route = QueryRouteKind.SQL
            confidence = min(0.9, 0.5 + 0.1 * sql_signals)
            rationale = "Question reads like an analytics / database query."
        else:
            route = QueryRouteKind.SQL
            confidence = 0.45
            rationale = "No strong document signals; defaulting to SQL analytics."

        return RouteClassification(
            route=route,
            confidence=confidence,
            rationale=rationale,
            sql_signals=sql_signals,
            rag_signals=rag_signals,
        )
