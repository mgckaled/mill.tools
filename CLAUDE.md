# mill.tools

Multiferramenta pessoal extensível para processamento de áudio, vídeo, imagens, documentos, dados estruturados e transcrição, com GUI desktop (Flet) e CLI. O módulo de Transcrição usa faster-whisper com aceleração GPU — 100% local. A GUI é organizada em **módulos** acessíveis por uma sidebar (NavigationRail) + 3 hubs no AppBar.

## Stack

- **Python 3.13** com `uv`
- **faster-whisper** + **ctranslate2** — Whisper sem PyTorch (por escolha)
- **yt-dlp** (download/metadata) · **ffmpeg/ffprobe** (conversão, loudnorm EBU R128)
- **noisereduce** + **soundfile** — denoise spectral gating (CPU, torch-free); **sounddevice** — playback PCM (reprodutor da GUI)
- **Pillow 12.2+** (imagens, AVIF nativo) · **pymupdf** (PDF engine) · **qrcode** (QR) · **rembg[cpu]** + **onnxruntime** (extra `[ai-image]`, remoção de fundo)
- **LangChain** + **Ollama** (local) / **Google Gemini** (nuvem) — formatação/análise/condensação/descrição de imagens; **RAG local** via `OllamaEmbeddings` (`nomic-embed-custom`, CPU, 768-dim)
- **numpy** — vector store do RAG (`.npz`) · **Flet 0.85** (Flutter desktop; testado 0.85.2) · **tqdm** (CLI)
- **duckdb** (motor SQL embutido, in-process, **torch-free**, sem servidor) + **charset-normalizer** (detecção de encoding de CSV) — módulo Dados; extensão `excel` do DuckDB só para XLSX

> **Decisão consciente: sem PyTorch.** Pós-processamento de áudio é CPU-only/torch-free. IA com torch (Demucs, DeepFilterNet) ficaria isolada num extra `[ai-audio]` — o app base permanece torch-free. **Encoding de vídeo 100% CPU — sem NVENC** (definitivo).

## Estrutura

```
main.py / gui.py                 — entry points CLI / GUI (splash → home → build_app)
src/
├── transcriber.py · formatter.py · analyzer.py · prompter.py · llm_factory.py · llm_utils.py · utils.py
├── analysis/                    — perfis de análise (puro): types/prompts/report + profiles/ por grupo
├── cli/                         — bus.py (CLIEventBus) + 1 módulo por subcomando (audio/video/image/document/library/ai/recipes/data) + transcription.py (helpers)
├── core/                        — PURO (sem Flet): reutilizável por CLI e GUI
│   ├── ffmpeg.py (run_ffmpeg, aceita cwd=) · subtitles.py · io_types.py · metadata.py · ytdlp_cookies.py
│   ├── audio/  video/  image/  document/   — cada um: args.py + downloader/converter/info + específicos
│   ├── library/                — types.py (LibraryItem) · scanner.py · thumbnails.py
│   ├── rag/                    — types · embedder (única rede) · store (VectorStore) · indexer · retriever · chat · templates · batch · stats
│   ├── recipes/                — types · registry · runner · validate · inputs · presets · store
│   └── data/                   — types · scanner · engine (única fronteira DuckDB; preview/abas XLSX) · nl2sql · validate · convert · profile · assess (qualidade IA) · datacard (cartão indexável) · store
└── gui/
    ├── app.py (build_app: rail + hubs) · splash.py · home.py · events.py · settings.py · settings_dialog.py · workers.py · help_content.py
    ├── components/             — input_source.py · profile_selector.py · audio_player.py
    ├── modules/                — base.py (Module) · _pipeline_runner.py + 1 pasta/módulo (form_view/worker/view/pipeline_log; image+document têm blocks/)
    ├── theme/                  — theme.py · tokens.py · components/ (factories + Cursor + sliders)
    └── views/                  — form_view (Transcrição) · progress_view (ProgressPanel) · result_view · file_viewer (visor .md/.txt)
```

> Responsabilidade de cada arquivo é derivável do código. Detalhe da CLI → skill `cli`; do design system / eventos de GUI → skill `design-system`; de testes → skill `testing`.

## Sistema de módulos (GUI)

- **6 ferramentas** (Áudio→Vídeo→Imagens→Transcrição→Documentos→Dados) na **NavigationRail**. **Biblioteca/IA/Receitas** são **hubs** fora da rail (operam sobre as saídas de todos) — botões dourados no AppBar. Os 3 ainda estão em `MODULES`/`ft.Stack`; `_RAIL_MODULES` exclui os `_HUB_IDS`.
- **Registry** (`app.py`): `MODULES: list[Module]` é fonte única — adicionar módulo = uma entrada. **Module** (`modules/base.py`): dataclass `id/label/icon/selected_icon/control/on_mount(payload)/on_unmount`; o `control` é construído uma vez (trocar de aba não destrói estado).
- **navigate_to(module_id, payload)**: alterna **visibilidade** num `ft.Stack` (não reatribui `content` — evita `object_patch` IndexError do Flet 0.85). Bloqueia troca enquanto `pipeline_running[0]`.
- **Entrada via Home Screen** (`home.py`): 6 ferramentas (grade 3 por linha = 3+3) + 3 hubs (cards largos, borda dourada, selo "HUB") sobre o moinho girando. Clique → `build_app(initial_module=id)`.
- **Bridges** (`navigate_to(target, {"file": path})` → `on_mount` chama `fill_from_path`/`bind_document`): Áudio/Vídeo/Biblioteca→Transcrição; Vídeo→Transcrição/Áudio (botões pós-`extract_audio`); Biblioteca→IA ("Conversar sobre", fixa escopo do documento).
- **Escopo de eventos**: cada `ProgressPanel` tem `owner_id` e ignora `module_id` diferente; IA e Receitas são auto-contidos (assinam os próprios eventos).

## Módulo Transcrição

Whisper + pipeline de IA (Formatação/Análise/Prompt-ready). `InputSource` único aceitando **URL**, **áudio/vídeo local** e **texto** (`.txt`/`.md`).

- **Formulário adaptativo** (`views/form_view.py`): texto → esconde a seção de transcrição (modelo/idioma/beam/legendas) e mantém só as etapas de IA; mídia/URL → mostra tudo.
- **Worker** (`gui/workers.py::run_pipeline`): **texto** → copia p/ `output/transcriptions/text/` (nunca edita o original — o `formatter` reescreve in-place), pula Whisper, roda só IA (**guarda**: exige ≥1 análise); **áudio/vídeo local** → transcreve (faster-whisper decodifica vídeo via PyAV, sem extração); **URL** → metadata + download + transcrição. `format/analyze/prompt` são compartilhados.
- **ETA (PR7.2.5)**: rótulo abaixo da última linha mostra tempo restante + fator de velocidade (`"≈ 3m 00s restantes · 0,85× tempo-real"`). `transcription/pipeline_log.format_eta(elapsed, end, audio_duration)` (puro/testado) = média móvel; só após **5%** transcrito (início ruidoso). `progress_view.py` captura `t0` em `transcribe_started`, atualiza por `transcribe_segment`, esconde nos estados terminais.

## Módulo Áudio

- Auto-detecta: URL → download; vídeo local → extração; áudio local → conversão. Formatos `best`/mp3/m4a/wav/ogg/opus + bitrate; `best` sem reencode. Capa/metadados embutidos por padrão (fallback em ogg/opus). Fila sequencial.
- **Saída**: downloads → `output/audio/source/`; processados → `output/audio/processed/`.
- **Reprodutor embutido** (`components/audio_player.py`): aparece após o pipeline; sounddevice; seek por clique no waveform. **Waveform — 2 threads**: decode rápido a 500 Hz mono (exibir) + decode completo 44100 estéreo (playback); `_load_generation` descarta cargas antigas; `gapless_playback=True` evita flicker no cursor.
- **Pós-processamento** (switches encadeáveis): `denoiser.py` (spectral gating noisereduce, salva WAV preservando subtype PCM via `sf.info`+`subtype`); `normalizer.py` (loudnorm 2 passes, alvo −23..−6 LUFS default −14, True Peak ≤ −1 dBFS, retorna `(path, stats)`).
- **Quirk Windows (downloader)**: `FFmpegExtractAudio` cria `.temp.<ext>` **no dir do arquivo de entrada** (hardcoded; `paths={"temp"}` não resolve). Solução: rodar download+pós em `tempfile.mkdtemp()` e mover o final via `shutil.move`.

## Módulo Vídeo

Download/conversão/processamento via yt-dlp + ffmpeg. 8 operações (download/convert/trim/compress/resize/extract_audio/thumbnail/subtitle). `core/video/converter.py` delega a `run_ffmpeg`. **Saída**: `output/video/source/` (download) · `output/video/processed/`.

- **Legenda** (`add_subtitles`): `soft` (mux) = `-c copy -c:s mov_text` (sem reencode); `hard` (burn-in) = `-vf subtitles=…` + libx264 (reencoda). Saída `<stem>_subbed.mp4`.
- **Quirk Windows — nunca usar `FFmpegVideoConvertor`** (qualquer formato): cria `.temp.<ext>` no dir de saída e o Defender bloqueia o rename (`[WinError 32]`). Usar só `merge_output_format` + `nopart=True`, `overwrites=True`, `paths={"temp": tempfile.gettempdir()}`. Fix durável: excluir `output/` do Defender.
- **Progresso yt-dlp**: `_percent_str`/`_speed_str`/`_eta_str` têm ANSI — strip antes de exibir (`re.sub(r'\x1b\[[0-9;]*m', '', s)`).
- **Quirk burn-in**: o filtro `subtitles` interpreta `:` como separador → o `:` do drive (`C:`) quebra o parser. Solução: rodar ffmpeg com `cwd` na pasta da legenda e referenciá-la por **basename** (`run_ffmpeg` aceita `cwd=`). Mux soft não usa filtro, dispensa `cwd`.

## Módulo Imagens

Conversão/manipulação + IA, com visor Before/After. 12 operações (convert/resize/crop/rotate/watermark/border/adjust/filter/favicon/contact_sheet/remove_bg/describe). `core/image/transform.py` = 9 funções puras; `background.py` (rembg, lazy, extra `[ai-image]`); `describe.py` (Ollama vision → `.txt`).

- **GUI** (`form_view.py` + `blocks/`): formulário quebrado em blocos `build_X_block(page) → (ft.Column, XRefs)` (`XRefs` = NamedTuple de `get_*`). Card `remove_bg`/`describe` desabilita com tooltip quando o extra falta (padrão **`_UNAVAILABLE`**).
- **Visor Before/After**: `_single_pane` vs `_before_after_row`, toggle por `visible=`; `_last_input_thumb` preserva o thumb p/ o split após `image_op_done`.
- `LOSSY_FMTS = {"jpg","jpeg","webp"}`. **Saída**: `output/image/source/` · `output/image/processed/`.

## Módulo Documentos

PDF + QR via pymupdf (sem ffmpeg). 13 operações GUI (merge/split/compress/rotate/watermark/stamp/encrypt/extract/ocr/pdf_to_images/images_to_pdf/analyze/qr); CLI tem 12 (sem `analyze`, só-GUI). Mesmo padrão de `blocks/` do módulo Imagens. **Saída**: `output/document/processed/`.

- **`core/document/`**: `processor.py` (7 funções pymupdf), `converter.py` (pdf_to_images/images_to_pdf/extract_text), `info.py` (`get_pdf_info` + `render_first_page_png`, reusado pela Biblioteca), `qr.py`.
- **OCR** (`ocr.py`, extra `[ocr]`): **híbrido** — usa a camada de texto nativa por página; só rasteriza + Tesseract nas páginas escaneadas (300 DPI piso). `is_available()` resolve o binário no PATH ou em `C:\Program Files\Tesseract-OCR`; card desabilita se ausente. Fecha **PDF escaneado → OCR → texto → `analyze`**.
- `analyze`: PDF passa por `extract_text`; `.txt`/`.md` é analisado direto.

## Módulo Biblioteca (PR6)

Hub navegável de tudo sob `output/`. **Read-only** (sem worker/pipeline) — ações disparam navegação/abertura. Torch-free, zero dependência nova.

- **Core puro** (`core/library/`): `scanner.py` mapeia cada dir de saída → `(kind, category)`, `scan_library()` (varredura rasa, mtime-desc, pula ocultos/ilegíveis), `filter_items`/`sort_items`; `thumbnails.py::thumbnail_for` despacha por kind (imagem→bytes, PDF→`render_first_page_png`, vídeo→frame via ffmpeg `pipe:1`; áudio/texto→ícone).
- **GUI** (`modules/library/`): tela cheia; 2 modos (grade `GridView`/lista `ListView`) por `visible=` num `Stack`; filtro por tipo (`segmented_selector`), busca (debounce via `page.run_task`), categoria/ordenação/período (`ft.Dropdown` com `on_select`). **Cache**: scan em `_all_items`, filtro/busca em memória; thumbnails numa **única thread daemon** com contador de geração + cache `(path, mtime)`; cada card recebe `set_thumbnail()` com **update escopado** (nunca `page.update()` — issue #6270). Paginação `_PAGE_SIZE=120`.
- **Ações**: Abrir (texto → visor in-app `file_viewer.py`; demais → `os.startfile`), Abrir pasta (`explorer /select,`), bridges p/ outros módulos. `on_mount` re-escaneia ao entrar + ao vivo em `task_done`.
- **CLI**: `library list [--kind] [--since] [--sort]` reusa o core; stdout em UTF-8 (nomes com `｜` quebram cp1252).

## Módulo IA (PR7)

RAG local sobre o corpus: indexa o texto que você produziu, recupera os trechos relevantes e responde **citando as fontes**. Embeddings **100% locais** (Ollama); Gemini só opt-in na resposta. Torch-free (só `numpy`). Reusa `make_llm`/`split_text`/`EventBus`/`scan_library`.

- **Core puro** (`core/rag/`): `embedder.py` é a **única rede** (injetável como `embed_fn`; o resto é unit-testável sem Ollama). `VectorStore` = matriz numpy `(N,D)` com busca cosseno + persistência `.npz`/`.json` em `~/.mill-tools/rag/`. `build_index()` **incremental** por `(path, mtime)` (pula inalterados, reembeda alterados, reconcilia removidos); indexa kinds textuais (`transcription`/`document` + descrições `.txt`), tira o header de transcrição, chunka via `split_text` (1200/150). **PR9.3**: aceita `card_fn` injetável e inclui `kind="data"` — arquivos de dados são indexados pelo **cartão de dados** (`core/data/datacard.card_for_path`), nunca pelas linhas cruas (vide Módulo Dados). `chat.answer()` monta contexto numerado `[n]` sob prompt estrito; **o `[n]` é chaveado pelo documento distinto** (chunks do mesmo arquivo compartilham número), então as citações nunca passam do total de fontes (antes numerava por chunk e citava `[5]`/`[6]` com 4 badges). `templates.py` (prompt library) · `batch.py` (1 prompt sobre N docs).
- **GUI** (`modules/ai/`): hub no AppBar, split form|painel, auto-contido. `form_view` — escopo, modelo (`gemma3-4b-custom` default → `gemma3-1b-custom` → `qwen7b-custom` → `gemini-2.5-flash`), chips de prompt. `worker` — `run_ai_index`/`run_ai_answer` em thread daemon (`module_id="ai"`). `view` — resposta em `ft.Markdown` com fontes clicáveis (badge `[n]` amarra ao `[n]` da resposta); status calculado **fora da UI thread** (`is_available()` faz ping no Ollama).
- **Persistência**: `last_ai_model`, `last_ai_scope`, `last_embed_model`, `last_ai_tab` (conversa|indice), `ai_answer_times` (janela móvel de durações por modelo) em `config.json`; índice em `~/.mill-tools/rag/`; prompts em `~/.mill-tools/prompts.json`.
- **CLI** (`cli/ai.py`): `ai index` · `ai stats` (resumo read-only) · `ai "pergunta"` · `--scope`/`--model`/`--k`/`--reindex`/`--batch [--kind]`. Embeddings sempre locais.
- **Gate**: `embedder.is_available()` bloqueia os fluxos com `SETUP_HINT`. Modelo CPU-pinned (`num_gpu 0`). **Quirk Ollama #10176**: configs que devolvem 8192 dims em vez de 768 → `_check_dim()` warning.

### Inspetor de índice + indexação por escolha (PR7.2)

- **`stats.py` (puro)**: `index_stats(directory) → IndexStats` (docs, chunks, dim, modelo, tamanho em disco, atualizado, `per_doc` ordenado por #chunks); `fmt_status_line()` → `"28 docs · 4.654 chunks · 20 jun 20:45"` (mês PT-BR manual, sem `locale`); `fmt_disk_size`/`fmt_thousands`/`fmt_datetime`/`chunks_for` (drill-down). `VectorStore.persist()` grava sidecar `index_info.json` (`embed_model`, `dim`); índices antigos → `embed_model="?"`.
- **Aba "Índice"** (`index_tab.py`): toggle `Conversa | Índice` (`visible=` num `Stack`). Cabeçalho global (`summary_card`) + tabela paginada por documento (`_PAGE_SIZE=120`) + drill-down de chunks num `AlertDialog` (lê `meta.json` via `chunks_for` fora da UI thread). `view::_refresh_status` passa o `IndexStats` a `index_tab.apply`.
- **Botão "Indexar no RAG"** (`index_button.py`): `rag_index_button(page)` nos painéis de resultado dos produtores (Transcrição, Documentos→analyze/extract/ocr, Receitas com saída textual). Dispara `run_ai_index` incremental numa thread com **bus de captura privado** (não usa pubsub → não interfere no módulo hospedeiro). Feedback inline + SnackBar; gate fora da UI thread. **Por escolha, nunca automática.**
- **Estimativa de tempo da resposta** (`timing.py`, puro/testado): a resposta é um `invoke()` bloqueante de comprimento desconhecido — **não há countdown honesto**. Em vez disso: cronômetro ao vivo + "tempo típico" da média móvel das últimas 5 respostas do modelo. `worker` emite `model_name`+`elapsed` no `answer_done`; `view` mostra `"Gerando resposta… 0:14 · ~28s (típico…)"` e grava em `ai_answer_times`. **O ticker roda no event loop da UI via `page.run_task` (async)** — um `control.update()` de thread daemon não repinta até o próximo `page.update()`. O `k` do RAG é fixo em 6 na GUI (CLI tem `--k`).

## Módulo Receitas (PR8)

Cadeias **lineares** nomeadas onde a saída de um passo alimenta o próximo, atravessando módulos (`URL → baixar áudio → transcrever → analisar`). Generaliza o `run_pipeline` da Transcrição. Sem dependência nova; reusa o core puro dos 5 módulos + `ai.answer`.

- **Core puro** (`core/recipes/`): `registry.py` — `STEP_REGISTRY: "module.op" → StepSpec(adapter, accepts, produces, label)`; **adaptadores finos** dão assinatura uniforme `adapter(inputs, params, ctx) → list[Path]` às funções de core heterogêneas (chamam o core puro, nunca o worker), gravam no dir canônico do módulo e normalizam os callbacks para `ctx.emit`. `runner.py` — `execute_recipe()` (valida, encadeia output→input, cancel entre passos, aborta no 1º erro; `emit_terminal` distingue run isolado de lote) + `execute_recipe_batch()`. `validate`/`inputs`/`presets` (5 embutidas)/`store`.
- **Casos sutis**: `transcription.format` reescreve in-place → devolve `[input_path]`; `transcription.transcribe` aceita áudio **e** vídeo → `[txt, *legendas]`; `video.subtitle` é o único **multi-input** (vídeo de `ctx.initial_inputs` + `.srt` de `ctx.outputs_by_op`); `ai.answer` reindexa, recupera com escopo no próprio arquivo, grava `.md` (exige `is_available()`).
- **GUI** (`modules/recipes/`): hub, auto-contido. Toggle **Rodar | Construir** (Construir: dropdown só oferece ops compatíveis com a saída anterior; reordenar por **↑/↓** — `ft.ReorderableListView` é scrollable frágil aninhado; validação ao vivo). `worker` roda `execute_recipe(_batch)` em thread; `clean_intermediates` apaga saídas não-finais.
- **CLI** (`cli/recipes.py`): `recipe list` / `recipe run "<nome>" <input>` (`--model` sobrescreve o Whisper). **Persistência**: `last_recipe`, `recipe_clean_intermediates`; receitas em `~/.mill-tools/recipes.json`.

## Módulo Dados (PR9)

6ª ferramenta na rail (transforma entrada→saída, como Documentos/Imagens — **não** é hub). Paradigma **query-first**: a composição (juntar+filtrar+agrupar+somar+ordenar) vive numa **consulta única**, escrita em português (traduzida pela IA) ou na mão. Motor **DuckDB** (in-process, torch-free). **Divisão de responsabilidades**: a IA recebe **só o schema** (nomes/tipos de coluna) e devolve `(sql, explicação)` — nunca toca nas linhas; o DuckDB abre os arquivos e executa; o core orquestra. **Privacidade**: com Gemini, só os nomes de coluna saem da máquina.

- **Core puro** (`core/data/`): `engine.py` é a **única fronteira com o DuckDB** (injetável, como o `embedder` do RAG) — conexão **in-memory efêmera** por consulta (nada gravável anexado), detecta encoding de CSV via `charset-normalizer` (cp1252/utf-8/utf-16 → encodings do DuckDB; exóticos → latin-1), registra cada arquivo como view, `run_query`/`export_query`/`convert_file` (`COPY ... TO`); **`preview(path, limit, offset, sheet)`** lê uma janela direto do arquivo (sem registrar view) e **`xlsx_sheet_names`** enumera abas via `zipfile`+`workbook.xml` (stdlib, sem dep nova); `reader_expr` aceita `sheet=` p/ XLSX. `validate.py` — guarda: só leitura (SELECT/WITH/FROM/DESCRIBE/SUMMARIZE), rejeita COPY/ATTACH/INSTALL/PRAGMA/DML e múltiplos statements (strip de comentários antes). `nl2sql.py` — `to_sql(schema, pergunta)` via `make_llm`; saída sempre validada por `ensure_select`. `scanner.py` — `scan_file → DataFile` (view name, contagem, colunas) + `schema_text` p/ a IA. `convert.py` — CSV/TSV/JSON/Parquet/XLSX + `rename_sql` (renomeia colunas no output, puro). `profile.py` — relatório textual (`SUMMARIZE`, **amostrado via `USING SAMPLE` acima de 200k linhas** — `summarize_sql` puro); `profile_text` em memória. `assess.py` (PR9.3) — **avaliação de qualidade pela IA** (prompt de responsabilidade única estilo `src/analysis`; recebe só esquema+`SUMMARIZE`+amostra, nunca as linhas); cache em `~/.mill-tools/data_assessments.json` keyed por `(path, mtime)`. `datacard.py` (PR9.3) — **cartão de dados** indexável (`build_data_card` puro = schema+perfil+amostra+avaliação cacheada; `card_for_path` orquestra). `store.py` — `queries.json`.
- **GUI** (`modules/data/`): rail tool, auto-contido (`module_id="data"`), split form|painel. `form_view` — fontes (FilePicker → chips com contagem de linhas/colunas + **olho** que abre o modal de prévia) + toggle **Português | Consulta** + caixa + Pré-visualizar/Executar. `worker` — `scan`/`translate`/`query`/`save` em threads daemon. `view` — cartão de revisão **"entendi assim"** (SQL editável), prévia **paginada** em `DataTable` (`_PAGE_SIZE=50`, no máx `PREVIEW_ROWS=200` em memória), **personalizar retorno** (renomear colunas, formato, Salvar/Conversar sobre/Salvar como Receita/**Indexar no RAG**). `table_view.py` (PR9.3) — **componente de tabela paginada reutilizável** (cabeçalho mostra o tipo por coluna). `preview_modal.py` (PR9.3) — `AlertDialog` com olho→prévia: 2 abas manuais (Prévia | Avaliação da IA), seletor de aba XLSX; leituras DuckDB e o `invoke()` da IA via `asyncio.to_thread` dentro de `page.run_task` (fora da UI thread, repintura correta).
- **CLI** (`cli/data.py`): `data query <arquivos...> "<pergunta>" [--sql] [--out csv|xlsx|json|parquet] [--name] [--limit]`, `data convert`, `data profile`, `data assess <arquivo> [--model] [--no-cache]` (PR9.3, parecer da IA + cache). Reusa o core direto (como `ai`/`library`, sem `CLIEventBus`); stdout em UTF-8.
- **Integrações**: Receitas — `data.query` (multi-input, consome a lista inteira; `sql` ou `question` nos params; produz KIND_TEXT p/ fechar `data.query → ai.answer`), `data.convert`, `data.profile` (novo `KIND_DATA`). Biblioteca — `output/data/ → kind="data"`; ícone de tabela; filtro "Dados"; bridge "Consultar nos Dados". **RAG (PR9.3)** — o `indexer.build_index` aceita `card_fn` injetável: itens `kind="data"` são indexados pelo **cartão de dados** (`card_for_path`), nunca pelas linhas cruas; `indexable_items` inclui `kind="data"` (casa por kind). `run_ai_index`/CLI `ai index` passam o `card_fn`.
- **Persistência**: `last_data_model`/`last_data_format`/`last_data_mode`; saídas em `output/data/`; consultas em `~/.mill-tools/queries.json`; avaliações em `~/.mill-tools/data_assessments.json`. **XLSX** isolado em `convert.py`/`engine.py` (extensão `excel` do DuckDB carregada sob demanda; degrada com erro claro se faltar).

## Cookies do YouTube (anti-bot)

Mitiga o gate anti-bot intermitente passando cookies de um navegador logado (`cookiesfrombrowser`). Lógica isolada em `core/ytdlp_cookies.py` (puro), reusada por **todos** os call sites.

- **Ponto único**: `cookie_ydl_opts() -> dict` é mesclado nas 3 funções core do yt-dlp (`audio/downloader`, `video/downloader`, `metadata`) — cobre Áudio/Vídeo/Transcrição/Receitas/CLI sem propagar parâmetro. **Nunca levanta** (try/except → `{}`).
- **Zen Browser**: o yt-dlp não conhece "zen" → mapeia `("firefox", <path do perfil Zen>, None, None)`; perfil resolvido do `profiles.ini` (`%APPDATA%\zen`).
- **Config** (core lê direto, sem `gui.settings`): env `MILL_YT_COOKIES_*` → `config.json`. Default `"none"` — **opt-in** (lê sessão logada, sensível). GUI: diálogo de Configurações (engrenagem no AppBar).
- **Limitação — PO Token / SABR** (validado jun/2026): cookies passam o gate anti-bot, mas cookies de **conta logada** fazem o YouTube exigir **PO Token**; sem ele o yt-dlp recebe só *storyboards* (`sb0-3`) → **`Requested format is not available`** (todos os vídeos). Por isso o default é `none`: cookies de conta costumam **atrapalhar**. Armadilha: sem cookies → gate anti-bot; com cookies → PO Token. Fix durável (provider `bgutil-ytdlp-pot-provider`) **não implementado** (exige Node/Deno — contra a leveza). Mitigações sem código: baixar sem cookies + retry, yt-dlp atualizado. Diagnóstico: `extract_info(..., process=False)` e comparar `formats` com/sem cookies.

## Splash + Home Screen + branding

Fluxo: `show_splash` → `show_home` → `build_app(initial_module)` (`splash.py`/`home.py`/`app.py`).

- **Home** (`home.py`): 6 ferramentas (grade 3 por linha, `_tool_row` paga as sobras com spacers) + 3 hubs sobre o moinho girando. Cards **crescer-no-hover**: cada card é **um único `GestureDetector`** (tap + `on_enter`/`on_exit`) sobre um `Container` animado (sem `ink=True`); cresce no hover e revela o detalhe; reflow sem fixar altura das `Row` (só um card hovered por vez → cabe sem scroll). **Crítico**: `Container.on_hover` não dispara quando coberto — usar o `on_enter`/`on_exit` do próprio GD (ver tabela de quirks).
- **AppBar** (`app.py`): wordmark + botões-hub Biblioteca/IA/Receitas (dourados quando ativos); Home/Splash/tema em `actions` (bloqueados se pipeline rodando). `page.pubsub.unsubscribe_all()` no início de `build_app` evita acúmulo de subscribers.
- **Spinner**: cata-vento, giro encadeado via `on_animation_end` (LINEAR). **Assets** (`assets.py`): `b64(name)` → bytes; `WINDOW_ICON`.

## Comandos

```bash
uv run gui.py                                          # GUI desktop
uv run main.py <URL>                                   # Transcrição básica (legado)
uv run main.py transcribe <URL|file.mp4|notas.txt> --format --analyze --profile lecture
uv run main.py audio   <URL_OR_FILE> [--fmt mp3] [--quality 320] [--denoise] [--normalize]
uv run main.py video   <download|convert|trim|compress|resize|extract-audio|thumbnail|subtitle> <input> [opções]
uv run main.py image   <convert|resize|crop|rotate|watermark|border|adjust|filter|favicon|contact-sheet|remove-bg|describe> <input> [opções]
uv run main.py document <merge|split|compress|rotate|watermark|stamp|encrypt|extract|ocr|pdf-to-images|images-to-pdf|qr> <input> [opções]
uv run main.py library list [--kind audio|data] [--since 7d] [--sort size]
uv run main.py ai index | ai stats | ai "pergunta" [--scope X] [--model gemini-2.5-flash] [--k 8] [--batch]
uv run main.py recipe list | recipe run "<nome>" <URL_OR_FILE> [--model medium]
uv run main.py data   query <arquivos...> "<pergunta>" [--sql] [--out csv|xlsx|json|parquet] [--name] [--limit]
uv run main.py data   convert <arquivo> [--out parquet] | data profile <arquivo> | data assess <arquivo> [--model] [--no-cache]
```

> Referência completa de flags → skill `cli` (`.claude/skills/cli/SKILL.md`).

## Convenções de código

- **Idioma do código**: docstrings, logs, comentários e strings internas em **inglês**. Português **só** em labels/textos visíveis da GUI. Há inconsistências históricas — ao tocar um arquivo, corrigir PT→EN em docstrings/logs na mesma passagem.
- Docstrings em todas as funções/módulos. Logging via handler dedicado — **nunca `print()`** para logs.
- **Core (`src/core/`) é puro**: sem Flet, reutilizável por CLI e GUI.
- **`subprocess` sempre em modo binário** (`Popen`/`run` sem `text=True`); decodificar manualmente com `.decode('utf-8', errors='replace')`. Em Windows `text=True` herda cp1252 → `UnicodeDecodeError` em saídas UTF-8 do ffmpeg/ffprobe.
- Linter: **ruff** · Testes: **pytest** (rodar `uv run pytest -m unit` antes de qualquer commit).

## Testes

- **Marcadores**: `unit` (Python puro, sem ffmpeg/rede/GPU) · `integration` (requer ffmpeg; pulado automaticamente se ausente via `pytest_collection_modifyitems`).
- **Regra**: `uv run pytest -m unit` verde antes de commitar. Cobertura sobre `src/` (branch on), excluindo `src/gui/` (Flet não testável headless). Agregado ~88%.
- **Plugins**: pytest-randomly (ordem aleatória — `--randomly-seed=NNN` reproduz), pytest-timeout (60s default), pytest-xdist (`-n auto`), pytest-clarity.
- **Estrutura** espelha `src/`; fixtures em `conftest.py` (function: `jpg_image`/`png_image`/`out_dir`; session: `sample_wav/mp3/mp4/wav_stereo`, `session_jpg`, `sample_pdf`, `sample_pdf_with_images`). Mocks de LLM via `GenericFakeChatModel`; RAG/Receitas via `embed_fn`/`STEP_REGISTRY` injetados.

> Guia completo (estrutura, mocks, cobertura por módulo) → skill `testing` (`.claude/skills/testing/SKILL.md`).

## Dependências externas (PATH)

- `yt-dlp`, `ffmpeg`/`ffprobe` — verificados em runtime por `check_dependencies()`.
- **Tesseract** (opcional, OCR) — extra `[ocr]` + binário com packs `por`/`eng`; resolvido no PATH ou em `C:\Program Files\Tesseract-OCR`.

## LLM pipeline (Formatter / Analyzer / Prompter)

- **Chunking** (`llm_utils.split_text`): formatter usa separadores por frase; analyzer/prompter os padrão. **Bypass de contexto longo** (`bypass_long_context=True` em analyzer/prompter): Gemini (1M) pula chunking sempre; locais conhecidos pulam **até um teto de chars** — `llm_factory.LONG_CONTEXT_LOCAL_BUDGETS` (`gemma3-4b-custom`: 12000 chars ≈ 3K tokens), bem abaixo do `num_ctx`. Acima do teto, volta a fatiar.
- **`num_ctx`** (`llm_factory.DEFAULT_OLLAMA_NUM_CTX = 8192`): o Ollama usa 2048 por padrão — pequeno demais p/ o JSON verboso (truncava → JSON inválido). `make_llm`/`_make_ollama` passam `num_ctx` ao `ChatOllama` por requisição (vence o slider do app Ollama, que é o nível mais baixo de precedência). `analyzer._invoke_and_parse` tenta o parse 1× extra antes de propagar erro.
- **Formatter** (`phi4mini-custom`, 4500/150) · **Analyzer** (`gemma3-4b-custom` local / GUI default `gemini-2.5-flash`; 4500/300, **perfil-dirigido** via `src/analysis/`) · **Prompter** (`gemma3-4b-custom`; 4500/200, ~40% compressão, remove CTAs).
- **Perfis de análise** (`src/analysis/`, puro): `build_*_prompt` **escapam chaves literais** `{`→`{{` p/ o `ChatPromptTemplate`; `format_report` despacha por `kind`. Catálogo em `profiles/` por grupo; adicionar perfil = uma entrada. Selecionável via CLI `--profile`, seletor GUI e param do passo `transcription.analyze`.

## Métricas de qualidade de transcrição

`transcriber.py` sinaliza segmentos com `[?]`: `avg_logprob < -1.0` (tokens incertos) ou `no_speech_prob > 0.6` (silêncio/ruído).

## Ollama

Modelos custom CPU-pinned (`num_gpu 0`); Modelfiles minimalistas (sem `SYSTEM`/`temperature` — `make_llm` define a temperatura por papel).

- **qwen7b-custom**: Qwen 2.5 7B — análise/RAG de máxima qualidade; lento na CPU (`ollama/Modelfile`).
- **phi4mini-custom**: Phi-4 Mini 3.8B — `--format` (`Modelfile.phi4mini`).
- **gemma3-4b-custom**: Gemma 3 4B (128K ctx) — **default da resposta de RAG e do Analyzer/Prompter local**; sintetiza e cita `[n]` muito melhor que o 1B (~3,3 GB). Setup: `ollama pull gemma3:4b && ollama create gemma3-4b-custom -f ollama/Modelfile.gemma3-4b`.
- **gemma3-1b-custom**: Gemma 3 1B (32K) — fallback rápido/baixa-RAM (~815 MB); fraco em síntese.
- **moondream-custom**: vision — descrição de imagens (`Modelfile.vision`).
- **nomic-embed-custom**: embeddings do RAG — 768-dim, CPU, torch-free. Setup: `ollama pull nomic-embed-text && ollama create nomic-embed-custom -f ollama/Modelfile.nomic`. Alternativas multilíngues (1024-dim, exigem reindexação): `bge-m3`, `mxbai-embed-large`.

## GUI Desktop (Flet 0.85)

`uv run gui.py` (Flutter desktop no Windows). **EventBus** (`events.py`) publica `PipelineEvent(type, stage, payload, module_id)` via `page.pubsub.send_all()` (thread-safe). `LogEventHandler` captura `logging.INFO` → eventos `log` (com `_SUPPRESSED_PREFIXES`). Design System, **tabelas de evento, barra de progresso e thread-safety** → skill `design-system` (`.claude/skills/design-system/SKILL.md`).

### Flet 0.85 — quirks críticos

| Armadilha | Correto |
|---|---|
| `ft.Audio` | **não existe** — usar `sounddevice` + ffmpeg (`audio_player.py`) |
| `ft.ImageFit` | usar `ft.BoxFit` |
| `ft.Tabs`/`ft.Tab` | abas manuais: `TextButton` + `visible=` |
| `ft.Colors.SURFACE_VARIANT` / `SURFACE_CONTAINER` | não existem no 0.85 — usar `ft.Colors.SURFACE` ou `Color.dark.surface_variant` |
| `surface_container_*` no `ColorScheme(...)` | kwarg inválido → `TypeError`; suportados: `surface`, `on_surface`, `on_surface_variant`, `outline`, `outline_variant` |
| trocar `Container.content` em runtime | reatribuir árvore quebra o patcher → toggle `visible` num `ft.Stack` |
| `page.update()` em cascata | causa `IndexError` no `object_patch` — um update por evento |
| `ink=True` em Container clicável | absorve eventos de ponteiro, anula cursor do `GestureDetector` externo — nunca usar; handler em `GestureDetector.on_tap` |
| `ft.Slider` programático | setar `.value` + `update()` **não** dispara `on_change`; usar `on_change_end` para seek |
| `ft.Dropdown` evento de seleção | **não** aceita `on_change` no construtor (0.85.2) — usar `on_select` (campos válidos: `on_select`, `on_text_change`) |
| `control.page` antes do mount | lança `RuntimeError` — proteger com `try/except RuntimeError` |
| FilePicker | `page.services.append(picker)` + `await picker.pick_files(...)` |
| `Container(box_shadow=...)` | usar `Container(shadow=ft.BoxShadow(...))` — sem prefixo `box_` |
| `ft.NavigationRailDestination` cursor | sem `mouse_cursor` — envolver o `NavigationRail` em `GestureDetector` |
| `ft.Image.src` tipo | aceita `Union[str, bytes]` no 0.85 — bytes PNG direto, sem base64 |
| `ft.Image` updates frequentes | `gapless_playback=True` mantém o frame anterior visível — evita flicker (cursor de waveform) |
| `Container.on_hover` coberto | **não dispara** quando o Container é totalmente coberto por outra região de mouse. Para hover **e** tap no mesmo card, usar **um único** `ft.GestureDetector` com `on_enter`/`on_exit` (+ `on_tap`) — ver `home.py` |
| `control.update()` de thread daemon | **não repinta** até o próximo `page.update()` da UI thread — um cronômetro/ticker em `threading.Thread` parece travado. Para atualização periódica viva, rodar no event loop da UI via `page.run_task` (corotina async com `await asyncio.sleep`) — ver `ai/view.py`, `home.py`, `library.py` |

### Modelos nos dropdowns de Transcrição

| Campo | Opções |
|---|---|
| Formatação | `phi4mini-custom`, `qwen7b-custom` |
| Análise / Prompt-ready | `gemini-2.5-flash`, `gemma3-4b-custom`, `qwen7b-custom` |

> `gemma3-4b-custom` é o meio-termo local (mais rápido que o `qwen7b-custom` na CPU, 128K ctx) para Análise/Prompt-ready. Fora da Formatação (o `phi4mini-custom` ocupa o slot pequeno e a formatação exige preservar texto verbatim).

### GPU — sobrecarga e estabilidade (MX150 / Pascal)

Flet (DirectX) e Whisper (CUDA) disputam a MX150 — uso simultâneo pode causar BSOD `WIN32K_POWER_WATCHDOG_TIMEOUT`. Mitigações: `LogEventHandler` em INFO; libs ruidosas capadas em WARNING; fila de áudio sequencial. Se persistir: forçar `python.exe` em "Economia de energia" (iGPU Intel) nas configs de gráficos do Windows.

## Hardware de desenvolvimento

Dell Inspiron 7580 — i5-8265U, 16GB RAM · NVIDIA MX150 (2GB VRAM), CUDA 12.6 · compute `int8_float32` (Pascal) · throttling gerenciado pelo EC Dell (~63-65°C) · Windows 10 Home.

## Roadmap

Histórico detalhado em `docs/ROADMAP_*.md` e `docs/STATUS_TIER0.md`.

- **PR5 / PR5.1** ✅ — Módulo Documentos (13 ops GUI / 12 CLI) + OCR híbrido via pytesseract.
- **Tier 0** ✅ — Legendas SRT/VTT, legenda no vídeo (mux/burn), OCR.
- **PR6 / PR6.6** ✅ — Módulo Biblioteca (índice de `output/`, grade+lista, bridges, visor in-app) + entrada flexível de análise (texto/vídeo local).
- **PR7** ✅ — Módulo IA / RAG local (core `src/core/rag/`, GUI hub, CLI `ai`).
- **PR8** ✅ — Módulo Receitas / Automação (core `src/core/recipes/`, GUI Rodar|Construir, CLI `recipe`).
- **PR7.2** ✅ — Inspetor de índice + `ai stats` + indexação por escolha + ETA da Transcrição + estimativa de tempo da resposta.
- **PR9** ✅ — Módulo Dados / query-first sobre DuckDB (core `src/core/data/`, GUI 6ª ferramenta, CLI `data`, PT→SQL pela IA, integração Receitas/Biblioteca).
- **PR9.3** ✅ — Prévia visual da fonte (modal olho→tabela paginada + tipos por coluna, seletor de aba XLSX), avaliação de qualidade pela IA (`assess.py` + cache) e **indexação dos 5 formatos no RAG** via cartão de dados (`datacard.py`, `card_fn` no indexer). CLI `data assess`.
- **PR9.1** — Gráficos (`plot`) via `matplotlib` (extra `[data-plot]`).
- **PR9.2** — Encadeamento em estágios (resultado vira nova fonte).
- **PR3.1-B** — IA de áudio com torch (extra `[ai-audio]`): DeepFilterNet, Demucs (a avaliar).
- **Futuro** — Imagens (batch rename, upscale); arrastar arquivos do SO (não nativo no Flet).
