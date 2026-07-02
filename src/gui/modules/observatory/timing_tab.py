"""Observatório — aba Tempo de resposta: latência persistente por modelo,
separada por domínio (LLM/VLM/Embedder).

Its own tab rather than a section inside Status — timing has enough surface
(3 tables + 2 charts) to deserve dedicated screen space instead of sharing one
with gates/classifier/config snapshot.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.gui.modules.observatory.timing_section import build_timing_section
from src.gui.theme.tokens import Space


def build_timing_tab(page: ft.Page) -> tuple[ft.Control, Callable[[], None]]:
    """Build the timing board control plus an ``apply()`` refresher."""
    llm_section = build_timing_section("LLM (texto)", show_chart=True)
    vlm_section = build_timing_section("VLM (descrição de imagem)", show_chart=True)
    # A single model (nomic-embed-custom) makes a comparison bar meaningless.
    embed_section = build_timing_section("Embedder", show_chart=False)

    control = ft.Column(
        controls=[llm_section.control, vlm_section.control, embed_section.control],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    def apply() -> None:
        from src.core.observatory.model_timing import load_timings, timings_by_domain
        from src.core.rag.analytics import model_timings

        entries = load_timings()
        llm_section.apply(model_timings(timings_by_domain(entries, "llm")))
        vlm_section.apply(model_timings(timings_by_domain(entries, "vlm")))
        embed_section.apply(model_timings(timings_by_domain(entries, "embed")))

        try:
            control.update()
        except Exception:
            pass

    return control, apply
