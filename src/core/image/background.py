"""Remoção de fundo via rembg (CPU/ONNX). Imports sempre lazy."""

from __future__ import annotations

from pathlib import Path

MODELS = ("u2net", "u2netp", "silueta", "isnet-general-use", "u2net_human_seg")

_MODEL_LABELS: dict[str, str] = {
    "u2net": "u2net",
    "u2netp": "u2netp",
    "silueta": "silueta",
    "isnet-general-use": "isnet",
    "u2net_human_seg": "humano",
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
    return replace_background(src, out_dir, session, bg_mode="transparent")


def replace_background(
    src: Path,
    out_dir: Path,
    session,
    *,
    bg_mode: str = "transparent",
    bg_color: str = "#ffffff",
    bg_blur: int = 15,
    bg_image: Path | None = None,
) -> Path:
    """Cut out the subject via rembg, then place it over a chosen background.

    Modes: transparent (PNG alpha), color (solid), blur (blurred original —
    portrait look), image (another photo, cover-fit). Non-transparent modes are
    flattened to an opaque PNG.
    """
    import rembg
    from PIL import Image, ImageFilter, ImageOps

    from src.core.image.transform import _hex_rgb, _out_path

    with Image.open(src) as im:
        original = im.convert("RGB")
        cutout = rembg.remove(im, session=session).convert("RGBA")

    if bg_mode == "transparent":
        out_path = _out_path(src, out_dir, "png")
        cutout.save(out_path, format="PNG")
        return out_path

    w, h = cutout.size
    if bg_mode == "blur":
        radius = max(1, int(bg_blur))
        bg = original.resize((w, h)).filter(ImageFilter.GaussianBlur(radius))
    elif bg_mode == "image" and bg_image is not None and Path(bg_image).exists():
        with Image.open(bg_image) as bgi:
            bg = ImageOps.fit(
                bgi.convert("RGB"), (w, h), method=Image.Resampling.LANCZOS
            )
    else:  # "color" (and fallback)
        bg = Image.new("RGB", (w, h), _hex_rgb(bg_color))

    canvas = bg.convert("RGBA")
    canvas.alpha_composite(cutout)
    out_path = _out_path(src, out_dir, "png")
    canvas.convert("RGB").save(out_path, format="PNG")
    return out_path
