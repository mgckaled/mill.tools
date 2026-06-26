"""The single matplotlib boundary: render a query result to a PNG chart.

Mirrors ``engine.py`` (DuckDB) and ``frames.py`` (DataFrame) as the only module
that imports matplotlib — always lazily, via the thread-safe object-oriented API
(``Figure`` + ``FigureCanvasAgg``, never ``pyplot``), so a worker daemon thread
can render without touching pyplot's non-thread-safe global state. Charts come
out as **PNG bytes** (shown in an ``ft.Image``, saved as an artifact); no
matplotlib object or DataFrame ever crosses into the GUI.

Plotting needs the ``[analysis]`` extra (for the pandas frame the renderer
consumes) and ``[data-plot]`` (for matplotlib); :func:`is_available` gates the
callers like ``frames.is_available`` does. ``render_png`` takes a **pandas**
DataFrame (the edge already converted by ``frames.to_pandas``), so this module
imports neither Polars nor DuckDB — only matplotlib.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

CHART_KINDS = ("bar", "line", "hist", "scatter")

SETUP_HINT = (
    "Gráficos indisponíveis. Instale os extras com "
    "`uv sync --extra analysis --extra data-plot` (pandas + matplotlib)."
)


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """A pure specification of the chart to draw (``kind`` ∈ :data:`CHART_KINDS`)."""

    kind: str
    x: str | None = None  # x-axis column (category/temporal/numeric)
    y: str | None = None  # y-axis column (numeric); None for hist / count bar
    title: str | None = None


@dataclass(frozen=True, slots=True)
class ChartPalette:
    """Chart colors. The GUI injects the dark theme; the core keeps neutral defaults."""

    bg: str = "#FFFFFF"
    fg: str = "#1E1E20"
    accent: str = "#F4A63C"
    grid: str = "#D0D0D0"
    muted: str = "#888888"


DEFAULT_PALETTE = ChartPalette()


def is_available() -> bool:
    """Return True if matplotlib (the ``[data-plot]`` extra) is importable.

    Gate for the chart flows, mirroring ``frames.is_available``; never raises.
    """
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        return False
    return True


# --- schema heuristics (pure, no matplotlib) ---------------------------------

_NUMERIC_HINTS = (
    "int",
    "float",
    "double",
    "decimal",
    "real",
    "numeric",
)
_TEMPORAL_HINTS = ("date", "time", "timestamp")


def _kind_of(dtype: str) -> str:
    """Classify a dtype string into ``numeric``/``temporal``/``categorical``.

    Accepts DuckDB types (``BIGINT``/``DOUBLE``/``DATE``), Polars/pandas dtypes
    (``Int64``/``float64``/``datetime64``) and the canonical category names, so
    both the GUI (rows-inferred) and the CLI/worker (frame dtypes) can feed it.
    """
    d = dtype.strip().lower()
    if d in ("numeric", "temporal", "categorical"):
        return d
    if any(h in d for h in _TEMPORAL_HINTS):
        return "temporal"
    if any(h in d for h in _NUMERIC_HINTS):
        return "numeric"
    return "categorical"


def schema_from_rows(
    columns: list[str], rows: list[tuple], *, sample: int = 50
) -> list[tuple[str, str]]:
    """Infer a ``(column, category)`` schema from in-memory result rows.

    Lets the GUI pre-fill the chart controls without building a DataFrame: it
    samples the first non-null value per column and maps it to
    numeric/temporal/categorical (the categories :func:`_kind_of` understands).
    """
    out: list[tuple[str, str]] = []
    for i, name in enumerate(columns):
        category = "categorical"
        for row in rows[:sample]:
            value = row[i] if i < len(row) else None
            if value is None:
                continue
            if isinstance(value, bool):
                category = "categorical"
            elif isinstance(value, (int, float)):
                category = "numeric"
            elif isinstance(value, (_dt.date, _dt.datetime)):
                category = "temporal"
            else:
                category = "categorical"
            break
        out.append((name, category))
    return out


def suggest_spec(schema: list[tuple[str, str]]) -> ChartSpec:
    """Propose a sensible chart from ``(column, dtype)`` pairs.

    Heuristic (from the web survey): temporal + numeric → line; two numerics →
    scatter; categorical + numeric → bar; a single numeric → hist; no numeric →
    a count bar of the first column.
    """
    cols = [(name, _kind_of(dtype)) for name, dtype in schema]
    numerics = [n for n, k in cols if k == "numeric"]
    temporals = [n for n, k in cols if k == "temporal"]
    categoricals = [n for n, k in cols if k == "categorical"]

    if temporals and numerics:
        return ChartSpec(kind="line", x=temporals[0], y=numerics[0])
    if categoricals and numerics:
        return ChartSpec(kind="bar", x=categoricals[0], y=numerics[0])
    if len(numerics) >= 2:
        return ChartSpec(kind="scatter", x=numerics[0], y=numerics[1])
    if len(numerics) == 1:
        return ChartSpec(kind="hist", x=numerics[0])
    first = schema[0][0] if schema else None
    return ChartSpec(kind="bar", x=first)  # count bar (renderer handles y=None)


# --- rendering (the single matplotlib touchpoint) ----------------------------


def render_png(
    df, spec: ChartSpec, *, palette: ChartPalette = DEFAULT_PALETTE
) -> bytes:
    """Render *df* to a PNG (bytes) per *spec* — the only matplotlib touchpoint.

    Uses ``Figure`` + ``FigureCanvasAgg`` directly (no ``pyplot``, no global
    backend mutation), so it is safe to call from a worker daemon thread. Colors
    come from *palette* (the GUI injects the dark theme).

    Args:
        df: a pandas DataFrame (from ``frames.to_pandas``).
        spec: which chart to draw.
        palette: chart colors.

    Raises:
        ValueError: if *df* is empty, the kind is unknown, a referenced column is
            missing, or a kind's required axis is unset.
    """
    import io

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    if df is None or len(df) == 0:
        raise ValueError("Sem dados para plotar.")
    if spec.kind not in CHART_KINDS:
        raise ValueError(f"Tipo de gráfico inválido: {spec.kind!r}.")
    _require_columns(df, spec)

    fig = Figure(figsize=(7.5, 4.5), dpi=110)
    fig.patch.set_facecolor(palette.bg)
    canvas = FigureCanvasAgg(fig)  # attach an Agg canvas so print_png has a renderer
    ax = fig.add_subplot()
    _style_axes(ax, palette)
    _DRAW[spec.kind](ax, df, spec, palette)
    if spec.title:
        ax.set_title(spec.title, color=palette.fg)
    fig.tight_layout()

    buf = io.BytesIO()
    canvas.print_png(buf)
    return buf.getvalue()


def _require_columns(df, spec: ChartSpec) -> None:
    """Validate the spec against the frame's columns before drawing."""
    if not spec.x:
        raise ValueError("Defina a coluna do eixo X.")
    missing = [c for c in (spec.x, spec.y) if c and c not in df.columns]
    if missing:
        raise ValueError(f"Coluna(s) inexistente(s): {', '.join(missing)}.")
    if spec.kind in ("line", "scatter") and not spec.y:
        raise ValueError(f"O gráfico {spec.kind} precisa de uma coluna Y numérica.")


def _style_axes(ax, palette: ChartPalette) -> None:
    """Apply the palette to axes background, spines, ticks and grid."""
    ax.set_facecolor(palette.bg)
    ax.tick_params(colors=palette.muted, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(palette.grid)
    ax.grid(True, color=palette.grid, alpha=0.3, linewidth=0.6)
    ax.xaxis.label.set_color(palette.fg)
    ax.yaxis.label.set_color(palette.fg)


def _rotate_xticks(ax) -> None:
    """Slant x tick labels so dense categorical/temporal axes stay readable."""
    for label in ax.get_xticklabels():
        label.set_rotation(30)
        label.set_horizontalalignment("right")


def _bar(ax, df, spec: ChartSpec, palette: ChartPalette) -> None:
    x = df[spec.x].astype(str)
    if spec.y:
        ax.bar(x, df[spec.y], color=palette.accent)
        ax.set_ylabel(spec.y)
    else:  # no y → count occurrences of the x category
        counts = x.value_counts()
        ax.bar(counts.index.astype(str), counts.values, color=palette.accent)
        ax.set_ylabel("contagem")
    ax.set_xlabel(spec.x)
    _rotate_xticks(ax)


def _line(ax, df, spec: ChartSpec, palette: ChartPalette) -> None:
    ax.plot(df[spec.x], df[spec.y], color=palette.accent, marker="o", markersize=3)
    ax.set_xlabel(spec.x)
    ax.set_ylabel(spec.y)
    _rotate_xticks(ax)


def _hist(ax, df, spec: ChartSpec, palette: ChartPalette) -> None:
    ax.hist(df[spec.x].dropna(), bins="auto", color=palette.accent)
    ax.set_xlabel(spec.x)
    ax.set_ylabel("frequência")


def _scatter(ax, df, spec: ChartSpec, palette: ChartPalette) -> None:
    ax.scatter(
        df[spec.x], df[spec.y], color=palette.accent, alpha=0.75, edgecolors="none"
    )
    ax.set_xlabel(spec.x)
    ax.set_ylabel(spec.y)


_DRAW = {"bar": _bar, "line": _line, "hist": _hist, "scatter": _scatter}
