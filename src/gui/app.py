"""Layout raiz do mill.tools — NavigationRail + sistema de módulos."""

from __future__ import annotations

import asyncio
import threading

import flet as ft
from flet.controls.core.stack import StackFit

from src.gui import settings
from src.gui.events import EventBus, PipelineEvent
from src.gui.home import show_home
from src.gui.splash import show_splash
from src.gui.theme import sync_page_bgcolor
from src.gui.theme.components import Cursor
from src.gui.theme.tokens import Motion, Space, Type
from src.gui.modules.audio.view import build_audio_module
from src.gui.modules.base import Module
from src.gui.modules.document.view import build_document_module
from src.gui.modules.image.view import build_image_module
from src.gui.modules.library.view import build_library_module
from src.gui.modules.transcription.view import (
    build_transcription_module,
    get_form_start_button,
)
from src.gui.modules.video.view import build_video_module


def build_app(page: ft.Page, initial_module: str = "transcription") -> None:
    """Monta o layout raiz: NavigationRail + Stack de módulos.

    Todos os módulos são montados simultaneamente num ft.Stack; navigate_to
    alterna visible= em vez de reatribuir content — evita object_patch IndexError
    do Flet 0.85 que forçou o abandono de ft.Tabs.
    """
    page.pubsub.unsubscribe_all()
    cfg = settings.load()
    page.theme_mode = (
        ft.ThemeMode.DARK
        if cfg.get("theme_mode", "dark") == "dark"
        else ft.ThemeMode.LIGHT
    )
    sync_page_bgcolor(page)  # re-sincroniza após ler o tema salvo

    cancel_event = threading.Event()
    bus = EventBus(page)
    pipeline_running: list[bool] = [False]

    # ------------------------------------------------------------------
    # AppBar
    # ------------------------------------------------------------------

    def _go_home(_e=None) -> None:
        if pipeline_running[0]:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Aguarde o pipeline terminar antes de navegar."),
                bgcolor=ft.Colors.ERROR,
            )
            page.snack_bar.open = True
            page.update()
            return
        page.appbar = None
        show_home(page, on_complete=lambda mid: build_app(page, initial_module=mid))

    def _go_splash(_e=None) -> None:
        if pipeline_running[0]:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Aguarde o pipeline terminar antes de navegar."),
                bgcolor=ft.Colors.ERROR,
            )
            page.snack_bar.open = True
            page.update()
            return
        page.appbar = None
        show_splash(
            page,
            on_complete=lambda: show_home(
                page,
                on_complete=lambda mid: build_app(page, initial_module=mid),
            ),
        )

    def _toggle_theme(_e) -> None:
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        sync_page_bgcolor(page)
        theme_btn.icon = ft.Icons.DARK_MODE if is_dark else ft.Icons.LIGHT_MODE
        settings.set("theme_mode", "light" if is_dark else "dark")
        page.update()

    home_btn = ft.TextButton(
        "Home",
        icon=ft.Icons.HOME_OUTLINED,
        on_click=_go_home,
        style=ft.ButtonStyle(mouse_cursor=Cursor.interactive),
    )
    splash_btn = ft.TextButton(
        "Splash",
        icon=ft.Icons.SLIDESHOW,
        on_click=_go_splash,
        style=ft.ButtonStyle(mouse_cursor=Cursor.interactive),
    )
    theme_btn = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE
        if page.theme_mode == ft.ThemeMode.DARK
        else ft.Icons.DARK_MODE,
        tooltip="Alternar tema",
        on_click=_toggle_theme,
        style=ft.ButtonStyle(mouse_cursor=Cursor.interactive),
    )

    # Library is a hub over every module's output, not a peer tool — it lives in
    # the AppBar next to the wordmark instead of the NavigationRail. on_click is
    # wired after navigate_to is defined (forward reference, like nav).
    def _library_btn_style(active: bool) -> ft.ButtonStyle:
        c = ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT
        return ft.ButtonStyle(
            mouse_cursor=Cursor.interactive,
            color={
                ft.ControlState.DEFAULT: c,
                ft.ControlState.HOVERED: ft.Colors.PRIMARY,
            },
        )

    library_btn = ft.TextButton(
        "Biblioteca",
        icon=ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED,
        style=_library_btn_style(initial_module == "library"),
    )

    wordmark = ft.Text(
        spans=[
            ft.TextSpan(
                "mill",
                ft.TextStyle(
                    color=ft.Colors.ON_SURFACE,
                    size=Type.title.size,
                    weight=ft.FontWeight.W_600,
                ),
            ),
            ft.TextSpan(
                ".tools",
                ft.TextStyle(
                    color=ft.Colors.PRIMARY,
                    size=Type.title.size,
                    weight=ft.FontWeight.W_400,
                ),
            ),
        ]
    )

    page.appbar = ft.AppBar(
        title=ft.Row(
            controls=[wordmark, library_btn],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        center_title=False,
        actions=[home_btn, splash_btn, theme_btn],
    )

    # ------------------------------------------------------------------
    # Módulos
    # ------------------------------------------------------------------

    # nav é populado após navigate_to ser definido — forward reference
    # necessário porque MODULES depende dos módulos e navigate_to depende de MODULES.
    nav: list = []

    _transcription = build_transcription_module(
        page, bus, cancel_event, pipeline_running
    )
    _audio = build_audio_module(page, bus, cancel_event, pipeline_running, nav)
    _video = build_video_module(page, bus, cancel_event, pipeline_running, nav)
    _image = build_image_module(page, bus, cancel_event, pipeline_running)
    _document = build_document_module(page, bus, cancel_event, pipeline_running)
    _library = build_library_module(page, bus, cancel_event, pipeline_running, nav)

    # Library is appended last so the default initial_module ("transcription")
    # and the opening behavior are unchanged.
    MODULES: list[Module] = [
        _audio,
        _video,
        _image,
        _transcription,
        _document,
        _library,
    ]
    _DEFAULT_ID = initial_module

    # The rail shows only the processing tools; Library is reached from the
    # AppBar. It still lives in MODULES (and the Stack) so navigate_to works.
    _RAIL_MODULES: list[Module] = [m for m in MODULES if m.id != "library"]

    def _rail_index(module_id: str) -> int | None:
        return next((i for i, m in enumerate(_RAIL_MODULES) if m.id == module_id), None)

    current_idx: list[int] = [
        next(i for i, m in enumerate(MODULES) if m.id == _DEFAULT_ID)
    ]

    # ------------------------------------------------------------------
    # navigate_to — visibilidade em vez de reatribuição de content
    # ------------------------------------------------------------------

    def navigate_to(module_id: str, payload: dict | None = None) -> None:
        if pipeline_running[0]:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "Aguarde o pipeline terminar antes de trocar de módulo."
                ),
                bgcolor=ft.Colors.ERROR,
            )
            page.snack_bar.open = True
            rail.selected_index = _rail_index(MODULES[current_idx[0]].id)
            page.update()
            return

        idx = next(i for i, m in enumerate(MODULES) if m.id == module_id)
        MODULES[current_idx[0]].on_unmount()
        current_idx[0] = idx
        # Library has no rail destination → deselect the rail (selected_index
        # None) and highlight the AppBar button instead.
        rail.selected_index = _rail_index(module_id)
        library_btn.style = _library_btn_style(module_id == "library")
        for i, m in enumerate(MODULES):
            m.control.visible = i == idx
        MODULES[idx].on_mount(payload or {})
        page.update()

    nav.append(navigate_to)  # resolve a forward reference do módulo Áudio
    library_btn.on_click = lambda _e: navigate_to("library")

    def _on_rail_change(e: ft.ControlEvent) -> None:
        idx = e.control.selected_index
        navigate_to(_RAIL_MODULES[idx].id)

    # ------------------------------------------------------------------
    # NavigationRail
    # ------------------------------------------------------------------

    rail = ft.NavigationRail(
        selected_index=_rail_index(_DEFAULT_ID),
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=80,
        destinations=[
            ft.NavigationRailDestination(
                icon=m.icon,
                selected_icon=m.selected_icon,
                label=m.label,
            )
            for m in _RAIL_MODULES
        ],
        on_change=_on_rail_change,
    )

    rail_gd = ft.GestureDetector(
        content=rail,
        mouse_cursor=Cursor.interactive,
    )

    def _on_pipeline_cursor(event) -> None:
        if not isinstance(event, PipelineEvent):
            return
        if event.type not in ("progress_start", "task_done", "task_error"):
            return
        new = Cursor.forbidden if pipeline_running[0] else Cursor.interactive
        if rail_gd.mouse_cursor != new:
            rail_gd.mouse_cursor = new
            try:
                rail_gd.update()
            except RuntimeError:
                pass

    page.pubsub.subscribe(_on_pipeline_cursor)

    # ------------------------------------------------------------------
    # Stack — todos os módulos montados; só um visível por vez
    # ------------------------------------------------------------------

    for m in MODULES:
        m.control.visible = m.id == _DEFAULT_ID

    module_stack = ft.Stack(
        controls=[m.control for m in MODULES],
        expand=True,
        fit=StackFit.EXPAND,
    )

    # ------------------------------------------------------------------
    # Layout raiz
    # ------------------------------------------------------------------

    layout = ft.Row(
        controls=[
            rail_gd,
            ft.VerticalDivider(width=2, thickness=1.5, color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(content=module_stack, expand=True, bgcolor=ft.Colors.SURFACE),
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        opacity=0,
        animate_opacity=ft.Animation(Motion.slow, ft.AnimationCurve.EASE_OUT),
    )

    # ------------------------------------------------------------------
    # Atalhos de teclado (delegam para o módulo ativo)
    # ------------------------------------------------------------------

    def _on_keyboard(e: ft.KeyboardEvent) -> None:
        active_module = MODULES[current_idx[0]]
        if active_module.id != "transcription":
            return

        if e.ctrl and e.key == "Enter" and not pipeline_running[0]:
            btn = get_form_start_button(active_module.control)
            if btn and not btn.disabled and btn.on_click:
                btn.on_click(e)

        if e.key == "Escape" and pipeline_running[0]:
            cancel_event.set()

    page.on_keyboard_event = _on_keyboard

    # ------------------------------------------------------------------
    # Montar página
    # ------------------------------------------------------------------

    page.controls.clear()
    page.add(layout)
    page.update()

    async def _fade_in() -> None:
        await asyncio.sleep(0.05)
        layout.opacity = 1
        page.update()

    page.run_task(_fade_in)
