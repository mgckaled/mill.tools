"""Tiny numpy-backed vector store. No new heavy dependency.

Cosine search over a dense ``(N, D)`` float32 matrix with sidecar metadata.
numpy comfortably handles a personal corpus (hundreds of thousands of chunks);
``sqlite-vec`` is the documented upgrade path if the scale ever demands it,
without changing this interface.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from src.core.rag.types import ChunkMeta, RetrievedChunk


class VectorStore:
    """In-memory cosine store with npz + json persistence."""

    def __init__(self, dim: int = 768) -> None:
        """Create an empty store for ``dim``-wide vectors."""
        self.dim = dim
        self.vectors = np.empty((0, dim), dtype=np.float32)
        self.meta: list[ChunkMeta] = []

    def __len__(self) -> int:
        """Number of stored chunks (rows in the matrix)."""
        return len(self.meta)

    def add(self, vecs: np.ndarray, metas: list[ChunkMeta]) -> None:
        """Append ``vecs`` (M, D) and their parallel ``metas`` to the store."""
        if len(vecs) != len(metas):
            raise ValueError(f"vecs/metas length mismatch: {len(vecs)} != {len(metas)}")
        if not len(vecs):
            return
        self.vectors = np.vstack([self.vectors, vecs]) if len(self.vectors) else vecs
        self.meta.extend(metas)

    def drop_source(self, source_path: str) -> None:
        """Remove every chunk belonging to one source (deleted or changed file)."""
        keep = [i for i, m in enumerate(self.meta) if m.source_path != source_path]
        if len(keep) == len(self.meta):
            return  # nothing to drop — avoid a needless copy
        self.vectors = (
            self.vectors[keep] if keep else np.empty((0, self.dim), dtype=np.float32)
        )
        self.meta = [self.meta[i] for i in keep]

    def search(self, query_vec: np.ndarray, k: int = 6) -> list[RetrievedChunk]:
        """Return the top-``k`` chunks by cosine similarity to ``query_vec``."""
        if len(self.vectors) == 0:
            return []
        mat = self.vectors / (
            np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8
        )
        q = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        scores = mat @ q
        top = np.argsort(scores)[::-1][:k]
        return [RetrievedChunk(self.meta[i], float(scores[i])) for i in top]

    def persist(self, directory: Path, *, embed_model: str | None = None) -> None:
        """Write the matrix (npz), metadata (json) and an info sidecar.

        ``index_info.json`` records the embedding model and vector width so the
        index can be described (``stats.index_stats``) and a future dimension
        mismatch detected (Ollama #10176) without loading the matrix. Older
        indexes lack the sidecar; ``index_stats`` treats that as ``embed_model="?"``.
        """
        directory.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(directory / "vectors.npz", vectors=self.vectors)
        (directory / "meta.json").write_text(
            json.dumps([asdict(m) for m in self.meta], ensure_ascii=False),
            encoding="utf-8",
        )
        (directory / "index_info.json").write_text(
            json.dumps(
                {
                    "embed_model": embed_model,
                    "dim": self.dim,
                    "created_at": time.time(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path, dim: int = 768) -> VectorStore:
        """Load a store from ``directory``; return an empty one if absent."""
        store = cls(dim)
        if (directory / "vectors.npz").exists():
            store.vectors = np.load(directory / "vectors.npz")["vectors"].astype(
                np.float32
            )
            raw = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
            store.meta = [ChunkMeta(**m) for m in raw]
            if store.vectors.shape[1]:
                store.dim = store.vectors.shape[1]
        return store
