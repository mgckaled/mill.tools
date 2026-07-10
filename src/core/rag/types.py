"""Typed models for the local RAG layer."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    """A RAG answer, the sources it consulted, and the subset it actually cites.

    ``sources`` is every distinct document whose chunks were retrieved into the
    answer's context (the *consulted* set), in first-seen order — parallel to
    the ``[n]`` markers ``build_context`` assigns. ``cited_sources`` is the
    subset the model actually referenced via ``[n]`` in ``text`` (the *cited*
    set), parsed by ``chat.cited_source_numbers``. The two differ whenever
    retrieval pulls in a document the answer never uses: the UI shows cited
    prominently and consulted-but-not-cited discreetly
    (``PLANO_FONTES_E_PISO_RELEVANCIA.md``, Fase 1). An answer that cites nothing
    parseable has ``cited_sources == []`` — every source is consulted-only and
    no citation is ever invented.
    """

    text: str
    sources: list[Path]  # distinct documents consulted (retrieved), first-seen order
    cited_sources: list[Path] = field(default_factory=list)  # subset actually cited


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
