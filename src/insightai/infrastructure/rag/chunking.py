"""Text chunking for RAG ingestion (Phase 10.2)."""

from __future__ import annotations

import re

from insightai.domain.models.rag import DocumentChunk

_HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def chunk_document_text(
    *,
    source_path: str,
    text: str,
    title: str | None = None,
    chunk_size: int,
    chunk_overlap: int,
) -> list[DocumentChunk]:
    """
    Split document text into chunks.

    Markdown headings start new sections; oversized sections are windowed with overlap.
    """
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    sections = _split_markdown_sections(normalized)
    chunks: list[DocumentChunk] = []
    chunk_index = 0

    for section_title, section_body in sections:
        section_text = section_body.strip()
        if not section_text:
            continue
        windows = _window_text(section_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for window in windows:
            chunks.append(
                DocumentChunk(
                    source_path=source_path,
                    chunk_index=chunk_index,
                    text=window,
                    title=title,
                    section=section_title,
                ),
            )
            chunk_index += 1

    return chunks


def _split_markdown_sections(text: str) -> list[tuple[str | None, str]]:
    matches = list(_HEADER_PATTERN.finditer(text))
    if not matches:
        return [(None, text)]

    sections: list[tuple[str | None, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append((None, preamble))

    for index, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((title, body))

    return sections


def _window_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    if chunk_overlap >= chunk_size:
        msg = "chunk_overlap must be smaller than chunk_size."
        raise ValueError(msg)

    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        piece = text[start:end].strip()
        if piece:
            windows.append(piece)
        if end >= len(text):
            break
        start = end - chunk_overlap
    return windows
