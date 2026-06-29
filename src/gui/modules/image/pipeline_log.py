"""Vocabulário de mensagens do pipeline de imagens.

Único lugar para ajustar cópia de log, stage labels e formatações.
Importado por:
  worker.py  — fmt_* constrói strings para emit("log", ...)
  view.py    — resolve_* traduz PipelineEvent → texto de display
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import PipelineEvent


# ─── Constantes ────────────────────────────────────────────────────────────────

OP_VERBS: dict[str, str] = {
    "download": "Baixando",
    "convert": "Convertendo",
    "resize": "Redimensionando",
    "crop": "Cortando",
    "rotate": "Rotacionando",
    "watermark": "Aplicando marca d'água",
    "border": "Adicionando borda",
    "adjust": "Ajustando",
    "filter": "Aplicando filtro",
    "favicon": "Gerando favicon",
    "contact_sheet": "Montando colagem",
    "remove_bg": "Removendo fundo",
    "describe": "Analisando",
}

OP_LABELS: dict[str, str] = {
    "download": "Baixando...",
    "convert": "Convertendo...",
    "resize": "Redimensionando...",
    "crop": "Cortando...",
    "rotate": "Rotacionando...",
    "watermark": "Marca d'água...",
    "border": "Adicionando borda...",
    "adjust": "Ajustando...",
    "filter": "Aplicando filtro...",
    "favicon": "Gerando favicon...",
    "contact_sheet": "Montando colagem...",
    "remove_bg": "Removendo fundo (ONNX/CPU)...",
    "describe": "Analisando imagem (Ollama)…",
}


# ─── Helper interno ────────────────────────────────────────────────────────────


def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b / (1024 * 1024):.1f} MB"


def _relative_output_dir(path_str: str) -> str:
    """Retorna o diretório de saída a partir de 'output/', com barras /."""
    try:
        parts = Path(path_str).parent.parts
        idx = next(i for i, p in enumerate(parts) if p == "output")
        return "/".join(parts[idx:]) + "/"
    except (StopIteration, Exception):
        return str(Path(path_str).parent)


# ─── Builder genérico ──────────────────────────────────────────────────────────


def fmt_image_info(
    name: str, width: int, height: int, mode: str, size_bytes: int
) -> str:
    """[i] nome | WxH px | MODE | tamanho"""
    return f"[i] {name} | {width}×{height} px | {mode} | {_fmt_size(size_bytes)}"


def _dims_label(w: int, h: int, fmt: str | None, size_bytes: int) -> str:
    """'1920×1080 PNG 2.3 MB' — omits unknown parts (zero dims / size)."""
    parts: list[str] = []
    if w and h:
        parts.append(f"{w}×{h}")
    if fmt:
        parts.append(fmt.upper())
    if size_bytes:
        parts.append(_fmt_size(size_bytes))
    return " ".join(parts)


def fmt_meta_strip(
    src_w: int,
    src_h: int,
    src_fmt: str | None,
    src_size: int,
    out_w: int,
    out_h: int,
    out_fmt: str | None,
    out_size: int,
) -> str:
    """Before→after metadata line for the viewer, e.g. '1920×1080 PNG 2.3 MB → 800×450 JPG 120 KB'."""
    left = _dims_label(src_w, src_h, src_fmt, src_size)
    right = _dims_label(out_w, out_h, out_fmt, out_size)
    if left and right:
        return f"{left}  →  {right}"
    return right or left


# ─── Builders por operação ─────────────────────────────────────────────────────


def fmt_convert_detail(src_fmt: str | None, tgt_fmt: str) -> str:
    return f"[i] {(src_fmt or '?').upper()} → {tgt_fmt.upper()}"


def fmt_resize_detail(
    mode: str,
    w_in: int,
    h_in: int,
    w_out: int | None,
    h_out: int | None,
    scale_pct: float,
) -> str:
    mode_labels = {"contain": "Caber", "exact": "Exato", "scale_pct": "Escala %"}
    label = mode_labels.get(mode, mode)
    if mode == "scale_pct":
        return f"[i] Modo: {label} {scale_pct:.0f}%"
    parts = [f"L={w_out}"] if w_out else []
    if h_out:
        parts.append(f"A={h_out}")
    limit = ", ".join(parts) if parts else "proporções preservadas"
    return f"[i] Modo: {label} | Limite: {limit}"


def fmt_crop_detail(
    mode: str,
    left: int = 0,
    top: int = 0,
    width: int = 0,
    height: int = 0,
    ratio: str = "1:1",
    trim_color: str = "#ffffff",
) -> str:
    match mode:
        case "manual":
            w_str = str(width) if width else "∞"
            h_str = str(height) if height else "∞"
            return f"[i] Corte manual: origem ({left},{top}) | {w_str}×{h_str} px"
        case "ratio":
            return f"[i] Proporção {ratio} — maior retângulo centralizado"
        case "autotrim":
            return f"[i] Auto-trim — removendo bordas {trim_color}"
        case _:
            return f"[i] Corte: {mode}"


def fmt_rotate_detail(angle: int, flip_h: bool, flip_v: bool, exif_auto: bool) -> str:
    parts = []
    if angle:
        parts.append(f"{angle}° horário")
    if flip_h:
        parts.append("espelhar H")
    if flip_v:
        parts.append("espelhar V")
    if exif_auto:
        parts.append("corr. EXIF")
    body = " | ".join(parts) if parts else "nenhuma"
    return f"[i] Transformação: {body}"


def fmt_watermark_detail(mode: str, position: str, opacity: float) -> str:
    pos_labels = {
        "top-left": "↖ sup-esq",
        "top-right": "↗ sup-dir",
        "center": "⬤ centro",
        "bottom-left": "↙ inf-esq",
        "bottom-right": "↘ inf-dir",
    }
    pos = pos_labels.get(position, position)
    return f"[i] Modo: {mode} | Posição: {pos} | Opacidade: {int(opacity * 100)}%"


def fmt_border_detail(padding: int, color: str, fill_alpha: bool) -> str:
    extra = " | preencher alpha" if fill_alpha else ""
    return f"[i] Borda: {padding}px | Cor: {color}{extra}"


def fmt_adjust_detail(
    brightness: float, contrast: float, color: float, sharpness: float
) -> str:
    fields = {
        "Brilho": brightness,
        "Contraste": contrast,
        "Saturação": color,
        "Nitidez": sharpness,
    }
    changed = [f"{k}: {v:.1f}" for k, v in fields.items() if abs(v - 1.0) > 0.05]
    return (
        f"[i] {' | '.join(changed)}"
        if changed
        else "[i] Ajustes: todos em 1.0 (sem alteração)"
    )


def fmt_filter_detail(filter_type: str) -> str:
    labels = {
        "blur": "Blur — suavização",
        "sharpen": "Sharpen — nitidez",
        "autocontrast": "Autocontraste — estica histograma",
        "equalize": "Equalizar — redistribui histograma",
        "grayscale": "Escala de cinza",
    }
    return f"[i] Filtro: {labels.get(filter_type, filter_type)}"


def fmt_exif_detail(mode: str) -> str:
    labels = {
        "preserve": "Preservar metadados originais",
        "strip": "Remover todos os metadados",
        "strip_gps": "Remover localização (GPS)",
        "inject": "Injetar autoria/copyright",
    }
    return f"[i] EXIF: {labels.get(mode, mode)}"


def fmt_favicon_detail(sizes: list[int]) -> str:
    sizes_str = ", ".join(str(s) for s in sorted(sizes))
    return f"[i] Favicon .ico — tamanhos: {sizes_str} px"


def fmt_cs_detail(
    n_items: int, cols: int, thumb_size: int, gap: int, bg_color: str
) -> str:
    rows = (n_items + cols - 1) // cols
    return f"[i] {n_items} imgs | grade {cols}×{rows} | thumb {thumb_size}px | gap {gap}px | bg {bg_color}"


# ─── Builders rembg ───────────────────────────────────────────────────────────


def fmt_rembg_loading(model: str) -> str:
    return f"[*] Carregando modelo '{model}' (1ª vez: baixa para ~/.u2net/)…"


def fmt_rembg_loaded(model: str) -> str:
    return f"[*] Modelo '{model}' pronto."


def fmt_rembg_inferring(name: str) -> str:
    return f"[~] Inferindo ONNX: {name} (CPU, pode levar alguns segundos)…"


# ─── Builders describe ────────────────────────────────────────────────────────


def fmt_describe_header(model: str, prompt: str) -> str:
    prompt_label = "[padrão PT-BR]" if not prompt.strip() else f'"{prompt}"'
    return f"[i] Modelo: {model} | Prompt: {prompt_label}"


def fmt_describe_sep_open() -> str:
    return "[»] ─── Descrição ─────────────────────"


def fmt_describe_sep_close() -> str:
    return "[»] ──────────────────────────────────"


# ─── Resolvers (view.py) ──────────────────────────────────────────────────────


def resolve_messages(event: "PipelineEvent") -> list[str]:
    """Traduz um PipelineEvent nas linhas de log a exibir no painel."""
    p = event.payload
    t = event.type
    match t:
        case "image_op_start":
            op = p.get("operation", "")
            name = p.get("item_name", "")
            verb = OP_VERBS.get(op, "Processando")
            return [f"[~] {verb}: {name}"]
        case "image_op_done":
            path = p.get("output_path", "")
            elapsed = p.get("elapsed", "")
            idx = p.get("item_idx", 1)
            total = p.get("total_items", 1)
            name = Path(path).name if path else path
            src_sz = p.get("src_size_bytes", 0)
            out_sz = p.get("out_size_bytes", 0)
            sz = (
                f" | {_fmt_size(src_sz)} → {_fmt_size(out_sz)}"
                if src_sz and out_sz
                else ""
            )
            prefix = f"{idx}/{total} — " if total > 1 else ""
            folder = _relative_output_dir(path)
            return [
                f"[i] {prefix}Salvo: {name} ({elapsed}){sz}",
                f"[i] Pasta: {folder}",
            ]
        case "image_op_error":
            return [f"[!] Erro em '{p.get('item_name', '')}': {p.get('message', '')}"]
        case "task_done":
            paths = p.get("output_paths", [])
            failed = p.get("failed_count", 0)
            lines = [f"[✓] Concluído — {len(paths)} arquivo(s) gerado(s)."]
            if failed:
                lines.append(f"[!] {failed} item(ns) com erro.")
            return lines
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
        case "image_op_start":
            return OP_LABELS.get(p.get("operation", ""), "Processando...")
        case "image_op_done":
            idx = p.get("item_idx", 1)
            tot = p.get("total_items", 1)
            return f"Item {idx}/{tot} concluído." if tot > 1 else "Concluído."
        case "image_op_error":
            return "Erro — continuando fila..."
        case "task_done":
            return "Pipeline concluído!"
        case "task_error":
            return "Erro no pipeline."
        case _:
            return None
