"""Tests for CLI video subcommand argument parsing."""
import argparse

import pytest

from src.cli.video import add_video_parser


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_video_parser(sub)
    return parser.parse_args(["video", *argv])


@pytest.mark.unit
def test_video_download_defaults():
    ns = _parse("download", "https://youtu.be/abc")
    assert ns.video_op == "download"
    assert ns.url == "https://youtu.be/abc"
    assert ns.quality == "1080"
    assert ns.container == "mp4"
    assert ns.no_meta is False


@pytest.mark.unit
def test_video_download_custom_quality():
    ns = _parse("download", "https://youtu.be/abc", "--quality", "720", "--container", "mkv")
    assert ns.quality == "720"
    assert ns.container == "mkv"


@pytest.mark.unit
def test_video_convert_defaults():
    ns = _parse("convert", "video.mp4")
    assert ns.video_op == "convert"
    assert ns.file == "video.mp4"
    assert ns.codec == "copy"
    assert ns.container == "mp4"


@pytest.mark.unit
def test_video_trim_required_start():
    ns = _parse("trim", "video.mp4", "--start", "0:30", "--end", "1:00")
    assert ns.trim_start == "0:30"
    assert ns.trim_end == "1:00"
    assert ns.trim_reenc is False


@pytest.mark.unit
def test_video_trim_reenc():
    ns = _parse("trim", "video.mp4", "--start", "0:30", "--reenc")
    assert ns.trim_reenc is True


@pytest.mark.unit
def test_video_compress_defaults():
    ns = _parse("compress", "video.mp4")
    assert ns.crf == 23
    assert ns.preset == "medium"


@pytest.mark.unit
def test_video_resize_dimensions():
    ns = _parse("resize", "video.mp4", "--width", "1280", "--height", "720")
    assert ns.width == 1280
    assert ns.height == 720


@pytest.mark.unit
def test_video_extract_audio_fmt():
    ns = _parse("extract-audio", "video.mp4", "--fmt", "wav")
    assert ns.video_op == "extract-audio"
    assert ns.fmt == "wav"


@pytest.mark.unit
def test_video_thumbnail_defaults():
    ns = _parse("thumbnail", "video.mp4")
    assert ns.time == "00:00:01"
    assert ns.fmt == "jpg"


@pytest.mark.unit
def test_video_func_is_callable():
    ns = _parse("download", "https://youtu.be/abc")
    assert callable(ns.func)


@pytest.mark.unit
def test_run_video_cli_download_dispatches_to_pipeline(mocker):
    """video download URL → VideoArgs with kind='url' and operation='download'."""
    mocker.patch("src.utils.check_dependencies")
    mock_pipeline = mocker.patch(
        "src.gui.modules.video.worker.run_video_pipeline",
        return_value=True,
    )
    ns = _parse("download", "https://youtu.be/abc", "--quality", "720")
    ns.func(ns)
    assert mock_pipeline.called
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "download"
    assert args.items[0].kind == "url"
    assert args.resolution == "720"


@pytest.mark.unit
def test_run_video_cli_extract_audio_normalises_op_name(mocker, tmp_path):
    """'extract-audio' (kebab) becomes 'extract_audio' (snake) in VideoArgs."""
    mocker.patch("src.utils.check_dependencies")
    mock_pipeline = mocker.patch(
        "src.gui.modules.video.worker.run_video_pipeline",
        return_value=True,
    )
    f = tmp_path / "movie.mp4"
    f.write_bytes(b"")
    ns = _parse("extract-audio", str(f), "--fmt", "wav")
    ns.func(ns)
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "extract_audio"
    assert args.audio_fmt == "wav"
