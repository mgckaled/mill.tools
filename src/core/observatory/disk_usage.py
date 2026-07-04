"""Read-only disk usage snapshot of ``~/.mill-tools/`` — every persisted store.

A generic directory walk, not a hardcoded list of known files: new stores
(JSON logs, the RAG index, cached ML models) show up automatically without
touching this module. Mirrors the read-only spirit of ``status.py`` —
transparency, not a settings surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DiskUsageEntry:
    """One entry under ``~/.mill-tools/`` — a file, or a subdirectory with its
    own direct children (``rag/``, ``ml/``) nested one level deep."""

    name: str
    size_bytes: int
    is_dir: bool
    children: tuple["DiskUsageEntry", ...] = ()


def mill_tools_dir() -> Path:
    """The root store directory — ``~/.mill-tools/`` (same path as gui/settings.py)."""
    return Path.home() / ".mill-tools"


def _scan_dir(path: Path) -> tuple[DiskUsageEntry, ...]:
    """Entries of ``path``, largest first — directories recurse into their own
    children so nested stores (``rag/``, ``ml/``) aren't just a single summed row.
    """
    entries = []
    for child in path.iterdir():
        try:
            if child.is_dir():
                nested = _scan_dir(child)
                size = sum(e.size_bytes for e in nested)
                entries.append(DiskUsageEntry(child.name, size, True, nested))
            elif child.is_file():
                entries.append(DiskUsageEntry(child.name, child.stat().st_size, False))
        except OSError:
            continue  # e.g. deleted or permission-denied mid-scan
    entries.sort(key=lambda e: -e.size_bytes)
    return tuple(entries)


def disk_usage(*, directory: Path | None = None) -> tuple[DiskUsageEntry, ...]:
    """Size of every entry under ``~/.mill-tools/``, largest first.

    Args:
        directory: Overrides ``mill_tools_dir()`` (injectable for tests);
            production always reads the real one.

    Returns:
        An empty tuple when the directory doesn't exist yet (a fresh install
        that hasn't run any pipeline).
    """
    root = directory if directory is not None else mill_tools_dir()
    if not root.exists():
        return ()
    try:
        return _scan_dir(root)
    except OSError:
        return ()


def total_bytes(entries: tuple[DiskUsageEntry, ...]) -> int:
    """Sum of every entry's size — the grand total shown atop the tab/CLI output."""
    return sum(e.size_bytes for e in entries)
