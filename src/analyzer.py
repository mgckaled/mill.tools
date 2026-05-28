"""
analyzer.py: Structured analysis of transcriptions using LangChain + Ollama.

Reads a transcription file, splits it into chunks if needed, sends each
chunk to a local Ollama model, and produces a structured Markdown report
with summary, key_points, action_items, and topics.

Usage (standalone):
    uv run yt-analyzer transcriptions/raw/transcricao_ovabeV.txt
    uv run yt-analyzer transcriptions/raw/transcricao_ovabeV.txt --model phi4-mini
    uv run yt-analyzer transcriptions/raw/transcricao_ovabeV.txt --verbose
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from time import time

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.utils import setup_logging, TRANSCRIPTIONS_ANALYSIS_DIR

DEFAULT_MODEL = "qwen7b-custom"
CHUNK_SIZE = 4500
CHUNK_OVERLAP = 300

ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "Você é um analista especialista. Você recebe a transcrição de um vídeo do YouTube "
        "e deve produzir uma análise estruturada em formato JSON. "
        "Responda APENAS com JSON válido, sem texto extra antes ou depois. "
        "Responda SEMPRE em português brasileiro.\n\n"
        "Estrutura JSON obrigatória:\n"
        '{{\n'
        '  "summary": "Um parágrafo conciso resumindo o conteúdo principal.",\n'
        '  "key_points": ["ponto 1", "ponto 2", "..."],\n'
        '  "action_items": ["ação 1", "ação 2", "..."],\n'
        '  "topics": ["tópico 1", "tópico 2", "..."]\n'
        '}}\n\n'
        "Regras:\n"
        "- summary: 3-5 frases, capture a essência\n"
        "- key_points: 5-10 pontos mais importantes\n"
        "- action_items: passos práticos ou recomendações mencionados (lista vazia se nenhum)\n"
        "- topics: principais assuntos/temas discutidos"
    )),
    ("human", "Transcrição:\n\n{text}"),
])

DETECT_LANGUAGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a language detector. Reply with ONLY the ISO 639-1 language code (e.g. pt, en, es, fr). No extra text."),
    ("human", "{text}"),
])

TRANSLATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a professional translator. Translate the following JSON content "
        "to Brazilian Portuguese (pt-BR). Keep the JSON structure intact — translate "
        "ONLY the string values, not the keys. Respond with ONLY the translated JSON, "
        "no extra text."
    )),
    ("human", "{json_text}"),
])

MERGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "Você é um analista especialista. Você recebe múltiplas análises parciais de uma "
        "única transcrição de vídeo do YouTube (que foi dividida em partes). "
        "Consolide tudo em UMA análise coerente. Remova duplicatas, "
        "unifique pontos sobrepostos e produza uma visão unificada.\n\n"
        "Responda APENAS com JSON válido, sem texto extra antes ou depois. "
        "Responda SEMPRE em português brasileiro.\n\n"
        "Estrutura JSON obrigatória:\n"
        '{{\n'
        '  "summary": "Um parágrafo conciso resumindo o conteúdo principal.",\n'
        '  "key_points": ["ponto 1", "ponto 2", "..."],\n'
        '  "action_items": ["ação 1", "ação 2", "..."],\n'
        '  "topics": ["tópico 1", "tópico 2", "..."]\n'
        '}}'
    )),
    ("human", "Análises parciais para consolidar:\n\n{analyses}"),
])


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


def _split_text(text: str) -> list[str]:
    """Split transcription text into chunks for processing.

    Uses RecursiveCharacterTextSplitter to break text at natural boundaries
    (paragraphs, sentences, words) while respecting chunk size limits.

    Args:
        text: Full transcription text.

    Returns:
        List of text chunks. Returns single-element list if text is short enough.
    """
    if len(text) <= CHUNK_SIZE:
        return [text]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)


def _extract_transcription_body(raw_text: str) -> str:
    """Separate the metadata header from the transcription body.

    The transcription files have a metadata header separated from the body
    by a line of dashes (64 '-' characters). This function returns only
    the body text after that separator.

    Args:
        raw_text: Full file content including metadata header.

    Returns:
        The transcription body without metadata header.
    """
    separator = "-" * 64
    if separator in raw_text:
        return raw_text.split(separator, 1)[1].strip()
    return raw_text.strip()


def _format_report(analysis: dict, source_path: Path) -> str:
    """Format the analysis dictionary as a Markdown report.

    Args:
        analysis: Dictionary with summary, key_points, action_items, topics.
        source_path: Path to the original transcription file.

    Returns:
        Formatted Markdown string.
    """
    lines = [
        f"# Análise: {source_path.stem}",
        "",
        f"> Fonte: `{source_path.name}`",
        "",
        "## Resumo",
        "",
        analysis.get("summary", "N/A"),
        "",
        "## Pontos-chave",
        "",
    ]
    for point in analysis.get("key_points", []):
        lines.append(f"- {point}")

    lines.extend(["", "## Ações sugeridas", ""])
    actions = analysis.get("action_items", [])
    if actions:
        for action in actions:
            lines.append(f"- {action}")
    else:
        lines.append("Nenhuma ação identificada.")

    lines.extend(["", "## Tópicos", ""])
    for topic in analysis.get("topics", []):
        lines.append(f"- {topic}")

    lines.append("")
    return "\n".join(lines)


def _ensure_portuguese(analysis: dict, llm: ChatOllama) -> dict:
    """Detect the language of the analysis and translate to PT-BR if needed.

    Uses the LLM to detect the language of the summary field. If it's not
    Portuguese, sends the full analysis JSON for translation.

    Args:
        analysis: Dictionary with analysis fields.
        llm: ChatOllama instance already loaded.

    Returns:
        Original analysis if already in Portuguese, or translated version.
    """
    summary = analysis.get("summary", "")
    if not summary:
        return analysis

    logging.info("[~] Detecting analysis language...")
    detect_chain = DETECT_LANGUAGE_PROMPT | llm
    lang_response = detect_chain.invoke({"text": summary[:500]})
    detected = lang_response.content.strip().lower()[:2]
    logging.info("[i] Detected language: %s", detected)

    if detected == "pt":
        return analysis

    logging.info("[~] Translating analysis to PT-BR...")
    json_text = json.dumps(analysis, ensure_ascii=False, indent=2)
    translate_chain = TRANSLATE_PROMPT | llm
    translated_response = translate_chain.invoke({"json_text": json_text})
    translated = _parse_json_response(translated_response.content)

    logging.info("[✓] Translation complete.")
    return translated


def analyze(
    input_path: Path,
    model_name: str = DEFAULT_MODEL,
) -> Path:
    """Analyze a transcription file and generate a structured Markdown report.

    Reads the transcription, splits into chunks if needed, sends to Ollama
    for analysis, merges partial results, and writes the final report.

    Args:
        input_path: Path to the transcription .txt file.
        model_name: Ollama model to use for analysis.

    Returns:
        Path to the generated .md report file.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If the LLM returns invalid JSON after all attempts.
    """
    if not input_path.exists():
        logging.error("File not found: %s", input_path)
        raise FileNotFoundError(input_path)

    logging.info("[*] Analyzing: %s", input_path.name)
    logging.info("[*] Model: %s", model_name)

    raw_text = input_path.read_text(encoding="utf-8")
    body = _extract_transcription_body(raw_text)
    logging.debug("[d] File: %d chars total | body after header strip: %d chars",
                  len(raw_text), len(body))

    if not body:
        logging.error("Transcription body is empty: %s", input_path)
        sys.exit(1)

    chunks = _split_text(body)
    logging.info("[i] Text split into %d chunk(s) (%d chars total)",
                 len(chunks), len(body))
    for i, chunk in enumerate(chunks, 1):
        logging.debug("[d] Chunk %d/%d: %d chars", i, len(chunks), len(chunk))

    llm = ChatOllama(model=model_name, temperature=0)

    start = time()

    if len(chunks) == 1:
        logging.info("[~] Analyzing single chunk...")
        chain = ANALYSIS_PROMPT | llm
        response = chain.invoke({"text": chunks[0]})
        analysis = _parse_json_response(response.content)
    else:
        partial_analyses = []
        for i, chunk in enumerate(chunks, 1):
            logging.info("[~] Analyzing chunk %d/%d...", i, len(chunks))
            t_chunk = time()
            chain = ANALYSIS_PROMPT | llm
            response = chain.invoke({"text": chunk})
            partial = _parse_json_response(response.content)
            logging.debug("[d] Chunk %d done in %.1fs | response: %d chars | keys: %s",
                          i, time() - t_chunk, len(response.content), list(partial.keys()))
            partial_analyses.append(partial)

        logging.info("[~] Merging %d partial analyses...", len(partial_analyses))
        t_merge = time()
        merge_input = json.dumps(partial_analyses, ensure_ascii=False, indent=2)
        merge_chain = MERGE_PROMPT | llm
        merge_response = merge_chain.invoke({"analyses": merge_input})
        analysis = _parse_json_response(merge_response.content)
        logging.debug("[d] Merge done in %.1fs", time() - t_merge)

    analysis = _ensure_portuguese(analysis, llm)

    elapsed = time() - start

    TRANSCRIPTIONS_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    report = _format_report(analysis, input_path)
    output_path = TRANSCRIPTIONS_ANALYSIS_DIR / f"{input_path.stem}.md"
    output_path.write_text(report, encoding="utf-8")

    logging.info("[✓] Analysis saved to: %s (%.0fs)", output_path, elapsed)
    return output_path


def main() -> None:
    """Entry point for standalone analyzer CLI."""
    parser = argparse.ArgumentParser(
        description="Analyze a transcription file using Ollama (local LLM).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_file",
        help="Path to the transcription .txt file",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Ollama model name",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    analyze(Path(args.input_file), model_name=args.model)
