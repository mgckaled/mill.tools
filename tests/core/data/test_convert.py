"""Tests for format conversion and query export (round-trips via DuckDB)."""

import pytest


def _excel_available() -> bool:
    """True when DuckDB's excel extension can be loaded (cached/bundled)."""
    import duckdb

    try:
        con = duckdb.connect()
        con.execute("INSTALL excel; LOAD excel;")
        con.close()
        return True
    except Exception:
        return False


@pytest.mark.unit
@pytest.mark.parametrize("fmt", ["csv", "tsv", "json", "parquet"])
def test_convert_file_round_trips(csv_sales, tmp_path, fmt):
    from src.core.data.convert import convert_file
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files

    # Write to a separate dir so a csv→csv conversion never clobbers the source.
    out_dir = tmp_path / "out"
    out = convert_file(csv_sales, out_dir, fmt)
    assert out.exists()
    assert out.stat().st_size > 0

    # Read it back through the engine and confirm the data survived.
    files = scan_files([out])
    res = run_query(files, f'SELECT count(*) AS n FROM "{files[0].view_name}"')
    assert res.rows == [(3,)]


@pytest.mark.unit
@pytest.mark.skipif(not _excel_available(), reason="DuckDB excel extension unavailable")
def test_convert_to_xlsx_round_trips(csv_sales, tmp_path):
    from src.core.data.convert import convert_file
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files

    out = convert_file(csv_sales, tmp_path / "out", "xlsx")
    assert out.suffix == ".xlsx"
    assert out.exists()

    files = scan_files([out])
    res = run_query(files, f'SELECT count(*) AS n FROM "{files[0].view_name}"')
    assert res.rows == [(3,)]


@pytest.mark.unit
def test_convert_file_unknown_format(csv_sales, tmp_path):
    from src.core.data.convert import ConvertError, convert_file

    with pytest.raises(ConvertError):
        convert_file(csv_sales, tmp_path, "xml")


@pytest.mark.unit
def test_out_path_for_builds_extension(tmp_path):
    from src.core.data.convert import out_path_for

    assert out_path_for("rel", tmp_path, "parquet").name == "rel.parquet"
    assert out_path_for("rel", tmp_path, "csv").name == "rel.csv"


@pytest.mark.unit
def test_save_query_writes_result(csv_sales, tmp_path):
    from src.core.data.convert import save_query
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files

    files = scan_files([csv_sales])
    view = files[0].view_name
    out = save_query(
        files,
        f'SELECT produto, sum(qtd) AS total FROM "{view}" GROUP BY produto',
        tmp_path,
        "csv",
        "resumo",
    )
    assert out.name == "resumo.csv"

    back = scan_files([out])
    res = run_query(back, f'SELECT count(*) AS n FROM "{back[0].view_name}"')
    assert res.rows == [(2,)]


@pytest.mark.unit
def test_rename_sql_noop_when_empty():
    from src.core.data.convert import rename_sql

    base = "SELECT a, b FROM t"
    assert rename_sql(base, ["a", "b"], {}) == base
    # new name equal to old, or for a missing column, is ignored
    assert rename_sql(base, ["a", "b"], {"a": "a", "z": "x"}) == base


@pytest.mark.unit
def test_rename_sql_wraps_and_aliases(csv_sales):
    from src.core.data.convert import rename_sql
    from src.core.data.engine import run_query
    from src.core.data.scanner import scan_files

    files = scan_files([csv_sales])
    base = f'SELECT produto, qtd FROM "{files[0].view_name}"'
    wrapped = rename_sql(base, ["produto", "qtd"], {"produto": "item"})
    res = run_query(files, wrapped)
    assert res.columns == ["item", "qtd"]


@pytest.mark.unit
def test_save_query_rejects_non_select(csv_sales, tmp_path):
    from src.core.data.convert import save_query
    from src.core.data.scanner import scan_files
    from src.core.data.validate import UnsafeQueryError

    files = scan_files([csv_sales])
    with pytest.raises(UnsafeQueryError):
        save_query(files, "DROP TABLE vendas", tmp_path, "csv", "x")
