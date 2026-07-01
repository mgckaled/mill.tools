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
- **polars/pandas/pyarrow** (extra opcional `[analysis]`, Plano 0) — camada de DataFrame sobre o resultado do DuckDB (`core/data/frames.py`), handoff **Arrow zero-copy**, torch-free; carregada só quando um consumidor (gráficos/ML, Planos 1+ do `docs/ROADMAP_ML_DADOS.md`) a aciona
- **matplotlib** (extra opcional `[data-plot]`, Plano 1) — única fronteira de plotagem (`core/data/charts.py`), render off-thread (`Figure`+`FigureCanvasAgg`, sem `pyplot`) → bytes PNG; consome a camada do Plano 0 (`frames.to_pandas`)
- **scikit-learn** (extra opcional `[ml]` ≥1.4, Planos 3/4A) — ML clássico **torch-free**: clustering (HDBSCAN/k-means), projeção 2D (PCA), c-TF-IDF (`CountVectorizer`). O acessor de embeddings (`features.py`), `dedup.py` e `recommend.py` são **numpy-puros** e não exigem o extra; `joblib` (persistência de modelos versionada) vem transitivo
- **umap-learn** (extra opcional `[ml-viz]`, Plano 4A) — projeção 2D alternativa (melhor que PCA) do mapa semântico; puxa `numba` → opt-in. PCA é o default sem dep nova
- **yake** + **spacy** (extra opcional `[nlp]`, Plano 4B) — NLP textual **torch-free**: keyphrases (YAKE, estatístico) e NER (spaCy CNN `pt_core_news_sm`, **nunca `_trf`** que puxaria torch). O resumo extractivo (`summarize.py`) é **self-contained** sobre o `TfidfVectorizer` do `[ml]` (sem dep nova, sem download nltk). Classificação de perfil é numpy + `[ml]` (sem dep nova). O **modelo spaCy** é download à parte (como o Tesseract)

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
│   ├── library/                — types.py (LibraryItem) · scanner.py (filter_items aceita tag_index) · thumbnails.py · analytics.py (Plano 2) · tags.py (auto-tags por keyphrase, cache, Plano 4B)
│   ├── rag/                    — types · embedder (única rede) · store (VectorStore) · indexer · retriever · chat · templates · batch · stats · analytics (Plano 2)
│   ├── recipes/                — types · registry · runner · validate · inputs · presets · store · history (Plano 2)
│   ├── data/                   — types · scanner · engine (única fronteira DuckDB; preview/abas XLSX) · nl2sql · validate · convert · profile · assess (qualidade IA) · datacard (cartão indexável) · store
│   ├── ml/                      — types · features (acessor de embeddings, numpy-puro: pool do VectorStore) · dedup · recommend (related/in_corpus, numpy, reranking por **MMR**) · deps (gate [ml]/[ml-viz]) · store (modelos versionados) · cluster (HDBSCAN/k-means, **k-means aceita `k=None` → auto-seleção por `silhouette_score` acima de 20 documentos**) · labeling (c-TF-IDF, `ngram_range=(1,3)` + `reduce_frequent_words`) · project (PCA/**TSNE**/UMAP 2D) · cache (mapa versionado) · mapviz (SemanticMap→PNG) · classify (perfil zero-shot/supervisionado, Plano 4B) (Planos 3/4A/4B; refinamentos em `docs/plan/PLANO_REFINAMENTO_ML_TEXTO_RAG.md`)
│   └── text/                    — NLP textual puro (Plano 4B): keywords (YAKE) · summarize (TextRank self-contained sobre TfidfVectorizer) · entities (spaCy NER CNN) · reader (corpo do doc, header-strip) · lang (heurística PT/EN). Cada motor gated; independente de core/ml
└── gui/
    ├── app.py (build_app: rail + hubs) · splash.py · home.py · events.py · settings.py · settings_dialog.py · workers.py · help_content.py
    ├── components/             — input_source.py · profile_selector.py · audio_player.py
    ├── modules/                — base.py (Module) · _pipeline_runner.py · _charts.py (helper de gráfico dos painéis, Plano 2) + 1 pasta/módulo (form_view/worker/view/pipeline_log; image+document têm blocks/)
    ├── theme/                  — theme.py · tokens.py · components/ (factories + Cursor + sliders)
    └── views/                  — form_view (Transcrição) · progress_view (ProgressPanel) · result_view · file_viewer (visor .md/.txt)
```

> Responsabilidade de cada arquivo é derivável do código. **Arquitetura/estrutura, camadas, limites de tamanho/coesão e padrões de decomposição (`blocks/`/`tabs/`/`registry/<módulo>`) → skill `architecture`** (orquestra as demais; usar ao criar módulos, dividir arquivos grandes ou implementar planos do roadmap); detalhe da CLI → skill `cli`; do design system / eventos de GUI → skill `design-system`; de testes → skill `testing`.

## Sistema de módulos (GUI)

- **6 ferramentas** (Áudio→Vídeo→Imagens→Transcrição→Documentos→Dados) na **NavigationRail**. **Biblioteca/IA/Receitas** são **hubs** fora da rail (operam sobre as saídas de todos) — botões dourados no AppBar. Os 3 ainda estão em `MODULES`/`ft.Stack`; `_RAIL_MODULES` exclui os `_HUB_IDS`.
- **Registry** (`app.py`): `MODULES: list[Module]` é fonte única — adicionar módulo = uma entrada. **Module** (`modules/base.py`): dataclass `id/label/icon/selected_icon/control/on_mount(payload)/on_unmount`; o `control` é construído uma vez (trocar de aba não destrói estado).
- **navigate_to(module_id, payload)**: alterna **visibilidade** num `ft.Stack` (não reatribui `content` — evita `object_patch` IndexError do Flet 0.85). Bloqueia troca enquanto `pipeline_running[0]`.
- **Entrada via Home Screen** (`home.py`): 6 ferramentas (grade 3 por linha = 3+3) + 3 hubs (cards largos, borda dourada, selo "HUB") sobre o moinho girando. Clique → `build_app(initial_module=id)`.
- **Bridges** (`navigate_to(target, {"file": path})` → `on_mount` chama `fill_from_path`/`bind_document`): Áudio/Vídeo/Biblioteca→Transcrição; Vídeo→Transcrição/Áudio (botões pós-`extract_audio`); Biblioteca→IA ("Conversar sobre", fixa escopo do documento).
- **Escopo de eventos**: cada `ProgressPanel` tem `owner_id` e ignora `module_id` diferente; IA e Receitas são auto-contidos (assinam os próprios eventos).

## Módulo Transcrição

Whisper + pipeline de IA (Formatação/Análise/Prompt-ready). `InputSource` único aceitando **URL**, **áudio/vídeo local** e **texto** (`.txt`/`.md`).

- **Formulário adaptativo** (`views/form_view.py`): texto → esconde a seção de transcrição (modelo/idioma/beam/legendas) e mantém só as etapas de IA; mídia/URL → mostra tudo. Fatiado (Plano 4B): helpers de `.env` em `views/form_env.py`; seção de perfil em `views/profile_section.py`.
- **Auto-sugestão de perfil (Plano 4B)**: ao selecionar um texto já indexado, `profile_section.suggest` classifica off-thread (`classify`) e **pré-seleciona** o perfil com um chip "Sugerido: Aula · 0,82" (margem baixa → "Sugestão incerta"); guardado (sem índice/embedder → no-op). A escolha final do usuário é gravada como rótulo de ouro pelo worker (`record_label` após `analyze`) — alimenta o upgrade supervisionado. **Insights textuais**: aba "Insights" no `result_view` (`views/insights_panel.py`) com keyphrases/resumo/entidades do documento, computados off-thread só na 1ª abertura, cada motor gated.
- **Worker** (`gui/workers.py::run_pipeline`): **texto** → copia p/ `output/transcriptions/text/` (nunca edita o original — o `formatter` reescreve in-place), pula Whisper, roda só IA (**guarda**: exige ≥1 análise); **áudio/vídeo local** → transcreve (faster-whisper decodifica vídeo via PyAV, sem extração); **URL** → metadata + download + transcrição. `format/analyze/prompt` são compartilhados.
- **ETA (PR7.2.5)**: rótulo abaixo da última linha mostra tempo restante + fator de velocidade (`"≈ 3m 00s restantes · 0,85× tempo-real"`). `transcription/pipeline_log.format_eta(elapsed, end, audio_duration)` (puro/testado) = média móvel; só após **5%** transcrito (início ruidoso). `progress_view.py` captura `t0` em `transcribe_started`, atualiza por `transcribe_segment`, esconde nos estados terminais.

## Módulo Áudio

- Auto-detecta: URL → download; vídeo local → extração; áudio local → conversão. Formatos `best`/mp3/m4a/wav/ogg/opus + bitrate; `best` sem reencode. Capa/metadados embutidos por padrão (fallback em ogg/opus). Fila sequencial.
- **Saída**: downloads → `output/audio/source/`; processados → `output/audio/processed/`.
- **Toggle `Converter | Visualizar`** (`view.py`, padrão `Edição|Descrição IA` do módulo Imagens): abas manuais `visible=` num `ft.Stack`, troca bloqueada durante o pipeline. **Aba Converter** = fluxo áudio→áudio (form + player + progress); **aba Visualizar** (`visualize_tab.py`) = áudio→imagem.
- **Reprodutor embutido** (`components/audio_player.py`): aparece após o pipeline; sounddevice; seek por clique no waveform. **Waveform — 2 threads de decode**: rápido a 500 Hz mono (exibir) + completo 44100 estéreo (playback); `_load_generation` descarta cargas antigas; `gapless_playback=True` evita flicker. **Loop de atualização do cursor roda na UI event loop via `page.run_task`** (não thread daemon): um `page.update()` de thread daemon só repinta no próximo update da UI thread → o cursor atrasava em relação ao áudio. **Seletor A/B `Original | Processado`** (`set_compare`, compacto): só aparece quando há original+processado; troca a fonte reusando o mesmo motor/waveform (sem segundo render ao vivo).
- **Aba Visualizar** (`visualize_tab.py`, áudio→imagem): fonte | imagem; `core/audio/visualize.py` gera waveform/espectrograma PNG estático via ffmpeg (`showwavespic`/`showspectrumpic`, `-frames:v 1`) **off-thread** (`page.run_task` + `asyncio.to_thread`), exibido num `ft.Image` (sem cursor/tick — caminho separado do waveform ao vivo). Saída em `output/audio/processed/<stem>_waveform.png|_spectrogram.png` (indexável pela Biblioteca); bridge "Abrir no módulo Imagens". **Mini-log** com cronômetro ao vivo + tempo típico (média móvel por tipo em `audio_viz_times`, reusa `ai/timing.py`).
- **Pós-processamento** (switches encadeáveis, ordem fixa **silêncio → denoise → velocidade → normalize → encode final**): `silence.py` (remoção de silêncio início/fim/meio via `silenceremove`, `stop_periods=-1`; `build_filtergraph` puro); `denoiser.py` (spectral gating noisereduce, modo `stationary` constante/adaptativo exposto na GUI, salva WAV preservando subtype PCM via `sf.info`+`subtype`); `speed.py` (`atempo` sem alterar pitch, `_atempo_chain` puro encadeia estágios p/ respeitar a faixa 0.5–2.0 por estágio, fator 0.5–4.0×); `normalizer.py` (loudnorm 2 passes, alvo −23..−6 LUFS default −14, True Peak ≤ −1 dBFS, retorna `(path, stats)`).
- **Encode final** (`worker`, op `encode`): conserta o denoise que sempre gravava `.wav` — a cadeia termina num `convert_audio` único para `args.fmt` que também aplica **downmix mono** (`-ac`) e **sample-rate** (`-ar`); só roda se o formato mudou ou se mono/taxa foram pedidos (downloads `best` sem resample não reencodam). `convert_audio` lida com transformação in-place (mp3→mp3 mono) via temp file + `shutil.move`.
- **Resultado** (`view.py`): o `audio_op_done` expõe `source_path` (arquivo pré-pós-processamento → A/B) e `loudness_stats`/`loudness_target` (quando há normalize). `view.py` captura esses payloads por uma assinatura própria do bus (keyed por `output_path`), aciona `player.set_compare` e mostra um **card de loudness** medido vs. alvo (`fmt_loudness_card`, puro/PT-BR: `−19,2 → −14,0 LUFS · TP … · LRA …`).
- **Formulário** (`form_view.py` + `blocks/`): fatiado em `blocks/` (`output` formato/bitrate/**canais+taxa** · `denoise` switch+modo · `silence` · `speed` · `normalize` · `presets`). **Presets de uma tecla** (`blocks/presets.py`): "Pronto p/ transcrição" (mono+16 kHz+denoise+silêncio), "Podcast" (denoise+silêncio+−16 LUFS), "Arquivo musical" (preserva tudo, sem normalizar) — chamam setters dos refs dos blocos. `segmented_selector` ganhou `with_setter` (retorna `set_value` programático, retrocompatível) p/ os presets pré-selecionarem canais/taxa.
- **Quirk Windows (downloader)**: `FFmpegExtractAudio` cria `.temp.<ext>` **no dir do arquivo de entrada** (hardcoded; `paths={"temp"}` não resolve). Solução: rodar download+pós em `tempfile.mkdtemp()` e mover o final via `shutil.move`.

## Módulo Vídeo

Download/conversão/processamento via yt-dlp + ffmpeg. 8 operações (download/convert/trim/compress/resize/extract_audio/thumbnail/subtitle). `core/video/converter.py` delega a `run_ffmpeg`. **Saída**: `output/video/source/` (download) · `output/video/processed/`.

- **Legenda** (`add_subtitles`): `soft` (mux) = `-c copy -c:s mov_text` (sem reencode); `hard` (burn-in) = `-vf subtitles=…` + libx264 (reencoda). Saída `<stem>_subbed.mp4`.
- **Quirk Windows — nunca usar `FFmpegVideoConvertor`** (qualquer formato): cria `.temp.<ext>` no dir de saída e o Defender bloqueia o rename (`[WinError 32]`). Usar só `merge_output_format` + `nopart=True`, `overwrites=True`, `paths={"temp": tempfile.gettempdir()}`. Fix durável: excluir `output/` do Defender.
- **Progresso yt-dlp**: `_percent_str`/`_speed_str`/`_eta_str` têm ANSI — strip antes de exibir (`re.sub(r'\x1b\[[0-9;]*m', '', s)`).
- **Quirk burn-in**: o filtro `subtitles` interpreta `:` como separador → o `:` do drive (`C:`) quebra o parser. Solução: rodar ffmpeg com `cwd` na pasta da legenda e referenciá-la por **basename** (`run_ffmpeg` aceita `cwd=`). Mux soft não usa filtro, dispensa `cwd`.

## Módulo Imagens

Conversão/manipulação + IA, com visor Before/After. **Toggle "Edição | Descrição IA"** no topo do módulo (abas manuais `visible=` num `Stack`): a Edição tem 12 operações imagem→{imagem|texto} (convert/resize/crop/rotate/watermark/border/adjust/filter/favicon/contact_sheet/remove_bg/**ocr**); a **Descrição IA** (`describe_tab.py`) isola o `describe` (imagem→texto) — fonte | descrição em `ft.Markdown` (ícone de copiar), reusa `build_ai_blocks` e o worker compartilhado (`operation="describe"`). `core/image/transform.py` = funções puras Pillow; `background.py` (rembg + **background replacement**, extra `[ai-image]`); `describe.py` (Ollama vision → `.txt`, `num_ctx=8192`; dropdown inclui `gemma3-4b-custom`); `exif.py`/`smart_crop.py`/`filter_previews.py`/`ocr.py` (puros).

- **GUI** (`form_view.py` + `blocks/`): formulário quebrado em blocos `build_X_block(page) → (ft.Column, XRefs)`. Cards `remove_bg`/`ocr` desabilitam com tooltip quando o extra falta (padrão **`_UNAVAILABLE`**). Botão **"Ver info"** (seção Entrada) abre diálogo com dimensões/modo/EXIF (`info.image_info` + `exif.read_summary`). **Quirk Flet 0.85.2**: `page.open` não existe — usar `page.show_dialog(...)` p/ diálogos **e** SnackBars (SnackBar é `DialogControl`); fechar = `page.pop_dialog()`.
- **Visor Before/After** (`preview.py`, extraído de `view.py`): **fundo xadrez** atrás do "Depois" quando a saída tem alfa (`out_mode` RGBA/LA — torna a transparência legível); **faixa de metadados** antes→depois (`fmt_meta_strip`, payload `out_w/out_h/out_mode/out_fmt`); **tira de miniaturas** navegável no lote (`add_batch_item`). Ações no rodapé: "Abrir arquivo", **"Criar PDF"** (`images_to_pdf` sobre as saídas do run), bridge "Ver na Biblioteca" (`view.py` recebe `nav`).
- **EXIF** (`exif.py`): `preserve | strip | strip_gps | inject` como **pós-processo aditivo** na saída (não toca a assinatura das transforms); JPEG re-salva com `quality="keep"`; zera Orientation (transforms já fazem `exif_transpose`); seção fixa (`blocks/exif.py`). CLI `image exif`.
- **Smart crop** (`smart_crop.py::focal_crop_box`, puro): modo `focal` do crop — recorta p/ uma proporção alvo mantendo o ponto focal (sliders X/Y) enquadrado.
- **Grade de filtros** (`filter_previews.py` + `blocks/filter.py`): grade clicável de previews (cada filtro aplicado a um thumbnail), gerada off-thread (`page.run_task` + `to_thread`) ao ativar a operação/trocar a fonte. `transform.apply_filter_im` é o motor puro reusado.
- **Background replacement** (`background.py::replace_background`): reusa a máscara do rembg p/ trocar o fundo por cor/desfoque (efeito retrato)/imagem; `remove_background` delega (modo transparent).
- **Watermark avançado** (`transform.watermark_image`): 9-grid + `tile`, rotação, e modos texto/imagem/**QR** (`_qr_rgba` reusa `qrcode`); stamp RGBA reutilizável (`_build_wm_stamp`).
- **OCR** (`ocr.py::ocr_image`): reusa o Tesseract do `[ocr]` (`_resolve_tesseract_cmd`/`is_available` de `core/document/ocr`); saída `<stem>_ocr.txt` indexável no RAG. Worker: modo curto `_run_batch_ocr`. CLI `image ocr --lang`.
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
- **Painel analítico (Plano 2)**: 3º modo (Grade·Lista·**Painel**) via `library/analytics_panel.py` (resumo, contagem/tamanho por tipo, maiores, gráfico de barras). Núcleo puro `core/library/analytics.py` (`summary`/`largest`/`size_by_kind`/`growth_by_period`). CLI `library stats [--top N]`.
- **Auto-tags (Plano 4B)**: `core/library/tags.py` extrai keyphrases (YAKE) por item de texto, cacheadas por `(path, mtime)` em `~/.mill-tools/library_tags.json` (gate-aware: sem `[nlp]` → `[]`). A `view` roda uma **thread de tagging** sobre todo o acervo populando `_tag_index` (a busca casa nome **ou** tag via `filter_items(tag_index=…)`) e preenche a linha de tags dos cards visíveis (`cards.set_tags`, update escopado).
- **Mapa semântico (Plano 4A)**: 4º modo (Grade·Lista·Painel·**Mapa**) via `library/semantic_map_panel.py`. Mostra o PNG do mapa (clusters coloridos + centroides rotulados) + lista de tópicos; clicar num documento abre diálogo de "Relacionados" (`recommend.related`). Lê o `VectorStore` persistido (independe dos filtros); `mapviz.build_semantic_map` + render **off-thread** (`page.run_task` + `asyncio.to_thread`); guard por `corpus_signature` evita recomputar mapa inalterado; gate `[ml]`/extras de gráfico com `SETUP_HINT`.

## Módulo IA (PR7)

RAG local sobre o corpus: indexa o texto que você produziu, recupera os trechos relevantes e responde **citando as fontes**. Embeddings **100% locais** (Ollama); Gemini só opt-in na resposta. Torch-free (só `numpy`). Reusa `make_llm`/`split_text`/`EventBus`/`scan_library`.

- **Core puro** (`core/rag/`): `embedder.py` é a **única rede** (injetável como `embed_fn`; o resto é unit-testável sem Ollama). `VectorStore` = matriz numpy `(N,D)` com busca cosseno + persistência `.npz`/`.json` em `~/.mill-tools/rag/`. `build_index()` **incremental** por `(path, mtime)` (pula inalterados, reembeda alterados, reconcilia removidos); indexa kinds textuais (`transcription`/`document` + descrições `.txt`), tira o header de transcrição, chunka via `split_text` (1200/150). **PR9.3**: aceita `card_fn` injetável e inclui `kind="data"` — arquivos de dados são indexados pelo **cartão de dados** (`core/data/datacard.card_for_path`), nunca pelas linhas cruas (vide Módulo Dados). `chat.answer()` monta contexto numerado `[n]` sob prompt estrito; **o `[n]` é chaveado pelo documento distinto** (chunks do mesmo arquivo compartilham número), então as citações nunca passam do total de fontes (antes numerava por chunk e citava `[5]`/`[6]` com 4 badges). `templates.py` (prompt library) · `batch.py` (1 prompt sobre N docs).
- **GUI** (`modules/ai/`): hub no AppBar, split form|painel, auto-contido. `form_view` — escopo, modelo (`gemma3-4b-custom` default → `gemma3-1b-custom` → `qwen7b-custom` → `gemini-2.5-flash`), chips de prompt. `worker` — `run_ai_index`/`run_ai_answer` em thread daemon (`module_id="ai"`). `view` — resposta em `ft.Markdown` com fontes clicáveis (badge `[n]` amarra ao `[n]` da resposta); status calculado **fora da UI thread** (`is_available()` faz ping no Ollama).
- **Persistência**: `last_ai_model`, `last_ai_scope`, `last_embed_model`, `last_ai_tab` (conversa|indice), `ai_answer_times` (janela móvel de durações por modelo) em `config.json`; índice em `~/.mill-tools/rag/`; prompts em `~/.mill-tools/prompts.json`.
- **CLI** (`cli/ai.py`): `ai index` · `ai stats` (resumo read-only, **+ timing por modelo** no Plano 2) · `ai dups` (duplicatas por similaridade, fundação de ML do Plano 3; `--threshold`/`--scope <kind>`) · `ai topics` (clusters + rótulos c-TF-IDF) · `ai map [--method pca|tsne|umap] [--out]` (PNG do mapa semântico) · `ai related <path> [--k]` (vizinhos por cosseno) — Plano 4A, **read-only/sem embedder** (topics/map exigem `[ml]`; related é numpy-puro) · **Plano 4B**: `ai classify <path>` (perfil sugerido + confiança/margem; reusa o vetor poolado), `ai keywords <path> [--top]` (YAKE), `ai summary <path> [--sentences]` (TextRank), `ai entities <path>` (spaCy NER) · `ai "pergunta"` · `--scope`/`--model`/`--k`/`--reindex`/`--batch [--kind]`. Embeddings sempre locais.
- **Aba "Painel" (Plano 2)**: 3ª aba (Conversa·Índice·**Painel**) via `ai/analytics_tab.py`. Núcleo puro `core/rag/analytics.py`: `index_health` (top por chunks + *stale* por mtime) e `model_timings` (count/mean/median/**p90** via `statistics`, mais rápido primeiro). Reusa `IndexStats`/`ai_answer_times`; `apply` roda na thread daemon do `_refresh_status` → render síncrono ali (fora da UI thread), gated por `control.visible` + extras.
- **Aviso de fora-de-escopo (Plano 4A)**: antes de gerar, o worker deriva a proximidade do acervo do **top-1 do retrieve** (`hits[0].score` — sem re-embeddar), compara com `recommend.DEFAULT_IN_CORPUS_THRESHOLD` e marca `low_confidence` no `answer_done` (+ log `[!]` via `fmt_out_of_scope`); a `view` mostra um banner discreto acima da resposta. Ainda responde — o usuário decide.
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
- **CLI** (`cli/recipes.py`): `recipe list` / `recipe run "<nome>" <input>` (`--model` sobrescreve o Whisper) / `recipe stats` (Plano 2, confiabilidade/velocidade). **Persistência**: `last_recipe`, `recipe_clean_intermediates`; receitas em `~/.mill-tools/recipes.json`.
- **Histórico + aba "Histórico" (Plano 2)**: `core/recipes/history.py` (puro) — `RunRecord` + `append_run`/`load_runs` (append-only, cap 500 em `~/.mill-tools/recipe_runs.json`) + `aggregate`; `RunTracker` observa `step_error`/cronômetro e o **worker/CLI** gravam um `RunRecord` no evento terminal (runner **intocado**). GUI: toggle Execução·**Histórico** (`recipes/history_tab.py`) com taxa de sucesso/duração média/passo que mais falha + gráfico. Matéria-prima do Plano 7.

## Módulo Dados (PR9)

6ª ferramenta na rail (transforma entrada→saída, como Documentos/Imagens — **não** é hub). Paradigma **query-first**: a composição (juntar+filtrar+agrupar+somar+ordenar) vive numa **consulta única**, escrita em português (traduzida pela IA) ou na mão. Motor **DuckDB** (in-process, torch-free). **Divisão de responsabilidades**: a IA recebe **só o schema** (nomes/tipos de coluna) e devolve `(sql, explicação)` — nunca toca nas linhas; o DuckDB abre os arquivos e executa; o core orquestra. **Privacidade**: com Gemini, só os nomes de coluna saem da máquina.

- **Core puro** (`core/data/`): `engine.py` é a **única fronteira com o DuckDB** (injetável, como o `embedder` do RAG) — conexão **in-memory efêmera** por consulta (nada gravável anexado), detecta encoding de CSV via `charset-normalizer` (cp1252/utf-8/utf-16 → encodings do DuckDB; exóticos → latin-1), registra cada arquivo como view, `run_query`/`export_query`/`convert_file` (`COPY ... TO`); **`preview(path, limit, offset, sheet)`** lê uma janela direto do arquivo (sem registrar view) e **`xlsx_sheet_names`** enumera abas via `zipfile`+`workbook.xml` (stdlib, sem dep nova); `reader_expr` aceita `sheet=` p/ XLSX. `validate.py` — guarda: só leitura (SELECT/WITH/FROM/DESCRIBE/SUMMARIZE), rejeita COPY/ATTACH/INSTALL/PRAGMA/DML e múltiplos statements (strip de comentários antes). `nl2sql.py` — `to_sql(schema, pergunta)` via `make_llm`; saída sempre validada por `ensure_select`. `scanner.py` — `scan_file → DataFile` (view name, contagem, colunas) + `schema_text` p/ a IA. `convert.py` — CSV/TSV/JSON/Parquet/XLSX + `rename_sql` (renomeia colunas no output, puro). `profile.py` — relatório textual (`SUMMARIZE`, **amostrado via `USING SAMPLE` acima de 200k linhas** — `summarize_sql` puro); `profile_text` em memória. `assess.py` (PR9.3) — **avaliação de qualidade pela IA** (prompt de responsabilidade única estilo `src/analysis`; recebe só esquema+`SUMMARIZE`+amostra, nunca as linhas); cache em `~/.mill-tools/data_assessments.json` keyed por `(path, mtime)`. `datacard.py` (PR9.3) — **cartão de dados** indexável (`build_data_card` puro = schema+perfil+amostra+avaliação cacheada; `card_for_path` orquestra). `store.py` — `queries.json`. **`frames.py` (Plano 0)** — **única fronteira de DataFrame** (espelha o `engine.py`): `to_polars`/`from_arrow`/`to_result` (round-trip com `QueryResult`, nulos preservados), `to_pandas` (borda ML/gráficos — único ponto pandas), `optimize` (só `shrink_dtype` numérico, tipo-neutro — categorização fica a cargo do consumidor), `describe`; `engine.run_query_arrow` faz o handoff **Arrow zero-copy** (`to_arrow_table`). polars/pandas/pyarrow só sob `TYPE_CHECKING` (extra `[analysis]`) — o `engine` segue DuckDB-puro: fundação **aditiva** para os Planos 1/2/5 (`docs/ROADMAP_ML_DADOS.md`). **`charts.py` (Plano 1)** — **única fronteira matplotlib** (espelha `engine`/`frames`): `suggest_spec` (heurística de tipo de gráfico por coluna → bar/line/hist/scatter), `schema_from_rows` (infere o esquema das linhas p/ a GUI), `render_png` (`Figure`+`FigureCanvasAgg` diretos, **sem `pyplot`** → thread-safe; recebe pandas, devolve bytes PNG; `ChartPalette` injetada pela GUI). matplotlib lazy sob `[data-plot]`; nenhum import de Polars/DuckDB.
- **GUI** (`modules/data/`): rail tool, auto-contido (`module_id="data"`), split form|painel. `form_view` — fontes (FilePicker → chips com contagem de linhas/colunas) + toggle **Português | Consulta** + caixa + Pré-visualizar/Executar; o ⓘ do cabeçalho tem `HELP_LONG["data"]` (modal detalhado). `worker` — `scan`/`translate`/`query`/`save`/**`index`**/**`assess`**/**`plot`** em threads daemon (indexação/avaliação/gráfico emitem sob `module_id="data"`). `view` — **4 abas manuais** no painel (estilo `Conversa | Índice` do hub de IA: `TextButton` + `hairline` + `visible=` num `Stack`, persistidas em `last_data_tab`), cada uma com **rodapé fixo** e **progress/log no topo** (mesmo formato do Consulta): **Consulta** (cartão **"entendi assim"** com SQL editável, prévia **paginada** do resultado em `DataTable` `_PAGE_SIZE=50`/`PREVIEW_ROWS=200`; footer = renomear colunas/formato/Salvar/Conversar sobre/Salvar como Receita) · **Pré-visualização** (primeiras linhas de uma fonte via `table_view.py` com o **tipo por coluna** no cabeçalho + seletor de aba XLSX; footer = **Indexar no RAG**, log de progresso `data_index_*` no topo) · **Análise com IA** (parecer de qualidade em Markdown via `assess`, reusa cache; footer = **Avaliar com a IA**, cronômetro ao vivo no topo; empty state detalha o prompt) · **Gráfico** (PR9.1: `suggest_spec` pré-preenche tipo/x/y do resultado; **Gerar** roda `run_data_plot` off-thread → PNG num `ft.Image`; footer = **Salvar PNG** em `output/data/`; tema escuro via `ChartPalette`). Cada aba tem **empty state fixo centralizado** e, com >1 fonte, um seletor de arquivo. **Spinner (regra de ouro)**: como o spinner vive em container `visible=False`, `_begin`/`_on_index`/`_on_assess` chamam **`page.update()` ANTES de `spinner.start()`** (montar/exibir primeiro, animar depois — senão a 1ª rotação vai p/ controle oculto e a cadeia `on_animation_end` morre). Já durante o giro, os eventos de progresso usam **update escopado** (`_scoped_update`) + `return` — um `page.update()` global interromperia a animação. `table_view.py` (PR9.3) — **componente de tabela paginada reutilizável**. Leituras DuckDB rodam via `asyncio.to_thread`/threads daemon.
- **CLI** (`cli/data.py`): `data query <arquivos...> "<pergunta>" [--sql] [--out csv|xlsx|json|parquet] [--name] [--limit]`, `data convert`, `data profile`, `data assess <arquivo> [--model] [--no-cache]` (PR9.3, parecer da IA + cache), `data plot <arquivos...> "<pergunta>" [--sql] [--kind bar|line|hist|scatter] [--x] [--y] [--out]` (PR9.1, gráfico PNG via `run_query_arrow`→`render_png`). Reusa o core direto (como `ai`/`library`, sem `CLIEventBus`); stdout em UTF-8.
- **Integrações**: Receitas — `data.query` (multi-input, consome a lista inteira; `sql` ou `question` nos params; produz KIND_TEXT p/ fechar `data.query → ai.answer`), `data.convert`, `data.profile` (novo `KIND_DATA`). Biblioteca — `output/data/ → kind="data"`; ícone de tabela; filtro "Dados"; bridge "Consultar nos Dados". **RAG (PR9.3)** — o `indexer.build_index` aceita `card_fn` injetável: itens `kind="data"` são indexados pelo **cartão de dados** (`card_for_path`), nunca pelas linhas cruas; `indexable_items` inclui `kind="data"` (casa por kind). `run_ai_index`/CLI `ai index` passam o `card_fn` (varredura da Biblioteca, com reconciliação). O botão **Indexar no RAG** da aba Pré-visualização usa `indexer.index_files` (**aditivo, sem reconciliação**, sempre reembeda) sobre os **arquivos selecionados** — indexa o arquivo previsto mesmo fora de `output/` e ele passa a constar no inspetor.
- **Persistência**: `last_data_model`/`last_data_format`/`last_data_mode`/`last_data_tab`; saídas em `output/data/`; consultas em `~/.mill-tools/queries.json`; avaliações em `~/.mill-tools/data_assessments.json`. **XLSX** isolado em `convert.py`/`engine.py` (extensão `excel` do DuckDB carregada sob demanda; degrada com erro claro se faltar).

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
uv run main.py audio   <URL_OR_FILE> [--fmt mp3] [--quality 320] [--mono] [--sample-rate 16000] [--trim-silence] [--speed 1.25] [--denoise [--denoise-adaptive]] [--normalize [--lufs -16]]
uv run main.py audio-viz <arquivo> [--spectrogram] [--width 1200] [--height 480]   # waveform/espectrograma PNG
uv run main.py video   <download|convert|trim|compress|resize|extract-audio|thumbnail|subtitle> <input> [opções]
uv run main.py image   <convert|resize|crop|rotate|watermark|border|adjust|filter|favicon|contact-sheet|remove-bg|describe|exif|ocr> <input> [opções]
uv run main.py document <merge|split|compress|rotate|watermark|stamp|encrypt|extract|ocr|pdf-to-images|images-to-pdf|qr> <input> [opções]
uv run main.py library list [--kind audio|data] [--since 7d] [--sort size]
uv run main.py ai index | ai stats | ai dups [--threshold 0.95] [--scope kind] | ai topics | ai map [--method pca|tsne|umap] [--out] | ai related <path> [--k 5]
uv run main.py ai classify <path> | ai keywords <path> [--top 10] | ai summary <path> [--sentences 5] | ai entities <path>   # Plano 4B (textual)
uv run main.py ai "pergunta" [--scope X] [--model gemini-2.5-flash] [--k 8] [--batch]
uv run main.py recipe list | recipe run "<nome>" <URL_OR_FILE> [--model medium]
uv run main.py data   query <arquivos...> "<pergunta>" [--sql] [--out csv|xlsx|json|parquet] [--name] [--limit]
uv run main.py data   convert <arquivo> [--out parquet] | data profile <arquivo> | data assess <arquivo> [--model] [--no-cache]
```

> Referência completa de flags → skill `cli` (`.claude/skills/cli/SKILL.md`).

## Convenções de código

- **Idioma do código**: docstrings, logs, comentários e strings internas em **inglês**. Português **só** em labels/textos visíveis da GUI. Há inconsistências históricas — ao tocar um arquivo, corrigir PT→EN em docstrings/logs na mesma passagem.
- Docstrings em todas as funções/módulos. Logging via handler dedicado — **nunca `print()`** para logs.
- **Core (`src/core/`) é puro**: sem Flet, reutilizável por CLI e GUI.
- **Tamanho e coesão de arquivo** (governado pela skill `architecture`): builder de GUI ≤ ~400–500 linhas; módulo de `core/` ≤ ~300–400. Um arquivo = uma responsabilidade. Builder/aba/seção que cresce → extrair via `blocks/`/`tabs/`/`registry/<módulo>` (sub-builder devolve `(controle, refs/handlers)`). Regra "divide-se ao tocar": dividir no momento em que um plano estende o arquivo, não preventivamente.
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

> **Quirk Windows — pacote corrompido após `uv sync` (lock de `.pyd`)**: um `uv sync` interrompido por **lock do Windows** sobre um `.pyd` (binário em uso por um `python.exe`/GUI ainda aberto, ou bloqueio do Defender) pode deixar um pacote **meio-instalado** — o diretório fica só com o `.pyd`/`.pyi`, **sem o `__init__.py`**, e o `RECORD` do `.dist-info` some. Sintoma: `ImportError: cannot import name 'X' from 'pkg' (unknown location)` (o `pkg.__file__` vira `None`, vira namespace vazio). Já visto com `markupsafe` quebrando `jinja2`/`spacy`. **Fix**: `uv run poe repair <pkg>` (= `uv sync --all-extras --all-groups --reinstall-package <pkg>`) — força reinstalação limpa só daquele pacote sem apagar os extras. **Prevenção**: feche a GUI/`python.exe` antes de rodar `uv sync`.

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

> **Modelo spaCy (Plano 4B, NER)**: `pt_core_news_sm` é download à parte (não é dep pip limpa), como o Tesseract. Setup: `uv sync --extra nlp && uv run python -m spacy download pt_core_news_sm`. CNN/thinc — **torch-free**; `text.entities.is_available()` checa pacote **e** modelo, e o campo de entidades degrada se faltar. Nunca usar variantes `_trf` (puxam torch). **Glossário opcional de domínio** (refinamento pós-4B): `~/.mill-tools/entity_glossary.json` — lista de padrões do `EntityRuler` (`[{"label": ..., "pattern": ...}]`), lida uma única vez no primeiro carregamento do pipeline por idioma (é um singleton em cache — não dá para trocar por chamada) e adicionada antes do `ner` estatístico. Sem o arquivo, comportamento idêntico a antes; não há CLI/GUI para editá-lo, só o arquivo.
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
| `ft.Image()` **exige `src` no construtor** | `Image.__init__() missing 1 required positional argument: 'src'` se omitido. Comece com um placeholder (`_charts.BLANK_PNG`, 1×1) e troque por `img.src = png` depois — padrão de `audio_player`/`plot_tab`/painéis do Plano 2 |
| `ft.Image` updates frequentes | `gapless_playback=True` mantém o frame anterior visível — evita flicker (cursor de waveform) |
| `Container.on_hover` coberto | **não dispara** quando o Container é totalmente coberto por outra região de mouse. Para hover **e** tap no mesmo card, usar **um único** `ft.GestureDetector` com `on_enter`/`on_exit` (+ `on_tap`) — ver `home.py` |
| `control.update()` de thread daemon | **não repinta** até o próximo `page.update()` da UI thread — um cronômetro/ticker em `threading.Thread` parece travado. Para atualização periódica viva, rodar no event loop da UI via `page.run_task` (corotina async com `await asyncio.sleep`) — ver `ai/view.py`, `home.py`, `library.py` |
| `page.open(...)` | **não existe** no 0.85.2 (`AttributeError` em runtime, no handler). Diálogos **e** SnackBars (SnackBar é `DialogControl`) vão por `page.show_dialog(...)`; fechar = `page.pop_dialog()`. Nunca `page.snack_bar=`/`page.dialog=`. Há usos latentes de `page.open` no repo (não exercitados) |

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
- **PR9.3** ✅ — Prévia visual da fonte (aba **Pré-visualização** na view: tabela paginada + tipos por coluna, seletor de aba XLSX), avaliação de qualidade pela IA (aba **Análise com IA**; `assess.py` + cache) e **indexação dos 5 formatos no RAG** via cartão de dados (`datacard.py`, `card_fn` no indexer). CLI `data assess`. Painel reorganizado em 3 abas (Consulta | Pré-visualização | Análise com IA).
- **Plano 0 (Fundação de dados)** ✅ — camada Polars sobre o DuckDB: `core/data/frames.py` (única fronteira de DataFrame) + `engine.run_query_arrow` (Arrow zero-copy), extra `[analysis]`. Puramente aditiva (ninguém consome ainda); destrava os Planos 1 (gráficos = PR9.1)/2 (painéis)/5 (ML tabular) do `docs/ROADMAP_ML_DADOS.md`. Ver `docs/PLANO_0_FUNDACAO_DADOS.md`.
- **PR9.1 / Plano 1** ✅ — Gráficos no módulo Dados: `core/data/charts.py` (única fronteira matplotlib, render off-thread `Figure`/`Agg` sem `pyplot` → PNG), aba **Gráfico** na GUI (4ª aba) + CLI `data plot`, extra `[data-plot]`. Reusa o caminho Arrow do Plano 0; bar/line/hist/scatter com `suggest_spec`. Ver `docs/PLANO_1_GRAFICOS.md`.
- **Plano 2 (Painéis analíticos dos hubs)** ✅ — superfície de painel em cada hub sobre os dados que eles já coletam, **sem ML** e sem dependência nova (números em stdlib; gráfico opcional via Plano 1, gated). Núcleos puros `core/library/analytics.py` (acervo) · `core/rag/analytics.py` (saúde do índice + timing por modelo, p90 via `statistics`) · `core/recipes/history.py` (histórico append-only de execução: `RunRecord`/`RunTracker`/`aggregate`, gravado pelo worker/CLI no evento terminal — runner intocado). GUI: Biblioteca ganha 3º modo (Grade·Lista·**Painel**), IA ganha 3ª aba (Conversa·Índice·**Painel**), Receitas ganha toggle (Execução·**Histórico**); helper compartilhado `gui/modules/_charts.py` (QueryResult→PNG). CLI `library stats`/`recipe stats` + `ai stats` estendido com timing. Ver `docs/PLANO_2_PAINEIS_HUBS.md`.
- **Plano 3 (Fundação de ML)** ✅ — pacote puro `core/ml/` espelhando `core/rag/`, **reusando o `VectorStore` já persistido** (sem recalcular embedding). `features.py` (acessor, **numpy-puro**) faz mean-pool dos chunks em vetores de documento (L2-norm, ordem first-seen) — a decisão de pooling/normalização é única e herdada pelos consumidores dos Planos 4/5; `dedup.py` agrupa duplicatas por cosseno (componentes conexas, guard `max_docs`) como prova de vida. `deps.py` (gate `[ml]` = scikit-learn ≥1.4, só os algoritmos futuros gateiam — acessor/dedup são fundação grátis numpy-pura) + `store.py` (persistência de modelos versionada por `sklearn.__version__`+signature, invalida no mismatch; joblib v1, skops documentado). CLI `ai dups [--threshold] [--scope kind]` (read-only, sem embedder); GUI deferida ao Plano 4. Ver `docs/PLANO_3_FUNDACAO_ML.md`.
- **Plano 4A (Inteligência semântica não-supervisionada)** ✅ — só geometria de embeddings (sem rótulos/treino), reusando `features.document_matrix` (Plano 3) e o `charts` (Plano 1). Núcleo `core/ml/`: `cluster` (HDBSCAN auto-k, ruído=-1; k-means), `labeling` (c-TF-IDF estilo BERTopic via `CountVectorizer`, stopwords PT/EN próprias), `project` (PCA determinística default; UMAP opcional sob `[ml-viz]`, métrica cosseno + pré-redução PCA→50D), `recommend` (related/in_corpus, **numpy-puro**), `cache` (mapa versionado por `corpus_signature`), `mapviz` (orquestra → `SemanticMap` → PNG). `charts.render_category_scatter` (scatter colorido por categoria + anotações de centroide, única fronteira matplotlib estendida). GUI: Biblioteca modo **Mapa** (`semantic_map_panel.py`, off-thread, "Relacionados" por documento) + aviso de fora-de-escopo na IA (banner via `low_confidence` do top-1 do retrieve). CLI `ai topics`/`ai map`/`ai related`. Nenhuma dep obrigatória nova (só `[ml-viz]` opcional). Ver `docs/PLANO_4A_SEMANTICO.md`.
- **Plano 4B (Classificação supervisionada + inteligência textual)** ✅ — a camada que precisa de **rótulo** ou de **NLP textual**, reusando `features.document_matrix` (Plano 3). `core/ml/classify.py`: classificação de perfil **zero-shot** (protótipos por perfil = `label`+`source_hint`, embeddados 1×, cacheados; nearest-prototype por cosseno; `margin`=incerteza) que **escala para supervisionado** conforme o usuário confirma/corrige o perfil (`record_label` no worker → `train_supervised` = `LinearSVC`+`CalibratedClassifierCV` sobre `dm.X`, persistido no `store` versionado; fallback transparente por signature). Pacote novo `core/text/` (puro, independente do `core/ml`): `keywords` (YAKE), `summarize` (TextRank self-contained sobre `TfidfVectorizer`, sem download nltk), `entities` (spaCy NER CNN, singleton lazy, gate de modelo), `reader`/`lang`. Extra `[nlp]` (yake+spacy); resumo/classificação sem dep nova. GUI: auto-sugestão de perfil na Transcrição (`profile_section`, chip + pré-seleção off-thread), aba **Insights** no resultado (`insights_panel`), **auto-tags** pesquisáveis na Biblioteca (`core/library/tags.py` + `filter_items(tag_index=…)`). CLI `ai classify`/`keywords`/`summary`/`entities`. Entrega os **motores** que o Plano 4C ("ficha de leitura") vai compor. Ver `docs/PLANO_4B_SUPERVISIONADO_TEXTUAL.md`.
- **Áudio Tier 1** ✅ — Cadeia de pós-processamento estendida 100% ffmpeg: remoção de silêncio (`silenceremove`), velocidade sem pitch (`atempo`), downmix mono + sample-rate no **encode final** (conserta o denoise→.wav), toggle de modo de ruído (`stationary`) e **presets de uma tecla** (Transcrição/Podcast/Música). Formulário fatiado em `blocks/`. Ver `docs/PLANO_AUDIO_TIER1.md`.
- **Áudio Tier 2** ✅ — Visualização e feedback: aba **Visualizar** (áudio→imagem, `core/audio/visualize.py` via `showwavespic`/`showspectrumpic`, off-thread, mini-log com cronômetro/previsão) + toggle `Converter|Visualizar`, **A/B antes/depois** no player (reusa o motor, sem 2º waveform) e **card de loudness** medido vs. alvo. CLI `audio-viz`. Loop do cursor migrado para `page.run_task` (corrige a dessincronização). Ver `docs/PLANO_AUDIO_TIER2.md`; itens avançados em `docs/PLANO_AUDIO_TIER3_RESUMO.md`.
- **PR9.2** — Encadeamento em estágios (resultado vira nova fonte).
- **PR3.1-B** — IA de áudio com torch (extra `[ai-audio]`): DeepFilterNet, Demucs (a avaliar).
- **Futuro** — Imagens (batch rename, upscale); arrastar arquivos do SO (não nativo no Flet).
