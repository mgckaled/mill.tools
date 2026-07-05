"""The single DataFrame boundary for the data core: ``QueryResult`` <-> Polars.

Mirrors ``engine.py`` (the single DuckDB boundary): only this module imports
Polars/pandas/pyarrow, so the rest of the data core never sees a DataFrame and
the optional ``[analysis]`` extra stays isolated behind lazy, function-local
imports. Polars is the in-core default; pandas appears only at the ML/plot edge
via :func:`to_pandas`. Nothing here touches DuckDB (that is the engine) or Flet
(that is the GUI) — the GUI only ever speaks ``QueryResult``.

The extra is optional, like ``[ai-image]``/``[ocr]``: :func:`is_available` gates
the callers (Planos 1/5/2) so a missing extra degrades gracefully instead of
failing mid-flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.data.types import QueryResult

if TYPE_CHECKING:  # static typing only — never imported at runtime
    import pandas as pd
    import polars as pl
    import pyarrow as pa

SETUP_HINT = (
    "Camada de análise indisponível. Instale o extra opcional com "
    "`uv sync --extra analysis` (polars, pandas, pyarrow)."
)


def is_available() -> bool:
    """Return True if the ``[analysis]`` extra (Polars + PyArrow) is importable.

    Gate for the DataFrame layer, mirroring ``embedder.is_available``: callers
    show ``SETUP_HINT`` instead of failing when the extra is absent. Never raises.

    Does not probe pandas even though :func:`to_pandas` needs it: the
    ``[analysis]`` extra in ``pyproject.toml`` always installs polars, pandas
    and pyarrow together, so a missing pandas here would mean a broken/partial
    install rather than a real "extra not selected" state — not worth a 3rd
    import just to special-case an environment this project does not support.
    """
    try:
        import polars  # noqa: F401
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return True


def to_polars(result: QueryResult) -> pl.DataFrame:
    """Build a Polars DataFrame from a ``QueryResult`` (universal row path).

    Works over what the engine already produces today (``columns`` + ``rows``),
    so it needs no Arrow handoff. Nulls (``None``) are preserved as Polars nulls.
    """
    import polars as pl

    return pl.DataFrame(result.rows, schema=result.columns, orient="row")


def from_arrow(table: pa.Table) -> pl.DataFrame:
    """Wrap a ``pyarrow.Table`` in a Polars DataFrame (zero-copy).

    Paired with ``engine.run_query_arrow``: both Polars and DuckDB use the Arrow
    columnar format, so the table is consumed by reference — no serialization or
    per-row Python tuples. Use this path when transforming large results.
    """
    import polars as pl

    return pl.from_arrow(table)


def to_result(df: pl.DataFrame, *, limit: int | None = None) -> QueryResult:
    """Materialize a Polars DataFrame back into the GUI contract ``QueryResult``.

    The single point that hands a DataFrame's content back to the GUI/event-bus
    world. ``elapsed`` is 0.0 because this is a pure conversion (no query ran);
    ``limit`` caps the materialized rows and ``n_rows`` reflects that cap.
    """
    if limit is not None:
        df = df.head(limit)
    rows = df.rows()
    return QueryResult(
        columns=list(df.columns),
        rows=rows,
        elapsed=0.0,
        n_rows=len(rows),
    )


def to_pandas(df: pl.DataFrame) -> pd.DataFrame:
    """Convert to pandas at the ML/plot edge (the single pandas touchpoint).

    pandas is never imported at module top — Polars pulls it in lazily here — so
    the data core stays pandas-free until a consumer (Planos 1/5) asks for it.
    """
    return df.to_pandas()


def optimize(df: pl.DataFrame) -> pl.DataFrame:
    """Shrink numeric columns to their minimal dtype, leaving values unchanged.

    A type-neutral best practice (an ``i8`` is still an integer downstream), so
    it never reshapes the types that pandas/scikit-learn/matplotlib consume.
    String and boolean columns pass through untouched: categorical encoding is a
    point-of-use decision (e.g. ML in Plano 5), deliberately not baked into this
    shared boundary. Uses ``Series.shrink_dtype`` (not the deprecated
    ``Expr.shrink_dtype``) for robustness across ``polars>=1.0``.
    """
    import polars as pl

    columns = [
        s.shrink_dtype() if s.dtype.is_numeric() else s
        for s in (df[name] for name in df.columns)
    ]
    return pl.DataFrame(columns)


def describe(df: pl.DataFrame) -> QueryResult:
    """Quick summary statistics as a ``QueryResult`` (reusable by profiles/panels).

    Delegates to Polars' ``describe`` (count, null_count, mean, std, min,
    quantiles, max) and returns it already in the GUI contract.
    """
    return to_result(df.describe())


# Future seam (not implemented — "divide-se ao tocar"): a lazy/streaming path
#   def scan(path) -> pl.LazyFrame: ...
# for Polars-native transforms over large files. DuckDB already reads out-of-core,
# so this only lands when a concrete plan needs it.
