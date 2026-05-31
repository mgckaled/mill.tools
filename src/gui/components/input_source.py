"""Componente de entrada de itens: URL + seletor de arquivos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft


@dataclass
class InputItem:
    """Representa um item de entrada: URL ou arquivo local."""

    kind: str   # "url" | "local"
    value: str  # URL completa ou caminho absoluto


@dataclass
class InputSource:
    """Componente de entrada com suporte a URL e seleção de arquivos."""

    control: ft.Control
    get_items: Callable[[], list[InputItem]]
    clear: Callable[[], None]
    set_enabled: Callable[[bool], None]
    add_item: Callable[[InputItem], None]


def build_input_source(
    page: ft.Page,
    allowed_extensions: list[str],
    on_change: Callable[[list[InputItem]], None] | None = None,
) -> InputSource:
    """Constrói o componente InputSource.

    Combina campo de URL com botão Adicionar e seletor de arquivos (FilePicker).
    Exibe lista de itens adicionados com botão de remoção individual.

    Args:
        page: Página Flet (necessário para FilePicker no overlay).
        allowed_extensions: Extensões permitidas no FilePicker (sem ponto).
        on_change: Chamado com lista atualizada a cada add/remove.
    """
    items: list[InputItem] = []

    # ── widgets ──────────────────────────────────────────────────────────────

    url_field = ft.TextField(
        hint_text="URL (YouTube, SoundCloud…)",
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.BLUE_400,
        text_size=13,
        expand=True,
        height=42,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
    )

    items_col = ft.Column(controls=[], spacing=2)

    items_border = ft.Container(
        content=items_col,
        padding=ft.Padding(left=4, right=4, top=4, bottom=4),
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        ),
        border_radius=4,
        visible=False,
    )

    # ── FilePicker ───────────────────────────────────────────────────────────
    # Flet 0.85: FilePicker é um Service com pick_files() async (sem on_result).
    # Deve ser registrado em page.services, não em page.overlay.

    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    # ── lógica ───────────────────────────────────────────────────────────────

    def _notify() -> None:
        items_border.visible = len(items) > 0
        if on_change:
            on_change(list(items))

    def _make_item_row(item: InputItem) -> ft.Row:
        is_local = item.kind == "local"
        label = Path(item.value).name if is_local else item.value
        icon = ft.Icons.AUDIO_FILE_OUTLINED if is_local else ft.Icons.LINK

        def _remove(_e) -> None:
            if item in items:
                items.remove(item)
            items_col.controls[:] = [_make_item_row(i) for i in items]
            items_col.update()
            _notify()

        return ft.Row(
            controls=[
                ft.Icon(icon, size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(
                    label,
                    size=12,
                    color=ft.Colors.ON_SURFACE,
                    expand=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    no_wrap=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_size=14,
                    icon_color=ft.Colors.ON_SURFACE_VARIANT,
                    style=ft.ButtonStyle(
                        padding=ft.Padding(left=2, right=2, top=2, bottom=2),
                    ),
                    on_click=_remove,
                ),
            ],
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _add_item(item: InputItem) -> None:
        if any(i.value == item.value for i in items):
            return
        items.append(item)
        items_col.controls.append(_make_item_row(item))
        if items_col.page:
            items_col.update()
        _notify()

    def _add_url() -> None:
        raw = (url_field.value or "").strip()
        if raw:
            _add_item(InputItem(kind="url", value=raw))
            url_field.value = ""
            if url_field.page:
                url_field.update()

    url_field.on_submit = lambda _: _add_url()

    # ── botões ───────────────────────────────────────────────────────────────

    add_btn = ft.IconButton(
        icon=ft.Icons.ADD_CIRCLE_OUTLINE,
        tooltip="Adicionar URL",
        on_click=lambda _: _add_url(),
    )

    async def _on_pick_click(_e) -> None:
        files = await file_picker.pick_files(
            allow_multiple=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=allowed_extensions,
        )
        if files:
            for f in files:
                if f.path:
                    _add_item(InputItem(kind="local", value=f.path))

    pick_btn = ft.OutlinedButton(
        "Selecionar arquivos",
        icon=ft.Icons.FOLDER_OPEN_OUTLINED,
        on_click=_on_pick_click,
    )

    # ── layout raiz ──────────────────────────────────────────────────────────

    control = ft.Column(
        controls=[
            ft.Row(
                controls=[url_field, add_btn],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            pick_btn,
            items_border,
        ],
        spacing=6,
    )

    # ── API pública ───────────────────────────────────────────────────────────

    def _get_items() -> list[InputItem]:
        return list(items)

    def _clear() -> None:
        items.clear()
        items_col.controls.clear()
        items_border.visible = False
        if on_change:
            on_change([])

    def _set_enabled(enabled: bool) -> None:
        url_field.disabled = not enabled
        add_btn.disabled = not enabled
        pick_btn.disabled = not enabled
        for row in list(items_col.controls):
            if isinstance(row, ft.Row):
                for child in row.controls:
                    if isinstance(child, ft.IconButton):
                        child.disabled = not enabled

    return InputSource(
        control=control,
        get_items=_get_items,
        clear=_clear,
        set_enabled=_set_enabled,
        add_item=_add_item,
    )
