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
import io
import json
import time
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from src.core.io_atomic import write_group
from src.core.ml.store import model_dir

if TYPE_CHECKING:
    from src.core.ml.types import SemanticMap
    from src.core.rag.types import ChunkMeta

_MAP_NPZ = "semantic_map.npz"
_MAP_JSON = "semantic_map.json"
_MAP_INFO = "semantic_map_info.json"


def corpus_signature(metas: list[ChunkMeta], embed_space_id: str = "?") -> str:
    """Return a stable hash of the corpus from its ``(source_path, mtime)`` pairs.

    Distinct documents only, sorted, so the signature is invariant to chunk order
    and re-scans — it changes only when a document is added, removed or modified.

    ``embed_space_id`` (model + dim + content scheme, from ``rag.stats.embed_space_id``)
    is folded into the hash: a reindex that changes the embedding space but
    touches the *same* files at the *same* mtimes (e.g. adopting task prefixes
    or a contextual chunk header) would otherwise leave this signature
    unchanged, silently serving the cached semantic map computed from the old
    vectors. Defaults to ``"?"`` for callers that don't track it explicitly.
    """
    distinct = sorted({(m.source_path, float(m.mtime)) for m in metas})
    payload = f"{embed_space_id}\n" + "\n".join(
        f"{path}\t{mtime!r}" for path, mtime in distinct
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sklearn_version() -> str:
    """Return the installed scikit-learn version (empty string if absent)."""
    try:
        import sklearn

        return sklearn.__version__
    except ImportError:  # pragma: no cover — cache is only used under [ml]
        return ""


def save_map(sm: SemanticMap, signature: str, *, directory: Path | None = None) -> Path:
    """Persist *sm* with a signature + version sidecar; return the npz path.

    The npz + both JSON sidecars are written as one atomic unit
    (:func:`src.core.io_atomic.write_group`) — a crash mid-write never leaves
    a fresh map paired with a stale/missing sidecar.
    """
    directory = directory or model_dir()
    npz_buf = io.BytesIO()
    np.savez_compressed(npz_buf, coords=sm.coords, labels=sm.labels)
    map_bytes = json.dumps(
        {
            # JSON keys are strings; cluster ids are restored to int on load.
            "cluster_names": {str(k): v for k, v in sm.cluster_names.items()},
            "source_paths": sm.source_paths,
            "kinds": sm.kinds,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    info_bytes = json.dumps(
        {
            "signature": signature,
            "sklearn_version": _sklearn_version(),
            "created_at": time.time(),
        },
        ensure_ascii=False,
    ).encode("utf-8")

    npz_path = directory / _MAP_NPZ
    write_group(
        [
            (npz_path, npz_buf.getvalue()),
            (directory / _MAP_JSON, map_bytes),
            (directory / _MAP_INFO, info_bytes),
        ]
    )
    return npz_path


def load_map(signature: str, *, directory: Path | None = None) -> SemanticMap | None:
    """Load the cached map only if its signature and sklearn version still match.

    Returns ``None`` (forcing a recompute) when the sidecar is absent, the corpus
    signature differs, the scikit-learn version changed, or a file is unreadable
    — including a corrupt ``.npz`` (``zipfile.BadZipFile``) or one missing an
    expected key (``KeyError``), same parity as ``classify.prototypes._load_prototypes``.
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
        return SemanticMap(
            coords=arrays["coords"],
            labels=arrays["labels"],
            cluster_names={int(k): v for k, v in payload["cluster_names"].items()},
            source_paths=payload["source_paths"],
            kinds=payload["kinds"],
        )
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None
