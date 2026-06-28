"""Analysis-profile section for the Transcription form — with 4B auto-suggestion.

Wraps the grouped profile selector and adds the Plan 4B behaviour: given a text
document already in the RAG index, ``suggest(path)`` classifies it (zero-shot
prototypes, upgraded by the supervised model when available) and **pre-selects**
the matching profile, showing a discreet chip ("Sugerido: Aula · 0,82"). A low
margin flips the chip to "incerto" — honest about uncertainty. The user's final
choice is captured as a gold label by the worker, not here.

The classification runs off the UI thread (``page.run_task`` + ``asyncio.to_thread``)
and is fully guarded: no index, an unresolved path or a missing embedder simply
leaves the selector untouched. Extracted from ``form_view`` (divide-se ao tocar).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.gui.components.profile_selector import build_profile_selector
from src.gui.theme.components import help_icon_for, section_label
from src.gui.theme.tokens import IconSize, Radius, Space, Type

# Below this top1−top2 margin the suggestion is shown as uncertain.
_LOW_MARGIN = 0.05


@dataclass
class ProfileSection:
    """Handle to the analysis-profile section."""

    control: ft.Control
    get_value: Callable[[], str]
    set_value: Callable[[str], None]
    set_visible: Callable[[bool], None]
    suggest: Callable[[str], None]


def _classify_path(path: str) -> tuple[str, float, float] | None:
    """Classify an indexed document → (profile_id, confidence, margin), off-thread.

    Returns ``None`` when the corpus is empty, the path is not (uniquely) in the
    index, or the embedder is needed but unavailable — any of which means "no
    suggestion", never an error.
    """
    from src.core.ml.classify import classify
    from src.core.ml.features import load_document_matrix
    from src.core.rag import embedder
    from src.core.rag.indexer import index_dir

    dm = load_document_matrix(index_dir())
    if len(dm) == 0:
        return None

    resolved = str(Path(path).resolve())
    if resolved in dm.source_paths:
        idx = dm.source_paths.index(resolved)
    else:
        name = Path(path).name
        matches = [j for j, sp in enumerate(dm.source_paths) if Path(sp).name == name]
        if len(matches) != 1:
            return None
        idx = matches[0]

    result = classify(
        dm.X[idx],
        embed_fn=lambda t: embedder.embed_texts(t, model=embedder.DEFAULT_EMBED_MODEL),
    )
    return result.profile_id, result.confidence, result.margin


def build_profile_section(
    page: ft.Page, *, initial_profile: str, visible: bool
) -> ProfileSection:
    """Build the profile selector + suggestion chip, returning a ProfileSection."""
    profile_grid, get_value, set_value = build_profile_selector(
        page, value=initial_profile
    )

    chip_icon = ft.Icon(
        ft.Icons.AUTO_AWESOME, size=IconSize.sm, color=ft.Colors.PRIMARY
    )
    chip_text = ft.Text("", size=Type.small.size, color=ft.Colors.PRIMARY)
    chip = ft.Container(
        content=ft.Row(
            controls=[chip_icon, chip_text],
            spacing=Space.xxs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
        border_radius=Radius.pill,
        padding=ft.Padding(left=Space.xs, right=Space.xs, top=2, bottom=2),
        visible=False,
    )

    _help = help_icon_for("transcription.analysis_profile", page)
    section = ft.Column(
        spacing=Space.sm,
        visible=visible,
        controls=[
            ft.Row(
                controls=[
                    section_label("Tipo de análise"),
                    ft.Container(expand=True),
                    chip,
                    *([_help] if _help else []),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            profile_grid,
        ],
    )

    def _set_visible(value: bool) -> None:
        section.visible = value

    def _suggest(path: str) -> None:
        """Pre-select the predicted profile for a document already in the index."""

        async def _run() -> None:
            try:
                result = await asyncio.to_thread(_classify_path, path)
            except Exception as exc:  # noqa: BLE001 — suggestion is best-effort
                logging.debug("[d] Profile suggestion failed: %s", exc)
                return
            if result is None:
                return
            profile_id, confidence, margin = result
            from src.analysis.profiles import get_profile

            set_value(profile_id)
            label = get_profile(profile_id).label
            conf_str = f"{confidence:.2f}".replace(".", ",")
            prefix = "Sugestão incerta" if margin < _LOW_MARGIN else "Sugerido"
            chip_text.value = f"{prefix}: {label} · {conf_str}"
            chip.visible = True
            try:
                page.update()
            except Exception:
                pass

        try:
            page.run_task(_run)
        except Exception as exc:  # page not mounted yet
            logging.debug("[d] Could not schedule profile suggestion: %s", exc)

    return ProfileSection(
        control=section,
        get_value=get_value,
        set_value=set_value,
        set_visible=_set_visible,
        suggest=_suggest,
    )
