# Plano de Refatoração — Prioridade Alta

> **Alvo:** mill.tools · **Execução:** via Claude Code
> **Escopo:** dois refactors de alto impacto que atacam a maior parte da duplicação e do "god file" do projeto.
> **Regra de ouro:** `src/core/` permanece puro (sem Flet). Rodar `uv run pytest -m unit` ao fim de cada etapa. Atenção aos quirks do Flet 0.85 listados no `CLAUDE.md`.

> ⚠️ **Coordenação com `REFACTORING.md` (plano de CLI).** Este plano NÃO roda primeiro. Ordem combinada acordada:
> **CLI Fase 0** (corrige bugs em `utils.py`; autossuficiente) → **CLI Fase 2** (extrai `AudioArgs/VideoArgs/ImageArgs` para `src/core/<m>/args.py`) → **Refactor A** (este doc) → **CLI Fase 1** (CLIEventBus) → **Refactor B** (este doc) → CLI Fases 3–5.
> Pré-requisitos detalhados em cada refactor abaixo.

---

## Refactor A — Runner base para os workers (audio / video / image)

> 🔗 **Pré-requisito: CLI Fase 2 (extração dos Args) deve vir ANTES deste refactor.**
> Hoje cada worker faz `from src.gui.modules.<m>.form_view import <M>Args` — os workers dependem da GUI só pelo dataclass. A CLI Fase 2 move `AudioArgs/VideoArgs/ImageArgs` para `src/core/<m>/args.py`; só então o worker (e o `_pipeline_runner`) ficam livres de Flet — o que torna este refactor e o teste dos workers (F3 do Plano 2) viáveis sem arrastar Flet. Fazer A antes da Fase 2 obrigaria a refazer os imports depois.
>
> ⛓️ **Contrato rígido de eventos.** A CLI Fase 1 (`CLIEventBus`) mapeia `type` e chaves de `payload` exatos (tabela em `REFACTORING.md`). A invariante "preservar a forma dos payloads" deixa de ser recomendação e passa a ser **obrigatória**: o Refactor A não pode renomear nenhum tipo de evento nem chave (`progress_update.current`, `queue_progress.current_item`, `*_op_done.elapsed`/`src_size_bytes`/`out_size_bytes`, etc.).

### Problema

`src/gui/modules/{audio,video,image}/worker.py` repetem o mesmo esqueleto:

- closure `emit(type, stage, payload)` → `bus.emit(..., module_id=_MODULE_ID)`
- instalação/remoção do `LogEventHandler` (addHandler, setLevel INFO, capar libs ruidosas, `removeHandler` no `finally`)
- `emit("progress_start")` + loop `for idx, item in enumerate(args.items, 1)`
- checagem de `cancel_event` no topo e no fim de cada item
- `emit("queue_progress", ...)` com o mesmo payload
- `try/except Exception → task_error` e `emit("task_done", {"output_paths": ...})`
- funções utilitárias **idênticas**: `_strip_ansi`, `_fmt_ydl_progress`, `_item_label`, e o regex `_ANSI_ESC`
- as funções `start_*_pipeline(args, bus, cancel_event, on_finish)` são idênticas a menos do `run_*` chamado.

São ~250 linhas por arquivo, com talvez 60% comuns.

### Objetivo

Centralizar o scaffolding num runner base e mover utilitários compartilhados, deixando cada `worker.py` apenas com a lógica que difere (o processamento de um item).

### Arquivos

**Novos:**
- `src/gui/modules/_pipeline_runner.py` — runner base + helpers compartilhados.

**Modificados:**
- `src/gui/modules/audio/worker.py`
- `src/gui/modules/video/worker.py`
- `src/gui/modules/image/worker.py`

### Desenho proposto

`_pipeline_runner.py` expõe:

```python
# src/gui/modules/_pipeline_runner.py
from __future__ import annotations
import logging, re, threading
from pathlib import Path
from typing import Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import EventBus

_ANSI_ESC = re.compile(r"\x1b\[[0-9;]*m")
_NOISY_LOGGERS = ("httpx", "httpcore", "yt_dlp", "urllib3")


def strip_ansi(s: str) -> str:
    return _ANSI_ESC.sub("", s).strip()


def fmt_ydl_progress(d: dict) -> str:
    """Linha de progresso yt-dlp mutable (pct | de total | speed | ETA)."""
    ...  # mover corpo idêntico de audio/video worker


def item_label(item) -> str:
    """Nome do arquivo (local) ou netloc (url)."""
    ...  # mover corpo idêntico


def make_emitter(bus: "EventBus", module_id: str, default_stage: str) -> Callable:
    def emit(type: str, stage: str | None = None, payload: dict | None = None) -> None:
        bus.emit(type, stage or default_stage, payload or {}, module_id=module_id)
    return emit


class _LogScope:
    """Context manager: instala/remove o LogEventHandler e ajusta níveis."""
    def __init__(self, bus, module_id): ...
    def __enter__(self): ...   # addHandler + setLevel INFO + capar _NOISY_LOGGERS
    def __exit__(self, *exc): ...  # removeHandler + restaurar nível


def run_queue_pipeline(
    *,
    items: list,
    bus: "EventBus",
    module_id: str,
    default_stage: str,
    cancel_event: threading.Event,
    process_item: Callable[..., str],   # ver assinatura abaixo
    stop_on_error: bool = True,
) -> bool:
    """Esqueleto genérico da fila sequencial.

    Para cada item: checa cancel, emite queue_progress, chama process_item,
    coleta o output_path. Emite progress_start no início e task_done no fim.
    Captura exceções → task_error. Gerencia o LogScope.

    process_item(emit, item, idx, total, cancel_event) -> str (output_path)
       — recebe o emit já vinculado; lança exceção em erro fatal.
    """
```

> **Nota sobre `image`:** o worker de imagens tem 3 ramos especiais que **não** entram no loop padrão (`contact_sheet` N→1, `_run_batch_rembg`, `_run_batch_describe`) e usa `stop_on_error=False` (erro por item não trava a fila). O runner deve suportar:
> 1. `stop_on_error: bool` — quando `False`, captura exceção do `process_item`, emite `image_op_error`/log e continua, contando falhas; retorna `True` se ≥1 item passou.
> 2. Permitir que o worker faça o *short-circuit* dos modos especiais **antes** de chamar `run_queue_pipeline` (eles já são funções separadas: `_run_contact_sheet`, `_run_batch_rembg`, `_run_batch_describe` — mantê-las, só compartilham `make_emitter`/`_LogScope`).

### Passos (ordenados)

1. **Criar `_pipeline_runner.py`** com `strip_ansi`, `fmt_ydl_progress`, `item_label`, `make_emitter`, `_LogScope`. Copiar os corpos **exatos** de `audio/worker.py` (são a referência canônica).
2. **Migrar `audio/worker.py`** primeiro (caso mais rico: download/extract/convert + denoise + normalize):
   - Remover `_strip_ansi`, `_fmt_ydl_progress`, `_item_label`, `_ANSI_ESC` locais → importar do runner.
   - Extrair o corpo do `for` em `def _process_item(emit, item, idx, total, cancel_event) -> str`.
   - `run_audio_pipeline` passa a só montar args e chamar `run_queue_pipeline(..., process_item=_process_item)`.
   - O bug latente das closures `_progress_cb`/`_ydl_hook` redefinidas no loop (com `# type: ignore[no-redef]`) some naturalmente ao virarem funções dentro de `_process_item`.
3. **Migrar `video/worker.py`**: idem; mover a lógica `match effective_op` para dentro do `_process_item`. Preservar o tratamento especial de `WinError 32` — passar um `error_decorator` opcional ao runner **ou** capturar/re-lançar dentro do `_process_item` com a mensagem aumentada. Preferir manter o enrich de erro no `except` do runner via hook `on_error(msg) -> str` opcional.
4. **Migrar `image/worker.py`**: manter os 3 short-circuits no topo de `run_image_pipeline`; o loop padrão (`convert/resize/crop/...`) vira `process_item` com `stop_on_error=False`.
5. **Unificar `start_*_pipeline`**: opcionalmente extrair `start_pipeline(run_fn, args, bus, cancel_event, on_finish)` no runner. Manter os wrappers finos `start_audio_pipeline` etc. para não quebrar imports de `view.py`/`workers.py`.
6. Rodar testes e smoke manual da GUI.

### Riscos / quirks

- **Thread safety:** `bus.emit()` roda na worker thread; não chamar `page.update()` aqui. Manter como está.
- **`pipeline_running[0]`** é resetado em `view.py`/`app.py` no `finally` do `on_finish`, não no worker — **não mexer nisso**.
- **`_LogScope`** deve sempre remover o handler no `__exit__`, inclusive em exceção, senão handlers acumulam (mesmo motivo do `page.pubsub.unsubscribe_all()` em `build_app`).
- Não alterar a **forma dos payloads** dos eventos — `progress_view.py`, os `view.py` **e o futuro `CLIEventBus`** dependem das chaves exatas (`current_item`, `item_idx`, `src_size_bytes`, etc.). Ver "Contrato rígido de eventos" no topo deste refactor.

### Verificação

- `uv run pytest -m unit -v` (workers não têm teste hoje — ver Plano 2, Refactor F, para extrair lógica testável).
- `uv run pytest gui/modules/audio/test_pipeline_log.py gui/modules/image/test_pipeline_log.py` (garantir que pipeline_log não foi tocado).
- Smoke manual: `uv run gui.py` → rodar 1 item em cada módulo (download URL, converter arquivo local, processar imagem), confirmar: barra de progresso, log mutable do yt-dlp, player de áudio aparecendo, e que cancelar no meio funciona.

### Critério de aceite

- `audio/worker.py`, `video/worker.py`, `image/worker.py` reduzidos (meta: −40% de linhas somadas).
- Zero cópias de `_strip_ansi`/`_fmt_ydl_progress`/`_item_label`/`_ANSI_ESC`.
- Comportamento da GUI idêntico.

---

## Refactor B — Quebrar `image/form_view.py` (1228 linhas) + helper `labeled_slider`

> 🔗 **Interação com CLI Fase 2.** A CLI Fase 2 já terá extraído o dataclass `ImageArgs` (33 campos) de `form_view.py` para `src/core/image/args.py`. Isto é complementar: este refactor parte do `form_view.py` já sem o dataclass. Não reintroduzir `ImageArgs` aqui — apenas importá-lo de `src/core/image/args.py` ao coletar valores.

### Problema

`src/gui/modules/image/form_view.py` é o maior arquivo do projeto: 38 funções numa única `build_image_form(...)`. Concentra os 12 blocos de operação (resize, crop, rotate, watermark, border, adjust, filter, favicon, contact_sheet, remove_bg, describe, convert) **e** ~18 handlers de slider `_on_*_change`/`_on_*_end` quase idênticos (change atualiza o label de valor; end aplica/persiste). Já existem `_make_adj_slider` e `_make_cs_slider`, mas só são usados em 2 grupos — o padrão não foi generalizado.

### Objetivo

1. Extrair um helper único `labeled_slider(...)` que encapsula o par change/end + label de valor, eliminando a maioria dos 18 handlers.
2. Quebrar os blocos de operação em submódulos, deixando `form_view.py` só com a orquestração (dataclass `ImageArgs`, seleção de operação, montagem do painel, coleta de valores).

### Arquivos

**Novos:**
- `src/gui/modules/image/blocks/__init__.py`
- `src/gui/modules/image/blocks/resize.py`, `crop.py`, `rotate.py`, `watermark.py`, `border.py`, `adjust.py`, `filter.py`, `favicon.py`, `contact_sheet.py`, `convert_fmt.py` (o `_fmt_section`)
  - (`remove_bg` e `describe` são pequenos — podem ficar juntos em `blocks/ai.py`.)
- `src/gui/theme/components/sliders.py` — `labeled_slider(...)` (ou adicionar a `inputs.py`, que já hospeda fábricas de input).

**Modificados:**
- `src/gui/modules/image/form_view.py`

### Desenho — `labeled_slider`

```python
# src/gui/theme/components/sliders.py
from __future__ import annotations
from typing import Callable
import flet as ft

def labeled_slider(
    *,
    label: str,
    value: float,
    min: float,
    max: float,
    divisions: int | None = None,
    fmt: Callable[[float], str] = lambda v: f"{v:.0f}",
    on_commit: Callable[[float], None] | None = None,
) -> tuple[ft.Column, ft.Slider]:
    """Slider com label de valor que atualiza ao vivo (on_change) e
    confirma no on_change_end (evita seeks/aplicações contínuas durante o drag).

    Retorna (coluna_pronta, referência_ao_slider) para leitura posterior do .value.
    """
    value_text = ft.Text(fmt(value))
    slider = ft.Slider(value=value, min=min, max=max, divisions=divisions)

    def _on_change(e: ft.ControlEvent) -> None:
        value_text.value = fmt(slider.value)
        value_text.update()           # NUNCA page.update() em cascata (quirk 0.85)

    def _on_end(e: ft.ControlEvent) -> None:
        if on_commit:
            on_commit(slider.value)

    slider.on_change = _on_change
    slider.on_change_end = _on_end     # on_change_end EXISTE no 0.85
    col = ft.Column([ft.Text(label), ft.Row([slider, value_text])], spacing=0)
    return col, slider
```

> Substitui `_make_adj_slider`, `_make_cs_slider`, `_on_resize_scale_change/end`, `_on_wm_size_change/end`, `_on_wm_opacity_change/end`, `_on_border_padding_change/end`, `_on_quality_change/end`, `_on_out_quality_change/end`, etc.

### Desenho — blocos

Cada bloco vira uma função-fábrica pura que recebe dependências e devolve `(ft.Column, dict_de_getters)`:

```python
# src/gui/modules/image/blocks/resize.py
def build_resize_block() -> tuple[ft.Column, "ResizeRefs"]:
    """Monta o bloco de resize. Devolve a coluna e refs/getters dos campos
    para o form_view ler ao montar ImageArgs."""
```

`form_view.py` faz:
```python
resize_block, resize_refs = build_resize_block()
_param_blocks["resize"] = resize_block
# ... ao coletar:
args.resize_mode = resize_refs.mode()
```

> Padronizar a interface dos blocos com um pequeno `Protocol`/dataclass de "refs" por bloco, ou um dict `{"campo": getter}`. Escolher **um** padrão e aplicar a todos.

### Passos (ordenados)

1. **Criar `labeled_slider`** em `theme/components/sliders.py`. Adicionar teste de fumaça se viável (Flet headless é limitado — ao menos importar e instanciar fora de página).
2. **Migrar os sliders um grupo por vez** dentro de `form_view.py`, sem mover nada de arquivo ainda: trocar cada par `_on_*_change/_end` + `Text` + `Slider` por uma chamada a `labeled_slider`. Validar na GUI a cada grupo. *(Esta etapa sozinha já corta ~150 linhas e é baixo risco.)*
3. **Extrair blocos para `blocks/`** um por vez, do mais isolado (`favicon`, `filter`, `border`) ao mais acoplado (`convert`/`_fmt_section`, que tem lógica de qualidade lossy e `_update_convert_quality_state`). Após cada extração: importar no `form_view`, registrar em `_param_blocks`, rodar GUI.
4. **Reduzir `build_image_form`** ao núcleo: dataclass `ImageArgs`, `_make_card`/`_refresh_cards`/`_select_op`, `_refresh_param_blocks`, coleta de valores.
5. Conferir o visor Before/After e o estado de `_last_input_thumb` continuam funcionando (não são de slider, mas vivem no mesmo arquivo).

### Riscos / quirks (Flet 0.85 — do CLAUDE.md)

- **Nunca `ink=True`** em containers clicáveis; usar `GestureDetector` externo + `Cursor.*`. Os cards de operação já seguem isso — não regredir ao mover código.
- **Não mutar `ctr.disabled` dentro de callbacks de mudança de estado** (ex.: `_on_items_change`) — causa rebuild que desfaz `border`/`bgcolor` de `_refresh_op_cards`. Os blocos `remove_bg`/`describe` têm `_set_*_disabled` — mantê-los chamados de fora desses callbacks.
- **`on_change` programático não dispara** no Python: ao setar `.value` + `update()`, atualizar o label manualmente.
- **Um `update()` por evento** — `labeled_slider` chama `value_text.update()`, não `page.update()`.
- **Toggle por `visible=`**, nunca reatribuir `Container.content` — o mecanismo de `_param_blocks`/`_refresh_param_blocks` já é por `visible`; preservar.
- `ft.Slider` usa `on_change_end` para confirmar (evita aplicar a cada frame do drag).

### Verificação

- `uv run pytest -m unit -v` (form_view não é testado headless, mas garantir que nada em `src/core`/`utils` quebrou via imports).
- Smoke manual obrigatório: `uv run gui.py` → módulo Imagens → exercitar **cada** operação, confirmando que sliders atualizam o label ao arrastar, aplicam no soltar, e que o visor Before/After e a troca de operação seguem corretos.

### Critério de aceite

- `form_view.py` < ~400 linhas.
- Um único helper de slider em uso (zero pares `_on_*_change/_end` manuais).
- Cada bloco em seu arquivo sob `blocks/`, com interface de coleta uniforme.
- Comportamento e aparência idênticos na GUI.

---

## Ordem de execução sugerida

Esta é a sequência GLOBAL combinada (Plano 1 + Plano 2 + `REFACTORING.md`):

1. **CLI Fase 0** — corrige `utils.py` (bug cp1252, validação YouTube, colisão de id); autossuficiente. Absorve o antigo Refactor F2 do Plano 2.
2. **CLI Fase 2** — extrai `AudioArgs/VideoArgs/ImageArgs` para `src/core/<m>/args.py`. **Pré-requisito do Refactor A e do Refactor B.**
3. **Refactor A** (este doc) — runner base dos workers. Antes da CLI Fase 1, enquanto a GUI ainda é o único consumidor dos workers.
4. **CLI Fase 1** — `CLIEventBus`, reusando os workers já limpos.
5. **Refactor B** (este doc) — `labeled_slider` + quebra em `blocks/`. A migração de sliders (passo 2) pode ser antecipada como aquecimento de baixo risco a qualquer momento após a Fase 2.
6. **CLI Fases 3–5** e os refactors C/D/E/F do Plano 2, conforme conveniência.

Commit a cada etapa concluída, sempre após `uv run pytest -m unit`.
