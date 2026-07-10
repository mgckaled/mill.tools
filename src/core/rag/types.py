"""Typed models for the local RAG layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple


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


class RetrievalResult(NamedTuple):
    """``retriever.retrieve()``'s return value: the final hits plus the best
    dense coverage found anywhere in the scope-respecting candidate set.

    ``pool_max_score`` is *not* necessarily ``max(h.score for h in hits)``:
    MMR diversification (Fase 3, PLANO_CONVERSA_MULTITURNO.md) can trade the
    single best-matching chunk away for variety, so the out-of-scope check
    needs the true best coverage, not just what MMR kept. A ``NamedTuple``
    keeps the common ``hits, _ = retrieve(...)`` unpack working for callers
    that only need the hits (``batch.py``, ``recipe/registry/ai.py``,
    ``cli/ai.py``) while still allowing ``.hits``/``.pool_max_score`` access
    where both matter (the GUI worker's out-of-scope warning).
    """

    hits: list[RetrievedChunk]
    pool_max_score: float
