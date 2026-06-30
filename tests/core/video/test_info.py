"""Testes de integração — src/core/video/info.py."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_get_video_info_returns_dataclass(sample_mp4):
    """get_video_info deve retornar VideoInfo com atributos esperados."""
    from src.core.video.info import get_video_info

    info = get_video_info(sample_mp4)
    assert info is not None
    assert hasattr(info, "width")
    assert hasattr(info, "height")
    assert hasattr(info, "duration")


def test_get_video_info_dimensions(sample_mp4):
    """Fixture MP4 é 320×240 — dimensões devem ser corretas."""
    from src.core.video.info import get_video_info

    info = get_video_info(sample_mp4)
    assert info.width == 320
    assert info.height == 240


def test_get_video_info_duration(sample_mp4):
    """Duração do fixture MP4 deve ser próxima de 3 s."""
    from src.core.video.info import get_video_info

    info = get_video_info(sample_mp4)
    assert info.duration is not None
    assert 2.5 <= info.duration <= 3.5


def test_get_video_info_nonexistent_returns_null_fields():
    """Arquivo inexistente não deve travar — implementação captura exceções e retorna VideoInfo com campos nulos."""
    from src.core.video.info import get_video_info

    result = get_video_info(Path("/nonexistent/video.mp4"))
    # get_video_info captura toda Exception e retorna VideoInfo(None, None, None, None, None, None, 0)
    assert result.duration is None
    assert result.width is None
    assert result.height is None
