"""Worker for the RAG evaluation flow, owned by the Observatório hub.

Runs the golden set through the production retrieval path (retrieval-only — no
LLM) and records the run. No Flet dependency — emits everything through the
EventBus (module_id="observatory"), so it is unit-testable with a fake bus. The
core (eval/retrieve) is imported lazily to keep app startup light.

Same worker+view shape as ``index_worker.py``: a pipeline that lives on the
Índice/RAG tab (the hub's "owns its own pipeline" exception), with progress per
question, a Cancelar button, and a fresh embedder gate — ``use_cache=False``, so
it never reuses the Conversa's short-lived availability verdict. The
completion is logged to ``ml_activity`` by this worker, never by the pure core.
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
    """Raised from the progress callback to abort evaluation on user cancel."""


def run_eval_pipeline(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    embed_model: str,
    install_log_handler: bool = True,
) -> bool:
    """Evaluate the golden set and record the run. Returns True on success.

    Emits: progress_start, eval_start (``total``), eval_progress
    (``current``/``total``, per question), eval_done (``hit_rate``/``mrr``),
    task_done — or task_error on an empty index / empty golden set / stale
    scheme / embedder unavailable / cancel. The view re-reads the persisted run
    on task_done (same pattern as the reindex tab), so ``eval_done`` only
    carries a headline for the log line.
    """
    from src.core.observatory.activity import log_activity
    from src.core.rag import embedder
    from src.core.rag.eval import load_eval_data, record_run, run_eval
    from src.core.rag.indexer import CURRENT_EMBED_SCHEME, index_dir
    from src.core.rag.stats import embed_space_id, index_stats, is_stale_scheme
    from src.core.rag.store import VectorStore

    emit = make_emitter(bus, _MODULE_ID, "observatory")
    scope: contextlib.AbstractContextManager = (
        _LogScope(bus, _MODULE_ID) if install_log_handler else contextlib.nullcontext()
    )
    with scope:
        try:
            emit("progress_start")

            directory = index_dir()
            store = VectorStore.load(directory, dim=embedder.EMBED_DIM)
            if len(store) == 0:
                emit(
                    "task_error",
                    payload={
                        "message": 'Índice vazio. Clique em "Reindexar" primeiro.'
                    },
                )
                return False

            data = load_eval_data()
            if not data.golden:
                emit(
                    "task_error",
                    payload={
                        "message": "Golden set vazio. Adicione perguntas via "
                        '"uv run main.py ai eval add".'
                    },
                )
                return False

            stats = index_stats(directory)
            # Evaluating a stale-scheme index measures an artifact (the sidecar
            # claims a scheme the vectors don't have) — refuse, point at reindex.
            if is_stale_scheme(stats, CURRENT_EMBED_SCHEME):
                emit(
                    "task_error",
                    payload={
                        "message": "Índice em esquema antigo — reindexe antes de avaliar."
                    },
                )
                return False

            # Fresh gate (use_cache=False): the eval is a cold flow, never reuses
            # the Conversa's short-lived availability verdict.
            if not embedder.is_available(embed_model, use_cache=False):
                emit(
                    "task_error",
                    payload={
                        "message": f"Embedder indisponível. Rode: {embedder.SETUP_HINT}"
                    },
                )
                return False

            total = len(data.golden)
            emit("eval_start", payload={"total": total})
            emit("log", payload={"message": pipeline_log.fmt_eval_start(total)})

            def _progress(current: int, tot: int) -> None:
                if cancel_event.is_set():
                    raise _Cancelled
                emit("eval_progress", payload={"current": current, "total": tot})
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_eval_progress(current, tot),
                        "mutable": True,
                    },
                )

            def _embed_query(q: str):
                return embedder.embed_query(q, model=embed_model)

            result = run_eval(
                data.golden,
                store,
                _embed_query,
                embed_space_id=embed_space_id(directory),
                embed_scheme=stats.embed_scheme,
                on_progress=_progress,
            )
            record_run(result)

            m = result.metrics
            emit("eval_done", payload={"hit_rate": m.hit_rate, "mrr": m.mrr})
            emit(
                "log",
                payload={"message": pipeline_log.fmt_eval_done(m.hit_rate, m.mrr)},
            )
            log_activity(
                "rag",
                "rag_eval",
                f"avaliação: hit-rate {m.hit_rate:.0%}, MRR {m.mrr:.2f} "
                f"({m.n_covered} cob. + {m.n_out_of_corpus} fora)",
            )
            emit("task_done", payload={})
            return True

        except _Cancelled:
            emit("task_error", payload={"message": "Avaliação cancelada."})
            return False
        except Exception as exc:  # core/Ollama failure — surface, don't crash UI
            logging.getLogger(__name__).warning("[!] Eval error: %s", exc)
            emit("task_error", payload={"message": str(exc)})
            return False


def start_eval_pipeline(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    embed_model: str,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch run_eval_pipeline in a daemon thread; call on_finish() when done."""

    def _run() -> None:
        run_eval_pipeline(bus, cancel_event, embed_model=embed_model)
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
