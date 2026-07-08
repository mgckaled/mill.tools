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

**Optional user glossary.** mill.tools has no single fixed domain — the RAG
corpus is whatever the user happens to transcribe/analyze, so there is no
universal list of proper nouns/jargon to hardcode here. Instead, an optional
``~/.mill-tools/entity_glossary.json`` (a list of spaCy ``EntityRuler``
patterns, e.g. ``[{"label": "MISC", "pattern": "Muad'Dib"}]``) is read once
when the pipeline for a language is first loaded and added as an
``entity_ruler`` *before* the statistical ``ner`` component, so it can catch
domain terms the CNN model was never trained on. Absent file → no ruler, zero
behavior change. Because the pipeline is a cached singleton per language
(below), the glossary is only re-read on the first load of that language in
the process — not reconfigurable per call.

**Long documents are chunked.** spaCy's own default guard (``nlp.max_length``)
rejects text over 1,000,000 characters — a full novel or a long transcription
can exceed that, and its own error message notes the underlying reason: NER
needs roughly 1GB of temporary memory per 100,000 characters, so raising the
limit to fit one huge document in a single call would risk exhausting RAM
rather than just failing loudly. Instead, ``entities()`` splits the text with
the same ``RecursiveCharacterTextSplitter`` the RAG indexer already uses
(``llm_utils.split_text``) into windows safely under that ceiling, runs
``nlp.pipe()`` over them, and merges the (already deduplicated) results — an
entity split exactly across a chunk boundary can be missed, an acceptable
trade-off for not risking a memory blowup on the machine's 16GB.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.llm_utils import split_text

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

# Human-readable language label for availability()'s per-language hint.
_LANG_LABELS = {"pt": "português", "en": "inglês"}

# Only these components are needed for NER; everything else is disabled per call.
# entity_ruler is included so the optional glossary (if loaded) actually runs.
# No "transformer" here: that component only exists in the forbidden _trf
# pipelines (see module docstring) — the *_sm models never have one to enable.
_NER_PIPES = ("tok2vec", "entity_ruler", "ner")

# Lazy singleton cache: one loaded pipeline per language, reused across calls.
_NLP_CACHE: dict[str, Language] = {}

_GLOSSARY_FILE = "entity_glossary.json"

# Chunk well under spaCy's own 1,000,000-char nlp.max_length guard (its error
# message estimates ~1GB of temporary memory per 100,000 chars) instead of
# raising the limit to fit one huge document in a single call.
_MAX_CHARS = 100_000
_CHUNK_OVERLAP = 200


def _glossary_path() -> Path:
    """Return the optional user-maintained entity glossary path."""
    return Path.home() / ".mill-tools" / _GLOSSARY_FILE


def _load_glossary_patterns() -> list[dict]:
    """Read the optional domain glossary (spaCy ``EntityRuler`` pattern format).

    Absent or malformed file yields no patterns — the ruler is only added to
    the pipeline when there is something to add, so a user who never creates
    this file sees no behavior change.
    """
    try:
        data = json.loads(_glossary_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _model_for(lang: str) -> str:
    """Return the spaCy model name for *lang* (falls back to the PT model)."""
    if lang not in _MODELS:
        logging.debug("[d] Unrecognized NER language %r, falling back to pt", lang)
    return _MODELS.get(lang, _MODELS[_DEFAULT_LANG])


def availability(lang: str = _DEFAULT_LANG) -> str | None:
    """Return ``None`` when ready, or a setup hint naming what's missing.

    ``is_available()`` collapses two different failure modes into one
    boolean: "the ``[nlp]`` extra itself is missing" (spaCy not importable)
    and "spaCy is installed but this one language's model isn't". A caller
    that only sees the boolean can't tell them apart and always shows the
    same generic hint — the actual bug behind a screenshot report: an
    English PDF, with every extra already installed, still got told to
    "install the NLP extra and the spaCy model" when only ``en_core_web_sm``
    was missing. Kept as a sibling function rather than changing
    ``is_available()``'s return type, so no existing boolean call site breaks.
    """
    try:
        import spacy
    except ImportError:
        return SETUP_HINT
    model = _model_for(lang)
    try:
        installed = bool(spacy.util.is_package(model))
    except Exception:  # pragma: no cover — spacy.util quirk, treat as unavailable
        installed = False
    if installed:
        return None
    label = _LANG_LABELS.get(lang, lang)
    return f"Modelo de {label} ausente: uv run python -m spacy download {model}"


def is_available(lang: str = _DEFAULT_LANG) -> bool:
    """True if spaCy AND the language model are importable/installed.

    Mirrors ``ocr.is_available()``: the package alone is not enough — the model
    download must be present too. Used to gate the entities field/flag. See
    :func:`availability` for a caller that needs to know *why* it's False.
    """
    return availability(lang) is None


def _load(lang: str) -> Language:
    """Load (and cache) the spaCy pipeline for *lang*, NER components only."""
    if lang not in _NLP_CACHE:
        import spacy

        nlp = spacy.load(_model_for(lang))
        patterns = _load_glossary_patterns()
        if patterns:
            ruler = nlp.add_pipe("entity_ruler", before="ner")
            ruler.add_patterns(patterns)
        _NLP_CACHE[lang] = nlp
        logging.debug(
            "[d] Loaded spaCy model %s (glossary patterns: %d)",
            _model_for(lang),
            len(patterns),
        )
    return _NLP_CACHE[lang]


def entities(text: str, *, lang: str = _DEFAULT_LANG) -> list[tuple[str, str]]:
    """Return the named entities of *text* as ``(entity_text, label)`` pairs.

    Labels follow the model's scheme (PER/ORG/LOC/MISC, plus DATE/etc. when the
    model emits them). Duplicate ``(text, label)`` pairs are collapsed, keeping
    first-seen order (across the whole document, not per chunk). Only the
    ``tok2vec`` + ``ner`` components run. Text longer than ``_MAX_CHARS`` is
    split into safely-sized windows first (see the module docstring) — texts
    that already fit go through unchanged, in a single ``nlp.pipe()`` call.

    Raises:
        RuntimeError: if spaCy or the language model is not installed.
    """
    # Skip the is_available() metadata scan once the pipeline is already
    # resident (spacy.util.is_package() on every call is dead weight when
    # nothing changed since the last successful load).
    if lang not in _NLP_CACHE and not is_available(lang):
        raise RuntimeError(SETUP_HINT)
    if not text.strip():
        return []

    nlp = _load(lang)
    enable = [p for p in _NER_PIPES if p in nlp.pipe_names]
    chunks = split_text(text, chunk_size=_MAX_CHARS, chunk_overlap=_CHUNK_OVERLAP)

    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    with nlp.select_pipes(enable=enable):
        for doc in nlp.pipe(chunks):
            for ent in doc.ents:
                pair = (ent.text.strip(), ent.label_)
                if pair[0] and pair not in seen:
                    seen.add(pair)
                    out.append(pair)
    return out
