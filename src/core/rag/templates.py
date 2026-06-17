"""Prompt library + structured templates for the AI module.

A template's ``instruction`` is the PT-BR text dropped into the question field and
answered by the normal RAG flow (retrieve scoped to the document/corpus → answer).
Built-in defaults ship with the app; user-defined templates persist to
``~/.mill-tools/prompts.json`` and are merged on top of (never overwrite) the
defaults.

PT-BR is intentional here: instructions and labels are user-facing prompts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

CATEGORY_PROMPT = "prompt"  # quick one-off instructions
CATEGORY_TEMPLATE = "template"  # structured outputs (minutes, e-mail, summary)


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """One reusable prompt: a chip label plus the instruction it inserts."""

    id: str
    label: str  # PT-BR, shown on the chip
    instruction: str  # the prompt text inserted into the question field
    category: str  # CATEGORY_PROMPT | CATEGORY_TEMPLATE


# Built-in library. Quick prompts first, then structured templates.
_DEFAULTS: tuple[PromptTemplate, ...] = (
    PromptTemplate(
        "summarize",
        "Resumir",
        "Resuma o conteúdo de forma objetiva em até 5 frases, destacando as "
        "ideias principais.",
        CATEGORY_PROMPT,
    ),
    PromptTemplate(
        "key_points",
        "Pontos-chave",
        "Liste os principais pontos do conteúdo em tópicos curtos e completos.",
        CATEGORY_PROMPT,
    ),
    PromptTemplate(
        "rewrite_formal",
        "Reescrever formal",
        "Reescreva o conteúdo em tom formal e profissional, preservando o significado.",
        CATEGORY_PROMPT,
    ),
    PromptTemplate(
        "translate_en",
        "Traduzir (EN)",
        "Traduza o conteúdo para o inglês, mantendo o sentido e a terminologia.",
        CATEGORY_PROMPT,
    ),
    PromptTemplate(
        "meeting_minutes",
        "Ata de reunião",
        "Gere uma ata de reunião estruturada a partir do conteúdo, com: "
        "participantes (se identificáveis), pauta, principais decisões e itens "
        "de ação com responsáveis.",
        CATEGORY_TEMPLATE,
    ),
    PromptTemplate(
        "email",
        "E-mail",
        "Escreva um e-mail claro e conciso que comunique os pontos principais "
        "do conteúdo, com assunto, saudação, corpo e encerramento.",
        CATEGORY_TEMPLATE,
    ),
    PromptTemplate(
        "exec_summary",
        "Resumo executivo",
        "Produza um resumo executivo do conteúdo em um parágrafo, seguido de 3 "
        "a 5 conclusões ou recomendações em tópicos.",
        CATEGORY_TEMPLATE,
    ),
)


def default_templates() -> list[PromptTemplate]:
    """Return a fresh list of the built-in templates."""
    return list(_DEFAULTS)


def prompts_file() -> Path:
    """Path to the user's prompt library (~/.mill-tools/prompts.json)."""
    return Path.home() / ".mill-tools" / "prompts.json"


def _read_user_raw() -> list[dict]:
    pf = prompts_file()
    if not pf.exists():
        return []
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError) as exc:
        logging.debug("[d] prompts.json read failed: %s", exc)
        return []


def load_templates() -> list[PromptTemplate]:
    """Built-in defaults plus any user-defined templates from prompts.json.

    User entries with an id that collides with a default are ignored (defaults
    win) so a broken user file can never hide a built-in template.
    """
    templates = default_templates()
    existing = {t.id for t in templates}
    for item in _read_user_raw():
        try:
            t = PromptTemplate(**item)
        except TypeError as exc:
            logging.debug("[d] skipping malformed template %r: %s", item, exc)
            continue
        if t.id not in existing:
            templates.append(t)
            existing.add(t.id)
    return templates


def save_user_template(template: PromptTemplate) -> None:
    """Persist (or replace by id) a user template in prompts.json.

    Defaults are never written — only user additions live in the file.
    """
    pf = prompts_file()
    pf.parent.mkdir(parents=True, exist_ok=True)
    entries = [e for e in _read_user_raw() if e.get("id") != template.id]
    entries.append(asdict(template))
    pf.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def get_template(
    template_id: str, templates: list[PromptTemplate] | None = None
) -> PromptTemplate | None:
    """Return the template with ``template_id`` or None if not found."""
    for t in templates if templates is not None else load_templates():
        if t.id == template_id:
            return t
    return None
