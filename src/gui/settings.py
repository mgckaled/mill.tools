"""Persistência de preferências do usuário em ~/.yt-transcriber/config.json."""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".yt-transcriber"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_DEFAULTS: dict = {
    "last_whisper_model": "small",
    "last_language": "auto",
    "last_beam_size": 1,
    "last_format_model": "phi4mini-custom",
    "last_analyzer_model": "gemini-2.5-flash",
    "last_prompt_model": "gemini-2.5-flash",
    "last_use_format": False,
    "last_use_analyze": False,
    "last_use_prompt": False,
    "theme_mode": "dark",
}


def load() -> dict:
    """Carrega configurações salvas, completando com defaults para chaves ausentes."""
    if not _CONFIG_FILE.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        return {**_DEFAULTS, **data}
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)


def save(settings: dict) -> None:
    """Persiste o dicionário de configurações no disco."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get(key: str, default=None):
    """Lê uma chave específica das configurações salvas."""
    return load().get(key, default)


def set(key: str, value) -> None:
    """Atualiza uma chave específica e persiste."""
    data = load()
    data[key] = value
    save(data)
