"""Library semantic map panel — the unsupervised topic map (Plano 4A).

A fourth view mode beside grid/list/panel. It clusters the indexed corpus
(``core/ml``), draws the 2D map through the Plano 1 ``charts`` boundary (rendered
off the UI thread → PNG), and lists the discovered topics with a per-document
"Relacionados" action (``recommend.related``). Independent of the Library
filters: it reads the persisted RAG ``VectorStore`` directly.

Gating: clustering/projection need the ``[ml]`` extra and the rendered map needs
the chart extras — when either is missing the panel shows a setup hint instead of
crashing. The build is cached by the corpus signature, so re-entering the mode or
typing in the search box does not recompute an unchanged map.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Callable

import flet as ft

from src.gui.modules import _charts
from src.gui.theme.components import hairline, section_label
from src.gui.theme.tokens import Space, Type


def build_semantic_map_panel(page: ft.Page) -> tuple[ft.Control, Callable[[], None]]:
    """Build the semantic-map control plus a ``refresh()`` that (re)builds it.

    ``refresh`` is cheap to call repeatedly: it hashes the corpus and skips the
    work when nothing changed since the last render.
    """
    # Last rendered corpus signature → skip rework when unchanged.
    _last_sig: list[str | None] = [None]
    # Pooled document matrix of the current map, for the "Relacionados" lookups.
    _dm: list[object] = [None]

    status = ft.Text(
        "", size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT, italic=True
    )
    map_img = ft.Image(
        _charts.BLANK_PNG,
        fit=ft.BoxFit.CONTAIN,
        expand=True,
        visible=False,
        gapless_playback=True,
    )
    clusters_col = ft.Column(spacing=Space.xs, scroll=ft.ScrollMode.AUTO, expand=True)

    panel = ft.Column(
        controls=[
            section_label("Mapa semântico do acervo"),
            status,
            ft.Row(
                [
                    ft.Container(content=map_img, expand=3, height=460),
                    ft.Container(
                        content=ft.Column(
                            [section_label("Tópicos"), clusters_col],
                            spacing=Space.xs,
                            expand=True,
                        ),
                        expand=2,
                        height=460,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=Space.xl,
            ),
            hairline(),
            ft.Text(
                "Clique em um documento para ver os relacionados.",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
        visible=False,
    )

    def _show_related(source_path: str) -> None:
        """Open a dialog listing the documents most similar to *source_path*."""
        from src.core.ml.recommend import related

        if _dm[0] is None:
            return
        try:
            neighbours = related(_dm[0], source_path, k=8)
        except ValueError:
            return
        rows = [
            ft.Text(
                f"{score:.2f}   {Path(p).name}",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE,
                no_wrap=True,
            )
            for p, score in neighbours
        ] or [
            ft.Text(
                "Nenhum documento relacionado.",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        ]
        dialog = ft.AlertDialog(
            title=ft.Text(f"Relacionados a {Path(source_path).name}"),
            content=ft.Column(rows, tight=True, scroll=ft.ScrollMode.AUTO, width=460),
            actions=[ft.TextButton("Fechar", on_click=lambda _e: page.pop_dialog())],
        )
        page.show_dialog(dialog)

    def _doc_row(source_path: str) -> ft.Control:
        return ft.TextButton(
            content=ft.Text(
                Path(source_path).name,
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                no_wrap=True,
            ),
            on_click=lambda _e, sp=source_path: _show_related(sp),
            style=ft.ButtonStyle(
                padding=ft.Padding(left=Space.sm, right=0, top=2, bottom=2)
            ),
        )

    def _populate_clusters(sm) -> None:
        """Fill the side list: each topic's name/size + its member documents."""
        from collections import Counter

        from src.core.ml.mapviz import ORPHAN_LABEL, cluster_display_name

        counts = Counter(int(label) for label in sm.labels)
        order = sorted((c for c in counts if c != -1), key=lambda c: -counts[c])
        controls: list[ft.Control] = []
        for cluster_id in order + ([-1] if counts.get(-1) else []):
            name = (
                cluster_display_name(cluster_id, sm.cluster_names)
                if cluster_id != -1
                else ORPHAN_LABEL
            )
            controls.append(
                ft.Text(
                    f"{name}  ·  {counts[cluster_id]}",
                    size=Type.label.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.PRIMARY
                    if cluster_id != -1
                    else ft.Colors.ON_SURFACE_VARIANT,
                )
            )
            members = [
                sp
                for sp, lab in zip(sm.source_paths, sm.labels)
                if int(lab) == cluster_id
            ]
            controls.extend(_doc_row(sp) for sp in members[:12])
        clusters_col.controls = controls

    def refresh() -> None:
        """(Re)build the map off-thread, skipping work when the corpus is unchanged."""
        from src.core.ml import deps
        from src.core.ml.cache import corpus_signature
        from src.core.rag import embedder
        from src.core.rag.indexer import index_dir
        from src.core.rag.stats import embed_space_id
        from src.core.rag.store import VectorStore

        if not deps.is_available():
            status.value = f"Mapa indisponível. {deps.SETUP_HINT}"
            status.visible = True
            map_img.visible = False
            return
        if not _charts.extras_available():
            status.value = _charts.setup_hint()
            status.visible = True
            map_img.visible = False
            return

        index_directory = index_dir()
        store = VectorStore.load(index_directory, dim=embedder.EMBED_DIM)
        if len(store) == 0:
            status.value = "Índice vazio. Indexe seu acervo no hub IA primeiro."
            status.visible = True
            map_img.visible = False
            clusters_col.controls = []
            _last_sig[0] = None
            return

        space_id = embed_space_id(index_directory)
        signature = corpus_signature(store.meta, space_id)
        if signature == _last_sig[0] and map_img.visible:
            return  # already rendered for this exact corpus

        status.value = "Gerando o mapa semântico…"
        status.visible = True

        async def _render() -> None:
            from src.core.ml import features
            from src.core.ml.mapviz import build_semantic_map, render_semantic_map_png

            try:
                sm = await asyncio.to_thread(
                    lambda: build_semantic_map(store, embed_space_id=space_id)
                )
                png = await asyncio.to_thread(
                    render_semantic_map_png, sm, palette=_charts.dark_palette()
                )
                _dm[0] = features.document_matrix(store)
                _populate_clusters(sm)
                map_img.src = png
                map_img.visible = True
                status.visible = False
                _last_sig[0] = signature
            except Exception as exc:  # build/render failure → message, never crash
                status.value = f"Não foi possível gerar o mapa: {exc}"
                status.visible = True
                map_img.visible = False
                _last_sig[0] = None
            with contextlib.suppress(Exception):
                page.update()

        page.run_task(_render)

    return panel, refresh
