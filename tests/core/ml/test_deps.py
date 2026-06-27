"""Unit tests for src/core/ml/deps.py — the scikit-learn availability gate."""

from __future__ import annotations

import sys

import pytest

from src.core.ml.deps import SETUP_HINT, is_available


@pytest.mark.unit
def test_is_available_true_when_sklearn_importable():
    # The [ml] extra is installed in the test environment.
    assert is_available() is True


@pytest.mark.unit
def test_is_available_false_when_sklearn_missing(mocker):
    # Shadow the module with None so `import sklearn` raises ImportError,
    # the same pattern used to gate the RAG embedder.
    mocker.patch.dict(sys.modules, {"sklearn": None})
    assert is_available() is False


@pytest.mark.unit
def test_setup_hint_mentions_the_extra():
    assert "ml" in SETUP_HINT
