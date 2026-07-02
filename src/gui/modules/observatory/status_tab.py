"""Observatório — aba Status: inventário read-only dos motores de ML.

Mirrors library/analytics_panel.py's shape: `build_status_tab(page) ->
(control, apply)`, `apply()` recomputes every row synchronously (cheap, pure
reads over what core/observatory/status.py already aggregates).
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.observatory import status
from src.gui.theme.components import hairline, help_icon_for, section_label
from src.gui.theme.tokens import Space, Type

_DOMAIN_LABELS = {
    "transcription_profile": "Perfil de transcrição",
    "data_domain": "Domínio de dados",
    "document_type": "Tipo de documento",
}


def _section_header(text: str, help_key: str, page: ft.Page) -> ft.Control:
    """A section_label with an optional ⓘ (tooltip, or modal for long help)."""
    icon = help_icon_for(help_key, page)
    if icon is None:
        return section_label(text)
    return ft.Row(
        [section_label(text), icon],
        spacing=Space.xs,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _gate_row(gate: status.GateStatus) -> ft.Row:
    icon = ft.Icons.CHECK_CIRCLE_OUTLINE if gate.available else ft.Icons.CANCEL_OUTLINED
    color = ft.Colors.GREEN if gate.available else ft.Colors.ON_SURFACE_VARIANT
    detail = "" if gate.available else gate.hint
    return ft.Row(
        controls=[
            ft.Icon(icon, size=Type.body.size, color=color),
            ft.Text(gate.name, size=Type.body.size, color=ft.Colors.ON_SURFACE),
            ft.Text(
                detail,
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
                expand=True,
                no_wrap=False,
            ),
        ],
        spacing=Space.sm,
    )


def _glossary_row(glossary: status.EntityGlossaryStatus) -> ft.Row:
    text = (
        f"Glossário de entidades: {glossary.n_patterns} padrão(ões) carregado(s)"
        if glossary.exists
        else "Glossário de entidades: nenhum arquivo configurado (opcional)"
    )
    return ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.INFO_OUTLINE,
                size=Type.body.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Text(text, size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT),
        ],
        spacing=Space.sm,
    )


def _binary_row(b: status.BinaryStatus) -> ft.Row:
    icon = ft.Icons.CHECK_CIRCLE_OUTLINE if b.path else ft.Icons.CANCEL_OUTLINED
    color = ft.Colors.GREEN if b.path else ft.Colors.ON_SURFACE_VARIANT
    detail = b.path or "não encontrado no PATH"
    return ft.Row(
        controls=[
            ft.Icon(icon, size=Type.body.size, color=color),
            ft.Text(b.name, size=Type.body.size, color=ft.Colors.ON_SURFACE, width=90),
            ft.Text(
                detail,
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
                expand=True,
                no_wrap=False,
            ),
        ],
        spacing=Space.sm,
    )


def _ollama_model_row(m: status.OllamaModelStatus) -> ft.Row:
    icon = ft.Icons.CHECK_CIRCLE_OUTLINE if m.installed else ft.Icons.CANCEL_OUTLINED
    color = ft.Colors.GREEN if m.installed else ft.Colors.ON_SURFACE_VARIANT
    return ft.Row(
        controls=[
            ft.Icon(icon, size=Type.body.size, color=color),
            ft.Text(m.name, size=Type.body.size, color=ft.Colors.ON_SURFACE),
        ],
        spacing=Space.sm,
    )


def _ollama_rows(inventory: status.OllamaInventoryStatus) -> list[ft.Control]:
    if not inventory.reachable:
        return [
            ft.Text(
                "Ollama não está acessível (serviço rodando?)",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            )
        ]
    return [_ollama_model_row(m) for m in inventory.models]


def _domain_row(d: status.DomainStatus) -> ft.Row:
    method = "supervisionado" if d.supervised else "zero-shot"
    return ft.Row(
        controls=[
            ft.Text(
                _DOMAIN_LABELS.get(d.domain, d.domain),
                size=Type.body.size,
                color=ft.Colors.ON_SURFACE,
                expand=True,
            ),
            ft.Text(
                f"{d.n_labels} rótulo(s) · {method}",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ]
    )


def build_status_tab(page: ft.Page) -> tuple[ft.Control, Callable[[], None]]:
    """Build the status board control plus an ``apply()`` refresher."""
    gates_col = ft.Column(spacing=Space.xs)
    ollama_col = ft.Column(spacing=Space.xs)
    binaries_col = ft.Column(spacing=Space.xs)
    domains_col = ft.Column(spacing=Space.xs)
    config_col = ft.Column(spacing=Space.xs)

    control = ft.Column(
        controls=[
            _section_header("Gates e extras", "observatory.gates", page),
            gates_col,
            hairline(),
            _section_header("Modelos Ollama", "observatory.ollama", page),
            ollama_col,
            hairline(),
            _section_header("Binários externos", "observatory.binaries", page),
            binaries_col,
            hairline(),
            _section_header(
                "Classificador (por domínio)", "observatory.classify", page
            ),
            domains_col,
            hairline(),
            _section_header("Configuração em vigor", "observatory.config", page),
            config_col,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    def apply() -> None:
        gates_col.controls = [_gate_row(g) for g in status.gate_statuses()] + [
            _glossary_row(status.entity_glossary_status())
        ]
        ollama_col.controls = _ollama_rows(status.ollama_inventory())
        binaries_col.controls = [_binary_row(b) for b in status.binary_statuses()]
        domains_col.controls = [_domain_row(d) for d in status.domain_statuses()]

        snap = status.config_snapshot()
        config_col.controls = [
            ft.Text(
                f"Limiar de dedup de texto: {snap.text_dedup_threshold:.2f}  ·  "
                f"Distância máx. dedup de imagem: {snap.image_dedup_max_distance}  ·  "
                f"Piso de corpus p/ auto-k: {snap.auto_k_min_corpus}  ·  "
                f"λ do MMR: {snap.mmr_lambda:.2f}",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                no_wrap=False,
            )
        ]

        try:
            control.update()
        except Exception:
            pass

    return control, apply
