"""Tiny numpy-backed vector store. No new heavy dependency.

Cosine search over a dense ``(N, D)`` float32 matrix with sidecar metadata.
numpy comfortably handles a personal corpus (hundreds of thousands of chunks);
``sqlite-vec`` is the documented upgrade path if the scale ever demands it,
without changing this interface.
"""

from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from src.core.io_atomic import write_group
from src.core.rag.bm25 import bm25_score, build_bm25_index
from src.core.rag.types import ChunkMeta, RetrievedChunk


class VectorStore:
    """In-memory cosine store with npz + json persistence."""

    def __init__(self, dim: int = 768) -> None:
        """Create an empty store for ``dim``-wide vectors."""
        self.dim = dim
        self.vectors = np.empty((0, dim), dtype=np.float32)
        self.meta: list[ChunkMeta] = []
        # Lazy cache of the L2-normalized vectors, invalidated by add()/drop_source().
        # `vectors` itself stays raw — ml.features.document_matrix means the raw rows
        # before normalizing the pooled result, so normalizing in place would shift
        # that pooling math.
        self._normalized: np.ndarray | None = None
        # Lazy cache of the BM25 index over chunk text, same invalidation as above.
        self._bm25: BM25Okapi | None = None

    def __len__(self) -> int:
        """Number of stored chunks (rows in the matrix)."""
        return len(self.meta)

    def add(self, vecs: np.ndarray, metas: list[ChunkMeta]) -> None:
        """Append ``vecs`` (M, D) and their parallel ``metas`` to the store."""
        if len(vecs) != len(metas):
            raise ValueError(f"vecs/metas length mismatch: {len(vecs)} != {len(metas)}")
        if not len(vecs):
            return
        # np.vstack already rejects a width mismatch once the store is
        # non-empty; an empty store has no prior row to check against, so a
        # wrong-width embed_fn (Ollama #10176: some configs return 8192-dim
        # vectors instead of 768) would otherwise be silently accepted here,
        # corrupting self.dim vs. self.vectors — and only surface later as a
        # confusing shape mismatch deep inside search().
        if len(self.vectors) == 0 and vecs.shape[1] != self.dim:
            raise ValueError(
                f"Embedding width {vecs.shape[1]} does not match store dim "
                f"{self.dim} (check the embed model — see Ollama #10176)."
            )
        self.vectors = np.vstack([self.vectors, vecs]) if len(self.vectors) else vecs
        self.meta.extend(metas)
        self._normalized = None
        self._bm25 = None

    def drop_source(self, source_path: str) -> None:
        """Remove every chunk belonging to one source (deleted or changed file)."""
        keep = [i for i, m in enumerate(self.meta) if m.source_path != source_path]
        if len(keep) == len(self.meta):
            return  # nothing to drop — avoid a needless copy
        self.vectors = (
            self.vectors[keep] if keep else np.empty((0, self.dim), dtype=np.float32)
        )
        self.meta = [self.meta[i] for i in keep]
        self._normalized = None
        self._bm25 = None

    def _normalized_vectors(self) -> np.ndarray:
        """Return the L2-normalized vectors, computed once and cached until mutated."""
        if self._normalized is None:
            self._normalized = self.vectors / (
                np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8
            )
        return self._normalized

    def _bm25_index(self) -> BM25Okapi | None:
        """Return the cached BM25 index over chunk text, built once until mutated.

        ``None`` for an empty store — BM25Okapi requires at least one document.
        """
        if self._bm25 is None and self.meta:
            self._bm25 = build_bm25_index([m.text for m in self.meta])
        return self._bm25

    def dense_scores(
        self, query_vec: np.ndarray, *, mask: np.ndarray | None = None
    ) -> np.ndarray:
        """Cosine similarity of ``query_vec`` against every stored chunk.

        Masked-out rows are ``-inf`` so they never win a downstream top-k. Factored
        out of :meth:`search` so :func:`src.core.rag.retriever.retrieve` can combine
        it with :meth:`bm25_scores` via rank fusion instead of taking a top-k here.
        """
        if len(self.vectors) == 0:
            return np.zeros(0, dtype=np.float32)
        q = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        scores = self._normalized_vectors() @ q
        if mask is not None:
            scores = np.where(mask, scores, -np.inf)
        return scores

    def bm25_scores(self, query: str, *, mask: np.ndarray | None = None) -> np.ndarray:
        """BM25 lexical relevance of ``query`` against every stored chunk.

        Masked-out rows are ``-inf``, same convention as :meth:`dense_scores`.
        """
        index = self._bm25_index()
        if index is None:
            return np.zeros(0, dtype=np.float64)
        scores = bm25_score(index, query)
        if mask is not None:
            scores = np.where(mask, scores, -np.inf)
        return scores

    def search(
        self, query_vec: np.ndarray, k: int = 6, *, mask: np.ndarray | None = None
    ) -> list[RetrievedChunk]:
        """Return the top-``k`` chunks by cosine similarity to ``query_vec``.

        Args:
            query_vec: Query embedding, shape ``(D,)``.
            k: Number of results to return.
            mask: Optional boolean array (length ``len(self)``) restricting the
                candidate rows *before* ranking. Pass a scope filter here rather
                than filtering the result afterwards — a selective scope (e.g. a
                single source document) still gets up to ``k`` hits instead of
                risking fewer because its rows didn't make an unscoped top-k'.
        """
        scores = self.dense_scores(query_vec, mask=mask)
        if len(scores) == 0:
            return []
        top = np.argsort(scores)[::-1][:k]
        top = top[np.isfinite(scores[top])]  # drop masked-out rows in a too-small scope
        return [RetrievedChunk(self.meta[i], float(scores[i])) for i in top]

    def persist(
        self,
        directory: Path,
        *,
        embed_model: str | None = None,
        embed_scheme: str | None = None,
    ) -> None:
        """Write the matrix (npz), metadata (json) and an info sidecar as one
        atomic unit (:func:`src.core.io_atomic.write_group`).

        ``index_info.json`` records the embedding model, vector width and
        content scheme so the index can be described (``stats.index_stats``),
        a future dimension mismatch detected (Ollama #10176) and a stale
        embedding space (``indexer.CURRENT_EMBED_SCHEME`` changed since this
        index was built) flagged — all without loading the matrix. Older
        indexes lack the sidecar, or lack the ``embed_scheme`` key; ``stats``
        treats either as ``"?"``.

        Writing the trio as a group means a crash or a concurrent reader never
        sees a fresh ``vectors.npz`` paired with a stale/missing ``meta.json``.
        """
        vectors_buf = io.BytesIO()
        np.savez_compressed(vectors_buf, vectors=self.vectors)
        meta_bytes = json.dumps(
            [asdict(m) for m in self.meta], ensure_ascii=False
        ).encode("utf-8")
        info_bytes = json.dumps(
            {
                "embed_model": embed_model,
                "dim": self.dim,
                "embed_scheme": embed_scheme,
                "created_at": time.time(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        write_group(
            [
                (directory / "vectors.npz", vectors_buf.getvalue()),
                (directory / "meta.json", meta_bytes),
                (directory / "index_info.json", info_bytes),
            ]
        )

    @classmethod
    def load(cls, directory: Path, dim: int = 768) -> VectorStore:
        """Load a store from ``directory``; return an empty one if absent.

        Tolerates ``vectors.npz`` present without its ``meta.json`` sidecar
        (an interrupted persist, or manual tampering) — returns an empty store
        with a warning instead of raising ``FileNotFoundError``. Also tolerates
        a *corrupted* pair (truncated npz, invalid JSON) the same way — same
        parity as ``classify.prototypes._load_prototypes``, which already
        treats a bad ``.npz``/JSON as a cache miss rather than propagating.
        """
        store = cls(dim)
        vectors_path = directory / "vectors.npz"
        meta_path = directory / "meta.json"
        if not vectors_path.exists():
            return store
        if not meta_path.exists():
            logging.warning(
                "[!] %s exists without its meta.json sidecar — treating index as empty.",
                vectors_path,
            )
            return store
        try:
            vectors = np.load(vectors_path)["vectors"].astype(np.float32)
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = [ChunkMeta(**m) for m in raw]
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile) as exc:
            logging.warning(
                "[!] Malformed index at %s (%s) — treating index as empty.",
                directory,
                exc,
            )
            return store
        store.vectors = vectors
        store.meta = meta
        if store.vectors.shape[1]:
            store.dim = store.vectors.shape[1]
        return store
