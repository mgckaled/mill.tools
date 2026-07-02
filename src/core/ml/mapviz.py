"""Build and render the semantic map: cluster + project + label → PNG.

The orchestrator that ties the 4A pieces together. ``build_semantic_map`` runs
clustering, 2D projection and c-TF-IDF labeling over the pooled document vectors
(Plan 3 accessor) and returns a cached ``SemanticMap``; ``render_semantic_map_png``
turns it into PNG bytes through the Plan 1 ``charts`` boundary (the only
matplotlib touchpoint), so no DataFrame or figure ever crosses into the GUI.

Clustering/projection/labeling need the ``[ml]`` extra; rendering additionally
needs the chart extras (``[analysis]`` for pandas, ``[data-plot]`` for
matplotlib). pandas is imported lazily, only at render time.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import numpy as np

from src.core.ml import features
from src.core.ml.cache import corpus_signature, load_map, save_map
from src.core.ml.cluster import cluster_documents
from src.core.ml.labeling import label_clusters
from src.core.ml.project import project_2d
from src.core.ml.types import SemanticMap

if TYPE_CHECKING:
    from src.core.data.charts import ChartPalette
    from src.core.rag.store import VectorStore

# Display name for the noise/orphan cluster (HDBSCAN label -1).
ORPHAN_LABEL = "órfãos"


def build_semantic_map(
    store: VectorStore,
    *,
    method: str = "hdbscan",
    projection: str = "pca",
    k: int | None = None,
    top_n: int = 5,
    use_cache: bool = True,
    cache_dir: Path | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> SemanticMap:
    """Cluster, project and label the corpus into a (cached) ``SemanticMap``.

    The cache is keyed by the corpus signature (``(source_path, mtime)``), so an
    unchanged index returns instantly without recomputing. Requires the ``[ml]``
    extra (raised by the underlying steps when missing).

    ``on_stage`` (optional) is called with ``"cluster"``/``"project"``/
    ``"label"`` right before each stage starts — the Observatório stepper's
    hook (item 3.5): this is the one place in ``core/ml`` that internally
    chains multiple stages itself, so it is the one pure function that needs
    to know about a progress callback at all.
    """
    signature = corpus_signature(store.meta)
    if use_cache:
        cached = load_map(signature, directory=cache_dir)
        if cached is not None:
            return cached

    dm = features.document_matrix(store)
    if on_stage:
        on_stage("cluster")
    clusters = cluster_documents(dm, method=method, k=k)
    if on_stage:
        on_stage("project")
    coords = project_2d(dm, method=projection)
    if on_stage:
        on_stage("label")
    names = label_clusters(features.document_texts(store), clusters.labels, top_n=top_n)

    semantic_map = SemanticMap(
        coords=coords.astype(np.float32),
        labels=clusters.labels,
        cluster_names=names,
        source_paths=dm.source_paths,
        kinds=dm.kinds,
    )
    if use_cache:
        save_map(semantic_map, signature, directory=cache_dir)
    return semantic_map


def cluster_display_name(cluster_id: int, cluster_names: dict[int, list[str]]) -> str:
    """Human name for a cluster: its top terms, or a fallback when unlabeled."""
    if cluster_id == -1:
        return ORPHAN_LABEL
    terms = cluster_names.get(cluster_id) or []
    return ", ".join(terms[:3]) if terms else f"grupo {cluster_id}"


def render_semantic_map_png(
    sm: SemanticMap, *, palette: ChartPalette | None = None, title: str | None = None
) -> bytes:
    """Render the semantic map to PNG bytes via the ``charts`` boundary.

    Builds a pandas DataFrame ``{x, y, cluster}`` (the edge), colors by cluster
    name (orphans muted) and annotates each non-orphan cluster's centroid.

    Raises:
        RuntimeError: if the chart extras are missing.
        ValueError: if the map is empty.
    """
    import pandas as pd

    from src.core.data import charts

    if not charts.is_available():
        raise RuntimeError(charts.SETUP_HINT)
    if len(sm) == 0:
        raise ValueError("Mapa vazio: nada para projetar.")

    display = [cluster_display_name(int(c), sm.cluster_names) for c in sm.labels]
    df = pd.DataFrame({"x": sm.coords[:, 0], "y": sm.coords[:, 1], "cluster": display})

    # Annotate each non-orphan cluster at its centroid.
    annotations: list[tuple[float, float, str]] = []
    for cluster_id in sorted(set(int(c) for c in sm.labels) - {-1}):
        mask = sm.labels == cluster_id
        cx = float(sm.coords[mask, 0].mean())
        cy = float(sm.coords[mask, 1].mean())
        terms = sm.cluster_names.get(cluster_id) or []
        annotations.append(
            (cx, cy, ", ".join(terms[:2]) if terms else f"#{cluster_id}")
        )

    return charts.render_category_scatter(
        df,
        x="x",
        y="y",
        color="cluster",
        annotations=annotations,
        title=title,
        noise_value=ORPHAN_LABEL,
        palette=palette or charts.DEFAULT_PALETTE,
    )
