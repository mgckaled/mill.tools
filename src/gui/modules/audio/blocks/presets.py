"""Presets block for the audio module — one-tap processing chains."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import secondary_button
from src.gui.theme.tokens import Space

# (id, label, icon)
_PRESETS: list[tuple[str, str, str]] = [
    ("transcription", "Pronto p/ transcrição", ft.Icons.SUBTITLES_OUTLINED),
    ("podcast", "Podcast", ft.Icons.PODCASTS),
    ("music", "Arquivo musical", ft.Icons.MUSIC_NOTE_OUTLINED),
]


class PresetsRefs(NamedTuple):
    set_disabled: Callable[[bool], None]


def build_presets_block(
    page: ft.Page, apply: Callable[[str], None]
) -> tuple[ft.Control, PresetsRefs]:
    """Build the preset chips row.

    Each chip calls ``apply(preset_id)``; the caller (form_view) maps the id to
    setter calls on the other blocks. Presets set form state, not the pipeline.
    """
    buttons: list[ft.OutlinedButton] = []
    for pid, label, icon in _PRESETS:
        btn = secondary_button(label, icon=icon, on_click=lambda _e, p=pid: apply(p))
        buttons.append(btn)

    control = ft.Row(buttons, spacing=Space.xs, wrap=True)

    def _set_disabled(running: bool) -> None:
        for b in buttons:
            b.disabled = running

    return control, PresetsRefs(set_disabled=_set_disabled)
