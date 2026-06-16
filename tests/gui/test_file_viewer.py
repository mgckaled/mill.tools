"""Unit tests for the Library in-app file viewer gating."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.gui.views.file_viewer import is_viewable


@pytest.mark.unit
@pytest.mark.parametrize("name", ["analise.md", "notas.txt", "A.MD", "B.TXT"])
def test_is_viewable_accepts_text_outputs(name: str):
    assert is_viewable(Path(name))


@pytest.mark.unit
@pytest.mark.parametrize(
    "name", ["song.mp3", "clip.mp4", "doc.pdf", "pic.png", "noext"]
)
def test_is_viewable_rejects_non_text(name: str):
    assert not is_viewable(Path(name))
