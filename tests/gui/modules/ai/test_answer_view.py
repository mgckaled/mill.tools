"""Unit tests for src/gui/modules/ai/answer_view.py — conversation history
window (Fase 2, PLANO_CONVERSA_MULTITURNO.md) and the "buscou por" legend.

Flet is not testable headless, so this builds the view with a MagicMock page
and drives it through its exposed handles (``ask``/``handle_answer_done``/
``clear_btn``) instead of a live UI. ``start_ai_answer`` is mocked at its
import site in ``answer_view`` — the worker's own history handling is covered
in ``test_worker.py``.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import flet as ft
import pytest


@pytest.fixture(autouse=True)
def isolate_settings(tmp_path, monkeypatch):
    import src.gui.settings as settings_mod

    cfg_dir = tmp_path / ".mill-tools"
    monkeypatch.setattr(settings_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_dir / "config.json")


def _build_view(*, query="pergunta"):
    from src.gui.modules.ai.answer_view import build_answer_view

    page = MagicMock()
    query_box = [query]
    return build_answer_view(
        page,
        MagicMock(),
        threading.Event(),
        [False],
        embed_model="nomic-embed-custom",
        get_query=lambda: query_box[0],
        get_scope=lambda: None,
        get_model=lambda: "gemma3-4b-custom",
        get_k=lambda: 6,
        on_begin=lambda: None,
        on_empty_query=lambda: None,
        toast=lambda _msg: None,
    ), query_box


def _done_payload(query: str, text: str = "resposta", sources=None, **extra) -> dict:
    return {
        "query": query,
        "search_query": extra.pop("search_query", query),
        "text": text,
        "sources": sources or [],
        "model_name": "gemma3-4b-custom",
        "elapsed": 1.0,
        "low_confidence": False,
        **extra,
    }


@pytest.mark.unit
def test_first_ask_sends_empty_history(mocker):
    start_mock = mocker.patch("src.gui.modules.ai.answer_view.start_ai_answer")
    view, _q = _build_view()

    view.ask()

    assert start_mock.call_args.kwargs["history"] == []


@pytest.mark.unit
def test_ask_carries_original_query_not_condensed_rewrite(mocker):
    start_mock = mocker.patch("src.gui.modules.ai.answer_view.start_ai_answer")
    view, q = _build_view()

    view.handle_answer_done(
        _done_payload(
            "e sobre isso?",
            "resposta 1",
            ["doc.txt"],
            search_query="pergunta reescrita standalone",
        )
    )
    q[0] = "e o resto?"
    view.ask()

    history = start_mock.call_args.kwargs["history"]
    assert history == [("e sobre isso?", "resposta 1", ["doc.txt"])]


@pytest.mark.unit
def test_history_window_trims_to_last_two_turns(mocker):
    start_mock = mocker.patch("src.gui.modules.ai.answer_view.start_ai_answer")
    view, q = _build_view()

    view.handle_answer_done(_done_payload("q1", "a1"))
    view.handle_answer_done(_done_payload("q2", "a2"))
    view.handle_answer_done(_done_payload("q3", "a3"))
    q[0] = "q4"
    view.ask()

    history = start_mock.call_args.kwargs["history"]
    assert [h[0] for h in history] == ["q2", "q3"]


@pytest.mark.unit
def test_clear_conversation_resets_history(mocker):
    start_mock = mocker.patch("src.gui.modules.ai.answer_view.start_ai_answer")
    view, q = _build_view()

    view.handle_answer_done(_done_payload("q1", "a1"))
    view.clear_btn.on_click(None)
    q[0] = "q2"
    view.ask()

    assert start_mock.call_args.kwargs["history"] == []


@pytest.mark.unit
def test_turn_card_shows_search_query_legend_only_when_rewritten():
    view, _q = _build_view()
    view.handle_answer_done(
        _done_payload(
            "e sobre isso?", "resposta", search_query="pergunta reescrita standalone"
        )
    )
    view.handle_answer_done(_done_payload("pergunta autossuficiente", "resposta 2"))

    rewritten_turn, plain_turn = view.session_area.controls[0].controls
    rewritten_texts = _flatten_text(rewritten_turn)
    plain_texts = _flatten_text(plain_turn)

    assert any("pergunta reescrita standalone" in t for t in rewritten_texts)
    assert not any("buscou por" in t for t in plain_texts)


def _flatten_text(control) -> list[str]:
    """Collect every ``.value`` string found in a control tree (best-effort)."""
    out: list[str] = []
    value = getattr(control, "value", None)
    if isinstance(value, str):
        out.append(value)
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                out.extend(_flatten_text(c))
        elif child is not None and not isinstance(child, (str, bytes)):
            out.extend(_flatten_text(child))
    return out


# ── 👍/👎 feedback (PLANO_RAG_EVAL, Fase 5) ──────────────────────────────────


def _icon_buttons(control) -> list:
    """Collect every ft.IconButton in a control tree."""
    out: list = []
    if isinstance(control, ft.IconButton):
        out.append(control)
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                out.extend(_icon_buttons(c))
        elif child is not None and not isinstance(child, (str, bytes)):
            out.extend(_icon_buttons(child))
    return out


def _thumbs(turn):
    """Return (up_btn, down_btn) for a turn card."""
    btns = [
        b
        for b in _icon_buttons(turn)
        if b.icon in (ft.Icons.THUMB_UP_OUTLINED, ft.Icons.THUMB_DOWN_OUTLINED)
    ]
    up = next(b for b in btns if b.icon == ft.Icons.THUMB_UP_OUTLINED)
    down = next(b for b in btns if b.icon == ft.Icons.THUMB_DOWN_OUTLINED)
    return up, down


@pytest.mark.unit
def test_feedback_thumbs_up_logs_and_disables(mocker):
    log_fb = mocker.patch("src.gui.modules.ai.answer_view.log_feedback")
    log_act = mocker.patch("src.core.observatory.activity.log_activity")
    view, _q = _build_view()

    view.handle_answer_done(
        _done_payload(
            "o que diz a aula?",
            "resposta",
            ["C:/out/aula.txt"],
            best_score=0.83,
            embed_space_id="nomic-embed-custom:768:scheme-x",
        )
    )
    turn = view.session_area.controls[0].controls[0]
    up, down = _thumbs(turn)
    up.on_click(None)

    log_fb.assert_called_once()
    kwargs = log_fb.call_args.kwargs
    assert kwargs["verdict"] == "up"
    assert kwargs["query"] == "o que diz a aula?"
    assert kwargs["sources"] == ["C:/out/aula.txt"]
    assert kwargs["pool_max_score"] == 0.83
    assert kwargs["embed_space_id"] == "nomic-embed-custom:768:scheme-x"
    assert kwargs["model"] == "gemma3-4b-custom"
    # a signal, not a review — both thumbs disable after one tap
    assert up.disabled is True
    assert down.disabled is True
    log_act.assert_called_once()
    assert log_act.call_args.args[1] == "rag_feedback"


@pytest.mark.unit
def test_feedback_thumbs_down_records_down_verdict(mocker):
    log_fb = mocker.patch("src.gui.modules.ai.answer_view.log_feedback")
    mocker.patch("src.core.observatory.activity.log_activity")
    view, _q = _build_view()

    view.handle_answer_done(_done_payload("pergunta", "resposta", ["a.txt"]))
    turn = view.session_area.controls[0].controls[0]
    _up, down = _thumbs(turn)
    down.on_click(None)

    assert log_fb.call_args.kwargs["verdict"] == "down"


@pytest.mark.unit
def test_feedback_uses_search_query_when_condensed(mocker):
    log_fb = mocker.patch("src.gui.modules.ai.answer_view.log_feedback")
    mocker.patch("src.core.observatory.activity.log_activity")
    view, _q = _build_view()

    view.handle_answer_done(
        _done_payload(
            "e sobre isso?",
            "resposta",
            ["a.txt"],
            search_query="pergunta reescrita standalone",
        )
    )
    turn = view.session_area.controls[0].controls[0]
    up, _down = _thumbs(turn)
    up.on_click(None)

    kwargs = log_fb.call_args.kwargs
    assert kwargs["query"] == "e sobre isso?"
    assert kwargs["search_query"] == "pergunta reescrita standalone"


@pytest.mark.unit
def test_feedback_failure_is_swallowed(mocker):
    """A feedback write failure must never break the conversation."""
    mocker.patch(
        "src.gui.modules.ai.answer_view.log_feedback",
        side_effect=OSError("disk full"),
    )
    mocker.patch("src.core.observatory.activity.log_activity")
    view, _q = _build_view()

    view.handle_answer_done(_done_payload("pergunta", "resposta", ["a.txt"]))
    turn = view.session_area.controls[0].controls[0]
    up, down = _thumbs(turn)
    up.on_click(None)  # must not raise

    assert up.disabled is True and down.disabled is True
