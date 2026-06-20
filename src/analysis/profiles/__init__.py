"""
profiles: Tier 1 catalog of analysis profiles + grouped metadata for the GUI.

Adding a profile is a single entry: define it in one of the group modules,
include it in that module's ``PROFILES`` tuple, and reference its id in ``GROUPS``.
"""

from __future__ import annotations

from src.analysis.profiles import creative, documents, media, quick
from src.analysis.types import AnalysisProfile, GroupMeta

# Ordered registry id -> profile (insertion order defines the default cycling).
PROFILES: dict[str, AnalysisProfile] = {
    p.id: p
    for p in (
        *media.PROFILES,
        *documents.PROFILES,
        *creative.PROFILES,
        *quick.PROFILES,
    )
}

# Grouped metadata for the grouped GUI selector (label/icon per section).
GROUPS: tuple[GroupMeta, ...] = (
    GroupMeta(
        label="Conteúdo / Mídia",
        icon="MOVIE_OUTLINED",
        profile_ids=("default", "lecture", "interview", "tutorial"),
    ),
    GroupMeta(
        label="Acadêmico / Documento",
        icon="DESCRIPTION_OUTLINED",
        profile_ids=("scientific", "administrative"),
    ),
    GroupMeta(
        label="Criativo",
        icon="PALETTE_OUTLINED",
        profile_ids=("literary", "review", "storytelling"),
    ),
    GroupMeta(
        label="Rápido",
        icon="BOLT",
        profile_ids=("notes", "tldr", "flashcards"),
    ),
)

DEFAULT_PROFILE_ID = "default"


def get_profile(profile_id: str) -> AnalysisProfile:
    """Return the profile for *profile_id*, falling back to the default.

    Args:
        profile_id: Profile identifier (CLI ``--profile`` / settings value).

    Returns:
        The matching ``AnalysisProfile``; the default profile when unknown so a
        stale setting never breaks the pipeline.
    """
    return PROFILES.get(profile_id, PROFILES[DEFAULT_PROFILE_ID])


def list_profiles() -> list[str]:
    """Return all profile ids in registry order."""
    return list(PROFILES.keys())
