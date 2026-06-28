"""Message vocabulary for the AI (RAG) module.

worker.py imports the fmt_* builders for emit("log", ...); view.py imports the
resolve_* helpers to turn PipelineEvents into status-line text. Same pattern as
the other modules — separates "what to emit" from "how to display".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import PipelineEvent


# ─── Builders (worker.py → emit("log", ...)) ──────────────────────────────────


def fmt_index_start(total: int) -> str:
    """Log line announcing how many text documents will be indexed."""
    return f"[*] Indexando {total} documento(s) de texto…"


def fmt_index_progress(current: int, total: int) -> str:
    """Mutable progress line during embedding."""
    return f"[~] Indexando {current}/{total}…"


def fmt_index_done(n_docs: int, n_chunks: int, added: int) -> str:
    """Summary line after indexing completes."""
    sign = "+" if added >= 0 else ""
    return (
        f"[✓] Índice atualizado: {n_docs} documento(s), "
        f"{n_chunks} chunk(s) ({sign}{added})."
    )


def fmt_answer_start(model_name: str) -> str:
    """Log line announcing the answer model being queried."""
    return f"[*] Consultando o acervo com {model_name}…"


def fmt_answer_done(n_sources: int) -> str:
    """Summary line after an answer is produced."""
    return f"[✓] Resposta gerada — {n_sources} fonte(s) citada(s)."


def fmt_out_of_scope(best_score: float) -> str:
    """Warning line when the corpus likely does not cover the question (Plano 4A)."""
    return (
        f"[!] O acervo provavelmente não cobre bem esta pergunta "
        f"(proximidade {best_score:.2f}) — a resposta pode ser imprecisa."
    )


# ─── Resolvers (view.py → status line) ────────────────────────────────────────


def resolve_status(event: PipelineEvent) -> str | None:
    """Translate a PipelineEvent into the status-line text. None = no change."""
    p = event.payload
    match event.type:
        case "progress_start":
            return "Iniciando…"
        case "index_start":
            return "Indexando…"
        case "progress_update":
            cur, tot = p.get("current"), p.get("total")
            return f"Indexando {cur}/{tot}…" if tot else None
        case "answer_start":
            return "Consultando o acervo…"
        case "index_done":
            return "Índice atualizado."
        case "answer_done":
            return "Resposta gerada."
        case "task_done":
            return "Concluído."
        case "task_error":
            return "Erro."
        case _:
            return None
