"""Format conversion for data files (CSV/TSV/JSON/Parquet/XLSX) via ``COPY``.

Thin orchestration over the engine: this module owns the format catalog
(extension + ``COPY`` options) and the output-path building; the actual DuckDB
``COPY`` lives in ``engine`` (the single DuckDB boundary). XLSX is isolated here
so a missing ``excel`` extension degrades with a clear error rather than a crash.
"""

from __future__ import annotations

from pathlib import Path

from src.core.data import engine
from src.core.data.types import DataFile

# fmt -> (extension, COPY options). JSON is written as a top-level array of
# objects (``ARRAY true``) so the file round-trips through read_json_auto and is
# friendly to other tools; TSV reuses the CSV writer with a tab delimiter.
_FORMATS: dict[str, tuple[str, str]] = {
    "csv": (".csv", "(FORMAT csv, HEADER true)"),
    "tsv": (".tsv", "(FORMAT csv, HEADER true, DELIMITER '\t')"),
    "json": (".json", "(FORMAT json, ARRAY true)"),
    "parquet": (".parquet", "(FORMAT parquet)"),
    "xlsx": (".xlsx", "(FORMAT xlsx, HEADER true)"),
}

SUPPORTED_FORMATS = tuple(_FORMATS)


class ConvertError(ValueError):
    """Raised for an unknown output format."""


def _resolve(fmt: str) -> tuple[str, str]:
    """Return ``(extension, copy_options)`` for *fmt* or raise ConvertError."""
    try:
        return _FORMATS[fmt.lower()]
    except KeyError:
        raise ConvertError(
            f"Formato de saída desconhecido: {fmt!r}. "
            f"Use um de: {', '.join(SUPPORTED_FORMATS)}."
        ) from None


def out_path_for(stem: str, out_dir: Path, fmt: str) -> Path:
    """Build the destination path for *stem* under *out_dir* in *fmt*."""
    ext, _ = _resolve(fmt)
    return Path(out_dir) / f"{stem}{ext}"


def convert_file(src_path: Path, out_dir: Path, fmt: str) -> Path:
    """Convert a whole file to *fmt*, writing to *out_dir*. Returns the new path."""
    src_path = Path(src_path)
    ext, options = _resolve(fmt)
    out_path = Path(out_dir) / f"{src_path.stem}{ext}"
    return engine.convert_file(src_path, out_path, options)


def _quote_ident(name: str) -> str:
    """Quote a SQL identifier (double quotes doubled)."""
    return '"' + name.replace('"', '""') + '"'


def rename_sql(base_sql: str, columns: list[str], renames: dict[str, str]) -> str:
    """Wrap *base_sql* so selected columns are renamed in the output.

    Pure and testable: returns *base_sql* unchanged when there is nothing to
    rename; otherwise wraps it as ``SELECT "c" AS "new", ... FROM (base) _q``.
    Only entries whose new name is non-empty and actually differs are applied,
    and only for columns that exist in *columns*.
    """
    effective = {
        old: new
        for old, new in renames.items()
        if new and new != old and old in columns
    }
    if not effective:
        return base_sql
    select_list = ", ".join(
        f"{_quote_ident(c)} AS {_quote_ident(effective.get(c, c))}" for c in columns
    )
    return f"SELECT {select_list} FROM ({base_sql}) AS _q"


def save_query(
    files: list[DataFile],
    sql: str,
    out_dir: Path,
    fmt: str,
    stem: str,
) -> Path:
    """Run *sql* over *files* and save the result to *out_dir* as *stem* in *fmt*."""
    ext, options = _resolve(fmt)
    out_path = Path(out_dir) / f"{stem}{ext}"
    return engine.export_query(files, sql, out_path, options)
