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


def fmt_query_condensed(search_query: str) -> str:
    """Log line shown when a follow-up question was rewritten as standalone
    (Fase 2, PLANO_CONVERSA_MULTITURNO.md) — only emitted when the condensed
    query actually differs from what the user typed."""
    return f'[~] Pergunta reformulada: "{search_query}"'


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


def fmt_command_start(model_name: str) -> str:
    """Log line announcing the model generating a CLI command (Fase 3)."""
    return f"[*] Gerando comando com {model_name}…"


def fmt_command_done(has_command: bool) -> str:
    """Summary line after a CLI command is generated (or refused)."""
    return "[✓] Comando gerado." if has_command else "[i] Pedido fora do escopo da CLI."


# ─── RAG eval (Observatório, PLANO_RAG_EVAL, Fase 4) ──────────────────────────


def fmt_eval_start(total: int) -> str:
    """Log line announcing how many golden questions the run will evaluate."""
    return f"[*] Avaliando {total} pergunta(s)…"


def fmt_eval_progress(current: int, total: int) -> str:
    """Mutable progress line during an evaluation run."""
    return f"[~] Avaliando {current}/{total}…"


def fmt_eval_done(hit_rate: float, mrr: float) -> str:
    """Summary line after an evaluation run completes."""
    return f"[✓] Avaliação concluída — hit-rate {hit_rate:.0%}, MRR {mrr:.2f}."


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
        case "condense_start":
            return "Condensando pergunta…"
        case "answer_start":
            return "Consultando o acervo…"
        case "index_done":
            return "Índice atualizado."
        case "answer_done":
            return "Resposta gerada."
        case "command_start":
            return "Gerando comando…"
        case "command_done":
            return "Comando gerado." if p.get("command") else "Pedido fora de escopo."
        case "task_done":
            return "Concluído."
        case "task_error":
            return "Erro."
        case _:
            return None
