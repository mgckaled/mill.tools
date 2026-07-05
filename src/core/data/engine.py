"""The single boundary with DuckDB: read files, register views, run queries.

Everything DuckDB-specific is funneled here (analogous to the RAG ``embedder``
being the only network touchpoint), so the rest of the data core stays trivially
testable. Each query runs in an ephemeral **in-memory** connection with nothing
writable attached — a malicious query cannot persist anything — and ``validate``
rejects non-SELECT statements before they ever reach this layer.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

from src.core.data.types import ColumnInfo, DataFile, QueryResult
from src.core.data.validate import ensure_select

if TYPE_CHECKING:  # pyarrow only annotates the Arrow seam; never imported at runtime
    import pyarrow as pa

# Extensions DuckDB reads natively (CSV/TSV via the CSV reader; JSON/Parquet via
# their own readers). XLSX needs the ``excel`` extension, loaded on demand.
_CSV_EXTS = {".csv", ".tsv", ".txt"}
_JSON_EXTS = {".json", ".ndjson", ".jsonl"}
_PARQUET_EXTS = {".parquet", ".pq"}
_XLSX_EXTS = {".xlsx"}

SUPPORTED_EXTS = _CSV_EXTS | _JSON_EXTS | _PARQUET_EXTS | _XLSX_EXTS

# DuckDB's CSV reader natively understands only these encodings; charset
# detection results are mapped onto them (everything exotic degrades to latin-1,
# which never raises on single-byte input).
_DUCKDB_ENCODINGS = {"utf-8", "utf-16", "latin-1"}

_IDENT_INVALID = re.compile(r"[^0-9a-z]+")


class DataEngineError(RuntimeError):
    """Raised when a file cannot be read or a query fails to execute."""


def _connect():
    """Open a fresh in-memory DuckDB connection (nothing writable attached)."""
    import duckdb

    return duckdb.connect(database=":memory:")


def _quote_str(value: str) -> str:
    """Quote a value as a SQL string literal (single quotes doubled)."""
    return "'" + value.replace("'", "''") + "'"


def view_name_for(path: Path, taken: set[str]) -> str:
    """Derive a unique, valid SQL identifier from a file stem.

    Lowercased, non-alphanumeric runs collapsed to ``_``; a leading digit is
    prefixed with ``t_`` (identifiers cannot start with a digit). Empty results
    fall back to ``data``. Collisions get a numeric suffix so two files named the
    same in different folders still register distinctly.
    """
    base = _IDENT_INVALID.sub("_", path.stem.lower()).strip("_")
    if not base:
        base = "data"
    if base[0].isdigit():
        base = f"t_{base}"
    name = base
    i = 2
    while name in taken:
        name = f"{base}_{i}"
        i += 1
    taken.add(name)
    return name


def detect_encoding(path: Path) -> str:
    """Return a DuckDB-compatible encoding for a CSV/TSV file.

    Uses ``charset-normalizer`` (a frequent Windows pain: cp1252 vs utf-8 vs
    BOM). The detected charset is mapped onto the three encodings DuckDB's CSV
    reader supports; anything else degrades to ``latin-1`` (lossless for
    single-byte data) so a mis-encoded file never aborts the read.
    """
    try:
        from charset_normalizer import from_path

        match = from_path(path).best()
        if match is None:
            return "utf-8"
        enc = (match.encoding or "utf-8").lower()
    except Exception as exc:  # detection is best-effort, never fatal
        logging.debug("[d] Encoding detection failed for %s: %s", path, exc)
        return "utf-8"

    if enc in _DUCKDB_ENCODINGS:
        return enc
    if enc.startswith("utf_16") or enc.startswith("utf-16"):
        return "utf-16"
    if enc in ("ascii", "utf_8", "utf8") or enc.startswith("utf_8"):
        return "utf-8"
    # cp1252 / windows-1252 / iso-8859-* and friends → latin-1
    return "latin-1"


def reader_expr(path: Path, *, sheet: str | None = None) -> str:
    """Return the DuckDB table-function expression that reads *path*.

    The expression is embedded in a ``FROM`` clause. CSV/TSV get an explicit
    ``encoding`` from :func:`detect_encoding`; the delimiter, header and types are
    left to DuckDB's sniffer. ``sheet`` selects a worksheet (XLSX only — ignored
    for the other formats, which have no concept of sheets).
    """
    suffix = path.suffix.lower()
    literal = _quote_str(str(path))
    if suffix in _CSV_EXTS:
        return f"read_csv({literal}, encoding={_quote_str(detect_encoding(path))})"
    if suffix in _JSON_EXTS:
        return f"read_json_auto({literal})"
    if suffix in _PARQUET_EXTS:
        return f"read_parquet({literal})"
    if suffix in _XLSX_EXTS:
        # all_varchar: read every cell as text so the file always loads. XLSX
        # type inference picks DOUBLE from numeric-looking cells and then chokes
        # on locale-formatted values (pt-BR "4.500,00" → not a US DOUBLE) or
        # mixed columns. Reading as text never fails; the user casts in SQL
        # (e.g. CAST(replace(replace(col,'.',''),',','.') AS DOUBLE)).
        sheet_arg = f", sheet = {_quote_str(sheet)}" if sheet else ""
        return f"read_xlsx({literal}, all_varchar = true{sheet_arg})"
    raise DataEngineError(f"Formato não suportado: {suffix or path.name}")


def xlsx_sheet_names(path: Path) -> list[str]:
    """Return the worksheet names of an XLSX file, or ``[]`` if not resolvable.

    An XLSX is a ZIP whose ``xl/workbook.xml`` lists the sheets — so the names
    are read with the stdlib (``zipfile`` + ``ElementTree``), no DuckDB round-trip
    and no new dependency. Best-effort: any failure (not an XLSX, corrupt zip,
    unexpected XML) returns ``[]`` so callers can fall back to the default sheet.
    """
    path = Path(path)
    if path.suffix.lower() not in _XLSX_EXTS:
        return []
    try:
        import xml.etree.ElementTree as ET
        import zipfile

        with zipfile.ZipFile(path) as zf:
            xml = zf.read("xl/workbook.xml")
        root = ET.fromstring(xml)
        # The <sheet> elements live under a namespaced <sheets>; match by local
        # tag name so we don't hard-code the spreadsheetml namespace URI.
        names = [
            el.get("name")
            for el in root.iter()
            if el.tag.rsplit("}", 1)[-1] == "sheet" and el.get("name")
        ]
        return [n for n in names if n]
    except Exception as exc:  # best-effort — never fatal
        logging.debug("[d] Could not read sheet names from %s: %s", path, exc)
        return []


def _ensure_excel(con) -> None:
    """Load the DuckDB ``excel`` extension (for XLSX read/write)."""
    try:
        con.execute("INSTALL excel; LOAD excel;")
    except Exception as exc:  # offline + not bundled → clear, actionable error
        raise DataEngineError(
            "A extensão 'excel' do DuckDB é necessária para XLSX e não pôde ser "
            f"carregada: {exc}"
        ) from exc


def _needs_excel(paths: Iterable[Path]) -> bool:
    """True if any path is an XLSX file (so the excel extension is required)."""
    return any(p.suffix.lower() in _XLSX_EXTS for p in paths)


def describe_file(
    path: Path, *, connect_fn: Callable = _connect
) -> tuple[int, list[ColumnInfo]]:
    """Return ``(row_count, columns)`` for a file. Used by the scanner.

    Schema comes from ``DESCRIBE`` (cheap: reads only the header/sniff sample);
    the row count is a ``count(*)`` (metadata-only for Parquet, a scan for CSV —
    acceptable for the file sizes this tool targets). ``connect_fn`` is
    injectable like every other engine entry point (``preview``/``run_query``/
    ``export_query``/``convert_file``) — this was the one boundary without the
    seam.
    """
    con = connect_fn()
    try:
        if _needs_excel([path]):
            _ensure_excel(con)
        expr = reader_expr(path)
        try:
            described = con.execute(f"DESCRIBE SELECT * FROM {expr}").fetchall()
            n_rows = con.execute(f"SELECT count(*) FROM {expr}").fetchone()[0]
        except Exception as exc:
            raise DataEngineError(f"Não foi possível ler {path.name}: {exc}") from exc
        # DESCRIBE rows: (column_name, column_type, null, key, default, extra)
        columns = [ColumnInfo(name=row[0], dtype=row[1]) for row in described]
        return int(n_rows), columns
    finally:
        con.close()


def register_views(con, files: list[DataFile]) -> None:
    """Register each DataFile as a DuckDB view under its ``view_name``."""
    if _needs_excel(f.path for f in files):
        _ensure_excel(con)
    for f in files:
        con.execute(
            f'CREATE OR REPLACE VIEW "{f.view_name}" AS SELECT * FROM {reader_expr(f.path)}'
        )


def _copy(con, select_sql: str, out_path: Path, options: str) -> Path:
    """Run ``COPY (select_sql) TO out_path options`` on *con*.

    Loads the excel extension first when the destination is an XLSX file. The
    output directory is created on demand (the data module has no central
    bootstrap, matching the rest of the project).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() in _XLSX_EXTS:
        _ensure_excel(con)
    con.execute(f"COPY ({select_sql}) TO {_quote_str(str(out_path))} {options}")
    return out_path


def export_query(
    files: list[DataFile],
    sql: str,
    out_path: Path,
    options: str,
    *,
    connect_fn: Callable = _connect,
) -> Path:
    """Validate *sql*, register *files* and ``COPY`` the result to *out_path*."""
    ensure_select(sql)
    con = connect_fn()
    try:
        register_views(con, files)
        return _copy(con, sql, out_path, options)
    except Exception as exc:
        if isinstance(exc, DataEngineError):
            raise
        raise DataEngineError(f"Erro ao exportar a consulta: {exc}") from exc
    finally:
        con.close()


def convert_file(
    src_path: Path,
    out_path: Path,
    options: str,
    *,
    connect_fn: Callable = _connect,
) -> Path:
    """``COPY`` a whole source file to *out_path* in another format."""
    src_path = Path(src_path)
    con = connect_fn()
    try:
        if _needs_excel([src_path]):
            _ensure_excel(con)
        select = f"SELECT * FROM {reader_expr(src_path)}"
        return _copy(con, select, out_path, options)
    except Exception as exc:
        if isinstance(exc, DataEngineError):
            raise
        raise DataEngineError(f"Erro ao converter {src_path.name}: {exc}") from exc
    finally:
        con.close()


def preview(
    path: Path,
    *,
    limit: int = 100,
    offset: int = 0,
    sheet: str | None = None,
    connect_fn: Callable = _connect,
) -> QueryResult:
    """Read a window of rows straight from *path* (no view registration needed).

    Powers the source-preview modal: ``SELECT * FROM <reader> LIMIT ? OFFSET ?``.
    Cheap for CSV/TSV/Parquet (streamed); for XLSX a whole sheet loads but the
    UI always passes a small ``limit``. ``sheet`` selects an XLSX worksheet.

    Raises:
        DataEngineError: if the file cannot be read.
    """
    path = Path(path)
    con = connect_fn()
    try:
        if _needs_excel([path]):
            _ensure_excel(con)
        expr = reader_expr(path, sheet=sheet)
        sql = f"SELECT * FROM {expr} LIMIT {int(limit)} OFFSET {int(offset)}"
        start = time.perf_counter()
        try:
            cur = con.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
        except Exception as exc:
            raise DataEngineError(f"Não foi possível ler {path.name}: {exc}") from exc
        return QueryResult(
            columns=columns,
            rows=[tuple(r) for r in rows],
            elapsed=time.perf_counter() - start,
            n_rows=len(rows),
        )
    finally:
        con.close()


def run_query(
    files: list[DataFile],
    sql: str,
    *,
    connect_fn: Callable = _connect,
    max_rows: int | None = None,
) -> QueryResult:
    """Validate, register the views, and execute *sql* over *files*.

    The connection factory is injectable (default: an ephemeral in-memory
    connection) to mirror the RAG embedder's testability seam. ``max_rows``, when
    set, caps the rows materialized into the result (the preview never needs the
    whole table); the reported ``n_rows`` reflects the materialized rows.

    Raises:
        UnsafeQueryError: if *sql* is not a single read-only SELECT.
        DataEngineError: if a file cannot be read or the query fails.
    """
    ensure_select(sql)
    con = connect_fn()
    try:
        register_views(con, files)
        start = time.perf_counter()
        try:
            cur = con.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
        except Exception as exc:
            raise DataEngineError(f"Erro ao executar a consulta: {exc}") from exc
        elapsed = time.perf_counter() - start
        return QueryResult(
            columns=columns,
            rows=[tuple(r) for r in rows],
            elapsed=elapsed,
            n_rows=len(rows),
        )
    finally:
        con.close()


def run_query_arrow(
    files: list[DataFile],
    sql: str,
    *,
    connect_fn: Callable = _connect,
) -> "pa.Table":
    """Validate, register the views, execute and return a ``pyarrow.Table``.

    Zero-copy seam to Polars (``frames.from_arrow``): DuckDB emits Arrow record
    batches the DataFrame layer consumes by reference, skipping the per-row
    Python tuple materialization that :func:`run_query` does. pyarrow is required
    only here (via DuckDB's ``to_arrow_table``); callers gate on
    ``frames.is_available()``, so the engine itself never imports it.

    Raises:
        UnsafeQueryError: if *sql* is not a single read-only SELECT.
        DataEngineError: if a file cannot be read or the query fails.
    """
    ensure_select(sql)
    con = connect_fn()
    try:
        register_views(con, files)
        try:
            return con.execute(sql).to_arrow_table()
        except Exception as exc:
            raise DataEngineError(f"Erro ao executar a consulta: {exc}") from exc
    finally:
        con.close()
