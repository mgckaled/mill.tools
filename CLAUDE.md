# mill.tools

Multiferramenta pessoal extensível para processamento de áudio, vídeo e transcrição, com GUI desktop (Flet) e CLI. O módulo de Transcrição usa faster-whisper com aceleração GPU — 100% local. A GUI é organizada em **módulos** acessíveis por uma sidebar (NavigationRail).

## Stack

- **Python 3.13** gerenciado com `uv`
- **faster-whisper** + **ctranslate2** — transcrição via Whisper (sem PyTorch, por escolha)
- **yt-dlp** — download de áudio/vídeo e metadados
- **ffmpeg** — conversão/extração de áudio
- **Pillow 12.2+** — processamento de imagens (AVIF nativo, EXIF transpose, conversão multi-formato)
- **rembg[cpu]** + **onnxruntime** (extra `[ai-image]`) — remoção de fundo CPU/ONNX
- **LangChain** + **Ollama** (local) / **Google Gemini** (nuvem) — formatação, análise, condensação e descrição de imagens (vision)
- **Flet 0.85** — GUI desktop (Flutter no Windows)
- **tqdm** — barra de progresso (CLI)

> Decisão consciente: o projeto evita **PyTorch**. Qualquer IA que dependa de torch (ex.: Demucs, DeepFilterNet) fica isolada num extra opcional `[ai-audio]` (planejado para o PR3.1) — o app base permanece torch-free.

## Hardware de desenvolvimento

- Dell Inspiron 7580 — i5-8265U, 16GB RAM
- NVIDIA GeForce MX150 (2GB VRAM), CUDA 12.6
- Compute type: `int8_float32` (arquitetura Pascal)
- Thermal throttling gerenciado pelo EC Dell (~63-65°C) — comportamento esperado
- OS: Windows 10 Home

## Estrutura

```
main.py                          — entry point CLI (argparse)
gui.py                           — entry point GUI (splash → build_app)
src/
├── transcriber.py · formatter.py · analyzer.py · prompter.py
├── llm_factory.py               — roteamento gemini-* → Google, demais → Ollama
├── utils.py                     — logging, validação, metadata, download, paths de output
├── core/
│   ├── audio/
│   │   ├── downloader.py        — yt-dlp: URL → output/audio/source/
│   │   ├── converter.py         — ffmpeg (-progress pipe:1): convert_audio(), extract_audio()
│   │   └── info.py              — get_duration_ffprobe()
│   └── image/
│       ├── downloader.py        — urllib: URL → output/image/source/
│       ├── converter.py         — convert_image(): EXIF transpose, RGBA→RGB, quality lossy
│       ├── transform.py         — 9 funções de manipulação (resize/crop/rotate/watermark/border/adjust/filter/favicon/contact_sheet)
│       ├── background.py        — remove_background() via rembg/ONNX (imports lazy; extra [ai-image])
│       ├── describe.py          — describe_image() + save_description() via LangChain + Ollama vision
│       └── info.py              — image_info() + thumbnail_bytes()
└── gui/
    ├── app.py                   — build_app(): NavigationRail + registry de módulos + navigate_to
    ├── splash.py                — show_splash(): cata-vento + fade → build_app
    ├── assets.py                — b64() (bytes p/ ft.Image), WINDOW_ICON
    ├── events.py                — EventBus, PipelineEvent (com module_id), LogEventHandler
    ├── settings.py              — persistência em ~/.mill-tools/config.json
    ├── workers.py               — pipeline de Transcrição em thread (module_id="transcription")
    ├── help_content.py          — HELP_SHORT/LONG: registro central de tooltips/modais
    ├── components/
    │   └── input_source.py      — InputItem, InputSource (URL + FilePicker, allow_multiple)
    ├── modules/
    │   ├── base.py              — dataclass Module (id, label, icon, control, on_mount/on_unmount)
    │   ├── transcription/view.py
    │   ├── audio/               — form_view.py, worker.py, view.py
    │   ├── image/               — form_view.py, worker.py, view.py, pipeline_log.py (PR-IMG-2B)
    │   └── video/view.py        — placeholder (PR4)
    └── views/
        ├── form_view.py         — formulário de Transcrição → FormPanel
        ├── progress_view.py     — ProgressPanel (logs/barra/spinner), filtro por owner_id
        └── result_view.py       — resultados em abas (Transcrição/Análise/Digest)
```

## Sistema de módulos (GUI)

A GUI é dividida em módulos selecionáveis numa **NavigationRail** à esquerda. Estado:
**Áudio** (PR3, completo), **Vídeo** (placeholder, PR4), **Imagens** (PR-IMG-2B, completo), **Transcrição** (completo).
Ordem na rail: Áudio → Vídeo → Imagens → Transcrição.

- **Registry** (`app.py`): `MODULES: list[Module]` é a fonte única. Adicionar um módulo = uma entrada na lista.
- **Module** (`modules/base.py`): dataclass com `id`, `label`, `icon`, `selected_icon`, `control`, `on_mount(payload)`, `on_unmount()`. O `control` é construído uma vez; trocar de aba **não** destrói o estado.
- **navigate_to(module_id, payload)**: alterna **visibilidade** dos controles num `ft.Stack` (não reatribui `content` — evita o `object_patch` IndexError do Flet 0.85). **Bloqueia a troca** enquanto `pipeline_running[0]` for `True`.
- **Bridge Áudio → Transcrição**: `navigate_to("transcription", {"file": path})` — o `on_mount` preenche o campo URL percorrendo a árvore de controles.
- **Escopo de eventos por módulo**: cada `ProgressPanel` recebe um `owner_id` e ignora eventos cujo `module_id` não casa.

## Módulo Áudio (PR3)

- **Operações** (auto-detectadas): URL → download; vídeo local → extração; áudio local → conversão.
- **Entrada**: URL + FilePicker via `page.services`, `allow_multiple=True`. Arrastar do SO fora de escopo.
- **Formato/qualidade**: `best`/mp3/m4a/wav/ogg/opus + bitrate (320…64 kb/s). `best` sem reencode.
- **Capa + metadados**: embutidos por padrão; switch desligável. Fallback gracioso em ogg/opus.
- **Fila sequencial**: um item por vez. Progresso via `queue_progress` + `progress_update`.
- **Saída**: downloads → `output/audio/source/`; convertidos → `output/audio/processed/`.

> IA de áudio planejada para **PR3.1** (DeepFilterNet/Demucs), isolada em extra opcional torch.

## Módulo Imagens (PR-IMG-2B)

Conversão, manipulação e operações de IA com visor Before/After integrado.

- **Operações** (12, selecionadas via card grid 3 colunas): `convert`, `resize` (caber/exato/escala%), `crop` (manual/proporção/auto-trim), `rotate` (ângulo/flip/EXIF), `watermark` (texto ou imagem), `border`, `adjust` (brilho/contraste/saturação/nitidez), `filter` (blur/sharpen/autocontrast/equalizar/cinza), `favicon` (.ico multires), `contact_sheet` (N→1), `remove_bg` (rembg/ONNX, CPU), `describe` (Ollama vision → .txt).
- **Core** (`core/image/`): `transform.py` com 9 funções puras; `background.py` — `remove_background()` via rembg (imports lazy, extra `[ai-image]`); `describe.py` — `describe_image()` + `save_description()` via LangChain + Ollama.
- **GUI** (`form_view.py`): `ImageArgs` com 33 campos. Card `remove_bg` desabilitado com tooltip quando extra não instalado (`_UNAVAILABLE`). Blocos `rembg_block` e `describe_block` com Dropdown de modelo. Formato oculto para `favicon` e `describe`.
- **Visor Before/After**: `_single_pane` (placeholder ou input thumb) e `_before_after_row` (Antes/Depois em `ft.Row`) num `ft.Row` pai, toggle por `visible=`. `_last_input_thumb` preserva o thumb do input para o split após `image_op_done`.
- **Formatos**: JPG, PNG, WebP, AVIF, TIFF, BMP, GIF, ICO. `LOSSY_FMTS = {"jpg", "jpeg", "webp"}`.
- **`pipeline_log.py`**: fonte única de mensagens do módulo — constantes `OP_VERBS`/`OP_LABELS`, builders `fmt_*` por operação (metadados PIL, detalhes de cada op, rembg, describe), `resolve_messages()` e `resolve_stage_label()` usados por `view.py`. `worker.py` emite metadados lazy (`_try_read_meta` lê cabeçalho sem decodificar pixels) e detalhe específico antes de cada chamada ao core. **Padrão a replicar nos módulos Áudio e Vídeo (PR4).**
- **Saída**: downloads → `output/image/source/`; processadas → `output/image/processed/`.

## Splash + spinner (branding)

- **Splash** (`gui/splash.py`): fade-in + scale + uma volta do cata-vento, então chama `build_app`. Cores via `Color.dark.*` — sem literais hardcoded.
- **Spinner**: `ft.Image` do cata-vento, giro encadeado via `on_animation_end` (curva LINEAR). Para na vertical ao terminar.
- **Assets** (`gui/assets.py`): `b64(name)` retorna bytes; `WINDOW_ICON` → `assets/icons/mill.ico`.

## Comandos

```bash
uv run gui.py                                        # GUI desktop
uv run main.py <YOUTUBE_URL>                         # transcrição básica
uv run main.py <URL> --format --analyze              # pipeline completo
uv run main.py <URL> --analyze --am gemini-2.5-flash # análise via Gemini
uv run -m src output/transcriptions/text/<file>.txt  # análise standalone
```

## Convenções de código

- Docstrings em todas as funções e módulos
- Logging via handler dedicado — nunca usar `print()` para logs
- Core (`src/core/`) é puro: sem dependência de Flet, reutilizável por CLI e GUI
- Linter: ruff · Testes: pytest (dev dependency)

## Dependências externas (PATH)

- `yt-dlp` e `ffmpeg`/`ffprobe` — verificados em runtime por `check_dependencies()`

## LLM pipeline (Formatter / Analyzer / Prompter)

- **Formatter**: `RecursiveCharacterTextSplitter` 4500 chars/150 overlap. Modelo padrão: `phi4mini-custom`.
- **Analyzer**: 4500 chars/300 overlap, merge parcial. 10 campos, tradução automática PT-BR. Modelo padrão: `qwen7b-custom`. Temperaturas 0.4 (análise) / 0.0 (tradução).
- **Prompter**: 4500 chars/200 overlap, ~40% de compressão. Remove CTAs/patrocinadores. Modelo padrão: `qwen7b-custom`.

## Métricas de qualidade de transcrição

`transcriber.py` sinaliza segmentos com `[?]`: `avg_logprob < -1.0` (tokens incertos) ou `no_speech_prob > 0.6` (silêncio/ruído).

## Ollama

- **qwen7b-custom**: Qwen 2.5 7B — `--analyze` (`ollama/Modelfile`)
- **phi4mini-custom**: Phi-4 Mini 3.8B — `--format` (`ollama/Modelfile.phi4mini`)
- **moondream-custom**: moondream vision — descrição de imagens (`ollama/Modelfile.vision`; `num_thread 2`, `num_gpu 0`)
- `num_gpu` controla camadas na GPU; `num_thread` controla threads CPU

## GUI Desktop (Flet 0.85)

Iniciada com `uv run gui.py`. Flutter desktop no Windows.

### Arquitetura

- **Sidebar (NavigationRail)** + `ft.Stack` com todos os módulos montados; só um visível por vez (toggle de `visible`).
- **EventBus** (`events.py`): publica `PipelineEvent(type, stage, payload, module_id)` via `page.pubsub.send_all()` (thread-safe). Worker em thread daemon; UI atualiza na thread principal.
- **LogEventHandler**: captura `logging.INFO` e encaminha como eventos `log`. `_SUPPRESSED_PREFIXES` filtra duplicados. Recebe `module_id`.
- **`pipeline_log.py` (por módulo)**: vocabulário centralizado de mensagens — `worker.py` importa `fmt_*` para `emit("log", ...)`, `view.py` importa `resolve_messages()`/`resolve_stage_label()`. Separa "o que emitir" de "como exibir" e elimina strings inline espalhadas. Implementado em `modules/image/`; padrão para módulos futuros.
- **Design System** (`theme/components/`): factories, tokens de tipografia, cursores e help system → skill `design-system` (`.claude/skills/design-system/SKILL.md`).

### Flet 0.85 — quirks conhecidos

| API antiga / armadilha | Correto no 0.85 |
|---|---|
| `ft.Tabs`/`ft.Tab` | abas manuais com `TextButton` + `visible=` |
| `ft.border.all(w, c)` | `ft.Border(left=ft.BorderSide(...), ...)` |
| `ft.alignment.center` | `ft.Alignment.CENTER` |
| `ft.Image(src_base64=...)` | `ft.Image(src=<bytes>)` — `src` posicional e **obrigatório** mesmo para imagem vazia |
| `rotate=<float>` | `ft.Rotate(angle=, alignment=ft.Alignment.CENTER)`; animar mutando `.angle` |
| `animate_*` | `int` (ms, LINEAR), `bool` ou `ft.Animation(dur, ft.AnimationCurve.X)` |
| FilePicker | `page.services.append(picker)` + async `await picker.pick_files(...)` |
| trocar `Container.content` em runtime | reatribuir árvore quebra o patcher → toggle de `visible` num Stack |
| `page.update()` em cascata | causa IndexError no `object_patch` — um update por evento |
| `ft.Column(controls=[]).append()` | preferir `Container(content=None)` (diff None→árvore quebra) |
| `ft.ImageFit.CONTAIN` | `ft.BoxFit.CONTAIN` — `ft.ImageFit` não existe no 0.85 |
| `control.page` antes do mount | lança `RuntimeError` — proteger com `try/except RuntimeError` |
| `ColorScheme.surface` vs page.bgcolor | `surface` → `ft.Colors.SURFACE` (painéis). `page.bgcolor` explícito via `sync_page_bgcolor(page)` |
| `surface_variant` / `surface_container_*` no ColorScheme | kwargs inválidos — geram `TypeError`. Suportados: `surface`, `on_surface`, `on_surface_variant`, `outline`, `outline_variant` |
| `ft.Colors.SURFACE_VARIANT` / `SURFACE_CONTAINER` | não existem no 0.85 — geram `AttributeError`. Usar `ft.Colors.SURFACE` |
| `BoxDecoration(shadow=...)` | deve ser `shadows=[ft.BoxShadow(...)]` — plural, lista |
| `Container(box_shadow=...)` | deve ser `Container(shadow=ft.BoxShadow(...))` — sem prefixo `box_` |
| `ink=True` em Container | cria Flutter InkWell que **absorve** eventos de ponteiro e anula o cursor do GestureDetector externo — cursor só aparece nas margens. Nunca usar `ink=True` em containers clicáveis; usar `GestureDetector` externo + `Cursor.*` |
| `ft.Tooltip` sem `size_constraints` | texto renderiza em linha única sem quebra. Usar `size_constraints=ft.BoxConstraints(max_width=280)` |
| `ft.NavigationRailDestination` cursor | não tem propriedade `mouse_cursor`. Solução: envolver o `NavigationRail` num `ft.GestureDetector(mouse_cursor=Cursor.interactive)` e alternar para `Cursor.forbidden` via `page.pubsub` quando pipeline estiver rodando |
| `ButtonStyle.mouse_cursor` | aceita valor flat (`Cursor.interactive`) **ou** dict por estado (`Cursor.btn`). `ControlState.DISABLED` existe e funciona — usar `Cursor.btn` em botões que podem ser desabilitados |

### Eventos do pipeline

`PipelineEvent(type, stage, payload, module_id)`. `module_id` ∈ {`"transcription"`, `"audio"`, `"image"`, `""` (legado)}. O `ProgressPanel` ignora eventos cujo `module_id` ≠ `owner_id`.

**Genéricos (todos os módulos):**

| Evento | Payload | Efeito na UI |
|---|---|---|
| `progress_start` | — | barra indeterminada + inicia spinner |
| `progress_update` | `current`, `total` (0–1) | barra determinada |
| `queue_progress` | `current_item`, `total_items`, `item_name` | label "Item 2/5 — arquivo.mp3" |
| `task_done` | `output_path(s)` | barra 1.0, para spinner, habilita Resultados |
| `task_error` | `message` | log de erro, para spinner |
| `log` | `message`, `level` | passthrough colorido |

**Áudio (stage="audio"):** `audio_op_start` (`operation`, `item_name`, `item_idx`, `total`), `audio_op_done` (`output_path`, `elapsed`).

**Imagens (stage="image"):** `image_op_start` (`operation`, `item_name`, `item_idx`, `total_items`, `thumb: bytes|None`), `image_op_done` (`output_path`, `elapsed`, `src_size_bytes`, `out_size_bytes`, `thumb`, `item_idx`, `total_items`), `image_op_error` (`item_name`, `message`).

**Transcrição (stage específico):** `metadata_start/done`, `audio_cached`, `download_start/done`, `whisper_loading/loaded`, `transcribe_started`, `language_detected` (`audio_duration`), `transcribe_segment` (`end`, `is_low_confidence`), `transcribe_summary`, `format_*`, `analyze_*`, `translation_*`, `prompt_*`.

### Barra de progresso

- **Idle**: oculta, label "Inicie o pipeline pelo formulário →"
- **Indeterminada**: ao primeiro evento de início (`value=None`)
- **Determinada (transcrição)**: `transcribe_segment.end / audio_duration`
- **Determinada (áudio)**: `progress_update(current/total)` (download bytes ou ffmpeg `out_time`)
- **Chunks (format/analyze/prompt)**: `i / total`

### Modelos disponíveis na GUI (dropdowns de Transcrição)

| Campo | Opções |
|---|---|
| Formatação | `phi4mini-custom`, `qwen7b-custom` |
| Análise | `gemini-2.5-flash`, `qwen7b-custom` |
| Prompt-ready | `gemini-2.5-flash`, `qwen7b-custom` |

### Thread safety

- `bus.emit()` roda na worker thread; `page.pubsub.send_all()` é thread-safe; callbacks de `subscribe` rodam na UI thread.
- `pipeline_running[0]` é resetado em `finally` (sucesso/erro/cancelamento) — senão a navegação trava.
- Não chamar `page.update()` em cascata no mesmo evento.

### GPU — sobrecarga e estabilidade (MX150 / Pascal)

Flet (DirectX) e Whisper (CUDA) disputam a MX150. Uso simultâneo pode causar BSOD `WIN32K_POWER_WATCHDOG_TIMEOUT`. Mitigações: `LogEventHandler` em INFO; libs ruidosas capadas em WARNING; fila de áudio sequencial. Se persistir: forçar `python.exe` em "Economia de energia" (iGPU Intel) nas configurações de gráficos do Windows.

## Roadmap

- **PR3.1** — IA de áudio opcional (extra `[ai-audio]`): DeepFilterNet (denoise, CPU); Demucs (stems) a decidir.
- **PR4** — Módulo Vídeo (análogo ao Áudio: mesmo InputSource, fila e eventos).
- **Futuro** — melhorias no Módulo Imagens (batch rename, redimensionamento guiado); IA de imagens (upscale).
- **Fora de escopo (definitivo)** — arrastar arquivos do SO (não nativo no Flet).
