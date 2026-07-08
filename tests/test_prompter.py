"""Unit tests for src/prompter.py."""

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


@pytest.fixture
def isolate_digest_dir(tmp_path, monkeypatch):
    """Redirect TRANSCRIPTIONS_DIGEST_DIR to tmp_path to avoid polluting output/."""
    import src.prompter as mod

    target = tmp_path / "digest"
    monkeypatch.setattr(mod, "TRANSCRIPTIONS_DIGEST_DIR", target)
    return target


# ── _extract_body_and_meta ───────────────────────────────────────────────────


def test_extract_body_and_meta_with_header():
    from src.prompter import _extract_body_and_meta

    text = _HEADER + "\n\nThis is the body."
    body, meta = _extract_body_and_meta(text)
    assert body == "This is the body."
    assert meta["title"] == "Test Video"
    assert meta["channel"] == "Test Channel"
    assert meta["url"] == "https://youtu.be/abc123"


def test_extract_body_and_meta_no_header():
    from src.prompter import _extract_body_and_meta

    body, meta = _extract_body_and_meta("Only body, no header.")
    assert body == "Only body, no header."
    assert meta == {}


def test_extract_body_and_meta_ignores_lines_without_colon():
    from src.prompter import _extract_body_and_meta

    text = (
        "title: T\nrandom line without colon\nurl: https://x\n" + ("-" * 64) + "\nbody"
    )
    _, meta = _extract_body_and_meta(text)
    assert meta == {"title": "T", "url": "https://x"}


def test_extract_body_and_meta_empty_keys_or_values_are_skipped():
    from src.prompter import _extract_body_and_meta

    text = "title: \n: orphan_value\nurl: https://x\n" + ("-" * 64) + "\nbody"
    _, meta = _extract_body_and_meta(text)
    assert meta == {"url": "https://x"}


# ── _split_for_prompt ────────────────────────────────────────────────────────


def test_split_for_prompt_short_text_single_chunk():
    from src.prompter import _split_for_prompt

    chunks = _split_for_prompt("Short text.", model_name="qwen7b-custom")
    assert chunks == ["Short text."]


def test_split_for_prompt_long_ollama_text_multiple_chunks():
    from src.prompter import PROMPT_CHUNK_SIZE, _split_for_prompt

    long_text = "Sentence ends here. " * 1000  # ~20000 chars
    chunks = _split_for_prompt(long_text, model_name="qwen7b-custom")
    assert len(chunks) > 1
    assert all(len(c) <= PROMPT_CHUNK_SIZE for c in chunks)


def test_split_for_prompt_gemini_bypasses_chunking():
    from src.prompter import _split_for_prompt

    long_text = "Sentence ends here. " * 1000  # ~20000 chars
    chunks = _split_for_prompt(long_text, model_name="gemini-2.5-flash")
    # Gemini → single chunk regardless of size (bypass_long_context=True)
    assert chunks == [long_text]


# ── build_prompt_ready ───────────────────────────────────────────────────────


def test_build_prompt_ready_missing_file_raises(tmp_path):
    from src.prompter import build_prompt_ready

    with pytest.raises(FileNotFoundError):
        build_prompt_ready(tmp_path / "missing.txt")


def test_build_prompt_ready_empty_body_returns_input_path(
    tmp_path, mocker, isolate_digest_dir
):
    from src import prompter

    mocker.patch.object(prompter, "make_llm")  # never called
    src = tmp_path / "empty.txt"
    src.write_text(_HEADER + "\n   \n", encoding="utf-8")
    result = prompter.build_prompt_ready(src)
    assert result == src
    # nothing written to digest dir
    assert not isolate_digest_dir.exists() or not any(isolate_digest_dir.iterdir())


def test_build_prompt_ready_single_chunk_writes_output(
    tmp_path, mocker, isolate_digest_dir
):
    from src import prompter

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nbody to condense.", encoding="utf-8")
    mocker.patch.object(
        prompter,
        "make_llm",
        return_value=_fake_llm("condensed body."),
    )
    out = prompter.build_prompt_ready(src)
    content = out.read_text(encoding="utf-8")
    assert "condensed body." in content
    # Header includes title + URL + duration from metadata
    assert "Test Video" in content
    assert "https://youtu.be/abc123" in content
    assert "00:02:05" in content


def test_build_prompt_ready_handles_list_content_gemini_shape(
    tmp_path, mocker, isolate_digest_dir
):
    """Gemini/GLM can return .content as a list of blocks — must route through
    extract_llm_text instead of AttributeError'ing on .content.strip()
    (Fase 1 do PLANO_CORRECOES_SRC_RAIZ)."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from src import prompter

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nshort body.", encoding="utf-8")
    fake = GenericFakeChatModel(
        messages=iter([AIMessage(content=[{"text": "condensed body."}])])
    )
    mocker.patch.object(prompter, "make_llm", return_value=fake)
    out = prompter.build_prompt_ready(src)
    assert "condensed body." in out.read_text(encoding="utf-8")


def test_build_prompt_ready_single_chunk_skips_merge(
    tmp_path, mocker, isolate_digest_dir
):
    """When only 1 chunk, MERGE_CONDENSE_PROMPT must NOT be invoked."""
    from src import prompter

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nshort body.", encoding="utf-8")
    fake = _fake_llm(
        "condensed body."
    )  # only 1 response — extra calls would StopIteration
    mocker.patch.object(prompter, "make_llm", return_value=fake)
    out = prompter.build_prompt_ready(src)
    assert "condensed body." in out.read_text(encoding="utf-8")


def test_build_prompt_ready_multiple_chunks_calls_merge(
    tmp_path, mocker, isolate_digest_dir
):
    from src import prompter

    src = tmp_path / "video.txt"
    # Force >1 chunks. Use long sentences with rare boundaries to ensure split.
    long_body = (
        "This is a relatively long sentence about a topic. " * 200
    )  # ~10000 chars
    # Verify in-test that this actually produces >1 chunks
    chunks = prompter._split_for_prompt(long_body, "qwen7b-custom")
    assert len(chunks) > 1, f"Test precondition failed: only {len(chunks)} chunks"
    src.write_text(_HEADER + "\n\n" + long_body, encoding="utf-8")
    # Enough responses for N chunk condensations + 1 final merge
    mocker.patch.object(
        prompter,
        "make_llm",
        return_value=_fake_llm(*["condensed chunk"] * len(chunks), "MERGED_FINAL_BODY"),
    )
    # pin a chunking model: the default (gemma3-4b) bypasses chunking for inputs
    # this size, which would skip the merge path this test exercises.
    out = prompter.build_prompt_ready(src, model_name="qwen7b-custom")
    # The output should be the MERGED result, not a concatenation
    assert "MERGED_FINAL_BODY" in out.read_text(encoding="utf-8")


def test_build_prompt_ready_no_header_uses_stem_as_title(
    tmp_path, mocker, isolate_digest_dir
):
    from src import prompter

    src = tmp_path / "my_video.txt"
    src.write_text("body without header", encoding="utf-8")
    mocker.patch.object(prompter, "make_llm", return_value=_fake_llm("condensed."))
    out = prompter.build_prompt_ready(src)
    content = out.read_text(encoding="utf-8")
    assert "# my_video" in content  # title falls back to stem
    assert "# Fonte:" not in content  # no URL in header → no Fonte line
    assert "# Duração:" not in content  # no duration


def test_build_prompt_ready_emits_lifecycle_events(
    tmp_path, mocker, isolate_digest_dir
):
    from src import prompter

    src = tmp_path / "video.txt"
    src.write_text(_HEADER + "\n\nshort body.", encoding="utf-8")
    mocker.patch.object(prompter, "make_llm", return_value=_fake_llm("condensed."))

    events: list[tuple[str, str, dict]] = []
    prompter.build_prompt_ready(src, on_event=lambda t, s, p: events.append((t, s, p)))

    types = [e[0] for e in events]
    assert "prompt_started" in types
    assert "prompt_chunk_start" in types
    assert "prompt_chunk_done" in types
    assert "prompt_done" in types
    assert all(stage == "prompt" for _, stage, _ in events)


def test_build_prompt_ready_output_filename_matches_input(
    tmp_path, mocker, isolate_digest_dir
):
    from src import prompter

    src = tmp_path / "abc_xyz.txt"
    src.write_text(_HEADER + "\n\nbody.", encoding="utf-8")
    mocker.patch.object(prompter, "make_llm", return_value=_fake_llm("c."))
    out = prompter.build_prompt_ready(src)
    assert out.name == "abc_xyz.txt"
    assert out.parent == isolate_digest_dir
