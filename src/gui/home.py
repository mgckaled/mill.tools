"""Home screen do mill.tools — fundo animado + 4 cards de módulo."""
from __future__ import annotations

import asyncio
import math
from typing import Callable

import flet as ft

from src.gui import settings as _settings
from src.gui.assets import b64
from src.gui.theme import sync_page_bgcolor
from src.gui.theme.components import Cursor
from src.gui.theme.tokens import Color, Motion, Radius, Space, Type

_MODULE_CARDS: list[dict] = [
    {
        "id": "audio",
        "title": "Áudio",
        "icon": ft.Icons.MUSIC_NOTE_OUTLINED,
        "accent": Color.log.ok,
        "desc": "Baixe e processe áudio com qualidade profissional",
        "features": [
            "Baixe áudio de YouTube e outras plataformas",
            "Remova ruído de fundo com processamento local",
            "Normalize o volume pelo padrão EBU R128",
        ],
    },
    {
        "id": "video",
        "title": "Vídeo",
        "icon": ft.Icons.VIDEO_FILE_OUTLINED,
        "accent": Color.log.info,
        "desc": "Sete operações para edição e processamento de vídeo",
        "features": [
            "Baixe, converta e corte vídeos com precisão",
            "Comprima em H.264 e redimensione sem perda visual",
            "Extraia a trilha de áudio ou capture thumbnail",
        ],
    },
    {
        "id": "image",
        "title": "Imagens",
        "icon": ft.Icons.IMAGE_OUTLINED,
        "accent": Color.log.step,
        "desc": "Doze operações para editar e analisar imagens",
        "features": [
            "Converta, redimensione, recorte e gire imagens",
            "Remova fundos automaticamente com IA local",
            "Descreva o conteúdo de imagens com visão por IA",
        ],
    },
    {
        "id": "transcription",
        "title": "Transcrição",
        "icon": ft.Icons.SUBTITLES_OUTLINED,
        "accent": Color.dark.primary,
        "desc": "Converta áudio em texto com Whisper, 100 % local",
        "features": [
            "Transcreva com faster-whisper acelerado por GPU",
            "Formate e analise com LLM local ou em nuvem",
            "Exporte em TXT, Markdown ou formato prompt",
        ],
    },
]


def _palette(page: ft.Page):
    """Retorna Color.dark ou Color.light conforme o tema ativo."""
    return Color.dark if page.theme_mode != ft.ThemeMode.LIGHT else Color.light


def _on_card_hover(
    e: ft.HoverEvent,
    ctr: ft.Container,
    accent: str,
    page: ft.Page,
) -> None:
    is_hover = e.data == "true"
    pal = _palette(page)
    ctr.bgcolor = pal.surface_hover if is_hover else ft.Colors.SURFACE
    side = ft.BorderSide(1.5, ft.Colors.with_opacity(0.6, accent))
    outline = ft.BorderSide(1.5, pal.outline_variant)
    ctr.border = ft.Border(
        left=side if is_hover else outline,
        right=side if is_hover else outline,
        top=side if is_hover else outline,
        bottom=side if is_hover else outline,
    )
    ctr.update()


def _make_card(
    data: dict,
    on_tap: Callable[[str], None],
    page: ft.Page,
) -> ft.GestureDetector:
    """Constrói o GestureDetector wrapping o card Container."""
    accent = data["accent"]
    pal = _palette(page)

    feature_rows = [
        ft.Row(
            controls=[
                ft.Icon(ft.Icons.CIRCLE, size=5, color=pal.text_secondary),
                ft.Text(
                    f,
                    size=Type.caption.size,
                    color=pal.text_secondary,
                    expand=True,
                    no_wrap=False,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        for f in data["features"]
    ]

    ctr = ft.Container(
        height=250,
        expand=True,
        border_radius=Radius.lg,
        border=ft.Border(
            left=ft.BorderSide(1.5, pal.outline_variant),
            right=ft.BorderSide(1.5, pal.outline_variant),
            top=ft.BorderSide(1.5, pal.outline_variant),
            bottom=ft.BorderSide(1.5, pal.outline_variant),
        ),
        bgcolor=ft.Colors.SURFACE,
        padding=ft.Padding(left=Space.xl, right=Space.xl, top=Space.xl, bottom=Space.xl),
        shadow=ft.BoxShadow(
            blur_radius=12,
            spread_radius=0,
            offset=ft.Offset(0, 4),
            color=ft.Colors.with_opacity(0.20, ft.Colors.BLACK),
        ),
        animate=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN_OUT),
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(data["icon"], size=40, color=accent),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    data["title"],
                                    size=Type.heading.size,
                                    weight=ft.FontWeight.W_600,
                                    color=ft.Colors.ON_SURFACE,
                                ),
                                ft.Text(
                                    data["desc"],
                                    size=Type.caption.size,
                                    color=pal.text_secondary,
                                    no_wrap=False,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=Space.md,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=Space.sm),
                ft.Column(controls=feature_rows, spacing=4),
                ft.Container(expand=True),
                ft.Row(
                    controls=[
                        ft.Text(
                            "Abrir módulo",
                            size=Type.caption.size,
                            color=accent,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Icon(ft.Icons.ARROW_FORWARD, size=14, color=accent),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=0,
            expand=True,
        ),
    )
    ctr.on_hover = lambda e: _on_card_hover(e, ctr, accent, page)

    return ft.GestureDetector(
        mouse_cursor=Cursor.interactive,
        content=ctr,
        on_tap=lambda _: on_tap(data["id"]),
        expand=True,
    )


def show_home(page: ft.Page, on_complete: Callable[[str], None]) -> None:
    """Exibe a home screen; chama on_complete(module_id) ao navegar."""
    cfg = _settings.load()
    page.theme_mode = (
        ft.ThemeMode.DARK if cfg.get("theme_mode", "dark") == "dark"
        else ft.ThemeMode.LIGHT
    )
    sync_page_bgcolor(page)

    page.padding = 0

    # ── background: mill-symbol girando ────────────────────────────────────────
    _bg_turns: list[int] = [0]

    bg_symbol = ft.Image(
        src=b64("mill-symbol.png"),
        width=500,
        height=500,
        opacity=0.10,
        rotate=ft.Rotate(angle=0, alignment=ft.Alignment.CENTER),
        animate_rotation=ft.Animation(20_000, ft.AnimationCurve.LINEAR),
    )

    def _next_turn(_e=None) -> None:
        _bg_turns[0] += 1
        bg_symbol.rotate.angle = _bg_turns[0] * 2 * math.pi
        try:
            bg_symbol.update()
        except RuntimeError:
            pass

    bg_symbol.on_animation_end = _next_turn

    bg_layer = ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=bg_symbol,
    )

    # ── navegação com fade-out ──────────────────────────────────────────────────
    home_root: list[ft.Container] = [None]

    async def _navigate(module_id: str) -> None:
        home_root[0].opacity = 0
        page.update()
        await asyncio.sleep(0.35)
        on_complete(module_id)

    def _on_tap(module_id: str) -> None:
        page.run_task(_navigate, module_id)

    # ── header ──────────────────────────────────────────────────────────────────
    pal = _palette(page)
    header = ft.Row(
        controls=[
            ft.Text(
                spans=[
                    ft.TextSpan(
                        "mill",
                        ft.TextStyle(
                            color=ft.Colors.ON_SURFACE,
                            size=44,
                            weight=ft.FontWeight.W_600,
                        ),
                    ),
                    ft.TextSpan(
                        ".tools",
                        ft.TextStyle(
                            color=pal.primary,
                            size=44,
                            weight=ft.FontWeight.W_400,
                        ),
                    ),
                ]
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # ── cards ────────────────────────────────────────────────────────────────────
    cards = [_make_card(data, _on_tap, page) for data in _MODULE_CARDS]

    cards_grid = ft.Column(
        controls=[
            ft.Row(controls=[cards[0], cards[1]], spacing=Space.xl),
            ft.Row(controls=[cards[2], cards[3]], spacing=Space.xl),
        ],
        spacing=Space.xl,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    cards_wrapper = ft.Container(
        content=cards_grid,
        width=960,
        padding=ft.Padding(left=Space.xl, right=Space.xl, top=0, bottom=0),
    )

    # ── foreground ───────────────────────────────────────────────────────────────
    fg_layer = ft.Column(
        controls=[
            header,
            ft.Container(height=Space.xxxl),
            cards_wrapper,
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
    )

    # ── root com Stack ───────────────────────────────────────────────────────────
    root = ft.Container(
        expand=True,
        opacity=0,
        animate_opacity=ft.Animation(Motion.slow, ft.AnimationCurve.EASE_OUT),
        content=ft.Stack(
            controls=[bg_layer, fg_layer],
            expand=True,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ),
    )
    home_root[0] = root

    # ── montar página ────────────────────────────────────────────────────────────
    page.controls.clear()
    page.add(root)
    page.update()

    async def _run() -> None:
        await asyncio.sleep(0.05)
        root.opacity = 1
        page.update()
        _next_turn()

    page.run_task(_run)
