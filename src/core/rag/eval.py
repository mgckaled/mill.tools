"""Retrieval-only evaluation harness for the local RAG (PLANO_RAG_EVAL).

A small set of *golden questions* with an expected answer, run through the real
production retrieval path (``retriever.retrieve`` — pool + MMR), reporting
hit-rate@k, MRR and the coverage-flag accuracy. It is the permanent instrument
the earlier embedding-space and multi-turn plans lacked: without it, every
future tuning (a reranker, a chunking change, a model swap) is blind.

**Retrieval-only by design.** No LLM call is made — the harness is
deterministic, fast and cheap. Judging the *generated answer* (LLM-as-judge) is
explicitly out of scope; it is non-deterministic and measures generation, not
retrieval.

Two kinds of golden question:

- **covered** — a question plus one or more expected source documents (by
  resolved path). A *hit* is any expected document appearing among the distinct
  sources of the retrieved chunks.
- **out-of-corpus** — a question with no expected document. The "right answer"
  is that the low-coverage flag fires (``pool_max_score`` below the same
  ``DEFAULT_IN_CORPUS_THRESHOLD`` the Conversa uses).

The question is embedded and retrieved **raw** — condensation belongs to a
conversation; golden questions are standalone by definition, so rewriting them
would measure something else. The runner is injectable (``embed_query_fn`` +
``store``, the same seam as ``retriever.retrieve``) so it is unit-testable
without a running Ollama.

Comparability: a run records the ``embed_space_id`` it ran under. Two runs are
only comparable when they share it — a reindex under a new model/scheme moves
every cosine into a different space, so comparing across it would report noise
as regression (the recurring lesson of ``PLANO_RAG_ESPACO_EMBEDDING``).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from src.core.io_atomic import atomic_write_text
from src.core.ml.recommend import DEFAULT_IN_CORPUS_THRESHOLD
from src.core.rag.retriever import retrieve
from src.core.rag.store import VectorStore

logger = logging.getLogger(__name__)

# The Conversa's default k (retriever.retrieve / run_ai_answer both default to
# 6). The eval runs at the same k the product uses, so what it measures matches
# what the user experiences; the value is recorded in the result regardless.
DEFAULT_K = 6


@dataclass(frozen=True, slots=True)
class GoldenQuestion:
    """One evaluation question. ``expected`` empty means out-of-corpus."""

    question: str
    expected: tuple[str, ...] = ()  # resolved source paths; empty = out-of-corpus

    @property
    def is_out_of_corpus(self) -> bool:
        """True when the question is expected to *not* be covered by the corpus."""
        return not self.expected


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A covered-question starter shown by ``ai eval list``.

    The 10 covered questions of the threshold-calibration seed can't be shipped
    active — their expected documents are the user's own corpus paths, which
    this code can't know. They live here as prompts instead: the user copies one
    and supplies the real document via ``ai eval add --expect``. Not persisted.
    """

    question: str
    hint: str  # the source theme, e.g. "romances de Duna"


@dataclass(frozen=True, slots=True)
class QuestionOutcome:
    """The result of running one golden question through retrieval."""

    question: str
    is_out_of_corpus: bool
    hit: bool  # covered: an expected doc was retrieved; out-of-corpus: always False
    rank: (
        int | None
    )  # 1-based rank of the first expected doc among sources; None if missed
    pool_max_score: float  # best dense cosine over every scope-respecting candidate
    flag_fired: bool  # low-coverage flag (pool_max_score < threshold)
    flag_correct: bool  # covered -> flag should stay off; out-of-corpus -> should fire


@dataclass(frozen=True, slots=True)
class EvalMetrics:
    """Aggregate metrics of one evaluation run."""

    n_covered: int
    n_out_of_corpus: int
    hit_rate: float  # fraction of covered questions with a hit (0.0 when none)
    mrr: float  # mean reciprocal rank over covered questions (0.0 when none)
    mean_covered_score: float  # mean pool_max_score of covered questions
    mean_out_score: float  # mean pool_max_score of out-of-corpus questions
    flag_accuracy: float  # fraction of all questions whose flag matched expectation


@dataclass(frozen=True, slots=True)
class EvalRunResult:
    """One evaluation run: aggregate metrics plus the context to compare it.

    ``outcomes`` is the per-question detail, used to render the immediate
    report; it is *not* persisted (the run history keeps only the aggregate
    ``metrics`` + context, to stay small — see ``rag_eval.json``). A loaded run
    therefore has ``outcomes=()``.
    """

    metrics: EvalMetrics
    k: int
    embed_space_id: str  # comparability key ("{model}:{dim}:{scheme}")
    embed_scheme: str  # scheme component, kept for display alongside the id
    n_docs: int
    n_chunks: int
    timestamp: float
    outcomes: tuple[QuestionOutcome, ...] = ()


def _distinct_sources(hits: Sequence) -> list[str]:
    """The retrieved chunks' source documents, de-duplicated, in rank order."""
    seen: list[str] = []
    for h in hits:
        sp = h.meta.source_path
        if sp not in seen:
            seen.append(sp)
    return seen


def _matches(expected: str, source: str) -> bool:
    """True when a retrieved ``source`` satisfies an ``expected`` path.

    Exact resolved-path equality first (what ``add_question`` stores and what
    ``ChunkMeta.source_path`` holds), then a basename fallback so a golden set
    survives the corpus moving between drives/folders — the same robustness the
    CLI's ``_resolve_doc_path`` already applies.
    """
    if expected == source:
        return True
    return Path(expected).name == Path(source).name


def _rank_of_expected(expected: tuple[str, ...], sources: list[str]) -> int | None:
    """1-based rank of the first source matching any expected path, or None."""
    for rank, source in enumerate(sources, 1):
        if any(_matches(e, source) for e in expected):
            return rank
    return None


def _mean(values: Sequence[float]) -> float:
    """Arithmetic mean, 0.0 for an empty sequence (never divides by zero)."""
    return sum(values) / len(values) if values else 0.0


def _compute_metrics(outcomes: Sequence[QuestionOutcome]) -> EvalMetrics:
    """Aggregate per-question outcomes into the run's metrics."""
    covered = [o for o in outcomes if not o.is_out_of_corpus]
    out = [o for o in outcomes if o.is_out_of_corpus]
    n_cov = len(covered)
    hit_rate = sum(1 for o in covered if o.hit) / n_cov if n_cov else 0.0
    mrr = _mean([1.0 / o.rank if o.rank else 0.0 for o in covered]) if covered else 0.0
    return EvalMetrics(
        n_covered=n_cov,
        n_out_of_corpus=len(out),
        hit_rate=hit_rate,
        mrr=mrr,
        mean_covered_score=_mean([o.pool_max_score for o in covered]),
        mean_out_score=_mean([o.pool_max_score for o in out]),
        flag_accuracy=_mean([1.0 if o.flag_correct else 0.0 for o in outcomes]),
    )


def run_eval(
    golden: Sequence[GoldenQuestion],
    store: VectorStore,
    embed_query_fn: Callable[[str], np.ndarray],
    *,
    k: int = DEFAULT_K,
    threshold: float = DEFAULT_IN_CORPUS_THRESHOLD,
    embed_space_id: str = "?",
    embed_scheme: str = "?",
    now: float | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> EvalRunResult:
    """Run every golden question through retrieval and aggregate the metrics.

    Each question is retrieved **raw** over the whole corpus (``scope=None``)
    with the production ``retrieve()`` path (pool + MMR) — evaluating a
    different path would measure a different thing. ``pool_max_score`` (the best
    dense cosine over every candidate, not just the MMR-kept hits) drives the
    coverage flag, exactly as ``run_ai_answer`` does.

    Args:
        golden: The golden questions to evaluate.
        store: The persisted vector store to search.
        embed_query_fn: Maps a query string to its embedding (injected so the
            harness is testable without Ollama).
        k: Chunks retrieved per question (the run records it).
        threshold: Coverage-flag cutoff — a question whose ``pool_max_score`` is
            below it is flagged low-coverage. Defaults to the same
            ``DEFAULT_IN_CORPUS_THRESHOLD`` the Conversa uses (single source of
            truth — never recomputed here).
        embed_space_id: The index's embedding-space id, recorded for
            comparability (callers pass ``rag.stats.embed_space_id``).
        embed_scheme: The content-scheme component, recorded for display.
        now: Injectable epoch seconds (deterministic tests); wall clock default.
        on_progress: Optional ``(done, total)`` callback, called after each
            question — the cancellation seam (a caller whose callback raises
            aborts the run between questions, mirroring ``index_worker``).

    Returns:
        An ``EvalRunResult`` carrying the aggregate metrics, the per-question
        ``outcomes`` (transient) and the context to compare it to another run.
    """
    outcomes: list[QuestionOutcome] = []
    total = len(golden)
    for i, gq in enumerate(golden, 1):
        result = retrieve(gq.question, store, embed_query_fn, k=k, scope=None)
        sources = _distinct_sources(result.hits)
        rank = None if gq.is_out_of_corpus else _rank_of_expected(gq.expected, sources)
        flag_fired = result.pool_max_score < threshold
        outcomes.append(
            QuestionOutcome(
                question=gq.question,
                is_out_of_corpus=gq.is_out_of_corpus,
                hit=rank is not None,
                rank=rank,
                pool_max_score=result.pool_max_score,
                flag_fired=flag_fired,
                flag_correct=flag_fired if gq.is_out_of_corpus else not flag_fired,
            )
        )
        if on_progress is not None:
            on_progress(i, total)

    return EvalRunResult(
        metrics=_compute_metrics(outcomes),
        k=k,
        embed_space_id=embed_space_id,
        embed_scheme=embed_scheme,
        n_docs=len({m.source_path for m in store.meta}),
        n_chunks=len(store),
        timestamp=now if now is not None else time.time(),
        outcomes=tuple(outcomes),
    )


# ── Seed golden set (PLANO_RAG_EVAL, Fase 1) ─────────────────────────────────
#
# Five out-of-corpus questions ship active — they need no corpus paths, so they
# exercise the coverage flag from the first run. Topics mirror the threshold
# calibration's out-of-corpus set (recommend.py): cooking, car maintenance,
# chess, taxes, dog training — subjects a personal AI/tech/Dune corpus should
# not cover, so a correct index flags them low-coverage.
_SEED_OUT_OF_CORPUS: tuple[str, ...] = (
    "Como preparar um risoto de cogumelos cremoso?",
    "De quantos em quantos quilômetros devo trocar o óleo do carro?",
    "Qual é a melhor abertura de xadrez para iniciantes?",
    "Como declarar imposto de renda sendo autônomo?",
    "Como ensinar um cachorro a sentar no comando?",
)

# The calibration's ten covered questions, shipped as prompts (their expected
# documents are the user's own corpus paths — unknowable here). ``ai eval list``
# shows them so the user can add each with the real document via ``--expect``.
_SUGGESTED_COVERED: tuple[Suggestion, ...] = (
    Suggestion("O que motiva Paul Atreides a se aliar aos Fremen?", "romances de Duna"),
    Suggestion(
        "Qual é a importância da especiaria melange em Duna?", "romances de Duna"
    ),
    Suggestion(
        "Como a Bene Gesserit exerce influência sobre a política do Império?",
        "romances de Duna",
    ),
    Suggestion("Quem são os Mentats e qual é a função deles?", "romances de Duna"),
    Suggestion(
        "Quais foram os principais pontos do vídeo sobre modelos de linguagem?",
        "transcrições de tech/IA",
    ),
    Suggestion(
        "O que o material explica sobre embeddings e busca semântica?",
        "transcrições de tech/IA",
    ),
    Suggestion(
        "Como o material descreve o funcionamento de um pipeline RAG?",
        "transcrições de tech/IA",
    ),
    Suggestion(
        "Que técnicas de avaliação de recuperação o material menciona?",
        "transcrições de tech/IA",
    ),
    Suggestion(
        "Quais princípios a constituição do Claude usa para respostas úteis?",
        "Constituição do Claude",
    ),
    Suggestion(
        "Como a constituição do Claude trata pedidos potencialmente prejudiciais?",
        "Constituição do Claude",
    ),
)


def seed_golden() -> tuple[GoldenQuestion, ...]:
    """The default golden set for a fresh install: the five out-of-corpus seeds."""
    return tuple(GoldenQuestion(question=q) for q in _SEED_OUT_OF_CORPUS)


def suggested_covered() -> tuple[Suggestion, ...]:
    """Covered-question prompts to seed a golden set with (see ``Suggestion``)."""
    return _SUGGESTED_COVERED


# ── Persistence: golden set + run history (PLANO_RAG_EVAL, Fase 2) ────────────
#
# ~/.mill-tools/rag_eval.json holds both the golden set and a small history of
# runs (last _MAX_RUNS — the model_timing per-bucket idea, but a flat cut here
# since one run stream). Its shape is a JSON object ({golden, runs}), *not* the
# flat append-only array of _jsonlog (which is for the feedback log), so it gets
# its own atomic load/save. Owner of the file: this module.
_MAX_RUNS = 20


@dataclass(frozen=True, slots=True)
class EvalData:
    """The persisted evaluation state: the golden set and the run history."""

    golden: tuple[GoldenQuestion, ...]
    runs: tuple[EvalRunResult, ...]


def eval_store_path() -> Path:
    """Canonical on-disk location for the eval golden set + run history."""
    return Path.home() / ".mill-tools" / "rag_eval.json"


def _golden_to_dict(g: GoldenQuestion) -> dict:
    return {"question": g.question, "expected": list(g.expected)}


def _golden_from_dict(raw: dict) -> GoldenQuestion:
    return GoldenQuestion(
        question=str(raw["question"]),
        expected=tuple(str(e) for e in raw.get("expected", [])),
    )


def _run_to_dict(r: EvalRunResult) -> dict:
    """Serialize a run to the aggregate record kept on disk (no per-question
    ``outcomes`` — those are transient, used only for the immediate report)."""
    m = r.metrics
    return {
        "timestamp": r.timestamp,
        "k": r.k,
        "embed_space_id": r.embed_space_id,
        "embed_scheme": r.embed_scheme,
        "n_docs": r.n_docs,
        "n_chunks": r.n_chunks,
        "metrics": {
            "n_covered": m.n_covered,
            "n_out_of_corpus": m.n_out_of_corpus,
            "hit_rate": m.hit_rate,
            "mrr": m.mrr,
            "mean_covered_score": m.mean_covered_score,
            "mean_out_score": m.mean_out_score,
            "flag_accuracy": m.flag_accuracy,
        },
    }


def _run_from_dict(raw: dict) -> EvalRunResult:
    md = raw["metrics"]
    return EvalRunResult(
        metrics=EvalMetrics(
            n_covered=int(md["n_covered"]),
            n_out_of_corpus=int(md["n_out_of_corpus"]),
            hit_rate=float(md["hit_rate"]),
            mrr=float(md["mrr"]),
            mean_covered_score=float(md["mean_covered_score"]),
            mean_out_score=float(md["mean_out_score"]),
            flag_accuracy=float(md["flag_accuracy"]),
        ),
        k=int(raw["k"]),
        embed_space_id=str(raw.get("embed_space_id", "?")),
        embed_scheme=str(raw.get("embed_scheme", "?")),
        n_docs=int(raw.get("n_docs", 0)),
        n_chunks=int(raw.get("n_chunks", 0)),
        timestamp=float(raw["timestamp"]),
    )


def load_eval_data(path: Path | None = None) -> EvalData:
    """Load the golden set + run history.

    A missing file yields the default seed (:func:`seed_golden`) with no runs —
    so a fresh install already has the five out-of-corpus questions to run. A
    corrupt file yields an empty set with a warning (never clobbers, never
    raises), and a malformed golden/run entry is skipped rather than aborting
    the whole load — same tolerance as ``_jsonlog.load_entries``.
    """
    path = path or eval_store_path()
    if not path.exists():
        return EvalData(golden=seed_golden(), runs=())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("[!] Could not read %s (%s) — treating as empty.", path, exc)
        return EvalData(golden=(), runs=())

    golden: list[GoldenQuestion] = []
    for g in raw.get("golden", []):
        try:
            golden.append(_golden_from_dict(g))
        except (KeyError, TypeError, ValueError):
            logger.warning("[!] Skipping malformed golden question: %r", g)
    runs: list[EvalRunResult] = []
    for r in raw.get("runs", []):
        try:
            runs.append(_run_from_dict(r))
        except (KeyError, TypeError, ValueError):
            logger.warning("[!] Skipping malformed eval run: %r", r)
    return EvalData(golden=tuple(golden), runs=tuple(runs))


def save_eval_data(data: EvalData, path: Path | None = None) -> None:
    """Persist the golden set + run history atomically (temp file + replace)."""
    path = path or eval_store_path()
    payload = json.dumps(
        {
            "golden": [_golden_to_dict(g) for g in data.golden],
            "runs": [_run_to_dict(r) for r in data.runs],
        },
        ensure_ascii=False,
        indent=2,
    )
    atomic_write_text(path, payload)


def add_question(
    question: str,
    expected: Sequence[str] = (),
    *,
    path: Path | None = None,
) -> GoldenQuestion:
    """Add one golden question and persist. Covered when ``expected`` is given.

    Expected paths are resolved (``Path.resolve``) so they match the resolved
    ``ChunkMeta.source_path`` the indexer stores — the same resolution
    ``_index_one`` and the CLI's ``_resolve_doc_path`` apply, or matching would
    silently diverge on Windows.
    """
    data = load_eval_data(path)
    resolved = tuple(str(Path(e).resolve()) for e in expected)
    gq = GoldenQuestion(question=question.strip(), expected=resolved)
    save_eval_data(EvalData(golden=(*data.golden, gq), runs=data.runs), path)
    return gq


def record_run(result: EvalRunResult, *, path: Path | None = None) -> None:
    """Append a run to the history, capped at the last ``_MAX_RUNS``."""
    data = load_eval_data(path)
    runs = (*data.runs, result)[-_MAX_RUNS:]
    save_eval_data(EvalData(golden=data.golden, runs=runs), path)


def latest_and_previous(
    data: EvalData,
) -> tuple[EvalRunResult | None, EvalRunResult | None]:
    """Return ``(latest_run, previous_comparable_run)``.

    The previous run is the most recent one *before* the latest that shares its
    ``embed_space_id`` — runs from a different embedding space are not
    comparable (a reindex under a new model/scheme moves every cosine). When the
    latest run has a prior of a different space only, the second element is
    ``None`` and callers can tell "incomparable" from "first run ever" by
    ``len(data.runs) > 1``.
    """
    if not data.runs:
        return None, None
    latest = data.runs[-1]
    previous = next(
        (
            r
            for r in reversed(data.runs[:-1])
            if r.embed_space_id == latest.embed_space_id
        ),
        None,
    )
    return latest, previous
