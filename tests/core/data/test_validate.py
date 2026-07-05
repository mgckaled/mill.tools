"""Tests for the read-only SQL safety guard."""

import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM t",
        "  select a, b from t where a > 1  ",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "FROM t SELECT a",  # DuckDB FROM-first
        "DESCRIBE SELECT * FROM t",
        "SUMMARIZE t",
        "SELECT 'DELETE inside a string literal' AS note FROM t",
        # replace() is a pure string function, not a mutating statement — the
        # canonical pt-BR-number cast recommended by engine.reader_expr's own
        # docstring must not be rejected.
        "SELECT CAST(replace(replace(col,'.',''),',','.') AS DOUBLE) FROM t",
        # A ';' inside a string literal is not a second statement.
        "SELECT * FROM t WHERE col = 'a;b'",
    ],
)
def test_safe_selects_pass(sql):
    from src.core.data.validate import ensure_select, is_safe_select

    assert is_safe_select(sql)
    assert ensure_select(sql) == sql


@pytest.mark.unit
@pytest.mark.parametrize(
    "sql",
    [
        "COPY t TO 'out.csv'",
        "DROP TABLE t",
        "DELETE FROM t",
        "UPDATE t SET a = 1",
        "INSERT INTO t VALUES (1)",
        "INSTALL excel",
        "ATTACH 'x.db'",
        "PRAGMA database_list",
        "CREATE TABLE t AS SELECT 1",
        "CREATE OR REPLACE TABLE t AS SELECT 1",  # the dangerous form of "replace"
        "SELECT 1; DELETE FROM t",  # multiple statements
        "",
        "   ",
    ],
)
def test_unsafe_queries_rejected(sql):
    from src.core.data.validate import UnsafeQueryError, ensure_select, is_safe_select

    assert not is_safe_select(sql)
    with pytest.raises(UnsafeQueryError):
        ensure_select(sql)


@pytest.mark.unit
def test_second_statement_after_literal_with_semicolon_is_still_caught():
    from src.core.data.validate import is_safe_select

    # The literal's ';' must not swallow a genuine second statement that
    # follows it — only semicolons *inside* a literal are ignored.
    assert not is_safe_select("SELECT * FROM t WHERE col = 'a;b'; DELETE FROM t")


@pytest.mark.unit
def test_comment_smuggled_statement_rejected():
    from src.core.data.validate import is_safe_select

    # A forbidden keyword hidden behind a -- comment must still be caught once
    # comments are stripped (the comment is removed, exposing the real DELETE).
    assert not is_safe_select("SELECT 1 -- ok\n; DELETE FROM t")


@pytest.mark.unit
def test_comment_only_query_is_empty():
    from src.core.data.validate import UnsafeQueryError, ensure_select

    with pytest.raises(UnsafeQueryError):
        ensure_select("-- just a comment")


@pytest.mark.unit
def test_trailing_semicolon_only_is_allowed():
    from src.core.data.validate import is_safe_select

    assert is_safe_select("SELECT * FROM t;")
