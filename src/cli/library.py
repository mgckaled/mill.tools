"""CLI subcommand `library` — browse files produced under output/.

Read-only: reuses the same core scanner/filters as the GUI Library module and
prints a table. No pipeline, so no CLIEventBus here.
"""

from __future__ import annotations

import argparse
import sys
import time

from src.core.library.image_dedup import DEFAULT_MAX_DISTANCE, near_duplicate_images
from src.core.library.scanner import filter_items, scan_library, sort_items
from src.core.library.types import ALL_KINDS, KIND_IMAGE

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

    stats = library_sub.add_parser(
        "stats", help="Dashboard of the archive (counts, sizes, growth)"
    )
    stats.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="How many largest files to show (default: 10)",
    )
    stats.add_argument("--verbose", action="store_true", help="Enable debug logging")

    dedup = library_sub.add_parser(
        "dedup-images",
        help="Encontra imagens quase-duplicadas no acervo (hash perceptual)",
    )
    dedup.add_argument(
        "--max-distance",
        type=int,
        default=DEFAULT_MAX_DISTANCE,
        help=f"Distância de Hamming máxima para considerar duplicata "
        f"(default: {DEFAULT_MAX_DISTANCE})",
    )
    dedup.add_argument(
        "--verbose", action="store_true", help="Ativa logging de depuração"
    )

    library_p.set_defaults(func=run_library_cli)


def run_library_cli(ns: argparse.Namespace) -> None:
    """Dispatch the `library` subcommand: `list`/`stats`/`dedup-images`."""
    # Output filenames may contain non-cp1252 characters (e.g. fullwidth ｜).
    # On Windows the console defaults to charmap and print() would raise — make
    # stdout UTF-8 and replace anything it still can't encode. Reconfigure only
    # our real stdout; under pytest sys.stdout is a capture wrapper (≠ __stdout__)
    # whose reconfigure would drop the captured output.
    if sys.stdout is sys.__stdout__:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if ns.library_op == "stats":
        _run_stats(ns)
    elif ns.library_op == "dedup-images":
        _run_dedup_images(ns)
    else:
        _run_list(ns)


def _run_dedup_images(ns: argparse.Namespace) -> None:
    """Scan the image catalog and print near-duplicate groups (dHash)."""
    items = filter_items(scan_library(), kinds={KIND_IMAGE})
    if not items:
        print("Nenhuma imagem encontrada em output/.")
        return

    groups = near_duplicate_images(
        [it.path for it in items], max_distance=ns.max_distance
    )
    if not groups:
        print(f"Nenhuma duplicata encontrada entre {len(items)} imagem(ns).")
        return

    print(f"{len(groups)} grupo(s) de imagens quase-duplicadas:\n")
    for i, group in enumerate(groups, start=1):
        print(f"Grupo {i} (distância máxima: {group.max_distance}):")
        for path in group.paths:
            print(f"  - {path.name}")
        print()

    from src.core.observatory.activity import log_activity

    log_activity(
        "library", "image_dedup", f"{len(groups)} grupo(s) de imagens quase-duplicadas"
    )


def _run_list(ns: argparse.Namespace) -> None:
    """Scan output/, apply the filters and print a table to stdout."""
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


def _run_stats(ns: argparse.Namespace) -> None:
    """Print the archive dashboard: totals, counts by kind, largest, growth."""
    from src.core.library.analytics import growth_by_period, largest, summary

    items = scan_library()
    if not items:
        print("No files found under output/.")
        return

    s = summary(items)
    print("Biblioteca")
    print(f"  Arquivos : {s.total_count}")
    print(f"  Tamanho  : {_fmt_size(s.total_bytes)}")

    print("\n  por tipo")
    for kind, count in s.count_by_kind.items():
        size = _fmt_size(s.bytes_by_kind.get(kind, 0))
        print(f"    {kind:<14} {count:>4} arquivo(s) · {size:>9}")

    print(f"\n  maiores ({ns.top})")
    for it in largest(items, ns.top):
        print(f"    {_fmt_size(it.size_bytes):>9}  {it.kind:<14} {it.path.name}")

    print("\n  crescimento por mês")
    for label, count, size in growth_by_period(items, "month").rows:
        print(f"    {label}   {count:>4} arquivo(s) · {_fmt_size(size):>9}")
