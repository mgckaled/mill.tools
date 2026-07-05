"""Safety guard: only read-only SELECT queries are allowed to reach DuckDB.

The engine already runs each query in an ephemeral in-memory connection with no
writable database attached, but DuckDB statements like ``COPY ... TO`` or
``INSTALL`` can still touch the filesystem. This module is the first line of
defence: it rejects anything that is not a single, read-only ``SELECT`` (or the
``WITH``/``FROM``-first / ``DESCRIBE``/``SUMMARIZE``/``PIVOT`` forms that still
only read), before the SQL is ever executed.
"""

from __future__ import annotations

import re

# Statements that read data without mutating anything. DuckDB supports
# FROM-first queries (``FROM t SELECT ...``) and table-producing keywords that
# never write, so they are allowed as the leading token.
_ALLOWED_LEADING = (
    "select",
    "with",
    "from",
    "describe",
    "summarize",
    "pivot",
    "unpivot",
    "values",
    "table",
)

# Whole-word tokens that can mutate the database or the filesystem. Their mere
# presence (anywhere) rejects the query — a deliberately blunt guard, since the
# user can always edit the SQL by hand if a false positive ever bites.
_FORBIDDEN = (
    "attach",
    "detach",
    "copy",
    "install",
    "load",
    "pragma",
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "truncate",
    "export",
    "import",
    "set",
    "reset",
    "call",
    "vacuum",
    "checkpoint",
    "begin",
    "commit",
    "rollback",
)
# NOTE: "replace" is deliberately absent. As a bare word it is DuckDB's
# read-only replace() string function (engine.reader_expr's own XLSX docstring
# recommends CAST(replace(replace(col,'.',''),',','.') AS DOUBLE) for pt-BR
# numbers) — it mutates nothing. The dangerous form, "CREATE OR REPLACE ...",
# is already caught by the "create" entry above.

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


class UnsafeQueryError(ValueError):
    """Raised when a query is not a single, read-only SELECT."""


def _strip_comments(sql: str) -> str:
    """Remove ``--`` line comments and ``/* */`` block comments."""
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    return sql


def ensure_select(sql: str) -> str:
    """Return *sql* unchanged if it is a single read-only query, else raise.

    Raises:
        UnsafeQueryError: when the query is empty, contains more than one
            statement, does not start with a read-only keyword, or mentions any
            mutating/filesystem keyword.
    """
    if not sql or not sql.strip():
        raise UnsafeQueryError("Consulta vazia.")

    # Strip string literals *before* looking for statement separators or
    # forbidden keywords, so a ';' or a keyword-looking substring sitting
    # inside a literal (e.g. WHERE col = 'a;b') is never mistaken for real SQL
    # structure. Everything from here on operates on this scrubbed text; the
    # original, untouched *sql* is only ever the return value.
    scannable = _STRING_LITERAL.sub(" ", _strip_comments(sql))

    # Reject multiple statements: anything after the first ';' (other than
    # trailing whitespace) means a second statement was smuggled in.
    body, _, rest = scannable.partition(";")
    if rest.strip():
        raise UnsafeQueryError("Apenas uma consulta SELECT é permitida (sem ';').")

    body = body.strip()
    if not body:
        raise UnsafeQueryError("Consulta vazia.")

    if not body.lower().startswith(_ALLOWED_LEADING):
        raise UnsafeQueryError(
            "Apenas consultas de leitura (SELECT/WITH/FROM/DESCRIBE) são permitidas."
        )

    body_lower = body.lower()
    for word in _FORBIDDEN:
        if re.search(rf"\b{word}\b", body_lower):
            raise UnsafeQueryError(
                f"Palavra-chave não permitida em consulta de leitura: '{word}'."
            )

    return sql


def is_safe_select(sql: str) -> bool:
    """Boolean convenience wrapper around :func:`ensure_select`."""
    try:
        ensure_select(sql)
        return True
    except UnsafeQueryError:
        return False
