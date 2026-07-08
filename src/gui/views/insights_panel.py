"""Textual insights panel (Plan 4B) — keyphrases, summary and entities.

Shown as an extra tab in the result view: it reads the produced transcription
once and renders YAKE keyphrases, a TextRank extractive summary and spaCy named
entities. Each engine is gated independently — a missing ``[nlp]`` extra or spaCy
model shows a setup hint for that field instead of breaking the panel.

The work runs off the UI thread (``page.run_task`` + ``asyncio.to_thread``) and
only the first time the tab is opened (``ensure_loaded``), so building the result
view stays instant. The engines themselves live in ``core/text`` (Plan 4B
commits 2/3); this is pure presentation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.gui.theme.components import helper_text, section_label
from src.gui.theme.tokens import Color, Radius, Space, Type


@dataclass
class _Insights:
    """Computed insights; ``None`` for an engine that is unavailable."""

    keywords: list[tuple[str, float]] | None
    summary: list[str] | None
    entities: list[tuple[str, str]] | None
    # Specific setup hint when entities is None — distinguishes "the [nlp]
    # extra itself is missing" from "spaCy is there but this language's model
    # isn't" (entities.availability()); irrelevant when entities has a value.
    entities_hint: str | None = None


def _compute(path: str) -> _Insights:
    """Read the document, clean it once, and run the three engines off-thread
    (gated each) on the same cleaned text — including entities()/detect_lang,
    which don't clean on their own: this panel wants a consistent view across
    all three sections, not just the page-marker/front-matter fix that
    summarize/keywords already apply internally regardless of caller."""
    from src.core.text import entities as ner
    from src.core.text import keywords, summarize
    from src.core.text.clean import clean_document_text
    from src.core.text.lang import detect_lang
    from src.core.text.reader import read_document_text

    text = clean_document_text(read_document_text(path))
    lang = detect_lang(text)
    entities_hint = ner.availability(lang)
    return _Insights(
        keywords=(
            keywords.keyphrases(text, lang=lang, top_n=10)
            if keywords.is_available()
            else None
        ),
        summary=(
            summarize.extractive_summary(text, sentences=5)
            if summarize.is_available()
            else None
        ),
        entities=ner.entities(text, lang=lang) if entities_hint is None else None,
        entities_hint=entities_hint,
    )


def _chip(text: str, accent: str) -> ft.Container:
    """A small pill used for keyphrases and entity values."""
    return ft.Container(
        content=ft.Text(text, size=Type.small.size, color=accent),
        bgcolor=ft.Colors.with_opacity(0.12, accent),
        border_radius=Radius.pill,
        padding=ft.Padding(left=Space.xs, right=Space.xs, top=2, bottom=2),
    )


def build_insights_panel(
    page: ft.Page, path: Path | None
) -> tuple[ft.Control, Callable[[], None]]:
    """Build the insights panel and a one-shot ``ensure_loaded`` trigger."""
    body = ft.Column(spacing=Space.lg, scroll=ft.ScrollMode.AUTO, expand=True)
    status = ft.Text(
        "Carregando insights…", size=Type.input.size, color=ft.Colors.ON_SURFACE_VARIANT
    )
    body.controls.append(status)
    loaded = [False]

    def _render(data: _Insights) -> None:
        body.controls.clear()

        # --- Keyphrases ---
        body.controls.append(section_label("Palavras-chave"))
        if data.keywords is None:
            body.controls.append(
                helper_text("Instale o extra de NLP para extrair palavras-chave.")
            )
        elif not data.keywords:
            body.controls.append(helper_text("Nenhuma palavra-chave relevante."))
        else:
            body.controls.append(
                ft.Row(
                    controls=[_chip(p, Color.log.work) for p, _ in data.keywords],
                    wrap=True,
                    spacing=Space.xs,
                    run_spacing=Space.xs,
                )
            )

        # --- Summary ---
        body.controls.append(section_label("Resumo"))
        if data.summary is None:
            body.controls.append(helper_text("Instale o extra de ML para o resumo."))
        elif not data.summary:
            body.controls.append(helper_text("Texto curto demais para resumir."))
        else:
            body.controls.append(
                ft.Column(
                    controls=[
                        ft.Text(
                            f"• {s}", size=Type.body.size, color=ft.Colors.ON_SURFACE
                        )
                        for s in data.summary
                    ],
                    spacing=Space.xs,
                )
            )

        # --- Entities ---
        body.controls.append(section_label("Entidades"))
        if data.entities is None:
            body.controls.append(helper_text(data.entities_hint))
        elif not data.entities:
            body.controls.append(helper_text("Nenhuma entidade encontrada."))
        else:
            by_label: dict[str, list[str]] = {}
            for text, label in data.entities:
                by_label.setdefault(label, []).append(text)
            for label in sorted(by_label):
                body.controls.append(
                    ft.Row(
                        controls=[
                            ft.Text(
                                label,
                                size=Type.small.size,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            *[_chip(v, Color.log.info) for v in by_label[label]],
                        ],
                        wrap=True,
                        spacing=Space.xs,
                        run_spacing=Space.xs,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )

        try:
            page.update()
        except Exception:
            pass

    def _ensure_loaded() -> None:
        if loaded[0] or path is None:
            return
        loaded[0] = True

        async def _run() -> None:
            try:
                data = await asyncio.to_thread(_compute, str(path))
            except Exception as exc:  # noqa: BLE001 — surface, never crash the view
                logging.debug("[d] Insights computation failed: %s", exc)
                status.value = "Não foi possível gerar os insights deste documento."
                try:
                    page.update()
                except Exception:
                    pass
                return
            _render(data)

        try:
            page.run_task(_run)
        except Exception as exc:
            logging.debug("[d] Could not schedule insights: %s", exc)

    return body, _ensure_loaded
