"""Remoção de fundo via rembg (CPU/ONNX). Imports sempre lazy."""
from __future__ import annotations

from pathlib import Path

MODELS = ("u2net", "u2netp", "silueta", "isnet-general-use", "u2net_human_seg")

_MODEL_LABELS: dict[str, str] = {
    "u2net":             "u2net",
    "u2netp":            "u2netp",
    "silueta":           "silueta",
    "isnet-general-use": "isnet",
    "u2net_human_seg":   "humano",
}


def is_available() -> bool:
    """True se rembg + onnxruntime instalados."""
    try:
        import rembg  # noqa: F401
        return True
    except ImportError:
        return False


def create_session(model: str = "u2net"):
    """Cria sessão rembg. 1ª vez: faz download para ~/.u2net/."""
    import rembg
    return rembg.new_session(model)


def remove_background(src: Path, out_dir: Path, session) -> Path:
    """Remove fundo; salva PNG com alpha em out_dir."""
    import rembg
    from PIL import Image
    from src.core.image.transform import _out_path

    with Image.open(src) as im:
        result = rembg.remove(im, session=session)

    out_path = _out_path(src, out_dir, "png")
    result.save(out_path, format="PNG")
    return out_path
