"""Unit tests for src/core/ml/labeling.py — class-based TF-IDF cluster names."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("sklearn")

from src.core.ml.labeling import label_clusters  # noqa: E402


@pytest.mark.unit
def test_discriminative_terms_per_cluster():
    doc_texts = [
        "whisper gpu transcription whisper gpu audio",
        "whisper transcription gpu whisper model",
        "duna herbert arrakis book duna herbert",
        "duna arrakis spice herbert duna",
    ]
    labels = np.array([0, 0, 1, 1])
    out = label_clusters(doc_texts, labels, top_n=3)

    assert set(out) == {0, 1}
    # Cluster 0 is about whisper/gpu; cluster 1 about duna/herbert.
    assert "whisper" in out[0]
    assert "duna" in out[1]
    # Discriminative: whisper must NOT be a top term of the duna cluster.
    assert "whisper" not in out[1]


@pytest.mark.unit
def test_noise_cluster_is_ignored():
    doc_texts = ["whisper gpu", "duna herbert", "isolated orphan content"]
    labels = np.array([0, 1, -1])
    out = label_clusters(doc_texts, labels)
    assert -1 not in out
    assert set(out) == {0, 1}


@pytest.mark.unit
def test_multiword_phrase_can_appear_as_a_label():
    # A discriminative trigram (no stopwords inside it) should be able to
    # surface as a cluster label now that ngram_range covers up to 3 words.
    doc_texts = [
        "processamento linguagem natural python processamento linguagem natural modelo",
        "processamento linguagem natural dados processamento linguagem natural treino",
        "duna herbert arrakis livro duna herbert",
        "duna arrakis especiaria herbert duna",
    ]
    labels = np.array([0, 0, 1, 1])
    out = label_clusters(doc_texts, labels, top_n=5)
    assert "processamento linguagem natural" in out[0]


@pytest.mark.unit
def test_stopwords_are_removed():
    doc_texts = ["the whisper and the gpu", "the whisper of the model"]
    labels = np.array([0, 0])
    out = label_clusters(doc_texts, labels, top_n=5)
    assert "the" not in out[0]
    assert "and" not in out[0]
    assert "whisper" in out[0]


@pytest.mark.unit
def test_empty_when_all_noise():
    out = label_clusters(["a", "b"], np.array([-1, -1]))
    assert out == {}


@pytest.mark.unit
def test_only_stopwords_yields_empty_labels():
    # A cluster whose text is all stopwords → empty vocabulary → empty list.
    out = label_clusters(["the and of", "the of and"], np.array([0, 0]))
    assert out == {0: []}


@pytest.mark.unit
def test_gate_blocks_when_ml_extra_missing(mocker):
    mocker.patch("src.core.ml.labeling.is_available", return_value=False)
    with pytest.raises(RuntimeError):
        label_clusters(["x"], np.array([0]))
