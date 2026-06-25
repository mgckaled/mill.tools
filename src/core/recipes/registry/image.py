"""Image step adapters for the recipe registry."""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import KIND_IMAGE, StepContext, StepSpec


def _image_convert(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """image → re-encoded image. Wraps convert_image."""
    from src.core.image.converter import convert_image
    from src.utils import IMAGE_PROCESSED_DIR

    out = convert_image(
        Path(inputs[0]),
        IMAGE_PROCESSED_DIR,
        fmt=params.get("fmt", "webp"),
        quality=params.get("quality", 90),
    )
    return [out]


def _image_resize(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """image → resized image. Wraps resize_image."""
    from src.core.image.transform import resize_image
    from src.utils import IMAGE_PROCESSED_DIR

    out = resize_image(
        Path(inputs[0]),
        IMAGE_PROCESSED_DIR,
        resize_mode=params.get("resize_mode", "contain"),
        width=params.get("width"),
        height=params.get("height"),
        scale_pct=params.get("scale_pct", 100.0),
        out_fmt=params.get("out_fmt"),
        quality=params.get("quality", 90),
    )
    return [out]


IMAGE_STEPS: dict[str, StepSpec] = {
    "image.convert": StepSpec(
        _image_convert, frozenset({KIND_IMAGE}), KIND_IMAGE, "Converter imagem"
    ),
    "image.resize": StepSpec(
        _image_resize, frozenset({KIND_IMAGE}), KIND_IMAGE, "Redimensionar imagem"
    ),
}
