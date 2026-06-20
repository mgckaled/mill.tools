"""
prompter.py: Condensed transcription generation for use as LLM context.

Reads a raw transcription file and produces a dense, information-rich version
optimized for use as context in future LLM prompts. Removes filler, CTAs,
repetitions and sponsor mentions while retaining all technical content.

Provider routing is handled by `src.llm_factory.make_llm`:
- model names starting with "gemini" → Google Gemini (requires GOOGLE_API_KEY)
- anything else → local Ollama

When the provider supports a very large context window (Gemini, 1M tokens),
chunking is skipped — the full body is condensed in a single pass, producing
better coherence and skipping the merge step.

Output is saved to transcriptions/prompt_ready/ with the same stem as the source.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from time import time

from langchain_core.prompts import ChatPromptTemplate

from src.llm_factory import make_llm
from src.llm_utils import split_text
from src.utils import TRANSCRIPTIONS_DIGEST_DIR

DEFAULT_PROMPT_MODEL = "gemma3-4b-custom"
PROMPT_CHUNK_SIZE = 4500
PROMPT_CHUNK_OVERLAP = 200
SEPARATOR = "-" * 64

CONDENSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You receive a segment of a YouTube video transcription. "
                "Your task: rewrite it as a dense, information-rich context block for an LLM.\n\n"
                "KEEP: all technical content, facts, arguments, definitions, examples, data points, "
                "named entities, step-by-step instructions, opinions backed by reasoning.\n\n"
                "REMOVE: greetings, sign-offs, CTAs (subscribe/like/comment), sponsor mentions, "
                "filler phrases ('you know', 'like I said', 'basically', 'so'), repetitions, "
                "meta-comments about the video itself ('in this video I will show you...').\n\n"
                "RULES:\n"
                "- Keep the same language as the input\n"
                "- Write in continuous prose; no bullet points, no headers\n"
                "- Preserve the original voice and wording where dense; paraphrase only filler\n"
                "- Target ~40% of the original word count while retaining ~90% of the information\n"
                "- Output ONLY the condensed text, no preamble, no commentary"
            ),
        ),
        ("human", "{text}"),
    ]
)

MERGE_CONDENSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You receive multiple condensed segments of the same video transcription. "
                "Join them into a single coherent context block.\n\n"
                "RULES:\n"
                "- Remove any duplicated ideas that appear across segments\n"
                "- Keep all distinct technical content and facts\n"
                "- Write in continuous prose; maintain logical flow between segments\n"
                "- Keep the same language as the input\n"
                "- Output ONLY the final condensed text, no preamble"
            ),
        ),
        ("human", "Segments to join:\n\n{segments}"),
    ]
)


def _split_for_prompt(text: str, model_name: str) -> list[str]:
    """Split transcription body into chunks for condensation.

    When the provider supports a 1M-token context (Gemini), chunking is
    skipped so the model can condense the whole body coherently in a single
    pass and the merge step is avoided.

    Args:
        text: Full transcription body.
        model_name: Active model name; controls whether chunking is bypassed.

    Returns:
        List of text chunks.
    """
    return split_text(
        text,
        chunk_size=PROMPT_CHUNK_SIZE,
        chunk_overlap=PROMPT_CHUNK_OVERLAP,
        model_name=model_name,
        bypass_long_context=True,
    )


def _extract_body_and_meta(raw_text: str) -> tuple[str, dict]:
    """Separate the metadata header from the transcription body.

    Args:
        raw_text: Full file content including metadata header.

    Returns:
        Tuple of (body text, metadata dict).
    """
    if SEPARATOR not in raw_text:
        return raw_text.strip(), {}

    header_text, body = raw_text.split(SEPARATOR, 1)
    meta = {}
    for line in header_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key and value:
                meta[key] = value
    return body.strip(), meta


def build_prompt_ready(
    input_path: Path,
    model_name: str = DEFAULT_PROMPT_MODEL,
    on_event: Callable[[str, str, dict], None] | None = None,
) -> Path:
    """Generate a condensed transcription file optimized for use as LLM context.

    Reads the raw transcription, strips metadata header, condenses the body
    using a local LLM, and writes the result to transcriptions/prompt_ready/.

    The output file has a minimal header (title, URL) followed by the condensed
    prose — ready to paste as context in any LLM prompt.

    Args:
        input_path: Path to the transcription .txt file.
        model_name: Model identifier — local Ollama tag (e.g. "qwen7b-custom")
            or Gemini name (e.g. "gemini-2.5-flash"). Provider is resolved by
            prefix in `llm_factory.make_llm`.

    Returns:
        Path to the generated prompt-ready .txt file.

    Raises:
        FileNotFoundError: If the input file does not exist.
    """

    def _emit(type: str, payload: dict = {}) -> None:
        if on_event:
            on_event(type, "prompt", payload)

    if not input_path.exists():
        logging.error("File not found: %s", input_path)
        raise FileNotFoundError(input_path)

    logging.info("[*] Building prompt-ready: %s", input_path.name)
    logging.info("[*] Prompt model: %s", model_name)

    raw_text = input_path.read_text(encoding="utf-8")
    body, meta = _extract_body_and_meta(raw_text)

    if not body:
        logging.warning("[!] Empty transcription body, skipping prompt-ready.")
        return input_path

    logging.debug("[d] Body to condense: %d chars", len(body))

    chunks = _split_for_prompt(body, model_name)
    logging.info("[i] %d chunk(s) to condense (%d chars total)", len(chunks), len(body))
    _emit(
        "prompt_started",
        {
            "filename": input_path.name,
            "total_chunks": len(chunks),
            "model_name": model_name,
        },
    )

    llm = make_llm(model_name=model_name, temperature=0.2)
    condense_chain = CONDENSE_PROMPT | llm

    start = time()
    condensed_chunks = []
    for i, chunk in enumerate(chunks, 1):
        logging.info("[~] Condensing chunk %d/%d...", i, len(chunks))
        _emit("prompt_chunk_start", {"i": i, "total": len(chunks)})
        t = time()
        response = condense_chain.invoke({"text": chunk})
        chunk_elapsed = time() - t
        condensed_chunks.append(response.content.strip())
        logging.debug(
            "[d] Chunk %d done in %.1fs | output: %d chars",
            i,
            chunk_elapsed,
            len(response.content),
        )
        _emit(
            "prompt_chunk_done",
            {"i": i, "total": len(chunks), "elapsed": round(chunk_elapsed, 1)},
        )

    if len(condensed_chunks) > 1:
        logging.info("[~] Merging %d condensed chunks...", len(condensed_chunks))
        merge_chain = MERGE_CONDENSE_PROMPT | llm
        joined = "\n\n---\n\n".join(condensed_chunks)
        merge_response = merge_chain.invoke({"segments": joined})
        final_body = merge_response.content.strip()
    else:
        final_body = condensed_chunks[0]

    elapsed = time() - start

    title = meta.get("title", input_path.stem)
    url = meta.get("url", "")
    duration = meta.get("duration", "")

    header_parts = [f"# {title}"]
    if duration:
        header_parts.append(f"# Duração: {duration}")
    if url:
        header_parts.append(f"# Fonte: {url}")
    header_parts.extend(["#", ""])

    result = "\n".join(header_parts) + final_body + "\n"

    TRANSCRIPTIONS_DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TRANSCRIPTIONS_DIGEST_DIR / input_path.name
    output_path.write_text(result, encoding="utf-8")

    ratio = len(final_body) / len(body) * 100 if body else 0
    logging.debug(
        "[d] Condensed: %d → %d chars (%.0f%% of original)",
        len(body),
        len(final_body),
        ratio,
    )
    logging.info("[✓] Prompt-ready saved to: %s (%.0fs)", output_path, elapsed)
    _emit(
        "prompt_done",
        {"elapsed": round(elapsed, 1), "ratio": ratio, "output_path": str(output_path)},
    )
    return output_path
