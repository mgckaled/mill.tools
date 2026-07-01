"""Query-time retrieval over the vector store.

Pure: the query embedding is injected as ``embed_query_fn`` so the top-k logic
and scope filtering can be tested without a running Ollama.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from src.core.rag.store import VectorStore
from src.core.rag.types import RetrievedChunk


def retrieve(
    query: str,
    store: VectorStore,
    embed_query_fn: Callable[[str], np.ndarray],
    *,
    k: int = 6,
    scope: str | None = None,
) -> list[RetrievedChunk]:
    """Embed the query and return the top-``k`` chunks, optionally scoped.

    Args:
        query: Natural-language question.
        store: The vector store to search.
        embed_query_fn: Maps the query string to a (D,) vector (injected so the
            function stays testable without Ollama).
        k: Number of chunks to return.
        scope: ``None`` searches the whole corpus. A source path restricts to
            that single document; a kind string restricts to one kind. The scope
            is applied as a mask *before* ranking (not a post-hoc filter over an
            unscoped top-k'), so a selective scope — e.g. one document among
            thousands of chunks — still returns up to ``k`` hits instead of
            risking fewer when its chunks don't make an unscoped candidate pool.

    Returns:
        Up to ``k`` retrieved chunks, highest score first.
    """
    mask = None
    if scope:
        mask = np.array(
            [m.source_path == scope or m.kind == scope for m in store.meta], dtype=bool
        )
    return store.search(embed_query_fn(query), k=k, mask=mask)
