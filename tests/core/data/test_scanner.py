"""Tests for the data-file scanner and schema rendering."""

import pytest


@pytest.mark.unit
def test_scan_files_assigns_distinct_view_names(csv_sales, json_file):
    from src.core.data.scanner import scan_files

    files = scan_files([csv_sales, json_file])
    names = [f.view_name for f in files]
    assert names == ["vendas", "itens"]
    assert all(f.n_rows >= 1 for f in files)


@pytest.mark.unit
def test_scan_file_populates_columns(csv_sales):
    from src.core.data.scanner import scan_file

    df = scan_file(csv_sales)
    assert df.n_cols == 3
    assert df.view_name == "vendas"
    assert [c.name for c in df.columns] == ["produto", "qtd", "preco"]


@pytest.mark.unit
def test_is_supported():
    from pathlib import Path

    from src.core.data.scanner import is_supported

    assert is_supported(Path("a.csv"))
    assert is_supported(Path("a.parquet"))
    assert is_supported(Path("a.xlsx"))
    assert not is_supported(Path("a.bin"))


@pytest.mark.unit
def test_schema_text_lists_names_and_types_only(csv_sales):
    from src.core.data.scanner import scan_files, schema_text

    files = scan_files([csv_sales])
    text = schema_text(files)
    assert "vendas (3 linhas):" in text
    assert "produto VARCHAR" in text
    assert "qtd BIGINT" in text
    # No data row ever leaks into the schema string.
    assert "maca" not in text
    assert "banana" not in text
