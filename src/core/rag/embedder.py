"""Local embeddings via Ollama. The only network touchpoint of the RAG core.

Kept tiny and dependency-light: it wraps ``langchain_ollama.OllamaEmbeddings``
(same package already used for ``ChatOllama``) so no new dependency is added. The
indexer/retriever inject these functions as ``embed_fn``/``embed_query_fn``, which
keeps the rest of the core testable without a running Ollama.
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

# CPU-pinned custom build of nomic-embed-text (num_gpu 0), matching the project's
# *-custom convention so embedding never contends for the MX150 with Whisper/Flet.
DEFAULT_EMBED_MODEL = "nomic-embed-custom"  # 768-dim, torch-free, CPU-only
EMBED_DIM = 768

# Embedding requests are split into sub-batches so a long document never sends
# one huge /api/embed request. That caps the Ollama runner's memory spike — a
# frequent cause of the embedding runner being killed on low-RAM machines — and
# lets callers report progress per batch.
EMBED_BATCH_SIZE = 16
# Bounded httpx read timeout for the Ollama client: fail with a clear error
# instead of hanging indefinitely when a runner stalls.
EMBED_TIMEOUT = 300.0

# Shown when is_available() is False: how to provision the embed model.
SETUP_HINT = (
    "ollama pull nomic-embed-text && "
    "ollama create nomic-embed-custom -f ollama/Modelfile.nomic"
)


def _embeddings(model: str):
    """Build an OllamaEmbeddings client with a bounded request timeout."""
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=model, client_kwargs={"timeout": EMBED_TIMEOUT})


def is_available(model: str = DEFAULT_EMBED_MODEL) -> bool:
    """Return True if langchain-ollama is importable and the embed model answers.

    Used to gate the GUI/CLI: when False, the caller shows ``SETUP_HINT``
    instead of failing mid-pipeline.
    """
    try:
        from langchain_ollama import OllamaEmbeddings  # noqa: F401
    except ImportError:
        return False
    try:
        _embeddings(model).embed_query("ping")
        return True
    except Exception as exc:  # Ollama down or model not pulled
        logging.debug("[d] Embedder unavailable: %s", exc)
        return False


def _check_dim(arr: np.ndarray) -> None:
    """Warn when the embedding width is not EMBED_DIM (Ollama #10176 quirk).

    Some Ollama configurations return 8192-dim vectors for ``nomic-embed-text``.
    The store still works with any consistent width, but a mismatch against a
    previously persisted index would corrupt cosine search — so surface it loudly.
    """
    if arr.ndim == 2 and arr.size and arr.shape[1] != EMBED_DIM:
        logging.warning(
            "[!] Unexpected embedding dim %d (expected %d) — check the embed model.",
            arr.shape[1],
            EMBED_DIM,
        )


def embed_texts(
    texts: list[str],
    model: str = DEFAULT_EMBED_MODEL,
    *,
    batch_size: int = EMBED_BATCH_SIZE,
    progress_cb: Callable[[int, int], None] | None = None,
) -> np.ndarray:
    """Return an (N, EMBED_DIM) float32 matrix, embedding in sub-batches.

    Sub-batching keeps each request small so a long document cannot spike the
    Ollama runner's memory; a single OllamaEmbeddings client is reused across
    batches so the model stays loaded. ``progress_cb(done, total)`` fires after
    each batch.
    """
    if not texts:
        return np.empty((0, EMBED_DIM), dtype=np.float32)

    client = _embeddings(model)
    out: list[list[float]] = []
    total = len(texts)
    for start in range(0, total, batch_size):
        out.extend(client.embed_documents(texts[start : start + batch_size]))
        if progress_cb:
            progress_cb(min(start + batch_size, total), total)

    arr = np.asarray(out, dtype=np.float32)
    _check_dim(arr)
    return arr


def embed_query(text: str, model: str = DEFAULT_EMBED_MODEL) -> np.ndarray:
    """Return a (EMBED_DIM,) float32 vector for a single query."""
    vec = _embeddings(model).embed_query(text)
    return np.asarray(vec, dtype=np.float32)
