"""Provider-specific completion token caps (Groq compound request limits)."""

from __future__ import annotations

# Groq ``groq/compound`` returns HTTP 413 when max_tokens is too large for the
# agentic stack (empirically ~2048+ with a typical SQL-generation prompt).
_COMPOUND_MAX_COMPLETION_TOKENS = 1024


def cap_completion_tokens(model: str, requested: int) -> int:
    """
    Lower ``max_tokens`` for models with strict request-size limits.

    ``groq/compound`` is used for agentic tooling; large ``max_tokens`` values
    can trigger ``413 Request Entity Too Large`` even with modest prompts.
    """
    if requested < 1:
        return 1
    if "compound" in model.lower():
        return min(requested, _COMPOUND_MAX_COMPLETION_TOKENS)
    return requested
