"""Workers for the Data module: scan, query and save flows in background threads.

No Flet dependency — everything is emitted through the EventBus
(module_id="data"), so the flows are unit-testable with a fake bus. The pure
data core (scanner/nl2sql/engine/convert) is imported lazily to keep startup
light and to keep heavy DuckDB work off the UI thread.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src.gui.modules._pipeline_runner import make_emitter

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "data"

# Rows materialized for the preview table. The full result is only ever written
# to disk by the save flow, so the UI never holds a huge table in memory.
PREVIEW_ROWS = 200


def run_data_scan(bus: EventBus, paths: list[Path]) -> bool:
    """Scan files into DataFiles and emit ``data_scanned`` with their chips.

    Emits: data_scanned ({files: [{name, view, n_rows, n_cols, columns}]}) on
    success, or task_error on failure. The DataFiles themselves are emitted under
    ``_files`` so the view can keep them for the query/save flows.
    """
    from src.core.data.scanner import scan_files

    emit = make_emitter(bus, _MODULE_ID, "data")
    try:
        files = scan_files(paths)
        emit(
            "data_scanned",
            payload={
                "_files": files,
                "files": [
                    {
                        "name": f.path.name,
                        "view": f.view_name,
                        "n_rows": f.n_rows,
                        "n_cols": f.n_cols,
                        "columns": [c.name for c in f.columns],
                    }
                    for f in files
                ],
            },
        )
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning("[!] Data scan error: %s", exc)
        emit("task_error", payload={"message": f"Falha ao ler os arquivos: {exc}"})
        return False


def run_data_translate(
    bus: EventBus, files: list, question: str, *, model_name: str
) -> bool:
    """Translate a Portuguese question into SQL and emit ``data_sql_ready``.

    Emits: progress_start, data_sql_ready ({sql, explanation}), task_done — or
    task_error if the IA fails or returns a non-SELECT.
    """
    from src.core.data import nl2sql
    from src.core.data.scanner import schema_text

    emit = make_emitter(bus, _MODULE_ID, "data")
    try:
        emit("progress_start")
        schema = schema_text(files)
        t0 = time.monotonic()
        sql, explanation = nl2sql.to_sql(schema, question, model_name=model_name)
        elapsed = time.monotonic() - t0
        emit(
            "data_sql_ready",
            payload={
                "sql": sql,
                "explanation": explanation,
                "model_name": model_name,
                "elapsed": elapsed,
            },
        )
        emit("task_done", payload={})
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning("[!] NL→SQL error: %s", exc)
        emit("task_error", payload={"message": f"Não consegui traduzir: {exc}"})
        return False


def run_data_query(bus: EventBus, files: list, sql: str) -> bool:
    """Execute *sql* over *files* and emit a paginated preview.

    Emits: progress_start, data_result ({columns, rows, n_rows, elapsed,
    truncated}), task_done — or task_error if the query is unsafe or fails.
    """
    from src.core.data.engine import run_query

    emit = make_emitter(bus, _MODULE_ID, "data")
    try:
        emit("progress_start")
        result = run_query(files, sql, max_rows=PREVIEW_ROWS)
        emit(
            "data_result",
            payload={
                "columns": result.columns,
                "rows": result.rows,
                "n_rows": result.n_rows,
                "elapsed": result.elapsed,
                "truncated": result.n_rows >= PREVIEW_ROWS,
            },
        )
        emit("task_done", payload={})
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning("[!] Data query error: %s", exc)
        emit("task_error", payload={"message": str(exc)})
        return False


def run_data_save(bus: EventBus, files: list, sql: str, fmt: str, stem: str) -> bool:
    """Save the full result of *sql* to output/data/ and emit ``data_saved``.

    Emits: progress_start, data_saved ({output_path}), task_done — or task_error.
    """
    from src.core.data import convert
    from src.utils import DATA_DIR

    emit = make_emitter(bus, _MODULE_ID, "data")
    try:
        emit("progress_start")
        out = convert.save_query(files, sql, DATA_DIR, fmt, stem)
        emit("data_saved", payload={"output_path": str(out)})
        emit("task_done", payload={})
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning("[!] Data save error: %s", exc)
        emit("task_error", payload={"message": f"Falha ao salvar: {exc}"})
        return False


def run_data_index(bus: EventBus, files: list, *, embed_model: str) -> bool:
    """Index the selected data *files* into the RAG via their data cards.

    Indexes exactly the files the user is working with (additively, without
    reconciling away the rest of the index), so a freshly picked/queried file
    actually lands in the index and shows up in the inspector — regardless of
    whether it lives under output/. Emits under module_id="data" so the Preview
    tab shows progress/log in the same shape as the Consulta tab.

    Emits: data_index_start, data_index_progress (current/total), log,
    data_indexed ({added, total, chunks}), task_done — or task_error on failure.
    """
    from src.core.library.types import LibraryItem
    from src.core.rag import embedder
    from src.core.rag.indexer import index_dir, index_files
    from src.core.rag.store import VectorStore

    emit = make_emitter(bus, _MODULE_ID, "data")
    try:
        emit("data_index_start")
        if not files:
            emit("task_error", payload={"message": "Nenhum arquivo para indexar."})
            return False
        if not embedder.is_available(embed_model):
            emit(
                "task_error",
                payload={
                    "message": f"Embedder indisponível. Rode: {embedder.SETUP_HINT}"
                },
            )
            return False

        items: list[LibraryItem] = []
        for f in files:
            p = Path(f.path)
            st = p.stat()
            items.append(
                LibraryItem(
                    path=p,
                    kind="data",
                    category="processed",
                    size_bytes=st.st_size,
                    modified=st.st_mtime,
                    stem=p.stem,
                    suffix=p.suffix.lower(),
                )
            )
        total = len(items)
        emit("log", payload={"message": f"Indexando {total} arquivo(s) de dados…"})
        store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
        before = len(store)

        def _progress(current: int, tot: int) -> None:
            emit("data_index_progress", payload={"current": current, "total": tot})

        def _embed(texts: list[str]):
            return embedder.embed_texts(texts, model=embed_model)

        def _card(item):
            from src.core.data.datacard import card_for_path

            return card_for_path(Path(item.path))

        index_files(items, store, _embed, progress_cb=_progress, card_fn=_card)
        store.persist(index_dir(), embed_model=embed_model)

        added = len(store) - before
        emit(
            "data_indexed",
            payload={"added": added, "total": total, "chunks": len(store)},
        )
        emit("task_done", payload={})
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning("[!] Data index error: %s", exc)
        emit("task_error", payload={"message": f"Falha ao indexar: {exc}"})
        return False


def run_data_assess(bus: EventBus, file, *, model_name: str) -> bool:
    """Run the IA data-quality assessment over *file*, emitting data events.

    Emits: data_assess_start ({name}), data_assessed ({name, text}), task_done —
    or task_error if the IA fails. The result is cached for reuse by indexing.
    """
    from src.core.data import assess as assess_mod
    from src.core.data.datacard import sample_to_text
    from src.core.data.engine import preview
    from src.core.data.profile import profile_text
    from src.core.data.scanner import schema_text

    emit = make_emitter(bus, _MODULE_ID, "data")
    try:
        emit("data_assess_start", payload={"name": file.path.name})
        schema = schema_text([file])
        prof = profile_text(file.path)
        sample = sample_to_text(preview(file.path, limit=10))
        text = assess_mod.assess(schema, prof, sample, model_name=model_name)
        assess_mod.save_assessment(file.path, text)  # cache → reused by indexing
        emit("data_assessed", payload={"name": file.path.name, "text": text})
        emit("task_done", payload={})
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning("[!] Data assess error: %s", exc)
        emit("task_error", payload={"message": f"Não foi possível avaliar: {exc}"})
        return False


def _spawn(target: Callable, *args, **kwargs) -> threading.Thread:
    """Run *target* in a daemon thread."""
    thread = threading.Thread(target=lambda: target(*args, **kwargs), daemon=True)
    thread.start()
    return thread


def start_scan(bus: EventBus, paths: list[Path]) -> threading.Thread:
    """Launch run_data_scan in a daemon thread."""
    return _spawn(run_data_scan, bus, paths)


def start_translate(
    bus: EventBus, files: list, question: str, *, model_name: str
) -> threading.Thread:
    """Launch run_data_translate in a daemon thread."""
    return _spawn(run_data_translate, bus, files, question, model_name=model_name)


def start_query(bus: EventBus, files: list, sql: str) -> threading.Thread:
    """Launch run_data_query in a daemon thread."""
    return _spawn(run_data_query, bus, files, sql)


def start_save(
    bus: EventBus, files: list, sql: str, fmt: str, stem: str
) -> threading.Thread:
    """Launch run_data_save in a daemon thread."""
    return _spawn(run_data_save, bus, files, sql, fmt, stem)


def start_index(bus: EventBus, files: list, *, embed_model: str) -> threading.Thread:
    """Launch run_data_index in a daemon thread."""
    return _spawn(run_data_index, bus, files, embed_model=embed_model)


def start_assess(bus: EventBus, file, *, model_name: str) -> threading.Thread:
    """Launch run_data_assess in a daemon thread."""
    return _spawn(run_data_assess, bus, file, model_name=model_name)
