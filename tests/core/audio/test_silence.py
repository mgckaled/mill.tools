"""Testes — src/core/audio/silence.py (unit com run_ffmpeg mockado)."""

import pytest


@pytest.mark.unit
def test_build_filtergraph_contains_expected_params():
    """O filtergraph deve conter os limiares e o stop_periods negativo (silêncio interno)."""
    from src.core.audio.silence import build_filtergraph

    af = build_filtergraph(threshold_db=-40.0, min_silence_s=0.5, keep_silence_s=0.1)

    assert af.startswith("silenceremove=")
    assert "stop_periods=-1" in af  # remove silêncio do meio
    assert "start_periods=1" in af  # remove silêncio do início
    assert "stop_threshold=-40.0dB" in af
    assert "stop_duration=0.5" in af
    assert "stop_silence=0.1" in af


@pytest.mark.unit
def test_remove_silence_builds_command_and_names_output(tmp_path, mocker):
    """remove_silence injeta o -af e nomeia a saída <stem>_nosilence.<fmt>."""
    from src.core.audio import silence as silence_mod

    src = tmp_path / "lecture.wav"
    src.write_bytes(b"")
    captured: dict = {}

    def _fake(cmd, out_path, **kwargs):
        captured["cmd"] = cmd
        captured["out_path"] = out_path
        return out_path

    mocker.patch.object(silence_mod, "run_ffmpeg", side_effect=_fake)

    out = silence_mod.remove_silence(src, tmp_path / "out", fmt="mp3")

    assert out.name == "lecture_nosilence.mp3"
    cmd = captured["cmd"]
    assert "-af" in cmd
    assert "silenceremove=" in cmd[cmd.index("-af") + 1]


@pytest.mark.integration
def test_remove_silence_produces_output(sample_wav, out_dir):
    """Integração: remove_silence gera um arquivo válido a partir de um WAV real."""
    from src.core.audio.silence import remove_silence

    out = remove_silence(sample_wav, out_dir, fmt="wav")
    assert out.exists()
    assert out.suffix.lower() == ".wav"
