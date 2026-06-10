"""Analyze operation block — model selector."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.tokens import Space


class AnalyzeRefs(NamedTuple):
    get_model: Callable[[], str]


def build_analyze_block(page: ft.Page) -> tuple[ft.Column, AnalyzeRefs]:
    """Build the analyze operation block."""
    _model_get: list[Callable] = []
    model_grid, _get_model, _ = segmented_selector(
        ["qwen7b-custom", "gemini-2.5-flash"],
        "qwen7b-custom",
        page,
        labels={"qwen7b-custom": "Local (Qwen)", "gemini-2.5-flash": "Gemini Flash"},
        columns=2,
    )
    _model_get.append(_get_model)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [section_label("Modelo de análise"), ft.Container(expand=True),
                 help_icon_for("document.analyze_model", page)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            model_grid,
        ],
    )
    return block, AnalyzeRefs(get_model=lambda: _model_get[0]())
