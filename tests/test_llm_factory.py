import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "model, expected",
    [
        ("gemini-2.5-flash", True),
        ("gemini-1.5-pro", True),
        ("GEMINI-test", True),
        ("qwen7b-custom", False),
        ("phi4mini-custom", False),
        ("ollama-model", False),
        ("", False),
    ],
)
def test_is_gemini(model, expected):
    from src.llm_factory import is_gemini_model

    assert is_gemini_model(model) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "model, expected",
    [
        ("gemma3-4b-custom", 12_000),
        ("qwen7b-custom", None),
        ("gemini-2.5-flash", None),  # Gemini bypasses unconditionally, not via budget
        ("unknown-model", None),
    ],
)
def test_long_context_char_budget(model, expected):
    from src.llm_factory import long_context_char_budget

    assert long_context_char_budget(model) == expected


@pytest.mark.unit
def test_make_llm_gemini_raises_without_api_key(monkeypatch):
    """make_llm para gemini sem GOOGLE_API_KEY deve lançar RuntimeError."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("src.llm_factory.load_dotenv", lambda *a, **kw: None)
    from src.llm_factory import make_llm

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        make_llm("gemini-2.5-flash")


@pytest.mark.unit
def test_make_llm_routes_ollama(mocker):
    """make_llm para nome sem prefixo 'gemini' deve instanciar ChatOllama."""
    mock_ollama = mocker.patch("src.llm_factory._make_ollama")
    from src.llm_factory import DEFAULT_OLLAMA_NUM_CTX, make_llm

    make_llm("qwen7b-custom", temperature=0.4)
    mock_ollama.assert_called_once_with("qwen7b-custom", 0.4, DEFAULT_OLLAMA_NUM_CTX)


@pytest.mark.unit
def test_make_ollama_passes_num_ctx_to_chatollama(mocker):
    """num_ctx must reach ChatOllama (overrides Ollama's 2048 default)."""
    import sys
    from unittest.mock import MagicMock

    fake_mod = MagicMock()
    mocker.patch.dict(sys.modules, {"langchain_ollama": fake_mod})
    from src.llm_factory import _make_ollama

    _make_ollama("qwen7b-custom", 0.4, num_ctx=8192)
    _, kwargs = fake_mod.ChatOllama.call_args
    assert kwargs["num_ctx"] == 8192


@pytest.mark.unit
def test_make_llm_routes_gemini(mocker, monkeypatch):
    """make_llm para 'gemini-*' deve chamar _make_gemini."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-test")
    mock_gemini = mocker.patch("src.llm_factory._make_gemini")
    from src.llm_factory import make_llm

    make_llm("gemini-2.5-flash", temperature=0.0)
    mock_gemini.assert_called_once_with("gemini-2.5-flash", 0.0)
