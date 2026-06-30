"""Unit tests for src/gui/modules/audio/pipeline_log.py."""

import pytest

pytestmark = pytest.mark.unit

_ALL_OPS = ["download", "convert", "extract", "denoise", "normalize"]


def _make_event(type_: str, payload: dict):
    """Build a minimal PipelineEvent-like object for testing."""

    class _Ev:
        type = type_
        payload: dict = {}
        module_id = "audio"
        stage = "audio"

    ev = _Ev()
    ev.payload = payload
    ev.type = type_
    return ev


# ── resolve_stage_label ──────────────────────────────────────────────────────


def test_resolve_stage_label_for_all_operations():
    from src.gui.modules.audio.pipeline_log import resolve_stage_label

    for op in _ALL_OPS:
        ev = _make_event("audio_op_start", {"operation": op, "item_name": "test.wav"})
        label = resolve_stage_label(ev)
        assert label and len(label) > 0, f"Empty label for op={op}"


def test_resolve_stage_label_progress_start():
    from src.gui.modules.audio.pipeline_log import resolve_stage_label

    ev = _make_event("progress_start", {})
    assert resolve_stage_label(ev) == "Iniciando..."


def test_resolve_stage_label_queue_progress_includes_position_and_name():
    from src.gui.modules.audio.pipeline_log import resolve_stage_label

    ev = _make_event(
        "queue_progress", {"current_item": 2, "total_items": 5, "item_name": "song.mp3"}
    )
    label = resolve_stage_label(ev)
    assert "2/5" in label
    assert "song.mp3" in label


def test_resolve_stage_label_op_done_singular_vs_plural():
    from src.gui.modules.audio.pipeline_log import resolve_stage_label

    one = _make_event("audio_op_done", {"item_idx": 1, "total": 1})
    many = _make_event("audio_op_done", {"item_idx": 2, "total": 3})
    assert resolve_stage_label(one) == "Concluído."
    assert "2/3" in resolve_stage_label(many)


def test_resolve_stage_label_unknown_event_returns_none():
    from src.gui.modules.audio.pipeline_log import resolve_stage_label

    assert resolve_stage_label(_make_event("xpto", {})) is None


# ── resolve_messages ─────────────────────────────────────────────────────────


def test_resolve_messages_op_start_uses_verb_and_item_name():
    from src.gui.modules.audio.pipeline_log import resolve_messages

    ev = _make_event(
        "audio_op_start", {"operation": "denoise", "item_name": "song.wav"}
    )
    lines = resolve_messages(ev)
    assert len(lines) == 1
    assert "Reduzindo ruído" in lines[0]
    assert "song.wav" in lines[0]


def test_resolve_messages_op_done_includes_elapsed_and_path():
    from src.gui.modules.audio.pipeline_log import resolve_messages

    ev = _make_event(
        "audio_op_done",
        {
            "output_path": "output/audio/processed/song_normalized.wav",
            "elapsed": "1.2s",
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": 500_000,
            "out_size_bytes": 480_000,
        },
    )
    lines = resolve_messages(ev)
    combined = " ".join(lines)
    assert "1.2s" in combined
    assert "song_normalized.wav" in combined


def test_resolve_messages_op_done_omits_size_when_zero():
    from src.gui.modules.audio.pipeline_log import resolve_messages

    ev = _make_event(
        "audio_op_done",
        {
            "output_path": "output/audio/processed/song.mp3",
            "elapsed": "0.5s",
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": 0,
            "out_size_bytes": 0,
        },
    )
    lines = resolve_messages(ev)
    combined = " ".join(lines)
    assert "→" not in combined  # the "src → out" arrow should not appear


def test_resolve_messages_task_error():
    from src.gui.modules.audio.pipeline_log import resolve_messages

    ev = _make_event("task_error", {"message": "ffmpeg failed"})
    lines = resolve_messages(ev)
    assert len(lines) == 1
    assert "[!]" in lines[0]
    assert "ffmpeg failed" in lines[0]


def test_resolve_messages_log_passthrough():
    from src.gui.modules.audio.pipeline_log import resolve_messages

    ev = _make_event("log", {"message": "  42%"})
    assert resolve_messages(ev) == ["  42%"]


# ── fmt_* builders ───────────────────────────────────────────────────────────


def test_fmt_ffmpeg_progress_formats_percentage():
    from src.gui.modules.audio.pipeline_log import fmt_ffmpeg_progress

    assert fmt_ffmpeg_progress(0.5) == "[d] 50%"
    assert fmt_ffmpeg_progress(0.0) == "[d] 0%"
    assert fmt_ffmpeg_progress(1.0) == "[d] 100%"


def test_fmt_audio_info_with_duration_and_size():
    from src.gui.modules.audio.pipeline_log import fmt_audio_info

    out = fmt_audio_info("song.wav", duration=10.5, size_bytes=1_048_576)
    assert "song.wav" in out
    assert "10.5s" in out
    assert "1.0 MB" in out


def test_fmt_audio_info_handles_unknown_duration():
    from src.gui.modules.audio.pipeline_log import fmt_audio_info

    out = fmt_audio_info("song.wav", duration=None, size_bytes=512)
    assert "duração desconhecida" in out
    assert "512 B" in out


def test_fmt_denoise_detail_stationary_vs_adaptive():
    from src.gui.modules.audio.pipeline_log import fmt_denoise_detail

    assert "estacionário" in fmt_denoise_detail(stationary=True)
    assert "adaptativo" in fmt_denoise_detail(stationary=False)


def test_fmt_normalize_detail_includes_target_lufs():
    from src.gui.modules.audio.pipeline_log import fmt_normalize_detail

    out = fmt_normalize_detail(target_lufs=-14.0)
    assert "-14.0" in out
    assert "LUFS" in out


def test_fmt_normalize_measured_extracts_stats():
    from src.gui.modules.audio.pipeline_log import fmt_normalize_measured

    stats = {"input_i": "-18.2", "input_lra": "7.8", "input_tp": "-3.1"}
    out = fmt_normalize_measured(stats)
    assert "-18.2" in out
    assert "7.8" in out
    assert "-3.1" in out


def test_fmt_normalize_measured_handles_missing_keys():
    from src.gui.modules.audio.pipeline_log import fmt_normalize_measured

    out = fmt_normalize_measured({})
    # Missing keys default to "?"
    assert "?" in out
