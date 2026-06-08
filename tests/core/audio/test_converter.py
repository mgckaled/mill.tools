"""Testes de integração — src/core/audio/converter.py."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_convert_audio_wav_to_mp3(sample_wav, out_dir):
    """Conversão WAV → MP3 deve produzir arquivo de saída válido."""
    from src.core.audio.converter import convert_audio

    out = convert_audio(sample_wav, out_dir, fmt="mp3", bitrate="128")
    assert out.exists()
    assert out.suffix.lower() == ".mp3"
    assert out.stat().st_size > 1000


def test_convert_audio_wav_to_ogg(sample_wav, out_dir):
    """Conversão WAV → OGG deve produzir arquivo de saída válido."""
    from src.core.audio.converter import convert_audio

    out = convert_audio(sample_wav, out_dir, fmt="ogg")
    assert out.exists()
    assert out.suffix.lower() == ".ogg"


def test_convert_audio_calls_progress_cb(sample_wav, out_dir):
    """progress_cb deve ser chamado ao menos uma vez durante a conversão."""
    from src.core.audio.converter import convert_audio

    calls: list[float] = []
    out = convert_audio(
        sample_wav,
        out_dir,
        fmt="mp3",
        bitrate="128",
        progress_cb=lambda ratio: calls.append(ratio),
    )
    assert out.exists()
    assert len(calls) > 0
    assert all(0.0 <= r <= 1.0 for r in calls)


def test_extract_audio_from_mp4(sample_mp4, out_dir):
    """Extração de áudio de MP4 deve produzir MP3 válido."""
    from src.core.audio.converter import extract_audio

    out = extract_audio(sample_mp4, out_dir, fmt="mp3")
    assert out.exists()
    assert out.suffix.lower() == ".mp3"
    assert out.stat().st_size > 500


def test_convert_audio_invalid_format_raises(sample_wav, out_dir):
    """Formato desconhecido deve lançar RuntimeError (ffmpeg retorna erro)."""
    from src.core.audio.converter import convert_audio

    with pytest.raises(RuntimeError):
        convert_audio(sample_wav, out_dir, fmt="xyz_invalid_format")


def test_convert_audio_nonexistent_file_raises(out_dir):
    """Arquivo de entrada inexistente deve lançar RuntimeError."""
    from src.core.audio.converter import convert_audio

    fake = Path("/nonexistent/path/audio.wav")
    with pytest.raises((RuntimeError, FileNotFoundError)):
        convert_audio(fake, out_dir, fmt="mp3")
