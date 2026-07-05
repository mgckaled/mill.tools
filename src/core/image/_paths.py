"""Shared unique-output-path helper for every core/image writer.

Before this module, the same "no-collision path" loop was duplicated across
downloader.py, converter.py, transform.py (as _out_path) and describe.py
(inline). Centralizing it here also means every writer gets a sanitized
stem for free, closing the one gap describe.save_description had (it built
its ``<stem>_description.txt`` name straight from the source path, unlike
every other writer in the package).
"""

from __future__ import annotations

from pathlib import Path

from src.utils import sanitize_filename


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    """Return ``directory/{stem}.{ext}`` without colliding with an existing file.

    ``stem`` is sanitized (Windows-safe) before building the candidate. If the
    plain name already exists, appends ``_1``, ``_2``, … until a free name is
    found.
    """
    ext = ext.lstrip(".")
    safe_stem = sanitize_filename(stem)
    candidate = directory / f"{safe_stem}.{ext}"
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = directory / f"{safe_stem}_{counter}.{ext}"
        if not candidate.exists():
            return candidate
        counter += 1
