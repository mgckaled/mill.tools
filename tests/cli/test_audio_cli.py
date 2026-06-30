"""Tests for CLI audio subcommand argument parsing."""

import argparse

import pytest

from src.cli.audio import add_audio_parser


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_audio_parser(sub)
    return parser.parse_args(["audio", *argv])


@pytest.mark.unit
def test_audio_url_defaults():
    ns = _parse("https://youtu.be/abc123")
    assert ns.input == "https://youtu.be/abc123"
    assert ns.fmt == "mp3"
    assert ns.quality == "best"
    assert ns.no_meta is False
    assert ns.denoise is False
    assert ns.normalize is False
    assert ns.lufs == -14.0


@pytest.mark.unit
def test_audio_local_file_custom_fmt():
    ns = _parse("audio.wav", "--fmt", "ogg", "--quality", "192")
    assert ns.input == "audio.wav"
    assert ns.fmt == "ogg"
    assert ns.quality == "192"


@pytest.mark.unit
def test_audio_denoise_normalize():
    ns = _parse("video.mp4", "--denoise", "--normalize", "--lufs", "-23")
    assert ns.denoise is True
    assert ns.normalize is True
    assert ns.lufs == -23.0


@pytest.mark.unit
def test_audio_no_meta():
    ns = _parse("https://example.com/song", "--no-meta")
    assert ns.no_meta is True


@pytest.mark.unit
def test_audio_tier1_flag_defaults():
    """Novas flags do Tier 1 têm os defaults esperados."""
    ns = _parse("audio.wav")
    assert ns.denoise_adaptive is False
    assert ns.mono is False
    assert ns.sample_rate is None
    assert ns.trim_silence is False
    assert ns.silence_threshold == -40.0
    assert ns.silence_min == 0.5
    assert ns.speed == 1.0


@pytest.mark.unit
def test_audio_mono_and_sample_rate():
    ns = _parse("audio.wav", "--mono", "--sample-rate", "16000")
    assert ns.mono is True
    assert ns.sample_rate == 16000


@pytest.mark.unit
def test_audio_trim_silence_options():
    ns = _parse(
        "lecture.mp3",
        "--trim-silence",
        "--silence-threshold",
        "-35",
        "--silence-min",
        "1.0",
    )
    assert ns.trim_silence is True
    assert ns.silence_threshold == -35.0
    assert ns.silence_min == 1.0


@pytest.mark.unit
def test_audio_speed_and_denoise_adaptive():
    ns = _parse("lesson.wav", "--speed", "1.5", "--denoise", "--denoise-adaptive")
    assert ns.speed == 1.5
    assert ns.denoise is True
    assert ns.denoise_adaptive is True


@pytest.mark.unit
def test_audio_invalid_sample_rate_rejected():
    """--sample-rate fora do choices deve falhar no parser."""
    with pytest.raises(SystemExit):
        _parse("audio.wav", "--sample-rate", "12345")


@pytest.mark.unit
def test_audio_func_is_callable():
    ns = _parse("https://youtu.be/abc")
    assert callable(ns.func)


@pytest.mark.unit
def test_run_audio_cli_dispatches_to_pipeline(mocker):
    """ns.func dispatches to run_audio_pipeline with an AudioArgs built from the namespace."""
    mocker.patch("src.utils.check_dependencies")
    mock_pipeline = mocker.patch(
        "src.gui.modules.audio.worker.run_audio_pipeline",
        return_value=True,
    )
    ns = _parse("https://youtu.be/abc", "--fmt", "wav", "--normalize", "--lufs", "-16")
    ns.func(ns)
    assert mock_pipeline.called
    args = mock_pipeline.call_args.args[0]
    assert args.fmt == "wav"
    assert args.normalize is True
    assert args.normalize_target_lufs == -16.0


@pytest.mark.unit
def test_run_audio_cli_passes_tier1_args(mocker):
    """As flags do Tier 1 chegam ao AudioArgs do pipeline."""
    mocker.patch("src.utils.check_dependencies")
    mock_pipeline = mocker.patch(
        "src.gui.modules.audio.worker.run_audio_pipeline",
        return_value=True,
    )
    ns = _parse(
        "lesson.wav",
        "--mono",
        "--sample-rate",
        "16000",
        "--trim-silence",
        "--speed",
        "1.25",
        "--denoise",
        "--denoise-adaptive",
    )
    ns.func(ns)
    args = mock_pipeline.call_args.args[0]
    assert args.channels == 1
    assert args.sample_rate == 16000
    assert args.trim_silence is True
    assert args.speed_factor == 1.25
    assert args.denoise is True
    assert args.denoise_stationary is False


@pytest.mark.unit
def test_run_audio_cli_nonzero_exit_on_failure(mocker):
    """Pipeline returning False triggers sys.exit(1)."""
    mocker.patch("src.utils.check_dependencies")
    mocker.patch("src.gui.modules.audio.worker.run_audio_pipeline", return_value=False)
    ns = _parse("https://youtu.be/abc")
    with pytest.raises(SystemExit) as exc:
        ns.func(ns)
    assert exc.value.code == 1
