"""Shared fixtures for core/text tests.

``messy_pdf_text`` reproduces the reported screenshot bug: an English PDF
("Claude's Constitution") whose extracted text is dominated by page markers,
unpunctuated front matter (title/author/date/section headers) and dashed list
items with no terminal punctuation — the exact shape ``core/text/clean.py``
(PLANO_INSIGHTS_QUALIDADE.md, Fase 2) must strip before ``summarize``/
``keywords`` ever see the text. It is the acceptance fixture for Fases 2–3:
the eventual summary must not contain a page marker, a front-matter line or a
sentence truncated at an abbreviation.
"""

from __future__ import annotations

import pytest

# Matches core/document/converter.py::extract_text's exact marker format —
# the format this fixture must stay byte-for-byte in sync with.
PAGE_MARKER_1 = "--- Página 1 ---"
PAGE_MARKER_2 = "--- Página 2 ---"

MESSY_PDF_TEXT = (
    f"\n\n{PAGE_MARKER_1}\n\n"
    "Claude's Constitution\n"
    "Anthropic\n"
    "January 2024\n"
    "Acknowledgments\n"
    f"\n\n{PAGE_MARKER_2}\n\n"
    "This document describes the constitution that guides Claude's behavior, "
    "e.g. how it should respond to ambiguous or sensitive user requests. The "
    "constitution reflects input from ethicists, policy experts, and "
    "researchers, i.e. a broad set of external stakeholders, including "
    "Dr. Jane Doe et al. from several partner institutions. It aims to make "
    "Claude helpful, honest, and harmless in practice, not just in theory.\n"
    "- Helpful\n"
    "- Honest\n"
    "- Harmless\n"
    "The constitution is a living document that will continue to be updated "
    "as our collective understanding of these tradeoffs improves over time.\n"
)


@pytest.fixture
def messy_pdf_text() -> str:
    """The screenshot-reproduction text (see module docstring)."""
    return MESSY_PDF_TEXT
