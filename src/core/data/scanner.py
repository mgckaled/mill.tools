"""Scan data files into typed ``DataFile`` records (chips + IA schema).

A scan is cheap by design: ``DESCRIBE`` reads only the sniff sample and the row
count is a single aggregate. The resulting ``DataFile`` feeds both the GUI source
chips (row/column counts, column names) and the schema string handed to the
NL→SQL layer.
"""

from __future__ import annotations

from pathlib import Path

from src.core.data.engine import SUPPORTED_EXTS, describe_file, view_name_for
from src.core.data.types import DataFile


def is_supported(path: Path) -> bool:
    """True if the file extension is a format the engine can read."""
    return path.suffix.lower() in SUPPORTED_EXTS


def scan_file(path: Path, taken: set[str] | None = None) -> DataFile:
    """Scan one file into a ``DataFile`` (view name, row count, columns).

    ``taken`` accumulates already-used view names so a batch of files gets
    distinct identifiers; pass the same set across calls (see :func:`scan_files`).
    """
    path = Path(path)
    taken = taken if taken is not None else set()
    view_name = view_name_for(path, taken)
    n_rows, columns = describe_file(path)
    return DataFile(path=path, view_name=view_name, n_rows=n_rows, columns=columns)


def scan_files(paths: list[Path]) -> list[DataFile]:
    """Scan several files, guaranteeing distinct view names across the batch."""
    taken: set[str] = set()
    return [scan_file(Path(p), taken) for p in paths]


def schema_text(files: list[DataFile]) -> str:
    """Render the tables/columns as a compact schema for the NL→SQL prompt.

    Only names and types are included — never a data row — so opting into Gemini
    leaks the schema at most, never the table contents.
    """
    lines: list[str] = []
    for f in files:
        cols = ", ".join(f"{c.name} {c.dtype}" for c in f.columns)
        lines.append(f"{f.view_name} ({f.n_rows} linhas): {cols}")
    return "\n".join(lines)
