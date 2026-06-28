"""Read/write GOOGLE_API_KEY in the project's .env (Transcription form helper).

Extracted from ``form_view`` (divide-se ao tocar) so the form builder stays under
the size budget while the 4B profile-suggestion block is added. Pure file I/O,
no Flet.
"""

from __future__ import annotations

from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def read_api_key() -> str:
    """Read GOOGLE_API_KEY from the project root .env (empty if absent)."""
    if not _ENV_FILE.exists():
        return ""
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def write_api_key(value: str) -> None:
    """Write or update GOOGLE_API_KEY in the project root .env (no-op if empty)."""
    if not value:
        return
    lines = (
        _ENV_FILE.read_text(encoding="utf-8").splitlines() if _ENV_FILE.exists() else []
    )
    key_line = f"GOOGLE_API_KEY={value}"
    updated = [
        key_line if line.startswith("GOOGLE_API_KEY=") else line for line in lines
    ]
    if not any(line.startswith("GOOGLE_API_KEY=") for line in lines):
        updated.append(key_line)
    _ENV_FILE.write_text("\n".join(updated) + "\n", encoding="utf-8")
