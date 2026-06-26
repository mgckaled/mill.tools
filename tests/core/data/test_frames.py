"""Tests for the DataFrame boundary (``frames.py``): QueryResult <-> Polars.

Polars/pandas/pyarrow live behind the optional ``[analysis]`` extra, so the whole
module skips gracefully when they are absent (``importorskip``), exactly like the
pymupdf-backed fixtures. DuckDB/Polars run in-process (no network/ffmpeg/GPU), so
these qualify as ``unit``.
"""

import datetime
import sys

import pytest

from src.core.data.types import QueryResult

pl = pytest.importorskip("polars")


@pytest.mark.unit
def test_is_available_true_with_extra_installed():
    from src.core.data import frames

    assert frames.is_available() is True


@pytest.mark.unit
def test_is_available_false_without_polars(mocker):
    from src.core.data import frames

    # A ``None`` entry in sys.modules makes ``import polars`` raise ImportError.
    mocker.patch.dict(sys.modules, {"polars": None})
    assert frames.is_available() is False


@pytest.mark.unit
def test_roundtrip_preserves_columns_rows_nrows_and_types():
    from src.core.data import frames

    r = QueryResult(
        columns=["i", "f", "s", "b", "d"],
        rows=[
            (1, 1.5, "maçã", True, datetime.date(2026, 6, 26)),
            (2, 0.8, "banana", False, datetime.date(2025, 1, 1)),
        ],
        elapsed=0.0,
        n_rows=2,
    )

    out = frames.to_result(frames.to_polars(r))

    assert out.columns == r.columns
    assert out.rows == r.rows
    assert out.n_rows == r.n_rows


@pytest.mark.unit
def test_roundtrip_preserves_nulls_without_nan():
    from src.core.data import frames

    r = QueryResult(
        columns=["i", "f"],
        rows=[(1, None), (None, 2.5), (3, None)],
        elapsed=0.0,
        n_rows=3,
    )

    out = frames.to_result(frames.to_polars(r))

    assert out.rows == r.rows  # None stays None, never coerced to a NaN float


@pytest.mark.unit
def test_roundtrip_empty_result():
    from src.core.data import frames

    r = QueryResult(columns=["a", "b"], rows=[], elapsed=0.0, n_rows=0)

    out = frames.to_result(frames.to_polars(r))

    assert out.columns == ["a", "b"]
    assert out.rows == []
    assert out.n_rows == 0


@pytest.mark.unit
def test_roundtrip_single_all_null_column():
    from src.core.data import frames

    r = QueryResult(columns=["only"], rows=[(None,), (None,)], elapsed=0.0, n_rows=2)

    out = frames.to_result(frames.to_polars(r))

    assert out.columns == ["only"]
    assert out.rows == [(None,), (None,)]


@pytest.mark.unit
def test_roundtrip_unicode_ptbr_strings():
    from src.core.data import frames

    r = QueryResult(
        columns=["cidade"],
        rows=[("São Paulo",), ("Córdoba",), ("Maricá",)],
        elapsed=0.0,
        n_rows=3,
    )

    out = frames.to_result(frames.to_polars(r))

    assert out.rows == r.rows


@pytest.mark.unit
def test_to_result_respects_limit():
    from src.core.data import frames

    df = pl.DataFrame({"n": [10, 20, 30, 40, 50]})

    out = frames.to_result(df, limit=2)

    assert out.rows == [(10,), (20,)]
    assert out.n_rows == 2


@pytest.mark.unit
def test_to_pandas_shape_columns_and_values():
    pytest.importorskip("pandas")
    from src.core.data import frames

    df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

    pdf = frames.to_pandas(df)

    assert list(pdf.columns) == ["a", "b"]
    assert pdf.shape == (3, 2)
    assert pdf["a"].tolist() == [1, 2, 3]
    assert pdf["b"].tolist() == ["x", "y", "z"]


@pytest.mark.unit
def test_optimize_shrinks_numeric_and_preserves_values():
    from src.core.data import frames

    df = pl.DataFrame({"small": [1, 2, 3]})  # inferred Int64
    assert df["small"].dtype == pl.Int64

    out = frames.optimize(df)

    assert out["small"].dtype == pl.Int8  # shrunk to the minimal width
    assert out["small"].to_list() == [1, 2, 3]  # values unchanged


@pytest.mark.unit
def test_optimize_leaves_string_and_bool_columns_untouched():
    from src.core.data import frames

    df = pl.DataFrame({"name": ["a", "b"], "flag": [True, False], "n": [1, 2]})

    out = frames.optimize(df)

    assert out["name"].dtype == pl.String
    assert out["flag"].dtype == pl.Boolean
    assert out["name"].to_list() == ["a", "b"]
    assert out["flag"].to_list() == [True, False]
    assert out["n"].to_list() == [1, 2]


@pytest.mark.unit
def test_describe_returns_queryresult_with_expected_stats():
    from src.core.data import frames

    out = frames.describe(pl.DataFrame({"qtd": [3, 5, 2]}))

    assert isinstance(out, QueryResult)
    assert out.columns[0] == "statistic"
    stats = {row[0]: row[1] for row in out.rows}
    assert stats["count"] == 3
    assert stats["min"] == 2
    assert stats["max"] == 5
    assert stats["mean"] == pytest.approx(10 / 3)
