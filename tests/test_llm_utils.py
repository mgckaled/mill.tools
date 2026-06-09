"""Unit tests for src/llm_utils.split_text."""
import pytest


@pytest.mark.unit
def test_split_text_short_returns_single_chunk():
    from src.llm_utils import split_text

    result = split_text("hello world", chunk_size=100, chunk_overlap=0)
    assert result == ["hello world"]


@pytest.mark.unit
def test_split_text_long_produces_multiple_chunks():
    from src.llm_utils import split_text

    text = "word " * 200  # 1000 chars
    chunks = split_text(text, chunk_size=200, chunk_overlap=0)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 200


@pytest.mark.unit
def test_split_text_gemini_bypass_returns_single_chunk(mocker):
    from src.llm_utils import split_text

    mocker.patch("src.llm_utils.is_gemini_model", return_value=True)
    text = "x" * 10_000
    result = split_text(
        text, chunk_size=100, chunk_overlap=0,
        model_name="gemini-2.5-flash", bypass_long_context=True,
    )
    assert result == [text]


@pytest.mark.unit
def test_split_text_gemini_without_bypass_still_splits(mocker):
    from src.llm_utils import split_text

    mocker.patch("src.llm_utils.is_gemini_model", return_value=True)
    text = "word " * 200
    chunks = split_text(
        text, chunk_size=200, chunk_overlap=0,
        model_name="gemini-2.5-flash", bypass_long_context=False,
    )
    assert len(chunks) > 1


@pytest.mark.unit
def test_split_text_ollama_bypass_true_still_splits(mocker):
    from src.llm_utils import split_text

    mocker.patch("src.llm_utils.is_gemini_model", return_value=False)
    text = "word " * 200
    chunks = split_text(
        text, chunk_size=200, chunk_overlap=0,
        model_name="qwen7b-custom", bypass_long_context=True,
    )
    assert len(chunks) > 1


@pytest.mark.unit
def test_split_text_custom_separators_respected():
    from src.llm_utils import split_text

    # Sentence-boundary separators (formatter pattern)
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    chunks = split_text(
        text, chunk_size=40, chunk_overlap=0,
        separators=[". ", " ", ""],
    )
    assert len(chunks) > 1
    # Each chunk should end after a sentence boundary when possible
    for chunk in chunks:
        assert len(chunk) <= 40


@pytest.mark.unit
def test_split_text_no_model_name_no_bypass():
    from src.llm_utils import split_text

    text = "word " * 200
    chunks = split_text(text, chunk_size=200, chunk_overlap=0)
    assert len(chunks) > 1
