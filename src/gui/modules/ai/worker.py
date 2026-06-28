"""Workers for the AI (RAG) module: index and answer flows in background threads.

No Flet dependency — emits everything through the EventBus (module_id="ai"), so
both flows are unit-testable with a fake bus. The core (scan/index/retrieve/
answer) is imported lazily to keep app startup light.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import TYPE_CHECKING, Callable

from src.gui.modules._pipeline_runner import _LogScope, make_emitter
from src.gui.modules.ai import pipeline_log

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "ai"


class _Cancelled(Exception):
    """Raised from the progress callback to abort indexing on user cancel."""


def run_ai_index(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    embed_model: str,
    install_log_handler: bool = True,
) -> bool:
    """Scan the Library, embed new/changed text items and persist the index.

    Emits: progress_start, index_start, progress_update (per item), index_done,
    task_done — or task_error on failure/cancel. Returns True on success.
    """
    from src.core.library.scanner import scan_library
    from src.core.rag import embedder
    from src.core.rag.indexer import build_index, indexable_items, index_dir
    from src.core.rag.store import VectorStore

    emit = make_emitter(bus, _MODULE_ID, "ai")
    scope: contextlib.AbstractContextManager = (
        _LogScope(bus, _MODULE_ID) if install_log_handler else contextlib.nullcontext()
    )
    with scope:
        try:
            emit("progress_start")
            if not embedder.is_available(embed_model):
                emit(
                    "task_error",
                    payload={
                        "message": f"Embedder indisponível. Rode: {embedder.SETUP_HINT}"
                    },
                )
                return False

            items = scan_library()
            total = len(indexable_items(items))
            emit("index_start", payload={"total": total})
            emit("log", payload={"message": pipeline_log.fmt_index_start(total)})

            store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
            before = len(store)

            def _progress(current: int, tot: int) -> None:
                if cancel_event.is_set():
                    raise _Cancelled
                emit("progress_update", payload={"current": current, "total": tot})
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_index_progress(current, tot),
                        "mutable": True,
                    },
                )

            def _embed(texts: list[str]):
                return embedder.embed_texts(texts, model=embed_model)

            def _card(item):
                from pathlib import Path

                from src.core.data.datacard import card_for_path

                return card_for_path(Path(item.path))

            build_index(items, store, _embed, progress_cb=_progress, card_fn=_card)
            store.persist(index_dir(), embed_model=embed_model)

            added = len(store) - before
            emit(
                "index_done",
                payload={"n_docs": total, "n_chunks": len(store), "added": added},
            )
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_index_done(total, len(store), added)
                },
            )
            emit("task_done", payload={})
            return True

        except _Cancelled:
            emit("task_error", payload={"message": "Indexação cancelada."})
            return False
        except Exception as exc:  # core/Ollama failure — surface, don't crash UI
            logging.getLogger(__name__).warning("[!] Index error: %s", exc)
            emit("task_error", payload={"message": str(exc)})
            return False


def run_ai_answer(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    query: str,
    scope: str | None,
    model_name: str,
    embed_model: str,
    k: int = 6,
    install_log_handler: bool = True,
) -> bool:
    """Retrieve top-k chunks for the question and emit a cited answer.

    Emits: progress_start, answer_start, answer_done (text + sources), task_done —
    or task_error if the index is empty / embedder unavailable / LLM fails.
    """
    from src.core.rag import embedder
    from src.core.rag.chat import answer as _answer
    from src.core.rag.indexer import index_dir
    from src.core.rag.retriever import retrieve
    from src.core.rag.store import VectorStore

    emit = make_emitter(bus, _MODULE_ID, "ai")
    scope_cm: contextlib.AbstractContextManager = (
        _LogScope(bus, _MODULE_ID) if install_log_handler else contextlib.nullcontext()
    )
    with scope_cm:
        try:
            emit("progress_start")
            store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
            if len(store) == 0:
                emit(
                    "task_error",
                    payload={
                        "message": 'Índice vazio. Clique em "Reindexar" para começar.'
                    },
                )
                return False
            if not embedder.is_available(embed_model):
                emit(
                    "task_error",
                    payload={
                        "message": f"Embedder indisponível. Rode: {embedder.SETUP_HINT}"
                    },
                )
                return False

            emit("answer_start", payload={"query": query, "model_name": model_name})
            emit("log", payload={"message": pipeline_log.fmt_answer_start(model_name)})

            def _embed_query(q: str):
                return embedder.embed_query(q, model=embed_model)

            t0 = time.monotonic()
            hits = retrieve(query, store, _embed_query, k=k, scope=scope)

            # Out-of-corpus warning (Plano 4A): the best retrieved chunk's cosine
            # is the corpus's closeness to the question. Below the threshold the
            # corpus probably does not cover it — flag it so the view can warn
            # (we still answer; the user decides). No re-embedding: reuse the hit.
            from src.core.ml.recommend import DEFAULT_IN_CORPUS_THRESHOLD

            best_score = hits[0].score if hits else 0.0
            low_confidence = best_score < DEFAULT_IN_CORPUS_THRESHOLD
            if low_confidence:
                emit(
                    "log",
                    payload={"message": pipeline_log.fmt_out_of_scope(best_score)},
                )

            result = _answer(query, hits, model_name=model_name)
            elapsed = time.monotonic() - t0

            emit(
                "answer_done",
                payload={
                    "query": query,
                    "text": result.text,
                    "sources": [str(s) for s in result.sources],
                    "model_name": model_name,
                    "elapsed": elapsed,
                    "low_confidence": low_confidence,
                    "best_score": best_score,
                },
            )
            emit(
                "log",
                payload={"message": pipeline_log.fmt_answer_done(len(result.sources))},
            )
            emit("task_done", payload={})
            return True

        except Exception as exc:  # make_llm / retrieval failure
            logging.getLogger(__name__).warning("[!] Answer error: %s", exc)
            emit("task_error", payload={"message": str(exc)})
            return False


def start_ai_index(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    embed_model: str,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch run_ai_index in a daemon thread; call on_finish() when done."""

    def _run() -> None:
        run_ai_index(bus, cancel_event, embed_model=embed_model)
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def start_ai_answer(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    query: str,
    scope: str | None,
    model_name: str,
    embed_model: str,
    k: int = 6,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch run_ai_answer in a daemon thread; call on_finish() when done."""

    def _run() -> None:
        run_ai_answer(
            bus,
            cancel_event,
            query=query,
            scope=scope,
            model_name=model_name,
            embed_model=embed_model,
            k=k,
        )
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
