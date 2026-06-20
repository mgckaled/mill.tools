"""Unit tests for the Tier 1 profile catalog (src/analysis/profiles)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_EXPECTED_PROFILES = {
    "default",
    "lecture",
    "interview",
    "tutorial",
    "scientific",
    "administrative",
    "literary",
    "review",
    "storytelling",
    "notes",
}

_DEFAULT_FIELDS = [
    ("summary", "Resumo"),
    ("key_points", "Pontos-chave"),
    ("action_items", "Ações sugeridas"),
    ("key_concepts", "Conceitos-chave"),
    ("tools_mentioned", "Ferramentas mencionadas"),
    ("metrics", "Métricas e números"),
    ("quotes", "Citações notáveis"),
    ("assumptions", "Premissas implícitas"),
    ("vocabulary", "Vocabulário do nicho"),
    ("sentiment_arc", "Arco de sentimento"),
]


def test_catalog_has_expected_profiles():
    from src.analysis import PROFILES

    assert set(PROFILES.keys()) == _EXPECTED_PROFILES


def test_profile_ids_match_dict_keys():
    from src.analysis import PROFILES

    for key, profile in PROFILES.items():
        assert profile.id == key


def test_every_profile_has_valid_fields():
    from src.analysis import ALL_KINDS, PROFILES

    for profile in PROFILES.values():
        assert profile.fields, f"{profile.id} has no fields"
        keys = [f.key for f in profile.fields]
        assert len(keys) == len(set(keys)), f"{profile.id} has duplicate keys"
        for f in profile.fields:
            assert f.kind in ALL_KINDS
            assert f.title
            assert f.rule


def test_default_profile_reproduces_legacy_schema():
    from src.analysis import get_profile

    fields = [(f.key, f.title) for f in get_profile("default").fields]
    assert fields == _DEFAULT_FIELDS


def test_default_required_fields_are_always_rendered():
    from src.analysis import get_profile

    by_key = {f.key: f for f in get_profile("default").fields}
    assert by_key["summary"].always and by_key["summary"].empty_text == "N/A"
    assert by_key["key_points"].always
    assert by_key["action_items"].always
    assert by_key["action_items"].empty_text == "Nenhuma ação identificada."


def test_groups_reference_existing_ids_and_cover_all_profiles():
    from src.analysis import GROUPS, PROFILES

    grouped = [pid for g in GROUPS for pid in g.profile_ids]
    assert set(grouped) == set(PROFILES.keys())
    assert len(grouped) == len(set(grouped)), "a profile is listed in two groups"


def test_get_profile_unknown_falls_back_to_default():
    from src.analysis import get_profile

    assert get_profile("does-not-exist").id == "default"


def test_list_profiles_returns_all_ids_in_registry_order():
    from src.analysis import PROFILES, list_profiles

    assert list_profiles() == list(PROFILES.keys())
    assert list_profiles()[0] == "default"


def test_literary_profile_shape_and_group():
    from src.analysis import GROUPS, get_profile

    prof = get_profile("literary")
    assert prof.label == "Literatura"
    assert prof.temperature == 0.55
    by_key = {f.key: f for f in prof.fields}
    # synopsis is always rendered; notable passages use blockquotes
    assert by_key["summary"].always
    assert by_key["notable_passages"].kind == "quotes"
    # literary lives in the creative group
    creative = next(g for g in GROUPS if g.label == "Criativo")
    assert "literary" in creative.profile_ids
    # creative profiles carry no "ignore CTAs" rule
    assert "IGNORE CTAs" not in " ".join(f.rule for f in prof.fields)


def test_creative_group_holds_literary_review_storytelling():
    from src.analysis import GROUPS, get_profile

    creative = next(g for g in GROUPS if g.label == "Criativo")
    assert creative.profile_ids == ("literary", "review", "storytelling")
    # review: verdict always rendered; storytelling: logline always rendered
    assert {f.key: f for f in get_profile("review").fields}["verdict"].always
    assert {f.key: f for f in get_profile("storytelling").fields}["logline"].always
    # both are interpretive, no "ignore CTAs" rule
    for pid in ("review", "storytelling"):
        assert "IGNORE CTAs" not in " ".join(f.rule for f in get_profile(pid).fields)


def test_ignore_cta_rule_only_in_media_profiles():
    from src.analysis import get_profile

    media_text = " ".join(f.rule for f in get_profile("default").fields)
    doc_text = " ".join(f.rule for f in get_profile("scientific").fields)
    assert "IGNORE CTAs" in media_text
    assert "IGNORE CTAs" not in doc_text


def test_every_profile_prompt_builds_and_report_renders():
    from src.analysis import (
        PROFILES,
        build_analysis_prompt,
        build_merge_prompt,
        format_report,
    )

    for profile in PROFILES.values():
        # Prompts must format without KeyError despite the JSON braces.
        build_analysis_prompt(profile).format_messages(text="x")
        build_merge_prompt(profile).format_messages(analyses="[]")
        # Report renders for an all-empty analysis (always fields still appear).
        out = format_report(profile, {}, Path("t.txt"))
        assert out.startswith("# ")
