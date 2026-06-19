"""
report.py: Render an analysis dictionary as a Markdown report from a profile.

The header (title/channel/duration/url/generated-at) and the optional
"Transcrição" appendix are profile-independent. The body iterates the profile
fields in order, dispatching by kind. The default profile's fields are tuned so
this generator reproduces the historical report byte-for-byte.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.analysis.types import (
    KIND_PARAGRAPH,
    KIND_QUOTES,
    AnalysisProfile,
    Field,
)


def _is_empty(value: object) -> bool:
    """Return True for None, blank strings and empty sequences."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return False


def _render_section(field: Field, value: object) -> list[str] | None:
    """Render one field as Markdown lines, or None when it should be omitted.

    Args:
        field: The profile field descriptor.
        value: The value read from the analysis dict for this field.

    Returns:
        The section lines (header + body) or None when the field is empty and
        not marked ``always``.
    """
    empty = _is_empty(value)
    if empty and not field.always:
        return None

    header = [f"## {field.title}", ""]

    if field.kind == KIND_PARAGRAPH:
        text = field.empty_text if empty else str(value)
        return header + ([text] if text else [])

    items = [] if empty else list(value)  # type: ignore[arg-type]

    if field.kind == KIND_QUOTES:
        body: list[str] = []
        for quote in items:
            body.append(f"> {quote}")
            body.append("")
        if not items and field.empty_text:
            body = [field.empty_text]
        return header + body

    # list / keyvalue — bullet list of raw strings
    if items:
        body = [f"- {item}" for item in items]
    elif field.empty_text:
        body = [field.empty_text]
    else:
        body = []
    return header + body


def format_report(
    profile: AnalysisProfile,
    analysis: dict,
    source_path: Path,
    video_meta: dict | None = None,
    transcription: str | None = None,
) -> str:
    """Format the analysis dictionary as a Markdown report for *profile*.

    Args:
        profile: The active analysis profile (drives the body sections).
        analysis: Dictionary keyed by the profile field keys.
        source_path: Path to the original transcription/source file.
        video_meta: Parsed metadata from the source header (optional).
        transcription: Formatted transcription body to append (optional).

    Returns:
        Formatted Markdown string.
    """
    video_meta = video_meta or {}
    title = video_meta.get("title") or f"Análise: {source_path.stem}"
    channel = video_meta.get("channel", "")
    duration = video_meta.get("duration", "")
    url = video_meta.get("url", "")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [f"# {title}", ""]

    meta_parts = []
    if channel:
        meta_parts.append(f"**Canal:** {channel}")
    if duration:
        meta_parts.append(f"**Duração:** {duration}")
    if meta_parts:
        lines.append(" | ".join(meta_parts))
    if url:
        lines.append(f"[Assistir no YouTube]({url})")

    lines.extend(
        [
            "",
            f"> Gerado em: {generated_at} | Fonte: `{source_path.name}`",
            "",
            "---",
            "",
        ]
    )

    if profile.disclaimer:
        lines.extend([f"> {profile.disclaimer}", "", "---", ""])

    sections = []
    for field in profile.fields:
        rendered = _render_section(field, analysis.get(field.key))
        if rendered is not None:
            sections.append(rendered)
    for i, section in enumerate(sections):
        if i > 0:
            lines.append("")
        lines.extend(section)

    if transcription:
        lines.extend(["", "---", "", "## Transcrição", "", transcription])

    lines.append("")
    return "\n".join(lines)
