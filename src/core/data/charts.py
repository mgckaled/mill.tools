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
import decimal
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


# Discrete, reasonably distinct colors for categorical scatter (e.g. the semantic
# map's clusters). Cycled in order; the noise/orphan category is drawn in ``muted``.
_CATEGORICAL = (
    "#F4A63C",
    "#5B9BD5",
    "#5FCF80",
    "#E0726B",
    "#B98CE0",
    "#4FD0E0",
    "#E0B84F",
    "#9CCF5F",
    "#E07FB0",
    "#7FA0E0",
)


@dataclass(frozen=True, slots=True)
class ChartPalette:
    """Chart colors. The GUI injects the dark theme; the core keeps neutral defaults."""

    bg: str = "#FFFFFF"
    fg: str = "#1E1E20"
    accent: str = "#F4A63C"
    grid: str = "#D0D0D0"
    muted: str = "#888888"
    categorical: tuple[str, ...] = _CATEGORICAL


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


def _numeric(df, col: str):
    """Coerce a column to float for plotting, with a clear error if it can't.

    DuckDB aggregates (``SUM`` over BIGINT → HUGEINT/DECIMAL) arrive as pandas
    ``object``/``Decimal`` columns that matplotlib's category machinery
    mishandles; coercing to float fixes that and turns a non-numeric pick for a
    numeric axis into a friendly message instead of a cryptic matplotlib error.
    """
    try:
        return df[col].astype(float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"A coluna '{col}' não é numérica.") from exc


def _numeric_x(df, col: str):
    """Coerce an x-axis column via :func:`_numeric`, but only if it holds numbers.

    Unlike y (always required numeric for line/scatter), a line chart's x is
    routinely temporal (``suggest_spec``'s own line heuristic is
    temporal+numeric) — coercing a datetime column to float would wreck
    matplotlib's date axis. So this only applies the same Decimal/object fix
    ``_bar``/``_scatter`` need when the column's first value is actually a
    number; a temporal or plain categorical x passes through untouched.
    """
    series = df[col]
    sample = series.dropna()
    if len(sample):
        first = sample.iloc[0]
        if not isinstance(first, bool) and isinstance(
            first, (int, float, decimal.Decimal)
        ):
            return _numeric(df, col)
    return series


def _bar(ax, df, spec: ChartSpec, palette: ChartPalette) -> None:
    if spec.y:
        labels = [str(v) for v in df[spec.x].tolist()]
        heights = _numeric(df, spec.y).tolist()
        ax.set_ylabel(spec.y)
    else:  # no y → count occurrences of the x category
        counts = df[spec.x].astype(str).value_counts()
        labels = [str(v) for v in counts.index.tolist()]
        heights = counts.values.tolist()
        ax.set_ylabel("contagem")
    # Plot against integer positions with explicit tick labels: passing string
    # categories straight to ax.bar trips matplotlib's category converter on
    # object/Decimal heights (the dtype DuckDB aggregates land in).
    positions = list(range(len(labels)))
    ax.bar(positions, heights, color=palette.accent)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel(spec.x)
    _rotate_xticks(ax)


def _line(ax, df, spec: ChartSpec, palette: ChartPalette) -> None:
    ax.plot(
        _numeric_x(df, spec.x),
        _numeric(df, spec.y),
        color=palette.accent,
        marker="o",
        markersize=3,
    )
    ax.set_xlabel(spec.x)
    ax.set_ylabel(spec.y)
    _rotate_xticks(ax)


def _hist(ax, df, spec: ChartSpec, palette: ChartPalette) -> None:
    ax.hist(_numeric(df, spec.x).dropna(), bins="auto", color=palette.accent)
    ax.set_xlabel(spec.x)
    ax.set_ylabel("frequência")


def _scatter(ax, df, spec: ChartSpec, palette: ChartPalette) -> None:
    ax.scatter(
        _numeric(df, spec.x),
        _numeric(df, spec.y),
        color=palette.accent,
        alpha=0.75,
        edgecolors="none",
    )
    ax.set_xlabel(spec.x)
    ax.set_ylabel(spec.y)


_DRAW = {"bar": _bar, "line": _line, "hist": _hist, "scatter": _scatter}


def render_category_scatter(
    df,
    *,
    x: str,
    y: str,
    color: str,
    annotations: list[tuple[float, float, str]] | None = None,
    title: str | None = None,
    noise_value: str | None = None,
    palette: ChartPalette = DEFAULT_PALETTE,
) -> bytes:
    """Render a categorical scatter to PNG (e.g. the semantic map) — bytes out.

    Each distinct value of the ``color`` column gets a discrete color from
    ``palette.categorical`` (first-seen order), with ``noise_value`` (the
    orphan/noise category) always drawn in ``palette.muted``. Optional
    ``annotations`` are ``(x, y, text)`` labels (cluster centroids). Like
    ``render_png`` this is the only matplotlib touchpoint — ``Figure`` +
    ``FigureCanvasAgg`` (no ``pyplot``), safe off the UI thread.

    Args:
        df: a pandas DataFrame with the ``x``/``y``/``color`` columns.
        x, y: numeric coordinate columns.
        color: the categorical column to color by (e.g. cluster name).
        annotations: optional centroid labels.
        title: optional chart title.
        noise_value: the category drawn muted (orphans); ``None`` to disable.
        palette: chart colors (the GUI injects the dark theme).

    Raises:
        ValueError: if *df* is empty or a referenced column is missing.
    """
    import io

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    if df is None or len(df) == 0:
        raise ValueError("Sem dados para plotar.")
    missing = [c for c in (x, y, color) if c not in df.columns]
    if missing:
        raise ValueError(f"Coluna(s) inexistente(s): {', '.join(missing)}.")

    fig = Figure(figsize=(7.5, 5.0), dpi=110)
    fig.patch.set_facecolor(palette.bg)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot()
    _style_axes(ax, palette)

    categories = list(dict.fromkeys(df[color].tolist()))  # distinct, first-seen
    cycle_i = 0
    for cat in categories:
        sub = df[df[color] == cat]
        if noise_value is not None and cat == noise_value:
            dot = palette.muted
        else:
            dot = palette.categorical[cycle_i % len(palette.categorical)]
            cycle_i += 1
        ax.scatter(
            _numeric(sub, x),
            _numeric(sub, y),
            color=dot,
            label=str(cat),
            alpha=0.8,
            edgecolors="none",
            s=32,
        )

    for ax_, ay, text in annotations or []:
        ax.annotate(
            text,
            (ax_, ay),
            color=palette.fg,
            fontsize=9,
            fontweight="bold",
            ha="center",
            va="center",
        )

    ax.set_xticks([])
    ax.set_yticks([])
    if title:
        ax.set_title(title, color=palette.fg)
    if len(categories) <= 12:
        legend = ax.legend(
            loc="best", fontsize=8, framealpha=0.2, labelcolor=palette.fg
        )
        if legend:
            legend.get_frame().set_facecolor(palette.bg)
    fig.tight_layout()

    buf = io.BytesIO()
    canvas.print_png(buf)
    return buf.getvalue()
