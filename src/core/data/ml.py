"""Classic ML over tabular query results — the ``core/data`` <-> ``core/ml`` border.

Mirrors ``charts.py``: consumes the pandas frame from ``frames.to_pandas`` (the
Plano 0 boundary) and stays out of DuckDB/Polars. Gated by the same scikit-learn
extra as the rest of the classic-ML layer — callers check
``src.core.ml.deps.is_available()`` directly rather than duplicating the gate here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # static typing only — never imported at runtime
    import pandas as pd

# Anomaly score column: lower = more anomalous (IsolationForest's own convention).
# Negative values are outliers, non-negative are inliers — the same threshold
# ``IsolationForest.predict()`` uses internally.
ANOMALY_COLUMN = "_anomaly_score"

_RANDOM_STATE = 42


def detect_outliers(df: pd.DataFrame, *, contamination: float = 0.05) -> pd.DataFrame:
    """Flag anomalous rows via ``IsolationForest`` over the numeric columns of ``df``.

    Returns ``df`` with an added ``ANOMALY_COLUMN`` (lower = more anomalous;
    negative = outlier, matching ``IsolationForest.decision_function``), original
    row order preserved. Non-numeric columns are ignored in this first cut —
    categorical encoding (one-hot/ordinal) is a known follow-up, not implemented
    here without a real use case to calibrate it against. Missing numeric values
    are mean-imputed before scoring (``IsolationForest`` does not accept NaN) —
    a pragmatic default good enough to rank anomalies, not general-purpose
    imputation.

    Args:
        df: Tabular data (e.g. from ``frames.to_pandas``).
        contamination: Expected fraction of anomalous rows (IsolationForest's
            own parameter); only shifts where the negative/positive threshold
            falls, not the returned scores' relative order.

    Raises:
        ValueError: if ``df`` has no numeric columns to score.
    """
    from sklearn.ensemble import IsolationForest

    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] == 0:
        raise ValueError("Nenhuma coluna numérica para detectar anomalias.")

    # An all-NaN numeric column survives fillna(mean) as NaN (the mean of an
    # empty series is itself NaN) and then trips IsolationForest with a
    # cryptic sklearn error — drop it before imputing, same as a column that
    # was never numeric to begin with.
    numeric = numeric.dropna(axis=1, how="all")
    if numeric.shape[1] == 0:
        raise ValueError("Nenhuma coluna numérica para detectar anomalias.")

    filled = numeric.fillna(numeric.mean())
    model = IsolationForest(contamination=contamination, random_state=_RANDOM_STATE)
    model.fit(filled)
    scores = model.decision_function(filled)

    out = df.copy()
    out[ANOMALY_COLUMN] = scores
    return out
