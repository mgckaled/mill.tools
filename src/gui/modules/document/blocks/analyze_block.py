"""Analyze operation block — model + analysis profile selectors."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.components.profile_selector import build_profile_selector
from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.tokens import Space


class AnalyzeRefs(NamedTuple):
    get_model: Callable[[], str]
    get_profile: Callable[[], str]


def build_analyze_block(page: ft.Page) -> tuple[ft.Column, AnalyzeRefs]:
    """Build the analyze operation block."""
    model_grid, _get_model, _ = segmented_selector(
        ["qwen7b-custom", "gemini-2.5-flash", "glm-4.7-flash"],
        "qwen7b-custom",
        page,
        labels={
            "qwen7b-custom": "Local (Qwen)",
            "gemini-2.5-flash": "Gemini Flash",
            "glm-4.7-flash": "GLM Flash",
        },
        columns=3,
    )

    profile_grid, _get_profile, _ = build_profile_selector(page, value="default")
    _profile_help = help_icon_for("transcription.analysis_profile", page)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Modelo de análise"),
                    ft.Container(expand=True),
                    help_icon_for("document.analyze_model", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            model_grid,
            ft.Row(
                [
                    section_label("Tipo de análise"),
                    ft.Container(expand=True),
                    *([_profile_help] if _profile_help else []),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            profile_grid,
        ],
    )
    return block, AnalyzeRefs(get_model=_get_model, get_profile=_get_profile)
