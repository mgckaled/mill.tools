"""Unit tests for kind_for — map a resolve_input() result to a recipe kind."""

import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "value,expected",
    [
        ("a.mp3", "audio"),
        ("a.WAV", "audio"),
        ("a.m4a", "audio"),
        ("v.mp4", "video"),
        ("v.mkv", "video"),
        ("i.png", "image"),
        ("i.jpeg", "image"),
        ("d.pdf", "pdf"),
        ("notes.txt", "text"),
        ("notes.md", "text"),
    ],
)
def test_kind_for_local_by_extension(value, expected):
    from src.core.recipes.inputs import kind_for

    assert kind_for("local", value) == expected


@pytest.mark.unit
def test_kind_for_url():
    from src.core.recipes.inputs import kind_for

    assert kind_for("url", "https://youtu.be/abc") == "url"


@pytest.mark.unit
def test_kind_for_unsupported_extension_raises():
    from src.core.recipes.inputs import kind_for

    with pytest.raises(ValueError, match="não suportado"):
        kind_for("local", "archive.zip")
