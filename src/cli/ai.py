"""CLI subcommand `ai` — local RAG over the Library corpus.

Two flows behind one positional:
    uv run main.py ai index                       # (re)build the vector index
    uv run main.py ai "what did I say about X?"    # ask the whole corpus
    uv run main.py ai "summarize" --scope path.txt # ask a single document
    uv run main.py ai "..." --model gemini-2.5-flash --k 8

Reuses the same core (scan_library / build_index / retrieve / answer) as the GUI.
Embeddings are always local (Ollama); only the answer step may use Gemini opt-in.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable

import numpy as np

# Sentinel positional that triggers a (re)index instead of a question.
_INDEX_CMD = "index"


def add_ai_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the `ai` subcommand and its arguments."""
    p = subparsers.add_parser(
        "ai",
        help="Ask questions about your processed corpus (local RAG)",
    )
    p.add_argument(
        "query",
        help='Your question, or the literal "index" to (re)build the index',
    )
    p.add_argument(
        "--scope",
        default=None,
        help="Restrict to a source file path or a kind (transcription/document/image)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Answer model — Ollama tag (e.g. qwen7b-custom) or Gemini (gemini-2.5-flash)",
    )
    p.add_argument(
        "--embed-model",
        default=None,
        dest="embed_model",
        help="Embedding model (default nomic-embed-text)",
    )
    p.add_argument(
        "--k",
        type=int,
        default=6,
        metavar="N",
        help="Number of chunks to retrieve (default 6)",
    )
    p.add_argument(
        "--reindex",
        action="store_true",
        help="Rebuild the index before answering the question",
    )
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    p.set_defaults(func=run_ai_cli)


def _resolve_scope(scope: str | None) -> str | None:
    """Normalize a --scope value: an existing file → absolute path; else a kind."""
    if not scope:
        return None
    p = Path(scope)
    if p.exists():
        return str(p.resolve())
    return scope  # treat as a kind filter (transcription/document/image)


def _embed_fns(
    embed_model: str,
) -> tuple[Callable[[list[str]], np.ndarray], Callable[[str], np.ndarray]]:
    """Bind the embedding model into the (embed_texts, embed_query) callables."""
    from src.core.rag import embedder

    return (
        lambda texts: embedder.embed_texts(texts, model=embed_model),
        lambda q: embedder.embed_query(q, model=embed_model),
    )


def _build(embed_model: str) -> None:
    """Scan the Library, embed new/changed text items and persist the index."""
    from tqdm import tqdm

    from src.core.library.scanner import scan_library
    from src.core.rag import embedder
    from src.core.rag.indexer import build_index, indexable_items, index_dir
    from src.core.rag.store import VectorStore

    items = scan_library()
    total = len(indexable_items(items))
    store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
    before = len(store)

    embed_texts, _ = _embed_fns(embed_model)
    bar = tqdm(total=total, desc="Indexando", unit="doc", disable=total == 0)

    def _progress(current: int, _total: int) -> None:
        bar.n = current
        bar.refresh()

    build_index(items, store, embed_texts, progress_cb=_progress)
    bar.close()
    store.persist(index_dir())

    added = len(store) - before
    sign = "+" if added >= 0 else ""
    print(
        f"Índice atualizado: {total} documento(s) de texto, "
        f"{len(store)} chunk(s) ({sign}{added}). Salvo em {index_dir()}."
    )


def _ask(ns: argparse.Namespace, embed_model: str) -> None:
    """Retrieve top-k chunks for the question and print a cited answer."""
    from src.core.rag import embedder
    from src.core.rag.chat import DEFAULT_MODEL, answer
    from src.core.rag.indexer import index_dir
    from src.core.rag.retriever import retrieve
    from src.core.rag.store import VectorStore

    store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
    if len(store) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)
    if not embedder.is_available(embed_model):
        print(f"Embedder indisponível. Rode: ollama pull {embed_model}")
        sys.exit(1)

    _, embed_query = _embed_fns(embed_model)
    hits = retrieve(
        ns.query,
        store,
        embed_query,
        k=ns.k,
        scope=_resolve_scope(ns.scope),
    )
    result = answer(ns.query, hits, model_name=ns.model or DEFAULT_MODEL)

    print(result.text)
    if result.sources:
        print("\nFontes:")
        for i, source in enumerate(result.sources, 1):
            print(f"  [{i}] {source.name}")


def run_ai_cli(ns: argparse.Namespace) -> None:
    """Dispatch the `ai` subcommand: (re)index and/or answer a question."""
    # Output filenames may contain non-cp1252 characters (e.g. fullwidth ｜).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    from src.core.rag import embedder

    embed_model = ns.embed_model or embedder.DEFAULT_EMBED_MODEL

    if ns.query == _INDEX_CMD or ns.reindex:
        if not embedder.is_available(embed_model):
            print(f"Embedder indisponível. Rode: ollama pull {embed_model}")
            sys.exit(1)
        logging.info("[*] Building index (embed model: %s)...", embed_model)
        _build(embed_model)
        if ns.query == _INDEX_CMD:
            return

    _ask(ns, embed_model)
