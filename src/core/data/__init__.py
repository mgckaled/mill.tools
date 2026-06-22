"""Structured-data module core (PR9): query-first manipulation over DuckDB.

Pure (no Flet), reusable by CLI and GUI. The only boundary with the DuckDB
engine lives in ``engine.py`` (injectable, like the RAG ``embedder``); the LLM
that translates Portuguese to SQL lives in ``nl2sql.py`` and never sees a data
row — only column names/types.
"""
