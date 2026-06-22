"""Tests for the DuckDB boundary: scanning, encoding, queries, registration."""

import pytest


@pytest.mark.unit
def test_view_name_for_sanitizes_and_dedupes():
    from pathlib import Path

    from src.core.data.engine import view_name_for

    taken: set[str] = set()
    assert view_name_for(Path("My File.csv"), taken) == "my_file"
    assert view_name_for(Path("my file.csv"), taken) == "my_file_2"  # collision
    assert view_name_for(Path("123.csv"), taken) == "t_123"  # leading digit
    assert view_name_for(Path("!!!.csv"), taken) == "data"  # empty stem


@pytest.mark.unit
def test_detect_encoding_utf8_and_cp1252(csv_sales, csv_people_cp1252):
    from src.core.data.engine import detect_encoding

    assert detect_encoding(csv_sales) == "utf-8"
    # cp1252 is mapped onto latin-1 (DuckDB-compatible, lossless for these chars)
    assert detect_encoding(csv_people_cp1252) == "latin-1"


@pytest.mark.unit
def test_describe_file_counts_rows_and_columns(csv_sales):
    from src.core.data.engine import describe_file

    n_rows, columns = describe_file(csv_sales)
    assert n_rows == 3
    names = [c.name for c in columns]
    assert names == ["produto", "qtd", "preco"]
    assert columns[1].dtype == "BIGINT"


@pytest.mark.unit
def test_run_query_join_and_aggregate(csv_sales):
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files

    files = scan_files([csv_sales])
    view = files[0].view_name
    res = run_query(
        files,
        f'SELECT produto, sum(qtd) AS total FROM "{view}" GROUP BY produto '
        "ORDER BY total DESC, produto",
    )
    assert res.columns == ["produto", "total"]
    assert res.rows == [("banana", 5), ("maca", 5)]
    assert res.n_rows == 2
    assert res.elapsed >= 0.0


@pytest.mark.unit
def test_run_query_reads_cp1252(csv_people_cp1252):
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files

    files = scan_files([csv_people_cp1252])
    res = run_query(files, f'SELECT cidade FROM "{files[0].view_name}" ORDER BY nome')
    # latin-1 decoding preserves the accented characters
    assert ("Córdoba",) in res.rows
    assert ("São Paulo",) in res.rows


@pytest.mark.unit
def test_run_query_max_rows_caps_preview(csv_sales):
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files

    files = scan_files([csv_sales])
    res = run_query(files, f'SELECT * FROM "{files[0].view_name}"', max_rows=2)
    assert res.n_rows == 2


@pytest.mark.unit
def test_run_query_rejects_non_select(csv_sales):
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files
    from src.core.data.validate import UnsafeQueryError

    files = scan_files([csv_sales])
    with pytest.raises(UnsafeQueryError):
        run_query(files, "DROP TABLE vendas")


@pytest.mark.unit
def test_run_query_bad_sql_raises_engine_error(csv_sales):
    from src.core.data.engine import DataEngineError, run_query
    from src.core.data.scanner import scan_files

    files = scan_files([csv_sales])
    with pytest.raises(DataEngineError):
        run_query(files, "SELECT nonexistent_col FROM vendas")


@pytest.mark.unit
def test_reader_expr_unsupported_format(tmp_path):
    from src.core.data.engine import DataEngineError, reader_expr

    with pytest.raises(DataEngineError):
        reader_expr(tmp_path / "x.bin")


@pytest.mark.unit
def test_detect_encoding_missing_file_falls_back(tmp_path):
    from src.core.data.engine import detect_encoding

    # charset detection on a nonexistent path must not raise — defaults to utf-8.
    assert detect_encoding(tmp_path / "nope.csv") == "utf-8"


@pytest.mark.unit
def test_export_query_writes_file(csv_sales, tmp_path):
    from src.core.data.engine import export_query
    from src.core.data.scanner import scan_files

    files = scan_files([csv_sales])
    out = tmp_path / "out" / "r.csv"
    result = export_query(
        files, f'SELECT * FROM "{files[0].view_name}"', out, "(FORMAT csv, HEADER true)"
    )
    assert result == out
    assert out.exists()


@pytest.mark.unit
def test_export_query_bad_sql_raises_engine_error(csv_sales, tmp_path):
    from src.core.data.engine import DataEngineError, export_query
    from src.core.data.scanner import scan_files

    files = scan_files([csv_sales])
    with pytest.raises(DataEngineError):
        export_query(
            files,
            f'SELECT bad FROM "{files[0].view_name}"',
            tmp_path / "x.csv",
            "(FORMAT csv)",
        )


@pytest.mark.unit
def test_json_file_is_queryable(json_file):
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files

    files = scan_files([json_file])
    res = run_query(files, f'SELECT count(*) AS n FROM "{files[0].view_name}"')
    assert res.rows == [(2,)]
