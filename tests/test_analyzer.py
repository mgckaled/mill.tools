"""Unit tests for src/analyzer.py."""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_HEADER = """title:        Test Video
channel:      Test Channel
upload_date:  2024-01-15
duration:     00:02:05
language:     pt
url:          https://youtu.be/abc123
""" + ("-" * 64)


_VALID_ANALYSIS = {
    "summary": "Resumo do conteúdo do vídeo em algumas frases.",
    "key_points": ["Ponto um sobre o tema.", "Ponto dois com mais detalhes."],
    "action_items": ["Fazer X.", "Configurar Y."],
    "key_concepts": ["Conceito A: definição curta."],
    "tools_mentioned": ["python", "pytest"],
    "metrics": ["100 testes em 2s"],
    "quotes": ["O importante é continuar."],
    "assumptions": ["O leitor conhece Python."],
    "vocabulary": ["fixture: contexto reutilizável."],
    "sentiment_arc": "Início introdutório → aprofundamento técnico → conclusão.",
}


def _fake_llm(*responses: str):
    """Build a GenericFakeChatModel that yields the given responses in order."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


@pytest.fixture
def isolate_analysis_dir(tmp_path, monkeypatch):
    """Redirect TRANSCRIPTIONS_ANALYSIS_DIR to tmp_path."""
    import src.analyzer as mod

    target = tmp_path / "analysis"
    monkeypatch.setattr(mod, "TRANSCRIPTIONS_ANALYSIS_DIR", target)
    return target


# ── _parse_json_response ─────────────────────────────────────────────────────


def test_parse_json_response_plain():
    from src.analyzer import _parse_json_response

    out = _parse_json_response('{"summary": "ok", "key_points": []}')
    assert out["summary"] == "ok"
    assert out["key_points"] == []


def test_parse_json_response_with_markdown_fence():
    from src.analyzer import _parse_json_response

    text = '```json\n{"summary": "ok"}\n```'
    out = _parse_json_response(text)
    assert out["summary"] == "ok"


def test_parse_json_response_with_generic_fence():
    from src.analyzer import _parse_json_response

    text = '```\n{"key": "value"}\n```'
    assert _parse_json_response(text) == {"key": "value"}


def test_parse_json_response_strips_surrounding_whitespace():
    from src.analyzer import _parse_json_response

    text = '\n\n   {"k": 1}   \n'
    assert _parse_json_response(text) == {"k": 1}


def test_parse_json_response_invalid_json_raises():
    from src.analyzer import _parse_json_response

    with pytest.raises(ValueError, match="valid JSON"):
        _parse_json_response("not json at all {{")


def test_parse_json_response_fenced_invalid_json_raises():
    from src.analyzer import _parse_json_response

    with pytest.raises(ValueError):
        _parse_json_response("```json\n{invalid}\n```")


def test_parse_json_response_unclosed_fence_still_parses():
    """Opening fence without closing ``` — parser strips only the opening."""
    from src.analyzer import _parse_json_response

    out = _parse_json_response('```json\n{"k": 1}')
    assert out == {"k": 1}


# ── _invoke_and_parse (retry on malformed/truncated JSON) ─────────────────────


class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChain:
    """Stand-in for a `prompt | llm` runnable yielding canned contents in order."""

    def __init__(self, *contents: str) -> None:
        self._it = iter(contents)
        self.calls = 0

    def invoke(self, _payload: dict) -> "_FakeMsg":
        self.calls += 1
        return _FakeMsg(next(self._it))


def test_invoke_and_parse_succeeds_first_try():
    from src.analyzer import _invoke_and_parse

    chain = _FakeChain('{"summary": "ok"}')
    assert _invoke_and_parse(chain, {"text": "x"}) == {"summary": "ok"}
    assert chain.calls == 1  # no retry consumed


def test_invoke_and_parse_retries_then_succeeds():
    from src.analyzer import _invoke_and_parse

    # truncated/invalid JSON on the first attempt, valid on the retry
    chain = _FakeChain('{"summary": "tru', '{"summary": "ok"}')
    assert _invoke_and_parse(chain, {"text": "x"}) == {"summary": "ok"}
    assert chain.calls == 2


def test_invoke_and_parse_raises_after_exhausting_retries():
    from src.analyzer import _invoke_and_parse

    chain = _FakeChain("not json {{", "still not json")
    with pytest.raises(ValueError, match="valid JSON"):
        _invoke_and_parse(chain, {"text": "x"})
    assert chain.calls == 2


# ── _extract_transcription_body ──────────────────────────────────────────────


def test_extract_transcription_body_with_separator():
    from src.analyzer import _extract_transcription_body

    text = _HEADER + "\n\nThis is the body."
    assert _extract_transcription_body(text) == "This is the body."


def test_extract_transcription_body_no_separator():
    from src.analyzer import _extract_transcription_body

    assert _extract_transcription_body("just body") == "just body"


# ── _parse_header ────────────────────────────────────────────────────────────


def test_parse_header_extracts_fields():
    from src.analyzer import _parse_header

    meta = _parse_header(_HEADER + "\nbody")
    assert meta["title"] == "Test Video"
    assert meta["channel"] == "Test Channel"
    assert meta["url"] == "https://youtu.be/abc123"


def test_parse_header_no_separator_returns_empty():
    from src.analyzer import _parse_header

    assert _parse_header("no separator here") == {}


def test_parse_header_skips_lines_without_colon():
    from src.analyzer import _parse_header

    text = "title: T\nnocolon line\nurl: https://x\n" + ("-" * 64) + "\nbody"
    meta = _parse_header(text)
    assert meta == {"title": "T", "url": "https://x"}


# ── _split_text ──────────────────────────────────────────────────────────────


def test_split_text_short_single_chunk():
    from src.analyzer import _split_text

    assert _split_text("Short text.", "qwen7b-custom") == ["Short text."]


def test_split_text_gemini_bypasses_chunking():
    from src.analyzer import _split_text

    long_text = "This is a long sentence about a topic. " * 1000  # ~40000 chars
    chunks = _split_text(long_text, "gemini-2.5-flash")
    assert chunks == [long_text]


def test_split_text_ollama_splits_long_text():
    from src.analyzer import CHUNK_SIZE, _split_text

    long_text = "This is a relatively long sentence. " * 500
    chunks = _split_text(long_text, "qwen7b-custom")
    assert len(chunks) > 1
    assert all(len(c) <= CHUNK_SIZE for c in chunks)


# ── _format_report ───────────────────────────────────────────────────────────


def test_format_report_with_full_analysis():
    from src.analyzer import _format_report

    out = _format_report(
        _VALID_ANALYSIS,
        source_path=Path("transcricao.txt"),
        video_meta={
            "title": "X",
            "channel": "Y",
            "duration": "01:00:00",
            "url": "https://yt/x",
        },
    )
    assert "# X" in out
    assert "**Canal:** Y" in out
    assert "**Duração:** 01:00:00" in out
    assert "[Assistir no YouTube](https://yt/x)" in out
    assert "## Resumo" in out
    assert _VALID_ANALYSIS["summary"] in out
    assert "## Pontos-chave" in out
    assert "## Ações sugeridas" in out
    assert "## Conceitos-chave" in out
    assert "## Ferramentas mencionadas" in out
    assert "## Métricas e números" in out
    assert "## Citações notáveis" in out
    assert "## Premissas implícitas" in out
    assert "## Vocabulário do nicho" in out
    assert "## Arco de sentimento" in out


def test_format_report_falls_back_to_stem_when_no_title():
    from src.analyzer import _format_report

    out = _format_report({"summary": "s"}, source_path=Path("meu_video.txt"))
    assert "# Análise: meu_video" in out


def test_format_report_no_actions_shows_placeholder():
    from src.analyzer import _format_report

    out = _format_report(
        {"summary": "s", "action_items": []}, source_path=Path("t.txt")
    )
    assert "Nenhuma ação identificada." in out


def test_format_report_omits_empty_optional_sections():
    from src.analyzer import _format_report

    minimal = {"summary": "S", "key_points": ["k1"]}
    out = _format_report(minimal, source_path=Path("t.txt"))
    # Optional sections must not appear when their list is empty/missing
    assert "## Conceitos-chave" not in out
    assert "## Ferramentas mencionadas" not in out
    assert "## Métricas" not in out
    assert "## Citações" not in out
    assert "## Premissas" not in out
    assert "## Vocabulário" not in out
    assert "## Arco de sentimento" not in out


def test_format_report_appends_transcription_when_provided():
    from src.analyzer import _format_report

    out = _format_report(
        {"summary": "S"},
        source_path=Path("t.txt"),
        transcription="FULL BODY TEXT HERE",
    )
    assert "## Transcrição" in out
    assert "FULL BODY TEXT HERE" in out


def test_format_report_meta_without_channel_or_duration_no_pipe_line():
    from src.analyzer import _format_report

    out = _format_report(
        {"summary": "S"}, source_path=Path("t.txt"), video_meta={"url": "https://yt/x"}
    )
    assert "**Canal:**" not in out
    assert "[Assistir" in out


# ── _ensure_portuguese ───────────────────────────────────────────────────────


def test_ensure_portuguese_already_pt_returns_same():
    from src.analyzer import _ensure_portuguese

    llm = _fake_llm("pt")  # detect → 'pt' → returns input as-is
    out = _ensure_portuguese(_VALID_ANALYSIS, llm)
    assert out == _VALID_ANALYSIS


def test_ensure_portuguese_other_language_triggers_translation():
    from src.analyzer import _ensure_portuguese

    translated = dict(_VALID_ANALYSIS, summary="Traduzido para PT-BR.")
    llm = _fake_llm("en", json.dumps(translated, ensure_ascii=False))
    out = _ensure_portuguese(_VALID_ANALYSIS, llm)
    assert out["summary"] == "Traduzido para PT-BR."


def test_ensure_portuguese_empty_summary_skips_detection():
    from src.analyzer import _ensure_portuguese

    # If summary empty, returns immediately without invoking LLM
    llm = _fake_llm()  # zero responses — would StopIteration on any call
    out = _ensure_portuguese({"summary": ""}, llm)
    assert out == {"summary": ""}


def test_ensure_portuguese_emits_language_detected_event():
    from src.analyzer import _ensure_portuguese

    events: list[tuple[str, str, dict]] = []
    llm = _fake_llm("pt")
    _ensure_portuguese(
        _VALID_ANALYSIS, llm, on_event=lambda t, s, p: events.append((t, s, p))
    )
    types = [e[0] for e in events]
    assert "language_detected" in types
    # The payload should expose the detected lang
    payload = next(p for t, _, p in events if t == "language_detected")
    assert payload["lang"] == "pt"


def test_ensure_portuguese_translation_emits_start_done_events():
    from src.analyzer import _ensure_portuguese

    translated = dict(_VALID_ANALYSIS, summary="Trad.")
    llm = _fake_llm("es", json.dumps(translated, ensure_ascii=False))
    events: list[tuple[str, str, dict]] = []
    _ensure_portuguese(
        _VALID_ANALYSIS, llm, on_event=lambda t, s, p: events.append((t, s, p))
    )
    types = [e[0] for e in events]
    assert "translation_start" in types
    assert "translation_done" in types


# ── analyze (orquestrador) ───────────────────────────────────────────────────


def test_analyze_missing_file_raises(tmp_path):
    from src.analyzer import analyze

    with pytest.raises(FileNotFoundError):
        analyze(tmp_path / "missing.txt")


def test_analyze_empty_body_raises_value_error(tmp_path, isolate_analysis_dir):
    from src.analyzer import analyze

    src = tmp_path / "empty.txt"
    src.write_text(_HEADER + "\n   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="vazio"):
        analyze(src)


def test_analyze_single_chunk_writes_report(tmp_path, mocker, isolate_analysis_dir):
    from src import analyzer

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nshort body.", encoding="utf-8")
    # Single chunk path → 1 analysis call + 1 detect_language call (returns 'pt')
    mocker.patch.object(
        analyzer,
        "make_llm",
        side_effect=[
            _fake_llm(
                json.dumps(_VALID_ANALYSIS, ensure_ascii=False)
            ),  # llm (analysis)
            _fake_llm("pt"),  # llm_util (detection)
        ],
    )
    out = analyzer.analyze(src)
    assert out.exists()
    assert out.suffix == ".md"
    content = out.read_text(encoding="utf-8")
    assert _VALID_ANALYSIS["summary"] in content
    assert "## Pontos-chave" in content


def test_analyze_with_profile_renders_profile_sections(
    tmp_path, mocker, isolate_analysis_dir
):
    """A non-default profile drives the schema and the report section titles."""
    from src import analyzer

    src = tmp_path / "aula.txt"
    src.write_text(_HEADER + "\n\nshort body.", encoding="utf-8")
    lecture_analysis = {
        "summary": "Resumo da aula.",
        "learning_objectives": ["Compreender o tema."],
        "key_concepts": ["Termo: definição."],
    }
    mocker.patch.object(
        analyzer,
        "make_llm",
        side_effect=[
            _fake_llm(
                json.dumps(lecture_analysis, ensure_ascii=False)
            ),  # llm (analysis)
            _fake_llm("pt"),  # llm_util (detection)
        ],
    )
    out = analyzer.analyze(src, profile="lecture")
    content = out.read_text(encoding="utf-8")
    assert "## Objetivos de aprendizagem" in content
    assert "- Compreender o tema." in content
    # default-only sections must NOT leak into the lecture report
    assert "## Arco de sentimento" not in content


def test_analyze_unknown_profile_falls_back_to_default(
    tmp_path, mocker, isolate_analysis_dir
):
    from src import analyzer

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nshort body.", encoding="utf-8")
    mocker.patch.object(
        analyzer,
        "make_llm",
        side_effect=[
            _fake_llm(json.dumps(_VALID_ANALYSIS, ensure_ascii=False)),
            _fake_llm("pt"),
        ],
    )
    out = analyzer.analyze(src, profile="does-not-exist")
    content = out.read_text(encoding="utf-8")
    assert "## Arco de sentimento" in content  # default schema


def test_analyze_single_chunk_with_transcription_appends_section(
    tmp_path, mocker, isolate_analysis_dir
):
    from src import analyzer

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nshort body.", encoding="utf-8")
    mocker.patch.object(
        analyzer,
        "make_llm",
        side_effect=[
            _fake_llm(json.dumps(_VALID_ANALYSIS, ensure_ascii=False)),
            _fake_llm("pt"),
        ],
    )
    out = analyzer.analyze(src, transcription="TRANSCRIPTION_BODY")
    content = out.read_text(encoding="utf-8")
    assert "## Transcrição" in content
    assert "TRANSCRIPTION_BODY" in content


def test_analyze_multi_chunk_calls_merge(tmp_path, mocker, isolate_analysis_dir):
    from src import analyzer

    src = tmp_path / "video.txt"
    long_body = "This is a relatively long sentence about a topic. " * 200
    chunks = analyzer._split_text(long_body, "qwen7b-custom")
    assert len(chunks) > 1, f"Test precondition failed: {len(chunks)} chunks"
    src.write_text(_HEADER + "\n\n" + long_body, encoding="utf-8")

    partial = {**_VALID_ANALYSIS, "summary": "partial."}
    merged = {**_VALID_ANALYSIS, "summary": "MERGED RESULT"}

    # llm: N partial analyses + 1 merge call. llm_util: 1 detect call.
    mocker.patch.object(
        analyzer,
        "make_llm",
        side_effect=[
            _fake_llm(
                *([json.dumps(partial, ensure_ascii=False)] * len(chunks)),
                json.dumps(merged, ensure_ascii=False),
            ),
            _fake_llm("pt"),
        ],
    )
    out = analyzer.analyze(src)
    assert "MERGED RESULT" in out.read_text(encoding="utf-8")


def test_analyze_emits_lifecycle_events(tmp_path, mocker, isolate_analysis_dir):
    from src import analyzer

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nbody.", encoding="utf-8")
    mocker.patch.object(
        analyzer,
        "make_llm",
        side_effect=[
            _fake_llm(json.dumps(_VALID_ANALYSIS, ensure_ascii=False)),
            _fake_llm("pt"),
        ],
    )
    events: list[tuple[str, str, dict]] = []
    analyzer.analyze(src, on_event=lambda t, s, p: events.append((t, s, p)))
    types = [e[0] for e in events]
    assert "analyze_started" in types
    assert "analyze_chunk_start" in types
    assert "analyze_chunk_done" in types
    assert "analyze_done" in types
    assert all(stage == "analyze" for _, stage, _ in events)


def test_analyze_multi_chunk_emits_merge_event(tmp_path, mocker, isolate_analysis_dir):
    from src import analyzer

    src = tmp_path / "video.txt"
    long_body = "This is a relatively long sentence about a topic. " * 200
    chunks = analyzer._split_text(long_body, "qwen7b-custom")
    assert len(chunks) > 1
    src.write_text(_HEADER + "\n\n" + long_body, encoding="utf-8")
    partial = {**_VALID_ANALYSIS, "summary": "p."}
    mocker.patch.object(
        analyzer,
        "make_llm",
        side_effect=[
            _fake_llm(
                *([json.dumps(partial, ensure_ascii=False)] * len(chunks)),
                json.dumps(_VALID_ANALYSIS, ensure_ascii=False),
            ),
            _fake_llm("pt"),
        ],
    )
    events: list[tuple[str, str, dict]] = []
    analyzer.analyze(src, on_event=lambda t, s, p: events.append((t, s, p)))
    assert "analyze_merge_start" in [e[0] for e in events]


# ── main (standalone CLI) ────────────────────────────────────────────────────


def test_main_invokes_analyze_with_parsed_args(tmp_path, mocker, isolate_analysis_dir):
    from src import analyzer

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nbody.", encoding="utf-8")

    mock_analyze = mocker.patch.object(analyzer, "analyze")
    mocker.patch("sys.argv", ["yt-analyzer", str(src), "--model", "qwen7b-custom"])
    analyzer.main()

    mock_analyze.assert_called_once()
    args, kwargs = mock_analyze.call_args
    assert args[0] == Path(str(src))
    assert kwargs["model_name"] == "qwen7b-custom"


def test_main_default_model_when_not_provided(tmp_path, mocker, isolate_analysis_dir):
    from src import analyzer

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nbody.", encoding="utf-8")

    mock_analyze = mocker.patch.object(analyzer, "analyze")
    mocker.patch("sys.argv", ["yt-analyzer", str(src)])
    analyzer.main()

    assert mock_analyze.call_args.kwargs["model_name"] == analyzer.DEFAULT_MODEL


def test_analyze_translates_when_non_pt(tmp_path, mocker, isolate_analysis_dir):
    from src import analyzer

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nbody.", encoding="utf-8")
    translated = {**_VALID_ANALYSIS, "summary": "Versão PT-BR."}
    mocker.patch.object(
        analyzer,
        "make_llm",
        side_effect=[
            _fake_llm(json.dumps(_VALID_ANALYSIS, ensure_ascii=False)),
            _fake_llm("en", json.dumps(translated, ensure_ascii=False)),
        ],
    )
    out = analyzer.analyze(src)
    assert "Versão PT-BR." in out.read_text(encoding="utf-8")
