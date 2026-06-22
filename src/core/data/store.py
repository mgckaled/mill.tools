"""Persist user-saved queries to ~/.mill-tools/queries.json.

Same directory and pattern as ``recipes.json``/``prompts.json``: a flat list of
named entries, malformed entries skipped (logged) rather than aborting the load.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SavedQuery:
    """A named, reusable query (the Portuguese question and/or the raw SQL)."""

    name: str
    sql: str
    question: str = ""  # the original PT question, when it came from NL→SQL
    description: str = ""


def _store_path() -> Path:
    """Canonical on-disk location for saved queries."""
    return Path.home() / ".mill-tools" / "queries.json"


def load_queries(path: Path | None = None) -> list[SavedQuery]:
    """Load saved queries. Returns [] if the file is missing or unreadable."""
    path = path or _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[!] Could not read queries file %s: %s", path, exc)
        return []

    queries: list[SavedQuery] = []
    for entry in data:
        try:
            queries.append(
                SavedQuery(
                    name=entry["name"],
                    sql=entry["sql"],
                    question=entry.get("question", ""),
                    description=entry.get("description", ""),
                )
            )
        except (KeyError, TypeError):
            logger.warning("[!] Skipping malformed query entry: %r", entry)
    return queries


def save_query(query: SavedQuery, path: Path | None = None) -> None:
    """Add or replace a query by name, then persist the full list."""
    path = path or _store_path()
    others = [q for q in load_queries(path) if q.name != query.name]
    others.append(query)
    _write(others, path)


def delete_query(name: str, path: Path | None = None) -> bool:
    """Remove a query by name. Returns True when something was removed."""
    path = path or _store_path()
    queries = load_queries(path)
    kept = [q for q in queries if q.name != name]
    if len(kept) == len(queries):
        return False
    _write(kept, path)
    return True


def _write(queries: list[SavedQuery], path: Path) -> None:
    """Serialize queries to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(q) for q in queries]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
