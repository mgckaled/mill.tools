# mill.tools

Multiferramenta pessoal extensível para processamento de áudio, vídeo e transcrição, com GUI desktop (Flet) e CLI. O módulo de Transcrição usa faster-whisper com aceleração GPU — 100% local. A GUI é organizada em **módulos** acessíveis por uma sidebar (NavigationRail).

## Stack

- **Python 3.13** gerenciado com `uv`
- **faster-whisper** + **ctranslate2** — transcrição via Whisper (sem PyTorch, por escolha)
- **yt-dlp** — download de áudio/vídeo e metadados
- **ffmpeg** — conversão/extração de áudio e normalização loudnorm (EBU R128)
- **noisereduce>=3.0** + **soundfile>=0.12** — spectral gating e I/O PCM (pós-processamento de áudio, CPU-only, sem torch)
- **sounddevice>=0.4** — reprodução de áudio PCM via PortAudio (CPU-only, sem torch); usado pelo reprodutor embutido na GUI
- **Pillow 12.2+** — processamento de imagens (AVIF nativo, EXIF transpose, conversão multi-formato)
- **rembg[cpu]** + **onnxruntime** (extra `[ai-image]`) — remoção de fundo CPU/ONNX
- **LangChain** + **Ollama** (local) / **Google Gemini** (nuvem) — formatação, análise, condensação e descrição de imagens (vision)
- **Flet 0.85** — GUI desktop (Flutter no Windows); constraint em `pyproject.toml`: `flet>=0.28`, versão instalada e testada: 0.85.2
- **tqdm** — barra de progresso (CLI)

> Decisão consciente: o projeto evita **PyTorch**. O pós-processamento de áudio (denoise + normalize) é CPU-only e torch-free. Qualquer IA que dependa de torch (ex.: Demucs, DeepFilterNet neural) ficará isolada num extra opcional `[ai-audio]` — o app base permanece torch-free.

## Estrutura

```
main.py                          — entry point CLI (argparse); despacha audio/video/image para src/cli/
gui.py                           — entry point GUI (splash → home → build_app)
src/
├── transcriber.py · formatter.py · analyzer.py · prompter.py
├── llm_factory.py               — roteamento gemini-* → Google, demais → Ollama
├── llm_utils.py                 — split_text(): chunking compartilhado + bypass Gemini (1M ctx)
├── utils.py                     — logging, validação, metadata, paths de output, sanitize_filename()
├── cli/
│   ├── bus.py                   — CLIEventBus: TqdmLoggingHandler + barra tqdm (sem Flet)
│   ├── transcription.py         — resolve_input(), build_output_stem() (helpers CLI)
│   ├── audio.py                 — subcomando `audio`: add_audio_parser(), run_audio_cli()
│   ├── video.py                 — subcomando `video`: 7 sub-subcomandos (download/convert/trim/…)
│   └── image.py                 — subcomando `image`: 12 sub-subcomandos (convert/resize/crop/…)
├── core/
│   ├── ffmpeg.py                — run_ffmpeg(): runner binário compartilhado com progresso pipe:1
│   ├── io_types.py              — InputItem: dataclass(kind, value) — compartilhado CLI e GUI
│   ├── audio/
│   │   ├── args.py              — AudioArgs: parâmetros do pipeline de áudio
│   │   ├── downloader.py        — yt-dlp: URL → output/audio/source/
│   │   ├── converter.py         — ffmpeg: convert_audio(), extract_audio() (usa core.ffmpeg)
│   │   ├── denoiser.py          — denoise() via noisereduce + soundfile (spectral gating, CPU)
│   │   ├── normalizer.py        — normalize_lufs() via ffmpeg loudnorm, dois passes (EBU R128)
│   │   └── info.py              — get_duration_ffprobe()
│   ├── video/
│   │   ├── __init__.py
│   │   ├── args.py              — VideoArgs: parâmetros do pipeline de vídeo
│   │   ├── downloader.py        — yt-dlp: URL → output/video/source/
│   │   ├── converter.py         — ffmpeg: convert, trim, compress, resize, extract_audio, thumbnail (usa core.ffmpeg)
│   │   └── info.py              — get_video_info() via ffprobe (VideoInfo dataclass)
│   └── image/
│       ├── args.py              — ImageArgs: parâmetros do pipeline de imagens
│       ├── downloader.py        — urllib: URL → output/image/source/
│       ├── converter.py         — convert_image(): EXIF transpose, RGBA→RGB, quality lossy
│       ├── transform.py         — 9 funções de manipulação (resize/crop/rotate/watermark/border/adjust/filter/favicon/contact_sheet)
│       ├── background.py        — remove_background() via rembg/ONNX (imports lazy; extra [ai-image])
│       ├── describe.py          — describe_image() + save_description() via LangChain + Ollama vision
│       └── info.py              — image_info() + thumbnail_bytes()
└── gui/
    ├── app.py                   — build_app(): NavigationRail + registry de módulos + navigate_to
    ├── splash.py                — show_splash(): cata-vento + fade → show_home
    ├── home.py                  — show_home(): 4 cards de módulo + moinho animado → build_app(initial_module)
    ├── assets.py                — b64() (bytes p/ ft.Image), WINDOW_ICON
    ├── events.py                — EventBus, PipelineEvent (com module_id), LogEventHandler
    ├── settings.py              — persistência em ~/.mill-tools/config.json
    ├── workers.py               — pipeline de Transcrição em thread (module_id="transcription")
    ├── help_content.py          — HELP_SHORT/LONG: registro central de tooltips/modais
    ├── components/
    │   ├── input_source.py      — InputSource (URL + FilePicker, allow_multiple); InputItem → core/io_types.py
    │   └── audio_player.py      — build_audio_player(): reprodutor play/pause/seek via sounddevice + ffmpeg; AudioPlayer.load(path)
    ├── modules/
    │   ├── base.py              — dataclass Module (id, label, icon, control, on_mount/on_unmount)
    │   ├── _pipeline_runner.py  — run_queue_pipeline(): loop base compartilhado por audio/video/image
    │   ├── transcription/       — view.py, pipeline_log.py
    │   ├── audio/               — form_view.py, worker.py, view.py, pipeline_log.py
    │   ├── image/               — form_view.py, worker.py, view.py, pipeline_log.py, blocks/ (12 blocos)
    │   └── video/               — form_view.py, worker.py, view.py, pipeline_log.py
    ├── theme/
    │   ├── theme.py             — apply_theme(), sync_page_bgcolor()
    │   ├── tokens.py            — Color, Type, Space, Radius, Motion, Layout
    │   └── components/          — factories de botões, cards, inputs, layout, feedback, help; Cursor; sliders.py
    └── views/
        ├── form_view.py         — formulário de Transcrição → FormPanel
        ├── progress_view.py     — ProgressPanel (logs/barra/spinner), filtro por owner_id; dispatcha para pipeline_log de cada módulo
        └── result_view.py       — resultados em abas (Transcrição/Análise/Digest)
```

## Sistema de módulos (GUI)

A GUI é dividida em módulos selecionáveis numa **NavigationRail** à esquerda. Módulos disponíveis: **Áudio**, **Vídeo**, **Imagens**, **Transcrição** — todos completos. Ordem na rail: Áudio → Vídeo → Imagens → Transcrição.

A entrada no app é mediada pela **Home Screen** (`src/gui/home.py`): ao clicar num card, `on_complete(module_id)` chama `build_app(initial_module=mid)` — o módulo escolhido abre diretamente sem passar pelo módulo padrão.

- **Registry** (`src/gui/app.py`): `MODULES: list[Module]` é a fonte única. Adicionar um módulo = uma entrada na lista.
- **Module** (`src/gui/modules/base.py`): dataclass com `id`, `label`, `icon`, `selected_icon`, `control`, `on_mount(payload)`, `on_unmount()`. O `control` é construído uma vez; trocar de aba **não** destrói o estado.
- **navigate_to(module_id, payload)**: alterna **visibilidade** dos controles num `ft.Stack` (não reatribui `content` — evita o `object_patch` IndexError do Flet 0.85). **Bloqueia a troca** enquanto `pipeline_running[0]` for `True`.
- **Bridge Áudio → Transcrição**: `navigate_to("transcription", {"file": path})` — o `on_mount` preenche o campo URL percorrendo a árvore de controles.
- **Bridge Vídeo → Transcrição/Áudio**: resultado de `extract_audio` exibe botões "Transcrever" e "Processar no Áudio" no painel de resultados de vídeo.
- **Escopo de eventos por módulo**: cada `ProgressPanel` recebe um `owner_id` e ignora eventos cujo `module_id` não casa.

## Módulo Áudio

- **Operações principais** (auto-detectadas): URL → download; vídeo local → extração; áudio local → conversão.
- **Entrada**: URL + FilePicker via `page.services`, `allow_multiple=True`. Arrastar do SO fora de escopo.
- **Formato/qualidade**: `best`/mp3/m4a/wav/ogg/opus + bitrate (320…64 kb/s). `best` sem reencode.
- **Capa + metadados**: embutidos por padrão; switch desligável. Fallback gracioso em ogg/opus.
- **Fila sequencial**: um item por vez. Progresso via `queue_progress` + `progress_update`.
- **Saída**: downloads → `output/audio/source/`; convertidos/pós-processados → `output/audio/processed/`.
- **Reprodutor embutido** (`src/gui/components/audio_player.py`): aparece acima do log após o pipeline concluir. Decodifica via ffmpeg (qualquer formato) em thread de background, reproduz via sounddevice. UI: nome do arquivo + anel de carregamento + play/pause + seek slider (`on_change_end`). `AudioPlayer.load(path)` carregado automaticamente em `_on_done` com o primeiro arquivo de áudio de `output_paths`.

### Pós-processamento

Ativado por switches no formulário; as duas operações são encadeáveis após a operação principal.

| Operação | Módulo core | Detalhe técnico |
|---|---|---|
| **Reduzir ruído** | `denoiser.py` | Spectral gating via noisereduce (CPU-only). Decodifica via ffmpeg, processa canal por canal, salva WAV preservando subtype PCM original (`sf.info` + `subtype=meta.subtype`). |
| **Normalizar volume** | `normalizer.py` | EBU R128 via ffmpeg loudnorm em 2 passes: passe 1 mede IL/LRA/TP; passe 2 aplica ganho linear (`linear=true`). Alvo configurável −23..−6 LUFS. True Peak máx. −1 dBFS. Retorna `(path, stats_dict)`. |

- **`pipeline_log.py`**: vocabulário centralizado para 5 operações (download, convert, extract, denoise, normalize). Segue o padrão descrito em "Arquitetura GUI > pipeline_log.py".
- **`AudioArgs`**: expandido com `denoise: bool`, `normalize: bool`, `normalize_target_lufs: float = -14.0`. Estado persistido em `~/.mill-tools/config.json`.

## Módulo Vídeo

Download, conversão e processamento via yt-dlp e ffmpeg. Encoding 100% CPU — sem NVENC (decisão definitiva).

- **Operações** (7, selecionadas via card grid 3 colunas): `download` (yt-dlp), `convert` (codec/container), `trim` (corte por tempo, copy ou reenc), `compress` (H.264/CRF 18–28), `resize` (scale ffmpeg, aspect ratio preservado), `extract_audio` (bridge para `core/audio/converter.py`), `thumbnail` (frame → jpg/png).
- **Core** (`src/core/video/`): `info.py` — `VideoInfo` + `get_video_info()` via ffprobe; `downloader.py` — `download_video()` via yt-dlp com hook de progresso; `converter.py` — 6 funções ffmpeg delegando para `src.core.ffmpeg.run_ffmpeg`.
- **GUI** (`src/gui/modules/video/form_view.py`): `VideoArgs` com 17 campos. Detecção automática URL → operação forçada para `download` (seletor desabilitado). 7 blocos condicionais com `visible=`/`animate_opacity`.
- **`pipeline_log.py`**: 7 operações (download, convert, trim, compress, resize, extract_audio, thumbnail). Segue o padrão descrito em "Arquitetura GUI > pipeline_log.py".
- **Saída**: downloads → `output/video/source/`; processados → `output/video/processed/`.
- **Bridge extract_audio**: resultado de áudio exibe botões "Transcrever" e "Processar no Áudio" no painel de resultados.
- **Downloader — quirks Windows**: **Nunca usar `FFmpegVideoConvertor`** em nenhum formato (MP4, WebM ou outro) — o post-processor cria `.temp.<ext>` no diretório de saída e o Windows Defender bloqueia o rename com `[WinError 32]`. Usar apenas `merge_output_format` para garantir o container; ele opera sobre arquivos temporários em `%TEMP%`. Opções obrigatórias: `nopart=True`, `overwrites=True`, `paths={"temp": tempfile.gettempdir()}`. Solução definitiva: adicionar a pasta `output/` às exclusões do Windows Defender.
- **Progresso yt-dlp**: campos `_percent_str`, `_speed_str`, `_eta_str` contêm códigos ANSI — strip obrigatório antes de exibir: `re.sub(r'\x1b\[[0-9;]*m', '', s).strip()`.

## Módulo Imagens

Conversão, manipulação e operações de IA com visor Before/After integrado.

- **Operações** (12, selecionadas via card grid 3 colunas): `convert`, `resize` (caber/exato/escala%), `crop` (manual/proporção/auto-trim), `rotate` (ângulo/flip/EXIF), `watermark` (texto ou imagem), `border`, `adjust` (brilho/contraste/saturação/nitidez), `filter` (blur/sharpen/autocontrast/equalizar/cinza), `favicon` (.ico multires), `contact_sheet` (N→1), `remove_bg` (rembg/ONNX, CPU), `describe` (Ollama vision → .txt).
- **Core** (`src/core/image/`): `transform.py` com 9 funções puras; `background.py` — `remove_background()` via rembg (imports lazy, extra `[ai-image]`); `describe.py` — `describe_image()` + `save_description()` via LangChain + Ollama.
- **GUI** (`src/gui/modules/image/form_view.py` + `blocks/`): `ImageArgs` com 33 campos. Formulário quebrado em 12 blocos — cada um é `build_X_block(page) → (ft.Column, XRefs)` onde `XRefs` é NamedTuple com `get_*` callables. Card `remove_bg` desabilitado com tooltip quando extra não instalado (`_UNAVAILABLE`).
- **Visor Before/After**: `_single_pane` (placeholder ou input thumb) e `_before_after_row` (Antes/Depois em `ft.Row`) num `ft.Row` pai, toggle por `visible=`. `_last_input_thumb` preserva o thumb do input para o split após `image_op_done`.
- **Formatos**: JPG, PNG, WebP, AVIF, TIFF, BMP, GIF, ICO. `LOSSY_FMTS = {"jpg", "jpeg", "webp"}`.
- **`pipeline_log.py`**: fonte única de mensagens do módulo — constantes `OP_VERBS`/`OP_LABELS`, builders `fmt_*` por operação (metadados PIL, detalhes de cada op, rembg, describe), `resolve_messages()` e `resolve_stage_label()` usados por `view.py`. `worker.py` emite metadados lazy (`_try_read_meta` lê cabeçalho sem decodificar pixels) e detalhe específico antes de cada chamada ao core.
- **Saída**: downloads → `output/image/source/`; processadas → `output/image/processed/`.

## Splash + Home Screen + spinner (branding)

Fluxo completo de entrada: `show_splash` → `show_home` → `build_app(initial_module)`.

- **Splash** (`src/gui/splash.py`): fade-in + scale + uma volta do cata-vento, então chama `show_home`. Cores via `Color.dark.*` — sem literais hardcoded.
- **Home Screen** (`src/gui/home.py`): tela intermediária com 4 cards de módulo (grid 2×2) sobre um fundo com o símbolo do moinho girando lentamente (opacity 0.16, 20s/volta). Ao clicar num card: fade-out 350ms EASE_IN → `build_app(initial_module=id)` com fade-in 500ms EASE_OUT. Tema salvo é aplicado em `show_home` (antes de `build_app`) para que `_palette()` retorne as cores corretas desde o primeiro frame. Cada card é um `GestureDetector` + `Container` (sem `ink=True`, sem `on_click` — quirk Flet 0.85); hover muta `bgcolor` e `border` com animação `Motion.fast`.
- **AppBar** (`src/gui/app.py`): wordmark "mill.tools" com spans (`ft.Colors.ON_SURFACE` / `pal_title.primary`). Botões "Home" e "Splash" em `actions` — chamam `_go_home` / `_go_splash` (bloqueados se pipeline rodando). `page.pubsub.unsubscribe_all()` no início de `build_app` evita acúmulo de subscribers em re-entradas. `page.appbar = None` antes de navegar para splash/home.
- **Spinner**: `ft.Image` do cata-vento, giro encadeado via `on_animation_end` (curva LINEAR). Para na vertical ao terminar.
- **Assets** (`src/gui/assets.py`): `b64(name)` retorna bytes; `WINDOW_ICON` → `assets/icons/mill.ico`.

## Comandos

```bash
uv run gui.py                                         # GUI desktop

# Transcrição (legado + subcomando explícito)
uv run main.py <YOUTUBE_URL>                          # básico
uv run main.py transcribe <URL> --format --analyze    # pipeline completo
uv run main.py transcribe <URL> --am gemini-2.5-flash # análise via Gemini
uv run -m src output/transcriptions/text/<file>.txt   # análise standalone

# Áudio
uv run main.py audio <URL_OR_FILE> [--fmt mp3] [--quality 320] [--denoise] [--normalize]

# Vídeo (sub-subcomandos: download convert trim compress resize extract-audio thumbnail)
uv run main.py video download <URL> [--quality 1080] [--container mp4]
uv run main.py video convert <FILE> [--codec h264]
uv run main.py video trim <FILE> --start 0:30 --end 1:00

# Imagens (sub-subcomandos: convert resize crop rotate watermark border adjust filter
#          favicon contact-sheet remove-bg describe)
uv run main.py image convert <FILE> [--fmt webp] [--quality 85]
uv run main.py image resize <FILE> --mode contain --width 1920
```

> Referência completa de flags CLI → skill `cli` (`.claude/skills/cli/SKILL.md`)

## Convenções de código

- **Idioma do código**: docstrings, mensagens de log, comentários e strings internas devem ser em **inglês**. Português é reservado exclusivamente para labels e textos visíveis na GUI (botões, labels, tooltips, seções do formulário). O projeto tem inconsistências históricas nesse ponto — ao tocar em qualquer arquivo, corrigir docstrings/logs em português para inglês na mesma passagem.
- Docstrings em todas as funções e módulos
- Logging via handler dedicado — nunca usar `print()` para logs
- Core (`src/core/`) é puro: sem dependência de Flet, reutilizável por CLI e GUI
- Linter: ruff · Testes: pytest (ver seção abaixo)
- `subprocess` — sempre **modo binário** (`Popen`/`run` sem `text=True`); decodificar manualmente com `.decode('utf-8', errors='replace')`. Em Windows, `text=True` herda cp1252 do sistema e causa `UnicodeDecodeError` em saídas UTF-8 de ffmpeg/ffprobe. Aplica-se a todos os módulos em `src/core/`.

## Testes

- **Framework**: pytest 9+ com pytest-mock e pytest-cov (dependências dev)
- **Marcadores**: `unit` — Python puro, sem ffmpeg/rede/GPU · `integration` — requer ffmpeg no PATH
- **Cobertura**: `src/` todo, excluindo `src/gui/` (Flet não é testável headless)
- **Regra**: rodar `uv run pytest -m unit` antes de qualquer commit
- **CI sem ffmpeg**: testes `integration` são pulados automaticamente via `pytest_collection_modifyitems`

```bash
uv run pytest -m unit -v                                                   # unitários apenas (rápido)
uv run pytest -m integration -v                                            # integração apenas (requer ffmpeg)
uv run pytest -v                                                           # suíte completa (209 testes)
uv run pytest --cov=src --cov-report=term-missing                         # cobertura completa
uv run pytest tests/caminho/test_arquivo.py -v                            # arquivo específico
uv run pytest -k "sanitize" -v                                            # filtrar por nome
```

Estrutura espelha `src/`: `tests/core/audio/`, `tests/core/image/`, `tests/core/video/`, `tests/cli/`, `tests/gui/`. Fixtures em `tests/conftest.py`:

- **Function-scoped**: `jpg_image`, `png_image`, `out_dir`
- **Session-scoped**: `sample_wav`, `sample_mp3`, `sample_mp4`, `sample_wav_stereo`, `session_jpg`

Novos arquivos de teste (pós-refatoração): `tests/core/test_ffmpeg.py` (8 unit, 100% cobertura), `tests/test_llm_utils.py` (7 unit, 100%), `tests/cli/test_audio_cli.py` (5 unit), `tests/cli/test_video_cli.py` (10 unit), `tests/cli/test_image_cli.py` (15 unit).

Cobertura dos módulos `src/core/`: `normalizer.py` 100%, `info.py` (áudio) 100%, `ffmpeg.py` 100%, `llm_utils.py` 100%, `transform.py` 94%, `info.py` (imagem) 94%, `info.py` (vídeo) 93%, `converter.py` (áudio) 91%, `denoiser.py` 79%, `converter.py` (imagem) 79%.

> Guia completo para adicionar/revisar testes → skill `testing` (`.claude/skills/testing/SKILL.md`)

## Dependências externas (PATH)

- `yt-dlp` e `ffmpeg`/`ffprobe` — verificados em runtime por `check_dependencies()`

## LLM pipeline (Formatter / Analyzer / Prompter)

- **Chunking compartilhado** (`src/llm_utils.py`): `split_text(text, *, chunk_size, chunk_overlap, model_name, bypass_long_context, separators)`. Formatter usa separadores orientados a frases `[". ", "? ", "! ", ...]`; analyzer/prompter usam separadores padrão `["\n\n", "\n", ". ", ...]`. Bypass Gemini (1M tokens) ativado por `bypass_long_context=True` em analyzer e prompter.
- **Formatter** (`src/formatter.py`): 4500 chars/150 overlap. Modelo padrão: `phi4mini-custom`.
- **Analyzer** (`src/analyzer.py`): 4500 chars/300 overlap, merge parcial. 10 campos, tradução automática PT-BR. Modelo padrão: `qwen7b-custom`. Temperaturas 0.4 (análise) / 0.0 (tradução).
- **Prompter** (`src/prompter.py`): 4500 chars/200 overlap, ~40% de compressão. Remove CTAs/patrocinadores. Modelo padrão: `qwen7b-custom`.

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

- **EventBus** (`src/gui/events.py`): publica `PipelineEvent(type, stage, payload, module_id)` via `page.pubsub.send_all()` (thread-safe). Worker em thread daemon; UI atualiza na thread principal.
- **LogEventHandler**: captura `logging.INFO` e encaminha como eventos `log`. `_SUPPRESSED_PREFIXES` filtra duplicados. Recebe `module_id`.
- **`pipeline_log.py` (por módulo)**: padrão de vocabulário centralizado — `worker.py` importa `fmt_*` para `emit("log", ...)`, `view.py`/`progress_view.py` importa `resolve_messages()`/`resolve_stage_label()`. Separa "o que emitir" de "como exibir". Implementado em todos os módulos: `audio/`, `image/`, `video/`, `transcription/`. `progress_view._resolve_messages` e `_resolve_stage_label` são dispatchers genéricos: delegam para o `pipeline_log` correto por tipo de evento.
- **`extra_header` no `build_progress_view`**: parâmetro opcional `ft.Control | None` inserido entre a barra de progresso e o log. Usado pelo módulo Áudio para injetar o `AudioPlayer`.
- **Design System** (`src/gui/theme/components/`): factories, tokens de tipografia, cursores e help system → skill `design-system` (`.claude/skills/design-system/SKILL.md`).

### Flet 0.85 — quirks críticos

> Lista completa → skill `design-system` (`.claude/skills/design-system/SKILL.md`)

| Armadilha | Correto |
|---|---|
| `ft.Audio` | **não existe** — usar `sounddevice` + ffmpeg (`audio_player.py`) |
| `ft.ImageFit` | usar `ft.BoxFit` |
| `ft.Tabs`/`ft.Tab` | abas manuais: `TextButton` + `visible=` |
| `ft.Colors.SURFACE_VARIANT` / `SURFACE_CONTAINER` | não existem no 0.85 — usar `ft.Colors.SURFACE` ou `Color.dark.surface_variant` |
| `surface_container_*` no `ColorScheme(...)` | kwarg inválido → `TypeError`; suportados: `surface`, `on_surface`, `on_surface_variant`, `outline`, `outline_variant` |
| trocar `Container.content` em runtime | reatribuir árvore quebra o patcher → toggle `visible` num `ft.Stack` |
| `page.update()` em cascata | causa `IndexError` no `object_patch` — um update por evento |
| `ink=True` em Container clicável | absorve eventos de ponteiro, anula cursor do `GestureDetector` externo — nunca usar; colocar handler em `GestureDetector.on_tap` |
| `ft.Slider` programático | setar `.value` + `update()` **não** dispara `on_change` no Python; usar `on_change_end` para seek |
| `control.page` antes do mount | lança `RuntimeError` — proteger com `try/except RuntimeError` |
| FilePicker | `page.services.append(picker)` + `await picker.pick_files(...)` |
| `Container(box_shadow=...)` | usar `Container(shadow=ft.BoxShadow(...))` — sem prefixo `box_` |
| `ft.NavigationRailDestination` cursor | sem `mouse_cursor` — envolver o `NavigationRail` em `GestureDetector`|

### Eventos do pipeline

`PipelineEvent(type, stage, payload, module_id)`. `module_id` ∈ {`"transcription"`, `"audio"`, `"image"`, `"video"`, `""` (legado)}. O `ProgressPanel` ignora eventos cujo `module_id` ≠ `owner_id`.

**Genéricos (todos os módulos):**

| Evento | Payload | Efeito na UI |
|---|---|---|
| `progress_start` | — | barra indeterminada + inicia spinner |
| `progress_update` | `current`, `total` (0–1) | barra determinada |
| `queue_progress` | `current_item`, `total_items`, `item_name` | label "Item 2/5 — arquivo.mp3" |
| `task_done` | `output_path(s)` | barra 1.0, para spinner, habilita Resultados |
| `task_error` | `message` | log de erro, para spinner |
| `log` | `message`, `level`, `mutable: bool` | passthrough colorido; `mutable=True` atualiza a última linha em vez de criar nova (para progresso contínuo, ex.: download yt-dlp) |

**Áudio (stage="audio"):** `audio_op_start` (`operation`, `item_name`, `item_idx`, `total`), `audio_op_done` (`output_path`, `elapsed`, `item_idx`, `total`, `src_size_bytes`, `out_size_bytes`). `operation` ∈ {`download`, `convert`, `extract`, `denoise`, `normalize`}.

**Vídeo (stage="video"):** `video_op_start` (`operation`, `item_name`, `item_idx`, `total`), `video_op_done` (`output_path`, `elapsed`, `item_idx`, `total`, `src_size_bytes`, `out_size_bytes`), `video_op_error` (`item_name`, `message`). `operation` ∈ {`download`, `convert`, `trim`, `compress`, `resize`, `extract_audio`, `thumbnail`}. `module_id = "video"`.

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

## Hardware de desenvolvimento

- Dell Inspiron 7580 — i5-8265U, 16GB RAM
- NVIDIA GeForce MX150 (2GB VRAM), CUDA 12.6
- Compute type: `int8_float32` (arquitetura Pascal)
- Thermal throttling gerenciado pelo EC Dell (~63-65°C) — comportamento esperado
- OS: Windows 10 Home

## Roadmap

- **PR3.1-B** — IA de áudio com torch (extra `[ai-audio]`): DeepFilterNet (denoise neural, CPU); Demucs (separação de stems) a avaliar.
- **Futuro** — melhorias no Módulo Imagens (batch rename, redimensionamento guiado); IA de imagens (upscale).
- **Fora de escopo (definitivo)** — arrastar arquivos do SO (não nativo no Flet).
