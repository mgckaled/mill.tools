# Timing persistente por modelo (LLM/VLM/Embedder) — plano de implementação

**Documento de execução — plano de implementação (teor técnico elevado)**
Data: 2 de julho de 2026 · Escopo: substituir a janela móvel de 5 amostras (`ai_answer_times`, só RAG chat) por um log persistente, cross-domínio (LLM/VLM/embedder), consolidado no hub Observatório · Restrição: **zero dependência nova** — só `langchain_core` (já instalado) e stdlib.

> **Origem.** Nasceu de uma observação direta na aba Status do hub Observatório: a seção "Tempo de resposta por modelo" aparecia vazia (`Screenshot_171.png`) porque `ai_answer_times` é uma janela móvel de 5 amostras, gravada só pelo fluxo de Conversa da IA — VLM (descrição de imagem) e o embedder (`nomic-embed-custom`) nunca tiveram timing registrado. Levantamento completo do estado atual + pesquisa técnica dirigida (Context7 sobre `langchain_core`) confirmaram o desenho abaixo.

---

## Sumário

1. Objetivo e escopo
2. Estado atual (achados do levantamento)
3. Pesquisa técnica — callbacks do LangChain (Context7)
4. Desenho da solução
5. O que **não** muda
6. Passos de implementação (commits)
7. Testes
8. Critérios de aceitação
9. Riscos e o que **não** fazer
10. Tabela-resumo de arquivos afetados
11. Fontes

---

## 1. Objetivo e escopo

Registrar tempo de resposta de **todos** os modelos usados pelo app — texto (LLM), visão (VLM) e embedding — de forma **persistente e cumulativa** (não uma janela móvel), separados por domínio, e exibi-los exclusivamente no hub **Observatório** (aba Status), removendo a duplicação que hoje existe também na aba Painel do hub IA.

**Decisões já fechadas com o usuário** (não reabrir sem motivo novo):

- **Um único domínio `"llm"`** para todo texto — sem sub-bucket por Formatter/Analyzer/Prompter/RAG/`data.assess`/`data.nl2sql`. Os chunks de origem têm tamanho semelhante entre esses fluxos; a granularidade extra não agrega valor prático.
- **`"vlm"`** (descrição de imagem) e **`"embed"`** (nomic-embed) ficam separados de `"llm"` — são workloads genuinamente diferentes, e o campo `domain` é o que resolve a ambiguidade do Gemini (mesma string `"gemini-2.5-flash"` usada como LLM de texto **e** como VLM).
- **Não** criar 3 arquivos de persistência — um único log, diferenciado por campo `domain`, mesmo padrão já usado em `core/observatory/activity.py` (que loga eventos de todos os módulos num arquivo só, diferenciados por `module`).
- **Painel da IA perde a seção de timing** — fica só no Observatório (single source of truth).

**Fora de escopo:** qualquer alteração em `ai_answer_times`/`gui/modules/ai/timing.py` (a estimativa "tempo típico" ao vivo da aba Conversa continua como está — ver seção 5).

---

## 2. Estado atual (achados do levantamento)

- **`ai_answer_times`** (`~/.mill-tools/config.json`) é uma **janela móvel de 5** (`timing.py::record_duration`, `keep=5`) — não é "não persiste", é "esquece de propósito" para alimentar a estimativa de "tempo típico" ao vivo (`gui/modules/ai/view.py::_record_answer_time`, linhas 196-202). Só é gravado no fluxo **RAG chat** (`run_ai_answer`).
- **VLM** (`core/image/describe.py::describe_image`) e **embedder** (`core/rag/embedder.py::embed_texts`/`embed_query`) **não medem tempo nenhum hoje** — ausência total de instrumentação, não um bug de persistência.
- **`core/rag/analytics.py::model_timings(times_map: dict[str, list[float]]) -> tuple[ModelTiming, ...]`** já é pura e genérica (count/mean/median/p90 via `statistics`). **Não precisa mudar** — só passa a receber 3 mapas diferentes (um por domínio) em vez de 1.
- **`gui/modules/observatory/status_tab.py`** e **`gui/modules/ai/analytics_tab.py`** hoje leem o **mesmo** `ai_answer_times` e chamam a **mesma** `model_timings()` — dado duplicado em duas telas; só o Painel da IA tem gráfico (via `gui/modules/_charts.py` + `core/data/charts.py`, extras `[analysis]`+`[data-plot]`, degrada graciosamente sem eles).
- **`make_llm()`** (`src/llm_factory.py`) é o **funil único** por onde passam TODAS as chamadas de LLM/VLM de texto/visão do projeto: `formatter.py:141`, `analyzer.py:358,359`, `prompter.py:183`, `core/rag/chat.py:99`, `core/data/assess.py:75` (via `make_llm_fn`, default = `make_llm`), `core/data/nl2sql.py:106` (idem), e `core/image/describe.py:79` (só o branch cloud — Gemini/GLM). O branch **local** de `describe_image` (Ollama, moondream/gemma3 vision) instancia `ChatOllama` **diretamente**, sem passar por `make_llm()`.
- **`core/rag/embedder.py::embed_texts`** já sub-batcha em `EMBED_BATCH_SIZE=16` (`client.embed_documents(...)` por lote) — unidade natural de medição. `embed_query` é uma chamada única (latência interativa de busca, workload distinto de indexação em lote).
- **GLM já se autodiferencia** pelo nome (`glm-4.7-flash` texto vs. `glm-4.6v-flash` visão) — só o Gemini reusa a mesma string em dois papéis. Nenhum campo (`module_id`/`operation`/`kind`) acompanha a duração hoje em lugar nenhum do projeto — o único precedente de chave "extra" é `audio_viz_times`, chaveado por `kind` (waveform/spectrogram), não por modelo.
- **Cap de referência do projeto**: `core/recipes/history.py` corta em 500 (`_MAX_RUNS`), `core/observatory/activity.py` corta em 200 (`_MAX_ENTRIES`) — ambos via `lista[-N:]` (FIFO simples, sem agregação; entradas mais antigas são silenciosamente descartadas ao exceder o teto).

---

## 3. Pesquisa técnica — callbacks do LangChain (Context7)

Pergunta central: dá para capturar latência **sem** embrulhar `time.monotonic()` manualmente em 6+ pontos de chamada (`formatter`/`analyzer`×2/`prompter`/`chat.answer`/`assess`/`nl2sql`)?

- **Chat models: sim.** `langchain_core.callbacks.BaseCallbackHandler` expõe `on_llm_start(serialized, prompts, *, run_id, **kwargs)` / `on_llm_end(response, *, run_id, **kwargs)` / `on_llm_error(error, *, run_id, **kwargs)`, disparados automaticamente por **qualquer** `Runnable` que envolva um `BaseChatModel` (inclusive `prompt | llm` via LCEL), sem precisar que o call site declare nada. A doc oficial confirma `callbacks` como campo de primeira classe do `RunnableConfig` (`docs.langchain.com/oss/python/langchain/models` — "Invocation config") e o próprio catálogo de integrações do LangChain usa esse mecanismo para medição de latência de produção (`BigQueryCallbackHandler`: *"built-in latency measurement for all LLM and tool calls"*) — validando que "callback mede latência" é idioma estabelecido, não invenção deste plano. Todo `BaseChatModel` (`ChatOllama`, `ChatGoogleGenerativeAI`, `ChatOpenAI`) aceita `callbacks=[...]` como kwarg de construtor (campo Pydantic herdado de `Serializable`/`RunnableSerializable`) — mais direto e mais certo do que `.with_config()`.
- **Embeddings: não.** A superfície pública de `Embeddings.embed_documents(texts)` / `.embed_query(text)` (confirmada em múltiplos exemplos de integração — Google, HuggingFace, Voyage, Fireworks) **não expõe** `run_manager`/`callbacks` em nenhuma assinatura. `langchain_core.embeddings.Embeddings` não dispara `on_*` hooks como `BaseChatModel` — precisa de medição manual no call site.

**Consequência de arquitetura**: LLM+VLM (via `make_llm()`) ganham instrumentação automática — **um único ponto de mudança** (`llm_factory.py`) cobre 6 dos 7 call sites de texto/visão de graça, sem tocar `formatter.py`/`analyzer.py`/`prompter.py`/`chat.py`/`assess.py`/`nl2sql.py`. Só o branch Ollama local de `describe_image` (que já bypassa `make_llm()`) e o embedder precisam de wiring manual — 2 arquivos, não 6+.

---

## 4. Desenho da solução

### 4.1 Novo módulo puro `src/core/observatory/model_timing.py`

Mesmo padrão de `activity.py` (append-only, `Path.home()/.mill-tools/model_timings.json`), com uma diferença deliberada: **corte por par `(domain, model)`**, não corte flat na lista inteira. Um corte flat deixaria `"llm"` (chamado com muito mais frequência) expulsar silenciosamente o histórico de `"vlm"`/`"embed"` do arquivo.

```python
"""Append-only, per-(domain, model) latency log — the Observatório's timing data.

Every call to make_llm() (LLM/VLM) and to the embedder (embed) writes one
TimingEntry here at its natural completion point, mirroring activity.py's
convention. Persisted to ~/.mill-tools/model_timings.json, capped at the last
_MAX_PER_BUCKET entries *per (domain, model) pair* — not a flat cut on the
whole file, because "llm" is called far more often than "vlm"/"embed" and a
flat cut would silently evict their history.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_PER_BUCKET = 500  # same magnitude as core.recipes.history's _MAX_RUNS


@dataclass(frozen=True, slots=True)
class TimingEntry:
    """One model call's latency, tagged by domain."""

    model: str
    domain: str  # "llm" | "vlm" | "embed"
    elapsed: float  # seconds
    timestamp: float  # epoch seconds


def _store_path() -> Path:
    """Canonical on-disk location for the model timing log."""
    return Path.home() / ".mill-tools" / "model_timings.json"


def load_timings(path: Path | None = None) -> list[TimingEntry]:
    """Load the log in append order. [] on absence or corruption; malformed
    individual entries are skipped (logged), same convention as activity.py."""
    path = path or _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[!] Could not read model timing log %s: %s", path, exc)
        return []

    entries: list[TimingEntry] = []
    for raw in data:
        try:
            entries.append(
                TimingEntry(
                    model=raw["model"],
                    domain=raw["domain"],
                    elapsed=float(raw["elapsed"]),
                    timestamp=float(raw["timestamp"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("[!] Skipping malformed timing entry: %r", raw)
    return entries


def _trim_per_bucket(
    entries: list[TimingEntry], *, cap: int = _MAX_PER_BUCKET
) -> list[TimingEntry]:
    """Keep only the last `cap` entries per (domain, model), then re-sort by time."""
    buckets: dict[tuple[str, str], list[TimingEntry]] = {}
    for e in entries:
        buckets.setdefault((e.domain, e.model), []).append(e)
    trimmed = [e for group in buckets.values() for e in group[-cap:]]
    trimmed.sort(key=lambda e: e.timestamp)
    return trimmed


def record_timing(
    model: str,
    domain: str,
    elapsed: float,
    *,
    path: Path | None = None,
    now: float | None = None,
) -> None:
    """Append one sample, capped at _MAX_PER_BUCKET per (domain, model).

    Non-positive elapsed is dropped silently (same guard as timing.py's
    record_duration) — a zero/negative duration means the call errored or was
    never actually timed, not a valid sample.
    """
    if elapsed <= 0:
        return
    path = path or _store_path()
    entries = load_timings(path)
    entries.append(
        TimingEntry(
            model=model,
            domain=domain,
            elapsed=float(elapsed),
            timestamp=now if now is not None else time.time(),
        )
    )
    entries = _trim_per_bucket(entries)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(e) for e in entries]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.debug("[d] Could not write model timing log: %s", exc)


def timings_by_domain(
    entries: list[TimingEntry], domain: str
) -> dict[str, list[float]]:
    """Filter + group into the {model: [durations]} shape model_timings() expects."""
    out: dict[str, list[float]] = {}
    for e in entries:
        if e.domain == domain:
            out.setdefault(e.model, []).append(e.elapsed)
    return out
```

Sem locking entre processos (mesmo risco aceito já existente em `activity.py`/`config.json` — app pessoal single-user; duas gravações colidindo no mesmo instante são improváveis e não introduzem complexidade nova como `filelock`, o que violaria "zero dependência nova").

### 4.2 Instrumentação LLM/VLM (cloud) — callback em `llm_factory.py`

```python
import time
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler


class _TimingCallback(BaseCallbackHandler):
    """Records the wall-clock latency of each raw LLM call via LangChain's
    on_llm_start/on_llm_end hooks — fires automatically for every chain built
    with `prompt | llm`, no call-site changes needed."""

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
    """Public helper so callers outside this module (describe.py's local Ollama
    branch, which bypasses make_llm()) can attach the same instrumentation."""
    return [_TimingCallback(model_name, domain)]
```

`make_llm()` ganha um kwarg **keyword-only** `domain: str = "llm"` (default preserva os 6 call sites de texto sem nenhuma mudança de código neles) e passa `callbacks=timing_callbacks(model_name, domain)` para `_make_gemini`/`_make_glm`/`_make_ollama`, que repassam ao construtor de cada `BaseChatModel` (`callbacks=` é kwarg Pydantic universal em todo `BaseChatModel`).

```python
def make_llm(
    model_name: str,
    temperature: float = 0.0,
    num_ctx: int = DEFAULT_OLLAMA_NUM_CTX,
    *,
    domain: str = "llm",
) -> "BaseChatModel":
    callbacks = timing_callbacks(model_name, domain)
    if _is_gemini(model_name):
        return _make_gemini(model_name, temperature, callbacks)
    if _is_glm(model_name):
        return _make_glm(model_name, temperature, callbacks)
    return _make_ollama(model_name, temperature, num_ctx, callbacks)
```

`_make_gemini`/`_make_glm`/`_make_ollama` ganham um parâmetro `callbacks: list | None = None` repassado ao respectivo construtor (`ChatGoogleGenerativeAI(..., callbacks=callbacks)` etc.).

**`core/image/describe.py`** (branch cloud, linha 79): `make_llm(model)` → `make_llm(model, domain="vlm")` — uma linha.

### 4.3 Instrumentação VLM (local Ollama) — `describe_image`, branch que bypassa `make_llm()`

```python
from src.llm_factory import DEFAULT_OLLAMA_NUM_CTX, timing_callbacks, ...

llm = ChatOllama(
    model=model,
    num_ctx=DEFAULT_OLLAMA_NUM_CTX,
    callbacks=timing_callbacks(model, "vlm"),
)
```

Não unificar este branch com `make_llm()` (que teria a vantagem de reusar o mesmo código, mas mudaria `temperature` de "default do Ollama" para `0.0` explícito — uma mudança de comportamento de sampling fora do escopo deste plano). Mantém a estrutura if/else atual, só adiciona `callbacks=`.

### 4.4 Instrumentação embed — medição manual em `core/rag/embedder.py`

```python
import time
from src.core.observatory.model_timing import record_timing

def embed_texts(texts, model=DEFAULT_EMBED_MODEL, *, batch_size=EMBED_BATCH_SIZE, progress_cb=None):
    ...
    for start in range(0, total, batch_size):
        t0 = time.monotonic()
        batch = client.embed_documents(texts[start : start + batch_size])
        record_timing(model, "embed", time.monotonic() - t0)
        out.extend(batch)
        ...

def embed_query(text, model=DEFAULT_EMBED_MODEL):
    t0 = time.monotonic()
    vec = _embeddings(model).embed_query(text)
    record_timing(model, "embed", time.monotonic() - t0)
    return np.asarray(vec, dtype=np.float32)
```

Uma entrada por **lote** (até 16 chunks) em `embed_texts`, não por documento inteiro — unidade estável/comparável entre indexações de tamanhos diferentes. `embed_query` mede a latência interativa de busca (workload distinto, mesmo domínio `"embed"` — sem sub-bucket, mesma decisão de simplicidade da seção 1).

`core/rag/embedder.py` já importa só stdlib+numpy+lazy langchain_ollama; importar `core/observatory/model_timing` é `core → core`, permitido pela skill `architecture`.

### 4.5 GUI — Observatório: 3 tabelas + 2 gráficos ✅ (revisado — aba própria, não seção do Status)

**Revisão pós-implementação**: o desenho original colocava as 3 seções dentro da aba **Status** existente. Ao usar, ficou claro que timing merece uma aba **própria** (3 tabelas + 2 gráficos é superfície demais para dividir espaço com gates/classificador/config) — então o hub Observatório ganhou uma **3ª aba** ("Tempo de resposta", `gui/modules/observatory/timing_tab.py`) e `status_tab.py` voltou a conter só gates/classificador/config, como antes deste plano.

Novo componente reusável `src/gui/modules/observatory/timing_section.py` (evita triplicar o código de tabela+gráfico entre LLM/VLM/embed — mesmo padrão de extração "divide-se ao tocar" da skill `architecture`, tabela reaproveitando os helpers `_cell`/`_header`/`_hcell`/`_data_row` que existiam em `gui/modules/ai/analytics_tab.py`):

```python
def build_timing_section(
    title: str, *, show_chart: bool
) -> tuple[ft.Control, Callable[[tuple[ModelTiming, ...]], None]]:
    """One domain's table (+ optional bar chart). Returns (control, apply)."""
```

`timing_tab.py::build_timing_tab(page) -> (control, apply)` (mesma assinatura de `build_status_tab`/`build_activity_tab`) monta as 3 seções e, no `apply()`:

```python
from src.core.observatory.model_timing import load_timings, timings_by_domain
from src.core.rag.analytics import model_timings

entries = load_timings()
llm_section.apply(model_timings(timings_by_domain(entries, "llm")))
vlm_section.apply(model_timings(timings_by_domain(entries, "vlm")))
embed_section.apply(model_timings(timings_by_domain(entries, "embed")))  # show_chart=False
```

`embed` usa `show_chart=False` (um modelo só — `nomic-embed-custom` — não é comparação, não precisa de barra; a tabela já mostra count/média/mediana/p90). LLM e VLM usam `show_chart=True`, reaproveitando `model_timings_result()` (`core/rag/analytics.py`, **intocada**) + `_charts.render_result_png` (`core/data/charts.py`, **intocado**) — mesmo caminho já provado no Painel da IA.

`view.py` (`build_observatory_module`) passa de duas para **três** abas manuais (`Atividade | Status | Tempo de resposta`, `visible=` num `ft.Stack`, mesmo padrão Flet 0.85 sem `ft.Tabs`); `last_observatory_tab` ganha o valor `"timing"` além de `"atividade"`/`"status"`.

`cli/observatory.py::_run_status` ganha a mesma quebra por domínio (3 blocos de texto em vez de 1), lendo `model_timings.json` diretamente (mesmo padrão de `_answer_times()` — CLI não importa `gui.settings`); a CLI não tem o conceito de "aba", então não muda com essa revisão.

### 4.6 GUI — remoção da seção de timing do Painel da IA

`gui/modules/ai/analytics_tab.py`: remove `timing_header`/`timing_body`/`timing_chart` e a chamada a `model_timings`/`model_timings_result` — mantém só "Documentos que dominam o índice". `AnalyticsTab.apply` muda de `apply(stats, times_map)` para `apply(stats)`.

`gui/modules/ai/view.py:229-230`: remove a leitura de `times_map` e simplifica a chamada para `analytics_tab.apply(stats)`.

---

## 5. O que **não** muda

- **`ai_answer_times` / `gui/modules/ai/timing.py`** — intocados. Continuam alimentando só a estimativa "tempo típico" ao vivo da aba Conversa (`_record_answer_time`, janela de 5, propósito de recência). O novo log em `model_timing.py` é gravado **em paralelo**, por um caminho totalmente diferente (callback do LangChain dentro de `chat.answer`'s `make_llm(model_name, temperature=0.2)`, que já herda `domain="llm"` por default) — sem dual-write manual, sem tocar `run_ai_answer`.
- **`core/rag/analytics.py::model_timings`/`model_timings_result`** — zero alteração de assinatura ou lógica.
- **`core/data/charts.py`/`gui/modules/_charts.py`** — zero alteração; reusados como já estão.
- **`formatter.py`/`analyzer.py`/`prompter.py`/`core/rag/chat.py`/`core/data/assess.py`/`core/data/nl2sql.py`** — zero linha tocada (instrumentação chega via `make_llm()` default `domain="llm"`).
- **Nenhuma migração de dados** — `ai_answer_times` continua existindo do jeito que está; o novo log começa vazio e acumula dali para frente (os no máximo 5 valores antigos por modelo não valem a complexidade de um backfill).

---

## 6. Passos de implementação (commits)

Branch **`main`** direto (sem branch de feature), commits sem `Co-Authored-By`. Cada commit deixa `uv run pytest -m unit` e `ruff` limpos antes do próximo.

1. **`feat(observatory): add persistent per-domain model timing log`**
   `src/core/observatory/model_timing.py` (novo) + `tests/core/observatory/test_model_timing.py` (round-trip, corte por bucket, malformado→skip, elapsed não-positivo descartado).

2. **`feat(llm): tag make_llm() with a domain and auto-record latency via callback`**
   `src/llm_factory.py` (`_TimingCallback`, `timing_callbacks()`, kwarg `domain` em `make_llm`/`_make_gemini`/`_make_glm`/`_make_ollama`) + `tests/test_llm_factory.py` (callback dispara em `on_llm_end`, não dispara em `on_llm_error`, default `domain="llm"` preservado).

3. **`feat(image): record VLM latency for both cloud and local describe_image branches`**
   `src/core/image/describe.py` (`domain="vlm"` no branch cloud; `callbacks=timing_callbacks(...)` no branch Ollama local) + `tests/core/image/test_describe.py` (ajustar mocks de `ChatOllama`/`make_llm` para o novo kwarg).

4. **`feat(rag): record embed latency per batch in embedder.embed_texts/embed_query`**
   `src/core/rag/embedder.py` + `tests/core/rag/test_embedder.py` (fixture de isolamento redirecionando `model_timing._store_path`, mesmo padrão já usado para `gui.settings`/`activity._store_path` nos testes do Observatório).

5. **`feat(observatory): break down the Status tab into 3 tables + 2 charts (LLM/VLM/embed)`**
   `src/gui/modules/observatory/timing_section.py` (novo, componente reusável) + `src/gui/modules/observatory/status_tab.py` (rewire) + `tests/gui/modules/observatory/` (construct-smoke atualizado).

6. **`feat(observatory): break down "observatory status" CLI output by domain`**
   `src/cli/observatory.py` (`_run_status`, leitura de `model_timings.json`) + teste correspondente em `tests/cli/`.

7. **`refactor(ai): remove per-model timing from the AI hub Painel — moved to Observatório`**
   `src/gui/modules/ai/analytics_tab.py` (remove seção de timing) + `src/gui/modules/ai/view.py` (simplifica `apply(stats)`) + testes correspondentes ajustados.

8. **`docs: document the model timing log in CLAUDE.md`**
   Atualiza a seção do Módulo Observatório (`core/observatory/`) e a lista de arquivos `~/.mill-tools/` no `CLAUDE.md`.

---

## 7. Testes

- **`test_model_timing.py`** (novo, `tests/core/observatory/`): round-trip `record_timing`→`load_timings` em `tmp_path`; corte por `(domain, model)` — plantar >500 entradas de `"llm"`+`"x-model"` e confirmar que entradas de `"vlm"`/`"embed"` intercaladas sobrevivem intactas (prova do porquê do corte não ser flat); `elapsed <= 0` não grava; entrada malformada no JSON é pulada (log, não exceção); `timings_by_domain` filtra e agrupa corretamente.
- **`test_llm_factory.py`**: mockar `langchain_ollama.ChatOllama`/`langchain_google_genai.ChatGoogleGenerativeAI`/`langchain_openai.ChatOpenAI` (padrão já existente no arquivo) e capturar o kwarg `callbacks=` passado — confirmar que contém uma instância de `_TimingCallback` com `domain` correto. Teste funcional do callback em si (sem precisar do Ollama real): instanciar `_TimingCallback` isolada, chamar `on_llm_start(..., run_id=X)` → `on_llm_end(..., run_id=X)` com `record_timing` mockado (`mocker.patch("src.core.observatory.model_timing.record_timing")`) e verificar a chamada com `elapsed > 0`; `on_llm_error` não deve chamar `record_timing`.
- **`test_describe.py`**: **risco identificado** — os testes existentes mockam `langchain_ollama.ChatOllama` e possivelmente `llm_factory.make_llm`; adicionar `callbacks=`/`domain="vlm"` pode quebrar uma asserção de kwargs exatos existente. Revisar e ajustar (não é um teste novo, é manutenção de um teste existente que este plano vai tocar).
- **`test_embedder.py`**: **risco de poluição de teste identificado** — `embed_texts`/`embed_query` são chamados de verdade nos testes atuais (só `langchain_ollama` é mockado via `sys.modules`), então o novo `record_timing()` embutido neles gravaria no `~/.mill-tools/model_timings.json` **real** da máquina do desenvolvedor durante `pytest`. Precisa de um fixture (`autouse` ou explícito) redirecionando `src.core.observatory.model_timing._store_path` para `tmp_path`, mesmo padrão já usado em `tests/gui/modules/observatory/` para isolar `gui.settings`/`activity._store_path`.
- **`status_tab.py`/`timing_section.py`**: construct-smoke (`MagicMock` page) confirmando as 3 seções renderizam com `load_timings` mockado retornando entradas sintéticas dos 3 domínios; seção vazia (sem entradas daquele domínio) mostra o texto "Nenhuma resposta registrada ainda" como hoje.
- **`cli/observatory.py`**: `_run_status` com `model_timings.json` mockado (arquivo em `tmp_path` ou `_answer_times`-style leitura direta mockada) — 3 blocos impressos, um por domínio.
- **`analytics_tab.py`**: teste existente (se houver) ajustado para `apply(stats)` sem `times_map`; nenhuma referência a timing sobrevive.

Cobertura alvo ≥ 90% em `core/observatory/model_timing.py` (mesmo padrão de `activity.py`, hoje 94-100%).

---

## 8. Critérios de aceitação

- Nenhuma dependência nova em `pyproject.toml` (só `langchain_core`, já instalado).
- `uv run pytest -m unit` verde e `ruff` limpo após cada commit.
- Uma pergunta na aba Conversa da IA, uma descrição de imagem (local **e** cloud) e uma indexação no RAG cada uma gera pelo menos 1 entrada nova em `~/.mill-tools/model_timings.json`, com o `domain` correto (`llm`/`vlm`/`embed`).
- A aba **Tempo de resposta** do Observatório (própria, não uma seção do Status) mostra 3 tabelas (LLM/VLM/embed) e 2 gráficos (LLM/VLM — embed só tabela).
- A aba Painel do hub IA não mostra mais nenhuma menção a tempo de resposta por modelo (só saúde do índice).
- `observatory status` (CLI) imprime a quebra por domínio.
- `ai_answer_times`/estimativa "tempo típico" da aba Conversa continuam funcionando exatamente como antes (nenhuma regressão).

---

## 9. Riscos e o que **não** fazer

Não introduzir `filelock` ou qualquer locking entre processos — mesmo risco (baixo, aceito) já presente em `activity.py`/`config.json`; introduzir uma dependência nova só para isso violaria a restrição do plano. Não migrar/backfillar `ai_answer_times` para o novo log — os no máximo 5 valores antigos por modelo não compensam a complexidade. Não unificar o branch Ollama local de `describe_image` com `make_llm()` — mudaria o `temperature` default do VLM local, fora de escopo. Não aplicar corte flat (`entries[-500:]`) no log novo — despejaria o histórico de VLM/embed sob volume alto de LLM; o corte tem que ser por bucket `(domain, model)`. Não esquecer o fixture de isolamento em `test_embedder.py` — sem ele, rodar a suíte de testes localmente escreve no `~/.mill-tools/model_timings.json` real do desenvolvedor.

---

## 10. Tabela-resumo de arquivos afetados

| Arquivo | Tipo | O que muda |
|---|---|---|
| `src/core/observatory/model_timing.py` | Novo | Log persistente `TimingEntry`, `record_timing`, `load_timings`, `timings_by_domain` |
| `tests/core/observatory/test_model_timing.py` | Novo | Testes do módulo acima |
| `src/llm_factory.py` | Modificado | `_TimingCallback`, `timing_callbacks()`, kwarg `domain` em `make_llm` |
| `tests/test_llm_factory.py` | Modificado | Cobertura do callback + kwarg `domain` |
| `src/core/image/describe.py` | Modificado | `domain="vlm"` (cloud) + `callbacks=` (local Ollama) |
| `tests/core/image/test_describe.py` | Modificado | Ajuste de mocks para os novos kwargs |
| `src/core/rag/embedder.py` | Modificado | Medição manual por lote em `embed_texts`/`embed_query` |
| `tests/core/rag/test_embedder.py` | Modificado | Fixture de isolamento de `model_timing._store_path` |
| `src/gui/modules/observatory/timing_section.py` | Novo | Componente reusável tabela+gráfico por domínio |
| `src/gui/modules/observatory/timing_tab.py` | Novo | Aba própria "Tempo de resposta" (revisão pós-implementação — não fica dentro do Status) |
| `src/gui/modules/observatory/status_tab.py` | Modificado (revertido) | Timing removido de volta; só gates/classificador/config |
| `src/gui/modules/observatory/view.py` | Modificado | 3ª aba manual "Tempo de resposta" |
| `tests/gui/modules/observatory/` | Modificado | Construct-smoke atualizado (`test_timing_tab.py` novo) |
| `src/cli/observatory.py` | Modificado | `_run_status` com quebra por domínio |
| `src/gui/modules/ai/analytics_tab.py` | Modificado | Remove seção de timing (mantém saúde do índice) |
| `src/gui/modules/ai/view.py` | Modificado | `analytics_tab.apply(stats)` sem `times_map` |
| `CLAUDE.md` | Modificado | Documenta `model_timing.py` e o novo arquivo em `~/.mill-tools/` |

---

## 11. Fontes

- [LangChain — Invocation config (callbacks em `RunnableConfig`)](https://docs.langchain.com/oss/python/langchain/models)
- [LangChain — BigQuery Callback Handler (latência nativa via callback, validação do idioma)](https://docs.langchain.com/oss/python/integrations/callbacks/google_bigquery)
- [LangChain — superfície de `Embeddings.embed_documents`/`embed_query` (sem `callbacks`/`run_manager` expostos)](https://docs.langchain.com/oss/python/integrations/embeddings/google_generative_ai)
