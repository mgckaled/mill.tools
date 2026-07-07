"""Unit tests for src/cli/reference.py — introspected CLI reference + validator."""

from __future__ import annotations

import pytest

from src.cli.reference import build_reference, validate_command

_PREFIX = "uv run main.py "


# ── build_reference ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_reference_contains_known_operations():
    ref = build_reference()
    assert "video trim" in ref
    assert "image contact-sheet" in ref
    assert "data query" in ref
    assert "transcribe" in ref
    assert "audio-viz" in ref


@pytest.mark.unit
def test_reference_preserves_kebab_case_operations():
    ref = build_reference()
    assert "image contact-sheet" in ref
    assert "video extract-audio" in ref
    assert "library dedup-images" in ref
    assert "document images-to-pdf" in ref
    # snake_case never leaks into the reference text (that conversion only
    # happens at runtime in the CLI dispatchers, e.g. `op.replace("-", "_")`).
    assert "contact_sheet" not in ref
    assert "extract_audio" not in ref


@pytest.mark.unit
def test_reference_shows_choices_and_defaults():
    ref = build_reference()
    line = next(ln for ln in ref.splitlines() if ln.startswith("video extract-audio "))
    assert "{mp3|m4a|wav|ogg|opus}" in line
    assert "=mp3" in line


@pytest.mark.unit
def test_reference_marks_required_flag_without_brackets():
    ref = build_reference()
    line = next(ln for ln in ref.splitlines() if ln.startswith("video trim "))
    assert "--start <TIME>" in line
    assert "[--start" not in line
    assert "[--end <TIME>]" in line  # optional flags stay bracketed


@pytest.mark.unit
def test_reference_includes_operation_description():
    ref = build_reference()
    line = next(ln for ln in ref.splitlines() if ln.startswith("video trim "))
    assert "Trim video to a time range" in line


@pytest.mark.unit
def test_reference_is_cached_across_calls():
    assert build_reference() is build_reference()


# ── validate_command ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_validate_command_accepts_a_valid_command():
    assert validate_command(f"{_PREFIX}video trim video.mp4 --start 0:30") is None


@pytest.mark.unit
def test_validate_command_accepts_kebab_case_operation():
    assert validate_command(f"{_PREFIX}image contact-sheet a.jpg b.jpg") is None


@pytest.mark.unit
def test_validate_command_accepts_multi_input_data_query():
    assert (
        validate_command(f'{_PREFIX}data query a.csv b.csv "quantas linhas tem?"')
        is None
    )


@pytest.mark.unit
def test_validate_command_rejects_missing_prefix():
    message = validate_command("video trim video.mp4 --start 0:30")
    assert message is not None
    assert _PREFIX.strip() in message


@pytest.mark.unit
def test_validate_command_rejects_unknown_operation():
    message = validate_command(f"{_PREFIX}video fly video.mp4")
    assert message is not None
    assert "invalid choice" in message


@pytest.mark.unit
def test_validate_command_rejects_unknown_subcommand():
    message = validate_command(f"{_PREFIX}teleport video.mp4")
    assert message is not None


@pytest.mark.unit
def test_validate_command_rejects_missing_required_flag():
    message = validate_command(f"{_PREFIX}video trim video.mp4")
    assert message is not None
    assert "--start" in message


@pytest.mark.unit
def test_validate_command_rejects_empty_after_prefix():
    message = validate_command(_PREFIX)
    assert message is not None


@pytest.mark.unit
def test_validate_command_handles_windows_paths():
    assert validate_command(f'{_PREFIX}video convert "C:\\videos\\clip.mp4"') is None
