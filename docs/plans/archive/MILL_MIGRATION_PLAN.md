# mill.tools — Fase A: PR0–PR2 (Fundação)

## Contexto e escopo deste doc

O projeto `yt-transcriber` será expandido e renomeado para **mill.tools** — uma multiferramenta pessoal extensível.

Este documento cobre apenas a **Fase A (PR0–PR2)**: rename, paths, settings, sistema de módulos e contratos transversais. Ao final desses PRs, mill.tools roda igual a hoje mas com sidebar e pronto para receber módulos.

**Fase B (PR3 Áudio, PR4 Vídeo, etc.)** será detalhada em `docs/MILL_MODULES_PLAN.md` após o PR2 estar validado. Os requisitos mínimos para dimensionar os contratos do PR2 estão no spike ao final deste documento.

**Premissas:**
- CLI `main.py` permanece intocado e 100% funcional; novos módulos são **GUI-only**
- Merge `feature/flet-gui` → `main` antes de qualquer implementação (DECIDIDO)
- Implementação em PRs sequenciais — cada PR válido isoladamente
- Flet 0.85.2 com quirks conhecidos (sem `ft.Tabs`, `ft.border.all` quebrado, etc.)

---

## Nova estrutura de output

```
output/
├── audio/
│   ├── source/        ← áudios baixados de URLs (hoje: audios/)
│   └── processed/     ← áudios processados + extraídos de vídeo
├── video/
│   └── processed/     ← vídeos baixados/convertidos
└── transcriptions/
    ├── text/          ← transcrições brutas (hoje: transcriptions/raw/)
    ├── analysis/      ← análises estruturadas (hoje: transcriptions/analysis/)
    └── digest/        ← condensado prompt-ready (hoje: transcriptions/prompt_ready/)
```

**Dados legados:** arquivos em `audios/` e `transcriptions/raw/` ficam onde estão. Novos outputs vão para `output/`. Documentar no README que saídas antigas permanecem nos caminhos legados.

---

## PR 0 — Merge feature/flet-gui → main

1. Criar PR `feature/flet-gui` → `main` no GitHub
2. Mergear
3. Criar branch `feature/mill-tools` a partir do `main` atualizado

---

## PR 1 — Rename + Reestruturação de Paths

**Objetivo:** Renomear o projeto e migrar paths. Nenhuma mudança funcional visível.

### 1.1 pyproject.toml

```toml
[project]
name = "mill-tools"
version = "0.1.0"
```

### 1.2 utils.py — novas constantes

Substituir as constantes de path **sem aliases** — todos os consumidores são atualizados no mesmo PR:

```python
# DEPOIS
OUTPUT_DIR               = PROJECT_ROOT / "output"
AUDIO_SOURCE_DIR         = OUTPUT_DIR / "audio" / "source"
AUDIO_PROCESSED_DIR      = OUTPUT_DIR / "audio" / "processed"
VIDEO_PROCESSED_DIR      = OUTPUT_DIR / "video" / "processed"
TRANSCRIPTIONS_TEXT_DIR  = OUTPUT_DIR / "transcriptions" / "text"
TRANSCRIPTIONS_ANALYSIS_DIR = OUTPUT_DIR / "transcriptions" / "analysis"
TRANSCRIPTIONS_DIGEST_DIR = OUTPUT_DIR / "transcriptions" / "digest"
```

Sem aliases — todos os consumidores são atualizados atomicamente no mesmo PR.

### 1.3 Consumidores a atualizar

| Arquivo | Constante antiga | Constante nova |
|---|---|---|
| `main.py` | `AUDIOS_DIR` | `AUDIO_SOURCE_DIR` |
| `main.py` | `TRANSCRIPTIONS_RAW_DIR` | `TRANSCRIPTIONS_TEXT_DIR` |
| `src/gui/workers.py` | `AUDIOS_DIR` | `AUDIO_SOURCE_DIR` |
| `src/gui/workers.py` | `TRANSCRIPTIONS_RAW_DIR` | `TRANSCRIPTIONS_TEXT_DIR` |
| `src/prompter.py` | `TRANSCRIPTIONS_PROMPT_DIR` | `TRANSCRIPTIONS_DIGEST_DIR` |
| `src/__main__.py` | verificar usos de path | atualizar se necessário |

`transcriber.py`, `formatter.py`, `llm_factory.py`, `analyzer.py` (usa `TRANSCRIPTIONS_ANALYSIS_DIR` — nome mantido) não precisam de alteração.

### 1.4 settings.py — novo config dir

```python
_CONFIG_DIR = Path.home() / ".mill-tools"

# Migração automática (uma vez)
_OLD_CONFIG = Path.home() / ".yt-transcriber" / "config.json"
if _OLD_CONFIG.exists() and not (_CONFIG_DIR / "config.json").exists():
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(_OLD_CONFIG, _CONFIG_DIR / "config.json")
```

`~/.yt-transcriber` não é removido — fica órfão silenciosamente (documentar).

### 1.5 gui.py e AppBar

```python
# gui.py → page.title = "mill.tools"
# app.py → ft.Text("mill.tools", weight=ft.FontWeight.BOLD)
```

### 1.6 .gitignore — correção para .gitkeep

```gitignore
# output gerado — ignorar conteúdo, preservar estrutura
output/**
!output/
!output/**/
!output/**/.gitkeep
```

> ⚠️ `output/` sozinho engolhiria os `.gitkeep`. A exceção explícita é necessária.

### Checklist PR 1
- [ ] `pyproject.toml`: name = "mill-tools"
- [ ] `utils.py`: novas constantes (sem aliases)
- [ ] `main.py`: `AUDIO_SOURCE_DIR`, `TRANSCRIPTIONS_TEXT_DIR`
- [ ] `src/gui/workers.py`: mesmas trocas
- [ ] `src/prompter.py`: `TRANSCRIPTIONS_DIGEST_DIR`
- [ ] `src/__main__.py`: verificar e atualizar paths se houver
- [ ] `src/gui/settings.py`: novo config dir + migração automática
- [ ] `gui.py` + `app.py`: título "mill.tools"
- [ ] `.gitignore`: novo bloco com exceções `.gitkeep`
- [ ] Criar estrutura `output/` com `.gitkeep` em cada subpasta
- [ ] `README.md`: seção sobre paths legados, novo título
- [ ] `CLAUDE.md`: atualizar estrutura de pastas
- [ ] Smoke test: `uv run main.py <URL>` → gera em `output/transcriptions/text/`
- [ ] Smoke test: `uv run gui.py` → título "mill.tools", pipeline completo
- [ ] Smoke test: `git status` confirma que `.gitkeep` estão sendo rastreados após o novo bloco de `.gitignore`

---

## PR 2 — NavigationRail + Sistema de Módulos

**Objetivo:** Sidebar de navegação, contrato de módulo e contrato de eventos genérico — tudo exercitado pelo módulo de Transcrição existente. Escopo restrito ao que tem consumidor agora.

### 2.1 Contrato de eventos genérico (camada fina)

O `ProgressPanel` passa a entender os 5 eventos neutros. O worker de Transcrição emite esses eventos em paralelo aos legados — **sem refatorar a renderização**, apenas adicionando o mapeamento.

```python
# Eventos genéricos (todos os módulos futuros emitem estes)
progress_start(stage: str)                     # barra indeterminada visível
progress_update(current: float, total: float)  # barra determinada (0.0–1.0)
log(message: str, level: str)                  # linha de log colorida
task_done(payload: dict)                       # fim com sucesso
task_error(message: str)                       # fim com erro
```

**Dívida técnica explícita:** eventos legados de Transcrição (`language_detected`, `transcribe_segment`, `whisper_loading`, etc.) ficam em paralelo no PR2. Marcar no código com `# TODO(PR3): remover evento legado`. Serão removidos quando o worker estiver 100% no contrato genérico.

**NÃO** adicionar lógica de fila, barra de dois níveis ou `queue_progress` no PR2. Isso vai no PR3 junto com o módulo Áudio (primeiro consumidor real).

**⚠️ `progress_view.py` é frágil:** IndexError no `object_patch`, não chamar `page.update()` em cascata, usar `Column+append` em vez de `Container+content`. Tocar o mínimo possível — apenas adicionar o mapeamento dos 5 eventos, sem refatorar a renderização.

### 2.2 Contrato de módulo — base.py

```python
from dataclasses import dataclass, field
from typing import Callable
import flet as ft

@dataclass
class Module:
    id: str                          # "transcription", "audio", "video"
    label: str                       # "Transcrição", "Áudio", "Vídeo"
    icon: str                        # ft.Icons.XXX (outline)
    selected_icon: str               # ft.Icons.XXX (filled)
    control: ft.Control              # painel construído uma vez no build_app
    on_mount: Callable[[dict], None] = field(default=lambda _: None)
    on_unmount: Callable[[], None]   = field(default=lambda: None)
```

**Semântica de cache:** `control` é construído uma vez e reutilizado — trocar de aba **não destrói** o estado. O log, barra e resultado da Transcrição são preservados ao voltar. `on_unmount` existe apenas para pausar/soltar recursos externos (ex.: parar preview de áudio), nunca para descartar o painel. Se não houver recurso externo a liberar, `on_unmount` é no-op.

`on_mount(payload)` recebe dados ao navegar para o módulo — usado pela bridge para preencher campos.

### 2.3 Registry e navigate_to

**Switching por visibilidade, não por reatribuição de content.** Reatribuir `module_container.content` a cada navegação reproduz o bug `object_patch` IndexError do Flet 0.85 que forçou o abandono de `ft.Tabs`. Em vez disso, todos os módulos são montados simultaneamente num `ft.Stack`; `navigate_to` apenas alterna `visible=True/False`. A árvore do controle permanece estável.

```python
# app.py
MODULES: list[Module] = [audio_module, video_module, transcription_module]
DEFAULT_MODULE_ID = "transcription"

def navigate_to(module_id: str, payload: dict | None = None) -> None:
    # Bloquear troca enquanto pipeline estiver ativo
    if pipeline_running[0]:
        _show_warning("Aguarde o pipeline terminar antes de trocar de módulo.")
        rail.selected_index = current_idx[0]  # restaurar seleção visual
        page.update()
        return

    idx = next(i for i, m in enumerate(MODULES) if m.id == module_id)
    MODULES[current_idx[0]].on_unmount()
    current_idx[0] = idx
    rail.selected_index = idx
    # Alternar visibilidade — não reatribuir content (evita object_patch bug)
    for i, m in enumerate(MODULES):
        m.control.visible = (i == idx)
    MODULES[idx].on_mount(payload or {})
    page.update()
```

**Decisão de navegação com pipeline ativo: bloquear.** Mais simples e seguro dado o modelo de threads (worker daemon + pubsub). `navigate_to` verifica `pipeline_running[0]`, ignora a troca e restaura o índice visual no rail.

- Nunca usa índice numérico hardcoded fora do registry
- Adicionar PDF/Word = uma entrada em `MODULES`, zero mudança em `app.py`

### 2.4 NavigationRail

> ⚠️ Verificar via `inspect.signature(ft.NavigationRail.__init__)` e `inspect.signature(ft.NavigationRailDestination.__init__)` antes de implementar — histórico de breaking changes no Flet 0.85.

Layout raiz — todos os módulos no Stack, só um visível por vez:

```python
module_stack = ft.Stack(
    controls=[m.control for m in MODULES],  # todos montados simultaneamente
    expand=True,
)
# visibilidade inicial
for m in MODULES:
    m.control.visible = (m.id == DEFAULT_MODULE_ID)

ft.Row([
    rail,                                           # gerado do registry MODULES
    ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT),
    ft.Container(content=module_stack, expand=True),
], expand=True)
```

> **Por que Stack e não Column?** Stack sobrepõe os controles no mesmo espaço — o módulo visível ocupa 100% da área; os invisíveis não consomem layout. Column empilharia verticalmente, causando scroll indesejado com múltiplos módulos visíveis acidentalmente.

### 2.4.1 pipeline_running em finally (workers.py)

`pipeline_running[0]` deve voltar a `False` em **todos** os desfechos do worker — sucesso, erro e cancelamento — dentro de um bloco `finally`. Se ficar `True` após um erro, `navigate_to` bloqueia permanentemente a navegação.

```python
# src/gui/workers.py — run_pipeline()
def run_pipeline(...):
    try:
        # ... pipeline completo ...
        bus.emit(PipelineEvent("pipeline_done", "pipeline", {...}))
    except Exception as e:
        bus.emit(PipelineEvent("pipeline_error", "pipeline", {"message": str(e)}))
    finally:
        pipeline_running[0] = False          # SEMPRE, independente do desfecho
        form_panel.set_running(False)
```

`pipeline_running[0] = False` precisa estar no `finally`, não apenas no handler de `pipeline_done`.

### 2.5 Módulo Transcrição

`src/gui/modules/transcription/view.py` — wrap do conteúdo atual de `app.py`:

```python
def build_transcription_module(page, bus, pipeline_running, cancel_event) -> Module:
    form_panel = build_form_view(page, on_start=_on_start)
    progress_panel = build_progress_view(page, on_cancel=_on_cancel, on_done=_on_done)
    # shortcuts_bar — idêntico ao app.py atual

    control = ft.Row([
        ft.Container(content=ft.Column([form_panel.control, shortcuts_bar], ...), width=380),
        ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT),
        ft.Container(content=progress_panel.control, expand=True, padding=ft.Padding(left=12, right=12, top=8, bottom=8)),
    ], expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.STRETCH)

    return Module(
        id="transcription",
        label="Transcrição",
        icon=ft.Icons.SUBTITLES_OUTLINED,
        selected_icon=ft.Icons.SUBTITLES,
        control=control,
        on_mount=lambda payload: _fill_from_payload(payload),
    )
```

`_fill_from_payload`: se `payload` contiver `{"file": path}`, preenche o campo de URL com o path. Preparação para a bridge Áudio→Transcrição do PR3.

### 2.6 Placeholders Áudio e Vídeo

```python
# src/gui/modules/audio/view.py
def build_audio_placeholder() -> Module:
    return Module(
        id="audio", label="Áudio",
        icon=ft.Icons.MUSIC_NOTE_OUTLINED, selected_icon=ft.Icons.MUSIC_NOTE,
        control=ft.Container(
            content=ft.Text("Módulo Áudio — Em breve", italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
            alignment=ft.alignment.center, expand=True,
        ),
    )
```

Mesmo padrão para Vídeo (`id="video"`, `label="Vídeo"`, ícones de vídeo).

### 2.7 InputSource + Modo Fila — ESPECIFICAÇÃO (implementação no PR3)

> Esta seção é design confirmado, **não implementação do PR2**. `InputSource`, `InputItem`, FilePicker wrapper, `queue_progress` e barra de dois níveis são implementados no PR3 junto com o módulo Áudio (primeiro consumidor real). Manter aqui para referência de compatibilidade com os contratos do PR2.

**Decisões de arquitetura travadas:**
- `InputSource` como componente compartilhado (`src/gui/components/input_source.py`)
- `InputItem(kind: "url"|"local", value: str)` — ramifica pipeline no worker; local pula downloader
- Fila sequencial (batch simples): processar um item por vez — serializa GPU/ffmpeg
- `navigate_to(module_id, payload)` com `payload={"file": path}` é o mecanismo da bridge E do preenchimento manual — mesma rota, sem duplicação
- FilePicker: overlay Flet (`page.overlay.append`), resultado via callback assíncrono, `allow_multiple=True`
- `queue_progress(current_item, total_items, item_name)` como sexto evento genérico (adicionado ao `ProgressPanel` no PR3)

### Checklist PR 2
- [ ] Verificar API `ft.NavigationRail` + `ft.NavigationRailDestination` via `inspect.signature`
- [ ] `src/gui/modules/__init__.py`
- [ ] `src/gui/modules/base.py` com `Module` (id, label, icon, selected_icon, control, on_mount, on_unmount)
- [ ] `src/gui/modules/transcription/__init__.py` + `view.py`
- [ ] `src/gui/modules/audio/__init__.py` + `view.py` (placeholder)
- [ ] `src/gui/modules/video/__init__.py` + `view.py` (placeholder)
- [ ] `src/gui/views/progress_view.py`: mapeamento dos 5 eventos genéricos (camada fina); marcar legados com `# TODO(PR3): remover`
- [ ] `src/gui/workers.py`: emitir eventos genéricos em paralelo aos legados; `pipeline_running[0] = False` em bloco `finally`
- [ ] `src/gui/app.py`: registry `MODULES`, `navigate_to()` via visibilidade (Stack), bloqueio de pipeline ativo, NavigationRail do registry, default Transcrição
- [ ] `_show_warning()` em `app.py`: aviso curto quando troca bloqueada (snackbar ou label)
- [ ] Smoke test: alternar entre os 3 módulos várias vezes seguidas sem crash
- [ ] Smoke test: pipeline de Transcrição ativo → tentar trocar de aba → bloqueado com aviso
- [ ] Smoke test: forçar erro no pipeline (URL inválida) → confirmar que navegação entre módulos volta a funcionar
- [ ] Smoke test: pipeline completo de Transcrição (URL → transcrição + análise) funciona normalmente
- [ ] Smoke test: atalhos Ctrl+Enter e Esc funcionam no módulo Transcrição

---

## Spike — Requisitos de Áudio/Vídeo (valida contratos do PR2)

> Este spike não é implementação — é a 1 página de requisitos que garante que Module, EventBus e InputSource do PR2 estão dimensionados corretamente. O detalhamento completo de PR3/PR4 vai em `docs/MILL_MODULES_PLAN.md` após o PR2 validado.

### Entradas por módulo

| Módulo | Fontes aceitas | Extensões locais |
|---|---|---|
| Áudio | URL (YT, SoundCloud...) + arquivo local | mp3, wav, flac, ogg, opus, aac, m4a |
| Vídeo | URL (YT, Twitter, TikTok...) + arquivo local | mp4, mkv, webm, avi, mov |
| Transcrição (futuro) | URL YT + arquivo de áudio local | mp3, wav, flac, ogg, opus |

**Conclusão:** `InputSource` com `accepted_extensions` por instância está correto. `InputItem.kind = url | local` cobre todos os casos.

### Eventos de progresso por operação

| Operação | Progresso interno | Observação |
|---|---|---|
| Download áudio/vídeo (yt-dlp) | porcentagem via callback `progress_hooks` | yt-dlp chama hook com `{"downloaded_bytes", "total_bytes"}` |
| Conversão ffmpeg | stderr parsing `time=HH:MM:SS` / `duration` | precisa capturar stderr linha a linha |
| Extração de áudio | igual conversão ffmpeg | mesma lógica |
| Transcrição Whisper | `segment.end / audio_duration` | já implementado |

**Conclusão:** `progress_update(current, total)` genérico cobre todos — cada worker mapeia sua fonte para floats 0–1. O contrato de 5 eventos do PR2 é suficiente; `queue_progress` é o único acréscimo no PR3.

### Modo fila

- Batch sequencial obrigatório: serializa GPU (Whisper) e CPU/ffmpeg
- `queue_progress(current_item, total_items, item_name)` é o único evento extra necessário
- `ProgressPanel` renderiza: label `"Item 2/5 — arquivo.mp3"` + barra interna do item

### Bridge

- Destino sempre é Transcrição: `navigate_to("transcription", {"file": path})`
- Recebido via `Module.on_mount(payload)` → preenche campo de URL
- Nenhum outro cruzamento entre módulos previsto no momento

### Dependências externas novas

- `ffmpeg`: verificar presença + codec mp3/aac/opus em `check_dependencies()`
- `yt-dlp`: já verificado — estender formatos de saída (mp4, mkv, webm)

**→ Fase B documentada em `docs/MILL_MODULES_PLAN.md` após PR2 em produção.**

---

## Verificação end-to-end — Fase A

| PR | Comando / Ação | Resultado esperado |
|---|---|---|
| 1 | `uv run main.py <URL>` | gera em `output/transcriptions/text/` |
| 1 | `uv run gui.py` | título "mill.tools", pipeline completo |
| 1 | `git status` | `.gitkeep` rastreados, conteúdo de `output/` ignorado |
| 2 | `uv run gui.py` | sidebar visível, Transcrição funcional, Áudio/Vídeo mostram placeholder |
| 2 | navegar Áudio/Vídeo | placeholder "Em breve", sem crash |
| 2 | pipeline ativo → trocar aba | bloqueado com aviso, aba permanece em Transcrição |
| 2 | Ctrl+Enter, Esc | atalhos funcionam no módulo Transcrição |

---

## Arquivos críticos — Fase A

| PR | Arquivo | Tipo de mudança |
|---|---|---|
| 1 | `src/utils.py` | Novas constantes de path |
| 1 | `src/gui/settings.py` | Novo config dir + migração automática |
| 1 | `main.py`, `src/gui/workers.py`, `src/prompter.py`, `src/__main__.py` | Novos nomes de constante |
| 1 | `gui.py`, `src/gui/app.py` | Título mill.tools |
| 1 | `pyproject.toml`, `.gitignore`, `README.md`, `CLAUDE.md` | Rename + .gitkeep fix |
| 2 | `src/gui/views/progress_view.py` | Mapeamento dos 5 eventos genéricos (camada fina) |
| 2 | `src/gui/workers.py` | Eventos genéricos em paralelo + `pipeline_running[0] = False` em `finally` |
| 2 | `src/gui/app.py` | Registry `MODULES` + `navigate_to()` via visibilidade (Stack) + NavigationRail |
| 2 | `src/gui/modules/` (novo) | `base.py` + `transcription/` + placeholders áudio/vídeo |

**Fase B** (PR3 Áudio, PR4 Vídeo): documentada em `docs/MILL_MODULES_PLAN.md` após PR2 em produção.
