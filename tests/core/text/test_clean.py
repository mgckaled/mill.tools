"""Unit tests for src/core/text/clean.py — shared PDF-extraction text cleanup."""

from __future__ import annotations

import pytest

from src.core.text import clean


# --- page markers -------------------------------------------------------------


@pytest.mark.unit
def test_page_marker_matches_converter_format():
    # core/document/converter.py builds the exact same string via this
    # function -- this pins the format both sides share.
    assert clean.page_marker(1) == "--- Página 1 ---"
    assert clean.page_marker(12) == "--- Página 12 ---"


@pytest.mark.unit
def test_strip_page_markers_removes_marker_lines():
    text = f"Texto da página um.\n\n{clean.page_marker(2)}\n\nTexto da página dois."
    out = clean.strip_page_markers(text)
    assert "Página" not in out
    assert "Texto da página um." in out
    assert "Texto da página dois." in out


@pytest.mark.unit
def test_strip_page_markers_noop_without_markers():
    text = "Um texto qualquer sem marcador nenhum."
    assert clean.strip_page_markers(text) == text


# --- abbreviation masking -------------------------------------------------------


@pytest.mark.unit
def test_mask_unmask_round_trip():
    text = "Ex: e.g. isso, i.e. aquilo, et al. mais, Dr. Fulano, p. ex. isso."
    masked = clean.mask_abbreviations(text)
    assert clean.unmask_abbreviations(masked) == text


@pytest.mark.unit
def test_mask_abbreviations_hides_dot_from_naive_split():
    import re

    text = "Fizemos o teste, e.g. o caso A. Depois seguimos."
    masked = clean.mask_abbreviations(text)
    # A naive [.!?]\s+ split must not cut right after "e.g" anymore.
    parts = re.split(r"(?<=[.!?])\s+", masked)
    assert not any(p.rstrip().endswith(("e", "e.g")) for p in parts[:-1])


# --- list-item boundaries -------------------------------------------------------


@pytest.mark.unit
def test_terminate_list_items_adds_period_when_missing():
    text = "- Helpful\n- Honest\n- Harmless\nProsa depois da lista."
    out = clean._terminate_list_items(text)
    assert "- Helpful.\n" in out
    assert "- Honest.\n" in out
    assert "- Harmless.\n" in out


@pytest.mark.unit
def test_terminate_list_items_keeps_existing_punctuation():
    text = "- Já pontuado!\n- Outro item?"
    out = clean._terminate_list_items(text)
    assert "- Já pontuado!\n" in out
    assert out.rstrip().endswith("- Outro item?")


@pytest.mark.unit
def test_terminate_list_items_ignores_non_list_lines():
    text = "Uma frase comum sem marcador de lista"
    assert clean._terminate_list_items(text) == text


# --- non-prose line filter -------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "line",
    [
        "Claude's Constitution",
        "Anthropic",
        "January 2024",
        "42",
    ],
)
def test_is_prose_line_flags_short_unpunctuated_lines_as_metadata(line):
    assert clean.is_prose_line(line) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "line",
    [
        "Ok.",  # short but punctuated -> real sentence
        "This is a longer line without a period at the end",  # long enough
    ],
)
def test_is_prose_line_keeps_punctuated_or_long_lines(line):
    assert clean.is_prose_line(line) is True


@pytest.mark.unit
def test_is_prose_line_blank_is_not_prose():
    assert clean.is_prose_line("   ") is False


@pytest.mark.unit
def test_filter_non_prose_drops_front_matter_keeps_body():
    text = "Claude's Constitution\nAnthropic\nJanuary 2024\nThis is a real sentence."
    out = clean.filter_non_prose(text)
    assert "Claude's Constitution" not in out
    assert "Anthropic" not in out
    assert "This is a real sentence." in out


@pytest.mark.unit
def test_filter_non_prose_preserves_blank_lines():
    text = "Primeira frase.\n\nSegunda frase."
    assert clean.filter_non_prose(text) == text


# --- clean_document_text (integration of the three steps) ----------------------


@pytest.mark.unit
def test_clean_document_text_strips_page_markers_and_front_matter(messy_pdf_text):
    out = clean.clean_document_text(messy_pdf_text)
    assert "Página" not in out
    assert "Claude's Constitution" not in out
    assert "Anthropic" not in out
    assert "January 2024" not in out
    assert "Acknowledgments" not in out
    assert "helpful, honest, and harmless" in out


@pytest.mark.unit
def test_clean_document_text_is_idempotent(messy_pdf_text):
    once = clean.clean_document_text(messy_pdf_text)
    twice = clean.clean_document_text(once)
    assert once == twice


@pytest.mark.unit
def test_clean_document_text_does_not_mask_abbreviations():
    # Structural cleaning alone must leave real dots untouched -- masking is
    # summarize.split_sentences' own concern, not clean_document_text's.
    text = "Fizemos o teste, e.g. o caso A."
    assert clean.clean_document_text(text) == text
