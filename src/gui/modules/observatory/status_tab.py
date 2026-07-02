"""Observatório — aba Status: inventário read-only dos motores de ML.

Mirrors library/analytics_panel.py's shape: `build_status_tab(page) ->
(control, apply)`, `apply()` recomputes every row synchronously (cheap, pure
reads over what core/observatory/status.py already aggregates).
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.observatory import status
from src.gui.theme.components import hairline, section_label
from src.gui.theme.tokens import Space, Type

_DOMAIN_LABELS = {
    "transcription_profile": "Perfil de transcrição",
    "data_domain": "Domínio de dados",
    "document_type": "Tipo de documento",
}


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
    domains_col = ft.Column(spacing=Space.xs)
    config_col = ft.Column(spacing=Space.xs)

    control = ft.Column(
        controls=[
            section_label("Gates e extras"),
            gates_col,
            hairline(),
            section_label("Classificador (por domínio)"),
            domains_col,
            hairline(),
            section_label("Configuração em vigor"),
            config_col,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    def apply() -> None:
        gates_col.controls = [_gate_row(g) for g in status.gate_statuses()]
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
