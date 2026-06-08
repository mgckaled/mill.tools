"""Testes de integração — src/core/audio/info.py."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_get_duration_ffprobe_wav(sample_wav):
    """ffprobe deve retornar duração próxima de 3.0 s para o fixture WAV."""
    from src.core.audio.info import get_duration_ffprobe

    duration = get_duration_ffprobe(sample_wav)
    assert duration is not None
    assert 2.5 <= duration <= 3.5


def test_get_duration_ffprobe_mp3(sample_mp3):
    """ffprobe deve retornar duração próxima de 3.0 s para o fixture MP3."""
    from src.core.audio.info import get_duration_ffprobe

    duration = get_duration_ffprobe(sample_mp3)
    assert duration is not None
    assert 2.5 <= duration <= 3.5


def test_get_duration_ffprobe_mp4(sample_mp4):
    """ffprobe deve retornar duração próxima de 3.0 s para o fixture MP4."""
    from src.core.audio.info import get_duration_ffprobe

    duration = get_duration_ffprobe(sample_mp4)
    assert duration is not None
    assert 2.5 <= duration <= 3.5


def test_get_duration_ffprobe_nonexistent_returns_none():
    """Arquivo inexistente não deve lançar exceção — retorna None."""
    from src.core.audio.info import get_duration_ffprobe

    result = get_duration_ffprobe(Path("/nonexistent/file.wav"))
    assert result is None
