"""Tests for the indexable data card."""

from pathlib import Path

import pytest

from src.core.data.types import ColumnInfo, DataFile, QueryResult


def _file(name="vendas.csv", n_rows=3):
    return DataFile(
        path=Path(name),
        view_name="vendas",
        n_rows=n_rows,
        columns=[ColumnInfo("produto", "VARCHAR"), ColumnInfo("valor", "VARCHAR")],
    )


def _sample():
    return QueryResult(
        columns=["produto", "valor"],
        rows=[("maca", "R$ 1,50"), ("banana", None)],
        elapsed=0.0,
        n_rows=2,
    )


@pytest.mark.unit
def test_build_data_card_includes_schema_profile_sample():
    from src.core.data.datacard import build_data_card

    card = build_data_card(_file(), "valor: VARCHAR · 0 nulos", _sample())
    assert "ARQUIVO: vendas.csv" in card
    assert "formato: CSV" in card
    assert "produto(VARCHAR)" in card
    assert "PERFIL (SUMMARIZE):" in card
    assert "valor: VARCHAR" in card
    assert "AMOSTRA" in card
    assert "maca\tR$ 1,50" in card
    # No assessment supplied → that section is absent.
    assert "AVALIAÇÃO DA IA" not in card


@pytest.mark.unit
def test_build_data_card_appends_assessment_when_given():
    from src.core.data.datacard import build_data_card

    card = build_data_card(
        _file(), "perfil", _sample(), assessment="- coluna valor é texto"
    )
    assert "AVALIAÇÃO DA IA:" in card
    assert "coluna valor é texto" in card


@pytest.mark.unit
def test_sample_to_text_handles_nulls_and_empty():
    from src.core.data.datacard import sample_to_text

    assert sample_to_text(_sample()) == "produto\tvalor\nmaca\tR$ 1,50\nbanana\t"
    empty = QueryResult(columns=[], rows=[], elapsed=0.0, n_rows=0)
    assert sample_to_text(empty) == "(sem linhas)"


@pytest.mark.unit
@pytest.mark.parametrize(
    "name,label",
    [("a.csv", "CSV"), ("a.parquet", "Parquet"), ("a.xlsx", "XLSX"), ("a.bin", "?")],
)
def test_format_label(name, label):
    from src.core.data.datacard import format_label

    assert format_label(Path(name)) == label


@pytest.mark.unit
def test_card_for_path_reads_real_file(csv_sales):
    from src.core.data.datacard import card_for_path

    card = card_for_path(csv_sales)
    assert "ARQUIVO: vendas.csv" in card
    assert "produto" in card
    # No cached assessment on a fresh file → no IA section.
    assert "AVALIAÇÃO DA IA" not in card


@pytest.mark.unit
def test_card_for_path_scans_the_file_only_once(csv_sales, mocker):
    """Regression: card_for_path used to scan the file twice (its own scan_file
    plus a second one inside profile_text) before profile_text learned to
    accept an already-scanned DataFile."""
    from src.core.data import scanner
    from src.core.data.datacard import card_for_path

    spy = mocker.spy(scanner, "scan_file")
    card_for_path(csv_sales)
    assert spy.call_count == 1


@pytest.mark.unit
def test_card_for_path_folds_in_cached_assessment(csv_sales, tmp_path, mocker):
    from src.core.data import assess, datacard

    # Seed a cached assessment for this file; card_for_path must reuse it.
    cache = tmp_path / "cache.json"
    assess.save_assessment(csv_sales, "## ok\n- consistente", cache_file=cache)
    mocker.patch.object(assess, "_cache_file", return_value=cache)

    card = datacard.card_for_path(csv_sales)
    assert "AVALIAÇÃO DA IA:" in card
    assert "consistente" in card
