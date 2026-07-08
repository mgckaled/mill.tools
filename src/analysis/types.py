"""
types.py: Data model for selectable analysis profiles.

A profile describes a structured-analysis schema as a list of fields. The
analysis/merge prompts and the Markdown report are *generated* from these
fields, so adding a profile is a single catalog entry — no prompt/report
duplication.

This module is pure (no Flet, no LangChain). The ``icon`` attribute holds an
``ft.Icons.*`` name as a plain string; the GUI resolves it via ``getattr``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Field render kinds — control how a field is rendered in the report and which
# JSON skeleton placeholder it gets in the generated prompt.
KIND_PARAGRAPH = "paragraph"  # plain text block
KIND_LIST = "list"  # bullet list
KIND_QUOTES = "quotes"  # blockquote list
KIND_KEYVALUE = "keyvalue"  # bullet list of "Term: definition" items

ALL_KINDS = frozenset({KIND_PARAGRAPH, KIND_LIST, KIND_QUOTES, KIND_KEYVALUE})


@dataclass(frozen=True)
class Field:
    """A single field of an analysis profile.

    Attributes:
        key: JSON key emitted by the LLM and read back from the response.
        title: Section heading used in the Markdown report.
        kind: One of ``ALL_KINDS`` — controls report rendering and the JSON
            skeleton placeholder in the generated prompt.
        rule: Instruction for the field; becomes a ``"- {key}: {rule}"`` line in
            the prompt's rules block.
        always: When True, the section is rendered even if the value is empty
            (used to reproduce the default schema's Resumo/Pontos-chave/Ações).
        empty_text: Placeholder rendered when ``always`` and the value is empty
            (e.g. "Nenhuma ação identificada." / "N/A").
    """

    key: str
    title: str
    kind: str
    rule: str
    always: bool = False
    empty_text: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ALL_KINDS:
            raise ValueError(
                f"Field {self.key!r} has unknown kind {self.kind!r} "
                f"(expected one of {sorted(ALL_KINDS)})"
            )
        if self.always and not self.empty_text:
            raise ValueError(
                f"Field {self.key!r} has always=True but no empty_text — "
                "an always-rendered section left empty has no placeholder text"
            )


@dataclass(frozen=True)
class AnalysisProfile:
    """A selectable analysis profile.

    Attributes:
        id: Stable identifier used by the CLI ``--profile`` flag and settings.
        label: Short PT-BR label shown on the GUI card.
        icon: ``ft.Icons.*`` name (string); resolved by the GUI, never imported
            here so the core stays Flet-free.
        persona: First sentence of the system prompt (the analyst's role).
        source_hint: How the source is described in the prompt — e.g.
            "transcrição de uma aula", "gravação de uma reunião".
        fields: Ordered tuple of fields that make up the schema.
        temperature: Sampling temperature for the analysis/merge calls.
        disclaimer: Optional notice inserted at the top of the report (legal/health).
    """

    id: str
    label: str
    icon: str
    persona: str
    source_hint: str
    fields: tuple[Field, ...]
    temperature: float = 0.4
    disclaimer: str = ""

    def __post_init__(self) -> None:
        keys = [f.key for f in self.fields]
        if any(not key for key in keys):
            raise ValueError(f"Profile {self.id!r} has a field with an empty key")
        if len(keys) != len(set(keys)):
            dupes = sorted({key for key in keys if keys.count(key) > 1})
            raise ValueError(f"Profile {self.id!r} has duplicate field keys: {dupes}")


@dataclass(frozen=True)
class GroupMeta:
    """A labelled group of profiles for the grouped GUI selector.

    Attributes:
        label: Section label shown above the group of cards.
        icon: ``ft.Icons.*`` name for the section (string; GUI resolves).
        profile_ids: Ordered profile ids belonging to this group.
    """

    label: str
    icon: str
    profile_ids: tuple[str, ...]
