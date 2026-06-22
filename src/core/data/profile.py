"""Textual profile of a data file: rows, columns, nulls, cardinality, stats.

Built on DuckDB's ``SUMMARIZE`` (read-only) and rendered as plain text so the
report drops straight into ``output/data/`` and is indexable by the RAG module
like any other ``.txt`` the user produces.
"""

from __future__ import annotations

from pathlib import Path

from src.core.data.engine import run_query
from src.core.data.scanner import scan_file
from src.core.data.types import DataFile, QueryResult

# Above this many rows the SUMMARIZE runs over a reservoir sample instead of a
# full scan — the profile stays a quick descriptive sketch (the exact min/max of
# a huge file is not worth a full pass when indexing the data card).
SAMPLE_THRESHOLD = 200_000
SAMPLE_ROWS = 100_000


def summarize_sql(
    view_name: str,
    n_rows: int,
    *,
    threshold: int = SAMPLE_THRESHOLD,
    sample_rows: int = SAMPLE_ROWS,
) -> str:
    """Build the SUMMARIZE query for a view, sampling when the file is large.

    Pure and testable: small files get ``SUMMARIZE "view"`` (whole table); files
    past *threshold* get ``SUMMARIZE SELECT * FROM "view" USING SAMPLE n ROWS`` so
    profiling never scans an enormous file end-to-end.
    """
    if n_rows > threshold:
        return f'SUMMARIZE SELECT * FROM "{view_name}" USING SAMPLE {int(sample_rows)} ROWS'
    return f'SUMMARIZE "{view_name}"'


def _fmt_cell(value) -> str:
    """Render a SUMMARIZE cell for the report (``-`` for NULL/empty).

    ``SUMMARIZE`` returns ``avg``/``std``/``min``/``max`` as strings, so long
    decimals are rounded to 4 significant figures for readability while genuine
    text values (e.g. ``"banana"``) pass through untouched.
    """
    if value is None or value == "":
        return "-"
    if isinstance(value, (int, float)):
        return f"{value:.4g}" if isinstance(value, float) else str(value)
    text = str(value)
    try:
        return f"{float(text):.4g}"
    except ValueError:
        return text


def format_profile(file: DataFile, summary: QueryResult) -> str:
    """Render a plain-text profile from a DataFile and its SUMMARIZE result.

    Pure and unit-testable: the heavy lifting (the SUMMARIZE) happens in
    :func:`profile_file`; this only formats already-computed numbers.
    """
    idx = {name: i for i, name in enumerate(summary.columns)}

    def col(row, name):
        i = idx.get(name)
        return row[i] if i is not None else None

    lines = [
        f"# Perfil dos dados — {file.path.name}",
        "",
        f"- Linhas: {file.n_rows}",
        f"- Colunas: {file.n_cols}",
        "",
        "## Colunas",
        "",
    ]
    for row in summary.rows:
        name = col(row, "column_name")
        dtype = col(row, "column_type")
        lines.append(f"### {name}  ({dtype})")
        stats = [
            ("nulos", "null_percentage", "%"),
            ("distintos", "approx_unique", ""),
            ("mín", "min", ""),
            ("máx", "max", ""),
            ("média", "avg", ""),
            ("desvio", "std", ""),
        ]
        for label, key, unit in stats:
            value = col(row, key)
            if value is None:
                continue
            lines.append(f"- {label}: {_fmt_cell(value)}{unit}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def profile_text(path: Path) -> str:
    """Profile *path* and return the report as text (no file written).

    Shared by :func:`profile_file` (writes it) and the data card builder (embeds
    it). The SUMMARIZE is sampled for large files via :func:`summarize_sql`.
    """
    path = Path(path)
    file = scan_file(path)
    summary = run_query([file], summarize_sql(file.view_name, file.n_rows))
    return format_profile(file, summary)


def profile_file(path: Path, out_dir: Path) -> Path:
    """Profile *path* and write the report to ``out_dir/<stem>_profile.txt``.

    Returns the path of the written report.
    """
    path = Path(path)
    text = profile_text(path)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{path.stem}_profile.txt"
    out.write_text(text, encoding="utf-8")
    return out
