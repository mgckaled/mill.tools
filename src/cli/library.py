"""CLI subcommand `library` — browse files produced under output/.

Read-only: reuses the same core scanner/filters as the GUI Library module and
prints a table. No pipeline, so no CLIEventBus here.
"""

from __future__ import annotations

import argparse
import sys
import time

from src.core.library.scanner import filter_items, scan_library, sort_items
from src.core.library.types import ALL_KINDS

_SINCE_UNITS = {"m": 60, "h": 3600, "d": 86400}


def _parse_since(value: str | None) -> float | None:
    """Convert a duration like '7d' / '24h' / '30m' to a min mtime epoch.

    A bare number is read as days. Returns None when no value is given.
    Raises ValueError on malformed input.
    """
    if not value:
        return None
    value = value.strip().lower()
    unit = value[-1]
    if unit in _SINCE_UNITS and value[:-1].isdigit():
        return time.time() - int(value[:-1]) * _SINCE_UNITS[unit]
    if value.isdigit():  # bare number = days
        return time.time() - int(value) * _SINCE_UNITS["d"]
    raise ValueError(f"Invalid --since value: {value!r} (use e.g. 7d, 24h, 30m)")


def _fmt_size(num_bytes: int) -> str:
    """Human-readable size (B/KB/MB/GB)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def add_library_parser(subparsers) -> None:
    """Register the `library` subcommand and its `list` sub-subcommand."""
    library_p = subparsers.add_parser(
        "library", help="Browse files produced under output/"
    )
    library_sub = library_p.add_subparsers(dest="library_op", required=True)

    lst = library_sub.add_parser("list", help="List output files as a table")
    lst.add_argument(
        "--kind",
        choices=list(ALL_KINDS),
        default=None,
        help="Filter by kind (default: all)",
    )
    lst.add_argument(
        "--since",
        default=None,
        help="Only items newer than a duration, e.g. 7d, 24h, 30m",
    )
    lst.add_argument(
        "--sort",
        choices=["modified", "name", "size"],
        default="modified",
        help="Sort key (default: modified)",
    )
    lst.add_argument("--verbose", action="store_true", help="Enable debug logging")

    library_p.set_defaults(func=run_library_cli)


def run_library_cli(ns: argparse.Namespace) -> None:
    """Scan output/, apply the filters and print a table to stdout."""
    # Output filenames may contain non-cp1252 characters (e.g. fullwidth ｜).
    # On Windows the console defaults to charmap and print() would raise — make
    # stdout UTF-8 and replace anything it still can't encode.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    items = sort_items(
        filter_items(
            scan_library(),
            kinds={ns.kind} if ns.kind else None,
            since=_parse_since(ns.since),
        ),
        by=ns.sort,
        desc=(ns.sort != "name"),
    )

    if not items:
        print("No files found under output/.")
        return

    print(f"{'KIND':<14} {'CATEGORY':<11} {'SIZE':>9}  {'MODIFIED':<16} NAME")
    for it in items:
        modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(it.modified))
        print(
            f"{it.kind:<14} {it.category:<11} "
            f"{_fmt_size(it.size_bytes):>9}  {modified:<16} {it.path.name}"
        )
    print(f"\n{len(items)} file(s).")
