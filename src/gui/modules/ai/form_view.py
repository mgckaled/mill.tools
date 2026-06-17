"""Form panel for the AI module: scope, answer model, question and Ask button.

Pure UI construction — no worker/threading here. The view wires `on_ask` and
reads the getters; `bind_document` is called by the Library bridge so a single
document can be the conversation scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.rag.embedder import SETUP_HINT
from src.core.rag.templates import load_templates
from src.gui import settings
from src.gui.theme.components import (
    Cursor,
    help_icon_for,
    primary_button,
    section_label,
    segmented_selector,
)
from src.gui.theme.tokens import Radius, Space, Type

_SCOPE_OPTIONS = ["all", "transcription", "document", "image"]
_SCOPE_LABELS = {
    "all": "Tudo",
    "transcription": "Transcrições",
    "document": "Documentos",
    "image": "Imagens",
}
# Answer models, recommended first: gemma3-4b is the quality/speed sweet spot for
# RAG synthesis + citation on this CPU; gemma3-1b is the fast/low-RAM fallback;
# qwen7b is slowest/heaviest; gemini is the cloud opt-in.
_MODELS = [
    "gemma3-4b-custom",
    "gemma3-1b-custom",
    "qwen7b-custom",
    "gemini-2.5-flash",
]


@dataclass
class AiForm:
    """Handles exposed by the form so the view can drive it."""

    control: ft.Control
    get_query: Callable[[], str]
    get_scope: Callable[[], str | None]
    get_model: Callable[[], str]
    set_running: Callable[[bool], None]
    set_available: Callable[[bool], None]
    bind_document: Callable[[str | None], None]
    clear_query: Callable[[], None]


def _is_gemini(model: str) -> bool:
    return model.lower().startswith("gemini")


def _all_border(width: float, color: str) -> ft.Border:
    side = ft.BorderSide(width, color)
    return ft.Border(left=side, right=side, top=side, bottom=side)


def build_ai_form(page: ft.Page, *, on_ask: Callable[[], None]) -> AiForm:
    """Build the left form panel and return its handles."""
    cfg = settings.load()
    _bound_doc: list[str | None] = [None]

    def _safe_update(*controls: ft.Control) -> None:
        for c in controls:
            try:
                c.update()
            except Exception:
                pass

    # ── header ────────────────────────────────────────────────────────────
    header_controls: list[ft.Control] = [
        ft.Icon(ft.Icons.AUTO_AWESOME_OUTLINED, color=ft.Colors.PRIMARY),
        ft.Text(
            "IA",
            size=Type.title.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
    ]
    _help = help_icon_for("ai", page)
    if _help is not None:
        header_controls.extend([ft.Container(expand=True), _help])
    header = ft.Row(
        header_controls,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=Space.sm,
    )

    # ── scope ─────────────────────────────────────────────────────────────
    scope_grid, get_scope_value, set_scope_disabled = segmented_selector(
        options=_SCOPE_OPTIONS,
        value=cfg.get("last_ai_scope", "all"),
        page=page,
        on_change=lambda v: settings.set("last_ai_scope", v),
        columns=2,
        labels=_SCOPE_LABELS,
    )

    doc_name = ft.Text(
        "",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        expand=True,
    )

    def _clear_doc(_e=None) -> None:
        _bound_doc[0] = None
        doc_chip.visible = False
        set_scope_disabled(False)
        _safe_update(doc_chip, scope_grid)

    doc_chip = ft.Container(
        visible=False,
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
        border=_all_border(1, ft.Colors.with_opacity(0.4, ft.Colors.PRIMARY)),
        border_radius=Radius.sm,
        padding=ft.Padding(
            left=Space.sm, right=Space.xs, top=Space.xs, bottom=Space.xs
        ),
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.ARTICLE_OUTLINED, size=16, color=ft.Colors.PRIMARY),
                ft.Text(
                    "Este documento:",
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                doc_name,
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_size=14,
                    tooltip="Limpar — voltar ao acervo",
                    on_click=_clear_doc,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    def bind_document(path: str | None) -> None:
        if not path:
            _clear_doc()
            return
        _bound_doc[0] = str(path)
        doc_name.value = Path(path).name
        doc_chip.visible = True
        set_scope_disabled(True)  # a bound document overrides the kind scope
        _safe_update(doc_chip, scope_grid)

    def get_scope() -> str | None:
        if _bound_doc[0]:
            return _bound_doc[0]
        value = get_scope_value()
        return None if value == "all" else value

    # ── answer model + Gemini privacy note ────────────────────────────────
    gemini_warning = ft.Container(
        visible=_is_gemini(cfg.get("last_ai_model", "gemma3-4b-custom")),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        border_radius=Radius.sm,
        padding=ft.Padding(
            left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
        ),
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.CLOUD_OUTLINED, size=16, color=ft.Colors.PRIMARY),
                ft.Text(
                    "Com Gemini, os trechos recuperados são enviados à nuvem no "
                    "passo de resposta. Os embeddings continuam locais.",
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
        settings.set("last_ai_model", value)
        gemini_warning.visible = _is_gemini(value)
        _safe_update(gemini_warning)

    model_dd = ft.Dropdown(
        label="Modelo da resposta",
        value=cfg.get("last_ai_model", "gemma3-4b-custom"),
        options=[ft.dropdown.Option(m) for m in _MODELS],
        on_select=_on_model_select,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def get_model() -> str:
        return model_dd.value or "gemma3-4b-custom"

    # ── question + ask ────────────────────────────────────────────────────
    question = ft.TextField(
        label="Pergunta",
        hint_text="O que você quer saber sobre o seu acervo?",
        multiline=True,
        min_lines=3,
        max_lines=6,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def get_query() -> str:
        return (question.value or "").strip()

    def clear_query() -> None:
        question.value = ""
        _safe_update(question)

    # ── prompt library (chips that fill the question field) ───────────────
    def _fill_question(instruction: str) -> None:
        question.value = instruction
        _safe_update(question)

    def _chip(label: str, instruction: str, *, structured: bool) -> ft.Control:
        return ft.OutlinedButton(
            label,  # label is positional in Flet 0.85 (no `text=` kwarg)
            icon=ft.Icons.DASHBOARD_CUSTOMIZE_OUTLINED
            if structured
            else ft.Icons.BOLT_OUTLINED,
            on_click=lambda _e, _i=instruction: _fill_question(_i),
            style=ft.ButtonStyle(mouse_cursor=Cursor.interactive),
        )

    prompt_chips = ft.Row(
        controls=[
            _chip(t.label, t.instruction, structured=t.category == "template")
            for t in load_templates()
        ],
        wrap=True,
        spacing=Space.xs,
        run_spacing=Space.xs,
    )

    ask_btn = primary_button(
        "Perguntar",
        icon=ft.Icons.SEND_OUTLINED,
        on_click=lambda _e: on_ask(),
    )

    unavailable = ft.Container(
        visible=False,
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.ERROR),
        border_radius=Radius.sm,
        padding=ft.Padding(
            left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
        ),
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.WARNING_AMBER_OUTLINED, size=16, color=ft.Colors.ERROR
                ),
                ft.Text(
                    f"Ollama / nomic-embed-custom indisponível. Rode: {SETUP_HINT}",
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

    def set_running(running: bool) -> None:
        ask_btn.disabled = running
        _safe_update(ask_btn)

    def set_available(available: bool) -> None:
        unavailable.visible = not available
        ask_btn.disabled = not available
        _safe_update(unavailable, ask_btn)

    # ── assemble ──────────────────────────────────────────────────────────
    body = ft.Column(
        controls=[
            header,
            unavailable,
            section_label("Escopo"),
            scope_grid,
            doc_chip,
            section_label("Resposta"),
            model_dd,
            gemini_warning,
            section_label("Modelos de prompt"),
            prompt_chips,
            question,
            ask_btn,
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

    return AiForm(
        control=control,
        get_query=get_query,
        get_scope=get_scope,
        get_model=get_model,
        set_running=set_running,
        set_available=set_available,
        bind_document=bind_document,
        clear_query=clear_query,
    )
