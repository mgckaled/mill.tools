"""Fixtures compartilhadas entre todos os testes."""
from pathlib import Path

import pytest
from PIL import Image


def _make_rgb_jpg(tmp_path: Path, width: int = 200, height: int = 150, name: str = "sample.jpg") -> Path:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    path = tmp_path / name
    img.save(path, format="JPEG", quality=85)
    return path


def _make_rgba_png(tmp_path: Path, width: int = 100, height: int = 100, name: str = "sample.png") -> Path:
    img = Image.new("RGBA", (width, height), color=(255, 0, 0, 128))
    path = tmp_path / name
    img.save(path, format="PNG")
    return path


@pytest.fixture
def jpg_image(tmp_path: Path) -> Path:
    """JPEG RGB 200×150."""
    return _make_rgb_jpg(tmp_path)


@pytest.fixture
def png_image(tmp_path: Path) -> Path:
    """PNG RGBA 100×100."""
    return _make_rgba_png(tmp_path)


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    """Diretório de saída limpo por teste."""
    d = tmp_path / "output"
    d.mkdir()
    return d
