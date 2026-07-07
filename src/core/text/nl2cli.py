"""Translate a Portuguese question into a ``uv run main.py ...`` CLI command.

Mirrors ``core/data/nl2sql.py``'s shape: the model is asked for a strict JSON
object ``{"command": ..., "explanation": ...}``; parsing is defensive (fenced
block / first-object fallback) because small local models occasionally wrap
the JSON in prose. Unlike ``nl2sql``, an invalid command retries once with the
argparse error appended, since ``validate_fn`` (unlike ``ensure_select``) can
point at exactly what was wrong — a cheap way to fix small mistakes (a wrong
flag name, a missing required flag) without giving up immediately.

``reference`` (the compact CLI reference, built by
``src.cli.reference.build_reference``) and ``validate_fn`` (``src.cli.
reference.validate_command``) are always injected — this module never imports
``cli/`` itself, so it stays unit-testable without argparse/CLI machinery.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from langchain_core.prompts import ChatPromptTemplate

from src.llm_factory import make_llm
from src.llm_utils import extract_llm_text

DEFAULT_MODEL = "qwen7b-custom"

# Few-shot pairs cover the spots small local models get wrong: kebab-case
# operation names, the audio-vs-video-extraction ambiguity, `data query`'s
# multi-input shape (+ `--sql`), `ai`'s literal-keyword flows vs. a free
# question, `transcribe`'s AI flags, and an out-of-scope refusal so the model
# does not hallucinate a command for a question this CLI cannot answer.
_NL2CLI_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Você é um tradutor de português para comandos da CLI do mill.tools "
            "(`uv run main.py ...`). Você recebe uma REFERÊNCIA completa dos "
            "subcomandos/flags disponíveis e uma pergunta em português. Gere o "
            "comando exato que resolve o pedido.\n\n"
            "Regras rígidas:\n"
            "- Responda SOMENTE com um objeto JSON válido, sem texto extra, no formato:\n"
            '  {{"command": "uv run main.py ...", "explanation": "<o que o comando faz, '
            'em português>"}}\n'
            "- Use somente os subcomandos/flags/valores de choices que aparecem na "
            "REFERÊNCIA — nunca invente um flag ou operação.\n"
            "- Preserve exatamente o kebab-case das operações (ex.: extract-audio, "
            "contact-sheet, images-to-pdf, dedup-images) — nunca troque por snake_case.\n"
            "- Se o pedido não for uma tarefa desta CLI (fora do escopo do app), responda\n"
            '  {{"command": "", "explanation": "<recusa educada em português explicando '
            "que o app processa áudio/vídeo/imagens/documentos/dados/transcrição/"
            'biblioteca/receitas/índice RAG>"}}\n'
            "  em vez de inventar um comando.\n\n"
            "Exemplos:\n"
            "PERGUNTA: extrai o áudio do vídeo palestra.mp4 em mp3\n"
            'COMANDO: {{"command": "uv run main.py video extract-audio palestra.mp4 '
            '--fmt mp3", "explanation": "Extrai a trilha de áudio do vídeo em mp3."}}\n\n'
            "PERGUNTA: converte esse podcast.wav para mp3 a 320kbps\n"
            'COMANDO: {{"command": "uv run main.py audio podcast.wav --fmt mp3 '
            '--quality 320", "explanation": "Converte o áudio para mp3 a 320kbps."}}\n\n'
            "PERGUNTA: gera um contact sheet com foto1.jpg e foto2.jpg\n"
            'COMANDO: {{"command": "uv run main.py image contact-sheet foto1.jpg '
            'foto2.jpg", "explanation": "Gera uma folha de contatos com as duas '
            'imagens."}}\n\n'
            "PERGUNTA: junta pagina1.png e pagina2.png num pdf só\n"
            'COMANDO: {{"command": "uv run main.py document images-to-pdf pagina1.png '
            'pagina2.png", "explanation": "Combina as duas imagens num único PDF."}}\n\n'
            "PERGUNTA: acha imagens quase duplicadas no meu acervo\n"
            'COMANDO: {{"command": "uv run main.py library dedup-images", '
            '"explanation": "Procura imagens quase-duplicadas por hash perceptual."}}\n\n'
            "PERGUNTA: quantas linhas tem vendas.csv? responde com SQL: "
            "SELECT COUNT(*) FROM vendas\n"
            'COMANDO: {{"command": "uv run main.py data query vendas.csv \\"SELECT '
            'COUNT(*) FROM vendas\\" --sql", "explanation": "Roda a consulta SQL '
            'diretamente, sem tradução da IA."}}\n\n'
            "PERGUNTA: reindexa o meu acervo\n"
            'COMANDO: {{"command": "uv run main.py ai index", "explanation": '
            '"Reconstrói o índice RAG a partir da Biblioteca."}}\n\n'
            "PERGUNTA: faça um resumo dos principais achados do meu acervo\n"
            'COMANDO: {{"command": "uv run main.py ai \\"faça um resumo dos principais '
            'achados do meu acervo\\"", "explanation": "Pergunta ao RAG local sobre o '
            'acervo (não é um dos comandos de manutenção index/stats/...)."}}\n\n'
            "PERGUNTA: transcreve aula.mp4 formatando e analisando com o perfil lecture\n"
            'COMANDO: {{"command": "uv run main.py transcribe aula.mp4 --format '
            '--analyze --profile lecture", "explanation": "Transcreve o vídeo, '
            'formata parágrafos e analisa com o perfil lecture."}}\n\n'
            "PERGUNTA: qual a previsão do tempo pra amanhã?\n"
            'COMANDO: {{"command": "", "explanation": "Isso não é uma tarefa da CLI do '
            "mill.tools — não sei prever o tempo. Posso ajudar com áudio, vídeo, "
            "imagens, documentos, dados, transcrição, biblioteca, receitas ou o índice "
            'RAG."}}',
        ),
        ("human", "REFERÊNCIA:\n{reference}\n\nPERGUNTA: {question}"),
    ]
)

_FENCED = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_FIRST_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class NL2CLIError(RuntimeError):
    """Raised when the model cannot produce a valid command after one retry."""


def _extract_payload(text: str) -> tuple[str, str]:
    """Pull ``(command, explanation)`` out of a model response.

    Tries strict JSON first, then a fenced block, then the first ``{...}``
    found. An empty ``command`` is a valid, deliberate refusal (out-of-scope
    question) — the caller must not treat it as a parse failure.
    """
    candidates: list[str] = [text.strip()]
    fenced = _FENCED.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    obj = _FIRST_OBJECT.search(text)
    if obj:
        candidates.append(obj.group(0))

    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "command" in data:
            command = str(data["command"] or "").strip()
            explanation = str(data.get("explanation", "")).strip()
            return command, explanation

    raise NL2CLIError("A IA não retornou um comando reconhecível.")


def _generate(chain, reference: str, question: str) -> tuple[str, str]:
    resp = chain.invoke({"reference": reference, "question": question})
    content = extract_llm_text(resp.content) if hasattr(resp, "content") else str(resp)
    return _extract_payload(content)


def to_command(
    question: str,
    reference: str,
    make_llm_fn: Callable = make_llm,
    *,
    model: str = DEFAULT_MODEL,
    validate_fn: Callable[[str], str | None],
) -> tuple[str, str]:
    """Translate *question* into ``(command, explanation)`` using *reference*.

    An empty ``command`` means the model deliberately refused an
    out-of-scope question — ``explanation`` carries the refusal message, and
    there is nothing to validate.

    Raises:
        NL2CLIError: if the model does not produce a command that passes
            ``validate_fn`` after one retry (the retry re-prompts with the
            validator's error message appended).
    """
    chain = _NL2CLI_PROMPT | make_llm_fn(model, temperature=0.0)

    try:
        command, explanation = _generate(chain, reference, question)
        if not command:
            return command, explanation
        error = validate_fn(command)
        if error is None:
            return command, explanation
    except NL2CLIError:
        command, error = "", "a resposta não pôde ser interpretada como JSON."

    retry_question = (
        f"{question}\n\n"
        f"Sua tentativa anterior foi: {command!r}\n"
        f"Esse comando gerado falhou com: {error}\n"
        "Gere um novo comando JSON corrigindo esse erro, mantendo o pedido original."
    )
    try:
        command, explanation = _generate(chain, reference, retry_question)
    except NL2CLIError as exc:
        raise NL2CLIError(
            f"A IA não conseguiu gerar um comando válido para esse pedido: {exc}"
        ) from exc

    if not command:
        return command, explanation
    error = validate_fn(command)
    if error is not None:
        raise NL2CLIError(
            f"A IA não conseguiu gerar um comando válido para esse pedido "
            f"(último erro: {error})."
        )
    return command, explanation
