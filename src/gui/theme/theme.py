"""Design System — constrói e aplica ft.Theme à página."""
from __future__ import annotations

import flet as ft

from src.gui.theme.tokens import Color, Type


def _color_scheme(dark: bool) -> ft.ColorScheme:
    c = Color.dark if dark else Color.light
    return ft.ColorScheme(
        # acento primário — dourado único
        primary=c.primary,
        on_primary=c.on_primary,
        primary_container=ft.Colors.with_opacity(0.14, c.primary),
        on_primary_container=c.text,
        # secondary = dourado também (acento único)
        secondary=c.primary,
        on_secondary=c.on_primary,
        # superfícies
        # ATENÇÃO: surface → ft.Colors.SURFACE (painéis/cards, NÃO o fundo da janela)
        # O fundo da página é controlado por page.bgcolor via sync_page_bgcolor().
        surface=c.surface,              # "#1E1E22" → painéis, cards
        on_surface=c.text,
        on_surface_variant=c.text_secondary,
        # contornos
        outline=c.outline,
        outline_variant=c.outline_variant,
        # erros
        error=c.error,
        on_error=c.on_error,
    )


def _text_theme() -> ft.TextTheme:
    return ft.TextTheme(
        display_large=ft.TextStyle(size=34, weight=ft.FontWeight.W_600),
        title_large=ft.TextStyle(size=22, weight=ft.FontWeight.W_600),
        headline_small=ft.TextStyle(size=18, weight=ft.FontWeight.W_600),
        label_large=ft.TextStyle(size=13, weight=ft.FontWeight.W_600),
        body_medium=ft.TextStyle(size=14),
        body_small=ft.TextStyle(size=12),
    )


def build_theme(dark: bool = True) -> ft.Theme:
    """Constrói ft.Theme completo para o modo especificado."""
    return ft.Theme(
        use_material3=True,
        font_family=Type.FONT_UI,
        color_scheme=_color_scheme(dark),
        text_theme=_text_theme(),
    )


def sync_page_bgcolor(page: ft.Page) -> None:
    """Sincroniza page.bgcolor com o tema ativo.

    Flet/Flutter não usa ColorScheme.surface para o Scaffold background —
    é preciso setar page.bgcolor explicitamente.
    Chamar sempre que theme_mode mudar.
    """
    page.bgcolor = (
        Color.dark.bg if page.theme_mode == ft.ThemeMode.DARK else Color.light.bg
    )


def apply_theme(page: ft.Page) -> None:
    """Aplica temas claro e escuro à página e sincroniza page.bgcolor."""
    page.theme = build_theme(dark=False)
    page.dark_theme = build_theme(dark=True)
    sync_page_bgcolor(page)
