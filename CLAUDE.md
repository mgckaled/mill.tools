# mill.tools

Multiferramenta pessoal extensível para processamento de áudio, vídeo, imagens, documentos, dados
estruturados e transcrição, com GUI desktop (Flet) e CLI. O módulo de Transcrição usa faster-whisper com
aceleração GPU — 100% local. A GUI tem **6 ferramentas** numa NavigationRail + **4 hubs** no AppBar.

> Este arquivo é o **índice**: orienta uma sessão de ponta a ponta sem precisar abrir skill nenhuma. As
> skills são profundidade, não pré-requisito. História e justificativas de decisão → `docs/HISTORY.md`.

## Fonte única por assunto (quem é o dono)

| Assunto | Dono |
|---|---|
| Camadas, limites de tamanho, decomposição (`blocks/`/`tabs/`/`registry/`) | skill `architecture` |
| Componentes de GUI, tokens, **quirks do Flet 0.85**, help system | skill `design-system` |
| Contrato de eventos (`PipelineEvent`, payloads por módulo, barra de progresso, thread-safety) | skill `design-system` (`events.md`) |
| RAG / ML / NLP / Observatório (core rag/ml/text/observatory, modelos Ollama, gates) | skill `ml-rag` |
| Subcomandos de CLI, argparse, `CLIEventBus` | skill `cli` (flags = `--help`) |
| Estrutura e mocks de teste | skill `testing` |
| Histórico, justificativas de decisão, planos concluídos | `docs/HISTORY.md` + `docs/plans/` |
| Roadmap pendente | `docs/ROADMAP.md` |

## Stack

- **Python 3.13** com `uv`.
- **faster-whisper** + **ctranslate2** — Whisper sem PyTorch (por escolha).
- **yt-dlp** (download/metadata) · **ffmpeg/ffprobe** (conversão, loudnorm EBU R128).
- **noisereduce** + **soundfile** (denoise spectral gating, CPU/torch-free) · **sounddevice** (playback PCM).
- **Pillow 12.2+** (imagens, AVIF nativo) · **pymupdf** (PDF) · **qrcode** · **rembg[cpu]** + **onnxruntime** (extra `[ai-image]`).
- **LangChain** + **Ollama** (local) / **Google Gemini** / **Zhipu GLM** (nuvem, opt-in) — formatação/análise/descrição de imagem + **RAG local** (embeddings Ollama, busca híbrida BM25+denso). Detalhe → skill `ml-rag`.
- **numpy** (vector store `.npz`) · **Flet 0.85** (Flutter desktop; testado 0.85.2) · **tqdm** (CLI).
- **duckdb** (SQL in-process, torch-free) + **charset-normalizer** — módulo Dados.
- Extras opcionais: `[analysis]` polars/pandas/pyarrow · `[data-plot]` matplotlib · `[ml]` scikit-learn ≥1.4 · `[ml-viz]` umap-learn · `[nlp]` yake+spacy · `[ocr]` Tesseract · `[ai-image]` rembg. Racional e gates → skill `ml-rag`.

> **Decisões operacionais**: **sem PyTorch** no app base (IA com torch iria p/ um extra `[ai-audio]` isolado);
> **encoding de vídeo 100% CPU — sem NVENC** (definitivo). Justificativas completas → `docs/HISTORY.md` e
> `docs/reference/RELATORIO_CENARIO_TORCH.md`.

## Estrutura

```text
main.py / gui.py                 — entry points CLI / GUI (splash → home → build_app)
src/
├── transcriber.py · formatter.py · analyzer.py · prompter.py · llm_factory.py · llm_utils.py · utils.py
├── analysis/                    — perfis de análise (puro): types/prompts/report + profiles/ por grupo
├── core/                        — PURO (sem Flet): reutilizável por CLI e GUI
│   ├── ffmpeg.py (run_ffmpeg, aceita cwd=) · subtitles.py · io_types.py · metadata.py · ytdlp_cookies.py
│   ├── audio/  video/           — cada um: args.py + downloader/converter/info + específicos
│   ├── image/                   — args + downloader/converter/info + transform/background/describe/exif/smart_crop/filter_previews/ocr/dhash
│   ├── document/                — args + downloader/converter/info + processor/converter/info/ocr/qr
│   ├── library/                — types · scanner · thumbnails · analytics · tags · image_dedup
│   ├── rag/ · ml/ · text/ · observatory/   — RAG, ML clássico, NLP, hub de ML → skill `ml-rag`
│   ├── recipes/                — types · registry/<módulo> · runner · validate · inputs · presets · store · history
│   └── data/                   — types · scanner · engine (única fronteira DuckDB) · nl2sql · validate · convert · profile · assess · datacard · store · frames · charts · ml
├── cli/                         — bus.py (CLIEventBus) + 1 módulo por subcomando + transcription.py → skill `cli`
└── gui/                         — app.py (rail + hubs) · splash · home · events · settings · workers + modules/ · theme/ · views/ → skill `design-system`
```

> Responsabilidade de cada arquivo é derivável do código; onde algo novo deve morar e como dividir arquivos
> grandes → skill `architecture`.

## Sistema de módulos (GUI)

- **6 ferramentas** (Áudio→Vídeo→Imagens→Transcrição→Documentos→Dados) na **NavigationRail**;
  **Biblioteca/IA/Receitas/Observatório** são **hubs** (botões dourados no AppBar, operam sobre as saídas de
  todos). `MODULES: list[Module]` em `app.py` é fonte única — adicionar módulo = uma entrada.
- **`navigate_to(module_id, payload)`** alterna **visibilidade** num `ft.Stack` (nunca reatribui `content` —
  quirk do Flet 0.85); bloqueia troca enquanto `pipeline_running[0]`.
- **Bridges** (`navigate_to(target, {...})` → `on_mount`): Áudio/Vídeo/Biblioteca→Transcrição; Vídeo→Áudio;
  Biblioteca→IA ("Conversar sobre"); IA→Observatório (`{"tab": "index"}` — "Indexar no Observatório", já que a
  reindexação roda lá, não no hub de IA).
- Escopo de eventos: cada `ProgressPanel` ignora `module_id` ≠ `owner_id`; IA/Receitas/Dados são auto-contidos.

## Módulo Transcrição

Whisper + pipeline de IA (Formatação/Análise/Prompt-ready). `InputSource` único aceitando **URL**,
**áudio/vídeo local** e **texto** (`.txt`/`.md`).

- **Formulário adaptativo** (`views/form_view.py`): texto → esconde a seção de transcrição, mantém só as
  etapas de IA; mídia/URL → mostra tudo. Auto-sugestão de perfil + aba **Insights** (Plano 4B) → skill `ml-rag`.
- **Worker** (`gui/workers.py::run_pipeline`): **texto** → copia p/ `output/transcriptions/text/` (nunca edita
  o original — o `formatter` reescreve in-place), pula Whisper, roda só IA (**guarda**: exige ≥1 análise);
  **áudio/vídeo local** → transcreve (faster-whisper decodifica vídeo via PyAV, sem extração); **URL** →
  metadata + download + transcrição.
- **Métricas**: `transcriber.py` sinaliza segmentos com `[?]` (`avg_logprob < -1.0` ou `no_speech_prob > 0.6`).
- **Credenciais** (`GOOGLE_API_KEY`/`ZHIPU_API_KEY`) **não** ficam aqui — moveram p/ o diálogo de Configurações
  (usadas por todo o app). ETA e payloads → skill `design-system` (`events.md`).

## Módulo Áudio

Auto-detecta URL→download / vídeo→extração / áudio→conversão. Formatos `best`/mp3/m4a/wav/ogg/opus.
**Saída**: `output/audio/source/` (downloads) · `output/audio/processed/`.

- Toggle **Converter | Visualizar** (áudio→áudio vs. áudio→imagem via `showwavespic`/`showspectrumpic`).
  Reprodutor embutido (`audio_player.py`, sounddevice) com **A/B Original|Processado** e card de loudness.
- **Pós-processamento** (ordem fixa **silêncio → denoise → velocidade → normalize → encode final**): o encode
  final aplica `args.fmt` + downmix mono (`-ac`) + sample-rate (`-ar`), consertando o denoise→`.wav`.
  Presets de uma tecla (Transcrição/Podcast/Música).
- **Quirk Windows (downloader)**: `FFmpegExtractAudio` cria `.temp.<ext>` **no dir do arquivo de entrada**
  (hardcoded; `paths={"temp"}` não resolve) → rodar download+pós em `tempfile.mkdtemp()` e mover via
  `shutil.move`. Payloads/player detail → `events.md`.

## Módulo Vídeo

Download/conversão/processamento via yt-dlp + ffmpeg. 8 operações (download/convert/trim/compress/resize/
extract_audio/thumbnail/subtitle). **Saída**: `output/video/source/` · `output/video/processed/`.

- **Legenda** (`add_subtitles`): `soft` (mux) = `-c copy -c:s mov_text` (sem reencode); `hard` (burn-in) =
  `-vf subtitles=…` + libx264. Saída `<stem>_subbed.mp4`.
- **Quirk Windows — nunca usar `FFmpegVideoConvertor`**: cria `.temp.<ext>` no dir de saída e o Defender
  bloqueia o rename (`[WinError 32]`). Usar só `merge_output_format` + `nopart=True`, `overwrites=True`,
  `paths={"temp": tempfile.gettempdir()}`. Fix durável: excluir `output/` do Defender.
- **Quirk burn-in**: o filtro `subtitles` interpreta `:` como separador → o `:` do drive (`C:`) quebra o
  parser. Rodar ffmpeg com `cwd` na pasta da legenda e referenciá-la por **basename** (`run_ffmpeg` aceita
  `cwd=`). Mux soft dispensa `cwd`.
- **Progresso yt-dlp**: `_percent_str`/`_speed_str`/`_eta_str` têm ANSI — strip antes de exibir.

## Módulo Imagens

Conversão/manipulação + IA, com visor Before/After. Toggle **Edição | Descrição IA**. A Edição tem 12
operações imagem→{imagem|texto} (convert/resize/crop/rotate/watermark/border/adjust/filter/favicon/
contact_sheet/remove_bg/ocr); a Descrição IA isola o `describe` (imagem→texto). **Saída**:
`output/image/source/` · `output/image/processed/`.

- `core/image/transform.py` = funções puras Pillow; `background.py` (rembg, `[ai-image]`); `describe.py`
  (Ollama vision local / `glm-4.6v-flash`/`gemini-2.5-flash` opt-in → skill `ml-rag`); `ocr.py` reusa o
  Tesseract do `[ocr]` → `<stem>_ocr.txt` (indexável no RAG).
- **EXIF** (`exif.py`): `preserve|strip|strip_gps|inject` como **pós-processo aditivo** (não toca a assinatura
  das transforms). Visor Before/After com fundo xadrez p/ alfa, faixa de metadados e "Criar PDF".

## Módulo Documentos

PDF + QR via pymupdf (sem ffmpeg). 13 operações GUI / 12 CLI (sem `analyze`, só-GUI). **Saída**:
`output/document/processed/`.

- `core/document/`: `processor.py` (7 funções pymupdf), `converter.py` (pdf_to_images/images_to_pdf/
  extract_text), `info.py` (`get_pdf_info` + `render_first_page_png`, reusado pela Biblioteca), `qr.py`.
- **OCR** (`[ocr]`): **híbrido** — usa a camada de texto nativa por página; só rasteriza + Tesseract nas
  páginas escaneadas (300 DPI piso). Fecha **PDF escaneado → OCR → texto → `analyze`**.

## Módulo Biblioteca (hub)

Hub navegável de tudo sob `output/`. **Read-only** (sem worker/pipeline) — ações disparam navegação/abertura.

- `core/library/`: `scanner.py` mapeia cada dir de saída → `(kind, category)` (inclui `transcription/
  subtitles`); `thumbnails.py` despacha primeiro por **suffix de imagem** (qualquer kind — cobre o PNG de
  waveform/espectrograma do Áudio), depois por kind (document/video). GUI: 4 modos (Grade·Lista·**Painel**·
  **Mapa**), filtro/busca/categoria; thumbnails numa thread daemon com update **escopado** (nunca
  `page.update()`).
- **Ações**: Abrir (texto → visor in-app `file_viewer.py`; demais → `os.startfile`), bridges. CLI `library
  list/stats/dedup-images`. Auto-tags, mapa semântico e dedup de imagens → skill `ml-rag`.

## Módulo IA (hub) · Módulo Observatório (hub)

Ambos são hubs de ML — **toda a maquinaria de RAG/ML/NLP e o detalhe destes dois hubs vivem na skill
`ml-rag`**. Resumo:

- **IA**: RAG local sobre o corpus (indexa o texto que você produziu, recupera trechos e responde citando
  fontes). Toggle **Corpus | Comandos CLI**: Corpus é a Conversa (mostra a linha de status do índice
  read-only + botão "Indexar no Observatório", já que a reindexação em si roda lá); Comandos CLI traduz um
  pedido em português no comando `uv run main.py ...` exato (nunca executa — só copia), via
  `core/text/nl2cli.py` + a referência introspectada de `cli/reference.py` (mesmo recurso do CLI `ai --cmd`).
- **Observatório**: hub cross-módulo de ML — read-only, **exceto** a sub-aba Índice (Índice/RAG), que roda o
  próprio pipeline de reindexação (botão Reindexar + progresso + Cancelar, `module_id="observatory"`). 5 abas
  (Índice/RAG · Status · Atividade · Logs · Tempo de resposta); Índice/RAG é aninhada (Índice·Painel·Uso de
  disco). Selo de novidades no AppBar (`last_ml_activity_seen`).

## Módulo Receitas (hub)

Cadeias **lineares** nomeadas onde a saída de um passo alimenta o próximo, atravessando módulos (`URL → baixar
áudio → transcrever → analisar`). Generaliza o `run_pipeline`; reusa o core puro dos módulos + `ai.answer`.

- `core/recipes/`: `registry/<módulo>.py` — `STEP_REGISTRY: "module.op" → StepSpec`; adaptadores finos
  (`adapter(inputs, params, ctx) → list[Path]`) chamam o core puro, gravam no dir canônico e normalizam
  callbacks p/ `ctx.emit`. `runner.execute_recipe(_batch)`.
- **Casos sutis**: `transcription.format` reescreve in-place → `[input_path]`; `video.subtitle` é o único
  **multi-input**; `ai.answer` exige `is_available()`. GUI toggle **Rodar | Construir** + aba **Histórico**
  (`recipe_runs.json`). Persistência: `recipes.json`.

## Módulo Dados

6ª ferramenta na rail (transforma entrada→saída, **não** é hub). **Query-first**: a composição vive numa
consulta única, em português (traduzida pela IA) ou na mão. Motor **DuckDB** (in-process, torch-free).
**Privacidade**: a IA recebe **só o schema** (nomes/tipos de coluna) e devolve `(sql, explicação)` — nunca as
linhas. **Saída**: `output/data/`.

- `core/data/`: `engine.py` é a **única fronteira DuckDB** (injetável); `nl2sql.py` (PT→SQL, validado por
  `ensure_select`); `validate.py` (só leitura, rejeita DML/COPY/ATTACH); `frames.py` (única fronteira de
  DataFrame, Polars/pandas, Arrow zero-copy, `[analysis]`); `charts.py` (única fronteira matplotlib,
  `[data-plot]`); `assess.py`/`datacard.py` (avaliação IA + cartão indexável, PR9.3); `ml.py` (outliers).
- GUI: **4 abas** (Consulta · Pré-visualização · Análise com IA · Gráfico), cada uma com rodapé fixo.
  Integrações: Receitas (`data.query/convert/profile/outliers`), Biblioteca (`kind="data"`), RAG (indexação
  pelo cartão de dados). CLI `data query/convert/profile/assess/plot/outliers`. Detalhe de indexação/outliers
  → skill `ml-rag`.

## Cookies do YouTube (anti-bot)

Mitiga o gate anti-bot passando cookies de um navegador logado. Lógica isolada em `core/ytdlp_cookies.py`
(puro), reusada por todos os call sites: `cookie_ydl_opts()` é mesclado nas 3 funções core do yt-dlp
(`audio/downloader`, `video/downloader`, `metadata`). **Nunca levanta** (try/except → `{}`).

- **Zen Browser**: o yt-dlp não conhece "zen" → mapeia `("firefox", <path do perfil Zen>, None, None)`.
- **Config**: env `MILL_YT_COOKIES_*` → `config.json`. Default `"none"` — **opt-in**.
- **Limitação — PO Token / SABR** (validado jun/2026): cookies passam o gate anti-bot, mas cookies de **conta
  logada** fazem o YouTube exigir **PO Token**; sem ele o yt-dlp recebe só storyboards → `Requested format is
  not available`. Por isso o default é `none` (cookies de conta costumam **atrapalhar**). Fix durável
  (`bgutil-ytdlp-pot-provider`) não implementado (exige Node/Deno). Mitigação: baixar sem cookies + retry.

## Splash + Home + Configurações

Fluxo: `show_splash` → `show_home` → `build_app(initial_module)`. Home: 6 ferramentas (grade 3×2) + 4 hubs
sobre o moinho girando, cards crescer-no-hover (um único `GestureDetector` com `on_enter`/`on_exit` — quirk
`Container.on_hover` coberto). **Diálogo de Configurações** (engrenagem no AppBar): 2 seções — **Cookies do
YouTube** e **Credenciais** (API keys salvas no `.env` da raiz no `on_blur`, via `views/form_env.py` →
`llm_factory._load_env_once`; nunca por `gui.settings`/rede).

## Comandos

```bash
uv run gui.py                                          # GUI desktop
uv run main.py <URL>                                   # Transcrição básica (legado)
uv run main.py transcribe <URL|file.mp4|notas.txt> --format --analyze --profile lecture
uv run main.py audio   <URL_OR_FILE> [--fmt mp3] [--quality 320] [--mono] [--sample-rate 16000] [--trim-silence] [--speed 1.25] [--denoise [--denoise-adaptive]] [--normalize [--lufs -16]]
uv run main.py audio-viz <arquivo> [--spectrogram] [--width 1200] [--height 480]
uv run main.py video   <download|convert|trim|compress|resize|extract-audio|thumbnail|subtitle> <input> [opções]
uv run main.py image   <convert|resize|crop|rotate|watermark|border|adjust|filter|favicon|contact-sheet|remove-bg|describe|exif|ocr> <input> [opções]
uv run main.py document <merge|split|compress|rotate|watermark|stamp|encrypt|extract|ocr|pdf-to-images|images-to-pdf|qr> <input> [opções]
uv run main.py library list [--kind audio|data] [--since 7d] [--sort size] | library dedup-images [--max-distance 8]
uv run main.py ai index | ai stats | ai dups | ai topics | ai map [--method pca|tsne|umap] | ai related <path> | ai classify|keywords|summary|entities <path>
uv run main.py ai "pergunta" [--scope X] [--model gemini-2.5-flash] [--k 8] [--batch]
uv run main.py ai --cmd "corta o silêncio do podcast.mp3 e acelera 1.25x"  # NL->CLI, imprime o comando
uv run main.py recipe list | recipe run "<nome>" <URL_OR_FILE> [--model medium]
uv run main.py data   query <arquivos...> "<pergunta>" [--sql] [--out csv|xlsx|json|parquet] | data convert|profile|assess|plot|outliers <arquivo>
uv run main.py observatory status | observatory activity | observatory logs | observatory disk-usage
```

> Referência completa de flags → `--help` do código (e skill `cli` p/ padrões/gotchas).

## Convenções de código

- **Idioma do código em inglês** (docstrings/logs/comentários/nomes); português **só** em labels da GUI. Ao
  tocar um arquivo com PT em docstring/log, corrigir p/ EN na mesma passagem.
- **Exceção — mensagens de exceção *user-facing* no core podem ser em PT.** Elas chegam cruas à GUI/CLI (ex.:
  `DataEngineError`, `ConvertError`, `ValueError` dos charts) — são texto de interface, não código. Decisão
  registrada na Fase 0 do `PLANO_CORRECOES_CORE_DATA.md` (`core/data` já seguia isso; formalizado aqui em
  vez de renomear módulos inteiros).
- **Core (`src/core/`) é puro**: sem Flet, sem `print` (logging via handler dedicado), dependência de
  rede/modelo **injetável**. Detalhe de camadas/tamanho/decomposição → skill `architecture`.
- **`subprocess` sempre em modo binário** (`Popen`/`run` sem `text=True`); decodificar com
  `.decode("utf-8", errors="replace")` — em Windows `text=True` herda cp1252 → `UnicodeDecodeError`.
- Linter **ruff** · Testes **pytest** (`uv run pytest -m unit` verde antes de qualquer commit).

## Testes · Dependências externas

- Marcadores `unit`/`integration` (este pulado se ffmpeg ausente); agregado ~88%, excluindo `src/gui/`.
  Estrutura, fixtures e mocks → skill `testing`.
- **PATH**: `yt-dlp`, `ffmpeg`/`ffprobe` (verificados por `check_dependencies()`); **Tesseract** opcional
  (`[ocr]`, resolvido no PATH ou `C:\Program Files\Tesseract-OCR`); **modelo spaCy** `pt_core_news_sm` à parte
  (`[nlp]`) → skill `ml-rag`.

> **Quirk Windows — pacote corrompido após `uv sync` (lock de `.pyd`)**: um `uv sync` interrompido por lock do
> Windows sobre um `.pyd` (binário em uso por `python.exe`/GUI aberto, ou Defender) deixa um pacote
> meio-instalado (sem `__init__.py`) → `ImportError: cannot import name 'X' from 'pkg' (unknown location)`.
> **Fix**: `uv run poe repair <pkg>`. **Prevenção**: feche a GUI antes de `uv sync`.

## GUI / Flet 0.85

`uv run gui.py` (Flutter desktop no Windows). **Quirks do Flet 0.85 e controles verificados → skill
`design-system`** (tabela única). Contrato de eventos → `design-system` (`events.md`). LLM pipeline
(Formatter/Analyzer/Prompter, `num_ctx`, bypass de contexto longo, perfis de análise) e modelos Ollama →
skill `ml-rag`.

### GPU — sobrecarga e estabilidade (MX150 / Pascal)

Flet (DirectX) e Whisper (CUDA) disputam a MX150 — uso simultâneo pode causar BSOD
`WIN32K_POWER_WATCHDOG_TIMEOUT`. Mitigações: `LogEventHandler` em INFO; libs ruidosas capadas em WARNING; fila
de áudio sequencial. Se persistir: forçar `python.exe` em "Economia de energia" (iGPU Intel) nas configs de
gráficos do Windows.

## Hardware de desenvolvimento

Dell Inspiron 7580 — i5-8265U, 16GB RAM · NVIDIA MX150 (2GB VRAM), CUDA 12.6 · compute `int8_float32`
(Pascal) · throttling gerenciado pelo EC Dell (~63-65°C) · Windows 10 Home.

## Roadmap

Pendentes: **PR9.2** (encadeamento em estágios), **PR3.1-B** (IA de áudio com torch, extra `[ai-audio]`),
**Planos 4C–7** (compõem os motores de ML já entregues), Imagens (batch rename, upscale), arrastar arquivos
do SO. Detalhe → `docs/ROADMAP.md` e `docs/plans/active/`. Marcos concluídos e decisões → `docs/HISTORY.md`.
