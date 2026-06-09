"""Shared text-chunking utilities for the LLM pipeline."""
from __future__ import annotations

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.llm_factory import is_gemini_model

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
    bypass_long_context is True and model_name identifies a Gemini model
    (which supports a 1M-token context window, making chunking unnecessary).

    Args:
        text: Full text to split.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Characters of overlap between consecutive chunks.
        model_name: Model name; evaluated only when bypass_long_context=True.
        bypass_long_context: Skip chunking for long-context providers (Gemini).
        separators: Priority-ordered split boundaries.
            Defaults to ["\n\n", "\n", ". ", " ", ""].

    Returns:
        List of text chunks (always at least one element).
    """
    if bypass_long_context and model_name and is_gemini_model(model_name):
        logging.debug("[d] Long context — chunking skipped (%d chars)", len(text))
        return [text]
    if len(text) <= chunk_size:
        return [text]
    seps = separators if separators is not None else _SEPARATORS
    logging.debug("[d] Splitting: chunk_size=%d | overlap=%d", chunk_size, chunk_overlap)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=seps,
    )
    return splitter.split_text(text)
