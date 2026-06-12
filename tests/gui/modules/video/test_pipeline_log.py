"""Unit tests for src/gui/modules/video/pipeline_log.py."""
from dataclasses import dataclass

import pytest

pytestmark = pytest.mark.unit

_ALL_OPS = [
    "download", "convert", "trim", "compress", "resize",
    "extract_audio", "thumbnail",
]


def _make_event(type_: str, payload: dict):
    """Build a minimal PipelineEvent-like object for testing."""
    class _Ev:
        type = type_
        payload: dict = {}
        module_id = "video"
        stage = "video"
    ev = _Ev()
    ev.payload = payload
    ev.type = type_
    return ev


@dataclass
class _FakeInfo:
    width: int | None = 1920
    height: int | None = 1080
    fps: float | None = 30.0
    vcodec: str | None = "h264"
    acodec: str | None = "aac"
    duration: float | None = 60.0
    size_bytes: int = 10_485_760  # 10 MB


# ── resolve_stage_label ──────────────────────────────────────────────────────

def test_resolve_stage_label_for_all_operations():
    from src.gui.modules.video.pipeline_log import resolve_stage_label
    for op in _ALL_OPS:
        ev = _make_event("video_op_start", {"operation": op, "item_name": "movie.mp4"})
        label = resolve_stage_label(ev)
        assert label and len(label) > 0, f"Empty label for op={op}"


def test_resolve_stage_label_progress_start():
    from src.gui.modules.video.pipeline_log import resolve_stage_label
    assert resolve_stage_label(_make_event("progress_start", {})) == "Iniciando..."


def test_resolve_stage_label_queue_progress_includes_position_and_name():
    from src.gui.modules.video.pipeline_log import resolve_stage_label
    ev = _make_event("queue_progress", {
        "current_item": 4, "total_items": 9, "item_name": "movie.mp4",
    })
    label = resolve_stage_label(ev)
    assert "4/9" in label
    assert "movie.mp4" in label


def test_resolve_stage_label_op_done_singular_vs_plural():
    from src.gui.modules.video.pipeline_log import resolve_stage_label
    one = _make_event("video_op_done", {"item_idx": 1, "total": 1})
    many = _make_event("video_op_done", {"item_idx": 2, "total": 3})
    assert resolve_stage_label(one) == "Concluído."
    assert "2/3" in resolve_stage_label(many)


def test_resolve_stage_label_op_error():
    from src.gui.modules.video.pipeline_log import resolve_stage_label
    assert resolve_stage_label(_make_event("video_op_error", {})) == "Erro — continuando fila..."


def test_resolve_stage_label_unknown_event_returns_none():
    from src.gui.modules.video.pipeline_log import resolve_stage_label
    assert resolve_stage_label(_make_event("xpto", {})) is None


# ── resolve_messages ─────────────────────────────────────────────────────────

def test_resolve_messages_op_start_uses_verb_and_item_name():
    from src.gui.modules.video.pipeline_log import resolve_messages
    ev = _make_event("video_op_start", {"operation": "compress", "item_name": "movie.mp4"})
    lines = resolve_messages(ev)
    assert len(lines) == 1
    assert "Comprimindo" in lines[0]
    assert "movie.mp4" in lines[0]


def test_resolve_messages_op_done_includes_elapsed_and_path():
    from src.gui.modules.video.pipeline_log import resolve_messages
    ev = _make_event("video_op_done", {
        "output_path": "output/video/processed/movie_compressed.mp4",
        "elapsed": "5.2s",
        "item_idx": 1,
        "total": 1,
        "src_size_bytes": 10_000_000,
        "out_size_bytes": 4_000_000,
    })
    lines = resolve_messages(ev)
    combined = " ".join(lines)
    assert "5.2s" in combined
    assert "movie_compressed.mp4" in combined


def test_resolve_messages_op_done_omits_size_when_zero():
    from src.gui.modules.video.pipeline_log import resolve_messages
    ev = _make_event("video_op_done", {
        "output_path": "output/video/processed/movie.mp4",
        "elapsed": "1s",
        "item_idx": 1,
        "total": 1,
        "src_size_bytes": 0,
        "out_size_bytes": 0,
    })
    lines = resolve_messages(ev)
    combined = " ".join(lines)
    assert "→" not in combined


def test_resolve_messages_op_error_includes_item_and_message():
    from src.gui.modules.video.pipeline_log import resolve_messages
    ev = _make_event("video_op_error", {"item_name": "bad.mp4", "message": "codec not found"})
    lines = resolve_messages(ev)
    assert "bad.mp4" in lines[0]
    assert "codec not found" in lines[0]


def test_resolve_messages_task_done_counts_outputs():
    from src.gui.modules.video.pipeline_log import resolve_messages
    ev = _make_event("task_done", {"output_paths": ["a.mp4", "b.mp4", "c.mp4"]})
    lines = resolve_messages(ev)
    assert any("3 arquivo" in l for l in lines)


def test_resolve_messages_log_passthrough():
    from src.gui.modules.video.pipeline_log import resolve_messages
    ev = _make_event("log", {"message": "[i] downloading…"})
    assert resolve_messages(ev) == ["[i] downloading…"]


# ── fmt_* builders ───────────────────────────────────────────────────────────

def test_fmt_video_info_with_full_metadata():
    from src.gui.modules.video.pipeline_log import fmt_video_info
    out = fmt_video_info(_FakeInfo())
    assert "1920×1080" in out
    assert "30.0fps" in out
    assert "h264/aac" in out
    assert "60.0s" in out
    assert "10.0 MB" in out


def test_fmt_video_info_handles_missing_fields():
    from src.gui.modules.video.pipeline_log import fmt_video_info
    out = fmt_video_info(_FakeInfo(width=None, fps=None, vcodec=None, duration=None))
    # Each missing field falls back to "?"
    assert "?" in out


def test_fmt_download_detail_resolution_label():
    from src.gui.modules.video.pipeline_log import fmt_download_detail
    out = fmt_download_detail("1080", "mp4")
    assert "máx. 1080p" in out
    assert "MP4" in out

    out_best = fmt_download_detail("best", "mkv")
    assert "melhor disponível" in out_best
    assert "MKV" in out_best


def test_fmt_convert_detail_translates_codec():
    from src.gui.modules.video.pipeline_log import fmt_convert_detail
    out = fmt_convert_detail("h264", "mp4")
    assert "H.264" in out
    assert "MP4" in out

    out_copy = fmt_convert_detail("copy", "mkv")
    assert "sem reencoding" in out_copy


def test_fmt_trim_detail_reenc_vs_copy():
    from src.gui.modules.video.pipeline_log import fmt_trim_detail
    fast = fmt_trim_detail("0:00", "0:10", reenc=False)
    precise = fmt_trim_detail("0:00", "0:10", reenc=True)
    assert "rápido (copy)" in fast
    assert "frame-preciso" in precise


def test_fmt_trim_detail_default_labels_when_blank():
    from src.gui.modules.video.pipeline_log import fmt_trim_detail
    out = fmt_trim_detail("", "", reenc=False)
    assert "início" in out
    assert "fim" in out


def test_fmt_compress_detail_quality_buckets():
    from src.gui.modules.video.pipeline_log import fmt_compress_detail
    high = fmt_compress_detail(crf=18, preset="medium")
    good = fmt_compress_detail(crf=23, preset="medium")
    compressed = fmt_compress_detail(crf=28, preset="fast")
    assert "qualidade alta" in high
    assert "qualidade boa" in good
    assert "comprimida" in compressed


def test_fmt_resize_detail_auto_dimensions():
    from src.gui.modules.video.pipeline_log import fmt_resize_detail
    width_only = fmt_resize_detail(width=1280, height=0)
    assert "1280×auto" in width_only

    both = fmt_resize_detail(width=1280, height=720)
    assert "1280×720" in both


def test_fmt_thumbnail_detail_includes_time_and_format():
    from src.gui.modules.video.pipeline_log import fmt_thumbnail_detail
    out = fmt_thumbnail_detail("00:00:05", "jpg")
    assert "00:00:05" in out
    assert "JPG" in out


def test_fmt_extract_audio_detail():
    from src.gui.modules.video.pipeline_log import fmt_extract_audio_detail
    out = fmt_extract_audio_detail("mp3")
    assert "MP3" in out
