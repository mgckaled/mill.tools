"""Testes unitários — convert_audio com run_ffmpeg mockado (sem ffmpeg)."""

import pytest

pytestmark = pytest.mark.unit


def _capture_cmd(mocker):
    """Patch run_ffmpeg to capture the argv and return the requested out_path."""
    captured: dict = {}

    def _fake(cmd, out_path, **kwargs):
        captured["cmd"] = cmd
        captured["out_path"] = out_path
        return out_path

    mocker.patch("src.core.audio.converter.run_ffmpeg", side_effect=_fake)
    return captured


def test_convert_audio_mono_adds_ac_flag(tmp_path, mocker):
    """channels=1 deve injetar '-ac 1' no comando ffmpeg."""
    from src.core.audio.converter import convert_audio

    src = tmp_path / "in.wav"
    src.write_bytes(b"")
    captured = _capture_cmd(mocker)

    convert_audio(src, tmp_path / "out", fmt="mp3", channels=1)

    cmd = captured["cmd"]
    assert "-ac" in cmd
    assert cmd[cmd.index("-ac") + 1] == "1"


def test_convert_audio_sample_rate_adds_ar_flag(tmp_path, mocker):
    """sample_rate=16000 deve injetar '-ar 16000' no comando ffmpeg."""
    from src.core.audio.converter import convert_audio

    src = tmp_path / "in.wav"
    src.write_bytes(b"")
    captured = _capture_cmd(mocker)

    convert_audio(src, tmp_path / "out", fmt="mp3", sample_rate=16000)

    cmd = captured["cmd"]
    assert "-ar" in cmd
    assert cmd[cmd.index("-ar") + 1] == "16000"


def test_convert_audio_no_resample_omits_flags(tmp_path, mocker):
    """Sem channels/sample_rate, '-ac'/'-ar' não aparecem."""
    from src.core.audio.converter import convert_audio

    src = tmp_path / "in.wav"
    src.write_bytes(b"")
    captured = _capture_cmd(mocker)

    convert_audio(src, tmp_path / "out", fmt="mp3")

    cmd = captured["cmd"]
    assert "-ac" not in cmd
    assert "-ar" not in cmd


def test_convert_audio_same_path_no_transform_returns_src(tmp_path, mocker):
    """Mesmo caminho e nenhuma transformação → retorna src sem chamar ffmpeg."""
    from src.core.audio.converter import convert_audio

    src = tmp_path / "song.mp3"
    src.write_bytes(b"")
    run = mocker.patch("src.core.audio.converter.run_ffmpeg")

    out = convert_audio(src, tmp_path, fmt="mp3")

    assert out == src
    run.assert_not_called()


def test_convert_audio_inplace_transform_uses_tempfile(tmp_path, mocker):
    """mp3→mp3 mono no mesmo dir deve encodar para temp e mover para o destino."""
    from src.core.audio.converter import convert_audio

    src = tmp_path / "song.mp3"
    src.write_bytes(b"")
    captured = _capture_cmd(mocker)
    move = mocker.patch("src.core.audio.converter.shutil.move")

    out = convert_audio(src, tmp_path, fmt="mp3", channels=1)

    # ffmpeg escreve num temp (não no destino final), depois move
    assert captured["out_path"].name.startswith(".tmp_encode_")
    move.assert_called_once()
    assert out == tmp_path / "song.mp3"
