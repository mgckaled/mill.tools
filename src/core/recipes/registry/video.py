"""Video step adapters for the recipe registry.

Includes ``video.subtitle`` — the only multi-input step of v1 — which recovers
the original video and the produced ``.srt`` from ``ctx``. See
``registry/__init__.py`` for the rationale on canonical output dirs.
"""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import (
    KIND_IMAGE,
    KIND_TEXT,
    KIND_URL,
    KIND_VIDEO,
    StepContext,
    StepSpec,
)


def _video_download(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """URL → video file in the canonical video/source dir. Wraps download_video."""
    from src.core.video.downloader import download_video
    from src.utils import VIDEO_SOURCE_DIR

    out = download_video(
        str(inputs[0]),
        VIDEO_SOURCE_DIR,
        resolution=params.get("resolution", "1080"),
        container=params.get("container", "mp4"),
        embed_meta=params.get("embed_meta", True),
        progress_hook=lambda d: ctx.emit("progress_update", d),
    )
    return [out]


def _video_convert(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → converted container/codec. Wraps convert_video."""
    from src.core.video.converter import convert_video
    from src.utils import VIDEO_PROCESSED_DIR

    out = convert_video(
        Path(inputs[0]),
        VIDEO_PROCESSED_DIR,
        container=params.get("container", "mp4"),
        vcodec=params.get("vcodec", "copy"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _video_trim(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → trimmed clip. Wraps trim_video."""
    from src.core.video.converter import trim_video
    from src.utils import VIDEO_PROCESSED_DIR

    out = trim_video(
        Path(inputs[0]),
        VIDEO_PROCESSED_DIR,
        start=params.get("start", ""),
        end=params.get("end", ""),
        reenc=params.get("reenc", False),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _video_compress(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → H.264/CRF compressed video. Wraps compress_video."""
    from src.core.video.converter import compress_video
    from src.utils import VIDEO_PROCESSED_DIR

    out = compress_video(
        Path(inputs[0]),
        VIDEO_PROCESSED_DIR,
        crf=params.get("crf", 23),
        preset=params.get("preset", "medium"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _video_resize(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → resized video (aspect preserved). Wraps resize_video."""
    from src.core.video.converter import resize_video
    from src.utils import VIDEO_PROCESSED_DIR

    out = resize_video(
        Path(inputs[0]),
        VIDEO_PROCESSED_DIR,
        width=params.get("width", 0),
        height=params.get("height", 0),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _video_thumbnail(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → single frame as image. Wraps make_thumbnail (no progress cb).

    The frame is an image, so it is written to the image/processed dir to keep
    the Library kind classification correct.
    """
    from src.core.video.converter import make_thumbnail
    from src.utils import IMAGE_PROCESSED_DIR

    out = make_thumbnail(
        Path(inputs[0]),
        IMAGE_PROCESSED_DIR,
        time=params.get("time", "00:00:01"),
        fmt=params.get("fmt", "jpg"),
    )
    return [out]


def _video_subtitle(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video + subtitle → subtitled video (mux/burn-in). Wraps add_subtitles.

    The only multi-input step of v1: the chain carries text after transcribing,
    but burning a subtitle needs the *original video* and the *.srt*. Both are
    recovered from ``ctx`` — the video from ``initial_inputs[0]`` and the subtitle
    from the transcribe step's outputs (any .srt/.vtt among them).
    """
    from src.core.video.converter import add_subtitles
    from src.utils import VIDEO_PROCESSED_DIR

    video = Path(ctx.initial_inputs[0])
    produced = ctx.outputs_by_op.get("transcription.transcribe", [])
    subs = [Path(p) for p in produced if Path(p).suffix.lower() in (".srt", ".vtt")]
    if not subs:
        raise ValueError(
            "video.subtitle requires a subtitle produced by transcription.transcribe "
            "(add subtitles=['srt'] to the transcribe step)"
        )
    out = add_subtitles(
        video,
        subs[0],
        VIDEO_PROCESSED_DIR,
        mode=params.get("mode", "soft"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


VIDEO_STEPS: dict[str, StepSpec] = {
    "video.download": StepSpec(
        _video_download, frozenset({KIND_URL}), KIND_VIDEO, "Baixar vídeo"
    ),
    "video.convert": StepSpec(
        _video_convert, frozenset({KIND_VIDEO}), KIND_VIDEO, "Converter vídeo"
    ),
    "video.trim": StepSpec(
        _video_trim, frozenset({KIND_VIDEO}), KIND_VIDEO, "Cortar vídeo"
    ),
    "video.compress": StepSpec(
        _video_compress, frozenset({KIND_VIDEO}), KIND_VIDEO, "Comprimir vídeo"
    ),
    "video.resize": StepSpec(
        _video_resize, frozenset({KIND_VIDEO}), KIND_VIDEO, "Redimensionar vídeo"
    ),
    "video.thumbnail": StepSpec(
        _video_thumbnail, frozenset({KIND_VIDEO}), KIND_IMAGE, "Gerar thumbnail"
    ),
    # video.subtitle consumes the text the chain carries after transcribing; the
    # adapter recovers the real video + .srt from ctx (the only multi-input step).
    "video.subtitle": StepSpec(
        _video_subtitle, frozenset({KIND_TEXT}), KIND_VIDEO, "Embutir legenda"
    ),
}
