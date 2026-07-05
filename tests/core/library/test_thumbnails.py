"""Unit tests for src/core/library/thumbnails.py — dispatch + safe fallbacks."""

from __future__ import annotations

from pathlib import Path

import pytest


def _item(path: Path, kind: str):
    """Build a LibraryItem for a path with the given logical kind."""
    from src.core.library.types import LibraryItem

    return LibraryItem(
        path=path,
        kind=kind,
        category="processed",
        size_bytes=path.stat().st_size if path.exists() else 0,
        modified=0.0,
        stem=path.stem,
        suffix=path.suffix.lower(),
    )


@pytest.mark.unit
def test_thumbnail_for_image_returns_bytes(jpg_image):
    from src.core.library.thumbnails import thumbnail_for
    from src.core.library.types import KIND_IMAGE

    data = thumbnail_for(_item(jpg_image, KIND_IMAGE))
    assert isinstance(data, bytes) and len(data) > 0


@pytest.mark.unit
def test_thumbnail_for_audio_and_transcription_fall_back_to_none(tmp_path):
    from src.core.library.thumbnails import thumbnail_for
    from src.core.library.types import KIND_AUDIO, KIND_TRANSCRIPTION

    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"ID3")
    text = tmp_path / "notes.txt"
    text.write_text("hello", encoding="utf-8")

    assert thumbnail_for(_item(audio, KIND_AUDIO)) is None
    assert thumbnail_for(_item(text, KIND_TRANSCRIPTION)) is None


@pytest.mark.unit
def test_thumbnail_for_audio_waveform_png_returns_bytes(jpg_image, tmp_path):
    """Waveform/spectrogram PNGs from the Audio module (kind='audio') still get
    a real raster preview — dispatch is by suffix first, not kind alone."""
    from src.core.library.thumbnails import thumbnail_for
    from src.core.library.types import KIND_AUDIO

    # Reuse the jpg_image fixture's bytes under a name matching Audio's output.
    waveform = tmp_path / "track_waveform.png"
    waveform.write_bytes(jpg_image.read_bytes())

    data = thumbnail_for(_item(waveform, KIND_AUDIO))
    assert isinstance(data, bytes) and len(data) > 0


@pytest.mark.unit
def test_thumbnail_for_pdf_returns_bytes(sample_pdf):
    from src.core.library.thumbnails import thumbnail_for
    from src.core.library.types import KIND_DOCUMENT

    data = thumbnail_for(_item(sample_pdf, KIND_DOCUMENT))
    assert isinstance(data, bytes) and len(data) > 0


@pytest.mark.unit
def test_thumbnail_for_corrupted_pdf_returns_none(tmp_path):
    from src.core.library.thumbnails import thumbnail_for
    from src.core.library.types import KIND_DOCUMENT

    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4 not really a pdf")
    assert thumbnail_for(_item(bad, KIND_DOCUMENT)) is None


@pytest.mark.unit
def test_thumbnail_for_corrupted_image_returns_none(tmp_path):
    from src.core.library.thumbnails import thumbnail_for
    from src.core.library.types import KIND_IMAGE

    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not a png")
    assert thumbnail_for(_item(bad, KIND_IMAGE)) is None


@pytest.mark.unit
def test_thumbnail_for_non_pdf_document_returns_none(tmp_path):
    from src.core.library.thumbnails import thumbnail_for
    from src.core.library.types import KIND_DOCUMENT

    # A document-kind file that is not a .pdf (e.g. an extracted .txt) gets the
    # type icon, not a raster.
    other = tmp_path / "extracted.txt"
    other.write_text("content", encoding="utf-8")
    assert thumbnail_for(_item(other, KIND_DOCUMENT)) is None


@pytest.mark.integration
def test_thumbnail_for_video_returns_bytes(sample_mp4):
    from src.core.library.thumbnails import thumbnail_for
    from src.core.library.types import KIND_VIDEO

    data = thumbnail_for(_item(sample_mp4, KIND_VIDEO))
    assert isinstance(data, bytes) and len(data) > 0
