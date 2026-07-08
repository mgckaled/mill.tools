"""
formatter.py: Paragraph segmentation of raw transcriptions.

Reads the transcription body, sends it to the configured LLM (local Ollama or
Google Gemini) to insert paragraph breaks at natural boundaries, and writes the
result back in place. No words are changed — only blank lines are added.

Provider routing is handled by `src.llm_factory.make_llm`:
- model names starting with "gemini" → Google Gemini (requires GOOGLE_API_KEY)
- anything else → local Ollama

Note on chunking: paragraph segmentation is a per-region task with no benefit
from global context, so chunking is preserved for both providers.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from time import time

from langchain_core.prompts import ChatPromptTemplate

from src.llm_factory import make_llm
from src.llm_utils import extract_llm_text, split_text

DEFAULT_FORMAT_MODEL = "phi4mini-custom"
FORMAT_CHUNK_SIZE = 4500
FORMAT_CHUNK_OVERLAP = 150
SEPARATOR = "-" * 64

FORMAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You receive a raw speech transcription without paragraph breaks. "
                "Your ONLY task is to insert blank lines between paragraphs at natural topic or idea boundaries.\n\n"
                "STRICT RULES:\n"
                "- Output the EXACT same words in the EXACT same order\n"
                "- Do NOT change, correct, add, or remove any word\n"
                "- Do NOT fix punctuation or spelling\n"
                "- Only insert blank lines (two newlines) between paragraphs\n"
                "- Insert a break where a new topic, idea, or logical section begins\n"
                "- Keep paragraphs between 3 and 8 sentences\n"
                "- PRESERVE all [?] markers exactly where they appear — they are quality indicators, not part of the speech\n"
                "- Output ONLY the formatted text, no explanations or comments"
            ),
        ),
        ("human", "{text}"),
    ]
)


# Sentence-boundary separators — formatter splits at sentence ends, not paragraph
# breaks, to avoid cutting mid-sentence when inserting paragraph markers.
_FORMAT_SEPARATORS = [". ", "? ", "! ", " ", ""]


def _split_for_format(text: str) -> list[str]:
    """Split transcription body into chunks for paragraph formatting.

    Uses sentence boundaries as split points to avoid cutting mid-sentence.

    Args:
        text: Full transcription body.

    Returns:
        List of text chunks.
    """
    return split_text(
        text,
        chunk_size=FORMAT_CHUNK_SIZE,
        chunk_overlap=FORMAT_CHUNK_OVERLAP,
        separators=_FORMAT_SEPARATORS,
    )


def format_transcription(
    input_path: Path,
    model_name: str = DEFAULT_FORMAT_MODEL,
    on_event: Callable[[str, str, dict], None] | None = None,
) -> str | None:
    """Add paragraph breaks to a raw transcription file using a local LLM.

    Reads the transcription body, formats it with paragraph breaks, and
    writes the result back in place. The metadata header is preserved intact.
    No words are added, removed, or changed — only blank lines are inserted.

    Args:
        input_path: Path to the transcription .txt file.
        model_name: Model identifier — local Ollama tag (e.g. "phi4mini-custom")
            or Gemini name (e.g. "gemini-2.5-flash"). Provider is resolved by
            prefix in `llm_factory.make_llm`.

    Returns:
        The formatted transcription body, or None if the body was empty.

    Raises:
        FileNotFoundError: If the input file does not exist.
    """

    def _emit(type: str, payload: dict = {}) -> None:
        if on_event:
            on_event(type, "format", payload)

    if not input_path.exists():
        logging.error("File not found: %s", input_path)
        raise FileNotFoundError(input_path)

    logging.info("[*] Formatting: %s", input_path.name)
    logging.info("[*] Format model: %s", model_name)

    raw_text = input_path.read_text(encoding="utf-8")

    if SEPARATOR in raw_text:
        header, body = raw_text.split(SEPARATOR, 1)
        body = body.strip()
    else:
        header = ""
        body = raw_text.strip()

    if not body:
        logging.warning("[!] Empty transcription body, skipping format.")
        return None

    logging.debug("[d] Body to format: %d chars", len(body))

    chunks = _split_for_format(body)
    logging.info("[i] %d chunk(s) to format (%d chars total)", len(chunks), len(body))
    for i, chunk in enumerate(chunks, 1):
        logging.debug("[d] Chunk %d/%d: %d chars", i, len(chunks), len(chunk))
    _emit(
        "format_started",
        {
            "filename": input_path.name,
            "total_chunks": len(chunks),
            "model_name": model_name,
        },
    )

    llm = make_llm(model_name=model_name, temperature=0)
    chain = FORMAT_PROMPT | llm

    start = time()
    formatted_chunks = []
    for i, chunk in enumerate(chunks, 1):
        logging.info("[~] Formatting chunk %d/%d...", i, len(chunks))
        _emit("format_chunk_start", {"i": i, "total": len(chunks)})
        t = time()
        response = chain.invoke({"text": chunk})
        text = extract_llm_text(response.content).strip()
        formatted_chunks.append(text)
        chunk_elapsed = time() - t
        logging.debug(
            "[d] Chunk %d done in %.1fs | output: %d chars",
            i,
            chunk_elapsed,
            len(text),
        )
        _emit(
            "format_chunk_done",
            {"i": i, "total": len(chunks), "elapsed": round(chunk_elapsed, 1)},
        )

    formatted_body = "\n\n".join(formatted_chunks)

    if not formatted_body:
        logging.warning("[!] LLM retornou resposta vazia — arquivo não modificado.")
        return body

    if header:
        result = header + SEPARATOR + "\n\n" + formatted_body + "\n"
    else:
        result = formatted_body + "\n"

    input_path.write_text(result, encoding="utf-8")
    elapsed = time() - start
    logging.debug("[d] Formatted body: %d chars", len(formatted_body))
    logging.info("[✓] Formatted in place: %s (%.0fs)", input_path.name, elapsed)
    _emit("format_done", {"elapsed": round(elapsed, 1), "output_path": str(input_path)})
    return formatted_body
