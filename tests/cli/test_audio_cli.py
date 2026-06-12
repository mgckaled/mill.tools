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
def test_run_audio_cli_nonzero_exit_on_failure(mocker):
    """Pipeline returning False triggers sys.exit(1)."""
    mocker.patch("src.utils.check_dependencies")
    mocker.patch("src.gui.modules.audio.worker.run_audio_pipeline", return_value=False)
    ns = _parse("https://youtu.be/abc")
    with pytest.raises(SystemExit) as exc:
        ns.func(ns)
    assert exc.value.code == 1
