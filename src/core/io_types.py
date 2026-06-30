"""
io_types.py: Shared I/O type definitions for the core layer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InputItem:
    """Represents a single input item: a remote URL or a local file path."""

    kind: str  # "url" | "local"
    value: str  # full URL or absolute path
