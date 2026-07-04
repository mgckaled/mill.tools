"""Pure, honest description of the persisted RAG index — no Ollama, no network.

Reads the on-disk store (``meta.json`` + ``vectors.npz`` + the ``index_info.json``
sidecar written by ``VectorStore.persist``) and summarizes it for the GUI index
inspector (PR7.2.3) and the CLI ``ai stats`` command (PR7.2.1). All formatting
helpers are pure so both front-ends share one source of truth.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Month abbreviations in PT-BR. Built manually instead of relying on
# locale/``%b`` — the C locale would render "Jun" (or "06") and the project must
# not depend on a locale being installed (CI, fresh Windows, etc.).
_PT_MONTHS = (
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
)


@dataclass(frozen=True, slots=True)
class DocStat:
    """Aggregated stats for one indexed source document."""

    source_path: str
    kind: str  # transcription | document | image
    n_chunks: int
    mtime: float  # source mtime (from ChunkMeta.mtime)
    char_total: int  # sum of len(chunk.text) over the document's chunks


@dataclass(frozen=True, slots=True)
class IndexStats:
    """Summary of the whole persisted index."""

    n_docs: int
    n_chunks: int
    dim: int  # vector width (0 when the index is absent)
    embed_model: str  # from index_info.json; "?" when the sidecar is absent
    disk_bytes: int  # vectors.npz + meta.json (+ index_info.json)
    updated_at: float | None  # mtime of vectors.npz; None when absent
    per_doc: tuple[DocStat, ...]  # ordered by n_chunks desc, then filename


# Files that make up the persisted index, summed for ``disk_bytes``.
_INDEX_FILES = ("vectors.npz", "meta.json", "index_info.json")


def _empty_stats() -> IndexStats:
    """Return a zeroed IndexStats (index missing / never built)."""
    return IndexStats(
        n_docs=0,
        n_chunks=0,
        dim=0,
        embed_model="?",
        disk_bytes=0,
        updated_at=None,
        per_doc=(),
    )


def _read_embed_model(directory: Path) -> str:
    """Read the embedding model name from index_info.json ("?" when absent)."""
    info_path = directory / "index_info.json"
    if not info_path.exists():
        return "?"
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "?"
    return info.get("embed_model") or "?"


def _read_dim(directory: Path) -> int:
    """Read the vector width, preferring the ``index_info.json`` sidecar (a
    few bytes) over loading ``vectors.npz`` — which can be large, and, being
    written with ``savez_compressed``, fully decompresses just to expose
    ``.shape``.

    ``vectors.npz`` still gates the result: its plain *existence* is checked
    first (0 when absent, same as before), but once it exists the sidecar's
    ``dim`` is trusted without decompressing the matrix to double-check it —
    detecting bit rot in the matrix's binary content is not this field's job.
    Falls back to loading the npz for older indexes that predate the sidecar,
    or when the sidecar is missing/malformed/lacks a usable ``dim``.
    """
    vectors_path = directory / "vectors.npz"
    if not vectors_path.exists():
        return 0

    info_path = directory / "index_info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        dim = info.get("dim")
        if isinstance(dim, int) and dim > 0:
            return dim

    try:
        import numpy as np

        shape = np.load(vectors_path)["vectors"].shape
    except (OSError, ValueError, KeyError):
        return 0
    return int(shape[1]) if len(shape) == 2 else 0


def _disk_bytes(directory: Path) -> int:
    """Sum the sizes of the index files present in ``directory``."""
    total = 0
    for name in _INDEX_FILES:
        path = directory / name
        if path.exists():
            total += path.stat().st_size
    return total


def index_stats(directory: Path) -> IndexStats:
    """Read the persisted index and summarize it. Pure, no Ollama/network.

    Args:
        directory: The on-disk index location (``index_dir()`` in production).

    Returns:
        An ``IndexStats``; a zeroed instance when ``meta.json`` is absent.
    """
    meta_path = directory / "meta.json"
    if not meta_path.exists():
        return _empty_stats()

    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty_stats()

    # Aggregate chunks per source document, preserving first-seen kind/mtime.
    chunks_by_doc: dict[str, list[dict]] = defaultdict(list)
    for chunk in raw:
        chunks_by_doc[chunk["source_path"]].append(chunk)

    per_doc = [
        DocStat(
            source_path=source,
            kind=chunks[0].get("kind", "?"),
            n_chunks=len(chunks),
            mtime=float(chunks[0].get("mtime", 0.0)),
            char_total=sum(len(c.get("text", "")) for c in chunks),
        )
        for source, chunks in chunks_by_doc.items()
    ]
    # Heaviest documents first; break ties on filename for a stable order.
    per_doc.sort(key=lambda d: (-d.n_chunks, Path(d.source_path).name.lower()))

    updated_at: float | None = None
    vectors_path = directory / "vectors.npz"
    if vectors_path.exists():
        updated_at = vectors_path.stat().st_mtime

    return IndexStats(
        n_docs=len(per_doc),
        n_chunks=len(raw),
        dim=_read_dim(directory),
        embed_model=_read_embed_model(directory),
        disk_bytes=_disk_bytes(directory),
        updated_at=updated_at,
        per_doc=tuple(per_doc),
    )


def fmt_thousands(n: int) -> str:
    """Format an int with a dot as the thousands separator (PT-BR style)."""
    return f"{n:,}".replace(",", ".")


def fmt_datetime(ts: float) -> str:
    """Format a POSIX timestamp as 'DD mês HH:MM' with a PT-BR month abbrev."""
    import time

    lt = time.localtime(ts)
    return f"{lt.tm_mday} {_PT_MONTHS[lt.tm_mon - 1]} {lt.tm_hour:02d}:{lt.tm_min:02d}"


def fmt_status_line(stats: IndexStats) -> str:
    """Render the short status line: '28 docs · 4.654 chunks · 20 jun 20:45'.

    Returns 'Índice vazio' when there is nothing indexed yet.
    """
    if stats.n_chunks == 0:
        return "Índice vazio"
    docs = fmt_thousands(stats.n_docs)
    chunks = fmt_thousands(stats.n_chunks)
    line = f"{docs} docs · {chunks} chunks"
    if stats.updated_at is not None:
        line += f" · {fmt_datetime(stats.updated_at)}"
    return line


def fmt_disk_size(num_bytes: int) -> str:
    """Render a byte count as a human-readable size (B / KB / MB / GB)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover — loop always returns first


def chunks_for(directory: Path, source_path: str) -> list[tuple[int, str]]:
    """Return ``(chunk_idx, text)`` pairs for one source, ordered by index.

    Powers the index inspector's drill-down (PR7.2.3) without loading the whole
    vector matrix — it only reads ``meta.json``.
    """
    meta_path = directory / "meta.json"
    if not meta_path.exists():
        return []
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = [
        (int(c.get("chunk_idx", 0)), c.get("text", ""))
        for c in raw
        if c.get("source_path") == source_path
    ]
    rows.sort(key=lambda r: r[0])
    return rows
