"""Fixtures compartilhadas entre todos os testes."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image


def _make_rgb_jpg(
    tmp_path: Path, width: int = 200, height: int = 150, name: str = "sample.jpg"
) -> Path:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    path = tmp_path / name
    img.save(path, format="JPEG", quality=85)
    return path


def _make_rgba_png(
    tmp_path: Path, width: int = 100, height: int = 100, name: str = "sample.png"
) -> Path:
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


# ---------------------------------------------------------------------------
# Fixtures de áudio de sessão — geradas via ffmpeg (sine wave 440 Hz)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sample_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """WAV mono 44100 Hz 3 s — sine wave 440 Hz."""
    out = tmp_path_factory.mktemp("fixtures") / "sample.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


@pytest.fixture(scope="session")
def sample_mp3(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """MP3 mono 128 kbps 3 s — sine wave 440 Hz."""
    out = tmp_path_factory.mktemp("fixtures") / "sample.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-b:a",
            "128k",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


@pytest.fixture(scope="session")
def sample_mp4(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """MP4 320×240 3 s com vídeo azul e áudio sine 440 Hz."""
    out = tmp_path_factory.mktemp("fixtures") / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "51",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


@pytest.fixture(scope="session")
def sample_wav_stereo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """WAV estéreo 44100 Hz 3 s — sine wave 440 Hz, 2 canais."""
    out = tmp_path_factory.mktemp("fixtures") / "sample_stereo.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


# ---------------------------------------------------------------------------
# Fixture de imagem de sessão — gerada via Pillow
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def session_jpg(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """JPEG RGB 640×480 reutilizável em escopo de sessão."""
    out = tmp_path_factory.mktemp("fixtures") / "session_sample.jpg"
    Image.new("RGB", (640, 480), color=(80, 120, 200)).save(
        out, format="JPEG", quality=85
    )
    return out


# ---------------------------------------------------------------------------
# Fixtures de PDF de sessão — geradas via pymupdf (importorskip se ausente)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory: pytest.TempPathFactory):
    """3-page PDF with extractable text — generated via pymupdf."""
    pymupdf = pytest.importorskip("pymupdf")
    tmp = tmp_path_factory.mktemp("pdfs")
    path = tmp / "sample.pdf"
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}\nTest content for extraction.")
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture(scope="session")
def sample_pdf_with_images(tmp_path_factory: pytest.TempPathFactory, session_jpg):
    """PDF with an embedded JPEG — used by compress tests."""
    pymupdf = pytest.importorskip("pymupdf")
    tmp = tmp_path_factory.mktemp("pdfs")
    path = tmp / "with_images.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    rect = pymupdf.Rect(50, 50, 500, 400)
    page.insert_image(rect, filename=str(session_jpg))
    doc.save(str(path))
    doc.close()
    return path


# ---------------------------------------------------------------------------
# Hook: pula testes de integração automaticamente se ffmpeg não estiver no PATH
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config, items):
    import shutil

    if shutil.which("ffmpeg") is None:
        skip_no_ffmpeg = pytest.mark.skip(reason="ffmpeg não encontrado no PATH")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip_no_ffmpeg)
