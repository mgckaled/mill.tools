# PR8 — Receitas / Automação (pipelines entre módulos)

> Plano de implementação detalhado. Corresponde ao **PR8** do roadmap revisado
> (Biblioteca → IA sobre corpus → **Receitas**). Conecta os módulos em **cadeias
> explícitas** — ex.: `URL → baixar áudio → normalizar → transcrever → analisar →
> exportar`. Generaliza o que hoje é o `run_pipeline` **hardcoded** da Transcrição
> (`src/gui/workers.py`) e as bridges manuais entre módulos.
>
> **Tese (contra o medo do Sonnet):** automação **não** exige redesenhar a
> orquestração do `app.py`. O core do projeto **já é puro e reutilizável** (o
> próprio CLAUDE.md afirma), o `run_queue_pipeline` já faz fila sequencial, e as
> bridges já passam payload. PR8 acrescenta só duas peças: um **registro de
> passos** (adaptadores finos sobre as funções de core) e um **runner sequencial**
> que encadeia output→input. O `navigate_to`/`Stack` permanece intocado.
>
> Princípios mantidos: **torch-free**, **core puro reutilizável por CLI e GUI**,
> **código em inglês / labels em PT-BR**, **Flet 0.85**.
>
> **Posição no roadmap:** último da série. Beneficia-se de tudo que veio antes
> (Tier 0, PR6 Biblioteca, PR7 IA) — uma receita pode terminar gravando na
> Biblioteca e até disparar um passo de IA — mas o **núcleo** (registro + runner +
> presets + CLI) **não depende** de PR6/PR7 e pode ser construído sobre os 5
> módulos atuais.

---

## 0. Skills do projeto a invocar durante a implementação

> Estes três skills vivem em `.claude/skills/` e são a fonte canônica dos padrões
> do projeto. **Invoque-os no Claude Code** ao tocar nas áreas correspondentes —
> cada fase abaixo aponta qual usar.

| Skill | Quando invocar neste PR | Fases |
|---|---|---|
| **`testing`** (`.claude/skills/testing/SKILL.md`) | Ao criar `tests/core/recipes/` — fixtures, mock de `subprocess`/core, marcadores `unit`/`integration`, padrão de mock de pipeline, isolamento de dirs e settings. | PR8.0, PR8.1, PR8.4 |
| **`cli`** (`.claude/skills/cli/SKILL.md`) | Ao adicionar o subcomando `recipe` em `src/cli/recipes.py` + dispatch em `main.py` (`_NON_TRANSCRIBE_CMDS`, `add_recipe_parser`/`run_recipe_cli`, `CLIEventBus`, mapeamento kebab→snake). | PR8.1 |
| **`design-system`** (`.claude/skills/design-system/SKILL.md`) | Ao construir o módulo GUI Receitas — factories (`segmented_selector`, `output_card`, `primary_button`, `spinner`), tokens (`Color`/`Space`/`Radius`/`Motion`/`Type`), `Cursor.*`, help system, e os quirks do Flet 0.85. | PR8.2, PR8.3 |

Referências inline a `→ skill X` aparecem ao longo do documento nos pontos exatos.

---

## 1. Objetivo e justificativa

Hoje, encadear operações é **manual**: o usuário baixa um áudio no módulo Áudio,
clica "Transcrever" (bridge), depois liga o switch de análise. Cada módulo é uma
ilha; a única cadeia automática que existe é o `run_pipeline` da Transcrição —
**hardcoded** (download → transcribe → format? → analyze? → prompt?).

PR8 transforma essa ideia em um recurso de primeira classe: **receitas** —
sequências nomeadas e reutilizáveis de passos, onde a saída de um passo alimenta a
entrada do próximo, atravessando módulos. Um clique roda
`YouTube → áudio → normalizar → transcrever → analisar → PDF`.

### O embrião já existe

`src/gui/workers.py::run_pipeline` **é** uma receita escrita à mão. PR8 a
generaliza: em vez de uma cadeia fixa em código, uma cadeia **declarada** (lista de
passos) executada por um runner genérico. (Reescrever a Transcrição como um preset
é possível, mas **não** é requisito — os dois podem coexistir.)

---

## 2. Escopo

**Dentro do PR8:**

- Modelo declarativo de **Receita** (lista ordenada de passos + params).
- **Registro de passos** (`step registry`): adaptadores finos que expõem cada
  operação de core com assinatura uniforme `step(inputs, params, ctx) → outputs`.
- **Runner sequencial** que encadeia output→input, emite eventos, respeita cancel,
  e roda em lote sobre múltiplas entradas.
- **Validação de coerência** de tipos entre passos (`produces`/`accepts`).
- **Presets** embutidos (receitas prontas que mostram o valor cross-módulo).
- **GUI**: rodar presets (PR8.2) e **construtor** de receitas (PR8.3).
- **Persistência** de receitas do usuário (`~/.mill-tools/recipes.json`).
- **Paridade CLI**: `mill recipe run/list`.

**Fora do PR8 (futuro):**

- Ramificações condicionais / loops / paralelismo (receitas são **lineares** no
  v1 — uma cadeia, não um DAG).
- Agendamento (rodar receita toda manhã) — encaixa depois via o sistema de tarefas
  agendadas, fora deste PR.
- Receitas que chamam serviços externos além do que os módulos já fazem.

---

## 3. Decisões de arquitetura

| Decisão | Escolha | Justificativa |
|---|---|---|
| Onde encadear | Adaptadores sobre **funções de core puro** (não sobre os workers da GUI) | Mantém `core/recipes/` puro e reutilizável por CLI e GUI; workers são acoplados a Flet/eventos. |
| Topologia | **Linear** (cadeia), não DAG | Cobre 95% dos casos pessoais; DAG multiplicaria a complexidade da GUI e do runner. Decisão consciente. |
| Reaproveitar runner? | Novo `execute_recipe`, **espelhando** `run_queue_pipeline` | `run_queue_pipeline` roda 1 op em N itens; receita roda N passos heterogêneos. Mesma anatomia de eventos (`progress_start`/`task_done`/cancel). |
| Identidade do passo | Chave `"module.op"` (ex.: `"audio.normalize"`) no registro | String serializável → receitas viram JSON; CLI e GUI compartilham o vocabulário. |
| Coerência de tipos | Cada passo declara `accepts`/`produces` (kinds) | `validate_recipe` rejeita `image.resize → transcription.transcribe` antes de rodar. Muito testável. |
| Mudanças no `app.py` | **Nenhuma** além de registrar o módulo | Sem rearquitetura de orquestração — o medo do Sonnet não se concretiza. |
| Intermediários | Gravados em `output/` normalmente (visíveis na Biblioteca); flag opcional "limpar intermediários" | Transparência > mágica; a Biblioteca (PR6) já é o navegador. |
| Falha parcial | `stop_on_error` (aborta no 1º erro, preserva intermediários) | Igual ao `run_queue_pipeline`; reporta qual passo falhou. |
| Dependência nova | **Zero** | Só composição de core existente + stdlib. |
| Validação externa | **N/A** | PR8 é arquitetura interna — não há lib/serviço externo a validar. |

---

## 4. Estrutura de arquivos

Espelhando `src/` ↔ `tests/`. Novos com `+`.

```
src/
├── core/
│   └── recipes/                      +  (core puro — sem Flet)
│       ├── __init__.py               +
│       ├── types.py                  +  Recipe, RecipeStep, StepSpec, StepContext, StepResult
│       ├── registry.py               +  STEP_REGISTRY: "module.op" → StepSpec(adapter, accepts, produces)
│       ├── runner.py                 +  execute_recipe(): encadeia passos, emite eventos, cancel, lote
│       ├── validate.py               +  validate_recipe(): coerência accepts/produces + params
│       ├── presets.py                +  PRESETS: receitas embutidas (showcase)
│       └── store.py                  +  load_recipes()/save_recipe() → ~/.mill-tools/recipes.json
├── gui/
│   └── modules/
│       └── recipes/                  +     → skill design-system
│           ├── __init__.py           +
│           ├── view.py               +  build_recipes_module(...) → Module
│           ├── form_view.py          +  lista de receitas + (PR8.3) construtor de passos
│           ├── worker.py             +  run_recipe_pipeline (execute_recipe em thread)
│           └── pipeline_log.py       +  vocab: recipe_start, step_start/done, step_error, task_done/error
└── cli/
    └── recipes.py                    +  add_recipe_parser() + run_recipe_cli()   → skill cli

tests/
└── core/
    └── recipes/                      +     → skill testing
        ├── __init__.py               +
        ├── test_registry.py          +  unit — cada StepSpec, accepts/produces
        ├── test_runner.py            +  unit — encadeamento, cancel, stop_on_error (core mockado)
        ├── test_validate.py          +  unit — receitas válidas/ inválidas
        └── test_presets.py           +  unit — todos os presets passam em validate_recipe
```

Arquivos **alterados:** `src/gui/app.py` (registro + `_HUB_IDS` ganha `"recipes"`),
`src/gui/home.py` (Receitas como **3º card de hub** — ver §11), `src/gui/settings.py`
(chaves), `main.py` (`"recipe"` em `_NON_TRANSCRIBE_CMDS`), `CLAUDE.md`/`README`/skills.

---

## 5. Modelo de dados — `types.py`

```python
"""Typed model for linear, cross-module automation recipes."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Logical payload kinds that flow between steps.
KIND_URL = "url"            # the initial input may be a URL
KIND_AUDIO = "audio"
KIND_VIDEO = "video"
KIND_IMAGE = "image"
KIND_PDF = "pdf"
KIND_TEXT = "text"          # transcription/extracted/ocr .txt
KIND_MARKDOWN = "markdown"  # analysis/digest .md


@dataclass(frozen=True, slots=True)
class RecipeStep:
    """One operation in a recipe: a registry key plus its parameters."""
    op: str                       # registry key, e.g. "audio.normalize"
    params: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Recipe:
    """An ordered, named chain of steps."""
    name: str
    steps: list[RecipeStep]
    description: str = ""


@dataclass(frozen=True, slots=True)
class StepContext:
    """Runtime context handed to every step adapter.

    Carries the full run history so multi-input steps can reach back for outputs
    the linear `current` no longer holds — e.g. burning a subtitle needs the
    original video (the recipe's initial input) *and* the .srt produced two steps
    earlier. `initial_inputs` and `outputs_by_op` cover both.
    """
    emit: Callable                        # emit(type, payload) → EventBus / CLIEventBus
    cancel_is_set: Callable[[], bool]
    initial_inputs: list                  # the recipe's original inputs ([url] or [Path, ...])
    outputs_by_op: dict[str, list[Path]]  # op key → that step's outputs, accumulated as the recipe runs


@dataclass(frozen=True, slots=True)
class StepSpec:
    """Registry entry: the adapter plus its type contract."""
    adapter: Callable             # (inputs: list[Path|str], params, ctx) -> list[Path]
    accepts: set[str]             # input kinds this step can consume
    produces: str                 # output kind this step emits
    label: str                    # PT-BR label for the GUI/CLI
```

> **Por que `StepContext` não tem `out_dir` (ajuste de revisão).** Cada adaptador
> escreve no **diretório canônico do seu módulo** (`AUDIO_SOURCE_DIR`,
> `AUDIO_PROCESSED_DIR`, `TRANSCRIPTIONS_TEXT_DIR`, … — já em `src/utils.py`), não
> num `out_dir` único passado pelo runner. Isso é o que mantém a **classificação da
> Biblioteca (PR6)** funcionando: o `scan_library` mapeia cada saída pelo seu root
> (`output/<kind>/...`). Um `out_dir` genérico jogaria tudo num lugar só e quebraria
> a classificação por kind. Em troca, o `ctx` ganha `initial_inputs`/`outputs_by_op`
> (histórico) para os passos multi-input — ver §7 e a nota do preset de legenda (§9).

---

## 6. Registro de passos — `registry.py`

O coração do PR8: **adaptadores finos** que dão assinatura uniforme às funções de
core heterogêneas (que têm assinaturas diferentes hoje). Cada adaptador chama a
função de core **pura** — nunca o worker da GUI — emitindo progresso pelo `ctx`.

```python
"""Uniform step adapters wrapping existing pure core functions."""
from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import (
    StepSpec, StepContext,
    KIND_URL, KIND_AUDIO, KIND_VIDEO, KIND_PDF, KIND_TEXT, KIND_MARKDOWN,
)


def _audio_download(inputs, params, ctx: StepContext) -> list[Path]:
    """URL → mp3 in the canonical audio/source dir. Wraps download_audio.

    Note: download_audio exposes progress via `progress_hook(dict)` (yt-dlp), a
    different shape from transcribe/analyze's `on_event`. The adapter normalizes
    it to ctx.emit so the step shows progress like every other.
    """
    from src.core.audio.downloader import download_audio
    from src.utils import AUDIO_SOURCE_DIR
    url = str(inputs[0])
    out = download_audio(
        url, AUDIO_SOURCE_DIR, fmt=params.get("fmt", "mp3"), embed_meta=False,
        progress_hook=lambda d: ctx.emit("progress_update", d),
    )
    return [out]


def _audio_normalize(inputs, params, ctx: StepContext) -> list[Path]:
    """audio → loudness-normalized audio. Wraps normalize_lufs.

    Note: normalize_lufs reports progress via `progress_cb(float 0..1)` — again a
    different shape from on_event; normalized to ctx.emit here.
    """
    from src.core.audio.normalizer import normalize_lufs
    from src.utils import AUDIO_PROCESSED_DIR
    out, _stats = normalize_lufs(
        inputs[0], AUDIO_PROCESSED_DIR, target_lufs=params.get("target_lufs", -14.0),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _transcribe(inputs, params, ctx: StepContext) -> list[Path]:
    """audio/video → transcription .txt (+ optional .srt/.vtt). Wraps transcribe.

    Returns [txt, *subtitle_paths]. transcribe() itself only returns elapsed time,
    so the adapter reconstructs the subtitle paths deterministically: the core
    writes them to TRANSCRIPTIONS_SUBTITLES_DIR / f"{output_path.stem}.{fmt}"
    (see transcriber.py). Returning them lets a later video.subtitle step reach
    the .srt via ctx.outputs_by_op["transcription.transcribe"].
    """
    from src import transcriber
    from src.utils import TRANSCRIPTIONS_TEXT_DIR, TRANSCRIPTIONS_SUBTITLES_DIR
    media = Path(inputs[0])                         # audio OR video (PyAV decodes video)
    out = TRANSCRIPTIONS_TEXT_DIR / f"transcription_{media.stem}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    subs = tuple(params.get("subtitles", ()))       # Tier 0
    transcriber.transcribe(
        audio_path=media, output_path=out,
        meta={"title": media.stem, "duration": 0}, url=str(media),
        model_size=params.get("model", "small"),
        language=None if params.get("language", "auto") == "auto" else params["language"],
        threads=params.get("threads", 2), beam_size=params.get("beam_size", 1),
        force_overwrite=True,
        subtitle_formats=subs,
        on_event=lambda t, s, p: ctx.emit(t, p),
    )
    sub_paths = [TRANSCRIPTIONS_SUBTITLES_DIR / f"{out.stem}.{fmt}" for fmt in subs]
    return [out, *sub_paths]


def _analyze(inputs, params, ctx: StepContext) -> list[Path]:
    """transcription/text → analysis .md. Wraps analyzer.analyze."""
    from src import analyzer
    out = analyzer.analyze(input_path=Path(inputs[0]),
                           model_name=params.get("model", "qwen7b-custom"),
                           on_event=lambda t, s, p: ctx.emit(t, p))
    return [out]


# ... análogos: audio.convert/denoise, video.*, image.*, document.*(merge/.../ocr),
#     transcription.format/prompt, ai.answer (PR7). Cada um é um wrapper de ~5 linhas.
#
# Sutilezas de assinatura confirmadas contra o código atual (ajuste de revisão):
#   • transcription.format → formatter.format_transcription reescreve o .txt
#     IN-PLACE e retorna `str | None` (o texto), não um Path. O adaptador deve
#     retornar [input_path] (o mesmo .txt, agora formatado), descartando a string.
#   • transcription.transcribe aceita áudio E vídeo: o faster-whisper decodifica
#     vídeo via PyAV (ver CLAUDE.md). Por isso accepts = {KIND_AUDIO, KIND_VIDEO}
#     abaixo — uma receita "vídeo → transcrever" não precisa de extract_audio.
#   • ai.answer (PR7) → chat.answer() retorna um AnswerResult (texto + fontes),
#     não um Path; o adaptador grava o texto num .md (ex.: TRANSCRIPTIONS_ANALYSIS_DIR
#     ou output/ai/) para produzir uma saída do kind MARKDOWN. Requer índice já
#     construído + embedder.is_available() (gate do PR7); senão o passo falha e o
#     stop_on_error reporta. PR8.4.

STEP_REGISTRY: dict[str, StepSpec] = {
    "audio.download":  StepSpec(_audio_download,  {KIND_URL},   KIND_AUDIO, "Baixar áudio"),
    "audio.normalize": StepSpec(_audio_normalize, {KIND_AUDIO}, KIND_AUDIO, "Normalizar volume"),
    "transcription.transcribe": StepSpec(_transcribe, {KIND_AUDIO, KIND_VIDEO}, KIND_TEXT, "Transcrever"),
    "transcription.format":     StepSpec(_format,  {KIND_TEXT}, KIND_TEXT, "Formatar"),   # in-place → [input_path]
    "transcription.analyze":    StepSpec(_analyze,    {KIND_TEXT}, KIND_MARKDOWN, "Analisar"),
    "document.ocr":    StepSpec(_ocr,  {KIND_PDF}, KIND_TEXT, "OCR"),          # Tier 0
    # ... demais operações dos 5 módulos
}
```

> **Princípio:** o adaptador é a **única** camada que conhece a assinatura exata da
> função de core. Adicionar uma operação à automação = um wrapper de poucas linhas
> + uma entrada no `STEP_REGISTRY`. As funções de core **não mudam**.
>
> **Normalização de callbacks de progresso (ajuste de revisão):** o core não tem um
> estilo único de callback. `transcribe`/`analyze` usam `on_event(type, stage,
> payload)`; `download_audio` usa `progress_hook(dict)`; `normalize_lufs` usa
> `progress_cb(float)`. A camada de adaptador é onde esses três estilos viram
> `ctx.emit(...)` — sem isso, os passos de download/normalize ficariam sem barra de
> progresso. Documentar o estilo de cada core no wrapper correspondente.

---

## 7. Runner sequencial — `runner.py`

Espelha a anatomia de eventos do `run_queue_pipeline` (`progress_start`,
`task_done`/`task_error`, checagem de cancel), mas itera **passos heterogêneos**,
encadeando `outputs[N] → inputs[N+1]`. Loop externo opcional dá **lote** (aplicar a
receita a vários arquivos).

```python
"""Sequential recipe executor: pipes each step's output into the next."""
from __future__ import annotations

import logging
from pathlib import Path

from src.core.recipes.registry import STEP_REGISTRY
from src.core.recipes.types import Recipe, StepContext
from src.core.recipes.validate import validate_recipe


def execute_recipe(
    recipe: Recipe,
    initial_inputs: list,           # [url] or [Path, ...]
    *,
    initial_kind: str,              # kind of initial_inputs (url/audio/video/pdf/...)
    emit,                           # emit(type, payload)
    cancel_is_set,                  # () -> bool
) -> list[Path]:
    """Run every step in order, feeding outputs forward. Returns final outputs.

    Adapters write to their module's canonical output dir (no shared out_dir),
    so PR6's Library classifies each artifact by kind. A history of every step's
    outputs is kept in `outputs_by_op` for multi-input steps (see §9).
    """
    # Guard: never index STEP_REGISTRY blindly — a stale user recipe may name an
    # op that was renamed/removed. validate_recipe catches unknown ops + kind
    # mismatches before any CPU is spent.
    errors = validate_recipe(recipe, initial_kind)
    if errors:
        emit("task_error", {"message": "Receita inválida: " + "; ".join(errors)})
        return []

    emit("recipe_start", {"name": recipe.name, "total_steps": len(recipe.steps)})
    current: list = initial_inputs
    outputs_by_op: dict[str, list[Path]] = {}

    for idx, step in enumerate(recipe.steps, 1):
        if cancel_is_set():
            emit("task_error", {"message": "Cancelado pelo usuário."})
            return []
        spec = STEP_REGISTRY[step.op]   # safe: validate_recipe ran above
        emit("step_start", {"op": step.op, "label": spec.label,
                            "idx": idx, "total": len(recipe.steps)})
        ctx = StepContext(emit=emit, cancel_is_set=cancel_is_set,
                          initial_inputs=initial_inputs, outputs_by_op=outputs_by_op)
        try:
            current = spec.adapter(current, step.params, ctx)
        except Exception as exc:
            logging.getLogger(__name__).warning("[!] Step '%s' failed: %s", step.op, exc)
            emit("step_error", {"op": step.op, "idx": idx, "message": str(exc)})
            emit("task_error", {"message": f"Falha no passo '{spec.label}': {exc}"})
            return []
        outputs_by_op[step.op] = [Path(p) for p in current]
        emit("step_done", {"op": step.op, "idx": idx, "total": len(recipe.steps),
                          "outputs": [str(p) for p in current]})

    emit("task_done", {"output_paths": [str(p) for p in current]})
    return [Path(p) for p in current]
```

> **Validação antes de iterar (ajuste de revisão):** o runner chama
> `validate_recipe` no topo. Antes, `STEP_REGISTRY[step.op]` indexava direto e
> estouraria `KeyError` numa receita salva que referenciasse uma op renomeada;
> agora isso vira uma mensagem limpa de "receita inválida".
>
> **Histórico para multi-input (ajuste de revisão):** `outputs_by_op` acumula as
> saídas de cada passo, e `ctx.initial_inputs` guarda as entradas originais. Um
> passo como `video.subtitle` (queimar legenda) lê o vídeo de `ctx.initial_inputs`
> (ou de um passo anterior via `ctx.outputs_by_op`) e a `.srt` do passo de
> transcrição — sem isso, a cadeia linear `current` já teria descartado ambos.
>
> Para **lote**, envolver `execute_recipe` num loop externo sobre N entradas
> reusando `queue_progress` (mesmo evento do `_pipeline_runner`) — "Item 2/5".
> Cancel é checado **entre passos** (nunca interrompe o Whisper no meio), igual ao
> resto do projeto.

---

## 8. Validação de coerência — `validate.py`

```python
def validate_recipe(recipe: Recipe, initial_kind: str) -> list[str]:
    """Return a list of human-readable errors (empty = valid).

    Checks that each step's `accepts` includes the kind produced by the previous
    step (or the initial input kind for the first step), and that every op exists.
    """
    errors: list[str] = []
    produced = initial_kind
    for i, step in enumerate(recipe.steps, 1):
        spec = STEP_REGISTRY.get(step.op)
        if spec is None:
            errors.append(f"Passo {i}: operação desconhecida '{step.op}'")
            break
        if produced not in spec.accepts:
            errors.append(
                f"Passo {i} ({spec.label}): não aceita '{produced}' "
                f"(aceita: {', '.join(sorted(spec.accepts))})"
            )
            break
        produced = spec.produces
    return errors
```

Usado pela GUI **ao vivo** (desabilita "Rodar" e mostra o erro) e pelo runner antes
de executar. `test_presets.py` roda `validate_recipe` em **todos** os presets — um
preset inválido quebra o teste.

---

## 9. Presets embutidos — `presets.py`

A vitrine do valor cross-módulo. Receitas prontas, type-coerentes por construção:

```python
PRESETS: list[Recipe] = [
    Recipe(
        name="YouTube → transcrição completa",
        description="Baixa o áudio, transcreve, formata e analisa.",
        steps=[
            RecipeStep("audio.download"),
            RecipeStep("transcription.transcribe", {"model": "small", "subtitles": ["srt", "vtt"]}),
            RecipeStep("transcription.format"),
            RecipeStep("transcription.analyze", {"model": "gemini-2.5-flash"}),
        ],
    ),
    Recipe(
        name="Limpar áudio",
        description="Baixa/converte, reduz ruído e normaliza o volume.",
        steps=[
            RecipeStep("audio.download"),
            RecipeStep("audio.denoise"),
            RecipeStep("audio.normalize", {"target_lufs": -14.0}),
        ],
    ),
    Recipe(
        name="PDF escaneado → resumo",
        description="OCR do PDF e análise por LLM.",
        steps=[
            RecipeStep("document.ocr", {"lang": "por"}),     # Tier 0
            RecipeStep("transcription.analyze", {"model": "qwen7b-custom"}),
        ],
    ),
    Recipe(
        name="Vídeo → legendado",
        description="Transcreve o vídeo, gera .srt e embute no vídeo (mux).",
        steps=[
            # initial_kind = video; transcribe aceita vídeo (PyAV), produz texto + .srt.
            RecipeStep("transcription.transcribe", {"subtitles": ["srt"]}),
            RecipeStep("video.subtitle", {"mode": "soft"}),  # Tier 0 — multi-input via ctx (ver nota)
        ],
    ),
]
```

> **Nota multi-input — "Vídeo → legendado" (reescrita na revisão).** O passo de
> embutir legenda precisa de **dois inputs de origens diferentes**: o vídeo
> original e a `.srt`. Numa cadeia linear pura isso **não funciona**, porque depois
> da transcrição o `current` só carregaria o texto — o vídeo já teria sido
> descartado. A solução é o **histórico no `StepContext`** (§7): o adaptador
> `_video_subtitle` lê o vídeo de `ctx.initial_inputs[0]` e a `.srt` de
> `ctx.outputs_by_op["transcription.transcribe"]` (onde o `_transcribe` agora
> devolve `[txt, srt]`). Como `transcribe` aceita vídeo, o preset **dispensa**
> `video.extract_audio`. O `accepts` de `video.subtitle` é `{KIND_TEXT}` (o kind que
> a cadeia carrega após transcrever) — a validação linear continua válida, e o
> adaptador pega os caminhos reais do `ctx`. Documentar isso no registro do passo:
> é o único caso multi-input do v1.

---

## 10. GUI — módulo Receitas (`src/gui/modules/recipes/`)  → skill `design-system`

Segue o contrato `Module`. Layout split, faseado:

```
┌────────────────────────┬──────────────────────────────────────┐
│ FORM (380px)           │  PAINEL                                │
│ • Receitas (cards):    │  • Progresso passo-a-passo:            │
│   presets + do usuário │    "Passo 2/4 — Transcrever"           │
│ • Entrada: URL/arquivos│  • Log + barra (EventBus)              │
│ • [Rodar receita]      │  • Resultados (output_card por saída,  │
│ • (PR8.3) Construtor:  │    com bridge p/ Biblioteca/módulos)   │
│   + adicionar passo ▾  │                                        │
│   [passos arrastáveis] │                                        │
└────────────────────────┴──────────────────────────────────────┘
```

> (Esquema textual de layout, não um diagrama.)

- **PR8.2 (rodar presets):** lista de receitas como cards (reusa `output_card`/
  card pattern → skill `design-system`); `InputSource` (URL + FilePicker, já existe
  em `components/input_source.py`); `primary_button("Rodar receita")`; o `worker`
  chama `execute_recipe` em thread; o painel mostra `step_start/done` traduzidos
  pelo `pipeline_log.py` (→ skill `design-system` para tokens/cores de log).
- **PR8.3 (construtor):** um editor de sequência — `+ Adicionar passo` abre um
  `segmented_selector`/menu com as ops válidas **dado o kind atual** (usa
  `validate_recipe` ao vivo: só oferece passos cujo `accepts` casa com o `produces`
  do passo anterior); botão de remover por passo. Salvar → `store.save_recipe`.
  - **Reordenar passos.** O `ft.ReorderableListView` (drag, handler `on_reorder`)
    **não está catalogado na skill `design-system`** — única fonte de quirks
    confiável e atual (a skill lista vários `ft.*` que *não* existem no 0.85.2).
    **Verificar empiricamente antes de depender dele:**
    `uv run python -c "import flet as ft; print(ft.ReorderableListView)"`. Se
    existir, **adicionar a linha correspondente à skill `design-system`** (com
    `on_reorder`) — aí vira referência canônica para o Claude Code. Se **não**
    existir, usar **fallback** sem drag: botões ↑/↓ por passo que trocam posições na
    lista (trivial, zero dependência nova). Não reintroduzir `docs/GUI_FLET_PR678.md`
    como fonte — está desatualizado e fora do contexto do Claude Code.
- **Bloqueio de navegação:** `pipeline_running[0]` durante a execução (guard já
  existe). Cancel entre passos.
- **Bridge:** resultados finais ganham botões "Abrir na Biblioteca" (PR6) /
  "Enviar para módulo" reusando `nav[0](...)`.

Quirks Flet 0.85 (→ skill `design-system`): sem `ink=True` em cards (usar
`GestureDetector`+`Cursor.interactive`); abas/menus manuais (sem `ft.Tabs`);
`ft.ListView` lazy para o log; um `page.update()` por evento.

---

## 11. Registry e Home

### 11.1 `app.py`

> **Precedente do PR6/PR7 (hub no AppBar):** Receitas também é um módulo "meta"
> → **fora da rail**, como botão-hub no AppBar. A rail segue com as **5 ferramentas
> de processamento**; os 3 módulos transversais (Biblioteca · IA · Receitas) ficam
> no AppBar.

```python
from src.gui.modules.recipes.view import build_recipes_module
_recipes = build_recipes_module(page, bus, cancel_event, pipeline_running, nav)

MODULES = [_audio, _video, _image, _transcription, _document, _library, _ai, _recipes]
_RAIL_MODULES = [m for m in MODULES if m.id not in ("library", "ai", "recipes")]  # rail = 5
```

- No AppBar, um `TextButton` **"Receitas"** junto aos de **"Biblioteca"** e **"IA"**
  (dourado quando ativo); `_rail_index("recipes")` → `None`. Ícone sugerido:
  `ft.Icons.ACCOUNT_TREE_OUTLINED` ou `ft.Icons.BOLT`.
- **`_HUB_IDS` passa a `("library", "ai", "recipes")`** (hoje `("library", "ai")`).
  É a constante que tira os hubs da rail e os mapeia para `None` em `_rail_index`.
- Com 3 botões-hub no AppBar, vale agrupá-los/espaçá-los (ex.: um separador antes
  do trio) para não competir com o wordmark.

### 11.2 `home.py` — 5 ferramentas + 3 hubs

A Home (launcher) **mantém o padrão atual do PR6/PR7** descrito no CLAUDE.md: duas
zonas visualmente distintas — **5 ferramentas** (cards verticais, grade **3+2**:
Áudio, Vídeo, Imagens, **Transcrição**, Documentos) e os **hubs** (cards horizontais
mais largos, borda dourada + selo "HUB"). PR8 apenas **acrescenta Receitas como 3º
hub**, ao lado de Biblioteca e IA — a zona de hubs vai de 2 para 3 cards. → skill
`design-system`.

> **Correção (resolvida na revisão):** uma versão anterior deste plano agrupava
> "Transcrição" com Biblioteca/IA em "Acervo & Inteligência" e propunha "8 cards
> 4×2 uniformes". Está **errado**. Transcrição é uma das **5 ferramentas** (rail);
> os **3 hubs** são exatamente **Biblioteca · IA · Receitas**. A distinção visual
> ferramenta/hub do CLAUDE.md (vertical vs. horizontal com selo HUB) é **mantida** —
> não se achata tudo numa grade uniforme.

---

## 12. Persistência

`settings.py` (`_DEFAULTS`):

```python
"last_recipe": "",                 # nome da última receita rodada
"recipe_clean_intermediates": False,
```

- **Receitas do usuário:** `~/.mill-tools/recipes.json` (presets embutidos +
  custom). Mesmo diretório do `config.json` — nada novo no projeto.
- **Saídas:** intermediárias e finais em `output/...` (visíveis na Biblioteca);
  flag opcional para apagar intermediárias ao fim.

---

## 13. Paridade CLI — `src/cli/recipes.py`  → skill `cli`

Seguindo o padrão da skill `cli` (novo subcomando = `add_recipe_parser` +
`run_recipe_cli`, `"recipe"` em `_NON_TRANSCRIBE_CMDS`, `CLIEventBus`,
`install_log_handler=False`):

```bash
uv run main.py recipe list                                   # lista presets + do usuário
uv run main.py recipe run "Limpar áudio" <URL_OR_FILE>       # roda por nome
uv run main.py recipe run "YouTube → transcrição completa" <URL> --model medium
```

`run_recipe_cli` resolve a receita (presets + `store.load_recipes`), constrói
`initial_inputs` **e** `initial_kind` via `resolve_input` (já existe em
`cli/transcription.py` — retorna `(kind, value)`), cria um `CLIEventBus` e chama
`execute_recipe(recipe, initial_inputs, initial_kind=kind, emit=..., cancel_is_set=...)`.
O core é o mesmo da GUI — paridade barata. (Mesma assinatura usada pelo `worker.py`
da GUI.)

---

## 14. Testes  → skill `testing`

Core unit-testável mockando as funções de core (sem ffmpeg/Whisper/rede). GUI fora
da cobertura. Invocar a skill `testing` para fixtures, marcadores e padrões de mock.

- `test_registry.py`: cada `StepSpec` tem `adapter` callable, `accepts` não-vazio,
  `produces` válido; chaves seguem `"module.op"`.
- `test_runner.py`: **encadeamento** — registrar specs falsas (adapters que
  retornam `[tmp_path/"x"]`) e asseverar que o output de um vira input do próximo;
  **cancel** entre passos (`cancel_is_set` retorna True no 2º) → `task_error`;
  **stop_on_error** (adapter levanta) → `step_error`+`task_error`, passos seguintes
  não rodam; ordem dos eventos (`recipe_start` → `step_start/done`×N → `task_done`).
  Mockar os adapters reais via `mocker.patch.dict(STEP_REGISTRY, {...})`.
- `test_validate.py`: cadeia coerente → `[]`; `image.resize → transcription.transcribe`
  → erro de kind; op inexistente → erro; primeiro passo incompatível com
  `initial_kind`.
- `test_presets.py`: **todos** os `PRESETS` passam em `validate_recipe` com o
  `initial_kind` declarado — garante que nenhum preset embutido está quebrado.
- Adaptadores individuais: testar 1–2 com a função de core **mockada** (ex.:
  `_transcribe` com `transcriber.transcribe` mockado, asserir que monta `meta`/
  `output_path` e repassa `subtitle_formats`). Padrão de mock de pipeline da skill
  `testing` (mockar no ponto de uso).

Alvo ≥ 90% no core novo. `store.py` (load/save JSON) com round-trip em `tmp_path`
+ isolamento de `~/.mill-tools` via `monkeypatch` (padrão da skill `testing`).

---

## 15. Convenções a respeitar

- `core/recipes/` **puro** — adapters chamam **core**, nunca workers de GUI.
- Inglês em docstrings/logs; PT-BR em labels (`StepSpec.label`, nomes de preset,
  descrições) e textos de GUI.
- Reusar `EventBus`/`CLIEventBus`, `resolve_input`, `InputSource`, design system —
  não reimplementar.
- Logging dedicado; nunca `print()`. Ruff limpo; `uv run pytest -m unit` verde.
- Ao tocar cada área, **invocar o skill correspondente** (§0).

---

## 16. Faseamento sugerido

| Fase | Entrega | Skill | Testável isolado |
|---|---|---|---|
| **PR8.0** | `core/recipes/` (`types`, `registry` com os passos dos 5 módulos, `runner`, `validate`) + testes | `testing` | ✅ sem GUI |
| **PR8.1** | `presets` + `store` + CLI `recipe run/list` | `cli`, `testing` | ✅ core |
| **PR8.2** | GUI: rodar presets (lista + execução + progresso passo-a-passo) | `design-system` | manual |
| **PR8.3** | GUI: construtor de receitas (editor de sequência + validação ao vivo + salvar) | `design-system` | manual |
| **PR8.4** | Lote (receita sobre N arquivos) + flag de limpar intermediários + passos de PR7 (`ai.answer`) | `testing` | ✅ core |

PR8.0–8.1 entregam automação real **via CLI** antes de qualquer GUI.

---

## 17. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Assinaturas heterogêneas de core | Absorvidas na camada de adaptadores (registro); core não muda. |
| Passos multi-input (ex.: queimar legenda) | Resolvido pelo **histórico no `StepContext`** (`initial_inputs` + `outputs_by_op`, §7): o adaptador busca o vídeo original e a `.srt` produzida em passos anteriores. A cadeia linear `current` sozinha **não** bastava. Validação trata o kind carreado (1º input). |
| Receita longa lenta na MX150/i5 | Sequencial; cancel entre passos; progresso por passo; passos de GPU (Whisper) serializados. |
| Falha no meio da cadeia | `stop_on_error`: aborta, preserva intermediários, reporta o passo. |
| Proliferação de arquivos intermediários | Visíveis na Biblioteca (PR6); flag "limpar intermediários". |
| Explosão de params na GUI | Presets fixam params sensatos; o construtor expõe só o essencial por passo. |
| Incoerência de tipos | `validate_recipe` ao vivo (GUI) e antes de rodar (runner); `test_presets` cobre os embutidos. |
| Escopo crescendo para DAG | v1 **linear** por decisão; ramificação/loop ficam fora — reavaliar só se houver demanda real. |

---

## 18. Definição de pronto (DoD)

- `uv run pytest -m unit` verde; cobertura do core novo ≥ 90% (→ skill `testing`).
- Ruff limpo; docstrings/logs em inglês; labels/presets PT-BR.
- Módulo Receitas como **3º hub** no AppBar (fora da rail, junto de Biblioteca/IA) e
  **3º card de hub** na Home (mantendo a zona ferramentas 3+2 | hubs), respeitando
  `pipeline_running`.
- É possível: rodar um preset (URL/arquivo → cadeia → resultados), ver progresso
  passo-a-passo, construir e salvar uma receita com validação de coerência, e rodar
  pela CLI (`recipe run/list`).
- `validate_recipe` cobre todos os presets; nenhum preset quebrado.
- Sem dependência nova; projeto permanece torch-free.
- `CLAUDE.md`/`README`/skills atualizados (novo módulo, `core/recipes/`, contagem
  de testes). As três skills do projeto (`cli`, `design-system`, `testing`) foram
  **invocadas** nas fases correspondentes.

---

## 19. Atualização de docs + consequências de PR6/PR7

> Tudo que **não estava previsto**, **precisa melhorar** ou é **consequência da
> implementação de PR6/PR7** foi consolidado aqui. As únicas fontes confiáveis e
> atuais são o **CLAUDE.md** e as **3 skills** (`cli`, `design-system`, `testing`) —
> atualizadas dentro das próprias sessões de PR6/PR7. `docs/GUI_FLET_PR678.md` está
> desatualizado e **não** deve ser usado como contexto.

### 19.1 Ajustes de design incorporados nesta revisão

Correções já refletidas nas seções acima (não são trabalho novo — são o plano
corrigido):

- **`StepContext` sem `out_dir`; com `initial_inputs` + `outputs_by_op`** (§5/§7).
  Adaptadores escrevem nos **dirs canônicos** (`src/utils.py`) para a Biblioteca
  classificar; o histórico habilita passos **multi-input**.
- **Runner valida antes de iterar** (§7) — sem `KeyError` em receita salva com op
  renomeada.
- **Normalização de progresso na camada de adaptador** (§6) — `on_event` /
  `progress_hook` / `progress_cb` convergem para `ctx.emit`.
- **`transcription.format` é in-place e retorna `str`** → adaptador devolve
  `[input_path]` (§6).
- **`transcribe` aceita `{KIND_AUDIO, KIND_VIDEO}`** (PyAV decodifica vídeo) — preset
  de legenda dispensa `extract_audio` (§6/§9).
- **`_transcribe` retorna `[txt, *legendas]`** para o passo de queima alcançar a
  `.srt` via `ctx.outputs_by_op` (§6/§9).
- **`ai.answer` retorna `AnswerResult`** (não Path) → adaptador grava `.md` (§6, §19.6).
- **Home = 5 ferramentas (3+2) + 3 hubs** (Transcrição é ferramenta) (§11.2).
- **`run_recipe_pipeline`** (não `start_…`) para casar com `run_*_pipeline` (§4).
- **`ReorderableListView` verificado empiricamente + fallback ↑/↓** (§10).

### 19.2 CLAUDE.md — o que atualizar ao concluir

- **Estrutura:** adicionar `src/core/recipes/` (types/registry/runner/validate/
  presets/store) e `src/gui/modules/recipes/` (view/form_view/worker/pipeline_log) à
  árvore; adicionar `src/cli/recipes.py`.
- **Sistema de módulos:** passa a **8 módulos**, **3 hubs** (Biblioteca · IA ·
  **Receitas**). Atualizar as frases que dizem "2 hubs" e `_HUB_IDS`/`_RAIL_MODULES`.
- **Nova subseção "Módulo Receitas"** (registro de passos + runner linear + presets
  + store + validação accepts/produces).
- **Home Screen:** a descrição "5 ferramentas (3+2) + 2 hubs" vira **+ 3 hubs**.
- **Eventos do pipeline:** nova tabela/linhas para `recipe_start`, `step_start`,
  `step_done`, `step_error`, e o reuso de `task_done`/`task_error`/`queue_progress`
  (lote). `module_id = "recipes"`.
- **Comandos:** bloco com `recipe list` / `recipe run`. `_NON_TRANSCRIBE_CMDS` ganha
  `"recipe"`.
- **Roadmap:** marcar PR8 (faseado 8.0→8.4). **Contagem de testes e cobertura
  agregada** atualizadas após PR8.

### 19.3 Skill `cli` — o que atualizar

- Incluir `"recipe"` no `_NON_TRANSCRIBE_CMDS` mostrado no topo e em `src/cli/`.
- **Nova seção `## Subcomando recipe`**: `recipe list` / `recipe run "<nome>"
  <URL_OR_FILE>`; resolve presets + `store.load_recipes`; `initial_inputs`+
  `initial_kind` via `resolve_input`; usa `CLIEventBus` + `install_log_handler=False`
  e chama `execute_recipe` (mesmo core da GUI). Diferente de `library`/`ai`: **usa**
  pipeline/eventos (tem runner), então segue o padrão dos runners normais.
- Citar `tests/cli/test_recipe_cli.py` na lista de arquivos de teste.

### 19.4 Skill `design-system` — o que atualizar

- **`ft.ReorderableListView`**: hoje **ausente** da tabela de quirks. Após a
  verificação (§10), **adicionar uma linha** confirmando-o (`on_reorder` reordena a
  lista) **ou** registrando-o como inexistente no 0.85.2 (e então o fallback ↑/↓ é o
  padrão). É a peça que falta para o PR8.3 ter fonte canônica.
- Se nascer um factory novo (ex.: `step_row` / card de receita), documentá-lo na
  tabela de Component Factories.

### 19.5 Skill `testing` — o que atualizar

- Adicionar `tests/core/recipes/` (`test_registry`, `test_runner`, `test_validate`,
  `test_presets`) à árvore de arquivos e à tabela de cobertura (alvo ≥ 90%).
- Documentar os **padrões de mock** do PR8: `mocker.patch.dict(STEP_REGISTRY,
  {...})` com adaptadores falsos que retornam `[tmp_path/"x"]` (encadeamento,
  cancel, stop_on_error, ordem de eventos); isolamento de `~/.mill-tools/recipes.json`
  via `monkeypatch` (mesmo padrão de `settings.py`); teste de 1–2 adaptadores com a
  função de core mockada no ponto de uso.
- Citar `tests/cli/test_recipe_cli.py` na seção de testes CLI.

### 19.6 Consequências de PR6 (Biblioteca) sobre PR8

- **Classificação por root** — os adaptadores devem gravar nos dirs canônicos
  (§5/§19.1) para os intermediários aparecerem com o kind certo na Biblioteca.
- **Auto-refresh ao vivo** — a Biblioteca re-escaneia em `task_done` quando visível
  (PR6). O `task_done` do runner dispara isso de graça: ao fim de uma receita, a
  Biblioteca já mostra as novas saídas.
- **Categoria "Processado"** agrupa processed+text+analysis+digest — os
  intermediários de receita caem aí naturalmente.
- **Bridges/visor** — o painel de resultados reusa `output_card` + `nav[0](...)` e o
  visor in-app de `.md`/`.txt`; nada novo a construir.

### 19.7 Consequências de PR7 (IA) sobre PR8

- **`ai.answer` (passo opcional, PR8.4)** — `chat.answer()` retorna `AnswerResult`
  (texto + fontes), **não** um Path; o adaptador serializa o texto num `.md`
  (KIND_MARKDOWN). Requer **índice construído** (`build_index`) e
  `embedder.is_available()` (gate do PR7, Ollama `nomic-embed-custom` no ar) — senão
  o passo falha e o `stop_on_error` reporta. Opcional: o adaptador rodar `index`
  antes, ou exigir índice pré-existente.
- **`module_id`** — um passo `ai.answer` dentro de uma receita emite sob
  `module_id="recipes"` (o do runner), **não** `"ai"`. O módulo IA é auto-contido e
  assina os próprios eventos; a receita não reaproveita aquele painel.
- **Embeddings sempre locais** — mantém o princípio torch-free; Gemini só opcional no
  passo de resposta, como no PR7.

---

## Apêndice — Decisões internas resolvidas (sem validação externa)

PR8 não introduz biblioteca ou serviço externo — portanto **não há ponto técnico
externo a validar via web/Context7**. Os "pontos em aberto" eram decisões de design,
resolvidas aqui:

- **Linear, não DAG** — cadeia simples cobre os casos pessoais; DAG fica fora.
- **Adapters sobre core puro, não sobre workers** — preserva pureza e paridade CLI/GUI.
- **Runner próprio espelhando `run_queue_pipeline`** — mesma anatomia de eventos,
  semântica diferente (N passos × 1 item, com lote opcional N itens).
- **Coerência por `accepts`/`produces`** — validação barata e testável, evita
  cadeias sem sentido antes de gastar CPU.
- **Sem mudança no `app.py`** além de registrar o módulo — a automação **não**
  exige rearquitetar a orquestração, contrariando a premissa pessimista inicial.

> Com PR8, a série de planos fecha: **Tier 0 → PR6 (Biblioteca) → PR7 (IA) → PR8
> (Receitas)**. Juntos cobrem o arco "processar mídia → recuperar conteúdo →
> raciocinar sobre ele → automatizar a cadeia inteira".
