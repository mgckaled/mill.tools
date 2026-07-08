"""
analyzer.py: Structured analysis of transcriptions using LangChain.

Reads a transcription file, splits it into chunks if needed, sends each
chunk to the configured LLM (local Ollama or Google Gemini), and produces
a structured Markdown report with summary, key_points, action_items, and
topics.

Provider routing is handled by `src.llm_factory.make_llm`:
- model names starting with "gemini" → Google Gemini (requires GOOGLE_API_KEY)
- anything else → local Ollama

Usage (standalone):
    uv run yt-analyzer transcriptions/raw/transcricao_ovabeV.txt
    uv run yt-analyzer transcriptions/raw/transcricao_ovabeV.txt --model qwen7b-custom
    uv run yt-analyzer transcriptions/raw/transcricao_ovabeV.txt --model gemini-2.5-flash
    uv run yt-analyzer transcriptions/raw/transcricao_ovabeV.txt --verbose
"""

import argparse
import json
import logging
from collections.abc import Callable
from pathlib import Path
from time import time

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from src.analysis import (
    build_analysis_prompt,
    build_merge_prompt,
    format_report,
    get_profile,
    list_profiles,
)
from src.llm_factory import make_llm
from src.llm_utils import extract_llm_text, split_text
from src.transcript_io import parse_header_meta, split_header_body
from src.utils import TRANSCRIPTIONS_ANALYSIS_DIR, setup_logging

DEFAULT_MODEL = "gemma3-4b-custom"
DEFAULT_PROFILE = "default"
CHUNK_SIZE = 4500
CHUNK_OVERLAP = 300

DETECT_LANGUAGE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a language detector. Reply with ONLY the ISO 639-1 language code (e.g. pt, en, es, fr). No extra text.",
        ),
        ("human", "{text}"),
    ]
)

TRANSLATE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a professional translator. Translate the following JSON content "
                "to Brazilian Portuguese (pt-BR). Keep the JSON structure intact — translate "
                "ONLY the string values, not the keys. Respond with ONLY the translated JSON, "
                "no extra text."
            ),
        ),
        ("human", "{json_text}"),
    ]
)


def _parse_json_response(text: str) -> dict:
    """Extract and parse JSON from LLM response, handling markdown fences.

    Args:
        text: Raw LLM response that may contain JSON wrapped in ```json fences.

    Returns:
        Parsed dictionary with analysis fields.

    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logging.error("Failed to parse JSON from LLM response:\n%s", text)
        raise ValueError("LLM did not return valid JSON") from exc


def _invoke_and_parse(chain, payload: dict, *, retries: int = 1) -> dict:
    """Invoke *chain* and parse its JSON response, retrying once on failure.

    Local models occasionally emit malformed or truncated JSON (verbose schemas
    can run long). A single re-invocation usually recovers without failing the
    whole pipeline; only after exhausting the retries does the error propagate.

    Args:
        chain: A `prompt | llm` runnable returning a message with `.content`.
        payload: The variables to pass to `chain.invoke`.
        retries: Number of extra attempts after the first (default 1).

    Returns:
        The parsed analysis dict.

    Raises:
        ValueError: If every attempt yields invalid JSON.
    """
    last_exc: ValueError | None = None
    for attempt in range(retries + 1):
        response = chain.invoke(payload)
        try:
            return _parse_json_response(extract_llm_text(response.content))
        except ValueError as exc:
            last_exc = exc
            if attempt < retries:
                logging.warning(
                    "[!] Invalid JSON from model (attempt %d/%d) — retrying",
                    attempt + 1,
                    retries + 1,
                )
    assert last_exc is not None
    raise last_exc


def _split_text(text: str, model_name: str) -> list[str]:
    """Split transcription text into chunks for processing.

    When the provider supports a very large context window (Gemini, 1M tokens),
    chunking is skipped — the full body is processed in a single call. This
    produces a more coherent analysis (no merge step) and consumes fewer
    requests against the daily quota.

    Args:
        text: Full transcription text.
        model_name: Active model name; controls whether chunking is bypassed.

    Returns:
        List of text chunks. Returns single-element list if text is short enough
        or if the provider supports the full body in a single call.
    """
    return split_text(
        text,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        model_name=model_name,
        bypass_long_context=True,
    )


def _format_report(
    analysis: dict,
    source_path: Path,
    video_meta: dict | None = None,
    transcription: str | None = None,
) -> str:
    """Format the analysis dictionary as a Markdown report (default profile).

    Thin backward-compatible wrapper around ``src.analysis.format_report`` with
    the default profile — preserves the historical signature/output for callers
    and tests that render the legacy schema directly.

    Args:
        analysis: Dictionary with summary, key_points, action_items, etc.
        source_path: Path to the original transcription file.
        video_meta: Parsed metadata from the transcription header (optional).
        transcription: Formatted transcription body to append at the end (optional).

    Returns:
        Formatted Markdown string.
    """
    return format_report(
        get_profile(DEFAULT_PROFILE), analysis, source_path, video_meta, transcription
    )


def _ensure_portuguese(
    analysis: dict,
    llm: BaseChatModel,
    on_event: Callable[[str, str, dict], None] | None = None,
) -> dict:
    """Detect the language of the analysis and translate to PT-BR if needed.

    Uses the LLM to detect the language of the summary field. If it's not
    Portuguese, sends the full analysis JSON for translation.

    Args:
        analysis: Dictionary with analysis fields.
        llm: LangChain chat model already loaded (Ollama or Gemini).

    Returns:
        Original analysis if already in Portuguese, or translated version.
    """

    def _emit(type: str, payload: dict = {}) -> None:
        if on_event:
            on_event(type, "analyze", payload)

    summary = analysis.get("summary", "")
    if not summary:
        return analysis

    logging.info("[~] Detecting analysis language...")
    detect_chain = DETECT_LANGUAGE_PROMPT | llm
    lang_response = detect_chain.invoke({"text": summary[:500]})
    raw_lang = extract_llm_text(lang_response.content).strip()
    detected = raw_lang.lower()[:2]
    logging.debug("[d] Language raw response: %r → parsed: %r", raw_lang, detected)
    logging.info("[i] Detected language: %s", detected)
    _emit("language_detected", {"lang": detected})

    if detected == "pt":
        return analysis

    logging.info("[~] Translating analysis to PT-BR...")
    _emit("translation_start", {})
    json_text = json.dumps(analysis, ensure_ascii=False, indent=2)
    translate_chain = TRANSLATE_PROMPT | llm
    translated_response = translate_chain.invoke({"json_text": json_text})
    translated = _parse_json_response(extract_llm_text(translated_response.content))

    logging.info("[✓] Translation complete.")
    _emit("translation_done", {})
    return translated


def analyze(
    input_path: Path,
    model_name: str = DEFAULT_MODEL,
    transcription: str | None = None,
    on_event: Callable[[str, str, dict], None] | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Analyze a transcription file and generate a structured Markdown report.

    Reads the transcription, splits into chunks if needed, sends to the
    configured LLM for analysis, merges partial results, and writes the
    final report.

    Args:
        input_path: Path to the transcription .txt file.
        model_name: Model identifier — local Ollama tag (e.g. "qwen7b-custom")
            or Gemini name (e.g. "gemini-2.5-flash"). Provider is resolved by
            prefix in `llm_factory.make_llm`.
        transcription: Formatted transcription body to append to the report (optional).
            When provided (e.g. after --format), the full text is included at the
            bottom of the .md under a "Transcrição" section.
        profile: Analysis profile id (see ``src.analysis``). Drives the schema,
            prompts, temperature and report sections. ``"default"`` reproduces the
            historical 10-field video schema. Unknown ids fall back to default.

    Returns:
        Path to the generated .md report file.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If the LLM returns invalid JSON after all attempts.
    """

    def _emit(type: str, payload: dict = {}) -> None:
        if on_event:
            on_event(type, "analyze", payload)

    if not input_path.exists():
        logging.error("File not found: %s", input_path)
        raise FileNotFoundError(input_path)

    prof = get_profile(profile)
    analysis_prompt = build_analysis_prompt(prof)
    merge_prompt = build_merge_prompt(prof)

    logging.info("[*] Analyzing: %s", input_path.name)
    logging.info("[*] Model: %s | Profile: %s", model_name, prof.id)

    raw_text = input_path.read_text(encoding="utf-8")
    header_text, body = split_header_body(raw_text)
    video_meta = parse_header_meta(header_text)
    logging.debug(
        "[d] File: %d chars total | body after header strip: %d chars",
        len(raw_text),
        len(body),
    )

    if not body:
        logging.error("Transcription body is empty: %s", input_path)
        raise ValueError(f"Corpo da transcrição está vazio: {input_path.name}")

    chunks = _split_text(body, model_name)
    logging.info(
        "[i] Text split into %d chunk(s) (%d chars total)", len(chunks), len(body)
    )
    for i, chunk in enumerate(chunks, 1):
        logging.debug("[d] Chunk %d/%d: %d chars", i, len(chunks), len(chunk))
    _emit(
        "analyze_started",
        {
            "filename": input_path.name,
            "total_chunks": len(chunks),
            "model_name": model_name,
            "profile": prof.id,
        },
    )

    # análise e merge usam a temperatura do perfil
    llm = make_llm(model_name=model_name, temperature=prof.temperature)
    llm_util = make_llm(
        model_name=model_name, temperature=0
    )  # detecção de idioma e tradução

    start = time()

    if len(chunks) == 1:
        logging.info("[~] Analyzing single chunk...")
        _emit("analyze_chunk_start", {"i": 1, "total": 1})
        t_chunk = time()
        chain = analysis_prompt | llm
        analysis = _invoke_and_parse(chain, {"text": chunks[0]})
        chunk_elapsed = time() - t_chunk
        logging.debug(
            "[d] Single chunk done in %.1fs | keys: %s",
            chunk_elapsed,
            list(analysis.keys()),
        )
        _emit(
            "analyze_chunk_done",
            {"i": 1, "total": 1, "elapsed": round(chunk_elapsed, 1)},
        )
    else:
        partial_analyses = []
        for i, chunk in enumerate(chunks, 1):
            logging.info("[~] Analyzing chunk %d/%d...", i, len(chunks))
            _emit("analyze_chunk_start", {"i": i, "total": len(chunks)})
            t_chunk = time()
            chain = analysis_prompt | llm
            partial = _invoke_and_parse(chain, {"text": chunk})
            chunk_elapsed = time() - t_chunk
            logging.debug(
                "[d] Chunk %d done in %.1fs | keys: %s",
                i,
                chunk_elapsed,
                list(partial.keys()),
            )
            _emit(
                "analyze_chunk_done",
                {"i": i, "total": len(chunks), "elapsed": round(chunk_elapsed, 1)},
            )
            partial_analyses.append(partial)

        logging.info("[~] Merging %d partial analyses...", len(partial_analyses))
        _emit("analyze_merge_start", {"total_chunks": len(partial_analyses)})
        t_merge = time()
        merge_input = json.dumps(partial_analyses, ensure_ascii=False, indent=2)
        merge_chain = merge_prompt | llm
        analysis = _invoke_and_parse(merge_chain, {"analyses": merge_input})
        logging.debug("[d] Merge done in %.1fs", time() - t_merge)

    analysis = _ensure_portuguese(analysis, llm_util, on_event)

    elapsed = time() - start

    TRANSCRIPTIONS_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    report = format_report(prof, analysis, input_path, video_meta, transcription)
    output_path = TRANSCRIPTIONS_ANALYSIS_DIR / f"{input_path.stem}.md"
    output_path.write_text(report, encoding="utf-8")
    md_size_kb = output_path.stat().st_size / 1024
    logging.debug("[d] Report size: %.1f KB", md_size_kb)

    logging.info("[✓] Analysis saved to: %s (%.0fs)", output_path, elapsed)
    _emit(
        "analyze_done", {"elapsed": round(elapsed, 1), "output_path": str(output_path)}
    )
    return output_path


def main() -> None:
    """Entry point for standalone analyzer CLI."""
    parser = argparse.ArgumentParser(
        description="Analyze a transcription file using a local or cloud LLM.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_file",
        help="Path to the transcription .txt file",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model name — local Ollama (e.g. qwen7b-custom) or Gemini (e.g. gemini-2.5-flash)",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        choices=list_profiles(),
        help="Analysis profile (schema/prompt). 'default' keeps the legacy video schema.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    analyze(Path(args.input_file), model_name=args.model, profile=args.profile)
