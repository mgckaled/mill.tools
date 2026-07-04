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
    """One direct child of ``~/.mill-tools/`` — a file or a whole subdirectory."""

    name: str
    size_bytes: int
    is_dir: bool


def mill_tools_dir() -> Path:
    """The root store directory — ``~/.mill-tools/`` (same path as gui/settings.py)."""
    return Path.home() / ".mill-tools"


def _dir_size(path: Path) -> int:
    """Recursively sum file sizes under ``path`` (skips unreadable entries)."""
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def disk_usage(*, directory: Path | None = None) -> tuple[DiskUsageEntry, ...]:
    """Size of every direct child of ``~/.mill-tools/``, largest first.

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

    entries = []
    for child in root.iterdir():
        try:
            if child.is_dir():
                entries.append(DiskUsageEntry(child.name, _dir_size(child), True))
            elif child.is_file():
                entries.append(DiskUsageEntry(child.name, child.stat().st_size, False))
        except OSError:
            continue  # e.g. deleted or permission-denied mid-scan
    entries.sort(key=lambda e: -e.size_bytes)
    return tuple(entries)


def total_bytes(entries: tuple[DiskUsageEntry, ...]) -> int:
    """Sum of every entry's size — the grand total shown atop the tab/CLI output."""
    return sum(e.size_bytes for e in entries)
