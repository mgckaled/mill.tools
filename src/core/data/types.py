"""Typed models for the structured-data module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    """One column of a data file: its name and DuckDB-inferred type."""

    name: str
    dtype: str  # DuckDB logical type, e.g. "VARCHAR", "BIGINT", "DOUBLE"


@dataclass(frozen=True, slots=True)
class DataFile:
    """A scanned data file: the table the IA and DuckDB will see.

    ``view_name`` is the SQL identifier the engine registers the file under, so
    the NL→SQL layer and the user's hand-written SQL reference the same name.
    Only the schema (``columns``) ever leaves the machine when the IA is Gemini —
    never the rows.
    """

    path: Path
    view_name: str
    n_rows: int
    columns: list[ColumnInfo] = field(default_factory=list)

    @property
    def n_cols(self) -> int:
        """Number of columns."""
        return len(self.columns)


@dataclass(frozen=True, slots=True)
class QueryResult:
    """The outcome of running a SELECT: column names, rows, timing and count."""

    columns: list[str]
    rows: list[tuple]
    elapsed: float  # seconds spent executing the query
    n_rows: int  # number of rows returned (== len(rows))
