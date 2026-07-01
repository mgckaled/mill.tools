"""Data (PR9, DuckDB) step adapters for the recipe registry."""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import KIND_DATA, KIND_TEXT, StepContext, StepSpec


def _data_query(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """N data files + a query → one result file. Wraps the DuckDB data core.

    Multi-input like document.merge: it consumes the *whole* input list (every
    data file the chain carries) and registers each as a view, so a query can
    join across them. The query comes from params: either ``sql`` (raw) or
    ``question`` (Portuguese, translated by the IA, which sees only the schema).
    Produces a saved result file; declared as KIND_TEXT so it can flow into the
    text-consuming steps (ai.answer/analyze) — see the registry note.
    """
    from src.core.data.convert import save_query
    from src.core.data.scanner import scan_files, schema_text
    from src.utils import DATA_DIR

    files = scan_files([Path(p) for p in inputs])
    sql = params.get("sql")
    if not sql:
        question = params.get("question")
        if not question:
            raise ValueError("data.query requer 'sql' ou 'question' nos params")
        from src.core.data.nl2sql import DEFAULT_MODEL, to_sql

        sql, _explanation = to_sql(
            schema_text(files), question, model_name=params.get("model", DEFAULT_MODEL)
        )
    out = save_query(
        files,
        sql,
        DATA_DIR,
        params.get("fmt", "csv"),
        params.get("stem", "consulta"),
    )
    return [out]


def _data_convert(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """data file → converted data file. Wraps convert_file."""
    from src.core.data.convert import convert_file
    from src.utils import DATA_DIR

    out = convert_file(Path(inputs[0]), DATA_DIR, params.get("fmt", "csv"))
    return [out]


def _data_profile(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """data file → textual profile report .txt. Wraps profile_file."""
    from src.core.data.profile import profile_file
    from src.utils import DATA_DIR

    out = profile_file(Path(inputs[0]), DATA_DIR)
    return [out]


def _data_outliers(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """data file → text report of anomalous rows via IsolationForest.

    Reads the whole file into a pandas frame (Plano 0 boundary, same path as
    ``_data_profile``) and writes a plain-text preview of the flagged rows.
    """
    from src.core.data import frames
    from src.core.data.engine import run_query_arrow
    from src.core.data.ml import ANOMALY_COLUMN, detect_outliers
    from src.core.data.scanner import scan_files
    from src.core.ml import deps
    from src.utils import DATA_DIR

    if not deps.is_available():
        raise RuntimeError(f"scikit-learn indisponível. {deps.SETUP_HINT}")

    (file,) = scan_files([Path(inputs[0])])
    pl_df = frames.from_arrow(
        run_query_arrow([file], f'SELECT * FROM "{file.view_name}"')
    )
    result = detect_outliers(
        frames.to_pandas(pl_df), contamination=params.get("contamination", 0.05)
    )
    flagged = result[result[ANOMALY_COLUMN] < 0].sort_values(ANOMALY_COLUMN)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{Path(inputs[0]).stem}_outliers.txt"
    header = f"{len(flagged)} de {len(result)} linha(s) sinalizada(s) como atípica(s)."
    out.write_text(f"{header}\n\n{flagged.to_string(index=False)}", encoding="utf-8")
    return [out]


DATA_STEPS: dict[str, StepSpec] = {
    # data.query is multi-input (consumes the whole data-file list, like
    # document.merge) and is declared as producing KIND_TEXT so the result can
    # feed text-consuming steps (closes the chain data.query → ai.answer).
    "data.query": StepSpec(
        _data_query, frozenset({KIND_DATA}), KIND_TEXT, "Consultar dados"
    ),
    "data.convert": StepSpec(
        _data_convert, frozenset({KIND_DATA}), KIND_DATA, "Converter dados"
    ),
    "data.profile": StepSpec(
        _data_profile, frozenset({KIND_DATA}), KIND_TEXT, "Perfilar dados"
    ),
    "data.outliers": StepSpec(
        _data_outliers, frozenset({KIND_DATA}), KIND_TEXT, "Detectar anomalias"
    ),
}
