"""Unit tests for src/core/observatory/status.py — read-only ML status board."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from src.core.observatory import status


@pytest.mark.unit
def test_gate_statuses_returns_one_entry_per_engine():
    gates = status.gate_statuses()
    names = [g.name for g in gates]
    assert any("[ml]" in n for n in names)
    assert any("[nlp]" in n for n in names)
    assert any("Embedder" in n for n in names)
    assert all(isinstance(g.available, bool) for g in gates)


@pytest.mark.unit
def test_gate_statuses_reflects_missing_extra(mocker):
    mocker.patch("src.core.ml.deps.is_available", return_value=False)
    gates = status.gate_statuses()
    ml_gate = next(g for g in gates if g.name.startswith("[ml] "))
    assert ml_gate.available is False
    assert ml_gate.hint  # a setup hint is present when unavailable


@pytest.mark.unit
def test_gate_statuses_includes_ocr_ai_image_analysis_and_data_plot():
    gates = status.gate_statuses()
    names = [g.name for g in gates]
    assert any("[ocr]" in n for n in names)
    assert any("[ai-image]" in n for n in names)
    assert any("[analysis]" in n for n in names)
    assert any("[data-plot]" in n for n in names)


@pytest.mark.unit
def test_gate_statuses_reflects_missing_ocr(mocker):
    mocker.patch("src.core.document.ocr.is_available", return_value=False)
    gates = status.gate_statuses()
    ocr_gate = next(g for g in gates if g.name.startswith("[ocr]"))
    assert ocr_gate.available is False
    assert ocr_gate.hint


@pytest.mark.unit
def test_entity_glossary_status_absent_file(mocker, tmp_path):
    mocker.patch(
        "src.core.text.entities._glossary_path",
        return_value=tmp_path / "entity_glossary.json",
    )
    glossary = status.entity_glossary_status()
    assert glossary.exists is False
    assert glossary.n_patterns == 0


@pytest.mark.unit
def test_entity_glossary_status_reads_pattern_count(mocker, tmp_path):
    import json

    glossary_path = tmp_path / "entity_glossary.json"
    glossary_path.write_text(
        json.dumps(
            [
                {"label": "PRODUCT", "pattern": "mill.tools"},
                {"label": "ORG", "pattern": "Anthropic"},
            ]
        ),
        encoding="utf-8",
    )
    mocker.patch("src.core.text.entities._glossary_path", return_value=glossary_path)
    glossary = status.entity_glossary_status()
    assert glossary.exists is True
    assert glossary.n_patterns == 2


@pytest.mark.unit
def test_binary_statuses_returns_the_four_binaries():
    binaries = status.binary_statuses()
    names = [b.name for b in binaries]
    assert names == ["yt-dlp", "ffmpeg", "ffprobe", "tesseract"]


@pytest.mark.unit
def test_binary_statuses_reflects_a_missing_binary(mocker):
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("src.core.document.ocr._resolve_tesseract_cmd", return_value=None)
    binaries = status.binary_statuses()
    assert all(b.path is None for b in binaries)


@pytest.mark.unit
def test_binary_statuses_reflects_a_resolved_binary(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
    mocker.patch(
        "src.core.document.ocr._resolve_tesseract_cmd",
        return_value="/usr/bin/tesseract",
    )
    binaries = status.binary_statuses()
    assert all(b.path is not None for b in binaries)


@pytest.mark.unit
def test_cloud_provider_statuses_reflects_configured_keys(monkeypatch):
    monkeypatch.setattr("src.llm_factory._load_env_once", lambda: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)

    providers = status.cloud_provider_statuses()
    by_name = {p.name: p.configured for p in providers}
    assert by_name["Gemini (GOOGLE_API_KEY)"] is True
    assert by_name["GLM (ZHIPU_API_KEY)"] is False


@pytest.mark.unit
def test_cloud_provider_statuses_never_touches_the_real_env_file(monkeypatch):
    """A missing/absent .env must not raise — only reflect absence."""
    monkeypatch.setattr("src.llm_factory._load_env_once", lambda: None)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)

    providers = status.cloud_provider_statuses()
    assert all(p.configured is False for p in providers)


@pytest.mark.unit
def test_domain_statuses_covers_all_three_domains(tmp_path):
    # embed_space_id passed explicitly — a fresh tmp_path has no trained model
    # for any domain regardless, but this avoids the default() reading the
    # real ~/.mill-tools/rag/index_info.json sidecar off this machine.
    domains = status.domain_statuses(directory=tmp_path, embed_space_id="?:0")
    assert {d.domain for d in domains} == {
        "transcription_profile",
        "data_domain",
        "document_type",
    }
    assert all(d.n_labels == 0 for d in domains)  # nothing recorded in a fresh dir
    assert all(d.supervised is False for d in domains)


@pytest.mark.unit
def test_domain_statuses_reflects_recorded_labels(tmp_path):
    from src.core.ml.classify import DOMAIN_DATA, record_label

    record_label("/a.csv", "financial", directory=tmp_path, domain=DOMAIN_DATA)

    domains = status.domain_statuses(directory=tmp_path, embed_space_id="?:0")
    data_status = next(d for d in domains if d.domain == DOMAIN_DATA)
    assert data_status.n_labels == 1
    assert data_status.supervised is False  # a label alone isn't a trained model


@pytest.mark.unit
def test_domain_statuses_supervised_false_after_embed_space_changes(tmp_path):
    """M2: domain_statuses must not report supervised=True for a model
    trained on an embedding space that no longer matches the RAG's current
    one (embed model swapped + corpus reindexed)."""
    pytest.importorskip("sklearn")
    import numpy as np

    from src.core.ml.classify import DOMAIN_DATA, record_label, train_supervised
    from src.core.ml.types import DocumentMatrix

    labels = {}
    rows = []
    for i in range(4):
        p = f"/fin/{i}.txt"
        rows.append((p, [1.0, 0.05 * i]))
        labels[p] = "financial"
    for i in range(4):
        p = f"/log/{i}.txt"
        rows.append((p, [0.05 * i, 1.0]))
        labels[p] = "log"
    for path, profile in labels.items():
        record_label(path, profile, directory=tmp_path, domain=DOMAIN_DATA)
    from pathlib import Path

    resolved_labels = {str(Path(p).resolve()): v for p, v in labels.items()}
    dm = DocumentMatrix(
        X=np.array([v for _, v in rows], dtype=np.float32),
        source_paths=[str(Path(p).resolve()) for p, _ in rows],
        kinds=["data"] * len(rows),
    )
    train_supervised(
        dm,
        resolved_labels,
        directory=tmp_path,
        domain=DOMAIN_DATA,
        embed_space_id="model-a:2",
    )

    same_space = status.domain_statuses(directory=tmp_path, embed_space_id="model-a:2")
    assert next(d for d in same_space if d.domain == DOMAIN_DATA).supervised is True

    changed_space = status.domain_statuses(
        directory=tmp_path, embed_space_id="model-b:2"
    )
    assert next(d for d in changed_space if d.domain == DOMAIN_DATA).supervised is False


@pytest.mark.unit
def test_domain_statuses_default_reads_real_rag_index_sidecar(tmp_path, mocker):
    """embed_space_id=None (the production default) must read the RAG's real
    index_dir(), not silently stay at a hardcoded placeholder."""
    mocker.patch("src.core.rag.indexer.index_dir", return_value=tmp_path / "rag")
    spy = mocker.patch(
        "src.core.rag.stats.embed_space_id", return_value="probe-marker:9"
    )

    status.domain_statuses(directory=tmp_path)

    spy.assert_called_once_with(tmp_path / "rag")


@pytest.mark.unit
def test_config_snapshot_reads_real_defaults_not_a_stale_copy():
    snap = status.config_snapshot()
    assert snap.text_dedup_threshold == 0.95
    assert snap.image_dedup_max_distance == 8
    assert snap.auto_k_min_corpus == 20
    assert snap.mmr_lambda == 0.6


def _fake_ollama_module(model_names: list[str]) -> SimpleNamespace:
    models = [SimpleNamespace(model=n) for n in model_names]

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def list(self):
            return SimpleNamespace(models=models)

    return SimpleNamespace(Client=_FakeClient)


@pytest.mark.unit
def test_ollama_inventory_all_installed(mocker):
    names = [f"{n}:latest" for n in status._KNOWN_CUSTOM_MODELS]
    mocker.patch.dict(sys.modules, {"ollama": _fake_ollama_module(names)})

    inv = status.ollama_inventory()
    assert inv.reachable is True
    assert all(m.installed for m in inv.models)
    assert [m.name for m in inv.models] == list(status._KNOWN_CUSTOM_MODELS)


@pytest.mark.unit
def test_ollama_inventory_normalizes_the_latest_tag_and_flags_missing(mocker):
    mocker.patch.dict(
        sys.modules, {"ollama": _fake_ollama_module(["gemma3-4b-custom:latest"])}
    )

    inv = status.ollama_inventory()
    assert inv.reachable is True
    by_name = {m.name: m.installed for m in inv.models}
    assert by_name["gemma3-4b-custom"] is True
    assert by_name["moondream-custom"] is False


@pytest.mark.unit
def test_ollama_inventory_package_missing(mocker):
    mocker.patch.dict(sys.modules, {"ollama": None})
    inv = status.ollama_inventory()
    assert inv.reachable is False
    assert inv.models == ()


@pytest.mark.unit
def test_ollama_inventory_passes_a_bounded_timeout(mocker):
    """A slow/half-open Ollama service must not hang this read forever."""
    captured: dict = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def list(self):
            return SimpleNamespace(models=[])

    mocker.patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=_FakeClient)})
    status.ollama_inventory()
    assert captured.get("timeout") == status._OLLAMA_TIMEOUT_S


@pytest.mark.unit
def test_ollama_inventory_service_unreachable(mocker):
    class _FailingClient:
        def __init__(self, **kwargs):
            pass

        def list(self):
            raise ConnectionError("refused")

    mocker.patch.dict(sys.modules, {"ollama": SimpleNamespace(Client=_FailingClient)})
    inv = status.ollama_inventory()
    assert inv.reachable is False
    assert inv.models == ()
