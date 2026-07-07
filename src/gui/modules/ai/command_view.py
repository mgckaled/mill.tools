"""NL→CLI command generation for the AI hub's "Comandos CLI" mode.

Fase 3 (PLANO_NL2CLI_HUB_IA.md). Mirrors answer_view.py's shape: a session of
cards (one per generated command, with a Copiar action instead of cited
sources) plus the ``ask()`` handler that kicks off ``run_ai_command``. The
ticker/``gen_status`` widget itself is owned by ``answer_view.py`` and reused
here (injected as ``start_ticker``) — only one of the two flows runs at a
time (``pipeline_running``) — but this file tracks its own "typical time"
from a separate settings bucket (``ai_command_times``), since RAG-answer
latency (retrieval + synthesis) is not comparable to command generation
(usually much shorter, no retrieval).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.gui import settings
from src.gui.modules.ai import timing
from src.gui.modules.ai.worker import start_ai_command
from src.gui.theme.components import action_button, secondary_button
from src.gui.theme.tokens import Color, IconSize, Radius, Space, Type

if TYPE_CHECKING:
    from src.gui.events import EventBus

_TIMES_KEY = "ai_command_times"


@dataclass
class CommandView:
    """Handles for the "Comandos CLI" session block."""

    clear_btn: ft.Control
    session_area: ft.Control
    ask: Callable[[], None]
    handle_command_done: Callable[[dict], None]


def build_command_view(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    *,
    get_query: Callable[[], str],
    get_model: Callable[[], str],
    on_begin: Callable[[], None],
    on_empty_query: Callable[[], None],
    start_ticker: Callable[[str | None], None],
) -> CommandView:
    """Build the "Comandos CLI" session view and return its handles."""

    _pending_model: list[str] = [""]

    def _record_command_time(model: str, elapsed: float) -> None:
        """Fold a finished generation's wall-clock time into the model's history."""
        if not model or elapsed <= 0:
            return
        times_map = dict(settings.load().get(_TIMES_KEY, {}))
        times_map[model] = timing.record_duration(times_map.get(model, []), elapsed)
        settings.set(_TIMES_KEY, times_map)

    # ------------------------------------------------------------------
    # Session rendering: one card per generated command, with a Copiar action.
    # ------------------------------------------------------------------

    def _copy_handler(command: str) -> Callable:
        # Quirk 0.85: page.set_clipboard doesn't exist — the async Clipboard
        # API needs an async handler (Flet awaits it automatically).
        async def _handler(_e) -> None:
            await ft.Clipboard().set(command)
            page.show_dialog(
                ft.SnackBar(content=ft.Text("Comando copiado."), duration=2000)
            )

        return _handler

    def _make_command_card(query: str, command: str, explanation: str) -> ft.Control:
        controls: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.HELP_OUTLINE,
                        size=IconSize.lg,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        query,
                        size=Type.body_strong.size,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE,
                        expand=True,
                        no_wrap=False,
                    ),
                ],
                spacing=Space.xs,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ]
        if not command:
            # A deliberate refusal (out-of-scope question) — no command to show.
            controls.append(
                ft.Text(
                    explanation or "Não entendi esse pedido.",
                    size=Type.body.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                    no_wrap=False,
                )
            )
        else:
            controls.append(
                ft.Container(
                    bgcolor=Color.dark.surface,
                    border_radius=Radius.md,
                    padding=ft.Padding(
                        left=Space.sm, right=Space.sm, top=Space.sm, bottom=Space.sm
                    ),
                    content=ft.Text(
                        command,
                        size=Type.mono.size,
                        font_family=Type.FONT_MONO,
                        color=ft.Colors.ON_SURFACE,
                        selectable=True,
                        no_wrap=False,
                    ),
                )
            )
            if explanation:
                controls.append(
                    ft.Text(
                        explanation,
                        size=Type.caption.size,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        no_wrap=False,
                    )
                )
            controls.append(
                secondary_button(
                    "Copiar",
                    icon=ft.Icons.CONTENT_COPY_OUTLINED,
                    on_click=_copy_handler(command),
                )
            )

        return ft.Container(
            bgcolor=Color.dark.surface_variant,
            border_radius=Radius.lg,
            padding=ft.Padding(
                left=Space.md, right=Space.md, top=Space.md, bottom=Space.md
            ),
            content=ft.Column(controls=controls, spacing=Space.sm),
        )

    def _append_card(query: str, command: str, explanation: str) -> None:
        empty_state.visible = False
        session_list.controls.append(_make_command_card(query, command, explanation))
        clear_btn.visible = True

    def _clear_session(_e=None) -> None:
        session_list.controls.clear()
        empty_state.visible = True
        clear_btn.visible = False
        page.update()

    def handle_command_done(payload: dict) -> None:
        _append_card(
            payload.get("query", ""),
            payload.get("command", ""),
            payload.get("explanation", ""),
        )
        _record_command_time(
            payload.get("model_name", _pending_model[0]), payload.get("elapsed", 0.0)
        )

    def ask() -> None:
        if pipeline_running[0]:
            return
        query = get_query()
        if not query:
            on_empty_query()
            return
        model = get_model()
        on_begin()
        _pending_model[0] = model
        times = settings.load().get(_TIMES_KEY, {}).get(model, [])
        typical = timing.format_typical(timing.average(times), model)
        start_ticker(typical)
        page.update()
        start_ai_command(bus, cancel_event, query=query, model_name=model)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    clear_btn = action_button(
        "Limpar comandos",
        icon=ft.Icons.DELETE_SWEEP_OUTLINED,
        on_click=_clear_session,
        accent=Color.log.muted,
    )
    clear_btn.visible = False

    empty_state = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.TERMINAL_OUTLINED,
                    size=IconSize.hero,
                    color=ft.Colors.OUTLINE_VARIANT,
                ),
                ft.Text(
                    "Descreva o que quer fazer",
                    size=Type.heading.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Vou gerar o comando exato da CLI do mill.tools — revise e copie, "
                    "nada roda sozinho.",
                    size=Type.input.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                    text_align=ft.TextAlign.CENTER,
                    no_wrap=False,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=Space.sm,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )

    session_list = ft.ListView(expand=True, spacing=Space.md, auto_scroll=True)
    session_area = ft.Stack([session_list, empty_state], expand=True)

    return CommandView(
        clear_btn=clear_btn,
        session_area=session_area,
        ask=ask,
        handle_command_done=handle_command_done,
    )
