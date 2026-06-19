"""Shared text-chunking utilities for the LLM pipeline."""

from __future__ import annotations

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.llm_factory import is_gemini_model, long_context_char_budget

# Default separators: paragraph breaks first, then sentence, word, character.
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def split_text(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    model_name: str | None = None,
    bypass_long_context: bool = False,
    separators: list[str] | None = None,
) -> list[str]:
    """Split text into chunks with RecursiveCharacterTextSplitter.

    Returns [text] unchanged when the text fits within chunk_size, or when
    bypass_long_context is True and the model supports a large context window:
    Gemini (1M tokens) bypasses unconditionally; known long-context local models
    (e.g. gemma3-4b-custom) bypass only while the text stays within their char
    budget — above it, chunking resumes to keep a CPU single pass practical.

    Args:
        text: Full text to split.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Characters of overlap between consecutive chunks.
        model_name: Model name; evaluated only when bypass_long_context=True.
        bypass_long_context: Skip chunking for long-context models.
        separators: Priority-ordered split boundaries.
            Defaults to ["\n\n", "\n", ". ", " ", ""].

    Returns:
        List of text chunks (always at least one element).
    """
    if bypass_long_context and model_name:
        if is_gemini_model(model_name):
            logging.debug(
                "[d] Long context (Gemini) — chunking skipped (%d chars)", len(text)
            )
            return [text]
        budget = long_context_char_budget(model_name)
        if budget is not None and len(text) <= budget:
            logging.debug(
                "[d] Long context (%s) — chunking skipped (%d <= %d chars)",
                model_name,
                len(text),
                budget,
            )
            return [text]
    if len(text) <= chunk_size:
        return [text]
    seps = separators if separators is not None else _SEPARATORS
    logging.debug(
        "[d] Splitting: chunk_size=%d | overlap=%d", chunk_size, chunk_overlap
    )
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=seps,
    )
    return splitter.split_text(text)
