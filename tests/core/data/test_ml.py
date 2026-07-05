"""Tests for src/core/data/ml.py — IsolationForest outlier detection.

pandas/scikit-learn live behind the optional ``[analysis]``/``[ml]`` extras;
IsolationForest is CPU-only and fast on tiny frames, so this stays ``unit``.
"""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("sklearn")

from src.core.data import ml  # noqa: E402


@pytest.mark.unit
def test_detect_outliers_flags_the_anomalous_row():
    df = pd.DataFrame(
        {
            "valor": [10, 11, 9, 10, 12, 10000],  # last row is wildly out of range
            "categoria": ["a", "a", "b", "b", "a", "b"],
        }
    )
    result = ml.detect_outliers(df, contamination=0.2)

    assert ml.ANOMALY_COLUMN in result.columns
    worst = result[ml.ANOMALY_COLUMN].idxmin()
    assert worst == 5  # the 10000 row scores as the most anomalous


@pytest.mark.unit
def test_detect_outliers_preserves_row_order_and_other_columns():
    df = pd.DataFrame({"valor": [1, 2, 3, 4, 5], "nome": list("abcde")})
    result = ml.detect_outliers(df)

    assert list(result["nome"]) == list("abcde")
    assert list(result.index) == list(df.index)


@pytest.mark.unit
def test_detect_outliers_ignores_non_numeric_columns():
    df = pd.DataFrame({"valor": [1, 2, 3, 4], "texto": ["x", "y", "z", "w"]})
    result = ml.detect_outliers(df)

    assert "texto" in result.columns  # untouched, just not scored on


@pytest.mark.unit
def test_detect_outliers_imputes_missing_numeric_values():
    df = pd.DataFrame({"valor": [1.0, 2.0, None, 4.0, 5.0]})
    result = ml.detect_outliers(df)  # must not raise on NaN

    assert len(result) == 5


@pytest.mark.unit
def test_detect_outliers_raises_without_numeric_columns():
    df = pd.DataFrame({"texto": ["a", "b", "c"]})
    with pytest.raises(ValueError):
        ml.detect_outliers(df)


@pytest.mark.unit
def test_detect_outliers_drops_all_nan_numeric_column():
    """An all-NaN numeric column used to survive fillna(mean) as NaN (mean of
    an empty series is NaN) and crash IsolationForest with a cryptic sklearn
    error instead of the module's own, clear ValueError."""
    df = pd.DataFrame(
        {
            "valor": [1, 2, 3, 4, 100],
            "vazio": pd.Series([float("nan")] * 5, dtype="float64"),
        }
    )
    result = ml.detect_outliers(df)

    assert ml.ANOMALY_COLUMN in result.columns
    assert "vazio" in result.columns  # untouched, just not scored on


@pytest.mark.unit
def test_detect_outliers_raises_when_all_numeric_columns_are_all_nan():
    df = pd.DataFrame(
        {
            "vazio": pd.Series([float("nan")] * 3, dtype="float64"),
            "texto": ["a", "b", "c"],
        }
    )
    with pytest.raises(ValueError):
        ml.detect_outliers(df)
