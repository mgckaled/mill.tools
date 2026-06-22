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
