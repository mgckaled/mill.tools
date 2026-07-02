"""Unit tests for the `observatory` CLI subcommand (parser + runner)."""

from __future__ import annotations

import argparse

import pytest

from src.cli.observatory import add_observatory_parser


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_observatory_parser(sub)
    return parser.parse_args(["observatory", *argv])


@pytest.mark.unit
def test_status_parser_defaults():
    ns = _parse("status")
    assert ns.observatory_op == "status"
    assert callable(ns.func)


@pytest.mark.unit
def test_activity_parser_defaults():
    ns = _parse("activity")
    assert ns.observatory_op == "activity"
    assert ns.limit == 15


@pytest.mark.unit
def test_activity_parser_custom_limit():
    ns = _parse("activity", "--limit", "5")
    assert ns.limit == 5


@pytest.mark.unit
def test_run_status_prints_every_section(mocker, capsys):
    from src.core.observatory.status import (
        DomainStatus,
        GateStatus,
        MLConfigSnapshot,
    )

    mocker.patch(
        "src.core.observatory.status.gate_statuses",
        return_value=(GateStatus("[ml]", True, ""), GateStatus("[nlp]", False, "dica")),
    )
    mocker.patch(
        "src.core.observatory.status.domain_statuses",
        return_value=(DomainStatus("data_domain", 2, False),),
    )
    mocker.patch(
        "src.core.observatory.status.config_snapshot",
        return_value=MLConfigSnapshot(0.95, 8, 20, 0.6),
    )
    mocker.patch("src.cli.observatory._answer_times", return_value={})

    ns = _parse("status")
    ns.func(ns)

    out = capsys.readouterr().out
    assert "Gates e extras" in out
    assert "[✓] [ml]" in out
    assert "[✗] [nlp]" in out and "dica" in out
    assert "Domínio de dados" in out
    assert "Configuração em vigor" in out
    assert "Nenhuma resposta registrada" in out


@pytest.mark.unit
def test_run_activity_prints_entries(mocker, capsys):
    from src.core.observatory.activity import ActivityEntry

    mocker.patch(
        "src.core.observatory.activity.load_activity",
        return_value=[ActivityEntry("data", "outliers_detected", "12 linhas", 100.0)],
    )

    ns = _parse("activity")
    ns.func(ns)

    out = capsys.readouterr().out
    assert "12 linhas" in out
    assert "data" in out


@pytest.mark.unit
def test_run_activity_empty(mocker, capsys):
    mocker.patch("src.core.observatory.activity.load_activity", return_value=[])
    ns = _parse("activity")
    ns.func(ns)
    assert "Nenhuma atividade" in capsys.readouterr().out
