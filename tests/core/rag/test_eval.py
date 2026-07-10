"""Unit tests for src/core/rag/eval.py — the retrieval-only eval runner.

The runner is injectable (``embed_query_fn`` + store, the same seam as
``retriever.retrieve``), so these build a tiny ``VectorStore`` with known
vectors and a fixed query embedding — no Ollama — exactly like
``test_retriever.py``.
"""

from __future__ import annotations

import numpy as np
import pytest


def _meta(source: str, idx: int = 0, *, kind: str = "transcription", text: str = "x"):
    from src.core.rag.types import ChunkMeta

    return ChunkMeta(source_path=source, kind=kind, mtime=1.0, chunk_idx=idx, text=text)


def _store_with(rows, *, dim: int = 3):
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=dim)
    vecs = np.array([v for v, _ in rows], dtype=np.float32)
    store.add(vecs, [m for _, m in rows])
    return store


def _fixed_query(vec):
    """An embed_query_fn that ignores the text and returns a fixed vector."""
    arr = np.array(vec, dtype=np.float32)
    return lambda _q: arr


@pytest.mark.unit
def test_golden_question_is_out_of_corpus_flag():
    from src.core.rag.eval import GoldenQuestion

    assert GoldenQuestion("q").is_out_of_corpus is True
    assert GoldenQuestion("q", expected=("a.txt",)).is_out_of_corpus is False


@pytest.mark.unit
def test_run_eval_covered_hit_rank_one():
    """A covered question whose expected document is retrieved first: hit,
    rank 1, MRR 1.0, and the coverage flag stays off (high cosine)."""
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with(
        [([1, 0, 0], _meta("aula.txt")), ([0, 1, 0], _meta("outro.txt"))]
    )
    result = run_eval(
        [GoldenQuestion("alpha beta", expected=("aula.txt",))],
        store,
        _fixed_query([1, 0, 0]),
    )
    (outcome,) = result.outcomes
    assert outcome.hit is True
    assert outcome.rank == 1
    assert outcome.flag_fired is False
    assert result.metrics.hit_rate == pytest.approx(1.0)
    assert result.metrics.mrr == pytest.approx(1.0)


@pytest.mark.unit
def test_run_eval_covered_miss_when_expected_absent():
    """A covered question whose expected document is not in the retrieved set:
    miss, rank None, hit_rate 0."""
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with(
        [([1, 0, 0], _meta("aula.txt")), ([0, 1, 0], _meta("outro.txt"))]
    )
    result = run_eval(
        [GoldenQuestion("alpha beta", expected=("inexistente.txt",))],
        store,
        _fixed_query([1, 0, 0]),
    )
    (outcome,) = result.outcomes
    assert outcome.hit is False
    assert outcome.rank is None
    assert result.metrics.hit_rate == pytest.approx(0.0)
    assert result.metrics.mrr == pytest.approx(0.0)


@pytest.mark.unit
def test_run_eval_mrr_reflects_rank_of_first_expected():
    """The expected document sits second among the distinct sources → MRR 0.5."""
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with(
        [([1, 0, 0], _meta("first.txt")), ([0.9, 0.1, 0], _meta("second.txt"))]
    )
    result = run_eval(
        [GoldenQuestion("alpha beta", expected=("second.txt",))],
        store,
        _fixed_query([1, 0, 0]),
    )
    (outcome,) = result.outcomes
    assert outcome.rank == 2
    assert result.metrics.mrr == pytest.approx(0.5)


@pytest.mark.unit
def test_run_eval_out_of_corpus_flag_fires_correctly():
    """An out-of-corpus question whose best cosine is below the threshold: the
    flag fires and that counts as correct (flag_accuracy 1.0)."""
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with(
        [([1, 0, 0], _meta("aula.txt")), ([0, 1, 0], _meta("outro.txt"))]
    )
    # Query orthogonal to every chunk → pool_max_score ~0 < 0.72 → flag fires.
    result = run_eval(
        [GoldenQuestion("nada a ver com o acervo")],
        store,
        _fixed_query([0, 0, 1]),
    )
    (outcome,) = result.outcomes
    assert outcome.is_out_of_corpus is True
    assert outcome.flag_fired is True
    assert outcome.flag_correct is True
    assert result.metrics.flag_accuracy == pytest.approx(1.0)
    assert result.metrics.n_out_of_corpus == 1
    assert result.metrics.n_covered == 0


@pytest.mark.unit
def test_run_eval_flag_accuracy_penalizes_false_low_coverage():
    """A covered question whose best cosine is (artificially) below threshold
    would fire the flag wrongly — flag_correct is False for it."""
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with([([1, 0, 0], _meta("aula.txt"))])
    # Weak cosine (0.2) to the only chunk → below 0.72 → flag fires, but the
    # question *is* covered, so firing is the wrong call.
    result = run_eval(
        [GoldenQuestion("alpha beta", expected=("aula.txt",))],
        store,
        _fixed_query([0.2, 0.98, 0]),
    )
    (outcome,) = result.outcomes
    assert outcome.flag_fired is True
    assert outcome.flag_correct is False
    assert result.metrics.flag_accuracy == pytest.approx(0.0)


@pytest.mark.unit
def test_run_eval_basename_fallback_matches_moved_corpus():
    """An expected path with a different directory still matches a retrieved
    source by basename — a golden set survives the corpus moving folders."""
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with([([1, 0, 0], _meta("aula.txt"))])
    result = run_eval(
        [GoldenQuestion("alpha beta", expected=(r"D:/old/path/aula.txt",))],
        store,
        _fixed_query([1, 0, 0]),
    )
    assert result.outcomes[0].hit is True


@pytest.mark.unit
def test_run_eval_records_index_context():
    """The run carries k, embed_space_id/scheme, doc/chunk counts and timestamp
    — the context needed to compare two runs honestly."""
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with(
        [([1, 0, 0], _meta("aula.txt", 0)), ([0.9, 0.1, 0], _meta("aula.txt", 1))]
    )
    result = run_eval(
        [GoldenQuestion("alpha beta", expected=("aula.txt",))],
        store,
        _fixed_query([1, 0, 0]),
        k=8,
        embed_space_id="nomic-embed-custom:768:scheme-x",
        embed_scheme="scheme-x",
        now=1234.5,
    )
    assert result.k == 8
    assert result.embed_space_id == "nomic-embed-custom:768:scheme-x"
    assert result.embed_scheme == "scheme-x"
    assert result.n_docs == 1  # both chunks belong to one document
    assert result.n_chunks == 2
    assert result.timestamp == 1234.5


@pytest.mark.unit
def test_run_eval_empty_golden_yields_zeroed_metrics():
    from src.core.rag.eval import run_eval

    store = _store_with([([1, 0, 0], _meta("aula.txt"))])
    result = run_eval([], store, _fixed_query([1, 0, 0]))
    m = result.metrics
    assert (m.n_covered, m.n_out_of_corpus) == (0, 0)
    assert (m.hit_rate, m.mrr, m.flag_accuracy) == (0.0, 0.0, 0.0)
    assert result.outcomes == ()


@pytest.mark.unit
def test_run_eval_on_progress_called_per_question_and_can_abort():
    """on_progress fires once per question (the cancellation seam) — a callback
    that raises aborts the run between questions, mirroring index_worker."""
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with([([1, 0, 0], _meta("aula.txt"))])
    calls: list[tuple[int, int]] = []

    def _progress(done: int, total: int) -> None:
        calls.append((done, total))
        if done == 2:
            raise KeyboardInterrupt  # stand-in for the worker's _Cancelled

    golden = [GoldenQuestion(f"q{i}") for i in range(5)]
    with pytest.raises(KeyboardInterrupt):
        run_eval(golden, store, _fixed_query([0, 0, 1]), on_progress=_progress)
    assert calls == [(1, 5), (2, 5)]


@pytest.mark.unit
def test_run_eval_uses_default_threshold_from_recommend():
    """The coverage flag reuses recommend.DEFAULT_IN_CORPUS_THRESHOLD (single
    source of truth) — not a private copy."""
    from src.core.ml.recommend import DEFAULT_IN_CORPUS_THRESHOLD
    from src.core.rag.eval import GoldenQuestion, run_eval

    store = _store_with([([1, 0, 0], _meta("aula.txt"))])
    # cosine just below the shared threshold → flag fires.
    below = DEFAULT_IN_CORPUS_THRESHOLD - 0.05
    result = run_eval(
        [GoldenQuestion("nada")],
        store,
        _fixed_query([below, np.sqrt(1 - below**2), 0]),
    )
    assert result.outcomes[0].flag_fired is True


@pytest.mark.unit
def test_seed_and_suggestions_shapes():
    from src.core.rag.eval import seed_golden, suggested_covered

    seeds = seed_golden()
    assert len(seeds) == 5
    assert all(g.is_out_of_corpus for g in seeds)

    suggestions = suggested_covered()
    assert len(suggestions) == 10
    assert all(s.question and s.hint for s in suggestions)
