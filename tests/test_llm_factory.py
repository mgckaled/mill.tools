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
        ("glm-4.7-flash", True),
        ("glm-4.5-flash", True),
        ("GLM-test", True),
        ("qwen7b-custom", False),
        ("gemini-2.5-flash", False),
        ("", False),
    ],
)
def test_is_glm(model, expected):
    from src.llm_factory import is_glm_model

    assert is_glm_model(model) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "model, expected",
    [
        ("gemini-2.5-flash", True),
        ("glm-4.7-flash", True),
        ("qwen7b-custom", False),
        ("phi4mini-custom", False),
        ("", False),
    ],
)
def test_is_cloud_model(model, expected):
    from src.llm_factory import is_cloud_model

    assert is_cloud_model(model) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "model, expected",
    [
        ("gemma3-4b-custom", 12_000),
        ("qwen7b-custom", None),
        ("gemini-2.5-flash", None),  # Gemini bypasses unconditionally, not via budget
        ("glm-4.7-flash", None),  # GLM bypasses unconditionally too, not via budget
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
def test_make_llm_glm_raises_without_api_key(monkeypatch):
    """make_llm para glm sem ZHIPU_API_KEY deve lançar RuntimeError."""
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.setattr("src.llm_factory.load_dotenv", lambda *a, **kw: None)
    from src.llm_factory import make_llm

    with pytest.raises(RuntimeError, match="ZHIPU_API_KEY"):
        make_llm("glm-4.7-flash")


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


@pytest.mark.unit
def test_make_llm_routes_glm(mocker, monkeypatch):
    """make_llm para 'glm-*' deve chamar _make_glm."""
    monkeypatch.setenv("ZHIPU_API_KEY", "fake-key-for-test")
    mock_glm = mocker.patch("src.llm_factory._make_glm")
    from src.llm_factory import make_llm

    make_llm("glm-4.7-flash", temperature=0.0)
    mock_glm.assert_called_once_with("glm-4.7-flash", 0.0)


@pytest.mark.unit
def test_make_glm_passes_base_url_and_api_key_to_chatopenai(mocker, monkeypatch):
    """_make_glm must configure ChatOpenAI with GLM's base_url and API key."""
    import sys
    from unittest.mock import MagicMock

    monkeypatch.setenv("ZHIPU_API_KEY", "fake-zhipu-key")
    monkeypatch.setattr("src.llm_factory.load_dotenv", lambda *a, **kw: None)
    fake_mod = MagicMock()
    mocker.patch.dict(sys.modules, {"langchain_openai": fake_mod})
    from src.llm_factory import GLM_BASE_URL, _make_glm

    _make_glm("glm-4.7-flash", 0.2)
    _, kwargs = fake_mod.ChatOpenAI.call_args
    assert kwargs["model"] == "glm-4.7-flash"
    assert kwargs["temperature"] == 0.2
    assert kwargs["api_key"] == "fake-zhipu-key"
    assert kwargs["base_url"] == GLM_BASE_URL
