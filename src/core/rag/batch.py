"""Batch RAG: apply one instruction across many Library documents.

For each selected source, retrieval is scoped to that single document and the
instruction is answered against it — so a prompt like "summarize" produces one
answer per document. Pure-ish core: ``embed_query_fn`` is injected and the LLM
goes through ``chat.answer`` (provider routed by ``make_llm``), keeping it
testable without Ollama.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src.core.rag.chat import DEFAULT_MODEL, answer
from src.core.rag.retriever import retrieve

if TYPE_CHECKING:
    import numpy as np

    from src.core.rag.store import VectorStore
    from src.core.rag.types import AnswerResult


@dataclass(frozen=True, slots=True)
class BatchResult:
    """One document's answer in a batch run."""

    source_path: str
    answer: AnswerResult


def distinct_sources(store: VectorStore, *, kind: str | None = None) -> list[str]:
    """Distinct source paths in the store, in first-seen order, optionally by kind."""
    seen: dict[str, None] = {}
    for m in store.meta:
        if kind and m.kind != kind:
            continue
        seen.setdefault(m.source_path, None)
    return list(seen)


def run_batch(
    instruction: str,
    store: VectorStore,
    embed_query_fn: Callable[[str], np.ndarray],
    *,
    sources: list[str],
    model_name: str = DEFAULT_MODEL,
    k: int = 6,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_is_set: Callable[[], bool] | None = None,
) -> list[BatchResult]:
    """Apply ``instruction`` to each source and collect the per-document answers.

    Args:
        instruction: The prompt to run against every selected document.
        store: The vector store to retrieve from.
        embed_query_fn: Maps the instruction to a query vector (injected).
        sources: Distinct source paths to process (e.g. from distinct_sources).
        model_name: Answer model — Ollama tag or Gemini name.
        k: Chunks to retrieve per document.
        progress_cb: Optional ``(current, total)`` callback, one call per source
            (attempted, regardless of success — mirrors ``indexer._index_one``'s
            per-item accounting).
        cancel_is_set: Optional ``() -> bool``, checked between sources — same
            convention as ``core.recipes.runner``. ``None`` (the default) never
            cancels. No current caller wires a real cancellation source (batch
            runs only through ``cli/ai.py --batch`` today, a synchronous
            script); this is the seam for the day one does.

    Returns:
        One ``BatchResult`` per source that answered successfully, in input
        order — a source whose retrieve/answer step raises (e.g. the LLM
        restarting mid-run) is logged and skipped rather than aborting the
        rest, the same "log + skip" contract ``indexer._index_one`` uses for a
        single bad item. Cancellation still stops the whole run early.
    """
    results: list[BatchResult] = []
    total = len(sources)
    for n, source in enumerate(sources, 1):
        if cancel_is_set is not None and cancel_is_set():
            break
        try:
            hits = retrieve(instruction, store, embed_query_fn, k=k, scope=source)
            result = answer(instruction, hits, model_name=model_name)
        except Exception as exc:  # one bad document must not abort the batch
            logging.warning("[!] Could not answer for %s: %s", Path(source).name, exc)
        else:
            results.append(BatchResult(source, result))
        if progress_cb:
            progress_cb(n, total)
    return results
