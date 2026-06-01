"""Contrato de módulo para a GUI do mill.tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import flet as ft


@dataclass
class Module:
    """Interface que todo módulo GUI deve implementar.

    O `control` é construído uma vez e reutilizado — trocar de módulo não
    destrói o estado (log, barra, resultado preservados ao voltar).

    `on_mount(payload)`: chamado ao navegar para o módulo. Recebe dados
    injetados por navigate_to (ex.: {"file": path} da bridge Áudio→Transcrição).

    `on_unmount()`: chamado ao sair do módulo. Serve apenas para pausar/soltar
    recursos externos (ex.: parar preview de áudio) — nunca para descartar o painel.
    """

    id: str
    label: str
    icon: ft.IconData
    selected_icon: ft.IconData
    control: ft.Control
    on_mount: Callable[[dict], None] = field(default_factory=lambda: lambda _: None)
    on_unmount: Callable[[], None] = field(default_factory=lambda: lambda: None)
