"""Tests for optional Knowledge excerpts in SQL prompts."""

from __future__ import annotations

from insightai.infrastructure.prompts.domain_context import format_domain_context_section


def test_format_domain_context_section_empty() -> None:
    assert format_domain_context_section(None) == ""
    assert format_domain_context_section("   ") == ""


def test_format_domain_context_section_with_text() -> None:
    out = format_domain_context_section("Rule one.")
    assert "Domain guidance" in out
    assert "Rule one." in out
