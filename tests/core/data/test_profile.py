"""Tests for the textual data profile."""

import pytest


@pytest.mark.unit
def test_profile_file_writes_report(csv_sales, tmp_path):
    from src.core.data.profile import profile_file

    out = profile_file(csv_sales, tmp_path)
    assert out.name == "vendas_profile.txt"
    text = out.read_text(encoding="utf-8")
    assert "Linhas: 3" in text
    assert "Colunas: 3" in text
    assert "produto" in text
    assert "qtd" in text


@pytest.mark.unit
def test_format_profile_is_pure_and_rounds(tmp_path):
    from pathlib import Path

    from src.core.data.profile import format_profile
    from src.core.data.types import ColumnInfo, DataFile, QueryResult

    file = DataFile(
        path=Path("t.csv"),
        view_name="t",
        n_rows=10,
        columns=[ColumnInfo("a", "DOUBLE")],
    )
    summary = QueryResult(
        columns=["column_name", "column_type", "avg", "null_percentage"],
        rows=[("a", "DOUBLE", "3.3333333333333335", "0.0")],
        elapsed=0.0,
        n_rows=1,
    )
    text = format_profile(file, summary)
    assert "média: 3.333" in text  # rounded to 4 significant figures
    assert "3.3333333333333335" not in text


@pytest.mark.unit
def test_fmt_cell_handles_text_and_null():
    from src.core.data.profile import _fmt_cell

    assert _fmt_cell(None) == "-"
    assert _fmt_cell("") == "-"
    assert _fmt_cell("banana") == "banana"  # genuine text passes through
    assert _fmt_cell(5) == "5"
