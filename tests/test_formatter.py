"""Unit tests for src/formatter.py."""

import pytest

pytestmark = pytest.mark.unit

_HEADER = """title:        Test Video
channel:      Test Channel
upload_date:  2024-01-15
duration:     00:02:05
language:     pt
url:          https://youtu.be/abc123
""" + ("-" * 64)


def _fake_llm(*responses: str):
    """Build a GenericFakeChatModel that yields the given responses in order."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


def _echo_llm():
    """A fake "LLM" that echoes its input chunk back verbatim.

    format_transcription's word-count-preservation guard (Fase 3 do
    PLANO_CORRECOES_SRC_RAIZ) rejects any output whose word count diverges
    from the input by more than 2% — a canned sentinel string like
    "chunk_n" would trip it for any body longer than a couple of words.
    Echoing the chunk trivially preserves word count for tests that only
    care about chunking/joining/header mechanics, not paragraph insertion.
    """
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    # FORMAT_PROMPT's human message is "{text}", so messages[-1].content is
    # exactly the chunk that was sent in.
    return RunnableLambda(lambda pv: AIMessage(content=pv.messages[-1].content))


# ── _split_for_format ────────────────────────────────────────────────────────


def test_split_for_format_short_text_single_chunk():
    from src.formatter import _split_for_format

    chunks = _split_for_format("Short transcription. Only one chunk.")
    assert chunks == ["Short transcription. Only one chunk."]


def test_split_for_format_long_text_multiple_chunks():
    from src.formatter import FORMAT_CHUNK_SIZE, _split_for_format

    long_text = "Sentence ends here. " * 1000  # ~20000 chars
    chunks = _split_for_format(long_text)
    assert len(chunks) > 1
    assert all(len(c) <= FORMAT_CHUNK_SIZE for c in chunks)


# ── format_transcription ─────────────────────────────────────────────────────


def test_format_transcription_missing_file_raises(tmp_path):
    from src.formatter import format_transcription

    with pytest.raises(FileNotFoundError):
        format_transcription(tmp_path / "missing.txt")


def test_format_transcription_empty_body_returns_none(tmp_path, mocker):
    from src import formatter

    mocker.patch.object(formatter, "make_llm")  # never called
    src = tmp_path / "empty.txt"
    src.write_text(_HEADER + "\n   \n", encoding="utf-8")
    result = formatter.format_transcription(src)
    assert result is None


def test_format_transcription_single_chunk_writes_back(tmp_path, mocker):
    from src import formatter

    src = tmp_path / "t.txt"
    src.write_text(_HEADER + "\n\nfrase um. frase dois. frase tres.", encoding="utf-8")
    mocker.patch.object(
        formatter,
        "make_llm",
        return_value=_fake_llm("frase um.\n\nfrase dois.\n\nfrase tres."),
    )
    out = formatter.format_transcription(src)
    assert out is not None
    assert "frase um." in out
    written = src.read_text(encoding="utf-8")
    assert "title:" in written  # header preserved
    assert "frase dois." in written


def test_format_transcription_handles_list_content_gemini_shape(tmp_path, mocker):
    """Gemini/GLM can return .content as a list of blocks — must route through
    extract_llm_text instead of AttributeError'ing on .content.strip()
    (Fase 1 do PLANO_CORRECOES_SRC_RAIZ)."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from src import formatter

    src = tmp_path / "t.txt"
    src.write_text(_HEADER + "\n\nhello world.", encoding="utf-8")
    fake = GenericFakeChatModel(
        messages=iter([AIMessage(content=[{"text": "hello world."}])])
    )
    mocker.patch.object(formatter, "make_llm", return_value=fake)
    out = formatter.format_transcription(src)
    assert out == "hello world."


def test_format_transcription_strips_response_whitespace(tmp_path, mocker):
    from src import formatter

    src = tmp_path / "t.txt"
    src.write_text(_HEADER + "\n\nhello world.", encoding="utf-8")
    # LLM returns surrounding whitespace — formatter should strip
    mocker.patch.object(
        formatter,
        "make_llm",
        return_value=_fake_llm("   \n\nhello world.\n\n   "),
    )
    out = formatter.format_transcription(src)
    assert out.startswith("hello world.")
    assert not out.endswith("   ")


def test_format_transcription_ignores_separator_look_alike_deep_in_body(
    tmp_path, mocker
):
    """Fase 2 do PLANO_CORRECOES_SRC_RAIZ: formatter agora usa a mesma janela
    de busca do analyzer. Antes (busca sem janela), um run de 64 traços no
    meio de um corpo sem header real era tratado como separador — o texto
    ANTES dele virava "header" e sobrevivia intocado no arquivo reescrito,
    e só o restinho depois dele era enviado ao LLM. Com a janela, tudo é
    corpo: nada do texto original sobrevive intocado (o LLM reescreve tudo)."""
    from src import formatter

    sep = "-" * 64
    body_before = "Paragrafo real com conteudo. " * 200
    src = tmp_path / "t.txt"
    src.write_text(f"{body_before}\n{sep}\nMais texto depois.", encoding="utf-8")
    mocker.patch.object(formatter, "make_llm", return_value=_echo_llm())
    formatter.format_transcription(src)
    written = src.read_text(encoding="utf-8")
    # Nothing before the look-alike separator was dropped as a fake "header".
    assert "Paragrafo real com conteudo." in written
    assert "Mais texto depois." in written


def test_format_transcription_no_header_just_body(tmp_path, mocker):
    from src import formatter

    src = tmp_path / "t.txt"
    src.write_text("just body without separator", encoding="utf-8")
    mocker.patch.object(formatter, "make_llm", return_value=_echo_llm())
    out = formatter.format_transcription(src)
    written = src.read_text(encoding="utf-8")
    assert out == "just body without separator"
    assert "----" not in written  # nenhum separator inventado


def test_format_transcription_empty_llm_response_keeps_body(tmp_path, mocker):
    from src import formatter

    src = tmp_path / "t.txt"
    body = "original body content."
    src.write_text(_HEADER + "\n\n" + body, encoding="utf-8")
    mocker.patch.object(
        formatter,
        "make_llm",
        return_value=_fake_llm("", ""),  # first attempt + retry, both empty
    )
    out = formatter.format_transcription(src)
    # Both attempts empty → _format_chunk falls back to the original chunk.
    assert out == body


def test_format_transcription_chunk_word_count_mismatch_keeps_original_chunk(
    tmp_path, mocker
):
    """A chunk whose formatted output diverges too much in word count from
    the input (e.g. the model summarized instead of just adding blank lines)
    falls back to the original chunk instead of gluing mangled text into the
    reassembled body (Fase 3 do PLANO_CORRECOES_SRC_RAIZ)."""
    from src import formatter

    src = tmp_path / "t.txt"
    body = "Uma frase inteira com bastante conteudo relevante para preservar aqui."
    src.write_text(_HEADER + "\n\n" + body, encoding="utf-8")
    mocker.patch.object(
        formatter,
        "make_llm",
        return_value=_fake_llm("resumo curto"),  # far fewer words than the input
    )
    out = formatter.format_transcription(src)
    assert out == body


def test_format_transcription_emits_lifecycle_events(tmp_path, mocker):
    from src import formatter

    src = tmp_path / "t.txt"
    src.write_text(_HEADER + "\n\nhello.", encoding="utf-8")
    mocker.patch.object(formatter, "make_llm", return_value=_fake_llm("hello."))

    events: list[tuple[str, str, dict]] = []
    formatter.format_transcription(
        src, on_event=lambda t, s, p: events.append((t, s, p))
    )

    types = [e[0] for e in events]
    assert "format_started" in types
    assert "format_chunk_start" in types
    assert "format_chunk_done" in types
    assert "format_done" in types
    # stage sempre "format"
    assert all(stage == "format" for _, stage, _ in events)


def test_format_transcription_multiple_chunks_joined_with_blank_line(tmp_path, mocker):
    from src import formatter

    from src.formatter import _split_for_format

    src = tmp_path / "t.txt"
    # Build a body large enough to require >1 chunks
    long_body = "Sentence ends here. " * 500  # ~10000 chars > 4500
    src.write_text(_HEADER + "\n\n" + long_body, encoding="utf-8")
    mocker.patch.object(formatter, "make_llm", return_value=_echo_llm())
    out = formatter.format_transcription(src)
    # Multiple chunks → joined with \n\n, each chunk echoed back unchanged.
    assert out == "\n\n".join(_split_for_format(long_body))
    assert out.count("\n\n") >= 1
