"""Testes — src/core/audio/speed.py (unit do encadeamento atempo)."""

import pytest


@pytest.mark.unit
def test_atempo_chain_in_range_single_stage():
    """Fatores dentro de 0.5-2.0 produzem um único estágio atempo."""
    from src.core.audio.speed import _atempo_chain

    assert _atempo_chain(1.25) == "atempo=1.25"
    assert _atempo_chain(0.5) == "atempo=0.5"
    assert _atempo_chain(2.0) == "atempo=2"


@pytest.mark.unit
def test_atempo_chain_above_two_splits_stages():
    """Fatores acima de 2.0 são divididos em estágios cujo produto = fator."""
    from src.core.audio.speed import _atempo_chain

    assert _atempo_chain(3.0) == "atempo=2,atempo=1.5"
    assert _atempo_chain(4.0) == "atempo=2,atempo=2"


@pytest.mark.unit
def test_atempo_chain_out_of_range_raises():
    """Fatores fora de [0.5, 4.0] levantam ValueError."""
    from src.core.audio.speed import _atempo_chain

    with pytest.raises(ValueError):
        _atempo_chain(0.4)
    with pytest.raises(ValueError):
        _atempo_chain(4.5)


@pytest.mark.unit
def test_change_speed_builds_command_and_names_output(tmp_path, mocker):
    """change_speed injeta o -af atempo e nomeia a saída <stem>_<factor>x.<fmt>."""
    from src.core.audio import speed as speed_mod

    src = tmp_path / "lesson.wav"
    src.write_bytes(b"")
    captured: dict = {}

    def _fake(cmd, out_path, **kwargs):
        captured["cmd"] = cmd
        return out_path

    mocker.patch.object(speed_mod, "run_ffmpeg", side_effect=_fake)

    out = speed_mod.change_speed(src, tmp_path / "out", fmt="mp3", factor=1.5)

    assert out.name == "lesson_1_5x.mp3"
    cmd = captured["cmd"]
    assert "-af" in cmd
    assert cmd[cmd.index("-af") + 1] == "atempo=1.5"


@pytest.mark.integration
def test_change_speed_produces_shorter_output(sample_wav, out_dir):
    """Integração: acelerar 2× reduz a duração para ~metade."""
    from src.core.audio.info import get_duration_ffprobe
    from src.core.audio.speed import change_speed

    src_dur = get_duration_ffprobe(sample_wav)
    out = change_speed(sample_wav, out_dir, fmt="wav", factor=2.0)
    assert out.exists()
    out_dur = get_duration_ffprobe(out)
    if src_dur and out_dur:
        assert out_dur < src_dur * 0.75
