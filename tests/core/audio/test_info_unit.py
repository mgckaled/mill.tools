"""Testes unitários — src/core/audio/info.py com subprocess mockado (ffprobe ausente)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_get_audio_codec_ffprobe_missing_binary_returns_none(mocker):
    """ffprobe ausente (FileNotFoundError do subprocess) não deve propagar — retorna None."""
    from src.core.audio.info import get_audio_codec_ffprobe

    mocker.patch("subprocess.run", side_effect=FileNotFoundError("ffprobe not found"))

    assert get_audio_codec_ffprobe(Path("anything.wav")) is None
