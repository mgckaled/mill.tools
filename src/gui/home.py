"""Home screen do mill.tools — fundo animado + 5 ferramentas + 3 hubs (Biblioteca/IA/Receitas)."""

from __future__ import annotations

import asyncio
import math
from typing import Callable

import flet as ft

from src.gui import settings as _settings
from src.gui.assets import b64
from src.gui.theme import sync_page_bgcolor
from src.gui.theme.components import Cursor
from src.gui.theme.tokens import Color, IconSize, Motion, Radius, Space, Type

# Layout constants local to the home screen (not shared design tokens).
# Cards rest compact (icon + title + one-line desc) and grow on hover to reveal
# the feature detail. Rows size to their content, so the hovered card grows and
# the rows below shift down (reflow). Only one card hovers at a time, so the
# layout never exceeds the original all-expanded footprint and fits the window.
# Tweak the *_EXPANDED_H values to the final copy if a feature line ever clips.
_TOOL_COMPACT_H = 104
_TOOL_EXPANDED_H = 210
_HUB_COMPACT_H = 92
_HUB_EXPANDED_H = 162
_HUB_ICON_CHIP = 56
_CARD_ICON_SIZE = 40
_GRID_WIDTH = 1280

# The 5 processing tools — vertical cards, three per row (3 + 2).
_TOOL_CARDS: list[dict] = [
    {
        "id": "audio",
        "title": "Áudio",
        "icon": ft.Icons.MUSIC_NOTE_OUTLINED,
        "accent": Color.log.ok,
        "desc": "Baixe e processe áudio com qualidade profissional",
        "features": [
            "Baixe de YouTube, SoundCloud e mais",
            "Converta entre MP3, M4A, WAV, OGG e Opus",
            "Reduza ruído de fundo, 100 % local",
            "Normalize o volume pelo padrão EBU R128",
        ],
    },
    {
        "id": "video",
        "title": "Vídeo",
        "icon": ft.Icons.VIDEO_FILE_OUTLINED,
        "accent": Color.log.info,
        "desc": "Oito operações para baixar, editar e processar vídeo",
        "features": [
            "Baixe, converta de codec e corte por tempo",
            "Comprima em H.264 e redimensione sem perda",
            "Extraia a trilha de áudio ou thumbnails",
            "Embuta ou queime legendas SRT/VTT",
        ],
    },
    {
        "id": "image",
        "title": "Imagens",
        "icon": ft.Icons.IMAGE_OUTLINED,
        "accent": Color.log.step,
        "desc": "Doze operações para editar e analisar imagens",
        "features": [
            "Converta, redimensione, recorte e gire",
            "Marca d'água, borda, filtros e ajustes",
            "Remova fundos automaticamente com IA local",
            "Descreva imagens com visão por IA",
        ],
    },
    {
        "id": "transcription",
        "title": "Transcrição",
        "icon": ft.Icons.SUBTITLES_OUTLINED,
        "accent": Color.log.work,
        "desc": "Converta áudio em texto com Whisper, 100 % local",
        "features": [
            "Transcreva áudio, vídeo ou URL local",
            "Aceleração por GPU + legendas SRT/VTT",
            "Formate e analise com LLM local ou nuvem",
            "Exporte em TXT, Markdown ou prompt",
        ],
    },
    {
        "id": "document",
        "title": "Documentos",
        "icon": ft.Icons.DESCRIPTION_OUTLINED,
        "accent": Color.log.error,
        "desc": "Treze operações para PDFs — local e torch-free",
        "features": [
            "Una, divida, comprima, gire e rotule",
            "Marcas d'água, carimbos e AES-256",
            "Extraia texto, faça OCR e analise",
            "Converta páginas em imagens e gere QR",
        ],
    },
]

# The 3 hubs — wider, horizontal cards with a gold accent + "HUB" badge. They
# operate over every tool's output, so they get their own highlighted section.
_HUB_CARDS: list[dict] = [
    {
        "id": "library",
        "title": "Biblioteca",
        "icon": ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED,
        "accent": Color.dark.primary,
        "desc": "Tudo que você já gerou, reunido",
        "features": [
            "Navegue, filtre, busque e ordene",
            "Abra resultados sem reprocessar",
            "Reenvie a qualquer outro módulo",
        ],
    },
    {
        "id": "ai",
        "title": "IA",
        "icon": ft.Icons.AUTO_AWESOME_OUTLINED,
        "accent": Color.log.step,
        "desc": "Converse com seu acervo, RAG local",
        "features": [
            "Pergunte sobre todo o seu acervo",
            "Respostas citando as fontes [n]",
            "Embeddings 100 % locais",
        ],
    },
    {
        "id": "recipes",
        "title": "Receitas",
        "icon": ft.Icons.ACCOUNT_TREE_OUTLINED,
        "accent": Color.log.work,
        "desc": "Cadeias automáticas entre módulos",
        "features": [
            "URL → áudio → transcrever → analisar",
            "Rode presets ou crie a sua",
            "Processe em lote, limpe restos",
        ],
    },
]


def _palette(page: ft.Page):
    """Retorna Color.dark ou Color.light conforme o tema ativo."""
    return Color.dark if page.theme_mode != ft.ThemeMode.LIGHT else Color.light


def _border(side: ft.BorderSide) -> ft.Border:
    """Borda uniforme nos quatro lados."""
    return ft.Border(left=side, right=side, top=side, bottom=side)


def _feature_row(text: str) -> ft.Row:
    """Linha de feature: marcador + texto, partilhada por ferramentas e hubs."""
    return ft.Row(
        controls=[
            ft.Icon(ft.Icons.CIRCLE, size=5, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(
                text,
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                expand=True,
                no_wrap=False,
            ),
        ],
        spacing=Space.xs,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _section_label(text: str) -> ft.Control:
    """Rótulo de seção — pequeno, maiúsculo, muted, alinhado à esquerda."""
    return ft.Row(
        controls=[
            ft.Text(
                text,
                size=Type.small.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        ],
        alignment=ft.MainAxisAlignment.START,
    )


def _make_card(
    data: dict,
    on_tap: Callable[[str], None],
    page: ft.Page,
) -> ft.GestureDetector:
    """Vertical tool card: rests compact, grows on hover to reveal its detail."""
    accent = data["accent"]
    pal = _palette(page)

    # Feature detail — present in the tree but hidden at rest (clip crops it; the
    # opacity fade is polish). Revealed when the card grows on hover.
    detail = ft.Column(
        controls=[_feature_row(f) for f in data["features"]],
        spacing=4,
        opacity=0,
        animate_opacity=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN),
    )

    body = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Icon(data["icon"], size=_CARD_ICON_SIZE, color=accent),
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
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                no_wrap=False,
                            ),
                        ],
                        spacing=Space.xxs,
                        expand=True,
                    ),
                ],
                spacing=Space.md,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(height=Space.sm),
            detail,
        ],
        spacing=0,
    )

    ctr = ft.Container(
        height=_TOOL_COMPACT_H,
        expand=True,
        scale=1.0,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # crops the detail while compact
        border_radius=Radius.lg,
        border=_border(ft.BorderSide(1.5, pal.outline_variant)),
        bgcolor=ft.Colors.with_opacity(0.75, pal.surface),
        padding=ft.Padding(
            left=Space.lg, right=Space.lg, top=Space.lg, bottom=Space.lg
        ),
        shadow=ft.BoxShadow(
            blur_radius=12,
            spread_radius=0,
            offset=ft.Offset(0, 4),
            color=ft.Colors.with_opacity(0.20, ft.Colors.BLACK),
        ),
        animate=ft.Animation(Motion.base, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(Motion.base, ft.AnimationCurve.EASE_OUT),
        content=body,
    )

    def _set_hover(on: bool) -> None:
        ctr.height = _TOOL_EXPANDED_H if on else _TOOL_COMPACT_H
        ctr.scale = 1.015 if on else 1.0
        ctr.bgcolor = ft.Colors.with_opacity(
            0.88 if on else 0.75, pal.surface_hover if on else pal.surface
        )
        ctr.border = _border(
            ft.BorderSide(1.5, ft.Colors.with_opacity(0.6, accent))
            if on
            else ft.BorderSide(1.5, pal.outline_variant)
        )
        detail.opacity = 1 if on else 0
        ctr.update()

    # Hover (enter/exit) and tap both live on the SAME GestureDetector. A
    # Container.on_hover on a control fully covered by a gesture/mouse region
    # never fires — the GestureDetector's own on_enter/on_exit do.
    return ft.GestureDetector(
        mouse_cursor=Cursor.interactive,
        on_tap=lambda _: on_tap(data["id"]),
        on_enter=lambda _e: _set_hover(True),
        on_exit=lambda _e: _set_hover(False),
        content=ctr,
        expand=True,
    )


def _make_hub_card(
    data: dict,
    on_tap: Callable[[str], None],
    page: ft.Page,
) -> ft.GestureDetector:
    """Horizontal hub card — icon chip on the left, content on the right.

    Wider, with a gold rest border and a "HUB" badge. Like the tool cards, it
    rests compact and grows on hover to reveal its feature detail.
    """
    accent = data["accent"]
    pal = _palette(page)

    icon_chip = ft.Container(
        width=_HUB_ICON_CHIP,
        height=_HUB_ICON_CHIP,
        border_radius=Radius.md,
        bgcolor=ft.Colors.with_opacity(0.14, accent),
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(data["icon"], size=IconSize.xl, color=accent),
    )

    hub_badge = ft.Container(
        bgcolor=ft.Colors.with_opacity(0.16, ft.Colors.PRIMARY),
        border_radius=Radius.pill,
        padding=ft.Padding(
            left=Space.xs, right=Space.xs, top=Space.xxs, bottom=Space.xxs
        ),
        content=ft.Text(
            "HUB",
            size=Type.tiny.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.PRIMARY,
        ),
    )

    # Feature detail — hidden at rest (clipped), revealed when the card grows.
    detail = ft.Column(
        controls=[_feature_row(f) for f in data["features"]],
        spacing=4,
        opacity=0,
        animate_opacity=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN),
    )

    info = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Text(
                        data["title"],
                        size=Type.heading.size,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE,
                    ),
                    ft.Container(expand=True),
                    hub_badge,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(
                data["desc"],
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                no_wrap=False,
            ),
            ft.Container(height=Space.xxs),
            detail,
        ],
        spacing=Space.xxs,
        expand=True,
    )

    ctr = ft.Container(
        height=_HUB_COMPACT_H,
        expand=True,
        scale=1.0,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        border_radius=Radius.lg,
        border=_border(
            ft.BorderSide(1.5, ft.Colors.with_opacity(0.45, ft.Colors.PRIMARY))
        ),
        bgcolor=ft.Colors.with_opacity(0.80, pal.surface),
        padding=ft.Padding(
            left=Space.lg, right=Space.lg, top=Space.lg, bottom=Space.lg
        ),
        shadow=ft.BoxShadow(
            blur_radius=14,
            spread_radius=0,
            offset=ft.Offset(0, 5),
            color=ft.Colors.with_opacity(0.24, ft.Colors.BLACK),
        ),
        animate=ft.Animation(Motion.base, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(Motion.base, ft.AnimationCurve.EASE_OUT),
        content=ft.Row(
            controls=[icon_chip, info],
            spacing=Space.md,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    )

    def _set_hover(on: bool) -> None:
        ctr.height = _HUB_EXPANDED_H if on else _HUB_COMPACT_H
        ctr.scale = 1.012 if on else 1.0
        ctr.bgcolor = ft.Colors.with_opacity(
            0.90 if on else 0.80, pal.surface_hover if on else pal.surface
        )
        ctr.border = _border(
            ft.BorderSide(1.5, ft.Colors.with_opacity(0.6, accent))
            if on
            else ft.BorderSide(1.5, ft.Colors.with_opacity(0.45, ft.Colors.PRIMARY))
        )
        detail.opacity = 1 if on else 0
        ctr.update()

    # Tap + hover (enter/exit) both on the same GestureDetector — see _make_card.
    return ft.GestureDetector(
        mouse_cursor=Cursor.interactive,
        on_tap=lambda _: on_tap(data["id"]),
        on_enter=lambda _e: _set_hover(True),
        on_exit=lambda _e: _set_hover(False),
        content=ctr,
        expand=True,
    )


def show_home(page: ft.Page, on_complete: Callable[[str], None]) -> None:
    """Exibe a home screen; chama on_complete(module_id) ao navegar."""
    cfg = _settings.load()
    page.theme_mode = (
        ft.ThemeMode.DARK
        if cfg.get("theme_mode", "dark") == "dark"
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
        opacity=0.16,
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
        home_root[0].animate_opacity = ft.Animation(350, ft.AnimationCurve.EASE_IN)
        home_root[0].opacity = 0
        page.update()
        await asyncio.sleep(0.37)
        on_complete(module_id)

    def _on_tap(module_id: str) -> None:
        page.run_task(_navigate, module_id)

    # ── header ──────────────────────────────────────────────────────────────────
    header = ft.Row(
        controls=[
            ft.Text(
                spans=[
                    ft.TextSpan(
                        "mill",
                        ft.TextStyle(
                            color=ft.Colors.ON_SURFACE,
                            size=Type.wordmark.size,
                            weight=ft.FontWeight.W_600,
                        ),
                    ),
                    ft.TextSpan(
                        ".tools",
                        ft.TextStyle(
                            color=ft.Colors.PRIMARY,
                            size=Type.wordmark.size,
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
    tool_cards = [_make_card(data, _on_tap, page) for data in _TOOL_CARDS]
    hub_cards = [_make_hub_card(data, _on_tap, page) for data in _HUB_CARDS]

    def _flex(ctrl: ft.Control, weight: int) -> ft.Container:
        return ft.Container(content=ctrl, expand=weight)

    # Tools: 3 + 2. The second row centers its two cards at the same 1/3 width
    # via half-width spacers (flex 1 | 2·2 | 1 → each card = 2/6 = 1/3).
    # Rows size to content. START alignment keeps resting (compact) siblings
    # anchored at the top, so the hovered card grows downward and only the rows
    # below it shift (reflow) — no reserved dead space at rest.
    tools_grid = ft.Column(
        controls=[
            ft.Row(
                controls=[tool_cards[0], tool_cards[1], tool_cards[2]],
                spacing=Space.xl,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            ft.Row(
                controls=[
                    ft.Container(expand=1),
                    _flex(tool_cards[3], 2),
                    _flex(tool_cards[4], 2),
                    ft.Container(expand=1),
                ],
                spacing=Space.xl,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ],
        spacing=Space.md,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    # Hubs: wide cards in a single row (Biblioteca · IA · Receitas), each equal width.
    hubs_grid = ft.Row(
        controls=hub_cards,
        spacing=Space.xl,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )

    cards_grid = ft.Column(
        controls=[
            _section_label("FERRAMENTAS"),
            tools_grid,
            ft.Container(height=Space.sm),
            _section_label("ACERVO & INTELIGÊNCIA"),
            hubs_grid,
        ],
        spacing=Space.sm,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    cards_wrapper = ft.Container(
        content=cards_grid,
        width=_GRID_WIDTH,
        padding=ft.Padding(left=Space.xl, right=Space.xl, top=0, bottom=0),
    )

    # ── foreground: wordmark raised toward the top + cards ──────────────────────
    fg_layer = ft.Column(
        controls=[
            ft.Container(height=Space.sm),  # small top margin — everything raised
            header,
            ft.Container(height=Space.md),
            cards_wrapper,
        ],
        alignment=ft.MainAxisAlignment.START,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
    )

    # ── single open hint, top-left corner ───────────────────────────────────────
    # Positioned (top/left), NOT expand=True: a full-size overlay would sit on top
    # of the cards in the Stack and swallow every click/hover.
    hint = ft.Container(
        top=Space.lg,
        left=Space.xl,
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.TOUCH_APP_OUTLINED,
                    size=IconSize.md,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Selecione um módulo para começar",
                    size=Type.caption.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    # ── root com Stack ───────────────────────────────────────────────────────────
    root = ft.Container(
        expand=True,
        opacity=0,
        animate_opacity=ft.Animation(Motion.slow, ft.AnimationCurve.EASE_OUT),
        content=ft.Stack(
            controls=[bg_layer, fg_layer, hint],
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
