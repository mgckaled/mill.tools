"""Worker for the RAG reindex flow, owned by the Observatório hub.

No Flet dependency — emits everything through the EventBus (module_id=
"observatory"), so it is unit-testable with a fake bus. The core (scan/index)
is imported lazily to keep app startup light.

Moved here from ``gui/modules/ai/worker.py`` (Fase 0b, PLANO_NL2CLI_HUB_IA.md):
the AI hub now only runs the Conversa (answer) flow — reindexing is a pipeline,
and Observatório is the hub that owns pipelines/read-only surfaces for
cross-module ML, so the reindex button and its progress feedback moved to the
Índice/RAG tab there. ``ai/index_button.py`` (the "Indexar no RAG" button
embedded in producer modules) imports ``run_ai_index`` from here.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import TYPE_CHECKING, Callable

from src.gui.modules._pipeline_runner import _LogScope, make_emitter
from src.gui.modules.ai import pipeline_log

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "observatory"


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
    from src.core.rag.indexer import (
        CURRENT_EMBED_SCHEME,
        build_index,
        index_dir,
        indexable_items,
    )
    from src.core.rag.stats import index_stats, is_stale_scheme
    from src.core.rag.store import VectorStore

    emit = make_emitter(bus, _MODULE_ID, "observatory")
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

            index_directory = index_dir()
            store = VectorStore.load(index_directory, dim=embedder.EMBED_DIM)
            before = len(store)
            # A scheme change alone never moves a source file's mtime — force
            # a full re-embed so "Reindexar" actually migrates a stale index
            # instead of silently no-op'ing (see build_index's `force` docstring).
            force = is_stale_scheme(index_stats(index_directory), CURRENT_EMBED_SCHEME)

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

            build_index(
                items, store, _embed, progress_cb=_progress, card_fn=_card, force=force
            )
            store.persist(
                index_directory,
                embed_model=embed_model,
                embed_scheme=CURRENT_EMBED_SCHEME,
            )

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
