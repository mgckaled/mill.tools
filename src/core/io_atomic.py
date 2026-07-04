"""Atomic, crash-safe writes for small on-disk artifacts (JSON logs, index
sidecars, model caches).

Every write lands via a temp file staged in the *same directory* as the
target, followed by ``os.replace`` — atomic on both POSIX and Windows as
long as source and destination share a volume (guaranteed here since the
temp file is never created elsewhere). A reader never observes a half
-written file, and a crash mid-write leaves the previous version intact.

``write_group`` extends this to *several* files that must advance together
(e.g. the RAG store's ``vectors.npz`` + ``meta.json`` + ``index_info.json``
trio): every temp file is staged first, and only then are all of them
swapped in — a failure while staging leaves every target file untouched,
so a reader never sees a fresh ``vectors.npz`` paired with a stale
``meta.json``.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

# Windows can transiently deny os.replace() over the destination (Defender
# scanning it, another process briefly holding it open without
# FILE_SHARE_DELETE) — a short retry budget resolves this in practice
# without masking a real, persistent lock.
_REPLACE_RETRIES = 5
_REPLACE_RETRY_DELAY = 0.05


def _stage_temp(path: Path, data: bytes) -> Path:
    """Write ``data`` to a temp file next to ``path`` and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return tmp_path


def _replace_with_retry(
    tmp_path: Path,
    dest: Path,
    *,
    retries: int,
    retry_delay: float,
) -> None:
    for attempt in range(retries + 1):
        try:
            os.replace(tmp_path, dest)
            return
        except PermissionError:
            if attempt == retries:
                raise
            time.sleep(retry_delay)


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    retries: int = _REPLACE_RETRIES,
    retry_delay: float = _REPLACE_RETRY_DELAY,
) -> None:
    """Write ``data`` to ``path`` atomically (temp file + ``os.replace``)."""
    path = Path(path)
    tmp_path = _stage_temp(path, data)
    try:
        _replace_with_retry(tmp_path, path, retries=retries, retry_delay=retry_delay)
    finally:
        tmp_path.unlink(missing_ok=True)  # no-op once os.replace has moved it


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    retries: int = _REPLACE_RETRIES,
    retry_delay: float = _REPLACE_RETRY_DELAY,
) -> None:
    """Text convenience wrapper around :func:`atomic_write_bytes`."""
    atomic_write_bytes(
        path, text.encode(encoding), retries=retries, retry_delay=retry_delay
    )


def write_group(
    writes: list[tuple[Path, bytes]],
    *,
    retries: int = _REPLACE_RETRIES,
    retry_delay: float = _REPLACE_RETRY_DELAY,
) -> None:
    """Write several files as one unit.

    Every temp file is staged first; only once all of them are written to
    disk does the function start swapping them in. A staging failure (disk
    full, permission error) leaves every target untouched — no partial pair
    like a fresh ``vectors.npz`` next to a stale ``meta.json``. A failure
    *during* the swap phase (rare — swaps are atomic renames) can still
    leave a partial group; that risk is inherent to updating >1 file and is
    not fully solvable without a journal, which this project's scale does
    not warrant.
    """
    staged: list[tuple[Path, Path]] = []
    try:
        for path, data in writes:
            path = Path(path)
            staged.append((_stage_temp(path, data), path))
        for tmp_path, dest in staged:
            _replace_with_retry(
                tmp_path, dest, retries=retries, retry_delay=retry_delay
            )
    finally:
        for tmp_path, _ in staged:
            tmp_path.unlink(missing_ok=True)
