"""Form panel for the AI module: mode toggle, scope, model, question, Ask button.

Pure UI construction — no worker/threading here. The view wires `on_ask` and
`on_mode_change`, and reads the getters; `bind_document` is called by the
Library bridge so a single document can be the conversation scope.

Fase 3 (PLANO_NL2CLI_HUB_IA.md) adds the "Corpus | Comandos CLI" toggle: in
CLI mode the scope/prompt-chip controls (RAG-only) are disabled and the
question field's hint changes — the panel (view.py) swaps which session area
is visible via `on_mode_change`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.rag.embedder import SETUP_HINT
from src.core.rag.templates import load_templates
from src.gui import settings
from src.llm_factory import OLLAMA_SETUP_HINT, is_cloud_model
from src.gui.theme.components import (
    Cursor,
    help_icon_for,
    primary_button,
    section_label,
    segmented_selector,
)
from src.gui.theme.tokens import IconSize, Radius, Space, Type

_SCOPE_OPTIONS = ["all", "transcription", "document", "image"]
_SCOPE_LABELS = {
    "all": "Tudo",
    "transcription": "Transcrições",
    "document": "Documentos",
    "image": "Imagens",
}
_MODE_OPTIONS = ["corpus", "cli"]
_MODE_LABELS = {"corpus": "Corpus", "cli": "Comandos CLI"}
# Answer models, recommended first: gemma3-4b is the quality/speed sweet spot for
# RAG synthesis + citation on this CPU; gemma3-1b is the fast/low-RAM fallback;
# qwen7b is slowest/heaviest (but the most reliable at strict-JSON/flag formatting,
# so it doubles as the "Comandos CLI" default); gemini/glm are the cloud opt-ins.
_MODELS = [
    "gemma3-4b-custom",
    "gemma3-1b-custom",
    "qwen7b-custom",
    "gemini-2.5-flash",
    "glm-4.7-flash",
]
_QUESTION_HINT_CORPUS = "O que você quer saber sobre o seu acervo?"
_QUESTION_HINT_CLI = (
    "Descreva o que quer fazer (ex.: 'corta o silêncio do podcast.mp3')"
)


@dataclass
class AiForm:
    """Handles exposed by the form so the view can drive it."""

    control: ft.Control
    get_query: Callable[[], str]
    get_scope: Callable[[], str | None]
    get_model: Callable[[], str]
    get_mode: Callable[[], str]
    set_running: Callable[[bool], None]
    set_available: Callable[[bool], None]
    set_cli_available: Callable[[bool], None]
    bind_document: Callable[[str | None], None]
    clear_query: Callable[[], None]
    sync_mode_ui: Callable[[], None]


def _all_border(width: float, color: str) -> ft.Border:
    side = ft.BorderSide(width, color)
    return ft.Border(left=side, right=side, top=side, bottom=side)


def build_ai_form(
    page: ft.Page,
    *,
    on_ask: Callable[[], None],
    on_mode_change: Callable[[str], None] = lambda _mode: None,
) -> AiForm:
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

    # ── mode toggle (Corpus | Comandos CLI) ─────────────────────────────────
    mode_grid, get_mode, _set_mode_disabled = segmented_selector(
        options=_MODE_OPTIONS,
        value=cfg.get("last_ai_mode", "corpus"),
        page=page,
        on_change=lambda v: _on_mode_change(v),
        columns=2,
        labels=_MODE_LABELS,
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

    def _sync_scope_disabled() -> None:
        # A bound document (Library bridge) or CLI mode both override the
        # kind-scope grid — either condition disables it.
        set_scope_disabled(get_mode() == "cli" or bool(_bound_doc[0]))
        _safe_update(scope_grid)

    def _clear_doc(_e=None) -> None:
        _bound_doc[0] = None
        doc_chip.visible = False
        _sync_scope_disabled()
        _safe_update(doc_chip)

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
                ft.Icon(
                    ft.Icons.ARTICLE_OUTLINED, size=IconSize.md, color=ft.Colors.PRIMARY
                ),
                ft.Text(
                    "Este documento:",
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                doc_name,
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_size=IconSize.sm,
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
        _sync_scope_disabled()
        _safe_update(doc_chip)

    def get_scope() -> str | None:
        if _bound_doc[0]:
            return _bound_doc[0]
        value = get_scope_value()
        return None if value == "all" else value

    # ── answer/command model + cloud privacy note ───────────────────────────
    cloud_warning = ft.Container(
        visible=is_cloud_model(cfg.get("last_ai_model", "gemma3-4b-custom")),
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
                    "Com modelos em nuvem (Gemini/GLM), os trechos recuperados são "
                    "enviados a um provedor externo no passo de resposta. Os "
                    "embeddings continuam locais.",
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

    def _sync_cloud_warning() -> None:
        # The privacy note is about RAG chunks leaving the machine — it does
        # not apply to CLI-command generation (no retrieval happens there).
        cloud_warning.visible = get_mode() == "corpus" and is_cloud_model(
            model_dd.value or "gemma3-4b-custom"
        )
        _safe_update(cloud_warning)

    def _on_model_select(e: ft.ControlEvent) -> None:
        value = e.control.value or "gemma3-4b-custom"
        settings.set("last_ai_model", value)
        _sync_cloud_warning()

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
        hint_text=_QUESTION_HINT_CORPUS,
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
    # RAG-only — instructions like "resuma isso" do not apply to CLI generation.
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
    prompt_section_label = section_label("Modelos de prompt")

    ask_btn = primary_button(
        "Perguntar",
        icon=ft.Icons.SEND_OUTLINED,
        on_click=lambda _e: on_ask(),
    )

    def _unavailable_banner(message: str) -> ft.Container:
        return ft.Container(
            visible=False,
            bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.ERROR),
            border_radius=Radius.sm,
            padding=ft.Padding(
                left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
            ),
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.WARNING_AMBER_OUTLINED,
                        size=IconSize.md,
                        color=ft.Colors.ERROR,
                    ),
                    ft.Text(
                        message,
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

    unavailable = _unavailable_banner(
        f"Ollama / nomic-embed-custom indisponível. Rode: {SETUP_HINT}"
    )
    unavailable_cli = _unavailable_banner(
        f"Ollama indisponível. Rode: {OLLAMA_SETUP_HINT}"
    )

    _availability = {"corpus": True, "cli": True}

    def _refresh_gate() -> None:
        mode = get_mode()
        unavailable.visible = mode == "corpus" and not _availability["corpus"]
        unavailable_cli.visible = mode == "cli" and not _availability["cli"]
        ask_btn.disabled = not _availability[mode]
        _safe_update(unavailable, unavailable_cli, ask_btn)

    def set_running(running: bool) -> None:
        ask_btn.disabled = running
        _safe_update(ask_btn)

    def set_available(available: bool) -> None:
        _availability["corpus"] = available
        _refresh_gate()

    def set_cli_available(available: bool) -> None:
        _availability["cli"] = available
        _refresh_gate()

    def _apply_mode_ui(mode: str) -> None:
        """Sync the form's own mode-dependent widgets (no external callback).

        Split from ``_on_mode_change`` so ``sync_mode_ui`` can re-run this at
        mount time (restoring a persisted mode) without re-firing
        ``on_mode_change`` — at that point in ``build_ai_form`` the view's own
        callback may still be a placeholder closure over objects that do not
        exist yet (``answer``/``command_view`` are built after ``form``).
        """
        is_cli = mode == "cli"
        question.hint_text = _QUESTION_HINT_CLI if is_cli else _QUESTION_HINT_CORPUS
        prompt_chips.visible = not is_cli
        prompt_section_label.visible = not is_cli
        _sync_scope_disabled()
        _sync_cloud_warning()
        _refresh_gate()
        _safe_update(question, prompt_chips, prompt_section_label)

    def _on_mode_change(mode: str) -> None:
        settings.set("last_ai_mode", mode)
        _apply_mode_ui(mode)
        on_mode_change(mode)

    def sync_mode_ui() -> None:
        _apply_mode_ui(get_mode())

    # ── assemble ──────────────────────────────────────────────────────────
    body = ft.Column(
        controls=[
            header,
            mode_grid,
            unavailable,
            unavailable_cli,
            section_label("Escopo"),
            scope_grid,
            doc_chip,
            section_label("Resposta"),
            model_dd,
            cloud_warning,
            prompt_section_label,
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
        get_mode=get_mode,
        set_running=set_running,
        set_available=set_available,
        set_cli_available=set_cli_available,
        bind_document=bind_document,
        clear_query=clear_query,
        sync_mode_ui=sync_mode_ui,
    )
