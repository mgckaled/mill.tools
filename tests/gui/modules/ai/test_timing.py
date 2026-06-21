"""Unit tests for the AI answer-time helpers (rolling average + formatting)."""

from __future__ import annotations

import pytest

from src.gui.modules.ai import timing


@pytest.mark.unit
def test_record_duration_appends_and_trims():
    out = timing.record_duration([1.0, 2.0], 3.0, keep=3)
    assert out == [1.0, 2.0, 3.0]
    # Oldest is dropped once the window is full.
    assert timing.record_duration([1.0, 2.0, 3.0], 4.0, keep=3) == [2.0, 3.0, 4.0]


@pytest.mark.unit
def test_record_duration_ignores_non_positive():
    assert timing.record_duration([2.0], 0.0) == [2.0]
    assert timing.record_duration([2.0], -5.0) == [2.0]
    # Pre-existing junk samples are filtered out too.
    assert timing.record_duration([0.0, -1.0, 2.0], 3.0) == [2.0, 3.0]


@pytest.mark.unit
def test_average():
    assert timing.average([2.0, 4.0]) == pytest.approx(3.0)
    assert timing.average([]) is None
    assert timing.average([0.0, -1.0]) is None  # no positive samples


@pytest.mark.unit
@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0:00"),
        (5, "0:05"),
        (14, "0:14"),
        (74, "1:14"),
        (3661, "61:01"),
        (-3, "0:00"),
    ],
)
def test_format_clock(seconds, expected):
    assert timing.format_clock(seconds) == expected


@pytest.mark.unit
def test_format_typical():
    assert timing.format_typical(None, "m") is None
    assert timing.format_typical(0.0, "m") is None
    assert timing.format_typical(27.6, "gemma3-4b-custom") == (
        "~28s (típico do gemma3-4b-custom)"
    )


@pytest.mark.unit
def test_compose_status():
    assert timing.compose_status(14, None) == "Gerando resposta… 0:14"
    assert timing.compose_status(14, "~28s (típico do m)") == (
        "Gerando resposta… 0:14 · ~28s (típico do m)"
    )
