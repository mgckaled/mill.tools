import pytest
from pathlib import Path
from src.cli.transcription import build_output_stem, resolve_input
from src.core.io_types import InputItem
from src.gui.modules._pipeline_runner import item_label


# ── build_output_stem ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_build_output_stem_uses_title():
    meta = {"title": "Test Video | Part 1"}
    result = build_output_stem(meta)
    assert result == "Test_Video-Part_1"
    assert "/" not in result
    assert "\\" not in result


@pytest.mark.unit
def test_build_output_stem_custom_name():
    meta = {"title": "Test Video"}
    result = build_output_stem(meta, custom_name="my output")
    assert result == "my_output"


@pytest.mark.unit
def test_build_output_stem_custom_name_takes_priority():
    meta = {"title": "Other Title"}
    result = build_output_stem(meta, custom_name="override")
    assert result == "override"


@pytest.mark.unit
def test_build_output_stem_fallback_no_title():
    result = build_output_stem({})
    assert result.startswith("transcription_")


@pytest.mark.unit
def test_build_output_stem_fallback_empty_sanitized_title():
    """Title that sanitises to empty string falls back to timestamp."""
    result = build_output_stem({"title": "!!!"})
    assert result.startswith("transcription_")


@pytest.mark.unit
def test_build_output_stem_no_spaces_or_invalid_chars():
    meta = {"title": 'My Video "Final" Version'}
    result = build_output_stem(meta)
    assert " " not in result
    assert '"' not in result


# ── resolve_input ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_resolve_input_url():
    kind, value = resolve_input("https://www.youtube.com/watch?v=test123")
    assert kind == "url"
    assert value == "https://www.youtube.com/watch?v=test123"


@pytest.mark.unit
def test_resolve_input_non_youtube_url():
    kind, value = resolve_input("https://soundcloud.com/artist/track")
    assert kind == "url"


@pytest.mark.unit
def test_resolve_input_existing_file(tmp_path):
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"")
    kind, value = resolve_input(str(f))
    assert kind == "local"
    assert Path(value).exists()


@pytest.mark.unit
def test_resolve_input_nonexistent_path_treated_as_url():
    kind, _ = resolve_input("/nonexistent/path/audio.mp3")
    assert kind == "url"


# ── item_label ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_item_label_local_returns_filename(tmp_path):
    f = tmp_path / "my_audio.mp3"
    f.write_bytes(b"")
    item = InputItem(kind="local", value=str(f))
    assert item_label(item) == "my_audio.mp3"


@pytest.mark.unit
def test_item_label_url_returns_netloc():
    item = InputItem(kind="url", value="https://www.youtube.com/watch?v=abc")
    assert item_label(item) == "www.youtube.com"
