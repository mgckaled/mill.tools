# mill.tools

Multiferramenta pessoal extensível para processamento de áudio, vídeo, imagens, documentos e transcrição, com GUI desktop (Flet) e CLI. O módulo de Transcrição usa faster-whisper com aceleração GPU — 100% local. A GUI é organizada em **módulos** acessíveis por uma sidebar (NavigationRail).

## Stack

- **Python 3.13** gerenciado com `uv`
- **faster-whisper** + **ctranslate2** — transcrição via Whisper (sem PyTorch, por escolha)
- **yt-dlp** — download de áudio/vídeo e metadados
- **ffmpeg** — conversão/extração de áudio e normalização loudnorm (EBU R128)
- **noisereduce>=3.0** + **soundfile>=0.12** — spectral gating e I/O PCM (pós-processamento de áudio, CPU-only, sem torch)
- **sounddevice>=0.4** — reprodução de áudio PCM via PortAudio (CPU-only, sem torch); usado pelo reprodutor embutido na GUI
- **Pillow 12.2+** — processamento de imagens (AVIF nativo, EXIF transpose, conversão multi-formato)
- **pymupdf>=1.24** — engine PDF: merge, split, compress, rotate, watermark, stamp, encrypt, rasterização e extração de texto
- **qrcode>=7.4** — geração de QR codes (PNG/JPG)
- **rembg[cpu]** + **onnxruntime** (extra `[ai-image]`) — remoção de fundo CPU/ONNX
- **LangChain** + **Ollama** (local) / **Google Gemini** (nuvem) — formatação, análise, condensação e descrição de imagens (vision); **RAG local** sobre o corpus (módulo IA) via `OllamaEmbeddings` (`nomic-embed-custom`, CPU-only, 768-dim, torch-free)
- **numpy>=1.26** — vector store do RAG (matriz cosseno em `.npz`); já presente via stack de áudio, declarado explícito
- **Flet 0.85** — GUI desktop (Flutter no Windows); constraint em `pyproject.toml`: `flet>=0.28`, versão instalada e testada: 0.85.2
- **tqdm** — barra de progresso (CLI)

> Decisão consciente: o projeto evita **PyTorch**. O pós-processamento de áudio (denoise + normalize) é CPU-only e torch-free. Qualquer IA que dependa de torch (ex.: Demucs, DeepFilterNet neural) ficará isolada num extra opcional `[ai-audio]` — o app base permanece torch-free.

## Estrutura

```
main.py                          — entry point CLI (argparse); despacha audio/video/image/document para src/cli/
gui.py                           — entry point GUI (splash → home → build_app)
src/
├── transcriber.py · formatter.py · analyzer.py · prompter.py
├── analysis/                    — perfis de análise (puro): types/prompts/report + profiles/ (Tier 1 por grupo); analyzer lê daqui
├── llm_factory.py               — roteamento gemini-* → Google, demais → Ollama
├── llm_utils.py                 — split_text(): chunking compartilhado + bypass Gemini (1M ctx)
├── utils.py                     — logging, validação, metadata, paths de output, sanitize_filename()
├── cli/
│   ├── bus.py                   — CLIEventBus: TqdmLoggingHandler + barra tqdm (sem Flet)
│   ├── transcription.py         — resolve_input(), build_output_stem() (helpers CLI)
│   ├── audio.py                 — subcomando `audio`: add_audio_parser(), run_audio_cli()
│   ├── video.py                 — subcomando `video`: 8 sub-subcomandos (download/convert/trim/…/subtitle)
│   ├── image.py                 — subcomando `image`: 12 sub-subcomandos (convert/resize/crop/…)
│   ├── document.py              — subcomando `document`: 12 sub-subcomandos (merge/split/compress/…/ocr)
│   ├── library.py               — subcomando `library`: `list` (tabela de tudo sob output/)
│   ├── ai.py                    — subcomando `ai`: index / pergunta / --batch (RAG local sobre o corpus)
│   └── recipes.py               — subcomando `recipe`: list / run "<nome>" <URL_OR_FILE> (cadeias entre módulos)
├── core/
│   ├── ffmpeg.py                — run_ffmpeg(): runner binário compartilhado com progresso pipe:1 (aceita cwd=)
│   ├── subtitles.py             — SubtitleCue + to_srt()/to_vtt()/write_subtitles() (puro)
│   ├── io_types.py              — InputItem: dataclass(kind, value) — compartilhado CLI e GUI
│   ├── ytdlp_cookies.py         — cookie_ydl_opts(): cookies-from-browser p/ TODO call site yt-dlp (Zen→firefox+perfil); puro
│   ├── audio/
│   │   ├── args.py              — AudioArgs: parâmetros do pipeline de áudio
│   │   ├── downloader.py        — yt-dlp: URL → output/audio/source/
│   │   ├── converter.py         — ffmpeg: convert_audio(), extract_audio() (usa core.ffmpeg)
│   │   ├── denoiser.py          — denoise() via noisereduce + soundfile (spectral gating, CPU)
│   │   ├── normalizer.py        — normalize_lufs() via ffmpeg loudnorm, dois passes (EBU R128)
│   │   └── info.py              — get_duration_ffprobe()
│   ├── video/
│   │   ├── args.py              — VideoArgs: parâmetros do pipeline de vídeo
│   │   ├── downloader.py        — yt-dlp: URL → output/video/source/
│   │   ├── converter.py         — ffmpeg: convert, trim, compress, resize, extract_audio, thumbnail, add_subtitles (usa core.ffmpeg)
│   │   └── info.py              — get_video_info() via ffprobe (VideoInfo dataclass)
│   ├── image/
│   │   ├── args.py              — ImageArgs: parâmetros do pipeline de imagens
│   │   ├── downloader.py        — urllib: URL → output/image/source/
│   │   ├── converter.py         — convert_image(): EXIF transpose, RGBA→RGB, quality lossy
│   │   ├── transform.py         — 9 funções de manipulação (resize/crop/rotate/watermark/border/adjust/filter/favicon/contact_sheet)
│   │   ├── background.py        — remove_background() via rembg/ONNX (imports lazy; extra [ai-image])
│   │   ├── describe.py          — describe_image() + save_description() via LangChain + Ollama vision
│   │   └── info.py              — image_info() + thumbnail_bytes()
│   ├── document/
│   │   ├── args.py              — DocumentArgs: 14 campos para todas as operações
│   │   ├── processor.py         — 7 funções pymupdf: merge, split, compress, rotate, watermark, stamp, encrypt
│   │   ├── converter.py         — pdf_to_images(), images_to_pdf(), extract_text()
│   │   ├── ocr.py               — ocr_pdf() híbrido (texto nativo + Tesseract) + is_available() (extra [ocr])
│   │   ├── qr.py                — generate_qr() via qrcode
│   │   └── info.py              — PdfInfo + get_pdf_info() + render_first_page_png() (raster 1ª página, reusado pela Biblioteca)
│   ├── library/
│   │   ├── types.py             — LibraryItem (dataclass frozen/slots) + KIND_* consts
│   │   ├── scanner.py           — scan_library(), classify_path(), filter_items(), sort_items() (puro, sobre output/)
│   │   └── thumbnails.py        — thumbnail_for(item): dispatch por kind (imagem/PDF/vídeo) → bytes|None
│   └── rag/                     — core do RAG local (puro; única rede isolada em embedder.py)
│       ├── types.py             — ChunkMeta, RetrievedChunk, AnswerResult (frozen/slots)
│       ├── embedder.py          — embed_texts() (sub-lotes de 16 + timeout 300s) / embed_query() via OllamaEmbeddings; is_available(); _check_dim
│       ├── store.py             — VectorStore: matriz numpy + meta; add/drop_source/search (cosseno)/persist/load
│       ├── indexer.py           — build_index() incremental por (path, mtime) + reconciliação; index_dir()
│       ├── retriever.py         — retrieve(query, store, embed_query_fn, k, scope) → top-k
│       ├── chat.py              — answer(): contexto numerado [n] + prompt|make_llm → AnswerResult
│       ├── templates.py         — prompt library + templates (ata/e-mail/resumo); ~/.mill-tools/prompts.json
│       ├── batch.py             — distinct_sources(), run_batch(): um prompt sobre N documentos
│       └── recipes/             — core de Receitas (puro; cadeias lineares entre módulos)
│           ├── types.py         — Recipe, RecipeStep, StepContext, StepSpec + KIND_* (kinds lógicos)
│           ├── registry.py      — STEP_REGISTRY "module.op" → StepSpec(adapter, accepts, produces, label); adaptadores finos sobre o core dos 5 módulos + ai.answer
│           ├── runner.py        — execute_recipe() (encadeia output→input; emit_terminal) + execute_recipe_batch() (lote)
│           ├── validate.py      — validate_recipe(): coerência accepts/produces + ops desconhecidas
│           ├── inputs.py        — kind_for(): resolve_input ("url"/"local") → kind lógico por extensão
│           ├── presets.py       — PRESETS: 5 receitas embutidas (showcase cross-módulo)
│           └── store.py         — load/save/delete em ~/.mill-tools/recipes.json
└── gui/
    ├── app.py                   — build_app(): NavigationRail + registry de módulos + navigate_to
    ├── splash.py                — show_splash(): cata-vento + fade → show_home
    ├── home.py                  — show_home(): 5 ferramentas (grade 3+2) + 3 hubs destacados (Biblioteca/IA/Receitas) + moinho animado → build_app(initial_module)
    ├── assets.py                — b64() (bytes p/ ft.Image), WINDOW_ICON
    ├── events.py                — EventBus, PipelineEvent (com module_id), LogEventHandler
    ├── settings.py              — persistência em ~/.mill-tools/config.json
    ├── settings_dialog.py       — diálogo global (engrenagem no AppBar): cookies do YouTube
    ├── workers.py               — pipeline de Transcrição em thread (module_id="transcription")
    ├── help_content.py          — HELP_SHORT/LONG: registro central de tooltips/modais
    ├── components/
    │   ├── input_source.py      — InputSource (URL + FilePicker, allow_multiple); InputItem → core/io_types.py
    │   ├── profile_selector.py  — seletor agrupado de perfis de análise (cards ícone+rótulo); reusado por Transcrição e Documentos
    │   └── audio_player.py      — reprodutor play/pause/seek via sounddevice + ffmpeg; AudioPlayer.load(path)
    ├── modules/
    │   ├── base.py              — dataclass Module (id, label, icon, control, on_mount/on_unmount)
    │   ├── _pipeline_runner.py  — run_queue_pipeline(): loop base compartilhado por audio/video/image/document
    │   ├── transcription/       — view.py, pipeline_log.py
    │   ├── audio/               — form_view.py, worker.py, view.py, pipeline_log.py
    │   ├── image/               — form_view.py, worker.py, view.py, pipeline_log.py, blocks/ (12 blocos)
    │   ├── video/               — form_view.py, worker.py, view.py, pipeline_log.py
    │   ├── document/            — form_view.py, worker.py, view.py, pipeline_log.py, blocks/ (12 blocos)
    │   ├── library/             — view.py (grade + filtros), cards.py (factory de card); read-only, sem worker
    │   ├── ai/                  — form_view.py (escopo/modelo/chips), worker.py (index/answer), view.py (resposta Markdown + fontes), pipeline_log.py
    │   └── recipes/             — form_view.py (lista + construtor), worker.py (execute_recipe em thread), view.py (passo-a-passo + resultados), pipeline_log.py
    ├── theme/
    │   ├── theme.py             — apply_theme(), sync_page_bgcolor()
    │   ├── tokens.py            — Color, Type, Space, Radius, Motion, Layout
    │   └── components/          — factories de botões, cards, inputs, layout, feedback, help; Cursor; sliders.py
    └── views/
        ├── form_view.py         — formulário de Transcrição → FormPanel
        ├── progress_view.py     — ProgressPanel (logs/barra/spinner), filtro por owner_id; dispatcha para pipeline_log de cada módulo
        ├── result_view.py       — resultados em abas (Transcrição/Análise/Digest); ações "Abrir pasta"/"Abrir arquivo" seguem a aba ativa (tab_paths)
        └── file_viewer.py       — visor in-app (modal) de `.md`/`.txt` via `page.show_dialog`; usado pela Biblioteca p/ ler resultados já processados sem reprocessar
```

## Sistema de módulos (GUI)

A GUI é dividida em módulos. As 5 **ferramentas de processamento** — **Áudio**, **Vídeo**, **Imagens**, **Transcrição**, **Documentos** — ficam numa **NavigationRail** à esquerda (ordem: Áudio → Vídeo → Imagens → Transcrição → Documentos). **Biblioteca** (6º), **IA** (7º) e **Receitas** (8º) são **hubs**: vivem **fora da rail** porque operam sobre as saídas de todos os módulos (não são ferramentas par). Seus pontos de entrada são botões "Biblioteca", "IA" e "Receitas" no **AppBar** ao lado do wordmark "mill.tools" (dourados quando ativos). A ⓘ de ajuda fica no cabeçalho interno do módulo (padrão de help por módulo), não no AppBar. Os três continuam em `MODULES` (e no `ft.Stack`), então `navigate_to` funciona normalmente; `_RAIL_MODULES` exclui os três `_HUB_IDS` (`library`, `ai`, `recipes`).

A entrada no app é mediada pela **Home Screen** (`src/gui/home.py`): duas zonas rotuladas — **5 ferramentas** (cards verticais, grade **3+2**) e **3 hubs** (Biblioteca/IA/Receitas, cards **horizontais mais largos** com borda dourada e selo "HUB"). O CTA "Abrir módulo" não se repete por card: há uma **dica única** no canto superior esquerdo ("Selecione um módulo para começar") — posicionada via `top`/`left` no `Stack` (nunca `expand=True`, que cobriria a tela e engoliria os cliques). Ao clicar num card, `on_complete(module_id)` chama `build_app(initial_module=mid)`.

- **Registry** (`src/gui/app.py`): `MODULES: list[Module]` é a fonte única. Adicionar um módulo = uma entrada na lista.
- **Module** (`src/gui/modules/base.py`): dataclass com `id`, `label`, `icon`, `selected_icon`, `control`, `on_mount(payload)`, `on_unmount()`. O `control` é construído uma vez; trocar de aba **não** destrói o estado.
- **navigate_to(module_id, payload)**: alterna **visibilidade** dos controles num `ft.Stack` (não reatribui `content` — evita o `object_patch` IndexError do Flet 0.85). **Bloqueia a troca** enquanto `pipeline_running[0]` for `True`.
- **Bridge Áudio/Vídeo/Biblioteca → Transcrição**: `navigate_to("transcription", {"file": path})` — o `on_mount` chama `form_panel.fill_from_path(path)`, que adiciona o arquivo como item único no `InputSource`.
- **Bridge Vídeo → Transcrição/Áudio**: resultado de `extract_audio` exibe botões "Transcrever" e "Processar no Áudio".
- **Bridge Biblioteca → IA** ("Conversar sobre"): `navigate_to("ai", {"file": path})` — o `on_mount` chama `form.bind_document(path)`, fixando o escopo "Este documento".
- **Escopo de eventos por módulo**: cada `ProgressPanel` recebe um `owner_id` e ignora eventos cujo `module_id` não casa. O módulo IA é auto-contido (assina seus próprios eventos `module_id="ai"`), não usa `ProgressPanel`.

## Módulo Transcrição

Transcrição (Whisper) + pipeline de IA (Formatação / Análise / Prompt-ready). Usa o `InputSource` padrão dos demais módulos (URL + seletor de arquivo, **entrada única**), aceitando **URL** (YouTube/SoundCloud…), **áudio/vídeo local** e **texto** (`.txt`/`.md`).

- **Formulário adaptativo** (`src/gui/views/form_view.py`): `_on_items_change` detecta o tipo da entrada. Texto → esconde a seção de transcrição (modelo Whisper, idioma, beam, legendas) atrás de um aviso "texto detectado" e mantém só Formatação/Análise/Prompt-ready; mídia/URL → mostra tudo. `FormPanel.fill_from_path(path)` é o ponto de entrada das bridges.
- **Worker** (`src/gui/workers.py`): `run_pipeline` ramifica a entrada. **Texto** → copia o arquivo para `output/transcriptions/text/` (nunca edita o original, pois o `formatter` reescreve o `input_path` no lugar), pula download+Whisper e roda só as etapas de IA; **guarda**: exige ao menos uma análise para arquivo de texto. **Áudio/vídeo local** → transcreve (faster-whisper decodifica vídeo via PyAV, sem extração separada). **URL** → metadata + download + transcrição. As etapas `format/analyze/prompt` são compartilhadas pelos dois caminhos.
- **Modelos**: ver "Modelos disponíveis na GUI". As 3 funções (`formatter`/`analyzer`/`prompter`) leem de um `input_path` e toleram `.txt` sem header.

## Módulo Áudio

- **Operações principais** (auto-detectadas): URL → download; vídeo local → extração; áudio local → conversão.
- **Entrada**: URL + FilePicker via `page.services`, `allow_multiple=True`. Arrastar do SO fora de escopo.
- **Formato/qualidade**: `best`/mp3/m4a/wav/ogg/opus + bitrate (320…64 kb/s). `best` sem reencode.
- **Capa + metadados**: embutidos por padrão; switch desligável. Fallback gracioso em ogg/opus.
- **Fila sequencial**: um item por vez. Progresso via `queue_progress` + `progress_update`.
- **Saída**: downloads → `output/audio/source/`; convertidos/pós-processados → `output/audio/processed/`.
- **Reprodutor embutido** (`src/gui/components/audio_player.py`): aparece acima do log após o pipeline concluir. Reproduz via sounddevice. UI: play/pause, skip ±10s, loop, volume, seek por clique no waveform. `AudioPlayer.load(path)` chamado automaticamente em `_on_done`.
- **Waveform — arquitetura de duas threads**: `_load()` lança duas threads paralelas — (1) decode rápido a **500 Hz mono** (`_decode_waveform_fast`) para calcular e exibir o waveform rapidamente; (2) decode completo 44100 Hz estéreo (`_decode_via_ffmpeg`) para playback. `_load_generation` (contador inteiro) descarta resultados de cargas anteriores. `gapless_playback=True` no `ft.Image` elimina flickering nas trocas de frame durante o polling do cursor.
- **Downloader — quirks Windows (áudio)**: `FFmpegExtractAudio` cria `.temp.<ext>` **no mesmo diretório do arquivo de entrada** (hardcoded no yt-dlp) — `paths={"temp": ...}` **não resolve** esse caso. Solução: executar todo o download e pós-processamento em `tempfile.mkdtemp()` (privado, fora do escopo do Defender) e mover o arquivo final para `out_dir` via `shutil.move`. Ver `src/core/audio/downloader.py`.

### Pós-processamento

Ativado por switches no formulário; as duas operações são encadeáveis após a operação principal.

| Operação | Módulo core | Detalhe técnico |
|---|---|---|
| **Reduzir ruído** | `denoiser.py` | Spectral gating via noisereduce (CPU-only). Decodifica via ffmpeg, processa canal por canal, salva WAV preservando subtype PCM original (`sf.info` + `subtype=meta.subtype`). |
| **Normalizar volume** | `normalizer.py` | EBU R128 via ffmpeg loudnorm em 2 passes: passe 1 mede IL/LRA/TP; passe 2 aplica ganho linear (`linear=true`). Alvo configurável −23..−6 LUFS. True Peak máx. −1 dBFS. Retorna `(path, stats_dict)`. |

- **`pipeline_log.py`**: vocabulário centralizado para 5 operações (download, convert, extract, denoise, normalize).
- **`AudioArgs`**: `denoise: bool`, `normalize: bool`, `normalize_target_lufs: float = -14.0`. Estado persistido em `~/.mill-tools/config.json`.

## Módulo Vídeo

Download, conversão e processamento via yt-dlp e ffmpeg. Encoding 100% CPU — sem NVENC (decisão definitiva).

- **Operações** (8, selecionadas via card grid 3 colunas): `download` (yt-dlp), `convert` (codec/container), `trim` (corte por tempo, copy ou reenc), `compress` (H.264/CRF 18–28), `resize` (scale ffmpeg, aspect ratio preservado), `extract_audio` (bridge para `core/audio/converter.py`), `thumbnail` (frame → jpg/png), `subtitle` (embutir `.srt`/`.vtt` via mux soft ou queimar via burn-in hard).
- **Core** (`src/core/video/`): `info.py` — `VideoInfo` + `get_video_info()` via ffprobe; `downloader.py` — `download_video()` via yt-dlp com hook de progresso; `converter.py` — 7 funções ffmpeg delegando para `src.core.ffmpeg.run_ffmpeg`.
- **GUI** (`src/gui/modules/video/form_view.py`): `VideoArgs` com 17 campos. Detecção automática URL → operação forçada para `download` (seletor desabilitado). 7 blocos condicionais com `visible=`/`animate_opacity`.
- **`pipeline_log.py`**: 8 operações (download, convert, trim, compress, resize, extract_audio, thumbnail, subtitle).
- **Legenda no vídeo** (`add_subtitles`): modo `soft` (mux) usa `-c copy -c:s mov_text` (sem reencode); modo `hard` (burn-in) usa `-vf subtitles=…` + libx264 (reencoda, CPU). Saída `<stem>_subbed.mp4` em `output/video/processed/`.
- **Saída**: downloads → `output/video/source/`; processados → `output/video/processed/`.
- **Bridge extract_audio**: resultado de áudio exibe botões "Transcrever" e "Processar no Áudio" no painel de resultados.
- **Downloader — quirks Windows**: **Nunca usar `FFmpegVideoConvertor`** em nenhum formato (MP4, WebM ou outro) — o post-processor cria `.temp.<ext>` no diretório de saída e o Windows Defender bloqueia o rename com `[WinError 32]`. Usar apenas `merge_output_format` para garantir o container; ele opera sobre arquivos temporários em `%TEMP%`. Opções obrigatórias: `nopart=True`, `overwrites=True`, `paths={"temp": tempfile.gettempdir()}`. Solução definitiva: adicionar a pasta `output/` às exclusões do Windows Defender.
- **Progresso yt-dlp**: campos `_percent_str`, `_speed_str`, `_eta_str` contêm códigos ANSI — strip obrigatório antes de exibir: `re.sub(r'\x1b\[[0-9;]*m', '', s).strip()`.
- **Legenda burn-in — quirk Windows**: o filtro `subtitles` do ffmpeg interpreta `:` como separador de argumentos, então o `:` do drive (`C:`) quebra o parser. Solução: rodar o ffmpeg com `cwd` na pasta da legenda e referenciá-la por **basename** (`subtitle_path.name`). `run_ffmpeg` aceita `cwd=` para isso. Mux soft (`-c copy -c:s mov_text`) não usa filtro, então não precisa de `cwd`.

## Módulo Imagens

Conversão, manipulação e operações de IA com visor Before/After integrado.

- **Operações** (12, selecionadas via card grid 3 colunas): `convert`, `resize` (caber/exato/escala%), `crop` (manual/proporção/auto-trim), `rotate` (ângulo/flip/EXIF), `watermark` (texto ou imagem), `border`, `adjust` (brilho/contraste/saturação/nitidez), `filter` (blur/sharpen/autocontrast/equalizar/cinza), `favicon` (.ico multires), `contact_sheet` (N→1), `remove_bg` (rembg/ONNX, CPU), `describe` (Ollama vision → .txt).
- **Core** (`src/core/image/`): `transform.py` com 9 funções puras; `background.py` — `remove_background()` via rembg (imports lazy, extra `[ai-image]`); `describe.py` — `describe_image()` + `save_description()` via LangChain + Ollama.
- **GUI** (`src/gui/modules/image/form_view.py` + `blocks/`): `ImageArgs` com 33 campos. Formulário quebrado em 12 blocos — cada um é `build_X_block(page) → (ft.Column, XRefs)` onde `XRefs` é NamedTuple com `get_*` callables. Card `remove_bg` desabilitado com tooltip quando extra não instalado (`_UNAVAILABLE`).
- **Visor Before/After**: `_single_pane` (placeholder ou input thumb) e `_before_after_row` (Antes/Depois em `ft.Row`) num `ft.Row` pai, toggle por `visible=`. `_last_input_thumb` preserva o thumb do input para o split após `image_op_done`.
- **Formatos**: JPG, PNG, WebP, AVIF, TIFF, BMP, GIF, ICO. `LOSSY_FMTS = {"jpg", "jpeg", "webp"}`.
- **`pipeline_log.py`**: constantes `OP_VERBS`/`OP_LABELS`, builders `fmt_*` por operação, `resolve_messages()`/`resolve_stage_label()` usados por `view.py`. `worker.py` emite metadados lazy (`_try_read_meta` lê cabeçalho sem decodificar pixels).
- **Saída**: downloads → `output/image/source/`; processadas → `output/image/processed/`.

## Módulo Documentos

Manipulação de PDF e geração de QR code via pymupdf. Sem dependência de ffmpeg.

- **Operações GUI** (13, selecionadas via card grid 3 colunas): `merge` (N PDFs → 1), `split` (por intervalo de páginas), `compress` (reimprimir imagens embutidas), `rotate` (ângulo configurável por página), `watermark` (texto diagonal semitransparente), `stamp` (carimbo em destaque — PAGO/RASCUNHO/CONFIDENCIAL), `encrypt` (AES-256), `extract` (texto → .txt), `ocr` (PDF escaneado → texto via Tesseract), `pdf_to_images` (rasterizar páginas; DPI 72–300), `images_to_pdf` (N imagens → PDF), `analyze` (conteúdo via LLM — PDF passa por extract_text; `.txt`/`.md` é analisado direto), `qr` (gerar QR code PNG/JPG).
- **Operações CLI** (12 sub-subcomandos): os mesmos exceto `analyze` (só-GUI). Inclui `ocr` (determinístico, sem LLM).
- **Core** (`src/core/document/`):
  - `processor.py` — 7 funções pymupdf: merge_pdfs, split_pdf, compress_pdf, rotate_pdf, watermark_pdf, stamp_pdf, encrypt_pdf.
  - `converter.py` — pdf_to_images() (rasterização), images_to_pdf(), extract_text().
  - `ocr.py` — `ocr_pdf()` híbrido (texto nativo por página; OCR via pytesseract só nas páginas sem camada de texto) + `is_available()` (resolve o binário no PATH ou em `C:\Program Files\Tesseract-OCR`). Extra `[ocr]`.
  - `qr.py` — generate_qr(data, output_dir, size, fmt).
  - `info.py` — `PdfInfo` (page_count, file_size_bytes, title, author, has_text, first_page_thumb) + `get_pdf_info()`.
  - `args.py` — `DocumentArgs` com 16 campos (operação, pages, image_quality, angle, watermark, stamp, password, dpi, qr_data, analyze_model, ocr_lang, ocr_dpi…).
- **GUI** (`src/gui/modules/document/`): mesmo padrão do módulo Imagens — form_view.py + worker.py + view.py + pipeline_log.py + blocks/ (13 blocos, cada um `build_X_block(page) → (ft.Column, XRefs)`). Card `ocr` habilita-se quando o Tesseract está disponível; do contrário desabilita com aviso — padrão `_UNAVAILABLE` do módulo Imagens.
- **`pipeline_log.py`**: 13 operações com `OP_VERBS`/`OP_LABELS`, `fmt_op_start`/`fmt_op_done` genéricos + builders específicos por op, `resolve_messages()`/`resolve_stage_label()`.
- **Saída**: arquivos processados → `output/document/processed/`.
- **OCR (PR5.1)** ✅: `src/core/document/ocr.py` via pytesseract (extra `[ocr]`, Tesseract no PATH ou local padrão do Windows). Fluxo híbrido: usa a camada de texto nativa quando existe; só rasteriza + OCR nas páginas escaneadas (300 DPI é o piso recomendado). Fecha o loop **PDF escaneado → OCR → texto → `analyze` (LLM)**.

## Módulo Biblioteca (PR6)

Hub navegável de tudo que os módulos já produziram sob `output/`. **Read-only** — sem `worker.py`/`pipeline_log.py`; as ações disparam navegação ou abertura de arquivo, não pipelines. Zero dependência nova (stdlib + Flet + geradores já presentes); torch-free.

- **Core puro** (`src/core/library/`): `types.py` — `LibraryItem` (`frozen=True, slots=True`) + `KIND_*`/`ALL_KINDS`; `scanner.py` — `_library_roots()` mapeia cada dir de saída → `(kind, category)`, `classify_path()`, `scan_library()` (varredura rasa, só arquivos, mtime-desc, pula ocultos `.gitkeep`/`.DS_Store` e arquivos ilegíveis), `filter_items()` (kind/query/since), `sort_items()` (modified/name/size); `thumbnails.py` — `thumbnail_for(item)` despacha por kind (imagem→`thumbnail_bytes`, PDF→`render_first_page_png`, vídeo→frame único via ffmpeg `pipe:1`; áudio/transcrição→`None` ícone).
- **GUI** (`src/gui/modules/library/`): `view.py` — `build_library_module(page, bus, cancel_event, pipeline_running, nav)`; tela cheia (sem split form|painel). Cabeçalho com título + ⓘ (`help_icon_for("library")`) + **toggle de modo de exibição** (dois `ft.IconButton`: grade|lista, dourado no ativo). Filtro por tipo via `segmented_selector` (6 chips); toolbar com busca por nome (`ft.TextField` + debounce via `page.run_task`), **categoria** (Todas/Origem/Processado — "Processado" agrupa processed+text+analysis+digest), ordenação e período via `ft.Dropdown` (evento `on_select`, não `on_change`). **Dois modos** alternados por visibilidade num `ft.Stack`: **grade** (`ft.GridView(max_extent=220, child_aspect_ratio=0.8, cache_extent=400)`, cards com thumbnail) e **lista** (cabeçalho de colunas fixo sobre um `ft.ListView`; linhas compactas só com ícone de tipo). `cards.py` — `build_item_card(...) → ItemCard(control, set_thumbnail)` (grade); `build_list_header()` + `build_item_row(item, page, on_open, build_actions)` (lista: colunas Nome/Categoria/Tamanho/Data/Ações com larguras compartilhadas; área de células clicável via `GestureDetector`, ações fora dele para não engolir os taps; texto truncado expõe o valor completo via `tooltip`; hover muta `bgcolor`).
- **Cache + threads**: o scan fica em `_all_items`; filtro/busca/ordenação operam em memória (teclas não tocam o disco). Thumbnails geram numa **única thread daemon** com contador de geração (descarta scans antigos) + cache `(path, mtime)`; cada card recebe `set_thumbnail()` com **update escopado** (nunca `page.update()` — issue #6270). Paginação: `_PAGE_SIZE=120` + botão "Carregar mais".
- **Persistência**: `last_library_filter`, `last_library_category`, `last_library_sort`, `last_library_view` (grid|list) em `~/.mill-tools/config.json`.
- **Atualização**: `on_mount` re-escaneia ao entrar (pega saídas novas e deleções externas); assina o EventBus e re-escaneia ao vivo se a Biblioteca estiver visível quando um `task_done` chega.
- **Ações por item**: **Abrir** — texto (`.txt`/`.md`) abre no **visor in-app** (`views/file_viewer.py`, modal com Markdown renderizado; lê resultado já processado sem reprocessar), demais tipos via `os.startfile` (toast se falhar); **Abrir pasta** (`explorer /select,`); e **bridges** via `nav[0](module_id, {"file": path})` — áudio/vídeo → Transcrição + Áudio; imagem → Imagens; PDF → Documentos; texto → "Analisar na Transcrição". Pré-requisito: `on_mount({"file": path})` + `fill_from_path` padronizados em **todos** os módulos-alvo (Áudio/Vídeo já tinham; Imagens/Documentos ganharam no PR6.4).
- **CLI**: `uv run main.py library list [--kind] [--since 7d] [--sort]` (`src/cli/library.py`) reaproveita o core e imprime uma tabela. Sem pipeline, sem `CLIEventBus`; reconfigura stdout p/ UTF-8 (nomes com `｜` quebram o console cp1252).
- **AppBar hub** (`src/gui/app.py`): fora da rail. `_RAIL_MODULES` = `MODULES` sem os `_HUB_IDS` (`library`, `ai`, `recipes`); `_rail_index(module_id)` mapeia o slot da rail (`None` para os hubs → rail deselecionada). `library_btn`/`ai_btn`/`recipes_btn` são TextButtons (dourados quando ativos) no título, via `_hub_btn_style(active)` — a ⓘ de ajuda fica no módulo, não no AppBar.

## Módulo IA (PR7)

RAG local sobre o corpus da Biblioteca: indexa o texto que você já produziu, recupera os trechos relevantes para uma pergunta e responde com um LLM **citando as fontes**. **100% local** nos embeddings (Ollama); Gemini só opcional no passo de resposta. Torch-free, **sem dependência pesada nova** (só `numpy` explícito). Reaproveita `make_llm`, `split_text`, `EventBus` e `scan_library` — não cria um segundo "jeito de falar com LLM".

- **Core puro** (`src/core/rag/`): `embedder.py` é a **única rede** (isolada, injetável como `embed_fn`); o resto opera sobre callables e é unit-testável sem Ollama. `VectorStore` é uma matriz numpy `(N, D)` com busca cosseno + persistência `.npz`/`.json` em `~/.mill-tools/rag/` (serialização via `dataclasses.asdict` — slots não têm `__dict__`). `build_index()` é **incremental** por `(path, mtime)`: pula inalterados, reembeda alterados, reconcilia removidos; indexa as **kinds textuais** (`transcription`/`document` + descrições de imagem `.txt`), tira o cabeçalho de transcrição e chunka via `split_text` (1200/150). `chat.answer()` monta contexto numerado `[n]` sob prompt estrito ("responda só pelo contexto + cite; senão diga que não achou"). `templates.py` = prompt library (defaults + `~/.mill-tools/prompts.json`); `batch.py` aplica um prompt a N documentos.
- **GUI** (`src/gui/modules/ai/`): hub no AppBar, split form|painel. `form_view.py` — escopo (`segmented_selector` Tudo/Transcrições/Documentos/Imagens + chip de documento fixado pela bridge), modelo da resposta (`gemma3-4b-custom` recomendado/default → `gemma3-1b-custom` rápido/baixa-RAM → `qwen7b-custom` → `gemini-2.5-flash`, com aviso de privacidade Gemini) e **chips de prompt** (`load_templates()`) que preenchem a pergunta. `worker.py` — `run_ai_index`/`run_ai_answer` em thread daemon emitindo por `EventBus` (`module_id="ai"`); cancelamento aborta a indexação pelo `progress_cb`. `view.py` — **auto-contido** (assina seus eventos, não usa `ProgressPanel`): status do índice ("N docs · M chunks · atualizado HH:MM") com **Reindexar** e **Limpar conversa** (zera só a lista visual de turnos), barra + spinner, e sessão rolável de turnos Q&A. A resposta é `ft.Markdown` (mesma stylesheet do visor); cada fonte citada é uma **linha compacta** (`_source_item`) com badge `[n]` (amarra ao `[n]` da resposta) + caminho relativo a `output/` — clique abre no visor in-app (texto) ou no SO, ícone à direita abre a pasta. O status é calculado **fora da thread de UI** porque `embedder.is_available()` faz ping no Ollama.
- **Persistência**: `last_ai_model`, `last_ai_scope`, `last_embed_model` em `config.json`; índice em `~/.mill-tools/rag/`; prompt library em `~/.mill-tools/prompts.json`.
- **CLI** (`src/cli/ai.py`): `ai index` (re)indexa; `ai "pergunta"` responde; `--scope <path|kind>` restringe; `--model`/`--k`; `--reindex`; `--batch [--kind]` aplica a pergunta como instrução a cada documento. Reaproveita o mesmo core; embeddings sempre locais.
- **Gate de disponibilidade**: `embedder.is_available()` (langchain-ollama importável + `nomic-embed-custom` respondendo) bloqueia ambos os fluxos com a dica `embedder.SETUP_HINT` (`ollama pull nomic-embed-text && ollama create nomic-embed-custom -f ollama/Modelfile.nomic`). Modelo CPU-pinned (`num_gpu 0`) p/ não disputar a MX150 com Whisper/Flet — mesma decisão do `moondream-custom`.
- **Quirk Ollama #10176**: configs que devolvem 8192 dims em vez de 768 → `_check_dim()` emite warning.

## Módulo Receitas (PR8)

Automação: cadeias **lineares** nomeadas onde a saída de um passo alimenta a entrada do próximo, atravessando módulos (ex.: `URL → baixar áudio → transcrever → analisar`). Generaliza o `run_pipeline` hardcoded da Transcrição. **Sem dependência nova**, torch-free; reaproveita `EventBus`/`CLIEventBus`, `resolve_input`, `InputSource`, `make_llm`, `scan_library` e o core puro dos 5 módulos.

- **Core puro** (`src/core/recipes/`): `types.py` — `Recipe`/`RecipeStep`/`StepContext`/`StepSpec` + `KIND_*` (kinds lógicos que fluem entre passos). `registry.py` — `STEP_REGISTRY: "module.op" → StepSpec(adapter, accepts, produces, label)`: **adaptadores finos** que dão assinatura uniforme `adapter(inputs, params, ctx) → list[Path]` às funções de core heterogêneas (chamam o **core puro**, nunca o worker da GUI) e gravam no **dir canônico do módulo** (`src/utils`) p/ a Biblioteca classificar por kind. A camada de adaptador é a única que conhece a assinatura exata e normaliza os 3 estilos de callback (`on_event`/`progress_hook`/`progress_cb`) para `ctx.emit`. `runner.py` — `execute_recipe()` valida antes de iterar, encadeia output→input, emite a mesma anatomia de eventos do `run_queue_pipeline`, respeita cancel entre passos e aborta no 1º erro (`emit_terminal` distingue run isolado de entrada de lote); `execute_recipe_batch()` roda a receita sobre N entradas com `queue_progress`. `validate.py` — `validate_recipe()` checa coerência `accepts`/`produces` + ops desconhecidas. `inputs.py` — `kind_for()` mapeia `resolve_input` (`url`/`local`) → kind lógico por extensão. `presets.py` — `PRESETS` (5 receitas embutidas, type-coerentes por construção). `store.py` — load/save/delete em `~/.mill-tools/recipes.json`.
- **Casos sutis** (confirmados contra o código): `transcription.format` reescreve in-place e retorna `str` → adaptador devolve `[input_path]`; `transcription.transcribe` aceita áudio **e** vídeo (PyAV) e devolve `[txt, *legendas]`; `video.subtitle` é o único **multi-input** — recupera o vídeo de `ctx.initial_inputs` e a `.srt` de `ctx.outputs_by_op["transcription.transcribe"]`; `ai.answer` (PR7) reindexa, recupera com escopo no próprio arquivo e grava `AnswerResult.text` + Fontes num `.md` (exige `embedder.is_available()`).
- **GUI** (`src/gui/modules/recipes/`): hub no AppBar, split form|painel, **auto-contido** (assina `module_id="recipes"`). `form_view.py` — toggle **Rodar | Construir** (abas manuais): Rodar lista receitas (presets + salvas) selecionáveis + `InputSource` + dica "entrada esperada" + switches **lote** e **limpar intermediários**; Construir é um editor de sequência (dropdown só oferece ops compatíveis com a saída do passo anterior; reordenar por **↑/↓** — `ft.ReorderableListView` existe mas é scrollable sem `shrink_wrap`, frágil aninhado; validação ao vivo desabilita Salvar em cadeia incoerente). `worker.py` — `run_recipe_pipeline(runs, clean_intermediates)` roda `execute_recipe`/`execute_recipe_batch` em thread; 1 run → execução direta, N runs → lote; `clean_intermediates` apaga saídas de passos não-finais. `view.py` — progresso passo-a-passo, log rolável, Cancelar (entre passos) e cards de resultado (`output_card`) com bridge "Abrir na Biblioteca". `pipeline_log.py` — `fmt_*` + `resolve_status`.
- **Persistência**: `last_recipe`, `recipe_clean_intermediates` em `config.json`; receitas do usuário em `~/.mill-tools/recipes.json`.
- **CLI** (`src/cli/recipes.py`): `recipe list` (presets + salvas, com a cadeia) e `recipe run "<nome>" <URL_OR_FILE>` (`--model` sobrescreve o Whisper dos passos de transcrição). Resolve a receita, monta `initial_inputs`+`initial_kind` via `resolve_input`+`kind_for`, cria `CLIEventBus` e chama `execute_recipe` — mesmo core da GUI.

## Cookies do YouTube (anti-bot)

O YouTube bloqueia downloads de forma intermitente com um gate anti-bot ("Sign in to confirm you're not a bot"). A mitigação é passar cookies de um navegador logado via a opção `cookiesfrombrowser` do yt-dlp. Toda a lógica fica **isolada** em `src/core/ytdlp_cookies.py` (puro, sem Flet) e é **reutilizada por todos os call sites** do yt-dlp.

- **Ponto único**: `cookie_ydl_opts() -> dict` é **mesclado** (`ydl_opts.update(...)`) dentro das **3** funções core que chamam o yt-dlp — `core/audio/downloader.py` (`download_audio`), `core/video/downloader.py` (`download_video`) e `core/metadata.py` (`fetch_metadata`). Isso cobre automaticamente **Áudio, Vídeo, Transcrição, Receitas e a CLI** sem propagar parâmetro. Novos call sites só precisam mesclar o helper.
- **Zen Browser**: o yt-dlp **não conhece "zen"** (`SUPPORTED_BROWSERS` = chromium-family + firefox + safari). Zen usa o formato `cookies.sqlite` do Firefox, então o mapeamento é `("firefox", <path absoluto do perfil Zen>, None, None)` — o `_extract_firefox_cookies` aceita um caminho absoluto como raiz. O perfil default do Zen é resolvido do `profiles.ini` (preferindo `[Install*].Default` ao legado `[Profile*] Default=1`); dir do Zen por plataforma (`%APPDATA%\zen` no Windows).
- **Config** (desacoplada do GUI — o core lê direto, sem importar `gui.settings`): env `MILL_YT_COOKIES_BROWSER`/`MILL_YT_COOKIES_PROFILE` → senão `~/.mill-tools/config.json` (`yt_cookies_browser`/`yt_cookies_profile`). Default `"none"` — **opt-in**: cookies só são lidos quando o usuário escolhe um navegador (decisão consciente por ser sensível; lê a sessão logada). Opções: `none`/`auto`/`zen`/`firefox`/`chrome`/`edge`/`brave`/`chromium`/`opera`/`vivaldi`(+`safari` no macOS); `auto` auto-detecta o Zen, nada detectado → no-op seguro.
- **Robustez**: `cookie_ydl_opts()` **nunca levanta** (try/except → `{}`); só retorna cookies de perfil cujo dir existe. Falha de resolução nunca quebra o download.
- **GUI**: diálogo global de Configurações (`src/gui/settings_dialog.py`), aberto pela engrenagem no AppBar (`app.py`), com seletor de navegador + status (`detected_summary()`) + perfil avançado opcional; persiste via `settings`. Vem **desativado** por padrão (opt-in); o usuário ativa escolhendo o navegador (ex.: `auto`/`zen` resolve o perfil do Zen).
- **Limitação conhecida — PO Token / SABR** (validado em campo, jun/2026): os cookies **passam o gate anti-bot**, mas usar cookies de uma **conta logada** faz o YouTube exigir um **PO Token**; sem ele o yt-dlp recebe só *storyboards* (`sb0-3`) → **`Requested format is not available`** (afeta **todos** os vídeos, não só um). É a razão de o default ser opt-in (`none`): cookies de conta costumam **atrapalhar** o download. A armadilha: **sem** cookies o IP pode cair no gate anti-bot; **com** cookies cai no PO Token. O fix durável (gate + formatos) é um provider de PO Token (`bgutil-ytdlp-pot-provider`), **deliberadamente não implementado** (exige runtime Node/Deno — contra a leveza do projeto). Mitigações sem código: baixar **sem** cookies + retry, manter o yt-dlp atualizado, ou (se reincidir) reavaliar o PO Token. Diagnóstico: `extract_info(..., process=False)` e comparar `formats` com/sem cookies — só storyboards = PO Token exigido.

## Splash + Home Screen + spinner (branding)

Fluxo completo de entrada: `show_splash` → `show_home` → `build_app(initial_module)`.

- **Splash** (`src/gui/splash.py`): fade-in + scale + uma volta do cata-vento, então chama `show_home`. Cores via `Color.dark.*` — sem literais hardcoded.
- **Home Screen** (`src/gui/home.py`): tela intermediária com **5 ferramentas (grade 3+2) + 3 hubs destacados (Biblioteca/IA/Receitas)** sobre o símbolo do moinho girando lentamente (opacity 0.16, 20s/volta). O wordmark é alinhado ao topo (não centralizado) para ganhar espaço. Hubs são `_make_hub_card` (horizontal: chip de ícone à esquerda + conteúdo, borda dourada `Color.PRIMARY`, selo "HUB"); ferramentas são `_make_card` (vertical, sem CTA). Dica única no canto superior esquerdo, posicionada por `top`/`left` no `Stack` (não `expand` — senão cobre a tela e bloqueia cliques). Ao clicar num card: fade-out 350ms EASE_IN → `build_app(initial_module=id)` com fade-in 500ms EASE_OUT. Tema salvo é aplicado em `show_home` antes de `build_app`. **Cards crescer-no-hover:** cada card é um **`GestureDetector` único** (tap + hover) envolvendo um `Container` animado (sem `ink=True` — quirk Flet 0.85). No repouso o card é compacto (`_TOOL_COMPACT_H`/`_HUB_COMPACT_H`: ícone + título + 1 linha de `desc`); ao passar o mouse cresce até `_TOOL_EXPANDED_H`/`_HUB_EXPANDED_H` e revela o detalhe (`features`: 4 por ferramenta / 3 por hub). `clip_behavior=ANTI_ALIAS` corta o detalhe no repouso; `height`/`scale`/`bgcolor`/`border` animam com `Motion.base` (EASE_OUT) e a `opacity` do detalhe faz fade. **Crítico — hover:** usar `on_enter`/`on_exit` do **próprio `GestureDetector`**; `Container.on_hover` (ou um `GestureDetector` aninhado) **não dispara** quando coberto por outra região de mouse de mesma área. As três `Row` de cards **não fixam altura** (`vertical_alignment=START`): o card cresce com **reflow** (empurra as fileiras de baixo); como só um card é hovered por vez, o total nunca passa do footprint original e cabe sem scroll. Hubs descansam com borda dourada.
- **AppBar** (`src/gui/app.py`): título = `ft.Row([wordmark, library_btn, ai_btn, recipes_btn])` — wordmark "mill.tools" com spans + os 3 botões-hub **Biblioteca**/**IA**/**Receitas** (TextButtons dourados quando ativos, navegam para o módulo correspondente). Botões "Home"/"Splash"/tema em `actions` — chamam `_go_home`/`_go_splash` (bloqueados se pipeline rodando). `page.pubsub.unsubscribe_all()` no início de `build_app` evita acúmulo de subscribers em re-entradas. `page.appbar = None` antes de navegar para splash/home.
- **Spinner**: `ft.Image` do cata-vento, giro encadeado via `on_animation_end` (curva LINEAR). Para na vertical ao terminar.
- **Assets** (`src/gui/assets.py`): `b64(name)` retorna bytes; `WINDOW_ICON` → `assets/icons/mill.ico`.

## Comandos

```bash
uv run gui.py                                         # GUI desktop

# Transcrição (legado + subcomando explícito) — aceita URL, áudio/vídeo local ou .txt/.md
uv run main.py <YOUTUBE_URL>                          # básico
uv run main.py transcribe <URL> --format --analyze    # pipeline completo
uv run main.py transcribe video.mp4                   # vídeo local (áudio decodificado via PyAV)
uv run main.py transcribe notas.txt --analyze         # texto local → pula Whisper, só IA
uv run main.py transcribe <URL> --analyze --profile lecture  # perfil (default/lecture/interview/tutorial/scientific/administrative/literary/review/storytelling/notes)
uv run main.py transcribe <URL> --am gemini-2.5-flash # análise via Gemini
uv run -m src output/transcriptions/text/<file>.txt   # análise standalone

# Áudio
uv run main.py audio <URL_OR_FILE> [--fmt mp3] [--quality 320] [--denoise] [--normalize]

# Vídeo (sub-subcomandos: download convert trim compress resize extract-audio thumbnail subtitle)
uv run main.py video download <URL> [--quality 1080] [--container mp4]
uv run main.py video convert <FILE> [--codec h264]
uv run main.py video trim <FILE> --start 0:30 --end 1:00
uv run main.py video subtitle <FILE> --subs legenda.srt [--mode soft|hard]

# Imagens (sub-subcomandos: convert resize crop rotate watermark border adjust filter
#          favicon contact-sheet remove-bg describe)
uv run main.py image convert <FILE> [--fmt webp] [--quality 85]
uv run main.py image resize <FILE> --mode contain --width 1920

# Documentos (sub-subcomandos: merge split compress rotate watermark stamp encrypt
#             extract ocr pdf-to-images images-to-pdf qr)
uv run main.py document merge a.pdf b.pdf c.pdf
uv run main.py document split doc.pdf --pages "1-3,5"
uv run main.py document compress doc.pdf --image-quality 60
uv run main.py document watermark doc.pdf --text "CONFIDENCIAL" --opacity 0.3
uv run main.py document encrypt doc.pdf --password "senha"
uv run main.py document ocr scanned.pdf --lang por --dpi 300
uv run main.py document pdf-to-images doc.pdf --fmt jpg --dpi 150
uv run main.py document qr "https://example.com" --size 300

# Biblioteca (lista tudo sob output/ — sem GUI)
uv run main.py library list
uv run main.py library list --kind audio
uv run main.py library list --since 7d --sort size

# IA / RAG local sobre o corpus (embeddings sempre locais; Gemini só na resposta)
uv run main.py ai index                                      # (re)indexa o corpus
uv run main.py ai "o que eu disse sobre faster-whisper?"     # pergunta ao acervo
uv run main.py ai "resuma" --scope output/transcriptions/text/x.txt  # um documento
uv run main.py ai "liste as ações" --batch --kind transcription      # batch por documento
uv run main.py ai "..." --model gemini-2.5-flash --k 8

# Receitas / Automação (cadeias entre módulos; mesmo core da GUI)
uv run main.py recipe list                                   # presets + receitas salvas
uv run main.py recipe run "Limpar áudio do YouTube" <URL>    # roda por nome
uv run main.py recipe run "YouTube → transcrição completa" <URL> --model medium
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

- **Framework**: pytest 9+ com pytest-mock, pytest-cov, pytest-xdist, pytest-timeout, pytest-clarity, pytest-randomly (todos dev deps)
- **Marcadores**: `unit` — Python puro, sem ffmpeg/rede/GPU · `integration` — requer ffmpeg no PATH
- **Cobertura**: `src/` todo (com `branch = true`), excluindo `src/gui/` (Flet não é testável headless)
- **Regra**: rodar `uv run pytest -m unit` antes de qualquer commit
- **CI sem ffmpeg**: testes `integration` são pulados automaticamente via `pytest_collection_modifyitems`
- **Plugins ativos por padrão**: `pytest-randomly` (ordem aleatória — usar `--randomly-seed=NNN` para reproduzir), `pytest-timeout` (60s default — `@pytest.mark.timeout(N)` para sobrescrever), `pytest-clarity` (diffs melhores)

```bash
uv run pytest -m unit -v                                                   # unitários apenas (rápido — <5s)
uv run pytest -m integration -v                                            # integração apenas (requer ffmpeg)
uv run pytest -v                                                           # suíte completa (684 unit)
uv run pytest -n auto                                                      # paraleliza (pytest-xdist; ganho cresce com a suíte)
uv run pytest --cov=src --cov-report=term-missing                         # cobertura terminal
uv run pytest --cov=src --cov-report=html                                  # cobertura HTML em htmlcov/
uv run pytest --durations=10                                              # top 10 testes mais lentos
uv run pytest --lf                                                         # só os que falharam no último run
uv run pytest --randomly-seed=NNN                                          # reproduz ordem específica
uv run pytest tests/caminho/test_arquivo.py -v                            # arquivo específico
uv run pytest -k "sanitize" -v                                            # filtrar por nome
```

Estrutura espelha `src/`: `tests/core/audio/`, `tests/core/image/`, `tests/core/video/`, `tests/core/document/`, `tests/core/library/`, `tests/core/rag/`, `tests/core/recipes/`, `tests/cli/`, `tests/gui/`. Fixtures em `tests/conftest.py`:

- **Function-scoped**: `jpg_image`, `png_image`, `out_dir`
- **Session-scoped**: `sample_wav`, `sample_mp3`, `sample_mp4`, `sample_wav_stereo`, `session_jpg`, `sample_pdf`, `sample_pdf_with_images` (PDFs gerados via `pytest.importorskip("pymupdf")`)

Cobertura por arquivo (recortes principais):

- **CLI**: `tests/cli/test_*_cli.py` cobrem parser **e** runner (`run_*_cli`) — mocks de `src.gui.modules.<m>.worker.run_*_pipeline` validam que `Namespace → XxxArgs` está correto. `tests/cli/test_bus.py` valida o `CLIEventBus`. `test_library_cli.py` cobre parser + runner (read-only — mocka `scan_library`, sem pipeline; valida `_parse_since` e a tabela).
- **Core áudio**: `test_normalizer_parser.py`/`test_normalizer_unit.py` (unit, subprocess mockado); `test_converter.py`, `test_denoiser.py`, `test_info.py`, `test_normalizer_integration.py`, `test_pipeline_e2e.py` (integration).
- **Core imagem**: `test_transform.py`, `test_converter.py`, `test_info.py` (unit, PIL puro); `test_downloader.py` (unit, urllib mockado).
- **Core vídeo**: `test_info.py` e `test_converter.py` (ambos integration — `test_converter.py` cobre as 7 funções ffmpeg, incluindo `add_subtitles` soft/hard).
- **Core document**: `test_processor.py`, `test_converter.py`, `test_info.py`, `test_qr.py` — unit, usam pymupdf/qrcode **reais** via fixtures de sessão. `test_ocr.py` — unit (mocka pytesseract para o fluxo híbrido) + 1 integration real com Tesseract (skip se ausente). `test_info.py` cobre também `render_first_page_png` (raster real + zero-page mockado).
- **Core library**: `test_scanner.py` — unit puro (`classify_path`, `scan_library` com árvore falsa via `monkeypatch` dos roots, skip de ocultos e ilegíveis, `filter_items`/`sort_items`). `test_thumbnails.py` — unit (imagem/PDF reais → bytes; áudio/transcrição/corrompidos → None) + 1 integration de frame de vídeo. Scanner/thumbnails ≥ 98%.
- **Core RAG** (`tests/core/rag/`): tudo unit, sem Ollama — `embed_fn`/`embed_query_fn` injetados e LLM via `GenericFakeChatModel`. `test_store.py` (cosseno determinístico, `drop_source`, persist/load), `test_retriever.py` (top-k + filtro de escopo), `test_embedder.py` (ramos de `is_available`/dim, `langchain_ollama` falso via `sys.modules`), `test_indexer.py` (chunking, header strip, filtro kind/sufixo, skip incremental/reembed por mtime, reconciliação, progresso), `test_chat.py` (contexto numerado + dedupe de fontes), `test_templates.py` (defaults + merge de `prompts.json` + proteção contra shadowing), `test_batch.py` (distinct/dedupe, kind, um answer por documento). Core ≥ 98% (`batch`/`chat`/`embedder`/`indexer`/`retriever`/`types` 100%).
- **GUI**: `tests/gui/modules/<audio|image|video|document>/test_pipeline_log.py` — `resolve_messages`/`resolve_stage_label` + `fmt_*` builders. `tests/gui/modules/ai/` — `test_worker.py` (index/answer via bus falso + core mockado; ramos indisponível/vazio/cancelado) e `test_pipeline_log.py` (`resolve_status` + `fmt_*`). `tests/gui/modules/recipes/` — `test_worker.py` (single/lote/clean/false/exceção via bus falso + `execute_recipe(_batch)` mockado) e `test_pipeline_log.py`. Workers não dependem de Flet, então são testáveis fora da cobertura.
- **Core Receitas** (`tests/core/recipes/`): tudo unit, sem ffmpeg/Whisper/rede. `test_registry.py` (cada `StepSpec` bem-formada + cada adaptador mockado no ponto de uso fixando o contrato `list[Path]` e pegando drift de assinatura; `ai.answer` com o core RAG mockado; multi-input `video.subtitle`), `test_runner.py` (encadeamento, ordem de eventos, cancel, stop_on_error, `emit_terminal`, `execute_recipe_batch` agrega/conta falhas/cancela, histórico multi-input via `mocker.patch.dict(STEP_REGISTRY, ...)`), `test_validate.py`, `test_presets.py` (cada preset válido p/ todo kind aceito pelo 1º passo), `test_store.py` (round-trip JSON em `tmp_path`), `test_inputs.py` (extensão → kind). Core ≥ 99%. `tests/cli/test_recipe_cli.py` cobre parser + `run_recipe_cli` (`execute_recipe` mockado).
- **LLM pipeline** (`tests/test_formatter.py`, `test_analyzer.py`, `test_prompter.py`): mockam LangChain via `GenericFakeChatModel` de `langchain_core.language_models.fake_chat_models` (Runnable real — `prompt | llm` funciona naturalmente sem fighting com MagicMock `__or__`).

Cobertura agregada do projeto: **88%** (com branch coverage).

Cobertura por módulo (último run, com branch):

- **100%**: `formatter.py`, `prompter.py`, `llm_utils.py`, `cli/audio.py`, `cli/transcription.py`, `core/ffmpeg.py`, `core/audio/normalizer.py`, `core/audio/info.py`, `core/video/converter.py`, `core/library/types.py`, `core/library/thumbnails.py`, `core/rag/{types,embedder,retriever,indexer,chat,batch}.py`, `core/recipes/{types,runner,validate,inputs,presets}.py`, e todos os `args.py`/`__init__.py`.
- **≥ 95% (Receitas)**: `core/recipes/registry.py` 99%, `core/recipes/store.py` 100%, `cli/recipes.py` 97%.
- **≥ 90%**: `analyzer.py` 99%, `cli/document.py` 98%, `cli/ai.py` 98%, `core/rag/store.py` 98%, `core/rag/templates.py` 98%, `core/library/scanner.py` 98%, `cli/video.py` 97%, `core/image/downloader.py` 96%, `cli/image.py` 94%, `core/document/info.py` 94%, `cli/library.py` ~93%, `core/audio/converter.py` 93%, `core/document/converter.py` 91%, `core/image/transform.py` 91%, `core/document/processor.py` 91%, `core/document/qr.py` 90%.
- **80-89%**: `cli/bus.py` 82%, `utils.py` 82%, `llm_factory.py` 81%, `core/audio/denoiser.py` 80%.
- **Lacunas conscientes**: `audio/downloader.py` 14%, `video/downloader.py` 12% (yt-dlp não mockado); `image/background.py` 32%, `image/describe.py` 23% (extras opcionais `[ai-image]`); `transcriber.py` 31% (Whisper — só `_resolve_device` testado).

> Guia completo para adicionar/revisar testes → skill `testing` (`.claude/skills/testing/SKILL.md`)

## Dependências externas (PATH)

- `yt-dlp` e `ffmpeg`/`ffprobe` — verificados em runtime por `check_dependencies()`
- **Tesseract** (opcional, OCR) — extra `[ocr]` (`uv sync --extra ocr`) + binário Tesseract com language packs (`por`, `eng`). `core/document/ocr.py::is_available()` resolve o binário no PATH ou em `C:\Program Files\Tesseract-OCR`; o card OCR desabilita graciosamente se ausente.

## LLM pipeline (Formatter / Analyzer / Prompter)

- **Chunking compartilhado** (`src/llm_utils.py`): `split_text(text, *, chunk_size, chunk_overlap, model_name, bypass_long_context, separators)`. Formatter usa separadores orientados a frases `[". ", "? ", "! ", ...]`; analyzer/prompter usam separadores padrão `["\n\n", "\n", ". ", ...]`. **Bypass de contexto longo** (ativado por `bypass_long_context=True` em analyzer e prompter): Gemini (1M tokens) pula o chunking **incondicionalmente**; modelos locais de contexto longo conhecidos pulam **só até um teto de chars** — `llm_factory.LONG_CONTEXT_LOCAL_BUDGETS` (`gemma3-4b-custom`: 12000 chars ≈ 3K tokens) via `long_context_char_budget()`. O teto fica bem abaixo do `num_ctx` para o prompt + a saída JSON verbosa caberem na janela. Acima do teto, volta a fatiar. Curtos/médios → passada única (mais coerente, sem merge); longos → chunk+merge como antes.
- **`num_ctx` do Ollama** (`llm_factory.DEFAULT_OLLAMA_NUM_CTX = 8192`): o Ollama usa **2048 por padrão**, pequeno demais para o JSON estruturado verboso do analyzer/prompter (e para o bypass) — isso **truncava a saída** gerando JSON inválido. `make_llm`/`_make_ollama` passam `num_ctx` ao `ChatOllama` (uniforme, p/ o Ollama não recarregar o modelo entre a chamada de análise grande e a de detecção de idioma pequena). Custo: KV-cache maior, sequencial. **Resiliência**: `analyzer._invoke_and_parse` tenta o parse 1× extra (modelos locais às vezes devolvem JSON malformado/truncado) antes de propagar o erro.
- **Formatter** (`src/formatter.py`): 4500 chars/150 overlap. Modelo padrão: `phi4mini-custom`.
- **Analyzer** (`src/analyzer.py`): 4500 chars/300 overlap, merge parcial. **Perfil-dirigido** (`src/analysis/`): `analyze(..., profile="default")` resolve o perfil e **gera** prompt de análise/merge + relatório a partir dos `fields` do perfil; a temperatura vem do perfil. Tradução automática PT-BR genérica. Modelo padrão: `qwen7b-custom`. `profile="default"` reproduz o esquema legado de 10 campos byte-a-byte (`_format_report` virou wrapper sobre `analysis.format_report(default)`).
- **Perfis de análise** (`src/analysis/`, puro/torch-free): `Field`/`AnalysisProfile`/`GroupMeta` (`types.py`); `build_analysis_prompt`/`build_merge_prompt` (`prompts.py`, **escapam chaves literais** `{`→`{{` p/ o `ChatPromptTemplate`); `format_report` (`report.py`, despacha por `kind` paragraph/list/quotes/keyvalue, `always`/`empty_text` p/ o default, disclaimer no topo). Catálogo em `profiles/` por grupo (`media.py`: default/lecture/interview/tutorial — regra "ignore CTAs" só aqui; `documents.py`: scientific/administrative; `creative.py`: literary/review/storytelling; `quick.py`: notes). `PROFILES`/`GROUPS`/`get_profile` (fallback ao default)/`list_profiles`. Adicionar perfil = uma entrada. Selecionável via CLI `transcribe --profile`, seletor GUI (`gui/components/profile_selector.py`, reusado por Transcrição e Documentos→Analisar) e param `profile` do passo `transcription.analyze` (Receitas). Persistência `last_analysis_profile`/`DocumentArgs.analyze_profile`.
- **Prompter** (`src/prompter.py`): 4500 chars/200 overlap, ~40% de compressão. Remove CTAs/patrocinadores. Modelo padrão: `qwen7b-custom`.

## Métricas de qualidade de transcrição

`transcriber.py` sinaliza segmentos com `[?]`: `avg_logprob < -1.0` (tokens incertos) ou `no_speech_prob > 0.6` (silêncio/ruído).

## Ollama

- **qwen7b-custom**: Qwen 2.5 7B — `--analyze` e resposta de RAG de máxima qualidade/batch; lento na CPU (`ollama/Modelfile`)
- **phi4mini-custom**: Phi-4 Mini 3.8B — `--format` (`ollama/Modelfile.phi4mini`)
- **gemma3-4b-custom**: Gemma 3 4B (multimodal, 128K ctx, multilíngue) — **resposta de RAG recomendada / default do dropdown da IA**. Validado em campo: sintetiza e cita `[n]` muito melhor que o 1B (corrige o otimismo do `docs/MODELOS_IA.md` de que "um 1B basta"). ~3,3 GB de RAM. Base `gemma3:4b`, CPU (`num_gpu 0`), `ollama/Modelfile.gemma3-4b`. Setup: `ollama pull gemma3:4b && ollama create gemma3-4b-custom -f ollama/Modelfile.gemma3-4b`.
- **gemma3-1b-custom**: Gemma 3 1B (só-texto, 32K ctx) — fallback **rápido / baixa-RAM** (~815 MB) da resposta de RAG; fraco em síntese/citação, usar quando a velocidade ou a RAM apertarem. Base `gemma3:1b`, CPU (`num_gpu 0`), `ollama/Modelfile.gemma3-1b`. Setup: `ollama pull gemma3:1b && ollama create gemma3-1b-custom -f ollama/Modelfile.gemma3-1b`.
- **moondream-custom**: moondream vision — descrição de imagens (`ollama/Modelfile.vision`; `num_thread 2`, `num_gpu 0`)
- **nomic-embed-custom**: embeddings do RAG (módulo IA) — 768-dim, **CPU (`num_gpu 0`)**, torch-free (`ollama/Modelfile.nomic`, base `nomic-embed-text`). Setup: `ollama pull nomic-embed-text && ollama create nomic-embed-custom -f ollama/Modelfile.nomic`. `embedder.is_available()` gateia o módulo (constante `SETUP_HINT` centraliza a dica). Alternativas multilíngues mais pesadas (1024-dim, exigem reindexação): `bge-m3` (567M, 8K ctx) e `mxbai-embed-large` (334M, 512 ctx).
- `num_gpu` controla camadas na GPU; `num_thread` controla threads CPU. Os Modelfiles do projeto são minimalistas (sem `SYSTEM`/`temperature`): o `make_llm` define a temperatura por papel e o prompt da chain fornece o system message.

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
| `ft.Dropdown` evento de seleção | **não** aceita `on_change` no construtor (0.85.2) — o evento é `on_select`; campos válidos: `on_select`, `on_text_change` |
| `control.page` antes do mount | lança `RuntimeError` — proteger com `try/except RuntimeError` |
| FilePicker | `page.services.append(picker)` + `await picker.pick_files(...)` |
| `Container(box_shadow=...)` | usar `Container(shadow=ft.BoxShadow(...))` — sem prefixo `box_` |
| `ft.NavigationRailDestination` cursor | sem `mouse_cursor` — envolver o `NavigationRail` em `GestureDetector`|
| `ft.Image.src` tipo | aceita `Union[str, bytes]` no 0.85 (confirmado via `ft.Image.__init__`) — bytes PNG passados diretamente sem base64 |
| `ft.Image` updates frequentes | usar `gapless_playback=True` para manter o frame anterior visível durante a troca — evita flickering (ex.: cursor de waveform a 5 fps) |
| `Container.on_hover` coberto | **não dispara** quando o Container é totalmente coberto por outra região de mouse (um `GestureDetector` filho com `mouse_cursor`, ou um GD pai). Para hover **e** tap no mesmo card, usar **um único** `ft.GestureDetector` com `on_enter`/`on_exit` (+ `on_tap`) — ver `home.py` (cards crescer-no-hover) |

### Eventos do pipeline

`PipelineEvent(type, stage, payload, module_id)`. `module_id` ∈ {`"transcription"`, `"audio"`, `"image"`, `"video"`, `"document"`, `"ai"`, `"recipes"`, `""` (legado)}. O `ProgressPanel` ignora eventos cujo `module_id` ≠ `owner_id`; os hubs IA e Receitas são auto-contidos (assinam os próprios eventos, não usam `ProgressPanel`).

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

**Documentos (stage="document"):** `document_op_start` (`operation`, `item_name`, `item_idx`, `total`, `page_count`), `document_op_done` (`output_path`, `elapsed`, `operation`, `item_idx`, `total`, `extra_stats`), `document_op_error` (`item_name`, `message`). `operation` ∈ {`merge`, `split`, `compress`, `rotate`, `watermark`, `stamp`, `encrypt`, `extract`, `ocr`, `pdf_to_images`, `images_to_pdf`, `analyze`, `qr`}.

**Transcrição (stage específico):** `metadata_start/done`, `audio_cached`, `download_start/done`, `whisper_loading/loaded`, `transcribe_started`, `language_detected` (`audio_duration`), `transcribe_segment` (`end`, `is_low_confidence`), `transcribe_summary`, `format_*`, `analyze_*`, `translation_*`, `prompt_*`.

**Receitas (module_id="recipes"):** `recipe_start` (`name`, `total_steps`), `step_start` (`op`, `label`, `idx`, `total`), `step_done` (`op`, `idx`, `total`, `outputs`), `step_error` (`op`, `idx`, `message`); reusa `progress_start`/`progress_update`/`task_done`/`task_error` e, no lote, `queue_progress`. Os adaptantes de passo encaminham os eventos das funções de core (ex.: `transcribe_segment`) sob o mesmo `module_id`.

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
| Análise | `gemini-2.5-flash`, `gemma3-4b-custom`, `qwen7b-custom` |
| Prompt-ready | `gemini-2.5-flash`, `gemma3-4b-custom`, `qwen7b-custom` |

> `gemma3-4b-custom` é o meio-termo **local** (mais rápido que o `qwen7b-custom` na CPU, ~3,3 GB, 128K ctx) para Análise e Prompt-ready — tarefas de síntese onde ele se sai bem (mesmo modelo do default do RAG). Não entra na Formatação (o `phi4mini-custom` já ocupa o slot pequeno/rápido e a formatação exige preservar o texto verbatim).

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

- **PR5** ✅ — Módulo Documentos: 13 operações GUI / 12 CLI (merge, split, compress, rotate, watermark, stamp, encrypt, extract, ocr, pdf_to_images, images_to_pdf, qr, analyze). Core pymupdf + qrcode. 28 testes unit adicionados.
- **PR5.1** ✅ — OCR: `ocr_pdf()` híbrido via pytesseract (extra `[ocr]`), Tesseract no PATH ou local padrão do Windows; card habilita/desabilita conforme disponibilidade. Fecha PDF escaneado → OCR → `analyze`.
- **Tier 0** ✅ — Legendas SRT/VTT na Transcrição (A+B), legenda no vídeo mux/burn (C), OCR (D). Ver `docs/STATUS_TIER0.md`.
- **PR6** ✅ — Módulo Biblioteca (Output Library): índice tipado de `output/` (core puro), grade GUI com filtro/busca/ordenação/período, thumbnails lazy, ações (abrir/abrir pasta) e bridges para outros módulos, paginação + auto-refresh, CLI `library list`. Hub no AppBar (fora da rail). Fundação para PR7 (IA sobre o corpus) e PR8 (receitas). Ver `docs/ROADMAP_PR6_BIBLIOTECA.md`.
- **PR6.6** ✅ — Biblioteca: 2º modo de exibição (lista/tabela) + visor in-app de `.md`/`.txt` (ler resultado processado sem reprocessar). Entrada flexível de análise: Transcrição aceita URL + áudio/vídeo local + texto (`.txt`/`.md` pula o Whisper); Documentos→Analisar aceita texto; CLI `transcribe` aceita texto/vídeo local; bridge `.txt` → "Analisar na Transcrição".
- **PR7** ✅ — Módulo IA / Conteúdo (RAG local sobre o corpus): core puro `src/core/rag/` (embeddings Ollama `nomic-embed-text`, vector store numpy, indexação incremental, retrieve cosseno, answer com citação de fontes, prompt library + templates, batch), módulo GUI (hub no AppBar, resposta Markdown com fontes clicáveis, status/reindexar) e CLI `ai index`/`ai "pergunta"`/`--batch`. Embeddings sempre locais; Gemini só opt-in na resposta. Torch-free, só `numpy` explícito de dependência. Streaming de resposta fica no v1 `invoke()` (adiável). Ver `docs/ROADMAP_PR7_IA.md`. Faseado PR7.0→7.4, um commit por fase.
- **PR8** ✅ — Módulo Receitas / Automação (cadeias lineares entre módulos): core puro `src/core/recipes/` (registro de passos `module.op` com adaptadores finos sobre o core dos 5 módulos + `ai.answer`, runner sequencial com cancel/`stop_on_error`/lote, validação `accepts`/`produces`, presets embutidos, store em `~/.mill-tools/recipes.json`), módulo GUI (3º hub no AppBar: rodar presets, construtor com validação ao vivo + reordenar ↑/↓, lote, limpar intermediários) e CLI `recipe list`/`recipe run`. Sem dependência nova, torch-free. Ver `docs/ROADMAP_PR8_RECEITAS.md`. Faseado PR8.0→8.4, um commit por fase.
- **PR3.1-B** — IA de áudio com torch (extra `[ai-audio]`): DeepFilterNet (denoise neural); Demucs (separação de stems) a avaliar.
- **Futuro** — melhorias no Módulo Imagens (batch rename, upscale); arrastar arquivos do SO fora de escopo (não nativo no Flet).
