"""Local fixtures for the data-module tests: small real CSV/JSON files.

DuckDB runs in-process (no ffmpeg/network/GPU), so these qualify as ``unit``
just like the numpy-based RAG tests.
"""

import pytest


@pytest.fixture
def csv_sales(tmp_path):
    """CSV with a categorical + two numeric columns (UTF-8)."""
    p = tmp_path / "vendas.csv"
    p.write_text(
        "produto,qtd,preco\nmaca,3,1.5\nbanana,5,0.8\nmaca,2,1.5\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def csv_people_cp1252(tmp_path):
    """CSV written in cp1252 (the classic Windows encoding pain)."""
    p = tmp_path / "pessoas.csv"
    p.write_bytes("nome,cidade\nJoão,São Paulo\nMaría,Córdoba\n".encode("cp1252"))
    return p


@pytest.fixture
def json_file(tmp_path):
    """A small JSON array of objects."""
    p = tmp_path / "itens.json"
    p.write_text(
        '[{"id": 1, "nome": "a"}, {"id": 2, "nome": "b"}]',
        encoding="utf-8",
    )
    return p
