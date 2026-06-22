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


def profile_file(path: Path, out_dir: Path) -> Path:
    """Profile *path* and write the report to ``out_dir/<stem>_profile.txt``.

    Returns the path of the written report.
    """
    path = Path(path)
    file = scan_file(path)
    summary = run_query([file], f'SUMMARIZE "{file.view_name}"')
    text = format_profile(file, summary)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{path.stem}_profile.txt"
    out.write_text(text, encoding="utf-8")
    return out
