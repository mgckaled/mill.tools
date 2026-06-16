"""Typed models for the local RAG layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChunkMeta:
    """Metadata for one embedded chunk (parallel to a row in the vector matrix).

    One ``ChunkMeta`` is stored per row of the vector store's matrix; index
    ``i`` in ``VectorStore.meta`` corresponds to row ``i`` of ``VectorStore.vectors``.
    The chunk text is kept here so retrieval can build the answer context without
    re-reading source files.
    """

    source_path: str  # the Library item the chunk came from
    kind: str  # "transcription" | "document" | ...
    mtime: float  # source mtime when embedded (drives incremental refresh)
    chunk_idx: int  # position of the chunk within its source document
    text: str  # the chunk text (kept for retrieval/context building)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk returned by retrieval, paired with its similarity score."""

    meta: ChunkMeta
    score: float  # cosine similarity in [-1, 1]; ~1.0 means near-identical


@dataclass(frozen=True, slots=True)
class AnswerResult:
    """A RAG answer plus the distinct source documents it cites."""

    text: str
    sources: list[Path]  # distinct source items cited, in first-seen order
