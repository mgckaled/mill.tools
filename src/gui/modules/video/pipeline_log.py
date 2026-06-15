"""Vocabulário de mensagens do pipeline de vídeo.

Importado por:
  worker.py  — fmt_* para emit("log", ...)
  view.py    — resolve_* para PipelineEvent → display (via progress_view.py)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import PipelineEvent


OP_VERBS: dict[str, str] = {
    "download": "Baixando",
    "convert": "Convertendo",
    "trim": "Recortando",
    "compress": "Comprimindo",
    "resize": "Redimensionando",
    "extract_audio": "Extraindo áudio",
    "thumbnail": "Gerando thumbnail",
    "subtitle": "Inserindo legenda",
}

OP_LABELS: dict[str, str] = {
    "download": "Baixando vídeo...",
    "convert": "Convertendo formato...",
    "trim": "Recortando (ffmpeg)...",
    "compress": "Comprimindo (H.264/CRF)...",
    "resize": "Redimensionando...",
    "extract_audio": "Extraindo áudio...",
    "thumbnail": "Gerando thumbnail...",
    "subtitle": "Inserindo legenda...",
}


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
    except Exception:
        return str(Path(path_str).parent)


# ── Builders ──────────────────────────────────────────────────────────────────


def fmt_video_info(info) -> str:
    """[i] resolução | fps | codec_v/codec_a | duração | tamanho"""
    res = f"{info.width}×{info.height}" if info.width else "?"
    fps = f"{info.fps:.1f}fps" if info.fps else "?"
    vc = info.vcodec or "?"
    ac = info.acodec or "?"
    sz = _fmt_size(info.size_bytes)
    dur = f"{info.duration:.1f}s" if info.duration else "?"
    return f"[i] {res} | {fps} | {vc}/{ac} | {dur} | {sz}"


def fmt_download_detail(resolution: str, container: str) -> str:
    res = f"máx. {resolution}p" if resolution != "best" else "melhor disponível"
    return f"[i] Resolução: {res} | Container: {container.upper()}"


def fmt_convert_detail(vcodec: str, container: str) -> str:
    codec_labels = {
        "copy": "sem reencoding (copy)",
        "h264": "H.264 (libx264)",
        "h265": "H.265 (libx265)",
        "vp9": "VP9 (libvpx-vp9)",
    }
    return f"[i] Codec: {codec_labels.get(vcodec, vcodec)} → {container.upper()}"


def fmt_trim_detail(start: str, end: str, reenc: bool) -> str:
    s = start or "início"
    e = end or "fim"
    mode = "frame-preciso (reenc)" if reenc else "rápido (copy)"
    return f"[i] Corte: {s} → {e} | Modo: {mode}"


def fmt_compress_detail(crf: int, preset: str) -> str:
    q = "alta" if crf <= 18 else ("boa" if crf <= 23 else "comprimida")
    return f"[i] CRF: {crf} (qualidade {q}) | Preset: {preset}"


def fmt_resize_detail(width: int, height: int) -> str:
    w = str(width) if width else "auto"
    h = str(height) if height else "auto"
    return f"[i] Dimensões: {w}×{h} (aspect ratio preservado)"


def fmt_thumbnail_detail(time: str, fmt: str) -> str:
    return f"[i] Frame em {time} → .{fmt.upper()}"


def fmt_extract_audio_detail(audio_fmt: str) -> str:
    return f"[i] Formato de saída: {audio_fmt.upper()}"


def fmt_subtitle_detail(subtitle_name: str, mode: str) -> str:
    mode_label = (
        "queimada (reencoda)" if mode == "hard" else "embutida (mux, sem reencode)"
    )
    return f"[i] Legenda: {subtitle_name} | Modo: {mode_label}"


# ── Resolvers ─────────────────────────────────────────────────────────────────


def resolve_messages(event: "PipelineEvent") -> list[str]:
    """Traduz um PipelineEvent nas linhas de log a exibir no painel de vídeo."""
    p = event.payload
    match event.type:
        case "video_op_start":
            verb = OP_VERBS.get(p.get("operation", ""), "Processando")
            return [f"[~] {verb}: {p.get('item_name', '')}"]
        case "video_op_done":
            path = p.get("output_path", "")
            name = Path(path).name if path else path
            elapsed = p.get("elapsed", "")
            idx, tot = p.get("item_idx", 1), p.get("total", 1)
            src_sz = p.get("src_size_bytes", 0)
            out_sz = p.get("out_size_bytes", 0)
            sz = (
                f" | {_fmt_size(src_sz)} → {_fmt_size(out_sz)}"
                if src_sz and out_sz
                else ""
            )
            prefix = f"{idx}/{tot} — " if tot > 1 else ""
            return [
                f"[✓] {prefix}Salvo: {name} ({elapsed}){sz}",
                f"[i] Pasta: {_relative_output_dir(path)}",
            ]
        case "video_op_error":
            return [f"[!] Erro em '{p.get('item_name', '')}': {p.get('message', '')}"]
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
        case "video_op_start":
            return OP_LABELS.get(p.get("operation", ""), "Processando...")
        case "video_op_done":
            idx, tot = p.get("item_idx", 1), p.get("total", 1)
            return f"Item {idx}/{tot} concluído." if tot > 1 else "Concluído."
        case "video_op_error":
            return "Erro — continuando fila..."
        case "task_done":
            return "Pipeline concluído!"
        case "task_error":
            return "Erro no pipeline."
        case _:
            return None
