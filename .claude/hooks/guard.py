#!/usr/bin/env python
"""Claude Code PostToolUse hook: enforce mill.tools hard invariants.

Reads the tool-call JSON from stdin and inspects the edited Python file:

  1. src/core/ must stay Flet-free — no `import flet` / `from flet`
     (core is pure and reusable by CLI and GUI).
  2. subprocess must run in binary mode — no `text=True` /
     `universal_newlines=True` (avoids cp1252 UnicodeDecodeError on Windows
     with UTF-8 output from ffmpeg/ffprobe; see CLAUDE.md).

On violation: prints an explanation to stderr and exits 2, which feeds the
message back to Claude so it self-corrects. Otherwise exits 0. Any internal
error exits 0 so the hook never breaks the session.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_FLET_IMPORT = re.compile(r"^\s*(?:import\s+flet\b|from\s+flet\b)", re.MULTILINE)
_SUBPROC_TEXT = re.compile(r"\b(?:text|universal_newlines)\s*=\s*True\b")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    raw = (data.get("tool_input") or {}).get("file_path", "")
    if not raw or not raw.endswith(".py"):
        return 0

    norm = raw.replace("\\", "/")
    if "/src/" not in norm and not norm.startswith("src/"):
        return 0  # only guard project source files

    try:
        content = Path(raw).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    violations: list[str] = []

    in_core = "/src/core/" in norm or norm.startswith("src/core/")
    if in_core and _FLET_IMPORT.search(content):
        violations.append(
            "  - src/core/ deve permanecer Flet-free (puro, reutilizavel por CLI e GUI). "
            "Remova o import de `flet` deste modulo core."
        )

    uses_subprocess = "subprocess" in content or "Popen(" in content
    if uses_subprocess and _SUBPROC_TEXT.search(content):
        violations.append(
            "  - subprocess deve rodar em modo binario: remova `text=True`/"
            "`universal_newlines=True` e decodifique manualmente com "
            ".decode('utf-8', errors='replace') (evita UnicodeDecodeError cp1252 "
            "no Windows; ver CLAUDE.md)."
        )

    if violations:
        print(
            f"[guard] Violacao de convencao do mill.tools em {Path(raw).name}:\n"
            + "\n".join(violations),
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
