# mill.tools

Multiferramenta pessoal extensível para processamento de áudio, vídeo e transcrição, com GUI desktop (Flet) e CLI. O módulo de Transcrição usa faster-whisper com aceleração GPU — 100% local. A GUI é organizada em **módulos** acessíveis por uma sidebar (NavigationRail).

## Stack

- **Python 3.13** gerenciado com `uv`
- **faster-whisper** + **ctranslate2** — transcrição via Whisper (sem PyTorch, por escolha)
- **yt-dlp** — download de áudio/vídeo e metadados
- **ffmpeg** — conversão/extração de áudio
- **Pillow 12.2+** — processamento de imagens (AVIF nativo, EXIF transpose, conversão multi-formato)
- **LangChain** + **Ollama** (local) / **Google Gemini** (nuvem) — formatação, análise e condensação
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
main.py                          — entry point, CLI (argparse)
gui.py                           — entry point, GUI desktop (Flet); mostra splash → build_app
src/
├── __init__.py
├── __main__.py                  — entry point do analyzer standalone
├── transcriber.py               — transcribe(), _resolve_device(), print_summary()
├── formatter.py                 — format_transcription(), parágrafos via LLM
├── analyzer.py                  — analyze(), análise estruturada via LangChain
├── prompter.py                  — build_prompt_ready(), condensação prompt-ready
├── llm_factory.py               — roteamento gemini-* → Google, demais → Ollama
├── utils.py                     — logging, validação, metadata, download, paths de output
├── core/                        — lógica pura (sem Flet), reutilizável por CLI e GUI
│   ├── audio/
│   │   ├── downloader.py        — yt-dlp: URL → output/audio/source/ (embed_meta, fallback ogg/opus)
│   │   ├── converter.py         — ffmpeg (-progress pipe:1): convert_audio(), extract_audio()
│   │   └── info.py              — get_duration_ffprobe() (duração via ffprobe)
│   └── image/
│       ├── downloader.py        — urllib: URL → output/image/source/ (valida com Pillow)
│       ├── converter.py         — convert_image(): EXIF transpose, RGBA→RGB, quality só para lossy
│       └── info.py              — image_info() + thumbnail_bytes() (miniatura para o visor)
└── gui/
    ├── app.py                   — build_app(): NavigationRail + registry de módulos + navigate_to
    ├── splash.py                — show_splash(): tela de abertura (cata-vento + fade) → build_app
    ├── assets.py                — b64() (bytes p/ ft.Image), WINDOW_ICON (path do .ico)
    ├── events.py                — EventBus, PipelineEvent (com module_id), LogEventHandler
    ├── settings.py              — persistência em ~/.mill-tools/config.json
    ├── workers.py               — pipeline de Transcrição em thread (module_id="transcription")
    ├── components/
    │   └── input_source.py      — InputItem, InputSource (URL + FilePicker, allow_multiple, url_hint)
    ├── modules/                 — sistema de módulos da sidebar
    │   ├── base.py              — dataclass Module (id, label, icon, control, on_mount/on_unmount)
    │   ├── transcription/view.py — build_transcription_module() (owner_id="transcription")
    │   ├── audio/               — form_view.py, worker.py, view.py (módulo Áudio, PR3)
    │   ├── image/               — form_view.py, worker.py, view.py (módulo Imagens, PR-IMG-1)
    │   └── video/view.py        — placeholder (PR4)
    └── views/
        ├── form_view.py         — formulário de Transcrição → FormPanel
        ├── progress_view.py     — ProgressPanel (logs/barra/spinner), filtro por owner_id
        └── result_view.py       — resultados em abas (Transcrição/Análise/Digest)
assets/
├── logo/                        — mill-symbol.(svg|png), mill-logo-wordmark*.(svg|png), mill-icon-256.png
└── icons/                       — mill.ico (multi-res), mill-512.png (p/ flet build)
ollama/
├── Modelfile                    — config do qwen7b-custom
└── Modelfile.phi4mini           — config do phi4mini-custom
docs/                            — planos de implementação (migração, PRs, splash, ícone, etc.)
output/
├── audio/
│   ├── source/                  — áudios baixados de URLs
│   └── processed/               — áudios convertidos/extraídos de vídeo
├── image/
│   ├── source/                  — imagens baixadas de URL
│   └── processed/               — imagens convertidas
├── video/
│   └── processed/               — vídeos baixados/convertidos (PR4)
└── transcriptions/
    ├── text/                    — transcrições brutas (.txt)
    ├── analysis/                — análises estruturadas (.md)
    └── digest/                  — versões condensadas prompt-ready (.txt)
```

> Arquivos gerados antes da migração (em `audios/` e `transcriptions/`) ficam nos caminhos originais — não foram movidos.

## Sistema de módulos (GUI)

A GUI é dividida em módulos selecionáveis numa **NavigationRail** à esquerda. Estado:
**Áudio** (PR3, completo), **Vídeo** (placeholder, PR4), **Imagens** (PR-IMG-1, completo), **Transcrição** (completo).
Ordem na rail: Áudio → Vídeo → Imagens → Transcrição.

- **Registry** (`app.py`): `MODULES: list[Module]` é a fonte única; a rail e o conteúdo são gerados dele. Adicionar um módulo = uma entrada na lista.
- **Module** (`modules/base.py`): dataclass com `id`, `label`, `icon`, `selected_icon`, `control`, `on_mount(payload)`, `on_unmount()`. O `control` é construído uma vez; trocar de aba **não** destrói o estado (log/barra/resultado preservados).
- **navigate_to(module_id, payload)**: alterna **visibilidade** dos controles num `ft.Stack` (não reatribui `content` — evita o `object_patch` IndexError do Flet 0.85). **Bloqueia a troca** enquanto `pipeline_running[0]` for `True` (mostra SnackBar e restaura a seleção da rail).
- **Bridge Áudio → Transcrição**: o botão "Transcrever este arquivo" chama `navigate_to("transcription", {"file": path})`; o `on_mount` do módulo de Transcrição preenche o campo de URL com o caminho (localiza o `url_field` percorrendo a árvore de controles).
- **Escopo de eventos por módulo**: cada `ProgressPanel` recebe um `owner_id` e ignora eventos cujo `module_id` não casa — evita cross-talk entre os painéis dos módulos (todos recebem todo evento via `pubsub.send_all`).

## Módulo Áudio (PR3)

Substitui o placeholder por download/conversão/extração de áudio.

- **Operações** (auto-detectadas por item da fila): `url` → download; arquivo de **vídeo** → extração; arquivo de **áudio** → conversão.
- **Entrada** (`components/input_source.py`): duas fontes — **URL** (TextField) e **seleção de arquivos** (`FilePicker` via `page.services`, `allow_multiple=True`). Cada item é `InputItem(kind="url"|"local", value)`. (Arrastar do SO ficou **fora de escopo** — não é nativo no Flet.)
- **Formato/qualidade**: `best`/mp3/m4a/wav/ogg/opus + bitrate (320…64 kb/s, só lossy). `best` preserva o codec da fonte sem reencode.
- **Capa + metadados**: embutidos por padrão (`--embed-metadata --embed-thumbnail`), switch desligável visível só quando há itens de URL. Fallback gracioso em ogg/opus (omite a capa, segue só com metadados).
- **Fila sequencial**: um item por vez (serializa CPU/ffmpeg e a GPU). Progresso via `queue_progress` (item N/M) + `progress_update` (item atual).
- **Core** (`core/audio/`): funções puras, sem Flet. Download via yt-dlp (`postprocessor_hooks`); conversão/extração via ffmpeg com `-progress pipe:1 -nostats` + `ffprobe` para duração (barra determinada; cai para indeterminada se não houver duração).
- **Saída**: downloads → `output/audio/source/`; convertidos/extraídos → `output/audio/processed/`.

> IA de áudio (denoise/stems) **não** está no PR3 — planejada para o **PR3.1** (DeepFilterNet primeiro; Demucs a decidir), isolada em extra opcional torch.

## Módulo Imagens (PR-IMG-1)

Conversão de imagens entre 8 formatos com visor de pré-visualização integrado.

- **Formatos**: JPG, PNG, WebP, AVIF, TIFF, BMP, GIF, ICO. `LOSSY_FMTS = {"jpg", "webp"}` — slider de qualidade ativo só para estes.
- **Entrada** (`components/input_source.py`): URL direta (urllib, validada com Pillow) ou arquivos locais (`FilePicker`). `url_hint` parametrizável.
- **Qualidade**: slider 50–100 (só para lossy). `on_change` atualiza estado interno; `on_change_end` atualiza o texto do valor — separa para evitar o disparo espúrio do Flet na renderização inicial.
- **Visor**: `ft.Image` com `_BLANK_PNG` (1×1 px transparente) como `src` inicial obrigatório. Placeholder + imagem num `ft.Stack`, alternados por `visible=`. Miniatura gerada via `thumbnail_bytes()` (Pillow, `Image.thumbnail()`, máx 600 px).
- **Core** (`core/image/`): `download_image()` (urllib + User-Agent + verify), `convert_image()` (EXIF transpose, RGBA→RGB flatten para JPEG, `optimize=True` para PNG), `image_info()`, `thumbnail_bytes()`.
- **Fila sequencial**: erro por item não interrompe a fila. Eventos: `image_op_start` (com thumb), `image_op_done` (com thumb, elapsed, src_size_bytes, out_size_bytes), `image_op_error`.
- **Saída**: downloads → `output/image/source/`; convertidas → `output/image/processed/`.
- **Paths** (`utils.py`): `IMAGE_SOURCE_DIR`, `IMAGE_PROCESSED_DIR`.

## Splash + spinner (branding)

- **Splash** (`gui/splash.py`): `show_splash(page, on_complete)` mostra o cata-vento (fade-in + scale + uma volta) sobre o azul-escuro do GUI e, ao fim, chama `build_app`. Roda no event loop via `page.run_task`.
- **Spinner do header**: no `ProgressPanel`, a engrenagem foi trocada por um `ft.Image` do cata-vento que **gira continuamente enquanto o pipeline trabalha** (giro encadeado via `on_animation_end`, curva **LINEAR**) e **para na vertical** ao terminar.
- **Assets** (`gui/assets.py`): `b64(name)` lê de `assets/logo/` e retorna **bytes** (Flet 0.85: `ft.Image(src=bytes)`); `WINDOW_ICON` aponta para `assets/icons/mill.ico` (use em `page.window.icon`, Windows-only).

## Comandos

```bash
# GUI desktop
uv run gui.py

# Transcrição básica (CLI)
uv run main.py <YOUTUBE_URL>

# Opções comuns
uv run main.py <URL> --wm medium --language pt --verbose
uv run main.py <URL> --format               # + parágrafos
uv run main.py <URL> --analyze              # + análise estruturada
uv run main.py <URL> --format --analyze     # pipeline completo
uv run main.py <URL> --prompt               # versão condensada (digest)

# Provider na nuvem (requer GOOGLE_API_KEY no .env)
uv run main.py <URL> --analyze --am gemini-2.5-flash

# Análise standalone (sobre transcrição existente)
uv run -m src output/transcriptions/text/transcricao_ovabeV.txt

# Ollama direto
ollama run qwen7b-custom "prompt aqui"
```

## CLI flags (módulo Transcrição)

| Flag            | Default           | Descrição                                                     |
|-----------------|-------------------|---------------------------------------------------------------|
| `--wm`          | small             | Whisper model: tiny/base/small/medium/large-v3-turbo/large-v3 |
| `--language`    | auto              | Código do idioma (pt, en, etc.)                               |
| `--threads`     | 2                 | Threads CPU (só em fallback CPU)                              |
| `--beam-size`   | 1                 | Beam size (1=rápido, 5=preciso)                               |
| `--output-name` | None              | Nome customizado do arquivo de saída                          |
| `--format`      | False             | Insere quebras de parágrafo via LLM                           |
| `--fm`          | phi4mini-custom   | Modelo de formatação — Ollama tag ou `gemini-*`               |
| `--analyze`     | False             | Roda análise estruturada após transcrição                     |
| `--am`          | qwen7b-custom     | Modelo de análise — Ollama tag ou `gemini-*`                  |
| `--prompt`      | False             | Gera versão condensada (digest)                               |
| `--pm`          | qwen7b-custom     | Modelo de condensação — Ollama tag ou `gemini-*`              |
| `--verbose`     | False             | Ativa logging DEBUG                                           |

## Convenções de código

- Docstrings em todas as funções e módulos
- Logging via handler dedicado — nunca usar print() para logs
- Core (`src/core/`) é puro: sem dependência de Flet, reutilizável por CLI e GUI
- Linter: ruff · Testes: pytest (dev dependency)
- Slugs de áudio: 6 primeiros chars alfanuméricos do video ID

## Dependências externas (PATH)

- `yt-dlp` e `ffmpeg`/`ffprobe` — verificados em runtime por `check_dependencies()`

## Formatter

LangChain + LLM para inserir quebras de parágrafo, preservando o texto original.
- **Chunking**: `RecursiveCharacterTextSplitter` (4500 chars, 150 overlap)
- **Output**: reescreve o `.txt` com parágrafos; retorna o body para o analyzer
- **Modelo padrão**: phi4mini-custom

## Analyzer

LangChain + LLM para análise estruturada. Standalone (`uv run -m src <arquivo>`) ou via `--analyze`.
- **Chunking**: 4500 chars, 300 overlap — merge das análises parciais
- **Output**: `.md` com header + summary, key_points, action_items, key_concepts, tools_mentioned, metrics, quotes, assumptions, vocabulary, sentiment_arc
- **Modelo padrão**: qwen7b-custom · **Tradução automática** para PT-BR · temperaturas 0.4 (análise) / 0.0 (idioma/tradução)

## Prompter

Versão condensada para uso como contexto em prompts. Via `--prompt`.
- **Chunking**: 4500 chars, 200 overlap · **Output**: `.txt` em `output/transcriptions/digest/`
- **Remove** cumprimentos/CTAs/patrocinadores/preenchimento; **mantém** todo conteúdo técnico
- **Compressão**: ~40% · **Modelo padrão**: qwen7b-custom

## Métricas de qualidade de transcrição

`transcriber.py` sinaliza segmentos de baixa confiança com `[?]` no `.txt`:
- `avg_logprob < -1.0` (tokens incertos) ou `no_speech_prob > 0.6` (silêncio/ruído)
- Log final informa a contagem total de segmentos flagados

## Ollama

- **qwen7b-custom**: Qwen 2.5 7B, usado em `--analyze` (`ollama/Modelfile`)
- **phi4mini-custom**: Phi-4 Mini 3.8B, usado em `--format` (`ollama/Modelfile.phi4mini`)
- `num_gpu` controla camadas na GPU; `num_thread` controla threads CPU

## GUI Desktop (Flet 0.85)

Iniciada com `uv run gui.py`. Flutter desktop no Windows.

### Arquitetura

- **Sidebar (NavigationRail)** + `ft.Stack` com todos os módulos montados; só um visível por vez (toggle de `visible`).
- **EventBus** (`events.py`): publica `PipelineEvent(type, stage, payload, module_id)` via `page.pubsub.send_all()` (thread-safe). Worker em thread daemon; UI atualiza na thread principal.
- **LogEventHandler**: captura `logging.INFO` e encaminha como eventos `log` (nível INFO evita flood de libs terceiras; `_SUPPRESSED_PREFIXES` filtra duplicados). Recebe `module_id`.
- **ProgressPanel** (`progress_view.py`): filtra por `owner_id`; spinner do cata-vento; `on_show_results` customizável por módulo (a Transcrição mostra abas; o Áudio mostra resultados + botão "Transcrever este arquivo").
- **FormPanel** (`form_view.py`): `set_running(bool)` desabilita o botão Iniciar com ampulheta.
- **Design System** (`theme/components/`): todos os módulos importam **exclusivamente** via `src.gui.theme.components` (o `__init__` é a interface pública). Cross-imports internos entre submódulos do DS são permitidos. Fábricas disponíveis: `primary_button`, `secondary_button`, `danger_button`, `action_button` (link-style, acento configurável), `segmented_selector`, `output_card` (card com borda colorida + botão abrir pasta), `spinner()` → `(control, start, stop)`, `log_line`, `summary_card`, `section_title`, `labeled_field`, `slider_row`, `switch_row`, `hairline`, `module_scaffold`, `section`, `section_label`, `help_icon`, `help_icon_for`.

### Flet 0.85 — quirks conhecidos

| API antiga / armadilha | Correto no 0.85 |
|---|---|
| `ft.Tabs`/`ft.Tab` | abas manuais com `TextButton` + `visible=` |
| `ft.border.all(w, c)` | `ft.Border(left=ft.BorderSide(...), ...)` |
| `ft.alignment.center` | `ft.Alignment.CENTER` |
| `ft.Image(src_base64=...)` | `ft.Image(src=<bytes>)` — `src` é posicional e **obrigatório** mesmo para imagem vazia |
| `rotate=<float>` | `ft.Rotate(angle=, alignment=ft.Alignment.CENTER)`; animar mutando `.angle` |
| `animate_*` | `int` (ms, LINEAR), `bool` ou `ft.Animation(dur, ft.AnimationCurve.X)` |
| FilePicker | adicionar via `page.services`; resultado por callback (assíncrono) |
| trocar `Container.content` em runtime | reatribuir árvore quebra o patcher → usar toggle de `visible` num Stack |
| `page.update()` em cascata | causa IndexError no `object_patch` — um update por evento |
| `ft.Column(controls=[]).append()` | preferir a `Container(content=None)` (diff None→árvore quebra) |
| `ft.ImageFit.CONTAIN` | `ft.BoxFit.CONTAIN` — `ft.ImageFit` não existe no 0.85 |
| `control.page` antes do mount | lança `RuntimeError` (não retorna `None`) — proteger com `try/except RuntimeError` |
| `ColorScheme.surface` vs page.bgcolor | `surface` → `ft.Colors.SURFACE` (painéis/cards) — **não** controla o fundo do Scaffold. Usar `page.bgcolor` explícito + `sync_page_bgcolor()` do DS |
| `surface_container_low` / `surface_container` no ColorScheme | não reconhecidos pelo Flet 0.85 — são ignorados silenciosamente. Usar `surface` + `surface_variant` |

### Eventos do pipeline

`PipelineEvent(type, stage, payload, module_id)`. `module_id` ∈ {`"transcription"`, `"audio"`, `"image"`, `""` (legado/global)}. O `ProgressPanel` ignora eventos cujo `module_id` ≠ `owner_id`.

**Genéricos (todos os módulos):**

| Evento | Payload | Efeito na UI |
|---|---|---|
| `progress_start` | — | barra indeterminada + inicia spinner |
| `progress_update` | `current`, `total` (0–1) | barra determinada |
| `queue_progress` | `current_item`, `total_items`, `item_name` | label "Item 2/5 — arquivo.mp3" |
| `task_done` | `output_path(s)` | barra 1.0, para spinner, habilita Resultados |
| `task_error` | `message` | log de erro, para spinner |
| `log` | `message`, `level` | passthrough colorido |

> Os eventos legados `pipeline_done`/`pipeline_error` foram **removidos** — a Transcrição agora usa `task_done`/`task_error`.

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

Flet (DirectX) e Whisper (CUDA) disputam a MX150. Uso simultâneo pode causar BSOD `WIN32K_POWER_WATCHDOG_TIMEOUT`. Mitigações: `LogEventHandler` em INFO; libs ruidosas capadas em WARNING; fila de áudio sequencial. Se persistir: forçar `python.exe` em "Economia de energia" (iGPU Intel) nas configurações de gráficos do Windows. O Flet 0.85 desktop não expõe `--disable-gpu`.

## Roadmap

- **PR3.1** — IA de áudio opcional (extra `[ai-audio]`): DeepFilterNet (denoise, CPU); Demucs (stems) a decidir.
- **PR4** — Módulo Vídeo (análogo ao Áudio: mesmo InputSource, fila e eventos).
- **Futuro** — melhorias no Módulo Imagens (batch rename, redimensionamento, crop); IA de imagens (upscale/remoção de fundo).
- **Fora de escopo (definitivo)** — arrastar arquivos do SO (não nativo no Flet).
