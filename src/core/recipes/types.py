"""Typed model for linear, cross-module automation recipes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# Logical payload kinds that flow between steps. They describe what a step
# consumes/produces so the chain can be validated before any CPU is spent.
KIND_URL = "url"  # the initial input may be a URL
KIND_AUDIO = "audio"
KIND_VIDEO = "video"
KIND_IMAGE = "image"
KIND_PDF = "pdf"
KIND_TEXT = "text"  # transcription / extracted / OCR .txt
KIND_MARKDOWN = "markdown"  # analysis / digest .md
KIND_DATA = "data"  # structured data file (CSV/TSV/JSON/Parquet/XLSX)

ALL_KINDS = frozenset(
    {
        KIND_URL,
        KIND_AUDIO,
        KIND_VIDEO,
        KIND_IMAGE,
        KIND_PDF,
        KIND_TEXT,
        KIND_MARKDOWN,
        KIND_DATA,
    }
)


@dataclass(frozen=True, slots=True)
class RecipeStep:
    """One operation in a recipe: a registry key plus its parameters."""

    op: str  # registry key, e.g. "audio.normalize"
    params: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Recipe:
    """An ordered, named chain of steps."""

    name: str
    steps: list[RecipeStep]
    description: str = ""


@dataclass(frozen=True, slots=True)
class StepContext:
    """Runtime context handed to every step adapter.

    Carries the full run history so multi-input steps can reach back for outputs
    the linear ``current`` no longer holds — e.g. burning a subtitle needs the
    original video (the recipe's initial input) *and* the .srt produced two steps
    earlier. ``initial_inputs`` and ``outputs_by_op`` cover both.

    Attributes:
        emit: ``emit(type, payload)`` — forwards to an EventBus or CLIEventBus.
        cancel_is_set: ``() -> bool`` — checked between steps (never mid-step).
        initial_inputs: The recipe's original inputs (``[url]`` or ``[Path, ...]``).
        outputs_by_op: Op key → that step's outputs, accumulated as the run goes.
    """

    emit: Callable
    cancel_is_set: Callable[[], bool]
    initial_inputs: list
    outputs_by_op: dict


@dataclass(frozen=True, slots=True)
class StepSpec:
    """Registry entry: the adapter plus its type contract.

    Attributes:
        adapter: ``(inputs: list, params: dict, ctx: StepContext) -> list[Path]``.
        accepts: Input kinds this step can consume.
        produces: Output kind this step emits.
        label: PT-BR label shown in the GUI/CLI.
    """

    adapter: Callable
    accepts: frozenset[str]
    produces: str
    label: str
