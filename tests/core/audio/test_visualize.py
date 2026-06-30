"""Testes — src/core/audio/visualize.py."""

import pytest


def _capture(mocker):
    captured: dict = {}

    def _fake(cmd, out_path, **kwargs):
        captured["cmd"] = cmd
        captured["out_path"] = out_path
        return out_path

    mocker.patch("src.core.audio.visualize.run_ffmpeg", side_effect=_fake)
    return captured


@pytest.mark.unit
def test_render_waveform_builds_showwavespic(tmp_path, mocker):
    from src.core.audio.visualize import render_waveform_png

    src = tmp_path / "song.wav"
    src.write_bytes(b"")
    captured = _capture(mocker)

    out = render_waveform_png(src, tmp_path / "out", width=800, height=120)

    assert out.name == "song_waveform.png"
    cmd = captured["cmd"]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.startswith("showwavespic=s=800x120")
    assert "colors=" in fc
    assert "-frames:v" in cmd


@pytest.mark.unit
def test_render_spectrogram_builds_showspectrumpic(tmp_path, mocker):
    from src.core.audio.visualize import render_spectrogram_png

    src = tmp_path / "song.wav"
    src.write_bytes(b"")
    captured = _capture(mocker)

    out = render_spectrogram_png(src, tmp_path / "out", width=1024, height=512)

    assert out.name == "song_spectrogram.png"
    cmd = captured["cmd"]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.startswith("showspectrumpic=s=1024x512")
    assert "mode=combined" in fc


@pytest.mark.integration
def test_render_waveform_produces_png(sample_wav, out_dir):
    from src.core.audio.visualize import render_waveform_png

    out = render_waveform_png(sample_wav, out_dir)
    assert out.exists()
    assert out.read_bytes()[:4] == b"\x89PNG"


@pytest.mark.integration
def test_render_spectrogram_produces_png(sample_wav, out_dir):
    from src.core.audio.visualize import render_spectrogram_png

    out = render_spectrogram_png(sample_wav, out_dir)
    assert out.exists()
    assert out.read_bytes()[:4] == b"\x89PNG"
