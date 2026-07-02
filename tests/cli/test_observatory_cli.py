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
        BinaryStatus,
        CloudProviderStatus,
        DomainStatus,
        EntityGlossaryStatus,
        GateStatus,
        MLConfigSnapshot,
        OllamaInventoryStatus,
        OllamaModelStatus,
    )

    mocker.patch(
        "src.core.observatory.status.gate_statuses",
        return_value=(GateStatus("[ml]", True, ""), GateStatus("[nlp]", False, "dica")),
    )
    mocker.patch(
        "src.core.observatory.status.entity_glossary_status",
        return_value=EntityGlossaryStatus(True, 3),
    )
    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=OllamaInventoryStatus(
            True,
            (
                OllamaModelStatus("gemma3-4b-custom", True),
                OllamaModelStatus("moondream-custom", False),
            ),
        ),
    )
    mocker.patch(
        "src.core.observatory.status.binary_statuses",
        return_value=(
            BinaryStatus("ffmpeg", "/usr/bin/ffmpeg"),
            BinaryStatus("tesseract", None),
        ),
    )
    mocker.patch(
        "src.core.observatory.status.cloud_provider_statuses",
        return_value=(
            CloudProviderStatus("Gemini (GOOGLE_API_KEY)", True),
            CloudProviderStatus("GLM (ZHIPU_API_KEY)", False),
        ),
    )
    mocker.patch(
        "src.core.observatory.status.domain_statuses",
        return_value=(DomainStatus("data_domain", 2, False),),
    )
    mocker.patch(
        "src.core.observatory.status.config_snapshot",
        return_value=MLConfigSnapshot(0.95, 8, 20, 0.6),
    )
    mocker.patch("src.core.observatory.model_timing.load_timings", return_value=[])

    ns = _parse("status")
    ns.func(ns)

    out = capsys.readouterr().out
    assert "Gates e extras" in out
    assert "[✓] [ml]" in out
    assert "[✗] [nlp]" in out and "dica" in out
    assert "Glossário de entidades: 3 padrão" in out
    assert "Modelos Ollama" in out
    assert "[✓] gemma3-4b-custom" in out
    assert "[✗] moondream-custom" in out
    assert "Binários externos" in out
    assert "[✓] ffmpeg: /usr/bin/ffmpeg" in out
    assert "[✗] tesseract: não encontrado no PATH" in out
    assert "Provedores de nuvem" in out
    assert "[✓] Gemini (GOOGLE_API_KEY): configurado" in out
    assert "[✗] GLM (ZHIPU_API_KEY): chave ausente" in out
    assert "Domínio de dados" in out
    assert "Configuração em vigor" in out
    assert "LLM (texto)" in out
    assert "VLM (descrição de imagem)" in out
    assert "Embedder" in out
    assert out.count("Nenhuma resposta registrada ainda.") == 3


@pytest.mark.unit
def test_run_status_breaks_down_timings_by_domain(mocker, capsys):
    from src.core.observatory.model_timing import TimingEntry
    from src.core.observatory.status import (
        DomainStatus,
        MLConfigSnapshot,
        OllamaInventoryStatus,
    )

    mocker.patch("src.core.observatory.status.gate_statuses", return_value=())
    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=OllamaInventoryStatus(False, ()),
    )
    mocker.patch(
        "src.core.observatory.status.domain_statuses",
        return_value=(DomainStatus("data_domain", 0, False),),
    )
    mocker.patch(
        "src.core.observatory.status.config_snapshot",
        return_value=MLConfigSnapshot(0.95, 8, 20, 0.6),
    )
    mocker.patch(
        "src.core.observatory.model_timing.load_timings",
        return_value=[
            TimingEntry("gemini-2.5-flash", "llm", 4.0, 1.0),
            TimingEntry("moondream-custom", "vlm", 2.0, 2.0),
            TimingEntry("nomic-embed-custom", "embed", 0.3, 3.0),
        ],
    )

    ns = _parse("status")
    ns.func(ns)

    out = capsys.readouterr().out
    assert "gemini-2.5-flash" in out
    assert "moondream-custom" in out
    assert "não está acessível" in out  # Ollama inventory, unreachable branch
    assert "nomic-embed-custom" in out


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


@pytest.mark.unit
def test_logs_parser_defaults():
    ns = _parse("logs")
    assert ns.observatory_op == "logs"
    assert ns.limit == 50


@pytest.mark.unit
def test_logs_parser_custom_limit():
    ns = _parse("logs", "--limit", "5")
    assert ns.limit == 5


@pytest.mark.unit
def test_run_logs_prints_entries(mocker, capsys):
    from src.core.observatory.logs import LogEntry

    mocker.patch(
        "src.core.observatory.logs.load_logs",
        return_value=[LogEntry("audio", "convert", "ffmpeg not found", 100.0)],
    )

    ns = _parse("logs")
    ns.func(ns)

    out = capsys.readouterr().out
    assert "ffmpeg not found" in out
    assert "audio" in out
    assert "convert" in out


@pytest.mark.unit
def test_run_logs_empty(mocker, capsys):
    mocker.patch("src.core.observatory.logs.load_logs", return_value=[])
    ns = _parse("logs")
    ns.func(ns)
    assert "Nenhuma falha" in capsys.readouterr().out
