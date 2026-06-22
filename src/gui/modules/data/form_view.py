"""Form panel for the Data module: source files, mode toggle, query box.

Pure UI construction — no worker/threading here. The view wires the callbacks
(``on_pick`` to scan added files, ``on_preview``/``on_run`` to drive the query)
and reads the getters. Source chips show each file's row/column counts and its
column names (as a tooltip), so the user — and the IA — know the schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.data.scanner import SUPPORTED_EXTS
from src.gui import settings
from src.gui.theme.components import (
    Cursor,
    help_icon_for,
    primary_button,
    secondary_button,
    section_label,
)
from src.gui.theme.tokens import IconSize, Radius, Space, Type

# NL→SQL models, recommended first: gemma3-4b is the quality/speed sweet spot on
# this CPU; qwen7b is heavier/slower; gemini is the cloud opt-in (schema only).
_MODELS = ["gemma3-4b-custom", "qwen7b-custom", "gemini-2.5-flash"]

# Picker extensions are the supported exts without the leading dot.
_ALLOWED_EXTS = sorted(e.lstrip(".") for e in SUPPORTED_EXTS)


@dataclass
class DataForm:
    """Handles exposed by the form so the view can drive it."""

    control: ft.Control
    get_text: Callable[[], str]
    get_mode: Callable[[], str]  # "pt" | "sql"
    get_model: Callable[[], str]
    set_files: Callable[[list], None]  # list[DataFile] → render chips
    get_files: Callable[[], list]
    set_running: Callable[[bool], None]
    set_text: Callable[[str], None]


def _is_gemini(model: str) -> bool:
    return model.lower().startswith("gemini")


def build_data_form(
    page: ft.Page,
    *,
    on_pick: Callable[[list[Path]], None],
    on_preview: Callable[[], None],
    on_run: Callable[[], None],
) -> DataForm:
    """Build the left form panel and return its handles."""
    cfg = settings.load()
    _files: list = []

    def _safe_update(*controls: ft.Control) -> None:
        for c in controls:
            try:
                c.update()
            except Exception:
                pass

    # ── header ────────────────────────────────────────────────────────────
    header_controls: list[ft.Control] = [
        ft.Icon(ft.Icons.TABLE_CHART_OUTLINED, color=ft.Colors.PRIMARY),
        ft.Text(
            "Dados",
            size=Type.title.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
    ]
    _help = help_icon_for("data", page)
    if _help is not None:
        header_controls.extend([ft.Container(expand=True), _help])
    header = ft.Row(
        header_controls,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=Space.sm,
    )

    # ── source files (FilePicker → chips with counts) ─────────────────────
    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    chips_col = ft.Column(controls=[], spacing=Space.xxs)

    async def _on_pick_click(_e) -> None:
        picked = await file_picker.pick_files(
            allow_multiple=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=list(_ALLOWED_EXTS),
        )
        if picked:
            on_pick([Path(f.path) for f in picked if f.path])

    pick_btn = secondary_button(
        "Selecionar arquivos", icon=ft.Icons.FOLDER_OPEN_OUTLINED
    )
    pick_btn.on_click = _on_pick_click

    def _chip(file) -> ft.Control:
        cols = ", ".join(c.name for c in file.columns)

        def _remove(_e, _f=file) -> None:
            _files[:] = [f for f in _files if f is not _f]
            _render_chips()

        return ft.Container(
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            border_radius=Radius.sm,
            padding=ft.Padding(
                left=Space.sm, right=Space.xs, top=Space.xs, bottom=Space.xs
            ),
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.INSERT_DRIVE_FILE_OUTLINED,
                        size=IconSize.md,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                file.path.name,
                                size=Type.input.size,
                                color=ft.Colors.ON_SURFACE,
                                no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                tooltip=f"Colunas: {cols}",
                            ),
                            ft.Text(
                                f"{file.n_rows} linhas · {file.n_cols} colunas · {file.view_name}",
                                size=Type.small.size,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=IconSize.sm,
                        tooltip="Remover",
                        on_click=_remove,
                        style=ft.ButtonStyle(mouse_cursor=Cursor.interactive),
                    ),
                ],
                spacing=Space.xs,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _render_chips() -> None:
        chips_col.controls[:] = [_chip(f) for f in _files]
        _safe_update(chips_col)

    def set_files(files: list) -> None:
        # Merge new files, de-duplicating by path (re-adding a file re-scans it).
        by_path = {str(f.path): f for f in _files}
        for f in files:
            by_path[str(f.path)] = f
        _files[:] = list(by_path.values())
        _render_chips()

    def get_files() -> list:
        return list(_files)

    # ── mode toggle (Português | Consulta) ────────────────────────────────
    _mode: list[str] = [cfg.get("last_data_mode", "pt")]

    def _mode_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_pt = ft.TextButton("Português", icon=ft.Icons.TRANSLATE_OUTLINED)
    tab_sql = ft.TextButton("Consulta", icon=ft.Icons.CODE)

    def _apply_mode() -> None:
        is_pt = _mode[0] == "pt"
        tab_pt.style = _mode_style(is_pt)
        tab_sql.style = _mode_style(not is_pt)
        query_box.label = "Pergunta em português" if is_pt else "Consulta SQL (SELECT)"
        query_box.hint_text = (
            "Ex.: total de vendas por produto, do maior para o menor"
            if is_pt
            else "SELECT ... FROM tabela ..."
        )
        model_dd.visible = is_pt  # the model only matters when translating
        preview_btn.visible = is_pt  # SQL mode runs directly
        _safe_update(tab_pt, tab_sql, query_box, model_dd, preview_btn)

    def _set_mode(mode: str) -> None:
        _mode[0] = mode
        settings.set("last_data_mode", mode)
        _apply_mode()

    tab_pt.on_click = lambda _e: _set_mode("pt")
    tab_sql.on_click = lambda _e: _set_mode("sql")

    # ── query box + model ─────────────────────────────────────────────────
    query_box = ft.TextField(
        label="Pergunta em português",
        multiline=True,
        min_lines=3,
        max_lines=8,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def get_text() -> str:
        return (query_box.value or "").strip()

    def set_text(value: str) -> None:
        query_box.value = value
        _safe_update(query_box)

    gemini_note = ft.Container(
        visible=_is_gemini(cfg.get("last_data_model", "gemma3-4b-custom")),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        border_radius=Radius.sm,
        padding=ft.Padding(
            left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
        ),
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.CLOUD_OUTLINED, size=IconSize.md, color=ft.Colors.PRIMARY
                ),
                ft.Text(
                    "Com Gemini, só os nomes de coluna saem da máquina. O conteúdo "
                    "das tabelas fica 100% local no DuckDB.",
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    expand=True,
                    no_wrap=False,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    def _on_model_select(e: ft.ControlEvent) -> None:
        value = e.control.value or "gemma3-4b-custom"
        settings.set("last_data_model", value)
        gemini_note.visible = _is_gemini(value)
        _safe_update(gemini_note)

    model_dd = ft.Dropdown(
        label="Modelo da tradução PT→SQL",
        value=cfg.get("last_data_model", "gemma3-4b-custom"),
        options=[ft.dropdown.Option(m) for m in _MODELS],
        on_select=_on_model_select,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def get_mode() -> str:
        return _mode[0]

    def get_model() -> str:
        return model_dd.value or "gemma3-4b-custom"

    # ── action buttons ────────────────────────────────────────────────────
    preview_btn = primary_button(
        "Pré-visualizar",
        icon=ft.Icons.VISIBILITY_OUTLINED,
        on_click=lambda _e: on_preview(),
    )
    run_btn = secondary_button("Executar", icon=ft.Icons.PLAY_ARROW_OUTLINED)
    run_btn.on_click = lambda _e: on_run()

    def set_running(running: bool) -> None:
        preview_btn.disabled = running
        run_btn.disabled = running
        pick_btn.disabled = running
        _safe_update(preview_btn, run_btn, pick_btn)

    _apply_mode()

    # ── assemble ──────────────────────────────────────────────────────────
    body = ft.Column(
        controls=[
            header,
            section_label("Fontes"),
            pick_btn,
            chips_col,
            section_label("Consulta"),
            ft.Row([tab_pt, tab_sql], spacing=Space.xs),
            model_dd,
            gemini_note,
            query_box,
            ft.Row([preview_btn, run_btn], spacing=Space.sm),
        ],
        spacing=Space.md,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    control = ft.Container(
        content=body,
        padding=ft.Padding(
            left=Space.md, right=Space.md, top=Space.md, bottom=Space.md
        ),
        expand=True,
    )

    return DataForm(
        control=control,
        get_text=get_text,
        get_mode=get_mode,
        get_model=get_model,
        set_files=set_files,
        get_files=get_files,
        set_running=set_running,
        set_text=set_text,
    )
