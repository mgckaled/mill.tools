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
    args, _ = mock_ollama.call_args
    assert args[:3] == ("qwen7b-custom", 0.4, DEFAULT_OLLAMA_NUM_CTX)
    assert len(args[3]) == 1  # timing callbacks list


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
    args, _ = mock_gemini.call_args
    assert args[:2] == ("gemini-2.5-flash", 0.0)
    assert len(args[2]) == 1  # timing callbacks list


@pytest.mark.unit
def test_make_llm_routes_glm(mocker, monkeypatch):
    """make_llm para 'glm-*' deve chamar _make_glm."""
    monkeypatch.setenv("ZHIPU_API_KEY", "fake-key-for-test")
    mock_glm = mocker.patch("src.llm_factory._make_glm")
    from src.llm_factory import make_llm

    make_llm("glm-4.7-flash", temperature=0.0)
    args, _ = mock_glm.call_args
    assert args[:2] == ("glm-4.7-flash", 0.0)
    assert len(args[2]) == 1  # timing callbacks list


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


@pytest.mark.unit
def test_make_ollama_forwards_callbacks_to_chatollama(mocker):
    """callbacks= must reach ChatOllama unchanged (timing instrumentation)."""
    import sys
    from unittest.mock import MagicMock

    fake_mod = MagicMock()
    mocker.patch.dict(sys.modules, {"langchain_ollama": fake_mod})
    from src.llm_factory import _make_ollama, timing_callbacks

    cbs = timing_callbacks("qwen7b-custom", "llm")
    _make_ollama("qwen7b-custom", 0.4, callbacks=cbs)
    _, kwargs = fake_mod.ChatOllama.call_args
    assert kwargs["callbacks"] is cbs


@pytest.mark.unit
def test_make_llm_domain_defaults_to_llm(mocker):
    """make_llm() without an explicit domain tags every call site 'llm'."""
    mock_ollama = mocker.patch("src.llm_factory._make_ollama")
    from src.llm_factory import make_llm

    make_llm("qwen7b-custom")
    args, _ = mock_ollama.call_args
    callback = args[3][0]
    assert callback._domain == "llm"


@pytest.mark.unit
def test_make_llm_domain_vlm_is_forwarded(mocker, monkeypatch):
    """describe.py's cloud branch passes domain='vlm' explicitly."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-test")
    mock_gemini = mocker.patch("src.llm_factory._make_gemini")
    from src.llm_factory import make_llm

    make_llm("gemini-2.5-flash", domain="vlm")
    args, _ = mock_gemini.call_args
    callback = args[2][0]
    assert callback._domain == "vlm"


@pytest.mark.unit
def test_timing_callback_records_elapsed_on_llm_end(mocker):
    """on_llm_start -> on_llm_end records a positive elapsed via record_timing."""
    from uuid import uuid4

    from src.llm_factory import _TimingCallback

    mock_record = mocker.patch("src.core.observatory.model_timing.record_timing")
    cb = _TimingCallback("gemini-2.5-flash", "llm")
    run_id = uuid4()

    cb.on_llm_start({}, [], run_id=run_id)
    cb.on_llm_end(object(), run_id=run_id)

    mock_record.assert_called_once()
    args, _ = mock_record.call_args
    assert args[0] == "gemini-2.5-flash"
    assert args[1] == "llm"
    assert args[2] > 0


@pytest.mark.unit
def test_timing_callback_skips_recording_on_llm_error(mocker):
    """A failed call must not be recorded — on_llm_error just discards the start."""
    from uuid import uuid4

    from src.llm_factory import _TimingCallback

    mock_record = mocker.patch("src.core.observatory.model_timing.record_timing")
    cb = _TimingCallback("gemini-2.5-flash", "llm")
    run_id = uuid4()

    cb.on_llm_start({}, [], run_id=run_id)
    cb.on_llm_error(RuntimeError("boom"), run_id=run_id)

    mock_record.assert_not_called()
    assert run_id not in cb._starts


@pytest.mark.unit
def test_timing_callback_ignores_end_without_matching_start(mocker):
    """on_llm_end for an unknown run_id (e.g. handler reused oddly) is a no-op."""
    from uuid import uuid4

    from src.llm_factory import _TimingCallback

    mock_record = mocker.patch("src.core.observatory.model_timing.record_timing")
    cb = _TimingCallback("gemini-2.5-flash", "llm")

    cb.on_llm_end(object(), run_id=uuid4())

    mock_record.assert_not_called()
