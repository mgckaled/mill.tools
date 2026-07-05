"""The "data card": a textual description of a data file, indexable by the RAG.

The RAG indexes the *card* (what the file is about), never the raw rows —
embedding rows would bloat the index and is weak with numbers (numeric filtering
stays in DuckDB). The card is format-agnostic: by the time it is built, the
scanner/engine have already abstracted CSV/TSV/JSON/Parquet/XLSX.

``build_data_card`` is pure (schema + profile + sample, plus an optional cached
assessment). ``card_for_path`` is the thin orchestrator the indexer calls — it
scans, profiles, samples and folds in a cached IA assessment if one exists (it
never triggers a new LLM call during indexing).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.data.types import DataFile, QueryResult

# Sample rows pulled into the card. Small — a few rows are enough to show shape
# and spot obvious issues; the profile already carries the statistics.
SAMPLE_ROWS = 10

_FORMAT_LABELS = {
    ".csv": "CSV",
    ".tsv": "TSV",
    ".txt": "CSV",
    ".json": "JSON",
    ".ndjson": "NDJSON",
    ".jsonl": "NDJSON",
    ".parquet": "Parquet",
    ".pq": "Parquet",
    ".xlsx": "XLSX",
}


def format_label(path: Path) -> str:
    """Return a human format label for a data file (by extension)."""
    return _FORMAT_LABELS.get(Path(path).suffix.lower(), "?")


def sample_to_text(sample: QueryResult, *, max_rows: int = SAMPLE_ROWS) -> str:
    """Render a QueryResult as a compact tab-separated sample block."""
    if not sample.columns:
        return "(sem linhas)"
    lines = ["\t".join(sample.columns)]
    for row in sample.rows[:max_rows]:
        lines.append("\t".join("" if v is None else str(v) for v in row))
    return "\n".join(lines)


def build_data_card(
    file: DataFile,
    profile_text: str,
    sample: QueryResult,
    assessment: str | None = None,
) -> str:
    """Render the indexable data card for *file*.

    Deterministic: schema + profile + sample. The IA assessment is appended only
    when one is supplied (cached) — the card never blocks on an LLM call.
    """
    schema = " · ".join(f"{c.name}({c.dtype})" for c in file.columns)
    lines = [
        f"ARQUIVO: {file.path.name}  ·  formato: {format_label(file.path)}  ·  "
        f"{file.n_rows} linhas × {file.n_cols} colunas",
        "",
        f"SCHEMA: {schema}",
        "",
        "PERFIL (SUMMARIZE):",
        profile_text.strip(),
        "",
        f"AMOSTRA ({min(SAMPLE_ROWS, file.n_rows)} linhas):",
        sample_to_text(sample),
    ]
    if assessment and assessment.strip():
        lines += ["", "AVALIAÇÃO DA IA:", assessment.strip()]
    return "\n".join(lines).rstrip() + "\n"


def card_for_path(path: Path) -> str:
    """Build the data card for *path* (scan + profile + sample + cached assessment).

    Used as the indexer's text provider for ``kind="data"`` items. Any cached IA
    assessment (from the preview modal) is reused; indexing never calls the LLM.
    """
    from src.core.data import assess
    from src.core.data.engine import preview
    from src.core.data.profile import profile_text
    from src.core.data.scanner import scan_file

    path = Path(path)
    file = scan_file(path)
    prof = profile_text(file)  # reuse the scan above instead of a 2nd DESCRIBE/count(*)
    sample = preview(path, limit=SAMPLE_ROWS)
    cached = None
    try:
        cached = assess.load_cached_assessment(path)
    except Exception as exc:  # cache is best-effort; never block indexing
        logging.debug("[d] assessment cache read failed for %s: %s", path, exc)
    return build_data_card(file, prof, sample, assessment=cached)
