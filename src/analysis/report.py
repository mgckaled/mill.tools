"""
report.py: Render an analysis dictionary as a Markdown report from a profile.

The header (title/channel/duration/url/generated-at) and the optional
"Transcrição" appendix are profile-independent. The body iterates the profile
fields in order, dispatching by kind. The default profile's fields are tuned so
this generator reproduces the historical report byte-for-byte.

Local models occasionally deviate from the requested JSON shape (a string
where a list was expected, a dict for a "term: definition" list, a stray
"..." placeholder echoed from the prompt skeleton). ``_normalize_items``/
``_normalize_paragraph`` absorb that drift before rendering so a shape
mismatch degrades into a slightly odd bullet instead of silent garbage
(character-split bullets, a Python repr in the middle of the report, ...).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.analysis.types import (
    KIND_PARAGRAPH,
    KIND_QUOTES,
    AnalysisProfile,
    Field,
)

# The JSON skeleton's placeholder value (see prompts.py::_skeleton_value).
# Small models sometimes echo it back verbatim instead of real content.
_PLACEHOLDER_ECHO = "..."


def _is_empty(value: object) -> bool:
    """Return True for None, blank strings and empty sequences/mappings."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _stringify_item(item: object) -> str:
    """Coerce a single list item into a display string.

    LLMs occasionally emit a dict where a plain string was expected — most
    often a two-value {"term": ..., "definition": ...} pair. Render that as
    "term: definition"; anything else falls back to compact JSON so the
    content survives instead of printing a Python repr.
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and len(item) == 2:
        return ": ".join(str(v) for v in item.values())
    if isinstance(item, (dict, list)):
        return json.dumps(item, ensure_ascii=False)
    return str(item)


def _normalize_items(value: object) -> list[str]:
    """Coerce *value* into a list of display strings for a list-kind field.

    Tolerates common LLM shape drift: a bare string (should have been a
    list) becomes a single-item list instead of being split character by
    character; a dict (should have been a list of "term: definition"
    entries) becomes one bullet per key. Blank items and echoed
    ``"..."`` placeholders are dropped.
    """
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, dict):
        items = [f"{k}: {v}" for k, v in value.items()]
    else:
        items = [_stringify_item(item) for item in value]
    return [item for item in items if item.strip() not in ("", _PLACEHOLDER_ECHO)]


def _normalize_paragraph(value: object) -> str:
    """Coerce *value* into a single paragraph string.

    Tolerates a list/dict where a paragraph was expected — joins entries
    instead of printing a Python repr — and collapses an echoed ``"..."``
    placeholder to an empty string.
    """
    if isinstance(value, (list, tuple)):
        text = "\n\n".join(_stringify_item(item) for item in value)
    elif isinstance(value, dict):
        text = "\n\n".join(f"{k}: {v}" for k, v in value.items())
    else:
        text = str(value)
    return "" if text.strip() == _PLACEHOLDER_ECHO else text


def _strip_leading_bullet(text: str) -> str:
    """Strip a leading "- " so an already-bulleted item doesn't double up."""
    return text[2:] if text.startswith("- ") else text


def _render_section(field: Field, analysis: dict) -> list[str] | None:
    """Render one field as Markdown lines, or None when it should be omitted.

    Args:
        field: The profile field descriptor.
        analysis: The full analysis dict (presence of the key matters for the
            paragraph fallback — a missing key uses ``empty_text``, while a
            present-but-blank value renders as-is, mirroring the legacy report).

    Returns:
        The section lines (header + body) or None when the field is empty and
        not marked ``always``.
    """
    present = field.key in analysis
    raw_value = analysis.get(field.key)
    is_paragraph = field.kind == KIND_PARAGRAPH

    if raw_value is None:
        value = None
    elif is_paragraph:
        value = _normalize_paragraph(raw_value)
    else:
        value = _normalize_items(raw_value)

    empty = _is_empty(value)
    if empty and not field.always:
        return None

    header = [f"## {field.title}", ""]

    if is_paragraph:
        if field.always:
            # Missing key -> placeholder; present (even blank) -> one value line.
            text = value if present else field.empty_text
            return header + [text if text is not None else ""]
        return header + [value]

    if field.kind == KIND_QUOTES:
        quote_items = [] if empty else value
        body: list[str] = []
        for quote in quote_items:
            for line in quote.splitlines() or [""]:
                body.append(f"> {line}")
            body.append("")
        if not quote_items and field.empty_text:
            body = [field.empty_text]
        return header + body

    # list / keyvalue — bullet list of strings
    items = [] if empty else [_strip_leading_bullet(item) for item in value]
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
        rendered = _render_section(field, analysis)
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
