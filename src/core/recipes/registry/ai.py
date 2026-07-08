"""AI (RAG) step adapter for the recipe registry.

``ai.answer`` belongs to the IA world (PR7 local RAG), kept separate from the
transcription/LLM pipeline steps.
"""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import KIND_MARKDOWN, KIND_TEXT, StepContext, StepSpec


def _ai_answer(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """text/markdown → cited RAG answer .md (PR7). Wraps the local RAG core.

    chat.answer() returns an AnswerResult (text + sources), not a Path, so the
    adapter serializes the answer (plus a Fontes list) to a .md. The just-produced
    document is reindexed first and the retrieval is scoped to it, so a chain like
    ``transcribe → ai.answer`` actually grounds the answer on the new file. Needs
    the local embedder available (PR7 gate); otherwise the step fails and
    stop_on_error reports it.
    """
    from src.core.library.scanner import scan_library
    from src.core.rag import embedder
    from src.core.rag.chat import DEFAULT_MODEL
    from src.core.rag.chat import answer as _answer
    from src.core.rag.indexer import CURRENT_EMBED_SCHEME, build_index, index_dir
    from src.core.rag.retriever import retrieve
    from src.core.rag.store import VectorStore
    from src.utils import TRANSCRIPTIONS_ANALYSIS_DIR

    embed_model = params.get("embed_model", "nomic-embed-custom")
    if not embedder.is_available(embed_model):
        raise RuntimeError(f"Embedder indisponível. {embedder.SETUP_HINT}")

    query = params.get("query") or "Resuma o conteúdo e liste os pontos principais."
    src = Path(inputs[0])

    # Reindex so the freshly produced document is embedded, then scope to it.
    store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
    build_index(
        scan_library(),
        store,
        lambda texts: embedder.embed_texts(texts, model=embed_model),
    )
    store.persist(
        index_dir(), embed_model=embed_model, embed_scheme=CURRENT_EMBED_SCHEME
    )

    hits = retrieve(
        query,
        store,
        lambda q: embedder.embed_query(q, model=embed_model),
        k=params.get("k", 6),
        scope=str(src),
    )
    result = _answer(query, hits, model_name=params.get("model", DEFAULT_MODEL))

    TRANSCRIPTIONS_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out = TRANSCRIPTIONS_ANALYSIS_DIR / f"{src.stem}_ia.md"
    body = result.text
    if result.sources:
        body += "\n\n## Fontes\n" + "\n".join(f"- {s.name}" for s in result.sources)
    out.write_text(body + "\n", encoding="utf-8")
    return [out]


AI_STEPS: dict[str, StepSpec] = {
    "ai.answer": StepSpec(
        _ai_answer,
        frozenset({KIND_TEXT, KIND_MARKDOWN}),
        KIND_MARKDOWN,
        "Perguntar à IA",
    ),
}
