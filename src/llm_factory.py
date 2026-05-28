"""
llm_factory.py: Provider-agnostic LLM factory.

Single entry point `make_llm()` decides which LangChain chat model to instantiate
based on the model name passed via CLI flags (--fm / --am / --pm). Names starting
with "gemini" are routed to Google's Gemini API; everything else falls back to
the local Ollama runtime — preserving full backwards compatibility with the
project's original 100% local pipeline.

Gemini usage requires GOOGLE_API_KEY in a .env file at the project root.
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:  # avoid hard import at module load — keeps Ollama-only runs fast
    from langchain_core.language_models.chat_models import BaseChatModel


# Provider routing: any model name starting with one of these prefixes goes to Gemini.
GEMINI_PREFIXES = ("gemini",)

# Sensible Gemini defaults for this project's workloads.
GEMINI_DEFAULT_MAX_RETRIES = 3
GEMINI_DEFAULT_TIMEOUT = 120  # seconds — Gemini Flash usually returns in <30s for 30k-token analyses


def _is_gemini(model_name: str) -> bool:
    """Return True when the model name belongs to the Google Gemini family."""
    return model_name.lower().startswith(GEMINI_PREFIXES)


def is_gemini_model(model_name: str) -> bool:
    """Public helper for callers that need to branch behaviour by provider.

    Used by analyzer.py and prompter.py to skip chunking when the provider
    supports a 1M-token context window.
    """
    return _is_gemini(model_name)


def _load_env_once() -> None:
    """Load variables from .env at the project root, once per process.

    Subsequent calls are no-ops thanks to python-dotenv's idempotency.
    """
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    load_dotenv(env_path)


def _make_gemini(model_name: str, temperature: float) -> "BaseChatModel":
    """Instantiate a ChatGoogleGenerativeAI with project-wide defaults.

    Args:
        model_name: Gemini model identifier (e.g. "gemini-2.5-flash").
        temperature: Sampling temperature.

    Returns:
        A ChatGoogleGenerativeAI configured with API key from environment.

    Raises:
        RuntimeError: If GOOGLE_API_KEY is not present in the environment.
    """
    _load_env_once()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY não encontrada. Crie um arquivo .env na raiz do projeto com:\n"
            "    GOOGLE_API_KEY=sua-chave-do-google-ai-studio\n"
            "Gere a chave em https://aistudio.google.com/apikey"
        )

    # Lazy import — only loaded when the user actually opts into Gemini.
    from langchain_google_genai import ChatGoogleGenerativeAI

    logging.debug("[d] Provider: Google Gemini | model=%s | temperature=%.2f",
                  model_name, temperature)
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        google_api_key=api_key,
        max_retries=GEMINI_DEFAULT_MAX_RETRIES,
        timeout=GEMINI_DEFAULT_TIMEOUT,
    )


def _make_ollama(model_name: str, temperature: float) -> "BaseChatModel":
    """Instantiate a ChatOllama for local inference.

    Args:
        model_name: Ollama model name (e.g. "qwen7b-custom").
        temperature: Sampling temperature.

    Returns:
        A ChatOllama instance.
    """
    # Lazy import — keeps the dependency optional in environments that use only Gemini.
    from langchain_ollama import ChatOllama

    logging.debug("[d] Provider: Ollama (local) | model=%s | temperature=%.2f",
                  model_name, temperature)
    return ChatOllama(model=model_name, temperature=temperature)


def make_llm(model_name: str, temperature: float = 0.0) -> "BaseChatModel":
    """Return a LangChain chat model routed by name prefix.

    - Names starting with "gemini" → Google Gemini (requires GOOGLE_API_KEY in .env)
    - Anything else → local Ollama

    Args:
        model_name: Model identifier as received from the CLI (--fm/--am/--pm).
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).

    Returns:
        A LangChain BaseChatModel compatible with the existing `prompt | llm`
        pipelines used across analyzer.py, formatter.py and prompter.py.

    Raises:
        RuntimeError: If a Gemini model is requested without GOOGLE_API_KEY set.
    """
    if _is_gemini(model_name):
        return _make_gemini(model_name, temperature)
    return _make_ollama(model_name, temperature)
