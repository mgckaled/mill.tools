"""Testes unitários — download_audio: montagem de postprocessors/ydl_opts por fmt (sem rede)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


class _FakeYDL:
    """Stand-in for yt_dlp.YoutubeDL: captures ydl_opts and writes a fake output file.

    extract_info never touches the network — it derives tmp_dir from the outtmpl
    template already built by download_audio and drops a fake file there, so the
    real move-to-out_dir/cleanup logic in download_audio still runs unmodified.
    """

    captured_opts: dict | None = None

    def __init__(self, opts: dict):
        self.opts = opts
        _FakeYDL.captured_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        out_dir = Path(self.opts["outtmpl"]).parent
        fake_file = out_dir / "video.mp3"
        fake_file.write_bytes(b"fake-audio")
        return {"requested_downloads": [{"filepath": str(fake_file)}]}


def _pp_names(opts: dict) -> list[str]:
    return [pp["key"] for pp in opts["postprocessors"]]


def test_download_audio_fmt_best_skips_thumbnail(tmp_path, mocker):
    """fmt='best': sem FFmpegExtractAudio (sem reencode) e sem EmbedThumbnail (container
    final desconhecido — pode ser webm, que o EmbedThumbnail do yt-dlp rejeita)."""
    from src.core.audio.downloader import download_audio

    mocker.patch("yt_dlp.YoutubeDL", _FakeYDL)

    out = download_audio("https://example.com/watch", tmp_path, fmt="best")

    opts = _FakeYDL.captured_opts
    assert "FFmpegExtractAudio" not in _pp_names(opts)
    assert "EmbedThumbnail" not in _pp_names(opts)
    assert opts["writethumbnail"] is False
    assert out.exists()


def test_download_audio_fmt_mp3_embeds_thumbnail(tmp_path, mocker):
    """fmt='mp3': FFmpegExtractAudio + EmbedThumbnail presentes (cover suportada)."""
    from src.core.audio.downloader import download_audio

    mocker.patch("yt_dlp.YoutubeDL", _FakeYDL)

    download_audio("https://example.com/watch", tmp_path, fmt="mp3")

    opts = _FakeYDL.captured_opts
    assert "FFmpegExtractAudio" in _pp_names(opts)
    assert "EmbedThumbnail" in _pp_names(opts)
    assert opts["writethumbnail"] is True


@pytest.mark.parametrize("fmt", ["ogg", "opus"])
def test_download_audio_ogg_opus_skip_thumbnail(tmp_path, mocker, fmt):
    """ogg/opus: FFmpegExtractAudio presente, mas sem EmbedThumbnail (decisão preexistente)."""
    from src.core.audio.downloader import download_audio

    mocker.patch("yt_dlp.YoutubeDL", _FakeYDL)

    download_audio("https://example.com/watch", tmp_path, fmt=fmt)

    opts = _FakeYDL.captured_opts
    assert "FFmpegExtractAudio" in _pp_names(opts)
    assert "EmbedThumbnail" not in _pp_names(opts)


def test_download_audio_embed_meta_false_skips_all_metadata_pps(tmp_path, mocker):
    """embed_meta=False: nem FFmpegMetadata nem EmbedThumbnail são adicionados."""
    from src.core.audio.downloader import download_audio

    mocker.patch("yt_dlp.YoutubeDL", _FakeYDL)

    download_audio("https://example.com/watch", tmp_path, fmt="mp3", embed_meta=False)

    opts = _FakeYDL.captured_opts
    names = _pp_names(opts)
    assert "FFmpegMetadata" not in names
    assert "EmbedThumbnail" not in names
