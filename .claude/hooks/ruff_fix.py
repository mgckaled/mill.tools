#!/usr/bin/env python
"""Claude Code PostToolUse hook: auto-format/lint a Python file with ruff.

Reads the tool-call JSON from stdin, extracts the edited file path, and runs
`ruff check --fix` + `ruff format` on it. Non-blocking: always exits 0 so a
formatter hiccup never interrupts the session. Invoked via `uv run python`,
so ruff (a dev dependency) is on PATH inside the project venv.
"""
from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    path = (data.get("tool_input") or {}).get("file_path", "")
    if not path or not path.endswith(".py"):
        return 0

    for cmd in (
        ["ruff", "check", "--fix", "--quiet", path],
        ["ruff", "format", "--quiet", path],
    ):
        try:
            subprocess.run(cmd, capture_output=True)
        except FileNotFoundError:
            # ruff not found (env not synced) — skip silently, never block.
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
