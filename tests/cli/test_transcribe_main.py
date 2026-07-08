"""Unit tests for main.py — transcribe parser and subtitle helpers."""

import argparse

import pytest

pytestmark = pytest.mark.unit


def _parse(*argv: str) -> argparse.Namespace:
    """Run main.parse_args with explicit argv (never touches sys.argv)."""
    import main as main_mod

    return main_mod.parse_args(list(argv))


# ── _subtitle_formats_from_args ──────────────────────────────────────────────


def test_subtitle_formats_no_flags_returns_empty():
    from main import _subtitle_formats_from_args

    ns = _parse("https://youtu.be/abc")
    assert _subtitle_formats_from_args(ns) == ()


def test_subtitle_formats_srt_only():
    from main import _subtitle_formats_from_args

    ns = _parse("https://youtu.be/abc", "--srt")
    assert _subtitle_formats_from_args(ns) == ("srt",)


def test_subtitle_formats_vtt_only():
    from main import _subtitle_formats_from_args

    ns = _parse("https://youtu.be/abc", "--vtt")
    assert _subtitle_formats_from_args(ns) == ("vtt",)


def test_subtitle_formats_srt_and_vtt():
    """Combining both individual flags yields ordered ('srt', 'vtt')."""
    from main import _subtitle_formats_from_args

    ns = _parse("https://youtu.be/abc", "--srt", "--vtt")
    assert _subtitle_formats_from_args(ns) == ("srt", "vtt")


def test_subtitle_formats_subtitles_shortcut_expands_to_both():
    from main import _subtitle_formats_from_args

    ns = _parse("https://youtu.be/abc", "--subtitles")
    assert _subtitle_formats_from_args(ns) == ("srt", "vtt")


def test_subtitle_formats_subtitles_takes_priority_over_individual():
    """When --subtitles is set, individual flags are subsumed (same result)."""
    from main import _subtitle_formats_from_args

    ns = _parse("https://youtu.be/abc", "--subtitles", "--srt")
    assert _subtitle_formats_from_args(ns) == ("srt", "vtt")


# ── parser defaults ──────────────────────────────────────────────────────────


def test_parse_args_subtitle_flags_default_false():
    ns = _parse("https://youtu.be/abc")
    assert ns.srt is False
    assert ns.vtt is False
    assert ns.subtitles is False


def test_parse_args_subtitle_flags_true_when_passed():
    ns = _parse("https://youtu.be/abc", "--srt", "--vtt")
    assert ns.srt is True
    assert ns.vtt is True


def test_parse_args_other_existing_flags_unchanged_by_subtitle_addition():
    """Sanity: --format and --analyze still parse correctly."""
    ns = _parse("https://youtu.be/abc", "--format", "--analyze", "--srt")
    assert ns.format is True
    assert ns.analyze is True
    assert ns.srt is True


# ── --profile (analysis profile) ─────────────────────────────────────────────


def test_parse_args_profile_defaults_to_default():
    ns = _parse("https://youtu.be/abc")
    assert ns.profile == "default"


def test_parse_args_profile_accepts_valid_choice():
    ns = _parse("https://youtu.be/abc", "--analyze", "--profile", "lecture")
    assert ns.profile == "lecture"


def test_parse_args_profile_rejects_unknown_choice():
    with pytest.raises(SystemExit):
        _parse("https://youtu.be/abc", "--profile", "does-not-exist")


# ── main() — check_dependencies conditional by input kind (Fase 4) ──────────


def test_main_skips_check_dependencies_for_local_text_input(
    tmp_path, mocker, monkeypatch
):
    import main as main_mod

    txt = tmp_path / "notas.txt"
    txt.write_text("algum conteudo de texto.", encoding="utf-8")
    monkeypatch.setattr(main_mod, "TRANSCRIPTIONS_TEXT_DIR", tmp_path / "out")
    mocker.patch("main.setup_logging")
    mock_check = mocker.patch("main.check_dependencies")
    mocker.patch("sys.argv", ["main.py", str(txt)])

    main_mod.main()

    mock_check.assert_not_called()


def test_main_calls_check_dependencies_for_url_input(mocker):
    import main as main_mod

    mocker.patch("main.setup_logging")
    mock_check = mocker.patch(
        "main.check_dependencies", side_effect=RuntimeError("stop before network")
    )
    mocker.patch("sys.argv", ["main.py", "https://youtu.be/abc123"])

    with pytest.raises(SystemExit):
        main_mod.main()

    mock_check.assert_called_once()


# ── main() — avisos de UX pra entrada de texto (Fase 4) ──────────────────────


def test_main_text_input_without_ai_steps_warns(tmp_path, mocker, monkeypatch, caplog):
    import logging as _logging

    import main as main_mod

    txt = tmp_path / "notas.txt"
    txt.write_text("algum conteudo de texto.", encoding="utf-8")
    monkeypatch.setattr(main_mod, "TRANSCRIPTIONS_TEXT_DIR", tmp_path / "out")
    mocker.patch("main.setup_logging")
    mocker.patch("sys.argv", ["main.py", str(txt)])

    with caplog.at_level(_logging.WARNING, logger="root"):
        main_mod.main()

    assert any("Nenhuma etapa de IA" in r.message for r in caplog.records)


def test_main_text_input_with_ai_step_does_not_warn(
    tmp_path, mocker, monkeypatch, caplog
):
    import logging as _logging

    import main as main_mod

    txt = tmp_path / "notas.txt"
    txt.write_text("algum conteudo de texto.", encoding="utf-8")
    monkeypatch.setattr(main_mod, "TRANSCRIPTIONS_TEXT_DIR", tmp_path / "out")
    mocker.patch("main.setup_logging")
    mocker.patch("src.prompter.build_prompt_ready")
    mocker.patch("sys.argv", ["main.py", str(txt), "--prompt"])

    with caplog.at_level(_logging.WARNING, logger="root"):
        main_mod.main()

    assert not any("Nenhuma etapa de IA" in r.message for r in caplog.records)


def test_main_text_input_with_subtitle_flags_warns(
    tmp_path, mocker, monkeypatch, caplog
):
    import logging as _logging

    import main as main_mod

    txt = tmp_path / "notas.txt"
    txt.write_text("algum conteudo de texto.", encoding="utf-8")
    monkeypatch.setattr(main_mod, "TRANSCRIPTIONS_TEXT_DIR", tmp_path / "out")
    mocker.patch("main.setup_logging")
    mocker.patch("sys.argv", ["main.py", str(txt), "--srt"])

    with caplog.at_level(_logging.WARNING, logger="root"):
        main_mod.main()

    assert any("ignorados para entrada de texto" in r.message for r in caplog.records)


def test_main_media_input_with_subtitle_flags_does_not_warn(
    tmp_path, mocker, monkeypatch, caplog
):
    """Sanity: the text-input-only warning must not fire for local media."""
    import logging as _logging

    import main as main_mod

    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    monkeypatch.setattr(main_mod, "TRANSCRIPTIONS_TEXT_DIR", tmp_path / "out")
    mocker.patch("main.setup_logging")
    mocker.patch("main.transcribe", return_value=None)
    mocker.patch("sys.argv", ["main.py", str(audio), "--srt"])

    with caplog.at_level(_logging.WARNING, logger="root"):
        main_mod.main()

    assert not any(
        "ignorados para entrada de texto" in r.message for r in caplog.records
    )
