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
from datetime import datetime
from pathlib import Path
from time import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.utils import TRANSCRIPTIONS_ANALYSIS_DIR, setup_logging

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
        '  "key_concepts": ["Termo: definição curta de uma linha", "..."],\n'
        '  "tools_mentioned": ["ferramenta ou tecnologia 1", "..."],\n'
        '  "metrics": ["número ou estatística com contexto", "..."],\n'
        '  "quotes": ["frase notável do speaker com contexto mínimo", "..."],\n'
        '  "assumptions": ["premissa implícita identificada", "..."],\n'
        '  "vocabulary": ["Jargão: definição inferida do contexto", "..."],\n'
        '  "sentiment_arc": "evolução do tom ao longo do conteúdo"\n'
        '}}\n\n'
        "Regras:\n"
        "- summary: 3-5 frases, capture a essência\n"
        "- key_points: 5-10 pontos mais importantes; cada ponto deve ser uma frase completa com sujeito e verbo, "
        "com no mínimo 12 palavras; explique o 'como' ou 'por que' sempre que possível, não apenas liste fatos; "
        "ERRADO: 'Bolo feito no liquidificador' | CERTO: 'O liquidificador substitui a batedeira ao emulsionar os ingredientes, resultando em massa mais homogênea e fofa'; "
        "IGNORE CTAs (curtir, inscrever, comentar), patrocinadores e autopromoção\n"
        "- action_items: passos práticos ou recomendações mencionados (lista vazia se nenhum); "
        "IGNORE pedidos de inscrição, curtida ou comentário\n"
        "- key_concepts: conceitos abstratos ou técnicos centrais para entender o tema, formato obrigatório 'Termo: definição de uma linha'; "
        "Ex: 'Fermento químico: agente que libera CO2 durante o cozimento, tornando a massa mais leve'; "
        "(lista vazia se nenhum)\n"
        "- tools_mentioned: ferramentas, bibliotecas, plataformas ou tecnologias citadas (lista vazia se nenhuma)\n"
        "- metrics: números, estatísticas, durações, quantidades mencionadas com seu contexto (lista vazia se nenhuma)\n"
        "- quotes: até 5 frases marcantes ou citações quase literais do speaker que sintetizem bem uma ideia; "
        "inclua contexto mínimo entre parênteses se necessário; (lista vazia se nenhuma)\n"
        "- assumptions: até 5 premissas implícitas que o speaker assume como verdade sem questionar; "
        "formule como afirmação, ex: 'O público já conhece os fundamentos de X'; (lista vazia se nenhuma)\n"
        "- vocabulary: jargões, siglas ou termos de nicho usados pelo speaker, formato 'Termo: definição inferida'; "
        "diferente de key_concepts — foco em linguagem específica do domínio/nicho; (lista vazia se nenhum)\n"
        "- sentiment_arc: UMA frase descrevendo como o tom evolui do início ao fim; "
        "ex: 'Introdução técnica e expositiva → aprofundamento crítico → encerramento motivacional'"
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
        "única transcrição de vídeo do YouTube dividida em partes. "
        "Sua tarefa é consolidar tudo em UMA análise final coerente e bem escrita.\n\n"
        "Regras de consolidação:\n"
        "- Elimine pontos duplicados ou semanticamente equivalentes — mantenha apenas a versão mais completa\n"
        "- Unifique pontos que tratam do mesmo assunto em um único ponto abrangente\n"
        "- Todos os itens de key_points devem ser frases completas com inicial maiúscula\n"
        "- O summary deve ser um parágrafo coeso de 3-5 frases, sem repetições\n"
        "- Use português brasileiro correto — sem neologismos, sem palavras inventadas\n\n"
        "Responda APENAS com JSON válido, sem texto extra antes ou depois.\n\n"
        "Estrutura JSON obrigatória:\n"
        '{{\n'
        '  "summary": "Um parágrafo conciso resumindo o conteúdo principal.",\n'
        '  "key_points": ["ponto 1", "ponto 2", "..."],\n'
        '  "action_items": ["ação 1", "ação 2", "..."],\n'
        '  "key_concepts": ["Termo: definição curta de uma linha", "..."],\n'
        '  "tools_mentioned": ["ferramenta ou tecnologia 1", "..."],\n'
        '  "metrics": ["número ou estatística com contexto", "..."],\n'
        '  "quotes": ["frase notável do speaker com contexto mínimo", "..."],\n'
        '  "assumptions": ["premissa implícita identificada", "..."],\n'
        '  "vocabulary": ["Jargão: definição inferida do contexto", "..."],\n'
        '  "sentiment_arc": "evolução do tom ao longo do conteúdo"\n'
        '}}\n\n'
        "Regras por campo:\n"
        "- summary: 3-5 frases, capture a essência sem repetir pontos do key_points\n"
        "- key_points: 5-10 pontos distintos; cada ponto deve ser uma frase completa com sujeito e verbo, "
        "com no mínimo 12 palavras; explique o 'como' ou 'por que' sempre que possível; "
        "IGNORE CTAs (curtir, inscrever, comentar), patrocinadores e autopromoção\n"
        "- action_items: passos práticos mencionados (lista vazia se nenhum); "
        "IGNORE pedidos de inscrição, curtida ou comentário\n"
        "- key_concepts: conceitos abstratos/técnicos centrais; formato 'Termo: definição'; elimine duplicatas (lista vazia se nenhum)\n"
        "- tools_mentioned: consolide sem repetição (lista vazia se nenhuma)\n"
        "- metrics: elimine duplicatas, mantenha contexto (lista vazia se nenhuma)\n"
        "- quotes: consolide as mais representativas, até 5; elimine duplicatas (lista vazia se nenhuma)\n"
        "- assumptions: consolide premissas únicas, até 5 (lista vazia se nenhuma)\n"
        "- vocabulary: consolide jargões únicos; formato 'Termo: definição' (lista vazia se nenhum)\n"
        "- sentiment_arc: sintetize o arco completo em UMA frase a partir de todos os arcos parciais"
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

    logging.debug("[d] Splitting text: chunk_size=%d | overlap=%d",
                  CHUNK_SIZE, CHUNK_OVERLAP)
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


def _parse_header(raw_text: str) -> dict:
    """Parse the key: value metadata fields from the transcription file header.

    Args:
        raw_text: Full file content including metadata header.

    Returns:
        Dictionary with metadata fields (title, channel, duration, url, etc.).
        Empty dict if no header separator is found.
    """
    separator = "-" * 64
    if separator not in raw_text:
        return {}

    header_text = raw_text.split(separator, 1)[0]
    meta = {}
    for line in header_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key and value:
                meta[key] = value
    return meta


def _format_report(
    analysis: dict,
    source_path: Path,
    video_meta: dict | None = None,
    transcription: str | None = None,
) -> str:
    """Format the analysis dictionary as a Markdown report.

    Args:
        analysis: Dictionary with summary, key_points, action_items, etc.
        source_path: Path to the original transcription file.
        video_meta: Parsed metadata from the transcription header (optional).
        transcription: Formatted transcription body to append at the end (optional).

    Returns:
        Formatted Markdown string.
    """
    video_meta = video_meta or {}
    title = video_meta.get("title") or f"Análise: {source_path.stem}"
    channel = video_meta.get("channel", "")
    duration = video_meta.get("duration", "")
    url = video_meta.get("url", "")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [f"# {title}", ""]

    meta_parts = []
    if channel:
        meta_parts.append(f"**Canal:** {channel}")
    if duration:
        meta_parts.append(f"**Duração:** {duration}")
    if meta_parts:
        lines.append(" | ".join(meta_parts))
    if url:
        lines.append(f"[Assistir no YouTube]({url})")

    lines.extend([
        "",
        f"> Gerado em: {generated_at} | Fonte: `{source_path.name}`",
        "",
        "---",
        "",
        "## Resumo",
        "",
        analysis.get("summary", "N/A"),
        "",
        "## Pontos-chave",
        "",
    ])
    for point in analysis.get("key_points", []):
        lines.append(f"- {point}")

    lines.extend(["", "## Ações sugeridas", ""])
    actions=analysis.get("action_items", [])
    if actions:
        for action in actions:
            lines.append(f"- {action}")
    else:
        lines.append("Nenhuma ação identificada.")

    concepts=analysis.get("key_concepts", [])
    if concepts:
        lines.extend(["", "## Conceitos-chave", ""])
        for concept in concepts:
            lines.append(f"- {concept}")

    tools=analysis.get("tools_mentioned", [])
    if tools:
        lines.extend(["", "## Ferramentas mencionadas", ""])
        for tool in tools:
            lines.append(f"- {tool}")

    metrics = analysis.get("metrics", [])
    if metrics:
        lines.extend(["", "## Métricas e números", ""])
        for metric in metrics:
            lines.append(f"- {metric}")

    quotes = analysis.get("quotes", [])
    if quotes:
        lines.extend(["", "## Citações notáveis", ""])
        for quote in quotes:
            lines.append(f"> {quote}")
            lines.append("")

    assumptions = analysis.get("assumptions", [])
    if assumptions:
        lines.extend(["", "## Premissas implícitas", ""])
        for assumption in assumptions:
            lines.append(f"- {assumption}")

    vocabulary = analysis.get("vocabulary", [])
    if vocabulary:
        lines.extend(["", "## Vocabulário do nicho", ""])
        for term in vocabulary:
            lines.append(f"- {term}")

    sentiment_arc = analysis.get("sentiment_arc", "")
    if sentiment_arc:
        lines.extend(["", "## Arco de sentimento", "", sentiment_arc])

    if transcription:
        lines.extend(["", "---", "", "## Transcrição", ""])
        lines.append(transcription)

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
    summary=analysis.get("summary", "")
    if not summary:
        return analysis

    logging.info("[~] Detecting analysis language...")
    detect_chain=DETECT_LANGUAGE_PROMPT | llm
    lang_response=detect_chain.invoke({"text": summary[:500]})
    raw_lang=lang_response.content.strip()
    detected=raw_lang.lower()[:2]
    logging.debug("[d] Language raw response: %r → parsed: %r",
                  raw_lang, detected)
    logging.info("[i] Detected language: %s", detected)

    if detected == "pt":
        return analysis

    logging.info("[~] Translating analysis to PT-BR...")
    json_text=json.dumps(analysis, ensure_ascii=False, indent=2)
    translate_chain=TRANSLATE_PROMPT | llm
    translated_response=translate_chain.invoke({"json_text": json_text})
    translated=_parse_json_response(translated_response.content)

    logging.info("[✓] Translation complete.")
    return translated


def analyze(
    input_path: Path,
    model_name: str = DEFAULT_MODEL,
    transcription: str | None = None,
) -> Path:
    """Analyze a transcription file and generate a structured Markdown report.

    Reads the transcription, splits into chunks if needed, sends to Ollama
    for analysis, merges partial results, and writes the final report.

    Args:
        input_path: Path to the transcription .txt file.
        model_name: Ollama model to use for analysis.
        transcription: Formatted transcription body to append to the report (optional).
            When provided (e.g. after --format), the full text is included at the
            bottom of the .md under a "Transcrição" section.

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

    raw_text=input_path.read_text(encoding="utf-8")
    video_meta=_parse_header(raw_text)
    body=_extract_transcription_body(raw_text)
    logging.debug("[d] File: %d chars total | body after header strip: %d chars",
                  len(raw_text), len(body))

    if not body:
        logging.error("Transcription body is empty: %s", input_path)
        sys.exit(1)

    chunks=_split_text(body)
    logging.info("[i] Text split into %d chunk(s) (%d chars total)",
                 len(chunks), len(body))
    for i, chunk in enumerate(chunks, 1):
        logging.debug("[d] Chunk %d/%d: %d chars", i, len(chunks), len(chunk))

    llm = ChatOllama(model=model_name, temperature=0.4)      # análise e merge
    llm_util = ChatOllama(model=model_name, temperature=0)   # detecção de idioma e tradução

    start=time()

    if len(chunks) == 1:
        logging.info("[~] Analyzing single chunk...")
        t_chunk=time()
        chain=ANALYSIS_PROMPT | llm
        response=chain.invoke({"text": chunks[0]})
        analysis=_parse_json_response(response.content)
        logging.debug("[d] Single chunk done in %.1fs | response: %d chars | keys: %s",
                      time() - t_chunk, len(response.content), list(analysis.keys()))
    else:
        partial_analyses=[]
        for i, chunk in enumerate(chunks, 1):
            logging.info("[~] Analyzing chunk %d/%d...", i, len(chunks))
            t_chunk=time()
            chain=ANALYSIS_PROMPT | llm
            response=chain.invoke({"text": chunk})
            partial=_parse_json_response(response.content)
            logging.debug("[d] Chunk %d done in %.1fs | response: %d chars | keys: %s",
                          i, time() - t_chunk, len(response.content), list(partial.keys()))
            partial_analyses.append(partial)

        logging.info("[~] Merging %d partial analyses...",
                     len(partial_analyses))
        t_merge=time()
        merge_input=json.dumps(partial_analyses, ensure_ascii=False, indent=2)
        merge_chain=MERGE_PROMPT | llm
        merge_response=merge_chain.invoke({"analyses": merge_input})
        analysis=_parse_json_response(merge_response.content)
        logging.debug("[d] Merge done in %.1fs", time() - t_merge)

    analysis = _ensure_portuguese(analysis, llm_util)

    elapsed=time() - start

    TRANSCRIPTIONS_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    report = _format_report(analysis, input_path, video_meta, transcription)
    output_path=TRANSCRIPTIONS_ANALYSIS_DIR / f"{input_path.stem}.md"
    output_path.write_text(report, encoding="utf-8")
    md_size_kb=output_path.stat().st_size / 1024
    logging.debug("[d] Report size: %.1f KB", md_size_kb)

    logging.info("[✓] Analysis saved to: %s (%.0fs)", output_path, elapsed)
    return output_path


def main() -> None:
    """Entry point for standalone analyzer CLI."""
    parser=argparse.ArgumentParser(
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
    args=parser.parse_args()

    setup_logging(args.verbose)
    analyze(Path(args.input_file), model_name=args.model)
