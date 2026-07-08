"""Unit tests for src/analysis/types.py."""

import dataclasses

import pytest

pytestmark = pytest.mark.unit


def test_field_defaults():
    from src.analysis.types import Field

    f = Field(key="summary", title="Resumo", kind="paragraph", rule="3-5 frases")
    assert f.always is False
    assert f.empty_text == ""


def test_field_is_frozen():
    from src.analysis.types import Field

    f = Field(key="k", title="T", kind="list", rule="r")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.key = "other"  # type: ignore[misc]


def test_profile_defaults_and_frozen():
    from src.analysis.types import AnalysisProfile, Field

    p = AnalysisProfile(
        id="x",
        label="X",
        icon="ARTICLE_OUTLINED",
        persona="Você é um analista.",
        source_hint="transcrição",
        fields=(Field(key="summary", title="Resumo", kind="paragraph", rule="r"),),
    )
    assert p.temperature == 0.4
    assert p.disclaimer == ""
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.id = "y"  # type: ignore[misc]


def test_all_kinds_contains_the_four_render_kinds():
    from src.analysis.types import (
        ALL_KINDS,
        KIND_KEYVALUE,
        KIND_LIST,
        KIND_PARAGRAPH,
        KIND_QUOTES,
    )

    assert ALL_KINDS == {KIND_PARAGRAPH, KIND_LIST, KIND_QUOTES, KIND_KEYVALUE}


def test_group_meta_holds_ordered_ids():
    from src.analysis.types import GroupMeta

    g = GroupMeta(label="Rápido", icon="LIGHTBULB_OUTLINE", profile_ids=("notes",))
    assert g.profile_ids == ("notes",)


# --- Fase 2 do PLANO_CORRECOES_SRC_ANALYSIS: integridade do catálogo -------


def test_field_rejects_unknown_kind():
    from src.analysis.types import Field

    with pytest.raises(ValueError, match="unknown kind"):
        Field(key="k", title="T", kind="pargraph", rule="r")


def test_field_requires_empty_text_when_always():
    from src.analysis.types import Field

    with pytest.raises(ValueError, match="empty_text"):
        Field(key="k", title="T", kind="list", rule="r", always=True)


def test_field_always_with_empty_text_is_valid():
    from src.analysis.types import Field

    f = Field(key="k", title="T", kind="list", rule="r", always=True, empty_text="N/A")
    assert f.empty_text == "N/A"


def test_profile_rejects_duplicate_field_keys():
    from src.analysis.types import AnalysisProfile, Field

    with pytest.raises(ValueError, match="duplicate field keys"):
        AnalysisProfile(
            id="x",
            label="X",
            icon="ARTICLE_OUTLINED",
            persona="Você é um analista.",
            source_hint="transcrição",
            fields=(
                Field(key="summary", title="Resumo", kind="paragraph", rule="r"),
                Field(key="summary", title="Resumo 2", kind="paragraph", rule="r"),
            ),
        )


def test_profile_rejects_empty_field_key():
    from src.analysis.types import AnalysisProfile, Field

    with pytest.raises(ValueError, match="empty key"):
        AnalysisProfile(
            id="x",
            label="X",
            icon="ARTICLE_OUTLINED",
            persona="Você é um analista.",
            source_hint="transcrição",
            fields=(Field(key="", title="Resumo", kind="paragraph", rule="r"),),
        )
