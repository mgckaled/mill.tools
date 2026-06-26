"""Unit tests for src/gui/modules/data/worker.py — run_data_plot event emission.

The worker has no Flet dependency: it emits through a fake bus. The Plano 0 chain
(run_query_arrow/frames) and the renderer (charts.render_png) are mocked at their
boundaries, so no real polars/matplotlib work runs here.
"""

from __future__ import annotations

import pytest


class _Bus:
    """Captures (type, payload) and ignores stage/module_id."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, type, stage, payload=None, module_id=""):
        self.events.append((type, payload or {}))

    def types(self) -> list[str]:
        return [t for t, _ in self.events]

    def payload_of(self, type: str) -> dict:
        return next(p for t, p in self.events if t == type)


def _spec():
    from src.core.data import charts

    return charts.ChartSpec(kind="bar", x="produto", y="qtd")


@pytest.mark.unit
def test_run_data_plot_emits_done_with_png(mocker):
    from src.core.data import charts
    from src.gui.modules.data.worker import run_data_plot

    mocker.patch("src.core.data.frames.is_available", return_value=True)
    mocker.patch("src.core.data.charts.is_available", return_value=True)
    mocker.patch("src.core.data.engine.run_query_arrow", return_value="ARROW")
    mocker.patch("src.core.data.frames.from_arrow", return_value="PLDF")
    mocker.patch("src.core.data.frames.to_pandas", return_value="PANDAS")
    mock_render = mocker.patch(
        "src.core.data.charts.render_png", return_value=b"\x89PNGdata"
    )

    bus = _Bus()
    spec = _spec()
    ok = run_data_plot(bus, ["f"], "SELECT 1", spec, charts.DEFAULT_PALETTE)

    assert ok is True
    assert bus.types() == ["data_plot_start", "data_plot_done", "task_done"]
    assert bus.payload_of("data_plot_done")["png"] == b"\x89PNGdata"
    # The renderer received the converted pandas frame and the exact spec.
    assert mock_render.call_args.args[0] == "PANDAS"
    assert mock_render.call_args.args[1] is spec


@pytest.mark.unit
def test_run_data_plot_gate_unavailable_emits_task_error(mocker):
    from src.core.data import charts
    from src.gui.modules.data.worker import run_data_plot

    mocker.patch("src.core.data.frames.is_available", return_value=False)
    render = mocker.patch("src.core.data.charts.render_png")

    bus = _Bus()
    ok = run_data_plot(bus, ["f"], "SELECT 1", _spec(), charts.DEFAULT_PALETTE)

    assert ok is False
    assert "data_plot_start" in bus.types()
    assert "task_error" in bus.types()
    assert "data_plot_done" not in bus.types()
    render.assert_not_called()  # never reaches the renderer without the extras
    assert charts.SETUP_HINT in bus.payload_of("task_error")["message"]


@pytest.mark.unit
def test_run_data_plot_render_error_emits_task_error(mocker):
    from src.core.data import charts
    from src.gui.modules.data.worker import run_data_plot

    mocker.patch("src.core.data.frames.is_available", return_value=True)
    mocker.patch("src.core.data.charts.is_available", return_value=True)
    mocker.patch("src.core.data.engine.run_query_arrow", return_value="ARROW")
    mocker.patch("src.core.data.frames.from_arrow", return_value="PLDF")
    mocker.patch("src.core.data.frames.to_pandas", return_value="PANDAS")
    mocker.patch("src.core.data.charts.render_png", side_effect=ValueError("Sem dados"))

    bus = _Bus()
    ok = run_data_plot(bus, ["f"], "SELECT 1", _spec(), charts.DEFAULT_PALETTE)

    assert ok is False
    assert "task_error" in bus.types()
    assert "data_plot_done" not in bus.types()
    assert "Sem dados" in bus.payload_of("task_error")["message"]
