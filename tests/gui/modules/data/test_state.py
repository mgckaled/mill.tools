"""Unit tests for the Data module's pure view-state helpers."""

from pathlib import Path

import pytest

from src.gui.modules.data._state import (
    build_refine_prompt,
    file_by_name,
    is_data_source,
    page_window,
    result_status,
    save_stem,
)


class _FakeFile:
    def __init__(self, name):
        self.path = Path(name)


@pytest.mark.unit
@pytest.mark.parametrize(
    "name,expected",
    [
        ("a.csv", True),
        ("a.TSV", True),
        ("a.json", True),
        ("a.parquet", True),
        ("a.xlsx", True),
        ("a.pq", True),
        ("a.txt", False),
        ("a.mp3", False),
        ("noext", False),
    ],
)
def test_is_data_source(name, expected):
    assert is_data_source(Path(name)) is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [("", "consulta"), (None, "consulta"), ("  ", "consulta"), ("  vendas ", "vendas")],
)
def test_save_stem(raw, expected):
    assert save_stem(raw) == expected


@pytest.mark.unit
def test_result_status_plain():
    assert result_status(42, 0.123, False) == "42 linha(s) · 0.123s"


@pytest.mark.unit
def test_result_status_truncated():
    assert result_status(200, 1.5, True) == "200 linha(s) · 1.500s · prévia limitada"


@pytest.mark.unit
def test_build_refine_prompt_uses_question_and_error():
    out = build_refine_prompt("total por produto", "SELECT x", "no column x")
    assert out.startswith("total por produto\n\n")
    assert "SQL com erro: SELECT x" in out
    assert "Mensagem de erro: no column x" in out


@pytest.mark.unit
def test_build_refine_prompt_defaults_blank_question():
    out = build_refine_prompt("", "", "boom")
    assert out.startswith("Corrija a consulta SQL para responder à pergunta.")
    assert "SQL com erro: (desconhecido)" in out


@pytest.mark.unit
def test_file_by_name_matches():
    files = [_FakeFile("a.csv"), _FakeFile("b.csv")]
    assert file_by_name(files, "b.csv").path.name == "b.csv"


@pytest.mark.unit
def test_file_by_name_falls_back_to_first():
    files = [_FakeFile("a.csv"), _FakeFile("b.csv")]
    assert file_by_name(files, "missing.csv").path.name == "a.csv"
    assert file_by_name(files, None).path.name == "a.csv"


@pytest.mark.unit
def test_file_by_name_empty_returns_none():
    assert file_by_name([], "a.csv") is None


@pytest.mark.unit
def test_page_window_empty():
    w = page_window(0, 0, 50)
    assert w.start == 0
    assert w.end == 0
    assert w.label == "—"
    assert not w.has_prev
    assert not w.has_next


@pytest.mark.unit
def test_page_window_first_page_of_many():
    w = page_window(200, 0, 50)
    assert (w.start, w.end) == (0, 50)
    assert w.label == "1–50 de 200"
    assert not w.has_prev
    assert w.has_next


@pytest.mark.unit
def test_page_window_middle_page():
    w = page_window(200, 2, 50)
    assert (w.start, w.end) == (100, 150)
    assert w.label == "101–150 de 200"
    assert w.has_prev
    assert w.has_next


@pytest.mark.unit
def test_page_window_last_partial_page():
    w = page_window(120, 2, 50)
    assert (w.start, w.end) == (100, 120)
    assert w.label == "101–120 de 120"
    assert w.has_prev
    assert not w.has_next


@pytest.mark.unit
def test_page_window_single_page_exact():
    w = page_window(50, 0, 50)
    assert (w.start, w.end) == (0, 50)
    assert not w.has_prev
    assert not w.has_next
