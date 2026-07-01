"""Unit tests for src/core/observatory/status.py — read-only ML status board."""

from __future__ import annotations

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
def test_domain_statuses_covers_all_three_domains(tmp_path):
    domains = status.domain_statuses(directory=tmp_path)
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

    domains = status.domain_statuses(directory=tmp_path)
    data_status = next(d for d in domains if d.domain == DOMAIN_DATA)
    assert data_status.n_labels == 1
    assert data_status.supervised is False  # a label alone isn't a trained model


@pytest.mark.unit
def test_config_snapshot_reads_real_defaults_not_a_stale_copy():
    snap = status.config_snapshot()
    assert snap.text_dedup_threshold == 0.95
    assert snap.image_dedup_max_distance == 8
    assert snap.auto_k_min_corpus == 20
    assert snap.mmr_lambda == 0.6
