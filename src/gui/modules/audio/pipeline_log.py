"""Vocabulário de mensagens do pipeline de áudio.

Importado por:
  worker.py  — fmt_* para emit("log", ...)
  view.py    — resolve_* para PipelineEvent → display (via progress_view.py)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import PipelineEvent


# ─── Constantes ────────────────────────────────────────────────────────────────

_TARGET_TP = -1.0  # True Peak máximo (dBFS) — espelhado do normalizer
_TARGET_LRA = 11.0  # Loudness Range alvo

OP_VERBS: dict[str, str] = {
    "download": "Baixando",
    "convert": "Convertendo",
    "extract": "Extraindo áudio",
    "denoise": "Reduzindo ruído",
    "normalize": "Normalizando volume",
    "encode": "Reencodando saída",
}

OP_LABELS: dict[str, str] = {
    "download": "Baixando...",
    "convert": "Convertendo...",
    "extract": "Extraindo áudio...",
    "denoise": "Reduzindo ruído (spectral)...",
    "normalize": "Normalizando (loudnorm — 2 passes)...",
    "encode": "Reencodando saída...",
}


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1_048_576:
        return f"{b / 1024:.0f} KB"
    return f"{b / 1_048_576:.1f} MB"


def _relative_output_dir(path_str: str) -> str:
    try:
        parts = Path(path_str).parent.parts
        idx = next(i for i, p in enumerate(parts) if p == "output")
        return "/".join(parts[idx:]) + "/"
    except (StopIteration, Exception):
        return str(Path(path_str).parent)


# ─── Builders — informação geral ──────────────────────────────────────────────


def fmt_ffmpeg_progress(ratio: float) -> str:
    """Linha dinâmica (mutable) de progresso ffmpeg: [d] X%"""
    return f"[d] {int(ratio * 100)}%"


def fmt_audio_info(name: str, duration: float | None, size_bytes: int) -> str:
    dur = f"{duration:.1f}s" if duration else "duração desconhecida"
    return f"[i] {name} | {dur} | {_fmt_size(size_bytes)}"


# ─── Builders — denoise ────────────────────────────────────────────────────────


def fmt_denoise_start(name: str) -> str:
    return f"[*] Spectral gating: {name}…"


def fmt_denoise_detail(stationary: bool) -> str:
    mode = "estacionário (rápido)" if stationary else "adaptativo (mais lento)"
    return f"[i] Modo: {mode}"


# ─── Builders — encode final ──────────────────────────────────────────────────


def fmt_encode_start(name: str, fmt: str) -> str:
    return f"[*] Reencodando para .{fmt}: {name}…"


def fmt_encode_detail(channels: int | None, sample_rate: int | None) -> str:
    parts: list[str] = []
    parts.append(
        "mono"
        if channels == 1
        else f"{channels} canais"
        if channels
        else "canais preservados"
    )
    if sample_rate:
        parts.append(f"{sample_rate / 1000:.0f} kHz")
    return f"[i] Saída: {' · '.join(parts)}"


# ─── Builders — normalize ─────────────────────────────────────────────────────


def fmt_normalize_start(name: str) -> str:
    return f"[*] Loudnorm — passe 1 (medição): {name}…"


def fmt_normalize_detail(target_lufs: float) -> str:
    return f"[i] Alvo: {target_lufs:.1f} LUFS | TP: {_TARGET_TP} dBFS | LRA: {_TARGET_LRA} LU"


def fmt_normalize_measured(stats: dict) -> str:
    il = stats.get("input_i", "?")
    lra = stats.get("input_lra", "?")
    tp = stats.get("input_tp", "?")
    return f"[i] Medido: IL={il} LUFS | LRA={lra} LU | TP={tp} dBTP"


def fmt_normalize_apply(name: str) -> str:
    return f"[*] Loudnorm — passe 2 (aplicação): {name}…"


def fmt_normalize_fallback() -> str:
    return "[»] Medição indisponível — usando passo único (menos preciso)"


# ─── Resolvers (progress_view.py) ─────────────────────────────────────────────


def resolve_messages(event: "PipelineEvent") -> list[str]:
    """Traduz um PipelineEvent nas linhas de log a exibir no painel de áudio."""
    p = event.payload
    match event.type:
        case "audio_op_start":
            op = p.get("operation", "")
            name = p.get("item_name", "")
            verb = OP_VERBS.get(op, "Processando")
            return [f"[~] {verb}: {name}"]
        case "audio_op_done":
            path = p.get("output_path", "")
            elapsed = p.get("elapsed", "")
            idx = p.get("item_idx", 1)
            total = p.get("total", 1)
            src_sz = p.get("src_size_bytes", 0)
            out_sz = p.get("out_size_bytes", 0)
            name = Path(path).name if path else path
            sz = (
                f" | {_fmt_size(src_sz)} → {_fmt_size(out_sz)}"
                if src_sz and out_sz
                else ""
            )
            prefix = f"{idx}/{total} — " if total > 1 else ""
            folder = _relative_output_dir(path)
            return [
                f"[✓] {prefix}Salvo: {name} ({elapsed}){sz}",
                f"[i] Pasta: {folder}",
            ]
        case "task_done":
            paths = p.get("output_paths", [])
            return [f"[✓] Concluído — {len(paths)} arquivo(s) gerado(s)."]
        case "task_error":
            return [f"[!] {p.get('message', 'erro desconhecido')}"]
        case "log":
            msg = p.get("message", "")
            return [msg] if msg else []
        case _:
            return []


def resolve_stage_label(event: "PipelineEvent") -> str | None:
    """Traduz um PipelineEvent no texto do stage label. None = sem alteração."""
    p = event.payload
    match event.type:
        case "progress_start":
            return "Iniciando..."
        case "queue_progress":
            cur = p.get("current_item", "?")
            tot = p.get("total_items", "?")
            name = p.get("item_name", "")
            return f"Item {cur}/{tot}" + (f" — {name}" if name else "")
        case "audio_op_start":
            return OP_LABELS.get(p.get("operation", ""), "Processando...")
        case "audio_op_done":
            idx = p.get("item_idx", 1)
            tot = p.get("total", 1)
            return f"Item {idx}/{tot} concluído." if tot > 1 else "Concluído."
        case "task_done":
            return "Pipeline concluído!"
        case "task_error":
            return "Erro no pipeline."
        case _:
            return None
