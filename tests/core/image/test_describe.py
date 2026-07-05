import sys
from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
def test_describe_image_local_uses_chatollama(jpg_image, mocker):
    """A non-GLM model name must route through ChatOllama with pinned num_ctx."""
    from src.core.image.describe import describe_image

    fake_response = MagicMock(content="uma descrição qualquer")
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = fake_response
    fake_mod = MagicMock()
    fake_mod.ChatOllama.return_value = fake_llm
    mocker.patch.dict(sys.modules, {"langchain_ollama": fake_mod})
    mock_make_llm = mocker.patch("src.llm_factory.make_llm")

    result = describe_image(jpg_image, model="moondream-custom")

    assert result == "uma descrição qualquer"
    mock_make_llm.assert_not_called()
    _, kwargs = fake_mod.ChatOllama.call_args
    assert kwargs["model"] == "moondream-custom"
    assert kwargs["num_ctx"] > 0
    assert len(kwargs["callbacks"]) == 1  # VLM timing callback, attached manually


@pytest.mark.unit
def test_describe_image_glm_routes_through_make_llm(jpg_image, mocker):
    """A glm-* model name must route through llm_factory.make_llm, not ChatOllama."""
    from src.core.image.describe import describe_image

    fake_response = MagicMock(content="descrição via GLM")
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = fake_response
    mock_make_llm = mocker.patch("src.llm_factory.make_llm", return_value=fake_llm)

    result = describe_image(jpg_image, model="glm-4.6v-flash")

    assert result == "descrição via GLM"
    mock_make_llm.assert_called_once_with("glm-4.6v-flash", domain="vlm")
    fake_llm.invoke.assert_called_once()


@pytest.mark.unit
def test_describe_image_handles_list_shaped_response_content(jpg_image, mocker):
    """Some Gemini/tool-call-shaped responses return .content as a list of
    blocks instead of a plain str — describe_image must join it via
    extract_llm_text instead of leaking the raw list."""
    from src.core.image.describe import describe_image

    fake_response = MagicMock(
        content=[{"type": "text", "text": "uma descrição "}, "em blocos"]
    )
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = fake_response
    mocker.patch("src.llm_factory.make_llm", return_value=fake_llm)

    result = describe_image(jpg_image, model="gemini-2.5-flash")

    assert result == "uma descrição em blocos"


@pytest.mark.unit
def test_describe_image_gemini_routes_through_make_llm(jpg_image, mocker):
    """A gemini-* model name must route through llm_factory.make_llm, not ChatOllama."""
    from src.core.image.describe import describe_image

    fake_response = MagicMock(content="descrição via Gemini")
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = fake_response
    mock_make_llm = mocker.patch("src.llm_factory.make_llm", return_value=fake_llm)

    result = describe_image(jpg_image, model="gemini-2.5-flash")

    assert result == "descrição via Gemini"
    mock_make_llm.assert_called_once_with("gemini-2.5-flash", domain="vlm")
    fake_llm.invoke.assert_called_once()
