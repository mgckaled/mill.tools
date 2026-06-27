"""Unit tests for src/core/recipes/history.py — run log round-trip + aggregate."""

from __future__ import annotations

import pytest

from src.core.recipes.history import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    RunRecord,
    RunTracker,
    aggregate,
    aggregate_result,
    append_run,
    load_runs,
)


@pytest.fixture
def runs_path(tmp_path):
    return tmp_path / ".mill-tools" / "recipe_runs.json"


def _record(name="R", *, status=STATUS_OK, duration=10.0, failed_op=None, batch=None):
    return RunRecord(
        recipe_name=name,
        started_at=1000.0,
        finished_at=1000.0 + duration,
        duration=duration,
        status=status,
        n_steps=3,
        failed_op=failed_op,
        batch_size=batch,
    )


# ---------------------------------------------------------------------------
# append_run / load_runs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_missing_returns_empty(runs_path):
    assert load_runs(runs_path) == []


@pytest.mark.unit
def test_append_and_load_round_trip(runs_path):
    append_run(_record("A", duration=5.0), path=runs_path)
    append_run(
        _record("B", status=STATUS_ERROR, failed_op="audio.download"), path=runs_path
    )

    runs = load_runs(runs_path)
    assert [r.recipe_name for r in runs] == ["A", "B"]
    assert runs[0].duration == 5.0
    assert runs[1].status == STATUS_ERROR
    assert runs[1].failed_op == "audio.download"


@pytest.mark.unit
def test_append_caps_at_max(runs_path, monkeypatch):
    monkeypatch.setattr("src.core.recipes.history._MAX_RUNS", 3)
    for i in range(5):
        append_run(_record(f"R{i}"), path=runs_path)

    runs = load_runs(runs_path)
    assert len(runs) == 3
    assert [r.recipe_name for r in runs] == ["R2", "R3", "R4"]  # oldest fell off


@pytest.mark.unit
def test_load_invalid_json_returns_empty(runs_path):
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    runs_path.write_text("{not json", encoding="utf-8")
    assert load_runs(runs_path) == []


@pytest.mark.unit
def test_load_skips_malformed_entries(runs_path):
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    runs_path.write_text(
        '[{"recipe_name":"ok","started_at":1,"finished_at":2,"duration":1,'
        '"status":"ok","n_steps":1},{"recipe_name":"bad"}]',
        encoding="utf-8",
    )
    runs = load_runs(runs_path)
    assert len(runs) == 1
    assert runs[0].recipe_name == "ok"


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# RunTracker
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_tracker_records_ok_with_duration():
    clock = iter([100.0, 130.0])
    tracker = RunTracker("R", 2, now=lambda: next(clock))
    record = tracker.record(STATUS_OK)

    assert record.status == STATUS_OK
    assert record.started_at == 100.0
    assert record.finished_at == 130.0
    assert record.duration == 30.0
    assert record.n_steps == 2
    assert record.failed_op is None
    assert record.batch_size is None


@pytest.mark.unit
def test_run_tracker_captures_failed_op_for_error():
    tracker = RunTracker("R", 1)
    tracker.observe("step_start", {"op": "audio.download"})
    tracker.observe("step_error", {"op": "audio.normalize", "message": "x"})
    record = tracker.record(STATUS_ERROR)

    assert record.status == STATUS_ERROR
    assert record.failed_op == "audio.normalize"


@pytest.mark.unit
def test_run_tracker_drops_failed_op_when_not_error():
    tracker = RunTracker("R", 1)
    tracker.observe("step_error", {"op": "audio.normalize"})
    # A later success means failed_op is irrelevant — only kept for error status.
    assert tracker.record(STATUS_OK).failed_op is None


@pytest.mark.unit
def test_run_tracker_batch_size():
    tracker = RunTracker("R", 3, batch_size=5)
    assert tracker.record(STATUS_CANCELLED).batch_size == 5


@pytest.mark.unit
def test_aggregate_empty():
    assert aggregate([]) == ()


@pytest.mark.unit
def test_aggregate_success_rate_and_avg_and_top_fail():
    runs = [
        _record("Clean", duration=10.0),
        _record("Clean", duration=20.0),
        _record(
            "Clean", status=STATUS_ERROR, duration=30.0, failed_op="audio.normalize"
        ),
        _record("Other", status=STATUS_CANCELLED, duration=5.0),
    ]
    aggs = aggregate(runs)
    # busiest recipe first
    assert [a.recipe_name for a in aggs] == ["Clean", "Other"]

    clean = aggs[0]
    assert clean.n_runs == 3
    assert clean.n_ok == 2
    assert clean.success_rate == pytest.approx(2 / 3)
    assert clean.avg_duration == pytest.approx(20.0)
    assert clean.most_failing_op == "audio.normalize"

    other = aggs[1]
    assert other.success_rate == 0.0
    assert other.most_failing_op is None  # cancelled, not an error with a failed_op


@pytest.mark.unit
def test_aggregate_result_shape():
    runs = [_record("R", duration=10.0), _record("R", status=STATUS_ERROR)]
    result = aggregate_result(aggregate(runs))
    assert result.columns == ["receita", "execuções", "sucesso_%", "duração_média_s"]
    assert result.rows[0][0] == "R"
    assert result.rows[0][1] == 2  # n_runs
    assert result.rows[0][2] == 50.0  # success %
    assert result.elapsed == 0.0
