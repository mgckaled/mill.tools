"""Unit tests for execute_recipe — chaining, cancel, stop_on_error, event order.

The real adapters are replaced via ``mocker.patch.dict(STEP_REGISTRY, ...)`` with
fakes that return ``[tmp_path/"x"]``, so no ffmpeg/Whisper/network is touched.
"""

import pytest


def _spec(adapter, accepts, produces, label="X"):
    from src.core.recipes.types import StepSpec

    return StepSpec(adapter, frozenset(accepts), produces, label)


def _recipe(*ops):
    from src.core.recipes.types import Recipe, RecipeStep

    return Recipe(name="r", steps=[RecipeStep(o) for o in ops])


@pytest.mark.unit
def test_chaining_feeds_output_into_next_step(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    seen = []

    def a1(inputs, params, ctx):
        seen.append(("s1", list(inputs)))
        return [tmp_path / "out1"]

    def a2(inputs, params, ctx):
        seen.append(("s2", list(inputs)))
        return [tmp_path / "out2"]

    mocker.patch.dict(
        STEP_REGISTRY,
        {
            "t.s1": _spec(a1, {"url"}, "audio"),
            "t.s2": _spec(a2, {"audio"}, "text"),
        },
    )

    events = []
    out = runner.execute_recipe(
        _recipe("t.s1", "t.s2"),
        ["http://x"],
        initial_kind="url",
        emit=lambda t, p: events.append((t, p)),
        cancel_is_set=lambda: False,
    )

    assert seen[0] == ("s1", ["http://x"])
    assert seen[1] == ("s2", [tmp_path / "out1"])
    assert out == [tmp_path / "out2"]


@pytest.mark.unit
def test_event_order(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    mocker.patch.dict(
        STEP_REGISTRY,
        {
            "t.s1": _spec(lambda i, p, c: [tmp_path / "a"], {"url"}, "audio"),
            "t.s2": _spec(lambda i, p, c: [tmp_path / "b"], {"audio"}, "text"),
        },
    )

    events = []
    runner.execute_recipe(
        _recipe("t.s1", "t.s2"),
        ["http://x"],
        initial_kind="url",
        emit=lambda t, p: events.append(t),
        cancel_is_set=lambda: False,
    )

    assert events == [
        "recipe_start",
        "progress_start",
        "step_start",
        "step_done",
        "step_start",
        "step_done",
        "task_done",
    ]


@pytest.mark.unit
def test_cancel_between_steps_aborts(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    ran = []
    mocker.patch.dict(
        STEP_REGISTRY,
        {
            "t.s1": _spec(
                lambda i, p, c: ran.append("s1") or [tmp_path / "a"], {"url"}, "audio"
            ),
            "t.s2": _spec(
                lambda i, p, c: ran.append("s2") or [tmp_path / "b"], {"audio"}, "text"
            ),
        },
    )

    state = {"n": 0}

    def cancel():
        state["n"] += 1
        return state["n"] >= 2  # False before s1, True before s2

    events = []
    out = runner.execute_recipe(
        _recipe("t.s1", "t.s2"),
        ["http://x"],
        initial_kind="url",
        emit=lambda t, p: events.append((t, p)),
        cancel_is_set=cancel,
    )

    assert out == []
    assert ran == ["s1"]  # s2 never ran
    err = [p for t, p in events if t == "task_error"]
    assert err and "Cancelado" in err[0]["message"]


@pytest.mark.unit
def test_stop_on_error_aborts_remaining_steps(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    ran = []

    def boom(inputs, params, ctx):
        raise RuntimeError("kaboom")

    mocker.patch.dict(
        STEP_REGISTRY,
        {
            "t.s1": _spec(
                lambda i, p, c: ran.append("s1") or [tmp_path / "a"], {"url"}, "audio"
            ),
            "t.s2": _spec(boom, {"audio"}, "text", label="Falhar"),
            "t.s3": _spec(
                lambda i, p, c: ran.append("s3") or [tmp_path / "c"], {"text"}, "text"
            ),
        },
    )

    events = []
    out = runner.execute_recipe(
        _recipe("t.s1", "t.s2", "t.s3"),
        ["http://x"],
        initial_kind="url",
        emit=lambda t, p: events.append((t, p)),
        cancel_is_set=lambda: False,
    )

    assert out == []
    assert ran == ["s1"]  # s3 never ran
    types = [t for t, _ in events]
    assert "step_error" in types
    err = [p for t, p in events if t == "task_error"][0]
    assert "Falhar" in err["message"]
    assert "kaboom" in err["message"]


@pytest.mark.unit
def test_invalid_recipe_emits_task_error_without_running(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    ran = []
    mocker.patch.dict(
        STEP_REGISTRY,
        {
            "t.s1": _spec(
                lambda i, p, c: ran.append("s1") or [tmp_path / "a"], {"audio"}, "text"
            )
        },
    )

    events = []
    # initial_kind 'url' but the only step accepts 'audio' → invalid.
    out = runner.execute_recipe(
        _recipe("t.s1"),
        ["http://x"],
        initial_kind="url",
        emit=lambda t, p: events.append((t, p)),
        cancel_is_set=lambda: False,
    )

    assert out == []
    assert ran == []
    msgs = [p["message"] for t, p in events if t == "task_error"]
    assert msgs and "Receita inválida" in msgs[0]


@pytest.mark.unit
def test_emit_terminal_false_suppresses_lifecycle_events(mocker, tmp_path):
    """In a batch entry (emit_terminal=False) no progress_start/task_done fire."""
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    mocker.patch.dict(
        STEP_REGISTRY,
        {"t.s1": _spec(lambda i, p, c: [tmp_path / "a"], {"url"}, "audio")},
    )

    events = []
    out = runner.execute_recipe(
        _recipe("t.s1"),
        ["http://x"],
        initial_kind="url",
        emit=lambda t, p: events.append(t),
        cancel_is_set=lambda: False,
        emit_terminal=False,
    )

    assert out == [tmp_path / "a"]
    types = set(events)
    assert "progress_start" not in types
    assert "task_done" not in types
    assert "step_start" in types  # step events still flow


@pytest.mark.unit
def test_emit_terminal_false_logs_failure_instead_of_task_error(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    # Invalid: initial_kind 'url' but the only step accepts 'audio'.
    mocker.patch.dict(
        STEP_REGISTRY,
        {"t.s1": _spec(lambda i, p, c: [tmp_path / "a"], {"audio"}, "text")},
    )

    events = []
    out = runner.execute_recipe(
        _recipe("t.s1"),
        ["http://x"],
        initial_kind="url",
        emit=lambda t, p: events.append((t, p)),
        cancel_is_set=lambda: False,
        emit_terminal=False,
    )

    assert out == []
    types = [t for t, _ in events]
    assert "task_error" not in types
    assert any(t == "log" and "inválida" in p.get("message", "") for t, p in events)


@pytest.mark.unit
def test_execute_recipe_batch_runs_each_entry_and_aggregates(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    seen = []
    mocker.patch.dict(
        STEP_REGISTRY,
        {
            "t.s1": _spec(
                lambda i, p, c: seen.append(i[0]) or [tmp_path / i[0]],
                {"audio"},
                "text",
            )
        },
    )

    events = []
    out = runner.execute_recipe_batch(
        _recipe("t.s1"),
        [(["a"], "audio", "a"), (["b"], "audio", "b")],
        emit=lambda t, p: events.append((t, p)),
        cancel_is_set=lambda: False,
    )

    assert seen == ["a", "b"]
    assert out == [tmp_path / "a", tmp_path / "b"]
    types = [t for t, _ in events]
    assert types[0] == "progress_start"
    assert types.count("queue_progress") == 2
    assert types[-1] == "task_done"
    done = [p for t, p in events if t == "task_done"][0]
    assert done["failed_count"] == 0


@pytest.mark.unit
def test_execute_recipe_batch_counts_failures_without_aborting(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    def _maybe_fail(inputs, params, ctx):
        if inputs[0] == "bad":
            raise RuntimeError("boom")
        return [tmp_path / inputs[0]]

    mocker.patch.dict(STEP_REGISTRY, {"t.s1": _spec(_maybe_fail, {"audio"}, "text")})

    events = []
    out = runner.execute_recipe_batch(
        _recipe("t.s1"),
        [(["bad"], "audio", "bad"), (["ok"], "audio", "ok")],
        emit=lambda t, p: events.append((t, p)),
        cancel_is_set=lambda: False,
    )

    assert out == [tmp_path / "ok"]  # the good entry still ran
    done = [p for t, p in events if t == "task_done"][0]
    assert done["failed_count"] == 1


@pytest.mark.unit
def test_execute_recipe_batch_cancel_between_entries(mocker, tmp_path):
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    mocker.patch.dict(
        STEP_REGISTRY,
        {"t.s1": _spec(lambda i, p, c: [tmp_path / "a"], {"audio"}, "text")},
    )
    state = {"n": 0}

    def cancel():
        state["n"] += 1
        return state["n"] >= 2

    events = []
    runner.execute_recipe_batch(
        _recipe("t.s1"),
        [(["a"], "audio", "a"), (["b"], "audio", "b")],
        emit=lambda t, p: events.append((t, p)),
        cancel_is_set=cancel,
    )

    assert any(t == "task_error" and "Cancelado" in p["message"] for t, p in events)


@pytest.mark.unit
def test_multi_input_step_reads_history_from_context(mocker, tmp_path):
    """A later step can reach an earlier step's outputs via ctx.outputs_by_op."""
    from src.core.recipes import runner
    from src.core.recipes.registry import STEP_REGISTRY

    captured = {}

    def producer(inputs, params, ctx):
        return [tmp_path / "txt.txt", tmp_path / "subs.srt"]

    def consumer(inputs, params, ctx):
        captured["initial"] = list(ctx.initial_inputs)
        captured["history"] = ctx.outputs_by_op.get("t.producer")
        return [tmp_path / "final.mp4"]

    mocker.patch.dict(
        STEP_REGISTRY,
        {
            "t.producer": _spec(producer, {"video"}, "text"),
            "t.consumer": _spec(consumer, {"text"}, "video"),
        },
    )

    runner.execute_recipe(
        _recipe("t.producer", "t.consumer"),
        [tmp_path / "movie.mp4"],
        initial_kind="video",
        emit=lambda t, p: None,
        cancel_is_set=lambda: False,
    )

    assert captured["initial"] == [tmp_path / "movie.mp4"]
    assert captured["history"] == [tmp_path / "txt.txt", tmp_path / "subs.srt"]
