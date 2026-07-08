"""CLI subcommand for the structured-data module (DuckDB, query-first).

Like ``ai``/``library``, this subcommand reuses the pure core directly rather
than a ``run_*_pipeline`` worker: data operations are synchronous and emit no
progress, so there is nothing for a ``CLIEventBus`` to render. The query path
mirrors the GUI's review card by printing the SQL (and the IA's explanation)
before the result table. ``sys.stdout`` is reconfigured to UTF-8 because data
values routinely contain characters outside cp1252 (the Windows console default).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.core.data import charts, convert, nl2sql, profile, scanner
from src.core.data.engine import run_query
from src.utils import DATA_DIR, setup_logging


def add_data_parser(subparsers) -> None:
    """Register the ``data`` subcommand and its query/convert/profile ops."""
    data_p = subparsers.add_parser(
        "data",
        help="Manipulação de dados estruturados (CSV/JSON/Parquet/XLSX via DuckDB)",
        description="Consulta, converte e perfila arquivos de dados. A pergunta em "
        "português é traduzida para SQL pela IA; o conteúdo das tabelas nunca sai "
        "da máquina.",
    )
    data_sub = data_p.add_subparsers(dest="data_op", required=True)

    # query -----------------------------------------------------------------
    q = data_sub.add_parser(
        "query", help="Consulta um ou mais arquivos (pergunta em PT ou SQL na mão)"
    )
    q.add_argument(
        "files", nargs="+", help="Arquivos de dados (CSV/TSV/JSON/Parquet/XLSX)"
    )
    q.add_argument(
        "question", help="Pergunta em português (ou a consulta SQL com --sql)"
    )
    q.add_argument(
        "--sql",
        action="store_true",
        help="Trata 'question' como SQL literal e pula a tradução pela IA",
    )
    q.add_argument(
        "--model",
        default=nl2sql.DEFAULT_MODEL,
        help=f"Modelo da tradução PT→SQL (default: {nl2sql.DEFAULT_MODEL})",
    )
    q.add_argument(
        "--out",
        choices=convert.SUPPORTED_FORMATS,
        help="Salva o resultado em output/data/ neste formato",
    )
    q.add_argument(
        "--name", help="Nome do arquivo de saída (sem extensão; default: 'consulta')"
    )
    q.add_argument(
        "--limit", type=int, default=50, help="Linhas exibidas na prévia (default: 50)"
    )
    q.add_argument("--verbose", action="store_true", help="Logging DEBUG")

    # convert ---------------------------------------------------------------
    c = data_sub.add_parser("convert", help="Converte um arquivo para outro formato")
    c.add_argument("file", help="Arquivo de dados de entrada")
    c.add_argument(
        "--out",
        choices=convert.SUPPORTED_FORMATS,
        default="csv",
        help="Formato de saída (default: csv)",
    )
    c.add_argument("--verbose", action="store_true", help="Logging DEBUG")

    # profile ---------------------------------------------------------------
    p = data_sub.add_parser("profile", help="Gera um relatório textual do arquivo")
    p.add_argument("file", help="Arquivo de dados de entrada")
    p.add_argument("--verbose", action="store_true", help="Logging DEBUG")

    # assess ----------------------------------------------------------------
    a = data_sub.add_parser(
        "assess", help="Avaliação de qualidade pela IA (esquema + perfil + amostra)"
    )
    a.add_argument("file", help="Arquivo de dados de entrada")
    a.add_argument(
        "--model",
        default=nl2sql.DEFAULT_MODEL,
        help=f"Modelo da avaliação (default: {nl2sql.DEFAULT_MODEL})",
    )
    a.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignora a avaliação cacheada e força uma nova",
    )
    a.add_argument("--verbose", action="store_true", help="Logging DEBUG")

    # plot ------------------------------------------------------------------
    pl = data_sub.add_parser(
        "plot", help="Gera um gráfico (PNG) a partir de uma consulta"
    )
    pl.add_argument(
        "files", nargs="+", help="Arquivos de dados (CSV/TSV/JSON/Parquet/XLSX)"
    )
    pl.add_argument(
        "question", help="Pergunta em português (ou a consulta SQL com --sql)"
    )
    pl.add_argument(
        "--sql",
        action="store_true",
        help="Trata 'question' como SQL literal e pula a tradução pela IA",
    )
    pl.add_argument(
        "--model",
        default=nl2sql.DEFAULT_MODEL,
        help=f"Modelo da tradução PT→SQL (default: {nl2sql.DEFAULT_MODEL})",
    )
    pl.add_argument(
        "--kind",
        choices=charts.CHART_KINDS,
        help="Tipo do gráfico (default: sugerido pelo esquema do resultado)",
    )
    pl.add_argument("--x", help="Coluna do eixo X (default: sugerida)")
    pl.add_argument("--y", help="Coluna do eixo Y (default: sugerida)")
    pl.add_argument("--out", help="Nome do arquivo PNG de saída (default: grafico.png)")
    pl.add_argument("--verbose", action="store_true", help="Logging DEBUG")

    # outliers ----------------------------------------------------------------
    o = data_sub.add_parser(
        "outliers", help="Detecta linhas estatisticamente anômalas (IsolationForest)"
    )
    o.add_argument("file", help="Arquivo de dados de entrada")
    o.add_argument(
        "--contamination",
        type=float,
        default=0.05,
        help="Fração esperada de linhas atípicas (default: 0.05)",
    )
    o.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Linhas atípicas exibidas na prévia (default: 20)",
    )
    o.add_argument("--verbose", action="store_true", help="Logging DEBUG")

    data_p.set_defaults(func=run_data_cli)


def _print_table(columns: list[str], rows: list[tuple]) -> None:
    """Print a result set as a simple fixed-width table."""
    if not columns:
        print("(sem colunas)")
        return
    cells = [columns] + [[_cell(v) for v in r] for r in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(columns))]
    sep = "  ".join("-" * w for w in widths)
    for i, row in enumerate(cells):
        print("  ".join(v.ljust(widths[j]) for j, v in enumerate(row)))
        if i == 0:
            print(sep)


def _cell(value) -> str:
    """Render a single cell for the text table."""
    return "" if value is None else str(value)


def _resolve_files(raw: list[str]) -> list[Path]:
    """Turn raw paths into existing, supported files or exit with an error."""
    paths: list[Path] = []
    for item in raw:
        path = Path(item)
        if not path.exists():
            logging.error("Arquivo não encontrado: %s", path)
            sys.exit(1)
        if not scanner.is_supported(path):
            logging.error("Formato não suportado: %s", path.name)
            sys.exit(1)
        paths.append(path)
    return paths


def _resolve_sql(ns: argparse.Namespace, files: list) -> str:
    """Resolve the SQL to run: the literal ``--sql`` text, or the IA's translation.

    Shared by the ``query`` and ``plot`` ops. Prints the IA's "Entendi assim"
    explanation (the GUI review card's analogue) and exits on a translation error.
    """
    if ns.sql:
        return ns.question
    schema = scanner.schema_text(files)
    try:
        sql, explanation = nl2sql.to_sql(schema, ns.question, model_name=ns.model)
    except Exception as exc:
        logging.error("Falha ao traduzir a pergunta para SQL: %s", exc)
        sys.exit(1)
    if explanation:
        print(f"\nEntendi assim: {explanation}")
    return sql


def _query(ns: argparse.Namespace) -> None:
    """Run the ``data query`` operation."""
    files = scanner.scan_files(_resolve_files(ns.files))
    for f in files:
        print(
            f"• {f.path.name} → {f.view_name} ({f.n_rows} linhas, {f.n_cols} colunas)"
        )

    sql = _resolve_sql(ns, files)
    print(f"\nSQL:\n{sql}\n")

    result = run_query(files, sql, max_rows=ns.limit)
    _print_table(result.columns, result.rows)
    print(f"\n{result.n_rows} linha(s) · {result.elapsed:.3f}s")

    if ns.out:
        stem = ns.name or "consulta"
        out = convert.save_query(files, sql, DATA_DIR, ns.out, stem)
        print(f"[✓] Resultado salvo em: {out}")


def _convert(ns: argparse.Namespace) -> None:
    """Run the ``data convert`` operation."""
    (src,) = _resolve_files([ns.file])
    out = convert.convert_file(src, DATA_DIR, ns.out)
    print(f"[✓] Convertido para: {out}")


def _profile(ns: argparse.Namespace) -> None:
    """Run the ``data profile`` operation."""
    (src,) = _resolve_files([ns.file])
    out = profile.profile_file(src, DATA_DIR)
    print(f"[✓] Perfil salvo em: {out}\n")
    print(out.read_text(encoding="utf-8"))


def _assess(ns: argparse.Namespace) -> None:
    """Run the ``data assess`` operation (IA data-quality narrative)."""
    from src.core.data import assess as assess_mod
    from src.core.data.datacard import sample_to_text
    from src.core.data.engine import preview

    (src,) = _resolve_files([ns.file])

    if not ns.no_cache:
        cached = assess_mod.load_cached_assessment(src)
        if cached:
            print(f"[✓] Avaliação de {src.name} (do cache):\n")
            print(cached)
            return

    file = scanner.scan_file(src)
    schema = scanner.schema_text([file])
    prof = profile.profile_text(src)
    sample = sample_to_text(preview(src, limit=10))
    try:
        text = assess_mod.assess(schema, prof, sample, model_name=ns.model)
    except Exception as exc:
        logging.error("Falha ao avaliar com a IA: %s", exc)
        sys.exit(1)
    assess_mod.save_assessment(src, text)  # cache → reused by indexing
    print(f"[✓] Avaliação de {src.name}:\n")
    print(text)


def _plot(ns: argparse.Namespace) -> None:
    """Run the ``data plot`` operation — render a chart PNG from a query.

    Consumes the Plano 0 foundation: ``run_query_arrow`` (zero-copy) →
    ``frames.from_arrow`` → ``frames.to_pandas`` → ``charts.render_png``. The
    chart kind/x/y come from ``--kind``/``--x``/``--y`` or ``suggest_spec``.
    """
    from src.core.data import frames
    from src.core.data.engine import run_query_arrow

    if not (frames.is_available() and charts.is_available()):
        logging.error(charts.SETUP_HINT)
        sys.exit(1)

    files = scanner.scan_files(_resolve_files(ns.files))
    for f in files:
        print(
            f"• {f.path.name} → {f.view_name} ({f.n_rows} linhas, {f.n_cols} colunas)"
        )
    sql = _resolve_sql(ns, files)
    print(f"\nSQL:\n{sql}\n")

    pl_df = frames.from_arrow(run_query_arrow(files, sql))
    if pl_df.height == 0:
        logging.error("A consulta não retornou linhas para plotar.")
        sys.exit(1)

    schema = [(name, str(dtype)) for name, dtype in pl_df.schema.items()]
    suggested = charts.suggest_spec(schema)
    spec = charts.ChartSpec(
        kind=ns.kind or suggested.kind,
        x=ns.x or suggested.x,
        y=ns.y or suggested.y,
    )

    png = charts.render_png(frames.to_pandas(pl_df), spec)
    out_name = ns.out or "grafico.png"
    if not out_name.lower().endswith(".png"):
        out_name += ".png"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / out_name
    out_path.write_bytes(png)
    print(f"[✓] Gráfico salvo em: {out_path} ({spec.kind}, x={spec.x}, y={spec.y})")


def _outliers(ns: argparse.Namespace) -> None:
    """Run the ``data outliers`` operation — flag anomalous rows via IsolationForest.

    Reads the whole file (not a filtered query) into a pandas frame via the
    Plano 0 boundary (``frames``/``run_query_arrow``), same as ``_plot``.
    """
    from src.core.data import frames
    from src.core.data.engine import run_query_arrow
    from src.core.data.ml import ANOMALY_COLUMN, detect_outliers
    from src.core.ml import deps

    if not (frames.is_available() and deps.is_available()):
        logging.error(deps.SETUP_HINT if not deps.is_available() else frames.SETUP_HINT)
        sys.exit(1)

    (src,) = _resolve_files([ns.file])
    files = scanner.scan_files([src])
    pl_df = frames.from_arrow(
        run_query_arrow(files, f'SELECT * FROM "{files[0].view_name}"')
    )
    if pl_df.height == 0:
        logging.error("Arquivo sem linhas para analisar.")
        sys.exit(1)

    try:
        result = detect_outliers(
            frames.to_pandas(pl_df), contamination=ns.contamination
        )
    except ValueError as exc:
        logging.error(str(exc))
        sys.exit(1)

    flagged = result[result[ANOMALY_COLUMN] < 0].sort_values(ANOMALY_COLUMN)
    print(f"{len(flagged)} de {len(result)} linha(s) sinalizada(s) como atípica(s).\n")
    if len(flagged):
        preview = flagged.head(ns.limit)
        _print_table(
            list(preview.columns),
            [tuple(row) for row in preview.itertuples(index=False)],
        )

    from src.core.observatory.activity import log_activity

    log_activity(
        "data",
        "outliers_detected",
        f"{src.name}: {len(flagged)} de {len(result)} linha(s) atípica(s)",
    )


def run_data_cli(ns: argparse.Namespace) -> None:
    """Dispatch the ``data`` subcommand to its operation handler."""
    # Data values often contain non-cp1252 characters; force UTF-8 stdout.
    # Reconfigure only our real stdout; under pytest sys.stdout is a capture
    # wrapper (≠ __stdout__) whose reconfigure would drop the captured output.
    if sys.stdout is sys.__stdout__:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    setup_logging(getattr(ns, "verbose", False))

    op = ns.data_op
    if op == "query":
        _query(ns)
    elif op == "convert":
        _convert(ns)
    elif op == "profile":
        _profile(ns)
    elif op == "assess":
        _assess(ns)
    elif op == "plot":
        _plot(ns)
    elif op == "outliers":
        _outliers(ns)
