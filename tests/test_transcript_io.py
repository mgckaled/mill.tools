"""Unit tests for src/transcript_io.py.

Single owner of the header/body split previously duplicated (with diverging
semantics) across analyzer.py, formatter.py and prompter.py — see Fase 2 of
docs/plans/active/PLANO_CORRECOES_SRC_RAIZ.md.
"""

import pytest

pytestmark = pytest.mark.unit

_HEADER = """title:        Test Video
channel:      Test Channel
upload_date:  2024-01-15
duration:     00:02:05
language:     pt
url:          https://youtu.be/abc123
""" + ("-" * 64)


# ── split_header_body ────────────────────────────────────────────────────────


def test_split_header_body_with_separator():
    from src.transcript_io import split_header_body

    text = _HEADER + "\n\nThis is the body."
    header, body = split_header_body(text)
    assert body == "This is the body."
    assert "title:" in header


def test_split_header_body_no_separator():
    from src.transcript_io import split_header_body

    header, body = split_header_body("just body")
    assert header == ""
    assert body == "just body"


def test_split_header_body_ignores_separator_look_alike_deep_in_body():
    from src.transcript_io import split_header_body

    # A plain text with no real metadata header can still coincidentally
    # contain a run of 64+ dashes far into its own body — must not be
    # mistaken for the header separator and silently drop everything before it.
    sep = "-" * 64
    body_before = "Paragrafo real com conteudo. " * 200
    text = f"{body_before}\n{sep}\nMais texto depois."
    header, body = split_header_body(text)
    assert header == ""
    assert body == text.strip()


def test_split_header_body_separator_exactly_at_window_edge_is_still_a_header():
    from src.transcript_io import HEADER_SEARCH_WINDOW, SEPARATOR, split_header_body

    padding = "x" * (HEADER_SEARCH_WINDOW - len(SEPARATOR))
    text = padding + SEPARATOR + "\nbody"
    header, body = split_header_body(text)
    assert header == padding
    assert body == "body"


# ── parse_header_meta ────────────────────────────────────────────────────────


def test_parse_header_meta_extracts_fields():
    from src.transcript_io import parse_header_meta, split_header_body

    header, _ = split_header_body(_HEADER + "\nbody")
    meta = parse_header_meta(header)
    assert meta["title"] == "Test Video"
    assert meta["channel"] == "Test Channel"
    assert meta["url"] == "https://youtu.be/abc123"


def test_parse_header_meta_empty_header_returns_empty_dict():
    from src.transcript_io import parse_header_meta

    assert parse_header_meta("") == {}


def test_parse_header_meta_skips_lines_without_colon():
    from src.transcript_io import parse_header_meta

    header = "title: T\nnocolon line\nurl: https://x"
    assert parse_header_meta(header) == {"title": "T", "url": "https://x"}


def test_parse_header_meta_skips_empty_keys_or_values():
    from src.transcript_io import parse_header_meta

    header = "title: \n: orphan_value\nurl: https://x"
    assert parse_header_meta(header) == {"url": "https://x"}
