"""
Selectable analysis profiles for the structured analyzer.

This package generates the analysis/merge prompts and the Markdown report from a
profile's field list, so adding a profile is a single catalog entry. It is pure
(no Flet): the GUI resolves the string ``icon`` names itself.
"""

from src.analysis.profiles import (
    DEFAULT_PROFILE_ID,
    GROUPS,
    PROFILES,
    get_profile,
    list_profiles,
)
from src.analysis.prompts import build_analysis_prompt, build_merge_prompt
from src.analysis.report import format_report
from src.analysis.types import (
    ALL_KINDS,
    KIND_KEYVALUE,
    KIND_LIST,
    KIND_PARAGRAPH,
    KIND_QUOTES,
    AnalysisProfile,
    Field,
    GroupMeta,
)

__all__ = [
    "ALL_KINDS",
    "DEFAULT_PROFILE_ID",
    "GROUPS",
    "KIND_KEYVALUE",
    "KIND_LIST",
    "KIND_PARAGRAPH",
    "KIND_QUOTES",
    "PROFILES",
    "AnalysisProfile",
    "Field",
    "GroupMeta",
    "build_analysis_prompt",
    "build_merge_prompt",
    "format_report",
    "get_profile",
    "list_profiles",
]
