"""Read/write cloud API keys in the project's .env (Transcription form helper).

Extracted from ``form_view`` (divide-se ao tocar) so the form builder stays under
the size budget while the 4B profile-suggestion block is added. Pure file I/O,
no Flet.
"""

from __future__ import annotations

from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _read_env_var(name: str) -> str:
    """Read a KEY=value line from the project root .env (empty if absent)."""
    if not _ENV_FILE.exists():
        return ""
    prefix = f"{name}="
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    return ""


def _write_env_var(name: str, value: str) -> None:
    """Write or update a KEY=value line in the project root .env (no-op if empty)."""
    if not value:
        return
    lines = (
        _ENV_FILE.read_text(encoding="utf-8").splitlines() if _ENV_FILE.exists() else []
    )
    prefix = f"{name}="
    key_line = f"{name}={value}"
    updated = [key_line if line.startswith(prefix) else line for line in lines]
    if not any(line.startswith(prefix) for line in lines):
        updated.append(key_line)
    _ENV_FILE.write_text("\n".join(updated) + "\n", encoding="utf-8")


def read_api_key() -> str:
    """Read GOOGLE_API_KEY from the project root .env (empty if absent)."""
    return _read_env_var("GOOGLE_API_KEY")


def write_api_key(value: str) -> None:
    """Write or update GOOGLE_API_KEY in the project root .env (no-op if empty)."""
    _write_env_var("GOOGLE_API_KEY", value)


def read_glm_api_key() -> str:
    """Read ZHIPU_API_KEY from the project root .env (empty if absent)."""
    return _read_env_var("ZHIPU_API_KEY")


def write_glm_api_key(value: str) -> None:
    """Write or update ZHIPU_API_KEY in the project root .env (no-op if empty)."""
    _write_env_var("ZHIPU_API_KEY", value)
