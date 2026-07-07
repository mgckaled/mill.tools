"""Unit tests for src/cli/ai.py — parser defaults, dispatch and scope helper."""

from __future__ import annotations

import argparse

import numpy as np
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.cli.ai import add_ai_parser


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_ai_parser(sub)
    return parser.parse_args(["ai", *argv])


def _fake_llm(*responses: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


def _persisted_store(directory, *, source: str = "doc.txt"):
    """Persist a one-row store at `directory` and return it."""
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    store = VectorStore(dim=768)
    store.add(
        np.ones((1, 768), dtype=np.float32),
        [ChunkMeta(source, "transcription", 1.0, 0, "context text")],
    )
    store.persist(directory)
    return store


@pytest.mark.unit
def test_defaults():
    ns = _parse("what did I say about whisper?")
    assert ns.query == "what did I say about whisper?"
    assert ns.k == 6
    assert ns.scope is None
    assert ns.model is None
    assert ns.embed_model is None
    assert ns.reindex is False
    assert ns.cmd is False
    assert callable(ns.func)


@pytest.mark.unit
def test_parses_options():
    ns = _parse(
        "resuma", "--scope", "transcription", "--model", "gemini-2.5-flash", "--k", "8"
    )
    assert ns.scope == "transcription"
    assert ns.model == "gemini-2.5-flash"
    assert ns.k == 8


@pytest.mark.unit
def test_parses_batch_flags():
    ns = _parse("resuma", "--batch", "--kind", "document")
    assert ns.batch is True
    assert ns.kind == "document"


@pytest.mark.unit
def test_index_query_dispatches_to_build_only(mocker):
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    build = mocker.patch("src.cli.ai._build")
    ask = mocker.patch("src.cli.ai._ask")

    ns = _parse("index")
    ns.func(ns)

    assert build.called
    assert not ask.called


@pytest.mark.unit
def test_question_dispatches_to_ask_only(mocker):
    build = mocker.patch("src.cli.ai._build")
    ask = mocker.patch("src.cli.ai._ask")

    ns = _parse("what is x?")
    ns.func(ns)

    assert ask.called
    assert not build.called


@pytest.mark.unit
def test_reindex_flag_builds_then_asks(mocker):
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    build = mocker.patch("src.cli.ai._build")
    ask = mocker.patch("src.cli.ai._ask")

    ns = _parse("what is x?", "--reindex")
    ns.func(ns)

    assert build.called
    assert ask.called


@pytest.mark.unit
def test_index_exits_when_embedder_unavailable(mocker, capsys):
    mocker.patch("src.core.rag.embedder.is_available", return_value=False)
    mocker.patch("src.cli.ai._build")

    ns = _parse("index")
    with pytest.raises(SystemExit):
        ns.func(ns)

    assert "ollama pull" in capsys.readouterr().out


@pytest.mark.unit
def test_stats_query_parses():
    ns = _parse("stats")
    assert ns.query == "stats"
    assert callable(ns.func)


@pytest.mark.unit
def test_stats_dispatches_to_stats_runner(mocker):
    stats = mocker.patch("src.cli.ai._stats")
    ask = mocker.patch("src.cli.ai._ask")
    build = mocker.patch("src.cli.ai._build")

    ns = _parse("stats")
    ns.func(ns)

    assert stats.called
    assert not ask.called
    assert not build.called


@pytest.mark.unit
def test_stats_runner_prints_summary(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _stats

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir, source="alpha.txt")
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch("src.cli.ai._answer_times", return_value={})  # hermetic

    _stats()

    out = capsys.readouterr().out
    assert "Índice RAG" in out
    assert "Documentos : 1" in out
    assert "Chunks     : 1" in out
    assert "alpha.txt" in out
    assert "transcription" in out


@pytest.mark.unit
def test_stats_runner_empty_index_prints_hint(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _stats

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")
    mocker.patch("src.cli.ai._answer_times", return_value={})  # hermetic
    _stats()
    assert "Índice vazio" in capsys.readouterr().out


@pytest.mark.unit
def test_print_model_timings_renders_fastest_first(mocker, capsys):
    from src.cli.ai import _print_model_timings

    mocker.patch(
        "src.cli.ai._answer_times",
        return_value={"slow": [10.0, 20.0], "fast": [1.0, 3.0]},
    )
    _print_model_timings()
    out = capsys.readouterr().out
    assert "Tempos de resposta por modelo" in out
    assert out.index("fast") < out.index("slow")  # fastest first


@pytest.mark.unit
def test_print_model_timings_silent_without_history(mocker, capsys):
    from src.cli.ai import _print_model_timings

    mocker.patch("src.cli.ai._answer_times", return_value={})
    _print_model_timings()
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_answer_times_reads_config(tmp_path, monkeypatch):
    from src.cli.ai import _answer_times

    config_dir = tmp_path / ".mill-tools"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(
        '{"ai_answer_times": {"m": [1.0, 2.0]}}', encoding="utf-8"
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert _answer_times() == {"m": [1.0, 2.0]}


@pytest.mark.unit
def test_answer_times_missing_config_returns_empty(tmp_path, monkeypatch):
    from src.cli.ai import _answer_times

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert _answer_times() == {}


@pytest.mark.unit
def test_resolve_scope_existing_file_becomes_absolute(tmp_path):
    from src.cli.ai import _resolve_scope

    f = tmp_path / "x.txt"
    f.write_text("hi", encoding="utf-8")
    assert _resolve_scope(str(f)) == str(f.resolve())


@pytest.mark.unit
def test_resolve_scope_kind_and_none():
    from src.cli.ai import _resolve_scope

    assert _resolve_scope("transcription") == "transcription"
    assert _resolve_scope(None) is None


@pytest.mark.unit
def test_build_scans_embeds_and_persists(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _build
    from src.core.library.types import LibraryItem

    rag_dir = tmp_path / "rag"
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    item = LibraryItem(
        path=f,
        kind="transcription",
        category="text",
        size_bytes=f.stat().st_size,
        modified=1.0,
        stem="a",
        suffix=".txt",
    )
    mocker.patch("src.core.library.scanner.scan_library", return_value=[item])
    mocker.patch(
        "src.core.rag.embedder.embed_texts",
        return_value=np.ones((1, 768), dtype=np.float32),
    )

    _build("nomic-embed-text")

    assert (rag_dir / "vectors.npz").exists()
    assert "Índice atualizado" in capsys.readouterr().out


@pytest.mark.unit
def test_ask_prints_answer_and_sources(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.chat as chat
    import src.core.rag.indexer as indexer
    from src.cli.ai import _ask

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir, source="doc.txt")
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch(
        "src.core.rag.embedder.embed_query",
        return_value=np.ones(768, dtype=np.float32),
    )
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta [1]"))

    _ask(_parse("pergunta?"), "nomic-embed-text")

    out = capsys.readouterr().out
    assert "resposta [1]" in out
    assert "Fontes:" in out
    assert "doc.txt" in out


@pytest.mark.unit
def test_ask_exits_when_index_empty(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _ask

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")

    with pytest.raises(SystemExit):
        _ask(_parse("q?"), "nomic-embed-text")
    assert "Índice vazio" in capsys.readouterr().out


@pytest.mark.unit
def test_ask_exits_when_embedder_unavailable(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _ask

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch("src.core.rag.embedder.is_available", return_value=False)

    with pytest.raises(SystemExit):
        _ask(_parse("q?"), "nomic-embed-text")
    assert "ollama pull" in capsys.readouterr().out


@pytest.mark.unit
def test_batch_flag_dispatches_to_batch_runner(mocker):
    batch = mocker.patch("src.cli.ai._batch")
    ask = mocker.patch("src.cli.ai._ask")

    ns = _parse("resuma", "--batch")
    ns.func(ns)

    assert batch.called
    assert not ask.called


@pytest.mark.unit
def test_batch_runner_prints_per_document(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.chat as chat
    import src.core.rag.indexer as indexer
    from src.cli.ai import _batch
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    rag_dir = tmp_path / "rag"
    store = VectorStore(dim=768)
    store.add(
        np.ones((2, 768), dtype=np.float32),
        [
            ChunkMeta("alpha.txt", "transcription", 1.0, 0, "ctx a"),
            ChunkMeta("beta.txt", "transcription", 1.0, 0, "ctx b"),
        ],
    )
    store.persist(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch(
        "src.core.rag.embedder.embed_query",
        return_value=np.ones(768, dtype=np.float32),
    )
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("R-alpha", "R-beta"))

    _batch(_parse("resuma", "--batch"), "nomic-embed-text")

    out = capsys.readouterr().out
    assert "alpha.txt" in out and "beta.txt" in out
    assert "R-alpha" in out and "R-beta" in out


@pytest.mark.unit
def test_batch_runner_exits_when_index_empty(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _batch

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")
    with pytest.raises(SystemExit):
        _batch(_parse("resuma", "--batch"), "nomic-embed-text")
    assert "Índice vazio" in capsys.readouterr().out


@pytest.mark.unit
def test_batch_runner_exits_when_embedder_unavailable(
    tmp_path, monkeypatch, mocker, capsys
):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _batch

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch("src.core.rag.embedder.is_available", return_value=False)

    with pytest.raises(SystemExit):
        _batch(_parse("resuma", "--batch"), "nomic-embed-text")
    assert "ollama pull" in capsys.readouterr().out


@pytest.mark.unit
def test_batch_runner_reports_no_match_for_kind(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _batch

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir)  # one transcription chunk
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)

    # No document-kind sources → graceful message, no crash.
    _batch(_parse("resuma", "--batch", "--kind", "document"), "nomic-embed-text")
    assert "Nenhum documento" in capsys.readouterr().out


# --- ai dups (Plan 3 — ML foundation proof of life) -------------------------


def _persist_two_docs(directory, *, identical: bool) -> None:
    """Persist a store with two single-chunk documents (identical or orthogonal).

    a.txt is kind=transcription, b.txt is kind=document. When ``identical`` both
    vectors are all-ones (cosine 1.0 → duplicates); otherwise b.txt is orthogonal
    to a.txt (cosine 0 → never grouped).
    """
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    a_vec = np.ones((1, 768), dtype=np.float32)
    if identical:
        b_vec = np.ones((1, 768), dtype=np.float32)
    else:
        b_vec = np.zeros((1, 768), dtype=np.float32)
        b_vec[0, 0] = 1.0  # unit vector orthogonal to all-ones

    store = VectorStore(dim=768)
    store.add(a_vec, [ChunkMeta("a.txt", "transcription", 1.0, 0, "ctx a")])
    store.add(b_vec, [ChunkMeta("b.txt", "document", 2.0, 0, "ctx b")])
    store.persist(directory)


@pytest.mark.unit
def test_dups_command_parses_with_threshold():
    ns = _parse("dups", "--threshold", "0.8")
    assert ns.query == "dups"
    assert ns.threshold == 0.8
    assert callable(ns.func)


@pytest.mark.unit
def test_dups_default_threshold():
    ns = _parse("dups")
    assert ns.threshold == 0.95


@pytest.mark.unit
def test_dups_dispatches_to_dups_runner(mocker):
    dups = mocker.patch("src.cli.ai._dups")
    ask = mocker.patch("src.cli.ai._ask")

    ns = _parse("dups")
    ns.func(ns)

    assert dups.called
    assert not ask.called


@pytest.mark.unit
def test_dups_groups_identical_documents(tmp_path, monkeypatch, capsys):
    import src.core.observatory.activity as activity
    import src.core.rag.indexer as indexer
    from src.cli.ai import _dups

    rag_dir = tmp_path / "rag"
    _persist_two_docs(rag_dir, identical=True)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    monkeypatch.setattr(activity, "log_activity", lambda *a, **k: None)

    _dups(_parse("dups"))

    out = capsys.readouterr().out
    assert "grupo" in out.lower()
    assert "a.txt" in out and "b.txt" in out


@pytest.mark.unit
def test_dups_reports_none_when_distinct(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _dups

    rag_dir = tmp_path / "rag"
    _persist_two_docs(rag_dir, identical=False)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    _dups(_parse("dups"))
    assert "Nenhuma duplicata" in capsys.readouterr().out


@pytest.mark.unit
def test_dups_scope_filters_by_kind(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _dups

    rag_dir = tmp_path / "rag"
    _persist_two_docs(rag_dir, identical=True)  # a=transcription, b=document
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    # Restricting to one kind leaves a single document → no pair to group.
    _dups(_parse("dups", "--scope", "transcription"))
    out = capsys.readouterr().out
    assert "Nenhuma duplicata" in out
    assert "1 documento" in out


@pytest.mark.unit
def test_dups_exits_when_index_empty(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _dups

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")
    with pytest.raises(SystemExit):
        _dups(_parse("dups"))
    assert "Índice vazio" in capsys.readouterr().out


# --- ai topics / map / related (Plan 4A — semantic layer) -------------------


def _persist_themes(directory) -> None:
    """Persist a store with two well-separated themes of single-chunk docs."""
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    rng = np.random.default_rng(0)
    store = VectorStore(dim=8)
    for i in range(8):
        v = np.zeros(8, dtype=np.float32)
        v[0] = 1.0
        v += rng.normal(0, 0.02, 8).astype(np.float32)
        store.add(
            v[None],
            [
                ChunkMeta(
                    f"whisper_{i}.txt",
                    "transcription",
                    1.0,
                    0,
                    "whisper gpu transcription audio",
                )
            ],
        )
    for i in range(8):
        v = np.zeros(8, dtype=np.float32)
        v[1] = 1.0
        v += rng.normal(0, 0.02, 8).astype(np.float32)
        store.add(
            v[None],
            [
                ChunkMeta(
                    f"duna_{i}.txt", "document", 2.0, 0, "duna herbert arrakis spice"
                )
            ],
        )
    store.persist(directory)


@pytest.mark.unit
def test_topics_map_related_parse():
    assert _parse("topics").query == "topics"
    m = _parse("map", "--method", "umap", "--out", "x.png")
    assert m.query == "map" and m.method == "umap" and m.out == "x.png"
    r = _parse("related", "doc.txt", "--k", "3")
    assert r.query == "related" and r.target == "doc.txt" and r.k == 3


@pytest.mark.unit
def test_map_default_method_is_pca():
    assert _parse("map").method == "pca"


@pytest.mark.unit
def test_map_accepts_tsne_method():
    assert _parse("map", "--method", "tsne").method == "tsne"


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd,runner",
    [
        ("topics", "_topics"),
        ("map", "_map"),
        ("related", "_related"),
    ],
)
def test_semantic_commands_dispatch(mocker, cmd, runner):
    target = mocker.patch(f"src.cli.ai.{runner}")
    ask = mocker.patch("src.cli.ai._ask")
    ns = _parse(cmd, *(["doc.txt"] if cmd == "related" else []))
    ns.func(ns)
    assert target.called
    assert not ask.called


@pytest.mark.unit
def test_related_prints_neighbours(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _related

    rag_dir = tmp_path / "rag"
    _persist_themes(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    _related(_parse("related", "whisper_0.txt", "--k", "3"))
    out = capsys.readouterr().out
    assert "Relacionados a whisper_0.txt" in out
    # Its nearest neighbours are other whisper docs, not the duna theme.
    assert "whisper_" in out


@pytest.mark.unit
def test_related_exits_without_target(tmp_path, monkeypatch, capsys):
    from src.cli.ai import _related

    with pytest.raises(SystemExit):
        _related(_parse("related"))
    assert "Informe o documento" in capsys.readouterr().out


@pytest.mark.unit
def test_related_exits_when_doc_not_found(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _related

    rag_dir = tmp_path / "rag"
    _persist_themes(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    with pytest.raises(SystemExit):
        _related(_parse("related", "ghost.txt"))
    assert "não encontrado" in capsys.readouterr().out


@pytest.mark.unit
def test_related_exits_when_index_empty(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _related

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")
    with pytest.raises(SystemExit):
        _related(_parse("related", "x.txt"))
    assert "Índice vazio" in capsys.readouterr().out


@pytest.mark.unit
def test_topics_lists_clusters(tmp_path, monkeypatch, capsys):
    pytest.importorskip("sklearn")
    import src.core.ml.store as ml_store
    import src.core.rag.indexer as indexer
    from src.cli.ai import _topics

    rag_dir = tmp_path / "rag"
    _persist_themes(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    monkeypatch.setattr(ml_store, "model_dir", lambda: tmp_path / "ml")  # isolate cache

    _topics()
    out = capsys.readouterr().out
    assert "Tópicos do acervo" in out


@pytest.mark.unit
def test_topics_exits_when_index_empty(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _topics

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")
    with pytest.raises(SystemExit):
        _topics()
    assert "Índice vazio" in capsys.readouterr().out


@pytest.mark.unit
def test_related_matches_absolute_path(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _related
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    # Store the source under an absolute path so the absolute-match branch hits.
    abs_a = str((tmp_path / "abs_a.txt").resolve())
    abs_b = str((tmp_path / "abs_b.txt").resolve())
    rag_dir = tmp_path / "rag"
    store = VectorStore(dim=8)
    store.add(
        np.ones((1, 8), dtype=np.float32),
        [ChunkMeta(abs_a, "transcription", 1.0, 0, "a")],
    )
    store.add(
        np.full((1, 8), 0.9, dtype=np.float32),
        [ChunkMeta(abs_b, "transcription", 1.0, 0, "b")],
    )
    store.persist(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    _related(_parse("related", abs_a))
    assert "abs_b.txt" in capsys.readouterr().out


@pytest.mark.unit
def test_topics_exits_when_ml_missing(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _topics

    rag_dir = tmp_path / "rag"
    _persist_themes(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch("src.core.ml.deps.is_available", return_value=False)

    with pytest.raises(SystemExit):
        _topics()
    assert "ML indisponível" in capsys.readouterr().out


@pytest.mark.unit
def test_map_writes_png(tmp_path, monkeypatch, capsys):
    pytest.importorskip("sklearn")
    pytest.importorskip("matplotlib")
    import src.core.ml.store as ml_store
    import src.core.rag.indexer as indexer
    from src.cli.ai import _map

    rag_dir = tmp_path / "rag"
    _persist_themes(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    monkeypatch.setattr(ml_store, "model_dir", lambda: tmp_path / "ml")

    out_png = tmp_path / "map.png"
    _map(_parse("map", "--out", str(out_png)))
    assert out_png.exists()
    assert out_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert "Mapa salvo" in capsys.readouterr().out


@pytest.mark.unit
def test_map_exits_when_index_empty(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _map

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")
    with pytest.raises(SystemExit):
        _map(_parse("map"))
    assert "Índice vazio" in capsys.readouterr().out


@pytest.mark.unit
def test_map_exits_when_chart_extras_missing(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _map

    rag_dir = tmp_path / "rag"
    _persist_themes(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch("src.core.data.charts.is_available", return_value=False)

    with pytest.raises(SystemExit):
        _map(_parse("map"))
    out = capsys.readouterr().out
    assert "Gráficos indisponíveis" in out or "extra" in out


@pytest.mark.unit
def test_related_reports_none_for_single_doc(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _related
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    rag_dir = tmp_path / "rag"
    store = VectorStore(dim=8)
    store.add(
        np.ones((1, 8), dtype=np.float32),
        [ChunkMeta("only.txt", "transcription", 1.0, 0, "alone")],
    )
    store.persist(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    _related(_parse("related", "only.txt"))
    assert "Nenhum documento relacionado" in capsys.readouterr().out


# --- ai classify / keywords / summary / entities (Plan 4B) ------------------


@pytest.mark.unit
def test_textual_commands_parse():
    assert _parse("classify", "doc.txt").target == "doc.txt"
    s = _parse("summary", "doc.txt", "--sentences", "3")
    assert s.query == "summary" and s.target == "doc.txt" and s.sentences == 3
    k = _parse("keywords", "doc.txt", "--top", "7")
    assert k.query == "keywords" and k.top == 7
    assert _parse("entities", "doc.txt").query == "entities"


@pytest.mark.unit
def test_textual_default_sentences_and_top():
    ns = _parse("summary", "doc.txt")
    assert ns.sentences == 5
    assert ns.top == 10


@pytest.mark.unit
@pytest.mark.parametrize(
    "cmd,runner",
    [
        ("classify", "_classify"),
        ("keywords", "_keywords"),
        ("summary", "_summary"),
        ("entities", "_entities"),
    ],
)
def test_textual_commands_dispatch(mocker, cmd, runner):
    target = mocker.patch(f"src.cli.ai.{runner}")
    ask = mocker.patch("src.cli.ai._ask")
    ns = _parse(cmd, "doc.txt")
    ns.func(ns)
    assert target.called
    assert not ask.called


@pytest.mark.unit
def test_classify_prints_suggested_profile(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _classify
    from src.core.ml.types import Classification

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir, source="aula.txt")
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch(
        "src.core.ml.classify.classify",
        return_value=Classification("lecture", 0.82, 0.30, "zeroshot"),
    )
    mocker.patch("src.core.observatory.activity.log_activity")

    _classify(_parse("classify", "aula.txt"))
    out = capsys.readouterr().out
    assert "Aula" in out  # the lecture profile's PT label
    assert "lecture" in out
    assert "zero-shot" in out


@pytest.mark.unit
def test_classify_warns_on_low_margin(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _classify
    from src.core.ml.types import Classification

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir, source="x.txt")
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch(
        "src.core.ml.classify.classify",
        return_value=Classification("lecture", 0.40, 0.01, "zeroshot"),
    )
    mocker.patch("src.core.observatory.activity.log_activity")

    _classify(_parse("classify", "x.txt"))
    assert "incerta" in capsys.readouterr().out


@pytest.mark.unit
def test_classify_exits_without_target(tmp_path, monkeypatch, capsys):
    from src.cli.ai import _classify

    with pytest.raises(SystemExit):
        _classify(_parse("classify"))
    assert "Informe o documento" in capsys.readouterr().out


@pytest.mark.unit
def test_classify_exits_when_doc_not_found(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _classify

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir, source="present.txt")
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    with pytest.raises(SystemExit):
        _classify(_parse("classify", "ghost.txt"))
    assert "não encontrado" in capsys.readouterr().out


@pytest.mark.unit
def test_classify_exits_when_prototypes_need_embedder(
    tmp_path, monkeypatch, mocker, capsys
):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _classify

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir, source="doc.txt")
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch(
        "src.core.ml.classify.classify", side_effect=RuntimeError("not cached")
    )

    with pytest.raises(SystemExit):
        _classify(_parse("classify", "doc.txt"))
    assert "ollama pull" in capsys.readouterr().out


@pytest.mark.unit
def test_keywords_prints_phrases(tmp_path, mocker, capsys):
    from src.cli.ai import _keywords

    f = tmp_path / "doc.txt"
    f.write_text("Banco Central e taxa de juros.", encoding="utf-8")
    mocker.patch("src.core.text.keywords.is_available", return_value=True)
    mocker.patch(
        "src.core.text.keywords.keyphrases",
        return_value=[("banco central", 0.01), ("taxa de juros", 0.03)],
    )

    _keywords(_parse("keywords", str(f)))
    out = capsys.readouterr().out
    assert "banco central" in out
    assert "0.0100" in out


@pytest.mark.unit
def test_keywords_exits_when_unavailable(tmp_path, mocker, capsys):
    from src.cli.ai import _keywords

    f = tmp_path / "doc.txt"
    f.write_text("texto", encoding="utf-8")
    mocker.patch("src.core.text.keywords.is_available", return_value=False)

    with pytest.raises(SystemExit):
        _keywords(_parse("keywords", str(f)))
    assert "nlp" in capsys.readouterr().out


@pytest.mark.unit
def test_textual_exits_when_file_missing(capsys):
    from src.cli.ai import _summary

    with pytest.raises(SystemExit):
        _summary(_parse("summary", "/no/such/file.txt"))
    assert "não encontrado" in capsys.readouterr().out


@pytest.mark.unit
def test_summary_prints_sentences(tmp_path, mocker, capsys):
    from src.cli.ai import _summary

    f = tmp_path / "doc.txt"
    f.write_text("Frase um. Frase dois. Frase três.", encoding="utf-8")
    mocker.patch("src.core.text.summarize.is_available", return_value=True)
    mocker.patch(
        "src.core.text.summarize.extractive_summary",
        return_value=["Frase central."],
    )

    _summary(_parse("summary", str(f), "--sentences", "1"))
    out = capsys.readouterr().out
    assert "Frase central." in out
    assert "1 frase" in out


@pytest.mark.unit
def test_entities_prints_grouped_by_label(tmp_path, mocker, capsys):
    from src.cli.ai import _entities

    f = tmp_path / "doc.txt"
    f.write_text("Maria foi à Petrobras.", encoding="utf-8")
    mocker.patch("src.core.text.entities.is_available", return_value=True)
    mocker.patch(
        "src.core.text.entities.entities",
        return_value=[("Maria", "PER"), ("Petrobras", "ORG")],
    )

    _entities(_parse("entities", str(f)))
    out = capsys.readouterr().out
    assert "PER: Maria" in out
    assert "ORG: Petrobras" in out


@pytest.mark.unit
def test_entities_exits_when_model_missing(tmp_path, mocker, capsys):
    from src.cli.ai import _entities

    f = tmp_path / "doc.txt"
    f.write_text("Maria foi ao Rio.", encoding="utf-8")
    mocker.patch("src.core.text.entities.is_available", return_value=False)

    with pytest.raises(SystemExit):
        _entities(_parse("entities", str(f)))
    assert "spacy download" in capsys.readouterr().out


# ── --cmd (NL->CLI, Fase 4) ───────────────────────────────────────────────────


@pytest.mark.unit
def test_cmd_flag_dispatches_to_nl2cli_runner(mocker):
    nl2cli_mock = mocker.patch("src.cli.ai._nl2cli")
    ask_mock = mocker.patch("src.cli.ai._ask")

    ns = _parse("corta o silêncio do podcast.mp3", "--cmd")
    ns.func(ns)

    nl2cli_mock.assert_called_once_with(ns)
    ask_mock.assert_not_called()


@pytest.mark.unit
def test_cmd_flag_overrides_keyword_flows():
    """--cmd short-circuits before the index/stats/dups/... keyword dispatch."""
    ns = _parse("stats", "--cmd")
    assert ns.query == "stats"
    assert ns.cmd is True


@pytest.mark.unit
def test_nl2cli_prints_command_and_explanation(mocker, capsys):
    from src.cli.ai import _nl2cli

    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=True),
    )
    mocker.patch("src.cli.reference.build_reference", return_value="REFERÊNCIA")
    mocker.patch(
        "src.core.text.nl2cli.to_command",
        return_value=(
            "uv run main.py audio podcast.mp3 --trim-silence --speed 1.25",
            "Corta o silêncio e acelera o áudio.",
        ),
    )
    log_mock = mocker.patch("src.core.observatory.activity.log_activity")

    _nl2cli(_parse("corta o silêncio do podcast.mp3 e acelera 1.25x", "--cmd"))

    out = capsys.readouterr().out
    assert "uv run main.py audio podcast.mp3 --trim-silence --speed 1.25" in out
    assert "Corta o silêncio e acelera o áudio." in out
    log_mock.assert_called_once_with(
        "rag", "nl2cli", "uv run main.py audio podcast.mp3 --trim-silence --speed 1.25"
    )


@pytest.mark.unit
def test_nl2cli_prints_refusal_without_a_command(mocker, capsys):
    from src.cli.ai import _nl2cli

    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=True),
    )
    mocker.patch("src.cli.reference.build_reference", return_value="REFERÊNCIA")
    mocker.patch(
        "src.core.text.nl2cli.to_command",
        return_value=("", "Isso não é uma tarefa da CLI do mill.tools."),
    )
    log_mock = mocker.patch("src.core.observatory.activity.log_activity")

    _nl2cli(_parse("qual a previsão do tempo?", "--cmd"))

    assert "não é uma tarefa" in capsys.readouterr().out
    log_mock.assert_not_called()


@pytest.mark.unit
def test_nl2cli_exits_when_ollama_unreachable_for_local_model(mocker, capsys):
    from src.cli.ai import _nl2cli

    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=False),
    )
    to_command_mock = mocker.patch("src.core.text.nl2cli.to_command")

    with pytest.raises(SystemExit):
        _nl2cli(_parse("corta o silêncio do podcast.mp3", "--cmd"))

    assert "ollama serve" in capsys.readouterr().out
    to_command_mock.assert_not_called()


@pytest.mark.unit
def test_nl2cli_skips_ollama_gate_for_cloud_model(mocker, capsys):
    from src.cli.ai import _nl2cli

    inventory_mock = mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=False),
    )
    mocker.patch("src.cli.reference.build_reference", return_value="REFERÊNCIA")
    mocker.patch(
        "src.core.text.nl2cli.to_command",
        return_value=("uv run main.py ai index", "ok"),
    )
    mocker.patch("src.core.observatory.activity.log_activity")

    _nl2cli(_parse("reindexa o acervo", "--cmd", "--model", "gemini-2.5-flash"))

    assert "uv run main.py ai index" in capsys.readouterr().out
    inventory_mock.assert_not_called()


@pytest.mark.unit
def test_nl2cli_exits_on_nl2cli_error(mocker, capsys):
    from src.cli.ai import _nl2cli
    from src.core.text.nl2cli import NL2CLIError

    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=True),
    )
    mocker.patch("src.cli.reference.build_reference", return_value="REFERÊNCIA")
    mocker.patch(
        "src.core.text.nl2cli.to_command",
        side_effect=NL2CLIError("não consegui gerar um comando válido"),
    )

    with pytest.raises(SystemExit):
        _nl2cli(_parse("corta o silêncio do podcast.mp3", "--cmd"))

    assert "não consegui gerar" in capsys.readouterr().out
