"""Versioned on-disk cache for the semantic map (mirrors ``store.py``).

Clustering + projection + labeling are expensive enough to cache: the result is
keyed by a **corpus signature** — a stable hash of the indexed documents'
``(source_path, mtime)`` — plus the scikit-learn version, exactly like the
Plan 3 model store and the data ``assess`` cache. ``load_map`` returns ``None``
on any mismatch (corpus changed or sklearn upgraded), forcing a recompute.

The map is stored as numpy arrays (coords/labels in an ``.npz``) plus JSON for
the names/paths, so there is no pickle and no cross-version portability concern;
the sidecar still records the version for invalidation when the algorithm
changes.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from src.core.ml.store import model_dir

if TYPE_CHECKING:
    from src.core.ml.types import SemanticMap
    from src.core.rag.types import ChunkMeta

_MAP_NPZ = "semantic_map.npz"
_MAP_JSON = "semantic_map.json"
_MAP_INFO = "semantic_map_info.json"


def corpus_signature(metas: list[ChunkMeta]) -> str:
    """Return a stable hash of the corpus from its ``(source_path, mtime)`` pairs.

    Distinct documents only, sorted, so the signature is invariant to chunk order
    and re-scans — it changes only when a document is added, removed or modified.
    """
    distinct = sorted({(m.source_path, float(m.mtime)) for m in metas})
    payload = "\n".join(f"{path}\t{mtime!r}" for path, mtime in distinct)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sklearn_version() -> str:
    """Return the installed scikit-learn version (empty string if absent)."""
    try:
        import sklearn

        return sklearn.__version__
    except ImportError:  # pragma: no cover — cache is only used under [ml]
        return ""


def save_map(sm: SemanticMap, signature: str, *, directory: Path | None = None) -> Path:
    """Persist *sm* with a signature + version sidecar; return the npz path."""
    directory = directory or model_dir()
    directory.mkdir(parents=True, exist_ok=True)
    npz_path = directory / _MAP_NPZ
    np.savez_compressed(npz_path, coords=sm.coords, labels=sm.labels)
    (directory / _MAP_JSON).write_text(
        json.dumps(
            {
                # JSON keys are strings; cluster ids are restored to int on load.
                "cluster_names": {str(k): v for k, v in sm.cluster_names.items()},
                "source_paths": sm.source_paths,
                "kinds": sm.kinds,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (directory / _MAP_INFO).write_text(
        json.dumps(
            {
                "signature": signature,
                "sklearn_version": _sklearn_version(),
                "created_at": time.time(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return npz_path


def load_map(signature: str, *, directory: Path | None = None) -> SemanticMap | None:
    """Load the cached map only if its signature and sklearn version still match.

    Returns ``None`` (forcing a recompute) when the sidecar is absent, the corpus
    signature differs, the scikit-learn version changed, or a file is unreadable.
    """
    from src.core.ml.types import SemanticMap

    directory = directory or model_dir()
    info_path = directory / _MAP_INFO
    npz_path = directory / _MAP_NPZ
    json_path = directory / _MAP_JSON
    if not (info_path.exists() and npz_path.exists() and json_path.exists()):
        return None
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if info.get("signature") != signature:
        return None
    if info.get("sklearn_version") != _sklearn_version():
        return None
    try:
        arrays = np.load(npz_path)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return SemanticMap(
        coords=arrays["coords"],
        labels=arrays["labels"],
        cluster_names={int(k): v for k, v in payload["cluster_names"].items()},
        source_paths=payload["source_paths"],
        kinds=payload["kinds"],
    )
