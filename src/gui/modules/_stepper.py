"""Shared "stepper" chip row — highlights the active stage of a short, fixed
sequence (RAG Buscar→Contexto→Responder, Mapa Agrupar→Projetar→Rotular,
Insights Palavras-chave→Resumo→Entidades). Item 3.5 (Observatório) of
``docs/plan/PLANO_ML_NOVAS_FEATURES.md``.

Only ever driven by real events from the worker/orchestration layer that
already knows the sequence — never a fabricated timer (the plan's explicit
"nenhum tempo fabricado" rule: most of these stages finish in well under a
second, so a chip lighting up briefly is honest; padding it out artificially
would not be).
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.gui.theme.tokens import Radius, Space, Type


def build_stepper(
    stages: list[tuple[str, str]],
) -> tuple[ft.Control, Callable[[str | None], None]]:
    """Build a row of stage chips; returns ``(control, set_active)``.

    Args:
        stages: ``(key, label)`` pairs, in execution order.

    ``set_active(key)`` highlights that stage and marks every earlier stage as
    done (checkmark); ``set_active(None)`` resets every chip to its resting
    (pending) state — call this once the whole sequence finishes.
    """
    labels = dict(stages)
    order = [key for key, _ in stages]
    chip_texts: dict[str, ft.Text] = {}
    chip_containers: dict[str, ft.Container] = {}

    def _chip(key: str, label: str) -> ft.Container:
        text = ft.Text(
            label, size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT
        )
        chip_texts[key] = text
        container = ft.Container(
            content=text,
            padding=ft.Padding(
                left=Space.sm, right=Space.sm, top=Space.xxs, bottom=Space.xxs
            ),
            border_radius=Radius.pill,
            bgcolor=ft.Colors.TRANSPARENT,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )
        chip_containers[key] = container
        return container

    row = ft.Row(
        controls=[_chip(key, label) for key, label in stages], spacing=Space.xs
    )

    def set_active(active: str | None) -> None:
        idx = order.index(active) if active in order else -1
        for i, key in enumerate(order):
            text = chip_texts[key]
            container = chip_containers[key]
            if i < idx:  # already done
                text.value = f"✓ {labels[key]}"
                text.weight = ft.FontWeight.W_400
                text.color = ft.Colors.ON_SURFACE_VARIANT
                container.bgcolor = ft.Colors.TRANSPARENT
            elif i == idx:  # active now
                text.value = labels[key]
                text.weight = ft.FontWeight.W_600
                text.color = ft.Colors.PRIMARY
                container.bgcolor = ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY)
            else:  # not reached yet
                text.value = labels[key]
                text.weight = ft.FontWeight.W_400
                text.color = ft.Colors.ON_SURFACE_VARIANT
                container.bgcolor = ft.Colors.TRANSPARENT

    return row, set_active
