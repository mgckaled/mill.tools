"""Carregamento de assets para uso na GUI (ft.Image e page.window.icon)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# src/gui/assets.py -> parents[2] = raiz do projeto
_ROOT = Path(__file__).resolve().parents[2]
_LOGO_DIR = _ROOT / "assets" / "logo"
_ICONS_DIR = _ROOT / "assets" / "icons"

#: Caminho absoluto para o .ico — use em page.window.icon (Windows-only)
WINDOW_ICON = str(_ICONS_DIR / "mill.ico")


@lru_cache(maxsize=None)
def b64(name: str) -> bytes:
    """Lê assets/logo/<name> e devolve bytes crus (cacheado).

    Flet 0.85+: ft.Image(src=bytes) aceita bytes diretamente — sem src_base64.
    """
    return (_LOGO_DIR / name).read_bytes()
