"""Shared chart helpers for the Plano 2 hub panels (Library/IA/Recipes).

One place to turn a pure ``QueryResult`` into a PNG via the Plano 1 path
(``frames`` → pandas → ``charts.render_png``) with the dark-theme palette
injected, so each panel does not re-implement the conversion. Core imports stay
lazy and behind ``extras_available()``: a missing ``[analysis]``/``[data-plot]``
extra degrades gracefully (the panel shows numbers, hides the chart). No Polars/
matplotlib object ever crosses back to the GUI — only PNG bytes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.gui.theme.tokens import Color

if TYPE_CHECKING:
    from src.core.data.charts import ChartSpec
    from src.core.data.types import QueryResult

# 1x1 transparent PNG: Flet 0.85's ``ft.Image`` requires a ``src`` at
# construction, so panels start with this placeholder and swap in the rendered
# chart bytes later (same pattern as audio_player/plot_tab).
BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def extras_available() -> bool:
    """True when both the DataFrame (``[analysis]``) and chart (``[data-plot]``) extras exist."""
    from src.core.data import charts, frames

    return frames.is_available() and charts.is_available()


def setup_hint() -> str:
    """The install hint shown when the chart extras are missing."""
    from src.core.data import charts

    return charts.SETUP_HINT


def dark_palette():
    """Build the dark-theme ``ChartPalette`` the GUI injects into the renderer."""
    from src.core.data.charts import ChartPalette

    return ChartPalette(
        bg=Color.dark.surface,
        fg=Color.dark.text,
        accent=Color.dark.primary,
        grid=Color.dark.outline_variant,
        muted=Color.dark.text_secondary,
    )


def render_result_png(result: QueryResult, spec: ChartSpec) -> bytes:
    """Convert a ``QueryResult`` to pandas and render a PNG — the blocking payload.

    Call off the UI thread (``asyncio.to_thread`` from a coroutine, or directly
    inside a daemon worker): matplotlib must never run on the UI thread.
    """
    from src.core.data import charts, frames

    pdf = frames.to_pandas(frames.to_polars(result))
    return charts.render_png(pdf, spec, palette=dark_palette())
