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


@pytest.mark.unit
def test_summarize_sql_full_for_small_files():
    from src.core.data.profile import summarize_sql

    # Below the threshold: a plain whole-table SUMMARIZE (no sampling).
    sql = summarize_sql("vendas", 100)
    assert sql == 'SUMMARIZE "vendas"'
    assert "SAMPLE" not in sql


@pytest.mark.unit
def test_summarize_sql_samples_large_files():
    from src.core.data.profile import summarize_sql

    # Past the threshold: SUMMARIZE over a reservoir sample so profiling a huge
    # file never scans it end-to-end.
    sql = summarize_sql("big", 5_000_000, threshold=1000, sample_rows=2000)
    assert sql == 'SUMMARIZE SELECT * FROM "big" USING SAMPLE 2000 ROWS'


@pytest.mark.unit
def test_profile_text_returns_report_without_writing(csv_sales):
    from src.core.data.profile import profile_text

    text = profile_text(csv_sales)
    assert "Linhas: 3" in text
    assert "produto" in text


@pytest.mark.unit
def test_profile_text_accepts_an_already_scanned_data_file(csv_sales, mocker):
    """Passing a pre-scanned DataFile must skip the internal scan_file call
    (the seam the data-card builder uses to avoid a 2nd DESCRIBE/count(*))."""
    from src.core.data import scanner
    from src.core.data.profile import profile_text

    file = scanner.scan_file(csv_sales)
    spy = mocker.spy(scanner, "scan_file")

    text = profile_text(file)

    assert spy.call_count == 0
    assert "Linhas: 3" in text
