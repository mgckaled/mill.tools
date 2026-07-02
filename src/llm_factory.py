"""
llm_factory.py: Provider-agnostic LLM factory.

Single entry point `make_llm()` decides which LangChain chat model to instantiate
based on the model name passed via CLI flags (--fm / --am / --pm). Names starting
with "gemini" are routed to Google's Gemini API, "glm" to Zhipu/Z.ai's GLM API;
everything else falls back to the local Ollama runtime — preserving full
backwards compatibility with the project's original 100% local pipeline.

Gemini usage requires GOOGLE_API_KEY, GLM usage requires ZHIPU_API_KEY, both in
a .env file at the project root.

`make_llm()` is also the single funnel every text/vision LLM call in the project
goes through (formatter/analyzer/prompter/RAG chat/data.assess/data.nl2sql, plus
the cloud branch of image description) — so it is the one place a `domain`-tagged
timing callback (see `_TimingCallback`) can observe every call without touching
each of those call sites.
"""

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler

if TYPE_CHECKING:  # avoid hard import at module load — keeps Ollama-only runs fast
    from langchain_core.language_models.chat_models import BaseChatModel


# Provider routing: any model name starting with one of these prefixes goes to Gemini.
GEMINI_PREFIXES = ("gemini",)

# Sensible Gemini defaults for this project's workloads.
GEMINI_DEFAULT_MAX_RETRIES = 3
GEMINI_DEFAULT_TIMEOUT = (
    120  # seconds — Gemini Flash usually returns in <30s for 30k-token analyses
)

# Provider routing: any model name starting with one of these prefixes goes to GLM
# (Zhipu/Z.ai), via its OpenAI-compatible API.
GLM_PREFIXES = ("glm",)
GLM_BASE_URL = "https://api.z.ai/api/paas/v4/"

# Sensible GLM defaults for this project's workloads (same values as Gemini's —
# both are cloud APIs with comparable latency for this project's prompt sizes).
GLM_DEFAULT_MAX_RETRIES = 3
GLM_DEFAULT_TIMEOUT = 120

# Ollama defaults num_ctx to 2048 tokens — far too small for the verbose structured
# JSON the analyzer/prompter emit (and for the long-context bypass), which silently
# truncates the output into invalid JSON. A larger window prevents that. Kept uniform
# so Ollama does not reload the model when a large analysis call and a small
# language-detection call alternate within the same run.
DEFAULT_OLLAMA_NUM_CTX = 8192


def _is_gemini(model_name: str) -> bool:
    """Return True when the model name belongs to the Google Gemini family."""
    return model_name.lower().startswith(GEMINI_PREFIXES)


def is_gemini_model(model_name: str) -> bool:
    """Public helper for callers that need to branch behaviour by provider.

    Used by analyzer.py and prompter.py to skip chunking when the provider
    supports a 1M-token context window.
    """
    return _is_gemini(model_name)


def _is_glm(model_name: str) -> bool:
    """Return True when the model name belongs to the Zhipu/Z.ai GLM family."""
    return model_name.lower().startswith(GLM_PREFIXES)


def is_glm_model(model_name: str) -> bool:
    """Public helper for callers that need to branch behaviour by provider."""
    return _is_glm(model_name)


def is_cloud_model(model_name: str) -> bool:
    """Return True for any third-party API provider (Gemini or GLM).

    Used where the distinction that matters is "runs locally via Ollama" vs.
    "calls out to an external API" — e.g. skipping chunking for large-context
    cloud models, or surfacing a privacy note in the GUI.
    """
    return _is_gemini(model_name) or _is_glm(model_name)


# Local models with a large context window: short/medium inputs can skip the
# chunk+merge step and run as a single, more coherent pass. The per-model char
# budget caps the cost of a CPU single pass (a giant pass on a small CPU model is
# impractically slow); above it we fall back to chunking. Cloud providers (Gemini
# 1M tokens, GLM 200K tokens) bypass unconditionally via is_cloud_model and are
# intentionally NOT listed here. Budgets are in characters (~4 chars/token).
LONG_CONTEXT_LOCAL_BUDGETS: dict[str, int] = {
    # gemma3-4b-custom: skip the merge for short/medium inputs. The cap stays well
    # under DEFAULT_OLLAMA_NUM_CTX so the prompt + the verbose JSON output still fit
    # in the window (~3K input tokens leaves ~4.5K for prompt+output at 8192 ctx);
    # it also keeps a CPU single pass practical. Above it, chunking resumes.
    "gemma3-4b-custom": 12_000,
}


def long_context_char_budget(model_name: str) -> int | None:
    """Max input chars eligible to skip chunking for a long-context LOCAL model.

    Args:
        model_name: Model identifier (Ollama tag).

    Returns:
        The per-model character budget when *model_name* is a known long-context
        local model (e.g. gemma3-4b-custom), or None otherwise. Cloud providers
        are handled separately (unconditional bypass) and are not included here.
    """
    return LONG_CONTEXT_LOCAL_BUDGETS.get(model_name)


def _load_env_once() -> None:
    """Load variables from .env at the project root, once per process.

    Subsequent calls are no-ops thanks to python-dotenv's idempotency.
    """
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    load_dotenv(env_path)


class _TimingCallback(BaseCallbackHandler):
    """Records the wall-clock latency of each raw LLM call.

    Fires automatically via LangChain's on_llm_start/on_llm_end hooks for any
    Runnable built as `prompt | llm` — no call-site changes needed in
    formatter/analyzer/prompter/chat/assess/nl2sql. Keyed by run_id (not a
    single shared timestamp) so a model instance reused across several
    sequential `.invoke()` calls — e.g. analyzer's chunk+merge loop — times
    each call independently.
    """

    def __init__(self, model_name: str, domain: str) -> None:
        self._model_name = model_name
        self._domain = domain
        self._starts: dict[UUID, float] = {}

    def on_llm_start(self, serialized, prompts, *, run_id: UUID, **kwargs) -> None:
        self._starts[run_id] = time.monotonic()

    def on_llm_end(self, response, *, run_id: UUID, **kwargs) -> None:
        t0 = self._starts.pop(run_id, None)
        if t0 is not None:
            from src.core.observatory.model_timing import record_timing

            record_timing(self._model_name, self._domain, time.monotonic() - t0)

    def on_llm_error(self, error, *, run_id: UUID, **kwargs) -> None:
        self._starts.pop(run_id, None)  # discard — don't record failed calls


def timing_callbacks(model_name: str, domain: str) -> list[BaseCallbackHandler]:
    """Build the callback list that records this model's latency by domain.

    Public so callers that build a chat model without going through make_llm()
    (describe.py's local-Ollama branch) can attach the same instrumentation.
    """
    return [_TimingCallback(model_name, domain)]


def _make_gemini(
    model_name: str,
    temperature: float,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> "BaseChatModel":
    """Instantiate a ChatGoogleGenerativeAI with project-wide defaults.

    Args:
        model_name: Gemini model identifier (e.g. "gemini-2.5-flash").
        temperature: Sampling temperature.
        callbacks: LangChain callback handlers to attach (e.g. timing).

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

    logging.debug(
        "[d] Provider: Google Gemini | model=%s | temperature=%.2f",
        model_name,
        temperature,
    )
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        google_api_key=api_key,
        max_retries=GEMINI_DEFAULT_MAX_RETRIES,
        timeout=GEMINI_DEFAULT_TIMEOUT,
        callbacks=callbacks,
    )


def _make_glm(
    model_name: str,
    temperature: float,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> "BaseChatModel":
    """Instantiate a ChatOpenAI pointed at Zhipu/Z.ai's OpenAI-compatible API.

    Args:
        model_name: GLM model identifier (e.g. "glm-4.7-flash").
        temperature: Sampling temperature.
        callbacks: LangChain callback handlers to attach (e.g. timing).

    Returns:
        A ChatOpenAI configured with GLM_BASE_URL and API key from environment.

    Raises:
        RuntimeError: If ZHIPU_API_KEY is not present in the environment.
    """
    _load_env_once()
    api_key = os.getenv("ZHIPU_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ZHIPU_API_KEY não encontrada. Crie um arquivo .env na raiz do projeto com:\n"
            "    ZHIPU_API_KEY=sua-chave-do-z.ai\n"
            "Gere a chave em https://z.ai/model-api (API Keys no menu do perfil)"
        )

    # Lazy import — only loaded when the user actually opts into GLM.
    from langchain_openai import ChatOpenAI

    logging.debug(
        "[d] Provider: Zhipu GLM | model=%s | temperature=%.2f",
        model_name,
        temperature,
    )
    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=GLM_BASE_URL,
        max_retries=GLM_DEFAULT_MAX_RETRIES,
        timeout=GLM_DEFAULT_TIMEOUT,
        callbacks=callbacks,
    )


def _make_ollama(
    model_name: str,
    temperature: float,
    num_ctx: int = DEFAULT_OLLAMA_NUM_CTX,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> "BaseChatModel":
    """Instantiate a ChatOllama for local inference.

    Args:
        model_name: Ollama model name (e.g. "qwen7b-custom").
        temperature: Sampling temperature.
        num_ctx: Context window in tokens. Overrides Ollama's 2048 default so the
            verbose structured JSON the analyzer/prompter emit is not truncated.
        callbacks: LangChain callback handlers to attach (e.g. timing).

    Returns:
        A ChatOllama instance.
    """
    # Lazy import — keeps the dependency optional in environments that use only Gemini.
    from langchain_ollama import ChatOllama

    logging.debug(
        "[d] Provider: Ollama (local) | model=%s | temperature=%.2f | num_ctx=%d",
        model_name,
        temperature,
        num_ctx,
    )
    # client_kwargs é repassado ao httpx.Client subjacente — define timeout de leitura
    # para evitar que chain.invoke() fique pendurado indefinidamente se o Ollama travar.
    return ChatOllama(
        model=model_name,
        temperature=temperature,
        num_ctx=num_ctx,
        client_kwargs={"timeout": 300.0},
        callbacks=callbacks,
    )


def make_llm(
    model_name: str,
    temperature: float = 0.0,
    num_ctx: int = DEFAULT_OLLAMA_NUM_CTX,
    *,
    domain: str = "llm",
) -> "BaseChatModel":
    """Return a LangChain chat model routed by name prefix.

    - Names starting with "gemini" → Google Gemini (requires GOOGLE_API_KEY in .env)
    - Names starting with "glm" → Zhipu/Z.ai GLM (requires ZHIPU_API_KEY in .env)
    - Anything else → local Ollama

    Args:
        model_name: Model identifier as received from the CLI (--fm/--am/--pm).
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).
        num_ctx: Ollama context window in tokens (ignored for cloud providers).
        domain: Timing bucket recorded for every call this model makes — "llm"
            (default, covers all text pipelines) or "vlm" (image description's
            cloud branch passes this explicitly). See _TimingCallback.

    Returns:
        A LangChain BaseChatModel compatible with the existing `prompt | llm`
        pipelines used across analyzer.py, formatter.py and prompter.py.

    Raises:
        RuntimeError: If a Gemini/GLM model is requested without its API key set.
    """
    callbacks = timing_callbacks(model_name, domain)
    if _is_gemini(model_name):
        return _make_gemini(model_name, temperature, callbacks)
    if _is_glm(model_name):
        return _make_glm(model_name, temperature, callbacks)
    return _make_ollama(model_name, temperature, num_ctx, callbacks)
