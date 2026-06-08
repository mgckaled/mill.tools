"""Design System — tokens de valor (sem dependência de Flet)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _TypeSpec:
    size: float
    weight: int
    family: str | None = None


class Color:
    """Paleta do mill.tools — dark / light / log."""

    class dark:
        bg = "#1E1E20"
        surface = "#262629"
        surface_variant = "#2F2F34"
        surface_hover = "#3A3A40"

        outline = "#52525B"
        outline_variant = "#484850"

        text = "#FFFFFF"
        text_secondary = "#A1A1AA"
        text_disabled = "#6B6B75"

        primary = "#F4A63C"
        primary_hover = "#F7B65C"
        primary_pressed = "#D88E2A"
        on_primary = "#1E1E20"

        error = "#E05A51"
        on_error = "#1E1E20"

    class light:
        bg = "#F6F8FB"
        surface = "#FFFFFF"
        surface_variant = "#EEF2F7"
        surface_hover = "#E4EBF5"
        outline = "#7890A0"
        outline_variant = "#AEBCC8"
        text = "#1B2A3A"
        text_secondary = "#5A6B7E"
        text_disabled = "#A6B2C0"
        primary = "#E0982F"
        primary_hover = "#E8A843"
        primary_pressed = "#C8841A"
        on_primary = "#1B2A3A"
        error = "#C62828"
        on_error = "#FFFFFF"

    class log:
        """Cores semânticas do log — estáveis em ambos os temas."""
        info = "#5B9BD5"   # [i]  azul     — informação (único uso de azul na UI)
        step = "#4FD0E0"   # [*]  ciano    — etapa / carregando
        work = "#F4A63C"   # [~]  dourado  — trabalhando (amarra com o spinner)
        ok = "#5FCF80"   # [✓]  verde    — concluído
        error = "#E5736B"   # [!]  vermelho — erro
        muted = "#6B7C90"   # [»][d] slate  — secundário / debug
        text = "#C0C8D0"   # (sem prefixo) — conteúdo transcrito


class Type:
    """Tipografia — família e escala de tamanho/peso."""

    FONT_UI = "Verdana"
    FONT_MONO = "JetBrains Mono"

    hero = _TypeSpec(68.0, 600)
    wordmark = _TypeSpec(44.0, 600)
    display = _TypeSpec(34.0, 600)
    title = _TypeSpec(22.0, 600)
    heading = _TypeSpec(18.0, 600)
    label = _TypeSpec(14.0, 600)
    body = _TypeSpec(16.0, 400)
    body_strong = _TypeSpec(16.0, 600)
    button = _TypeSpec(16.0, 600)
    caption = _TypeSpec(14.0, 400)
    small = _TypeSpec(11.0, 400)   # labels de ícone, caminhos, badges
    tiny = _TypeSpec(10.0, 400)    # rótulos micro ("Antes"/"Depois")
    input = _TypeSpec(13.0, 400)
    mono = _TypeSpec(13, 300, "JetBrains Mono")


class Space:
    """Grade de espaçamento em px (múltiplos de 4)."""

    xxs = 2
    xs = 6
    sm = 12
    md = 16
    lg = 18
    xl = 24
    xxl = 32
    xxxl = 48


class Radius:
    """Raios de borda."""

    sm = 6
    md = 10
    lg = 14
    pill = 999


class Motion:
    """Durações de animação em ms."""

    fast = 200
    base = 300
    slow = 500
    spin = 900


class Layout:
    """Constantes de layout global."""

    form_width = 380
    field_height = 38
    content_padding = 16
    content_lateral = 24
    nav_rail_width = 80
    section_gap = Space.xl
