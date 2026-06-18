"""Message vocabulary for the Recipes module.

worker.py imports the fmt_* builders for emit("log", ...); view.py imports
resolve_status to turn PipelineEvents into the step status line. Same split as
the other modules — "what to emit" vs "how to display".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import PipelineEvent


# ─── Builders (worker.py → emit("log", ...)) ──────────────────────────────────


def fmt_recipe_start(name: str, total_steps: int) -> str:
    """Log line announcing the recipe and its step count."""
    return f"[*] Receita: {name} ({total_steps} passo(s))"


def fmt_step_start(idx: int, total: int, label: str) -> str:
    """Log line announcing the step about to run."""
    return f"[~] Passo {idx}/{total}: {label}"


def fmt_step_output(name: str) -> str:
    """Indented log line for one output produced by a step."""
    return f"    [✓] {name}"


def fmt_recipe_done(n_outputs: int) -> str:
    """Summary line after the whole recipe completes."""
    return f"[✓] Receita concluída — {n_outputs} arquivo(s) final(is)."


# ─── Resolver (view.py → step status line) ────────────────────────────────────


def resolve_status(event: PipelineEvent) -> str | None:
    """Translate a PipelineEvent into the status-line text. None = no change."""
    p = event.payload
    match event.type:
        case "recipe_start":
            return "Iniciando…"
        case "step_start":
            return f"Passo {p.get('idx')}/{p.get('total')} — {p.get('label', '')}"
        case "task_done":
            return "Concluído."
        case "task_error":
            return "Erro."
        case _:
            return None
