"""Local embeddings via Ollama. The only network touchpoint of the RAG core.

Kept tiny and dependency-light: it wraps ``langchain_ollama.OllamaEmbeddings``
(same package already used for ``ChatOllama``) so no new dependency is added. The
indexer/retriever inject these functions as ``embed_fn``/``embed_query_fn``, which
keeps the rest of the core testable without a running Ollama.
"""

from __future__ import annotations

import logging

import numpy as np

# CPU-pinned custom build of nomic-embed-text (num_gpu 0), matching the project's
# *-custom convention so embedding never contends for the MX150 with Whisper/Flet.
DEFAULT_EMBED_MODEL = "nomic-embed-custom"  # 768-dim, torch-free, CPU-only
EMBED_DIM = 768

# Shown when is_available() is False: how to provision the embed model.
SETUP_HINT = (
    "ollama pull nomic-embed-text && "
    "ollama create nomic-embed-custom -f ollama/Modelfile.nomic"
)


def is_available(model: str = DEFAULT_EMBED_MODEL) -> bool:
    """Return True if langchain-ollama is importable and the embed model answers.

    Used to gate the GUI/CLI: when False, the caller shows ``SETUP_HINT``
    instead of failing mid-pipeline.
    """
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        return False
    try:
        OllamaEmbeddings(model=model).embed_query("ping")
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


def embed_texts(texts: list[str], model: str = DEFAULT_EMBED_MODEL) -> np.ndarray:
    """Return an (N, EMBED_DIM) float32 matrix for the given texts."""
    from langchain_ollama import OllamaEmbeddings

    vecs = OllamaEmbeddings(model=model).embed_documents(texts)
    arr = np.asarray(vecs, dtype=np.float32)
    _check_dim(arr)
    return arr


def embed_query(text: str, model: str = DEFAULT_EMBED_MODEL) -> np.ndarray:
    """Return a (EMBED_DIM,) float32 vector for a single query."""
    from langchain_ollama import OllamaEmbeddings

    vec = OllamaEmbeddings(model=model).embed_query(text)
    return np.asarray(vec, dtype=np.float32)
