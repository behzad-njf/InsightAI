"""Persist ingested RAG chunks to JSONL + manifest (Phase 10.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from insightai.domain.models.rag import IngestedChunkRecord, RAGIndexManifest


def write_jsonl_index(
    output_path: Path,
    records: list[IngestedChunkRecord],
) -> None:
    """Write one JSON object per line (UTF-8)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json())
            handle.write("\n")


def write_manifest(
    output_path: Path,
    manifest: RAGIndexManifest,
) -> None:
    """Write ``manifest.json`` next to the JSONL index file."""
    manifest_path = manifest_path_for(output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )


def manifest_path_for(output_path: Path) -> Path:
    return output_path.with_name("manifest.json")


def load_manifest(output_path: Path) -> RAGIndexManifest:
    raw = manifest_path_for(output_path).read_text(encoding="utf-8")
    return RAGIndexManifest.model_validate_json(raw)


def iter_index_records(output_path: Path) -> list[IngestedChunkRecord]:
    records: list[IngestedChunkRecord] = []
    with output_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(IngestedChunkRecord.model_validate_json(line))
    return records


def utc_now() -> datetime:
    return datetime.now(UTC)
