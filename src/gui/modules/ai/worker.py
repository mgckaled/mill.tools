"""Workers for the AI hub's two flows: Conversa (RAG answer) and Comandos CLI
(NL→CLI command generation), each in its own background thread.

No Flet dependency — emits everything through the EventBus (module_id="ai"), so
both are unit-testable with a fake bus. The core (retrieve/answer, nl2cli) is
imported lazily to keep app startup light.

The reindex flow used to live here too; it moved to
``gui/modules/observatory/index_worker.py`` (Fase 0b, PLANO_NL2CLI_HUB_IA.md) —
the AI hub now only runs Conversa/Comandos CLI.
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


def run_ai_command(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    query: str,
    model_name: str,
    install_log_handler: bool = True,
) -> bool:
    """Translate *query* into a ``uv run main.py ...`` command and emit it.

    Emits: progress_start, command_start, command_done (command + explanation,
    no ``sources``), task_done — or task_error if Ollama is unreachable (cloud
    models skip this check) or the LLM cannot produce a valid command.
    """
    # Layer exception (documented in docs/HISTORY.md + skill `architecture`):
    # gui/ normally only imports core/, never cli/ — src/cli/reference.py's
    # build_reference()/validate_command() are the one place the AI hub's NL→CLI
    # mode needs the *real* argparse parsers, so this import crosses that
    # boundary deliberately, mirrored only here.
    from src.cli.reference import build_reference, validate_command
    from src.core.observatory.status import ollama_inventory
    from src.core.text.nl2cli import NL2CLIError, to_command
    from src.llm_factory import OLLAMA_SETUP_HINT, is_cloud_model

    emit = make_emitter(bus, _MODULE_ID, "ai")
    scope_cm: contextlib.AbstractContextManager = (
        _LogScope(bus, _MODULE_ID) if install_log_handler else contextlib.nullcontext()
    )
    with scope_cm:
        try:
            emit("progress_start")
            if not is_cloud_model(model_name) and not ollama_inventory().reachable:
                emit(
                    "task_error",
                    payload={
                        "message": f"Ollama indisponível. Rode: {OLLAMA_SETUP_HINT}"
                    },
                )
                return False

            emit("command_start", payload={"query": query, "model_name": model_name})
            emit("log", payload={"message": pipeline_log.fmt_command_start(model_name)})

            t0 = time.monotonic()
            command, explanation = to_command(
                query,
                build_reference(),
                model=model_name,
                validate_fn=validate_command,
            )
            elapsed = time.monotonic() - t0

            emit(
                "command_done",
                payload={
                    "query": query,
                    "command": command,
                    "explanation": explanation,
                    "model_name": model_name,
                    "elapsed": elapsed,
                },
            )
            emit(
                "log", payload={"message": pipeline_log.fmt_command_done(bool(command))}
            )

            from src.core.observatory.activity import log_activity

            log_activity("rag", "nl2cli", command or "(fora de escopo)")

            emit("task_done", payload={})
            return True

        except NL2CLIError as exc:
            emit("task_error", payload={"message": str(exc)})
            return False
        except Exception as exc:  # make_llm failure
            logging.getLogger(__name__).warning("[!] Command error: %s", exc)
            emit("task_error", payload={"message": str(exc)})
            return False


def start_ai_command(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    query: str,
    model_name: str,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch run_ai_command in a daemon thread; call on_finish() when done."""

    def _run() -> None:
        run_ai_command(bus, cancel_event, query=query, model_name=model_name)
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
