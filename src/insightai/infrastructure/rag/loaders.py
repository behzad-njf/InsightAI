"""Load source documents for RAG ingestion (Phase 10.2)."""

from __future__ import annotations

from pathlib import Path

from insightai.domain.exceptions import InsightAIError

SUPPORTED_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
SUPPORTED_PDF_SUFFIXES = {".pdf"}


class DocumentLoadError(InsightAIError):
    """Failed to read or parse a source document."""


def discover_document_paths(
    input_path: Path,
    *,
    recursive: bool,
) -> list[Path]:
    """Collect supported files from a file or directory path."""
    path = input_path.resolve()
    if path.is_file():
        return [path] if _is_supported_file(path) else []

    if not path.is_dir():
        msg = f"Input path does not exist: {input_path}"
        raise DocumentLoadError(msg)

    pattern = "**/*" if recursive else "*"
    files = [candidate for candidate in path.glob(pattern) if candidate.is_file()]
    return sorted(file for file in files if _is_supported_file(file))


def load_document_text(path: Path) -> tuple[str, str | None]:
    """
    Return ``(text, title)`` for a supported document file.

    Raises:
        DocumentLoadError: Unsupported type or parse failure.
    """
    resolved = path.resolve()
    suffix = resolved.suffix.lower()

    if suffix in SUPPORTED_TEXT_SUFFIXES:
        text = resolved.read_text(encoding="utf-8")
        return text, resolved.stem

    if suffix in SUPPORTED_PDF_SUFFIXES:
        return _load_pdf_text(resolved), resolved.stem

    msg = f"Unsupported document type: {resolved.suffix}"
    raise DocumentLoadError(msg)


def _is_supported_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in SUPPORTED_TEXT_SUFFIXES or suffix in SUPPORTED_PDF_SUFFIXES


def _load_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        msg = "PDF ingestion requires optional dependency: pip install 'insightai[rag]'"
        raise DocumentLoadError(msg) from exc

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        msg = f"Failed to read PDF {path}: {exc}"
        raise DocumentLoadError(msg) from exc

    return "\n\n".join(part.strip() for part in pages if part.strip())
