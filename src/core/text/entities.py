"""Named-entity recognition via spaCy's CNN models — torch-free, CPU-only.

``pt_core_news_sm`` is a CNN (thinc) pipeline, so NER runs on CPU without pulling
torch — only the ``_trf`` (transformer) variants would, and they are deliberately
not used. The model is loaded **once** (lazy singleton) and reused across calls;
only the ``tok2vec`` + ``ner`` components run (the parser/lemmatizer/etc. are
disabled per call) so extraction stays fast.

Gate: the spaCy package is a normal ``[nlp]`` dependency, but the *model* is a
separate download (``python -m spacy download pt_core_news_sm``), exactly like
the Tesseract binary for OCR — so ``is_available`` checks both, and the GUI/CLI
disables the entities field when the model is absent instead of crashing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spacy.language import Language

SETUP_HINT = (
    "Instale o extra de NLP e o modelo: uv sync --extra nlp && "
    "uv run python -m spacy download pt_core_news_sm"
)

# Language → spaCy CNN model. Both are torch-free; only the *_sm models are
# assumed installed (the _trf variants are forbidden — they pull torch).
_MODELS = {"pt": "pt_core_news_sm", "en": "en_core_web_sm"}
_DEFAULT_LANG = "pt"

# Only these components are needed for NER; everything else is disabled per call.
_NER_PIPES = ("tok2vec", "transformer", "ner")

# Lazy singleton cache: one loaded pipeline per language, reused across calls.
_NLP_CACHE: dict[str, Language] = {}


def _model_for(lang: str) -> str:
    """Return the spaCy model name for *lang* (falls back to the PT model)."""
    return _MODELS.get(lang, _MODELS[_DEFAULT_LANG])


def is_available(lang: str = _DEFAULT_LANG) -> bool:
    """True if spaCy AND the language model are importable/installed.

    Mirrors ``ocr.is_available()``: the package alone is not enough — the model
    download must be present too. Used to gate the entities field/flag.
    """
    try:
        import spacy
    except ImportError:
        return False
    try:
        return bool(spacy.util.is_package(_model_for(lang)))
    except Exception:  # pragma: no cover — spacy.util quirk, treat as unavailable
        return False


def _load(lang: str) -> Language:
    """Load (and cache) the spaCy pipeline for *lang*, NER components only."""
    if lang not in _NLP_CACHE:
        import spacy

        _NLP_CACHE[lang] = spacy.load(_model_for(lang))
        logging.debug("[d] Loaded spaCy model %s", _model_for(lang))
    return _NLP_CACHE[lang]


def entities(text: str, *, lang: str = _DEFAULT_LANG) -> list[tuple[str, str]]:
    """Return the named entities of *text* as ``(entity_text, label)`` pairs.

    Labels follow the model's scheme (PER/ORG/LOC/MISC, plus DATE/etc. when the
    model emits them). Duplicate ``(text, label)`` pairs are collapsed, keeping
    first-seen order. Only the ``tok2vec`` + ``ner`` components run.

    Raises:
        RuntimeError: if spaCy or the language model is not installed.
    """
    if not is_available(lang):
        raise RuntimeError(SETUP_HINT)
    if not text.strip():
        return []

    nlp = _load(lang)
    enable = [p for p in _NER_PIPES if p in nlp.pipe_names]
    with nlp.select_pipes(enable=enable):
        doc = nlp(text)

    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for ent in doc.ents:
        pair = (ent.text.strip(), ent.label_)
        if pair[0] and pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out
