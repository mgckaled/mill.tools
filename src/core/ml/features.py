"""Embedding accessor — turns the persisted RAG store into ML-ready matrices.

This is the heart of the ML foundation and the **only** module that knows the
``VectorStore`` layout: if the RAG ever migrates its storage (e.g. to
``sqlite-vec``, already noted as the upgrade path in ``rag/store.py``), only this
file changes. numpy-pure — no scikit-learn, no Ollama, no re-embedding. The
chunk vectors were already computed and persisted by the RAG indexer; here we
only read and pool them.

Two matrix levels, decided once here and inherited by every consumer:

* ``chunk_matrix`` — the raw ``(N, D)`` matrix + parallel metas (no copy).
* ``document_matrix`` — one row per source document (mean-pool of its chunks,
  L2-normalized by default). Semantic ML operates on documents, so the pooling
  choice lives here so no Plan-4 feature reinvents the aggregation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.core.rag.embedder import EMBED_DIM
from src.core.rag.indexer import index_dir
from src.core.rag.store import VectorStore
from src.core.rag.types import ChunkMeta

from src.core.ml.types import DocumentMatrix


def chunk_matrix(store: VectorStore) -> tuple[np.ndarray, list[ChunkMeta]]:
    """Return the store's raw chunk matrix and its parallel metadata.

    No copy beyond what the store already holds: row ``i`` of the returned array
    corresponds to ``metas[i]``. Callers that need document-level vectors should
    use ``document_matrix`` instead.
    """
    return store.vectors, store.meta


def document_matrix(store: VectorStore, *, l2_normalize: bool = True) -> DocumentMatrix:
    """Pool the chunk vectors into one vector per source document.

    Pooling is the mean of the chunk rows sharing a ``source_path``; the mean is
    then (optionally) L2-normalized so downstream cosine/SVM/k-means operate on
    the unit sphere. Document order is first-seen (stable, deterministic), and
    everything stays ``float32`` — promoting to float64 would double the memory
    for no gain in similarity precision.

    Args:
        store: The chunk-level vector store (typically ``VectorStore.load(...)``).
        l2_normalize: When True (default), each pooled row is divided by its L2
            norm (with a ``+1e-8`` guard, as in ``VectorStore.search``).

    Returns:
        A ``DocumentMatrix`` with ``X`` shaped ``(M, D)`` where ``M`` is the
        number of distinct documents; an empty ``(0, D)`` matrix when the store
        is empty.
    """
    dim = store.vectors.shape[1] if store.vectors.shape[1] else store.dim

    # Group row indices by source_path, preserving first-seen document order.
    rows_by_doc: dict[str, list[int]] = {}
    kind_by_doc: dict[str, str] = {}
    for i, meta in enumerate(store.meta):
        rows_by_doc.setdefault(meta.source_path, []).append(i)
        kind_by_doc.setdefault(meta.source_path, meta.kind)

    if not rows_by_doc:
        return DocumentMatrix(
            X=np.empty((0, dim), dtype=np.float32), source_paths=[], kinds=[]
        )

    source_paths = list(rows_by_doc)
    pooled = np.empty((len(source_paths), dim), dtype=np.float32)
    for d, source in enumerate(source_paths):
        pooled[d] = store.vectors[rows_by_doc[source]].mean(axis=0)

    if l2_normalize:
        norms = np.linalg.norm(pooled, axis=1, keepdims=True) + 1e-8
        pooled = (pooled / norms).astype(np.float32)

    return DocumentMatrix(
        X=pooled,
        source_paths=source_paths,
        kinds=[kind_by_doc[s] for s in source_paths],
    )


def load_document_matrix(
    directory: Path | None = None, *, l2_normalize: bool = True
) -> DocumentMatrix:
    """Load the persisted RAG store and pool it into a ``DocumentMatrix``.

    ``directory`` is injectable (default = the RAG index dir, ``~/.mill-tools/rag``)
    so the flow is unit-testable against a store persisted in ``tmp_path`` — the
    same injection style as the RAG ``embed_fn`` and the Data engine's
    ``connect_fn``. An absent index yields an empty ``DocumentMatrix``.
    """
    directory = directory or index_dir()
    store = VectorStore.load(directory, dim=EMBED_DIM)
    return document_matrix(store, l2_normalize=l2_normalize)
