"""Carregamento de assets de branding para uso em ft.Image (src aceita bytes)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# src/gui/assets.py -> parents[2] = raiz do projeto
_BRANDING = Path(__file__).resolve().parents[2] / "branding"


@lru_cache(maxsize=None)
def b64(name: str) -> bytes:
    """Lê branding/<name> e devolve bytes crus (cacheado).

    Flet 0.85+: ft.Image(src=bytes) aceita bytes diretamente — sem src_base64.
    """
    return (_BRANDING / name).read_bytes()
