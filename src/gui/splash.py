"""Tela de abertura (splash) do mill.tools — cata-vento + fade de entrada."""
from __future__ import annotations

import asyncio
import math
from typing import Callable

import flet as ft

from src.gui.assets import b64

BG, GOLD, LIGHT = "#0E1B2C", "#F4A63C", "#EAF0F6"


def show_splash(page: ft.Page, on_complete: Callable[[], None]) -> None:
    """Exibe o splash full-screen; ao terminar, chama on_complete()."""
    page.padding = 0
    page.bgcolor = BG

    symbol = ft.Image(
        src=b64("mill-symbol.png"),
        width=300,
        height=300,
        opacity=0,
        scale=0.85,
        rotate=ft.Rotate(angle=0, alignment=ft.Alignment.CENTER),
        animate_opacity=ft.Animation(500, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(600, ft.AnimationCurve.EASE_OUT),
        animate_rotation=ft.Animation(1400, ft.AnimationCurve.EASE_OUT),
    )
    title = ft.Text(
        spans=[
            ft.TextSpan("mill", ft.TextStyle(color=LIGHT, weight=ft.FontWeight.W_600)),
            ft.TextSpan(".tools", ft.TextStyle(color=GOLD, weight=ft.FontWeight.W_400)),
        ],
        size=68,
        opacity=0,
        animate_opacity=ft.Animation(500, ft.AnimationCurve.EASE_OUT),
    )
    root = ft.Container(
        expand=True,
        bgcolor=BG,
        alignment=ft.Alignment.CENTER,
        opacity=1,
        animate_opacity=ft.Animation(350, ft.AnimationCurve.EASE_IN),
        content=ft.Column(
            controls=[symbol, ft.Container(height=36), title],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    page.controls.clear()
    page.add(root)
    page.update()

    async def _run() -> None:
        await asyncio.sleep(0.05)
        symbol.opacity = 1
        symbol.scale = 1
        symbol.rotate.angle = 2 * math.pi
        page.update()
        await asyncio.sleep(0.25)
        title.opacity = 1
        page.update()
        await asyncio.sleep(1.4)
        root.opacity = 0
        page.update()
        await asyncio.sleep(0.35)
        on_complete()

    page.run_task(_run)
