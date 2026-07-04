"""Observatório — sub-aba Uso de disco: tamanho de cada entrada em ~/.mill-tools/.

Nested under the Índice/RAG tab, beside Índice e Painel. Cheap (only
``os.stat`` calls, no imports of optional-extra packages, no network) — unlike
the Status tab, this never needs a background thread.

Directory entries (``rag/``, ``ml/``) render their own children indented right
below them (``DiskUsageEntry.children``, arbitrary depth) instead of just a
single summed row — the point of this tab is to show *where* the space goes,
not just how much. Below the listing, a short glossary explains what each
file actually is; the glossary only shows entries that are present in the
current scan (``_FILE_DESCRIPTIONS`` is a lookup, not a schema — an
undocumented future file just doesn't get an explanation yet).

The returned control is the scrollable ``ft.Column`` itself, not a wrapper —
its right padding lives on the inner content ``Container`` instead, so the
scrollbar (owned by the outer Column) stays at the tab's normal edge instead
of being dragged inward along with the content.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.observatory.disk_usage import DiskUsageEntry, disk_usage, total_bytes
from src.core.rag.stats import fmt_disk_size
from src.gui.theme.components import hairline, help_icon_for, section_label
from src.gui.theme.tokens import IconSize, Radius, Space, Type

# Display name for a folder's glossary card header ("Pasta RAG" reads better
# than "Pasta rag") — cosmetic only, falls back to the raw dirname.
_FOLDER_DISPLAY_NAMES: dict[str, str] = {"rag": "RAG", "ml": "ML"}

# Keyed by filename (not by path) — good enough since nothing under
# ~/.mill-tools/ collides today. Missing on purpose for files not worth
# explaining twice (the parent dir's own description already covers "what is
# this store for"); a name absent here just gets no glossary line.
_FILE_DESCRIPTIONS: dict[str, str] = {
    "rag": (
        "Índice semântico do RAG — embeddings e metadados dos trechos "
        "indexados do seu acervo (hub de IA)."
    ),
    "vectors.npz": (
        "Matriz de vetores de embedding, um por trecho indexado — a base da "
        "busca por similaridade."
    ),
    "meta.json": (
        "Metadados de cada trecho indexado: arquivo de origem, texto, "
        "posição e data de modificação."
    ),
    "index_info.json": (
        "Modelo de embedding usado para indexar e a dimensão dos vetores — "
        "detecta quando o índice ficou desatualizado."
    ),
    "ml": (
        "Modelos e caches de ML: classificador de perfil/domínio e mapa "
        "semântico da Biblioteca."
    ),
    "profile_labels.json": (
        "Rótulos que você confirmou ou corrigiu (perfil de transcrição, "
        "domínio de dados, tipo de documento) — treinam o classificador "
        "supervisionado."
    ),
    "profile_prototypes.json": (
        "Metadados dos protótipos zero-shot por perfil/domínio, usados "
        "antes de haver rótulos suficientes para treinar."
    ),
    "profile_prototypes.npz": "Vetores de embedding dos protótipos zero-shot.",
    "semantic_map.json": (
        "Clusters e tópicos do mapa semântico da Biblioteca — rótulos por "
        "cluster e quais documentos pertencem a cada um."
    ),
    "semantic_map.npz": (
        "Coordenadas 2D dos documentos no mapa semântico (projeção PCA/t-SNE/UMAP)."
    ),
    "semantic_map_info.json": (
        "Assinatura do acervo usada para saber se o mapa semântico ficou "
        "desatualizado, sem precisar recalculá-lo toda vez."
    ),
    "ml_activity.json": (
        "Log de atividade de ML entre módulos — alimenta a aba Atividade deste hub."
    ),
    "ml_logs.json": (
        "Log de falhas de pipeline entre módulos — alimenta a aba Logs deste hub."
    ),
    "model_timings.json": (
        "Histórico de latência por modelo (LLM/VLM/Embedder) — alimenta a "
        "aba Tempo de resposta."
    ),
    "config.json": (
        "Preferências salvas da GUI: últimos modelos escolhidos, filtros, "
        "abas abertas etc."
    ),
    "recipes.json": "Receitas salvas no módulo Receitas.",
    "recipe_runs.json": (
        "Histórico de execuções de receitas — alimenta a aba Histórico do "
        "módulo Receitas."
    ),
    "queries.json": "Consultas salvas no módulo Dados.",
    "data_assessments.json": (
        "Cache dos pareceres de qualidade que a IA gera para arquivos de "
        "dados (aba Análise com IA)."
    ),
    "library_tags.json": (
        "Cache de auto-tags (palavras-chave) extraídas dos itens de texto "
        "da Biblioteca."
    ),
    "entity_glossary.json": (
        "Glossário opcional de entidades nomeadas — configurado manualmente, "
        "não gerado pelo app."
    ),
    "prompts.json": "Biblioteca de prompts salvos no hub de IA.",
}


def _icon_for(entry: DiskUsageEntry) -> str:
    if entry.is_dir:
        return ft.Icons.FOLDER_OUTLINED
    name = entry.name.lower()
    if name.endswith(".json"):
        return ft.Icons.DATA_OBJECT_OUTLINED
    if name.endswith(".npz"):
        return ft.Icons.DATA_ARRAY
    return ft.Icons.INSERT_DRIVE_FILE_OUTLINED


def _entry_row(entry: DiskUsageEntry, *, indent: int = 0) -> ft.Control:
    row = ft.Row(
        controls=[
            ft.Icon(
                _icon_for(entry),
                size=Type.body.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Text(
                entry.name,
                size=Type.body.size,
                color=ft.Colors.ON_SURFACE,
                expand=True,
            ),
            ft.Text(
                fmt_disk_size(entry.size_bytes),
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                font_family=Type.FONT_MONO,
            ),
        ],
        spacing=Space.sm,
    )
    return ft.Container(
        content=row,
        padding=ft.Padding(left=Space.xl * indent, right=0, top=0, bottom=0),
    )


def _entry_rows(
    entries: tuple[DiskUsageEntry, ...], *, indent: int = 0
) -> list[ft.Control]:
    """Flatten entries + their children into rows, each nesting level indented."""
    rows: list[ft.Control] = []
    for e in entries:
        rows.append(_entry_row(e, indent=indent))
        if e.children:
            rows.extend(_entry_rows(e.children, indent=indent + 1))
    return rows


def _glossary_row(name: str, description: str) -> ft.Control:
    return ft.Column(
        controls=[
            ft.Text(
                name,
                size=Type.small.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE,
                font_family=Type.FONT_MONO,
            ),
            ft.Text(
                description,
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                no_wrap=False,
            ),
        ],
        spacing=Space.xxs,
    )


def _folder_label(name: str) -> str:
    return f"Pasta {_FOLDER_DISPLAY_NAMES.get(name, name)}"


def _folder_card(entry: DiskUsageEntry) -> ft.Control:
    """A bordered group for a folder's glossary entry — its own (bigger)
    heading + description, followed by its children's regular glossary rows,
    all inside the same accent-bordered card (usual primary/orange tone)."""
    column: list[ft.Control] = [
        ft.Text(
            _folder_label(entry.name),
            size=Type.body_strong.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        )
    ]
    description = _FILE_DESCRIPTIONS.get(entry.name)
    if description:
        column.append(
            ft.Text(
                description,
                size=Type.body.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                no_wrap=False,
            )
        )
    child_rows = [
        _glossary_row(c.name, _FILE_DESCRIPTIONS[c.name])
        for c in entry.children
        if c.name in _FILE_DESCRIPTIONS
    ]
    if child_rows:
        column.append(
            ft.Container(
                content=ft.Column(controls=child_rows, spacing=Space.sm),
                padding=ft.Padding(left=Space.sm, right=0, top=Space.xs, bottom=0),
            )
        )
    return ft.Container(
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        border=ft.Border(
            left=ft.BorderSide(3, ft.Colors.with_opacity(0.6, ft.Colors.PRIMARY))
        ),
        border_radius=Radius.sm,
        padding=ft.Padding(
            left=Space.md, right=Space.sm, top=Space.sm, bottom=Space.sm
        ),
        content=ft.Column(controls=column, spacing=Space.xs),
    )


def _glossary_controls(entries: tuple[DiskUsageEntry, ...]) -> list[ft.Control]:
    """One card per describable folder, one plain row per describable file."""
    controls: list[ft.Control] = []
    for e in entries:
        if e.is_dir:
            has_content = e.name in _FILE_DESCRIPTIONS or any(
                c.name in _FILE_DESCRIPTIONS for c in e.children
            )
            if has_content:
                controls.append(_folder_card(e))
        elif e.name in _FILE_DESCRIPTIONS:
            controls.append(_glossary_row(e.name, _FILE_DESCRIPTIONS[e.name]))
    return controls


def build_disk_usage_tab(page: ft.Page) -> tuple[ft.Control, Callable[[], None]]:
    """Build the disk usage sub-tab control plus an ``apply()`` refresher."""
    entries_col = ft.Column(spacing=Space.xs)
    glossary_col = ft.Column(spacing=Space.sm)
    total_text = ft.Text(
        "—",
        size=Type.body_strong.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE,
        font_family=Type.FONT_MONO,
    )

    header_controls: list[ft.Control] = [
        ft.Icon(ft.Icons.STORAGE_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY),
        ft.Text(
            "Uso de disco",
            size=Type.heading.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
    ]
    _help = help_icon_for("observatory.disk_usage", page)
    if _help is not None:
        header_controls.append(_help)
    # The path lives beside the help icon (not its own section row) to save
    # vertical space — the list below is the whole point of this tab.
    header_controls.append(
        ft.Text(
            "~/.mill-tools/",
            size=Type.caption.size,
            color=ft.Colors.ON_SURFACE_VARIANT,
            font_family=Type.FONT_MONO,
        )
    )
    header_controls.append(ft.Container(expand=True))
    header_controls.append(
        ft.Text("Total:", size=Type.small.size, color=ft.Colors.ON_SURFACE_VARIANT)
    )
    header_controls.append(total_text)

    # The right padding lives on this inner Container, nested *inside* the
    # scrollable Column below — that shifts the content left without moving
    # the scrollbar, which belongs to the outer Column and stays at the
    # tab's normal edge. Padding the outer Column itself (a Container
    # wrapping it) would shrink the whole scrollable area, dragging the
    # scrollbar in with the content — not what we want here.
    content = ft.Container(
        padding=ft.Padding(left=0, right=Space.lg, top=0, bottom=0),
        content=ft.Column(
            controls=[
                ft.Row(
                    header_controls,
                    spacing=Space.sm,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                entries_col,
                hairline(),
                section_label("Glossário de arquivos"),
                glossary_col,
            ],
            spacing=Space.md,
        ),
    )
    control = ft.Column(controls=[content], scroll=ft.ScrollMode.AUTO, expand=True)

    def apply() -> None:
        entries = disk_usage()
        if not entries:
            entries_col.controls = [
                ft.Text(
                    "Nenhum arquivo em ~/.mill-tools/ ainda.",
                    italic=True,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    size=Type.input.size,
                )
            ]
            glossary_col.controls = []
        else:
            entries_col.controls = _entry_rows(entries)
            glossary_col.controls = _glossary_controls(entries)
        total_text.value = fmt_disk_size(total_bytes(entries))
        try:
            control.update()
        except Exception:
            pass

    return control, apply
