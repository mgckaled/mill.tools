"""Vocabulary of messages for the transcription pipeline.

Imported by:
  progress_view.py — resolve_* translates PipelineEvent → display text
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import PipelineEvent


def _fmt_dur(seconds: int | float) -> str:
    from src.core.metadata import format_duration
    return format_duration(int(seconds))


# ---------------------------------------------------------------------------
# resolve_messages
# ---------------------------------------------------------------------------

def resolve_messages(event: "PipelineEvent") -> list[str]:
    """Translate a PipelineEvent into zero or more log lines for the transcription panel."""
    p = event.payload
    match event.type:
        case "metadata_start":
            return ["[i] Fetching video metadata..."]
        case "metadata_done":
            title = p.get("title", "")
            dur = p.get("duration", 0)
            lines = []
            if title:
                lines.append(f"[i] Title: {title}")
            lines.append(f"[i] Duration: {_fmt_dur(dur)}")
            return lines
        case "audio_cached":
            path = p.get("audio_path", "")
            name = Path(path).name if path else path
            return [f"[»] Audio already exists, skipping download: {name}"]
        case "download_start":
            return ["[i] Downloading audio..."]
        case "download_done":
            path = p.get("audio_path", "")
            name = Path(path).name if path else path
            return [f"[✓] Audio downloaded: {name}"]
        case "whisper_loading":
            model = p.get("model_size", "?")
            device = p.get("device", "?").upper()
            ctype = p.get("compute_type", "?")
            return [f"[*] Loading model '{model}' on {device} ({ctype})..."]
        case "whisper_loaded":
            elapsed = p.get("elapsed", 0)
            return [f"[d] Model loaded in {elapsed:.1f}s"]
        case "transcribe_started":
            return ["[~] Transcribing... (this may take a while for long videos)"]
        case "language_detected":
            if event.stage == "transcribe":
                lang = p.get("language", "?")
                conf = p.get("confidence", 0)
                return [f"[i] Detected language: {lang} ({conf * 100:.0f}% confidence)"]
            else:
                lang = p.get("lang", p.get("language", "?"))
                return [
                    "[~] Detecting analysis language...",
                    f"[i] Detected language: {lang}",
                ]
        case "transcribe_segment":
            text = p.get("text", "").strip()
            if not text:
                return []
            suffix = " [?]" if p.get("is_low_confidence") else ""
            return [f"{text}{suffix}"]
        case "transcribe_done":
            lines = ["[✓] Transcription saved"]
            flagged = p.get("flagged_count", 0)
            if flagged:
                lines.append(
                    f"[!] {flagged} segment(s) flagged as low-confidence [?] — review recommended"
                )
            return lines
        case "transcribe_summary":
            return []
        case "format_started":
            name = p.get("filename", "")
            model = p.get("model_name", "")
            lines = []
            if name:
                lines.append(f"[*] Formatting: {name}")
            if model:
                lines.append(f"[*] Format model: {model}")
            return lines or ["[*] Formatting..."]
        case "format_chunk_start":
            i = p.get("i", "?")
            total = p.get("total", "?")
            return [f"[~] Formatting chunk {i}/{total}..."]
        case "format_chunk_done":
            i = p.get("i", "?")
            elapsed = p.get("elapsed", 0)
            return [f"[d] Chunk {i} done in {elapsed:.1f}s"]
        case "format_done":
            elapsed = p.get("elapsed", 0)
            return [f"[✓] Formatted in place ({elapsed:.0f}s)"]
        case "analyze_started":
            name = p.get("filename", "")
            model = p.get("model_name", "")
            lines = []
            if name:
                lines.append(f"[*] Analyzing: {name}")
            if model:
                lines.append(f"[*] Model: {model}")
            return lines or ["[*] Analyzing..."]
        case "analyze_chunk_start":
            i = p.get("i", "?")
            total = p.get("total", "?")
            return [f"[~] Analyzing chunk {i}/{total}..."]
        case "analyze_chunk_done":
            i = p.get("i", "?")
            elapsed = p.get("elapsed", 0)
            return [f"[d] Chunk {i} done in {elapsed:.1f}s"]
        case "analyze_merge_start":
            n = p.get("total_chunks", "?")
            return [f"[~] Merging {n} partial analyses..."]
        case "translation_start":
            return ["[~] Translating analysis to PT-BR..."]
        case "translation_done":
            return ["[✓] Translation complete."]
        case "analyze_done":
            path = p.get("output_path", "")
            elapsed = p.get("elapsed", 0)
            name = Path(path).name if path else ""
            return [f"[✓] Analysis saved to: {name} ({elapsed:.0f}s)"]
        case "prompt_started":
            name = p.get("filename", "")
            model = p.get("model_name", "")
            lines = []
            if name:
                lines.append(f"[*] Building prompt-ready: {name}")
            if model:
                lines.append(f"[*] Prompt model: {model}")
            return lines or ["[*] Building prompt-ready..."]
        case "prompt_chunk_start":
            i = p.get("i", "?")
            total = p.get("total", "?")
            return [f"[~] Condensing chunk {i}/{total}..."]
        case "prompt_chunk_done":
            i = p.get("i", "?")
            elapsed = p.get("elapsed", 0)
            return [f"[d] Chunk {i} done in {elapsed:.1f}s"]
        case "prompt_done":
            path = p.get("output_path", "")
            elapsed = p.get("elapsed", 0)
            name = Path(path).name if path else ""
            return [f"[✓] Prompt-ready saved to: {name} ({elapsed:.0f}s)"]
        case "pipeline_done":
            return ["[✓] Pipeline complete."]
        case "pipeline_error":
            msg = p.get("message", "erro desconhecido")
            return [f"[!] Error: {msg}"]
        case _:
            return []


# ---------------------------------------------------------------------------
# resolve_stage_label
# ---------------------------------------------------------------------------

def resolve_stage_label(event: "PipelineEvent") -> str | None:
    """Translate a PipelineEvent into a stage label string. None = no change."""
    match event.type:
        case "metadata_start":
            return "Buscando metadados..."
        case "audio_cached":
            return "Áudio em cache."
        case "download_start":
            return "Baixando áudio..."
        case "download_done":
            return "Áudio pronto."
        case "whisper_loading":
            return "Carregando modelo Whisper..."
        case "transcribe_started":
            return "Transcrevendo..."
        case "format_started":
            return "Formatando parágrafos..."
        case "analyze_started":
            return "Analisando..."
        case "analyze_merge_start":
            return "Consolidando análises..."
        case "translation_start":
            return "Traduzindo para PT-BR..."
        case "prompt_started":
            return "Gerando prompt-ready..."
        case "pipeline_done":
            return "Pipeline concluído!"
        case "pipeline_error":
            return "Erro no pipeline."
        case _:
            return None
