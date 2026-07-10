"""CLI subcommand `ai` — local RAG over the Library corpus.

Flows behind one positional:
    uv run main.py ai index                       # (re)build the vector index
    uv run main.py ai stats                        # summarize the persisted index
    uv run main.py ai dups                          # near-duplicate documents (ML)
    uv run main.py ai topics                        # cluster the corpus into topics
    uv run main.py ai map [--method pca|tsne|umap]  # render the semantic map PNG
    uv run main.py ai related <path> [--k N]        # documents similar to one
    uv run main.py ai classify <path>               # suggest the analysis profile
    uv run main.py ai keywords <path> [--top N]     # YAKE keyphrases
    uv run main.py ai summary <path> [--sentences N] # extractive TextRank summary
    uv run main.py ai entities <path>               # spaCy named entities
    uv run main.py ai "what did I say about X?"    # ask the whole corpus
    uv run main.py ai "summarize" --scope path.txt # ask a single document
    uv run main.py ai "..." --model gemini-2.5-flash --k 8
    uv run main.py ai "..." --model glm-4.7-flash --k 8
    uv run main.py ai --cmd "corta o silêncio do podcast.mp3 e acelera 1.25x"
    uv run main.py ai eval                          # run the golden-set eval
    uv run main.py ai eval list                     # show golden set + suggestions
    uv run main.py ai eval add --question "..." --expect aula.txt  # add a golden question
    uv run main.py ai eval promote                  # promote 👍 feedback to golden questions

Reuses the same core (scan_library / build_index / retrieve / answer) as the GUI.
Embeddings are always local (Ollama); only the answer step may use a cloud
provider opt-in (Gemini or GLM).
``dups``/``topics``/``map``/``related`` are read-only over the persisted index
(the ML layer, Plans 3/4A): no embedder/network needed. ``topics``/``map`` need
the ``[ml]`` extra; ``related`` is numpy-pure like ``dups``.

``--cmd`` (PLANO_NL2CLI_HUB_IA.md, Fase 4) bypasses the RAG/retriever entirely:
``query`` becomes a natural-language request, translated to the equivalent
``uv run main.py ...`` command (never executed — printed for the user to run).
Mirrors the AI hub's "Comandos CLI" GUI mode; same core (``core/text/nl2cli``)
and reference (``cli/reference``).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable

import numpy as np

# Sentinel positionals that trigger maintenance flows instead of a question.
_INDEX_CMD = "index"
_STATS_CMD = "stats"
_DUPS_CMD = "dups"
_TOPICS_CMD = "topics"
_MAP_CMD = "map"
_RELATED_CMD = "related"
# Plan 4B textual/classification flows — read-only over one document path.
_CLASSIFY_CMD = "classify"
_KEYWORDS_CMD = "keywords"
_SUMMARY_CMD = "summary"
_ENTITIES_CMD = "entities"
# Retrieval-only eval harness (PLANO_RAG_EVAL): sub-action carried by `target`.
_EVAL_CMD = "eval"


def add_ai_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the `ai` subcommand and its arguments."""
    p = subparsers.add_parser(
        "ai",
        help="Ask questions about your processed corpus (local RAG)",
    )
    p.add_argument(
        "query",
        help=(
            "Your question, or a flow keyword: index/stats/dups/topics/map/"
            "related/classify/keywords/summary/entities/eval"
        ),
    )
    p.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Document path — required by related/classify/keywords/summary/"
            "entities; or the eval sub-action (run/list/add/promote)"
        ),
    )
    p.add_argument(
        "--scope",
        default=None,
        help="Restrict to a source file path or a kind (transcription/document/image)",
    )
    p.add_argument(
        "--model",
        default=None,
        help=(
            "Answer model — Ollama tag (e.g. qwen7b-custom) or cloud "
            "(gemini-2.5-flash / glm-4.7-flash)"
        ),
    )
    p.add_argument(
        "--embed-model",
        default=None,
        dest="embed_model",
        help="Embedding model (default nomic-embed-custom)",
    )
    p.add_argument(
        "--k",
        type=int,
        default=6,
        metavar="N",
        help="Number of chunks to retrieve (default 6)",
    )
    p.add_argument(
        "--reindex",
        action="store_true",
        help="Rebuild the index before answering the question",
    )
    p.add_argument(
        "--batch",
        action="store_true",
        help="Apply the question as an instruction to every indexed document",
    )
    p.add_argument(
        "--kind",
        choices=["transcription", "document", "image"],
        default=None,
        help="With --batch, restrict to one kind of document",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.95,
        metavar="C",
        help="With dups, the minimum cosine similarity to group documents (0.95)",
    )
    p.add_argument(
        "--method",
        choices=["pca", "tsne", "umap"],
        default="pca",
        help=(
            "With map, the 2D projection (pca default; tsne separates clusters "
            "better, no extra beyond [ml]; umap needs the [ml-viz] extra)"
        ),
    )
    p.add_argument(
        "--out",
        default=None,
        help="With map, the output PNG path (default output/data/semantic_map.png)",
    )
    p.add_argument(
        "--sentences",
        type=int,
        default=5,
        metavar="N",
        help="With summary, how many sentences to keep (default 5)",
    )
    p.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="With keywords, how many keyphrases to return (default 10)",
    )
    p.add_argument(
        "--question",
        default=None,
        help='With eval add, the golden question text (e.g. "o que eu disse sobre X?")',
    )
    p.add_argument(
        "--expect",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "With eval add, an expected document path (repeatable); omit for an "
            "out-of-corpus question"
        ),
    )
    p.add_argument(
        "--cmd",
        action="store_true",
        help=(
            "Treat 'query' as a natural-language request and print the "
            "equivalent uv run main.py ... command instead of answering "
            "(bypasses the RAG/retriever entirely)"
        ),
    )
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    p.set_defaults(func=run_ai_cli)


def _resolve_scope(scope: str | None) -> str | None:
    """Normalize a --scope value: an existing file → absolute path; else a kind."""
    if not scope:
        return None
    p = Path(scope)
    if p.exists():
        return str(p.resolve())
    return scope  # treat as a kind filter (transcription/document/image)


def _embed_fns(
    embed_model: str,
) -> tuple[Callable[[list[str]], np.ndarray], Callable[[str], np.ndarray]]:
    """Bind the embedding model into the (embed_texts, embed_query) callables."""
    from src.core.rag import embedder

    return (
        lambda texts: embedder.embed_texts(texts, model=embed_model),
        lambda q: embedder.embed_query(q, model=embed_model),
    )


def _build(embed_model: str) -> None:
    """Scan the Library, embed new/changed text items and persist the index."""
    from tqdm import tqdm

    from src.core.library.scanner import scan_library
    from src.core.rag import embedder
    from src.core.rag.indexer import (
        CURRENT_EMBED_SCHEME,
        build_index,
        index_dir,
        indexable_items,
    )
    from src.core.rag.stats import index_stats, is_stale_scheme
    from src.core.rag.store import VectorStore

    index_directory = index_dir()
    items = scan_library()
    total = len(indexable_items(items))
    store = VectorStore.load(index_directory, dim=embedder.EMBED_DIM)
    before = len(store)
    # A scheme change alone never moves a source file's mtime — without this,
    # the incremental (path, mtime) check would skip every already-indexed
    # item forever, leaving old-space vectors under a sidecar that claims the
    # new scheme (see build_index's `force` docstring).
    force = is_stale_scheme(index_stats(index_directory), CURRENT_EMBED_SCHEME)

    embed_texts, _ = _embed_fns(embed_model)
    bar = tqdm(total=total, desc="Indexando", unit="doc", disable=total == 0)

    def _progress(current: int, _total: int) -> None:
        bar.n = current
        bar.refresh()

    def _card(item):
        from pathlib import Path

        from src.core.data.datacard import card_for_path

        return card_for_path(Path(item.path))

    build_index(
        items, store, embed_texts, progress_cb=_progress, card_fn=_card, force=force
    )
    bar.close()

    store.persist(
        index_directory, embed_model=embed_model, embed_scheme=CURRENT_EMBED_SCHEME
    )

    added = len(store) - before
    sign = "+" if added >= 0 else ""
    print(
        f"Índice atualizado: {total} documento(s) de texto, "
        f"{len(store)} chunk(s) ({sign}{added}). Salvo em {index_dir()}."
    )


def _answer_times() -> dict[str, list[float]]:
    """Read the per-model answer-time map from ~/.mill-tools/config.json.

    Read directly (not via gui.settings) so the CLI layer never imports the GUI.
    Returns an empty map when the file is missing or malformed.
    """
    import json

    config = Path.home() / ".mill-tools" / "config.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    times = data.get("ai_answer_times", {})
    return times if isinstance(times, dict) else {}


def _print_model_timings() -> None:
    """Print per-model answer timing (count/mean/median/p90), fastest first."""
    from src.core.rag.analytics import model_timings

    timings = model_timings(_answer_times())
    if not timings:
        return
    print("\nTempos de resposta por modelo (s)")
    print(f"  {'modelo':<22} {'n':>3} {'média':>7} {'mediana':>8} {'p90':>7}")
    print(f"  {'-' * 22} {'-' * 3} {'-' * 7} {'-' * 8} {'-' * 7}")
    for t in timings:
        print(
            f"  {t.model:<22} {t.count:>3} {t.mean:>7.1f} "
            f"{t.median:>8.1f} {t.p90:>7.1f}"
        )


def _stats() -> None:
    """Print a read-only summary of the persisted index (reuses the core)."""
    import time

    from src.core.rag.indexer import index_dir
    from src.core.rag.stats import fmt_disk_size, index_stats

    directory = index_dir()
    stats = index_stats(directory)
    if stats.n_chunks == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        _print_model_timings()  # timing history can exist without an index
        return

    when = (
        time.strftime("%d/%m/%Y %H:%M", time.localtime(stats.updated_at))
        if stats.updated_at
        else "?"
    )
    print("Índice RAG")
    print(f"  Documentos : {stats.n_docs}")
    print(f"  Chunks     : {stats.n_chunks}")
    print(f"  Dimensão   : {stats.dim}")
    print(f"  Modelo     : {stats.embed_model}")
    print(f"  Tamanho    : {fmt_disk_size(stats.disk_bytes)}")
    print(f"  Atualizado : {when}")
    print(f"  Local      : {directory}")
    print()

    name_w = 48
    print(f"  {'documento':<{name_w}} {'tipo':<13} {'chunks':>6}  data")
    print(f"  {'-' * name_w} {'-' * 13} {'-' * 6}  {'-' * 16}")
    for doc in stats.per_doc:
        name = Path(doc.source_path).name
        if len(name) > name_w:
            name = name[: name_w - 1] + "…"
        doc_when = time.strftime("%d/%m/%Y %H:%M", time.localtime(doc.mtime))
        print(f"  {name:<{name_w}} {doc.kind:<13} {doc.n_chunks:>6}  {doc_when}")

    _print_model_timings()


def _dups(ns: argparse.Namespace) -> None:
    """Print groups of near-duplicate documents (numpy-pure ML, no embedder).

    Reads the persisted index, pools it into document vectors and groups by
    cosine similarity. ``--scope`` (when a kind) restricts to one document kind;
    ``--threshold`` sets the minimum cosine to consider two documents duplicates.
    """
    from src.core.ml.dedup import near_duplicates
    from src.core.ml.features import document_matrix
    from src.core.ml.types import DocumentMatrix
    from src.core.rag import embedder
    from src.core.rag.indexer import index_dir
    from src.core.rag.store import VectorStore

    store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
    if len(store) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)

    dm = document_matrix(store)
    if ns.scope:  # restrict to one kind (a file scope simply won't match a kind)
        idx = [i for i, k in enumerate(dm.kinds) if k == ns.scope]
        dm = DocumentMatrix(
            X=dm.X[idx],
            source_paths=[dm.source_paths[i] for i in idx],
            kinds=[dm.kinds[i] for i in idx],
        )

    groups = near_duplicates(dm, threshold=ns.threshold)
    if not groups:
        print(
            f"Nenhuma duplicata acima de {ns.threshold:.2f} "
            f"entre {len(dm)} documento(s)."
        )
        return

    print(
        f"{len(groups)} grupo(s) de documentos semelhantes "
        f"(limiar {ns.threshold:.2f}):\n"
    )
    for n, group in enumerate(groups, 1):
        print(f"Grupo {n} — similaridade mínima {group.score:.3f}")
        for source in group.source_paths:
            print(f"  • {Path(source).name}")
        print()

    from src.core.observatory.activity import log_activity

    log_activity(
        "rag", "text_dedup", f"{len(groups)} grupo(s) de documentos semelhantes"
    )


def _semantic_map(store, *, embed_space_id: str = "?"):
    """Build the cached SemanticMap, exiting with a hint if [ml] is missing."""
    from src.core.ml import deps
    from src.core.ml.mapviz import build_semantic_map

    if not deps.is_available():
        print(f"ML indisponível. {deps.SETUP_HINT}")
        sys.exit(1)
    return build_semantic_map(store, embed_space_id=embed_space_id)


def _topics() -> None:
    """List the discovered topics (clusters): name, size; orphans last."""
    from collections import Counter

    from src.core.ml.mapviz import cluster_display_name
    from src.core.rag import embedder
    from src.core.rag.indexer import index_dir
    from src.core.rag.stats import embed_space_id
    from src.core.rag.store import VectorStore

    index_directory = index_dir()
    store = VectorStore.load(index_directory, dim=embedder.EMBED_DIM)
    if len(store) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)

    sm = _semantic_map(store, embed_space_id=embed_space_id(index_directory))
    counts = Counter(int(label) for label in sm.labels)
    clusters = sorted((c for c in counts if c != -1), key=lambda c: -counts[c])
    print(f"Tópicos do acervo ({len(sm)} documentos, {len(clusters)} grupos):\n")
    for c in clusters:
        print(f"  {counts[c]:>4}  {cluster_display_name(c, sm.cluster_names)}")
    if counts.get(-1):
        print(f"  {counts[-1]:>4}  órfãos (isolados)")


def _map(ns: argparse.Namespace) -> None:
    """Render the semantic map PNG to --out (default output/data/semantic_map.png)."""
    from src.core.data import charts
    from src.core.ml.mapviz import build_semantic_map, render_semantic_map_png
    from src.core.rag import embedder
    from src.core.rag.indexer import index_dir
    from src.core.rag.stats import embed_space_id
    from src.core.rag.store import VectorStore
    from src.utils import DATA_DIR

    index_directory = index_dir()
    store = VectorStore.load(index_directory, dim=embedder.EMBED_DIM)
    if len(store) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)
    if not charts.is_available():
        print(charts.SETUP_HINT)
        sys.exit(1)
    space_id = embed_space_id(index_directory)
    _semantic_map(store, embed_space_id=space_id)  # gate [ml] before projecting

    sm = build_semantic_map(store, projection=ns.method, embed_space_id=space_id)
    png = render_semantic_map_png(sm, title="Mapa semântico do acervo")
    out = Path(ns.out) if ns.out else DATA_DIR / "semantic_map.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"Mapa salvo em {out} ({len(sm)} documentos).")


def _resolve_doc_path(target: str, dm) -> str | None:
    """Match a user-given path to a document in the index (absolute, then basename)."""
    resolved = str(Path(target).resolve())
    if resolved in dm.source_paths:
        return resolved
    name = Path(target).name
    matches = [sp for sp in dm.source_paths if Path(sp).name == name]
    return matches[0] if len(matches) == 1 else None


def _related(ns: argparse.Namespace) -> None:
    """Print the documents most similar to a given one (numpy-pure, no [ml])."""
    from src.core.ml.features import load_document_matrix
    from src.core.ml.recommend import related
    from src.core.rag.indexer import index_dir

    if not ns.target:
        print("Informe o documento: uv run main.py ai related <arquivo>")
        sys.exit(1)
    dm = load_document_matrix(index_dir())
    if len(dm) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)

    source = _resolve_doc_path(ns.target, dm)
    if source is None:
        print(f"Documento não encontrado no índice: {ns.target}")
        sys.exit(1)

    hits = related(dm, source, k=ns.k)
    if not hits:
        print("Nenhum documento relacionado encontrado.")
        return
    print(f"Relacionados a {Path(source).name}:\n")
    for path, score in hits:
        print(f"  {score:.3f}  {Path(path).name}")


def _classify(ns: argparse.Namespace) -> None:
    """Print the suggested analysis profile for an indexed document.

    Reuses the pooled document vectors (no re-embedding of the doc itself); the
    embedder is only needed the first time, to embed the profile prototypes.
    """
    from src.analysis.profiles import get_profile
    from src.core.ml.classify import classify
    from src.core.ml.features import load_document_matrix
    from src.core.rag import embedder
    from src.core.rag.indexer import index_dir
    from src.core.rag.stats import embed_space_id

    if not ns.target:
        print("Informe o documento: uv run main.py ai classify <arquivo>")
        sys.exit(1)
    index_directory = index_dir()
    dm = load_document_matrix(index_directory)
    if len(dm) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)

    source = _resolve_doc_path(ns.target, dm)
    if source is None:
        print(f"Documento não encontrado no índice: {ns.target}")
        sys.exit(1)

    embed_model = ns.embed_model or embedder.DEFAULT_EMBED_MODEL
    doc_vec = dm.X[dm.source_paths.index(source)]
    try:
        result = classify(
            doc_vec,
            embed_fn=lambda t: embedder.embed_texts(t, model=embed_model),
            embed_space_id=embed_space_id(index_directory),
        )
    except RuntimeError:
        print(
            f"Embedder indisponível (protótipos não cacheados). {embedder.SETUP_HINT}"
        )
        sys.exit(1)

    label = get_profile(result.profile_id).label
    method = "supervisionado" if result.method == "supervised" else "zero-shot"
    print(f"Perfil sugerido para {Path(source).name}:\n")
    print(f"  {label}  ({result.profile_id})")
    print(
        f"  confiança {result.confidence:.2f} · margem {result.margin:.2f} · {method}"
    )
    if result.margin < 0.05:
        print(
            "\n  [!] Sugestão incerta — margem baixa entre os dois perfis mais próximos."
        )

    from src.core.observatory.activity import log_activity

    log_activity(
        "rag",
        "profile_classified",
        f"{Path(source).name}: {label} ({result.confidence:.2f})",
    )


def _read_target_text(ns: argparse.Namespace) -> tuple[Path, str] | None:
    """Resolve --target to an existing path and read its body, or exit."""
    from src.core.text.reader import read_document_text

    if not ns.target:
        print(
            "Informe o documento: uv run main.py ai <keywords|summary|entities> <arquivo>"
        )
        sys.exit(1)
    path = Path(ns.target)
    if not path.exists():
        print(f"Arquivo não encontrado: {ns.target}")
        sys.exit(1)
    return path, read_document_text(path)


def _keywords(ns: argparse.Namespace) -> None:
    """Print the document's keyphrases (YAKE), best (lowest score) first."""
    from src.core.text import keywords
    from src.core.text.lang import detect_lang

    path, text = _read_target_text(ns)
    if not keywords.is_available():
        print(keywords.SETUP_HINT)
        sys.exit(1)

    out = keywords.keyphrases(text, lang=detect_lang(text), top_n=ns.top)
    if not out:
        print("Nenhuma palavra-chave extraída.")
        return
    print(f"Palavras-chave de {path.name}:\n")
    for phrase, score in out:
        print(f"  {score:.4f}  {phrase}")


def _summary(ns: argparse.Namespace) -> None:
    """Print an extractive summary (TextRank) of the document."""
    from src.core.text import summarize

    path, text = _read_target_text(ns)
    if not summarize.is_available():
        print(summarize.SETUP_HINT)
        sys.exit(1)

    sentences = summarize.extractive_summary(text, sentences=ns.sentences)
    if not sentences:
        print("Documento vazio — nada a resumir.")
        return
    print(f"Resumo de {path.name} ({len(sentences)} frase(s)):\n")
    for sentence in sentences:
        print(f"  • {sentence}")


def _entities(ns: argparse.Namespace) -> None:
    """Print the named entities (spaCy NER) grouped by label."""
    from src.core.text import entities as ner
    from src.core.text.lang import detect_lang

    path, text = _read_target_text(ns)
    lang = detect_lang(text)
    if not ner.is_available(lang):
        print(ner.SETUP_HINT)
        sys.exit(1)

    found = ner.entities(text, lang=lang)
    if not found:
        print("Nenhuma entidade encontrada.")
        return
    by_label: dict[str, list[str]] = {}
    for entity_text, label in found:
        by_label.setdefault(label, []).append(entity_text)
    print(f"Entidades de {path.name}:\n")
    for label in sorted(by_label):
        print(f"  {label}: {', '.join(by_label[label])}")


def _nl2cli(ns: argparse.Namespace) -> None:
    """Translate ns.query (PT) into a `uv run main.py ...` command and print it.

    Same wiring as the AI hub's "Comandos CLI" GUI worker
    (gui/modules/ai/worker.py::run_ai_command): the same gate (Ollama chat,
    skipped for cloud models), the same core (nl2cli.to_command) with
    reference/validate_fn from cli/reference.py, the same Atividade log entry.
    """
    from src.cli.reference import build_reference, validate_command
    from src.core.observatory.status import ollama_inventory
    from src.core.text.nl2cli import DEFAULT_MODEL as NL2CLI_DEFAULT_MODEL
    from src.core.text.nl2cli import NL2CLIError, to_command
    from src.llm_factory import OLLAMA_SETUP_HINT, is_cloud_model

    model = ns.model or NL2CLI_DEFAULT_MODEL
    if not is_cloud_model(model) and not ollama_inventory().reachable:
        print(f"Ollama indisponível. Rode: {OLLAMA_SETUP_HINT}")
        sys.exit(1)

    try:
        command, explanation = to_command(
            ns.query, build_reference(), model=model, validate_fn=validate_command
        )
    except NL2CLIError as exc:
        print(f"Não consegui gerar um comando: {exc}")
        sys.exit(1)

    if not command:
        print(explanation or "Pedido fora do escopo desta CLI.")
        return

    print(command)
    if explanation:
        print(f"\n{explanation}")

    from src.core.observatory.activity import log_activity

    log_activity("rag", "nl2cli", command)


def _ask(ns: argparse.Namespace, embed_model: str) -> None:
    """Retrieve top-k chunks for the question and print a cited answer."""
    from src.core.rag import embedder
    from src.core.rag.chat import DEFAULT_MODEL, answer
    from src.core.rag.indexer import index_dir
    from src.core.rag.retriever import retrieve
    from src.core.rag.store import VectorStore

    store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
    if len(store) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)
    if not embedder.is_available(embed_model):
        print(f"Embedder indisponível. Rode: {embedder.SETUP_HINT}")
        sys.exit(1)

    _, embed_query = _embed_fns(embed_model)
    hits, _ = retrieve(
        ns.query,
        store,
        embed_query,
        k=ns.k,
        scope=_resolve_scope(ns.scope),
    )
    result = answer(ns.query, hits, model_name=ns.model or DEFAULT_MODEL)

    print(result.text)
    if result.sources:
        print("\nFontes:")
        for i, source in enumerate(result.sources, 1):
            print(f"  [{i}] {source.name}")


def _batch(ns: argparse.Namespace, embed_model: str) -> None:
    """Apply the question as an instruction to every indexed document (per kind)."""
    from src.core.rag import embedder
    from src.core.rag.batch import distinct_sources, run_batch
    from src.core.rag.chat import DEFAULT_MODEL
    from src.core.rag.indexer import index_dir
    from src.core.rag.store import VectorStore

    store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
    if len(store) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)
    if not embedder.is_available(embed_model):
        print(f"Embedder indisponível. Rode: {embedder.SETUP_HINT}")
        sys.exit(1)

    sources = distinct_sources(store, kind=ns.kind)
    if not sources:
        print("Nenhum documento corresponde ao filtro.")
        return

    _, embed_query = _embed_fns(embed_model)
    results = run_batch(
        ns.query,
        store,
        embed_query,
        sources=sources,
        model_name=ns.model or DEFAULT_MODEL,
        k=ns.k,
    )
    for result in results:
        print(f"\n=== {Path(result.source_path).name} ===")
        print(result.answer.text)

    succeeded = {r.source_path for r in results}
    failed = [s for s in sources if s not in succeeded]
    if failed:
        print(f"\n{len(failed)} de {len(sources)} documento(s) falharam (ver log):")
        for source in failed:
            print(f"  • {Path(source).name}")


def _eval(ns: argparse.Namespace) -> None:
    """Dispatch `ai eval` by its ``target`` sub-action: run/list/add/promote."""
    action = (ns.target or "run").lower()
    if action == "list":
        _eval_list()
    elif action == "add":
        _eval_add(ns)
    elif action == "promote":
        _eval_promote()
    elif action == "run":
        _eval_run(ns)
    else:
        print(f"Ação desconhecida: {action}. Use: ai eval [run|list|add|promote].")
        sys.exit(1)


def _eval_list() -> None:
    """List the golden set (covered + out-of-corpus) plus covered suggestions."""
    from src.core.rag.eval import load_eval_data, suggested_covered

    data = load_eval_data()
    covered = [g for g in data.golden if not g.is_out_of_corpus]
    out = [g for g in data.golden if g.is_out_of_corpus]
    print(
        f"Golden set — {len(covered)} coberta(s), {len(out)} fora-do-acervo, "
        f"{len(data.runs)} rodada(s) no histórico\n"
    )
    if covered:
        print("Cobertas (documento esperado no top-k):")
        for g in covered:
            docs = ", ".join(Path(e).name for e in g.expected)
            print(f"  • {g.question}")
            print(f"      → {docs}")
        print()
    if out:
        print("Fora-do-acervo (devem disparar o aviso de baixa cobertura):")
        for g in out:
            print(f"  • {g.question}")
        print()
    print('Sugestões (adicione com: ai eval add --question "..." --expect <arquivo>):')
    for s in suggested_covered():
        print(f"  • {s.question}  [{s.hint}]")


def _eval_add(ns: argparse.Namespace) -> None:
    """Add a golden question — covered when --expect is given, else out-of-corpus."""
    from src.core.rag.eval import add_question

    if not ns.question:
        print('Informe a pergunta: ai eval add --question "..." [--expect <arquivo>]')
        sys.exit(1)
    expected = ns.expect or []
    missing = [e for e in expected if not Path(e).exists()]
    gq = add_question(ns.question, expected)
    if gq.expected:
        print(
            f"Pergunta coberta adicionada ({len(gq.expected)} documento(s) esperado(s))."
        )
    else:
        print("Pergunta fora-do-acervo adicionada.")
    if missing:
        print(
            f"[!] {len(missing)} caminho(s) não existe(m) agora — o casamento usará "
            "o nome do arquivo (basename)."
        )


def _eval_promote() -> None:
    """Promote thumbs-up feedback with cited sources into covered golden questions.

    A 👍 whose turn cited sources is a ready-made covered question (question =
    the query actually searched, expected = the cited sources). This is the only
    curation surface (PLANO_RAG_EVAL, Fase 5.2) — no editing UI; the feedback is
    still collect-only otherwise.
    """
    from src.core.rag.eval import add_question, load_eval_data
    from src.core.rag.feedback import VERDICT_UP, load_feedback

    ups = [e for e in load_feedback() if e.verdict == VERDICT_UP and e.sources]
    if not ups:
        print("Nenhum feedback 👍 com fontes citadas para promover.")
        return

    existing = {g.question for g in load_eval_data().golden}
    added = 0
    for entry in ups:
        question = entry.search_query or entry.query
        if question in existing:
            continue
        add_question(question, entry.sources)
        existing.add(question)
        added += 1

    if added:
        print(f"{added} pergunta(s) promovida(s) a golden a partir do feedback 👍.")
    else:
        print("Nenhuma pergunta nova — os 👍 já estão no golden set.")


def _print_eval_report(result, stats) -> None:
    """Print the run's metrics and the per-question breakdown."""
    from src.core.rag.stats import fmt_thousands

    m = result.metrics

    def _row(label: str, value: str) -> None:
        print(f"  {label:<22}: {value}")

    print(f"Avaliação do RAG (k={result.k})")
    print(
        f"  Índice   : {fmt_thousands(stats.n_docs)} docs · "
        f"{fmt_thousands(stats.n_chunks)} chunks · esquema {result.embed_scheme}"
    )
    print(
        f"  Perguntas: {m.n_covered} coberta(s) + {m.n_out_of_corpus} fora-do-acervo\n"
    )

    covered_hits = sum(1 for o in result.outcomes if not o.is_out_of_corpus and o.hit)
    _row(
        f"hit-rate@{result.k}",
        f"{m.hit_rate:.0%}  ({covered_hits}/{m.n_covered})"
        if m.n_covered
        else "—  (sem cobertas)",
    )
    _row("MRR", f"{m.mrr:.2f}" if m.n_covered else "—")
    _row("cosseno médio (cob.)", f"{m.mean_covered_score:.2f}" if m.n_covered else "—")
    _row(
        "cosseno médio (fora)",
        f"{m.mean_out_score:.2f}" if m.n_out_of_corpus else "—",
    )
    _row("acurácia do flag", f"{m.flag_accuracy:.0%}")

    if result.outcomes:
        print("\n  Por pergunta:")
        for o in result.outcomes:
            _print_outcome(o)


def _print_outcome(o) -> None:
    """Print one per-question line of the eval report."""
    score = f"{o.pool_max_score:.2f}"
    question = o.question if len(o.question) <= 60 else o.question[:59] + "…"
    if o.is_out_of_corpus:
        mark = "flag ✓" if o.flag_correct else "flag ✗"
        print(f"   [{mark}] {score}  {question}  (fora-do-acervo)")
    elif o.hit:
        print(f"   [✓] rank {o.rank:<2} {score}  {question}")
    else:
        print(f"   [✗] ----   {score}  {question}")


def _print_eval_delta(latest, previous, *, has_prior: bool) -> None:
    """Print the delta against the previous comparable run (same embed space)."""
    if previous is not None:
        d_hit = latest.metrics.hit_rate - previous.metrics.hit_rate
        d_mrr = latest.metrics.mrr - previous.metrics.mrr
        print("\nDelta vs. rodada anterior comparável:")
        print(f"  hit-rate {d_hit:+.0%} · MRR {d_mrr:+.2f}")
    elif has_prior:
        print(
            "\n[i] Rodada anterior em espaço de embedding diferente — incomparável "
            "(o modelo/esquema mudou; a reindexação recalibra a base)."
        )


def _eval_run(ns: argparse.Namespace) -> None:
    """Run the golden set through retrieval; print metrics + delta, record the run.

    Retrieval-only (no LLM). Refuses when the index is empty, the embedder is
    down, or the index is on a stale scheme (evaluating that measures an
    artifact — the sidecar claims a scheme the vectors don't have).
    """
    from src.core.observatory.activity import log_activity
    from src.core.rag import embedder
    from src.core.rag.eval import (
        latest_and_previous,
        load_eval_data,
        record_run,
        run_eval,
    )
    from src.core.rag.indexer import CURRENT_EMBED_SCHEME, index_dir
    from src.core.rag.stats import embed_space_id, index_stats, is_stale_scheme
    from src.core.rag.store import VectorStore

    directory = index_dir()
    store = VectorStore.load(directory, dim=embedder.EMBED_DIM)
    if len(store) == 0:
        print('Índice vazio. Rode "uv run main.py ai index" primeiro.')
        sys.exit(1)

    data = load_eval_data()
    if not data.golden:
        print('Golden set vazio. Adicione perguntas com: ai eval add --question "..."')
        return

    stats = index_stats(directory)
    if is_stale_scheme(stats, CURRENT_EMBED_SCHEME):
        print(
            "[!] Índice em esquema antigo — reindexe antes de avaliar "
            "(uv run main.py ai index)."
        )
        sys.exit(1)

    embed_model = ns.embed_model or embedder.DEFAULT_EMBED_MODEL
    if not embedder.is_available(embed_model):
        print(f"Embedder indisponível. Rode: {embedder.SETUP_HINT}")
        sys.exit(1)

    _, embed_query = _embed_fns(embed_model)
    result = run_eval(
        data.golden,
        store,
        embed_query,
        k=ns.k,
        embed_space_id=embed_space_id(directory),
        embed_scheme=stats.embed_scheme,
    )
    record_run(result)

    _print_eval_report(result, stats)
    data_after = load_eval_data()
    latest, previous = latest_and_previous(data_after)
    _print_eval_delta(latest, previous, has_prior=len(data_after.runs) > 1)

    m = result.metrics
    log_activity(
        "rag",
        "rag_eval",
        f"avaliação: hit-rate {m.hit_rate:.0%}, MRR {m.mrr:.2f} "
        f"({m.n_covered} cob. + {m.n_out_of_corpus} fora)",
    )


def run_ai_cli(ns: argparse.Namespace) -> None:
    """Dispatch the `ai` subcommand: (re)index and/or answer/batch a question."""
    # Output filenames may contain non-cp1252 characters (e.g. fullwidth ｜).
    # Reconfigure only our real stdout; under pytest sys.stdout is a capture
    # wrapper (≠ __stdout__) whose reconfigure would drop the captured output.
    if sys.stdout is sys.__stdout__:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if getattr(ns, "cmd", False):  # NL->CLI mode overrides every keyword flow below
        _nl2cli(ns)
        return

    if ns.query == _STATS_CMD:  # read-only summary; no embedder needed
        _stats()
        return

    if ns.query == _DUPS_CMD:  # read-only ML over the persisted index; no embedder
        _dups(ns)
        return

    if ns.query == _TOPICS_CMD:  # cluster the index into named topics ([ml])
        _topics()
        return

    if ns.query == _MAP_CMD:  # render the semantic map PNG ([ml] + chart extras)
        _map(ns)
        return

    if ns.query == _RELATED_CMD:  # nearest documents to one (numpy-pure, no [ml])
        _related(ns)
        return

    if ns.query == _CLASSIFY_CMD:  # suggest the analysis profile (zero-shot/supervised)
        _classify(ns)
        return

    if ns.query == _KEYWORDS_CMD:  # YAKE keyphrases over the document ([nlp])
        _keywords(ns)
        return

    if ns.query == _SUMMARY_CMD:  # extractive TextRank summary ([ml])
        _summary(ns)
        return

    if ns.query == _ENTITIES_CMD:  # spaCy NER over the document ([nlp] + model)
        _entities(ns)
        return

    if ns.query == _EVAL_CMD:  # retrieval-only eval harness (run/list/add)
        _eval(ns)
        return

    from src.core.rag import embedder

    embed_model = ns.embed_model or embedder.DEFAULT_EMBED_MODEL

    if ns.query == _INDEX_CMD or ns.reindex:
        if not embedder.is_available(embed_model):
            print(f"Embedder indisponível. Rode: {embedder.SETUP_HINT}")
            sys.exit(1)
        logging.info("[*] Building index (embed model: %s)...", embed_model)
        _build(embed_model)
        if ns.query == _INDEX_CMD:
            return

    if getattr(ns, "batch", False):
        _batch(ns, embed_model)
    else:
        _ask(ns, embed_model)
