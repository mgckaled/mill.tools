"""Vocabulário de mensagens do pipeline de documentos.

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
    "merge":         "Unindo documentos",
    "split":         "Dividindo documento",
    "compress":      "Comprimindo",
    "rotate":        "Girando",
    "watermark":     "Aplicando marca d'água",
    "stamp":         "Aplicando carimbo",
    "encrypt":       "Criptografando",
    "extract":       "Extraindo texto",
    "pdf_to_images": "Rasterizando",
    "images_to_pdf": "Convertendo imagens",
    "analyze":       "Analisando",
    "qr":            "Gerando QR code",
}

OP_LABELS: dict[str, str] = {
    "merge":         "Unindo documentos...",
    "split":         "Dividindo documento...",
    "compress":      "Comprimindo...",
    "rotate":        "Girando páginas...",
    "watermark":     "Marca d'água...",
    "stamp":         "Aplicando carimbo...",
    "encrypt":       "Criptografando...",
    "extract":       "Extraindo texto...",
    "pdf_to_images": "Rasterizando páginas...",
    "images_to_pdf": "Convertendo imagens...",
    "analyze":       "Analisando documento...",
    "qr":            "Gerando QR code...",
}

# Operations classified by viewer mode
_VISUAL_OPS     = {"rotate", "watermark", "stamp"}
_STRUCTURAL_OPS = {"merge", "split", "compress", "encrypt"}
_SINGLE_OPS     = {"pdf_to_images", "images_to_pdf", "extract", "analyze", "qr"}


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


# ─── Builder genérico ──────────────────────────────────────────────────────────

def fmt_op_start(
    operation: str,
    item_name: str,
    item_idx: int,
    total: int,
    page_count: int = 0,
) -> str:
    """[i] item info line emitted at the start of each operation."""
    verb = OP_VERBS.get(operation, "Processando")
    pages = f" · {page_count} pág." if page_count > 0 else ""
    prefix = f"{item_idx}/{total} — " if total > 1 else ""
    return f"[i] {prefix}{item_name}{pages}"


def fmt_op_done(
    operation: str,
    output_path: str,
    elapsed: str,
    extra_stats: dict | None = None,
) -> list[str]:
    """[✓] completion lines with operation-specific extra stats."""
    stats = extra_stats or {}
    name = Path(output_path).name if output_path else output_path
    lines: list[str] = []

    match operation:
        case "merge":
            page_total = stats.get("page_total", 0)
            file_count = stats.get("file_count", 0)
            pages_str = f" · {page_total} páginas" if page_total else ""
            files_str = f" · {file_count} arquivos" if file_count else ""
            lines.append(f"[✓] {name}{files_str}{pages_str} ({elapsed})")
        case "split":
            out_files: list[str] = stats.get("output_files", [])
            page_counts: list[int] = stats.get("page_counts", [])
            lines.append(f"[✓] {len(out_files)} arquivo(s) gerado(s) ({elapsed})")
            for fname, n_pages in zip(out_files, page_counts):
                lines.append(f"[»] {fname}  ·  {n_pages} pág.")
        case "compress":
            pct = stats.get("size_reduction_pct", 0.0)
            lines.append(f"[✓] {name} · −{pct:.0f}% ({elapsed})")
        case "encrypt":
            lines.append(f"[✓] {name} · Documento protegido com senha ({elapsed})")
        case "pdf_to_images":
            img_count = stats.get("image_count", 0)
            resolution = stats.get("resolution", "")
            res_str = f" · {resolution}px" if resolution else ""
            lines.append(f"[✓] {img_count} imagem(ns) gerada(s){res_str} ({elapsed})")
        case "extract":
            word_count = stats.get("word_count", 0)
            lines.append(f"[✓] {name} · ~{word_count} palavras ({elapsed})")
        case "qr":
            preview = stats.get("qr_data_preview", "")
            if preview:
                lines.append(f"[»] Conteúdo: {preview}")
            lines.append(f"[✓] {name} ({elapsed})")
        case _:
            lines.append(f"[✓] {name} ({elapsed})")

    folder = _relative_output_dir(output_path)
    lines.append(f"[i] Pasta: {folder}")
    return lines


def fmt_op_error(item_name: str, message: str) -> str:
    return f"[!] Erro em '{item_name}': {message}"


# ─── Builders específicos por operação ────────────────────────────────────────

def fmt_merge_detail(file_count: int, total_pages: int) -> str:
    return f"[i] {file_count} arquivos · {total_pages} páginas no total"


def fmt_split_detail(filename: str, page_count: int, spec: str) -> str:
    return f"[i] {filename} · {page_count} páginas\n[~] Extraindo páginas {spec}…"


def fmt_compress_detail(filename: str, page_count: int, src_mb: float, quality: int) -> str:
    return (
        f"[i] {filename} · {page_count} páginas · {src_mb:.1f} MB\n"
        f"[~] Recomprimindo imagens embutidas (qualidade {quality}%)…"
    )


def fmt_rotate_detail(filename: str, page_count: int, pages_desc: str, angle: int) -> str:
    return (
        f"[i] {filename} · {page_count} páginas\n"
        f"[~] Girando {pages_desc} em {angle}°…"
    )


def fmt_watermark_detail(filename: str, page_count: int, text: str, pct: int) -> str:
    return (
        f"[i] {filename} · {page_count} páginas\n"
        f'[~] Aplicando marca d\'água "{text}" em todas as páginas (opacidade {pct}%)…'
    )


def fmt_stamp_detail(filename: str, page_count: int, text: str) -> str:
    return (
        f"[i] {filename} · {page_count} páginas\n"
        f'[~] Aplicando carimbo "{text}" em todas as páginas…'
    )


def fmt_encrypt_detail(filename: str, page_count: int, src_mb: float) -> str:
    return (
        f"[i] {filename} · {page_count} páginas · {src_mb:.1f} MB\n"
        f"[~] Criptografando documento…"
    )


def fmt_pdf_to_images_progress(current: int, total: int) -> str:
    """Mutable progress line during rasterization."""
    return f"[~] Rasterizando página {current}/{total}…"


def fmt_images_to_pdf_progress(filename: str, current: int, total: int) -> str:
    """Mutable progress line while adding images."""
    return f"[*] Adicionando {filename} ({current}/{total})…"


def fmt_extract_detail(filename: str, page_count: int) -> str:
    return f"[i] {filename} · {page_count} páginas\n[~] Extraindo texto…"


def fmt_qr_detail(data_preview: str, size: int) -> str:
    return f"[~] Gerando QR code…\n[»] Conteúdo: {data_preview}\n[»] {size}×{size}px"


# ─── Resolvers (view.py) ──────────────────────────────────────────────────────

def resolve_messages(event: "PipelineEvent") -> list[str]:
    """Translate a PipelineEvent into log lines to display in the panel."""
    p = event.payload
    t = event.type
    match t:
        case "document_op_start":
            op = p.get("operation", "")
            name = p.get("item_name", "")
            verb = OP_VERBS.get(op, "Processando")
            return [f"[~] {verb}: {name}"]
        case "document_op_done":
            path = p.get("output_path", "")
            elapsed = p.get("elapsed", "")
            op = p.get("operation", "")
            extra = p.get("extra_stats", {})
            return fmt_op_done(op, path, elapsed, extra)
        case "document_op_error":
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
    """Translate a PipelineEvent into the stage label text. None = no change."""
    p = event.payload
    match event.type:
        case "progress_start":
            return "Iniciando..."
        case "queue_progress":
            cur = p.get("current_item", "?")
            tot = p.get("total_items", "?")
            name = p.get("item_name", "")
            return f"Item {cur}/{tot}" + (f" — {name}" if name else "")
        case "document_op_start":
            return OP_LABELS.get(p.get("operation", ""), "Processando...")
        case "document_op_done":
            idx = p.get("item_idx", 1)
            tot = p.get("total", 1)
            return f"Item {idx}/{tot} concluído." if tot > 1 else "Concluído."
        case "document_op_error":
            return "Erro — continuando..."
        case "task_done":
            return "Pipeline concluído!"
        case "task_error":
            return "Erro no pipeline."
        case _:
            return None
