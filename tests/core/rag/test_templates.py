"""Unit tests for src/core/rag/templates.py — defaults, persistence, lookup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_prompts(tmp_path, monkeypatch):
    """Redirect prompts_file() to a tmp path for every test."""
    import src.core.rag.templates as mod

    pf = tmp_path / ".mill-tools" / "prompts.json"
    monkeypatch.setattr(mod, "prompts_file", lambda: pf)
    return pf


@pytest.mark.unit
def test_default_templates_include_prompts_and_structured():
    from src.core.rag.templates import (
        CATEGORY_PROMPT,
        CATEGORY_TEMPLATE,
        default_templates,
    )

    defaults = default_templates()
    cats = {t.category for t in defaults}
    assert CATEGORY_PROMPT in cats and CATEGORY_TEMPLATE in cats
    ids = {t.id for t in defaults}
    assert {"summarize", "meeting_minutes", "email", "exec_summary"} <= ids


@pytest.mark.unit
def test_load_templates_without_user_file_returns_defaults():
    from src.core.rag.templates import default_templates, load_templates

    assert [t.id for t in load_templates()] == [t.id for t in default_templates()]


@pytest.mark.unit
def test_save_and_load_user_template(isolate_prompts):
    from src.core.rag.templates import (
        CATEGORY_PROMPT,
        PromptTemplate,
        load_templates,
        save_user_template,
    )

    save_user_template(
        PromptTemplate(
            "my_q", "Minha pergunta", "Faça X com o conteúdo.", CATEGORY_PROMPT
        )
    )

    loaded = load_templates()
    assert any(t.id == "my_q" and t.label == "Minha pergunta" for t in loaded)
    # Defaults are not written to the file — only the user entry.
    raw = json.loads(Path(isolate_prompts).read_text(encoding="utf-8"))
    assert [e["id"] for e in raw] == ["my_q"]


@pytest.mark.unit
def test_save_user_template_replaces_same_id(isolate_prompts):
    from src.core.rag.templates import (
        CATEGORY_PROMPT,
        PromptTemplate,
        save_user_template,
    )

    save_user_template(PromptTemplate("dup", "v1", "primeira", CATEGORY_PROMPT))
    save_user_template(PromptTemplate("dup", "v2", "segunda", CATEGORY_PROMPT))

    raw = json.loads(Path(isolate_prompts).read_text(encoding="utf-8"))
    assert len(raw) == 1
    assert raw[0]["label"] == "v2"


@pytest.mark.unit
def test_user_template_cannot_shadow_a_default(isolate_prompts):
    from src.core.rag.templates import (
        CATEGORY_PROMPT,
        PromptTemplate,
        get_template,
        save_user_template,
    )

    save_user_template(
        PromptTemplate("summarize", "Hijack", "instrução maliciosa", CATEGORY_PROMPT)
    )
    # The built-in "summarize" still wins.
    assert get_template("summarize").label == "Resumir"


@pytest.mark.unit
def test_load_templates_skips_malformed_entries(isolate_prompts):
    from src.core.rag.templates import load_templates

    Path(isolate_prompts).parent.mkdir(parents=True, exist_ok=True)
    Path(isolate_prompts).write_text(
        json.dumps([{"id": "broken"}, {"bogus": True}]), encoding="utf-8"
    )
    # Malformed entries are dropped; defaults still load.
    ids = {t.id for t in load_templates()}
    assert "summarize" in ids
    assert "broken" not in ids


@pytest.mark.unit
def test_load_templates_tolerates_corrupt_json(isolate_prompts):
    from src.core.rag.templates import default_templates, load_templates

    Path(isolate_prompts).parent.mkdir(parents=True, exist_ok=True)
    Path(isolate_prompts).write_text("{not valid json", encoding="utf-8")
    assert len(load_templates()) == len(default_templates())


@pytest.mark.unit
def test_load_templates_tolerates_non_list_json(isolate_prompts):
    from src.core.rag.templates import default_templates, load_templates

    Path(isolate_prompts).parent.mkdir(parents=True, exist_ok=True)
    # Valid JSON, but an object instead of the expected array.
    Path(isolate_prompts).write_text(json.dumps({"id": "x"}), encoding="utf-8")
    assert len(load_templates()) == len(default_templates())


@pytest.mark.unit
def test_get_template_unknown_returns_none():
    from src.core.rag.templates import get_template

    assert get_template("does-not-exist") is None
