<div align="center">

<img src="assets/logo/mill-logo-wordmark.png" alt="mill.tools" width="380">

**Multiferramenta pessoal, local-first, para áudio, vídeo, imagens, documentos, dados e transcrição — com GUI desktop e CLI.**

![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9)
![Flet](https://img.shields.io/badge/GUI-Flet%200.85-02569B)
![faster-whisper](https://img.shields.io/badge/faster--whisper-GPU-FFB000)
![Ollama](https://img.shields.io/badge/Ollama-local-000000?logo=ollama&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-embutido-FFF000?logo=duckdb&logoColor=black)
![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?logo=scikitlearn&logoColor=white)

![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue)
![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)
![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
![torch-free](https://img.shields.io/badge/PyTorch-free-success?logo=pytorch&logoColor=white)

</div>

---

## Visão geral

**mill.tools** é uma caixa de ferramentas pessoal que processa mídia, documentos e dados **diretamente no seu computador** — sem enviar arquivos para servidores, sem assinaturas e sem limites de uso. A IA roda 100% local por padrão (via [Ollama](https://ollama.com)), com o [Google Gemini](https://ai.google.dev/) disponível como alternativa opt-in na nuvem.

A aplicação é organizada em **módulos independentes que se integram**: cada um é especializado numa categoria de tarefa, mas a saída de um alimenta o outro — um áudio baixado segue para a transcrição com um clique, e uma cadeia inteira (`URL → áudio → transcrever → analisar`) cabe numa receita.

Acesse por uma **GUI desktop** (Flet/Flutter) ou pela **CLI** — paridade de comportamento entre as duas.

---

## Módulos

Seis **ferramentas** de processamento (NavigationRail) e três **hubs** que operam sobre as saídas de todas elas (AppBar).

| Módulo | Tipo | Descrição |
|---|---|---|
| **Transcrição** | Ferramenta | Whisper local (GPU) sobre URL, áudio/vídeo local ou texto; pós-processamento por IA: parágrafos, análise estruturada e digest. Um `.txt`/`.md` pula o Whisper e vai direto à IA |
| **Áudio** | Ferramenta | Download (yt-dlp), conversão e extração de faixas em fila; pós-processamento encadeável: remoção de silêncio, denoise (spectral gating), velocidade sem pitch (`atempo`), normalização de loudness (EBU R128), downmix mono e reamostragem; **presets de uma tecla** (Transcrição/Podcast/Música); reprodutor com **A/B antes/depois**; aba **Visualizar** (waveform/espectrograma PNG) |
| **Vídeo** | Ferramenta | 8 operações: download, convert, trim, compress, resize, extract-audio, thumbnail e legenda (mux/burn-in). Encoding 100% CPU — sem NVENC |
| **Imagens** | Ferramenta | Conversão/manipulação + IA, com toggle **Edição \| Descrição IA**. Edição: convert, resize, **smart crop** (ponto focal), rotate, **watermark** (texto/imagem/QR, 9-grid, tiling, rotação), border, adjust, **grade de filtros**, favicon, colagem, **remoção/troca de fundo** (rembg) e **OCR** (Tesseract). Controle de **EXIF** (privacidade/copyright), visor Antes/Depois (xadrez de transparência, metadados, lote navegável), bridge **imagem→PDF**. Descrição por visão (gemma3-4b) em aba própria com Markdown |
| **Documentos** | Ferramenta | 13 operações PDF/QR (merge, split, compress, rotate, watermark, stamp, encrypt, extract, OCR, pdf↔imagens, QR, análise). 100% local via pymupdf |
| **Dados** | Ferramenta | Consulte CSV/TSV/JSON/Parquet/XLSX em **português** (a IA traduz para SQL vendo só o schema) ou SQL na mão; motor **DuckDB** embutido. Salva o resultado, perfila e gera **gráficos** (barras/linha/histograma/dispersão) |
| **Biblioteca** | Hub | Índice navegável de tudo em `output/`: grade com thumbnails, lista, **painel analítico** (acervo por tipo/tamanho/crescimento) ou **mapa semântico** (temas do acervo agrupados + relacionados); filtro/busca/ordenação, abrir arquivo/pasta e reenviar a outro módulo |
| **IA** | Hub | RAG local sobre o seu acervo: pergunte ao corpus e receba respostas **citando as fontes** (com aviso quando o acervo não cobre a pergunta). Embeddings sempre locais; Gemini opt-in. **Painel**: saúde do índice + tempo de resposta por modelo. **ML semântico**: duplicatas (`ai dups`), tópicos automáticos (`ai topics`), mapa semântico (`ai map`) e relacionados (`ai related`) — tudo reusando o índice |
| **Receitas** | Hub | Automação: cadeias lineares entre módulos (`URL → áudio → transcrever → analisar`). Presets + construtor com validação ao vivo; lote; **histórico de execução** (confiabilidade/velocidade); CLI `recipe run` |

---

## Destaques técnicos

| Característica | Detalhe |
|---|---|
| Transcrição local | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + ctranslate2, aceleração GPU, **sem PyTorch** |
| Dados | [DuckDB](https://duckdb.org) embutido (in-process, torch-free); PT→SQL pela IA recebendo só o schema — o conteúdo das tabelas nunca sai da máquina |
| RAG local | embeddings Ollama (`nomic-embed-text`, CPU), vector store numpy, busca cosseno, resposta com fontes `[n]` |
| ML local | `core/ml` **torch-free** sobre os embeddings do RAG (sem recálculo): duplicatas e relacionados por cosseno (**numpy**); clustering ([HDBSCAN](https://scikit-learn.org)), rótulos de tema (c-TF-IDF) e mapa semântico 2D (PCA) via [scikit-learn](https://scikit-learn.org) (extra `[ml]`); projeção UMAP opcional (extra `[ml-viz]`); **classificação de perfil** zero-shot→supervisionada (`classify`) |
| NLP textual | `core/text` **torch-free** (extra `[nlp]`): keyphrases ([YAKE](https://github.com/LIAAD/yake)), resumo extractivo (TextRank self-contained, sem nltk) e entidades ([spaCy](https://spacy.io) CNN `pt_core_news_sm`). Auto-sugestão de perfil, aba Insights e auto-tags da Biblioteca |
| Vídeo | yt-dlp + ffmpeg CPU-only (libx264/libx265/libvpx-vp9) — sem NVENC |
| Áudio | noisereduce (spectral gating, CPU) + ffmpeg loudnorm (EBU R128, 2 passes), silenceremove e atempo (silêncio/velocidade); torch-free |
| Imagens | Pillow (transforms, EXIF, smart crop, watermark/QR, filtros) + rembg/ONNX (CPU) para remoção/troca de fundo; OCR via Tesseract (extra `[ocr]`); descrição por visão via Ollama (`gemma3-4b`) |
| Documentos | [pymupdf](https://pymupdf.readthedocs.io) (PDF) + Tesseract (OCR híbrido, opcional) |
| Interface | [Flet 0.85](https://flet.dev) (Flutter desktop) com log em tempo real, design system próprio e ajuda contextual (ⓘ) |
| IA | Ollama local por padrão; Gemini opt-in por prefixo de modelo (`gemini-*`) |

> **Decisão consciente: sem PyTorch.** O app base é torch-free. IA de áudio com torch (DeepFilterNet/Demucs) ficaria isolada num extra opcional.

---

## Requisitos

| Requisito | Necessário para |
|---|---|
| [Python 3.13+](https://www.python.org/) · [uv](https://docs.astral.sh/uv/) | Tudo |
| [ffmpeg](https://ffmpeg.org/download.html) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) (no PATH) | Áudio, Vídeo, Transcrição |
| [Ollama](https://ollama.com/download) | Modelos de IA locais (formatação, análise, RAG, PT→SQL) |
| Chave [Google AI Studio](https://aistudio.google.com/apikey) | Modelos Gemini (opcional) |
| [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) + packs `por`/`eng` | OCR de Documentos (extra `[ocr]`) |
| Modelo spaCy `pt_core_news_sm` (`python -m spacy download …`) | NER do `[nlp]` (download à parte, como o Tesseract) |

DuckDB e a extensão `excel` (XLSX) são embutidos — sem instalação separada.

---

## Instalação

```bash
git clone https://github.com/mgckaled/mill.tools
cd mill.tools
uv sync
```

### Modelos locais (Ollama)

```bash
# formatação de parágrafos (Transcrição)
ollama pull phi4-mini      && ollama create phi4mini-custom  -f ollama/Modelfile.phi4mini
# análise / RAG / PT→SQL (qualidade máxima, lento na CPU)
ollama pull qwen2.5:7b     && ollama create qwen7b-custom    -f ollama/Modelfile
# análise / RAG / PT→SQL (padrão — melhor custo-benefício) e fallback rápido
ollama pull gemma3:4b      && ollama create gemma3-4b-custom -f ollama/Modelfile.gemma3-4b
ollama pull gemma3:1b      && ollama create gemma3-1b-custom -f ollama/Modelfile.gemma3-1b
# embeddings do RAG (CPU-only, num_gpu 0)
ollama pull nomic-embed-text && ollama create nomic-embed-custom -f ollama/Modelfile.nomic
# descrição de imagens (visão)
ollama pull moondream      && ollama create moondream-custom -f ollama/Modelfile.vision
```

### Extras opcionais

```bash
uv sync --extra ai-image   # remoção de fundo (Imagens)
uv sync --extra ocr        # OCR de PDFs escaneados (requer binário Tesseract no PATH)
uv sync --extra analysis --extra data-plot  # gráficos no módulo Dados (aba Gráfico / data plot)
uv sync --extra ml         # clustering/tópicos/mapa semântico (Plano 4A); dups/related rodam sem ele (numpy)
uv sync --extra ml-viz     # projeção UMAP do mapa (opcional, puxa numba; PCA é o default)
uv sync --extra nlp        # keyphrases (YAKE) + entidades (spaCy NER); ai keywords/entities, Insights, auto-tags
uv run python -m spacy download pt_core_news_sm  # modelo de NER (download à parte, como o Tesseract)
```

> O app base funciona sem os extras; os cards correspondentes desabilitam-se graciosamente quando ausentes.
> O resumo extractivo (`ai summary` / Insights) e a classificação de perfil usam só o extra `[ml]` — sem dep nova.

### Google Gemini (opcional, free tier)

```bash
cp .env.example .env       # preencha GOOGLE_API_KEY=...
```

O `.env` é carregado quando um modelo começa com `gemini`. O Ollama segue como padrão — nada quebra sem o `.env`. Recomendado: `gemini-2.5-flash` (contexto de 1M tokens).

---

## Uso

### GUI desktop

```bash
uv run gui.py
```

Abre maximizado: splash animada → **Home Screen** (6 ferramentas em grade 3+3 e 3 hubs em destaque) → módulo escolhido. Cada módulo tem layout split — formulário à esquerda, painel de acompanhamento (log + barra de progresso + spinner) à direita. A troca de módulo é bloqueada enquanto um pipeline roda; os logs são preservados ao navegar.

### CLI

```bash
# Transcrição (idioma automático; --format/--analyze/--prompt adicionam etapas de IA)
uv run main.py <URL|video.mp4|notas.txt> --format --analyze --profile lecture

# Áudio — download/conversão/extração + pós-processamento
uv run main.py audio <URL|arquivo> --fmt mp3 --quality 320 --denoise --normalize
# Pronto p/ transcrição: mono + 16 kHz + remoção de silêncio
uv run main.py audio aula.mp4 --mono --sample-rate 16000 --trim-silence
# Estudo acelerado: 1,5× sem alterar o tom
uv run main.py audio podcast.mp3 --speed 1.5
# Visualização — waveform/espectrograma PNG
uv run main.py audio-viz musica.mp3 --spectrogram

# Vídeo — download | convert | trim | compress | resize | extract-audio | thumbnail | subtitle
uv run main.py video download <URL> --quality 1080 --container mp4
uv run main.py video subtitle video.mp4 --subs legenda.srt --mode soft

# Imagens — convert | resize | crop | rotate | watermark | border | adjust | filter | favicon | contact-sheet | remove-bg | describe | exif | ocr
uv run main.py image convert photo.jpg --fmt webp --quality 85
uv run main.py image crop photo.jpg --mode focal --ratio 1:1 --focal-x 0.5 --focal-y 0.35
uv run main.py image watermark photo.jpg --mode qr --text "https://mill.tools" --position bottom-right
uv run main.py image remove-bg photo.png --model u2net --bg-mode blur --bg-blur 20
uv run main.py image exif photo.jpg --strip-gps          # privacidade (remove localização)
uv run main.py image ocr captura.png --lang por          # texto → .txt indexável no RAG

# Documentos — merge | split | compress | rotate | watermark | stamp | encrypt | extract | ocr | pdf-to-images | images-to-pdf | qr
uv run main.py document split doc.pdf --pages "1-3,5,8-"
uv run main.py document ocr scanned.pdf --lang por --dpi 300

# Dados — consulta em PT (a IA traduz) ou SQL na mão; converte e perfila
uv run main.py data query vendas.csv clientes.csv "total por cliente, do maior para o menor" --out xlsx
uv run main.py data query dados.parquet "SELECT * FROM dados LIMIT 10" --sql
uv run main.py data convert dados.csv --out parquet
uv run main.py data profile dados.csv
uv run main.py data plot vendas.csv "total por produto" --kind bar   # gráfico PNG em output/data/

# Biblioteca — índice de output/ como tabela (+ dashboard do acervo)
uv run main.py library list --kind audio --since 7d --sort size
uv run main.py library stats --top 10

# IA — RAG local sobre o corpus (cita fontes); stats inclui timing por modelo
uv run main.py ai index
uv run main.py ai "o que eu disse sobre faster-whisper?" --k 8
uv run main.py ai stats

# Receitas — cadeias nomeadas entre módulos (+ histórico de execução)
uv run main.py recipe list
uv run main.py recipe run "YouTube → transcrição completa" "https://youtu.be/..." --model medium
uv run main.py recipe stats
```

#### Flags da Transcrição

| Flag | Default | Descrição |
|---|---|---|
| `--wm` | `small` | Whisper: `tiny`/`base`/`small`/`medium`/`large-v3-turbo`/`large-v3` |
| `--language` | auto | Código do idioma (`pt`, `en`…) |
| `--beam-size` | `1` | `1` = rápido, `5` = preciso |
| `--format` / `--fm` | off / `phi4mini-custom` | Quebra de parágrafos via LLM |
| `--analyze` / `--am` | off / `gemma3-4b-custom` | Análise estruturada (`--profile` escolhe o esquema) |
| `--prompt` / `--pm` | off / `gemma3-4b-custom` | Digest condensado (~40%) |
| `--verbose` | off | Logging DEBUG |

> Modelos `gemini-*` em `--fm`/`--am`/`--pm` roteiam para o Google (requer `GOOGLE_API_KEY`).

#### Cookies do YouTube (verificação anti-bot)

O YouTube às vezes bloqueia downloads com "Sign in to confirm you're not a bot". O app pode usar os **cookies do seu navegador logado** (Áudio/Vídeo/Transcrição) — **desativado por padrão** (opt-in). Ative em **Configurações** (engrenagem no AppBar) ou via `MILL_YT_COOKIES_BROWSER`/`MILL_YT_COOKIES_PROFILE`. Os cookies são lidos localmente. **Atenção:** cookies de **conta logada** podem fazer o YouTube exigir um *PO Token* e o download falhar (`Requested format is not available`) — nesse caso, desative-os e tente sem.

---

## Saídas

Tudo é gravado em `output/`, organizado por tipo:

```text
output/
├── audio/         source/ (downloads) · processed/ (conversões, extrações)
├── video/         source/ · processed/
├── image/         source/ · processed/
├── document/      processed/
├── data/          consultas, conversões e perfis do módulo Dados
└── transcriptions/ text/ · analysis/ (--analyze) · digest/ (--prompt) · subtitles/
```

- **Transcrição** (`text/*.txt`): cabeçalho de metadados + texto; segmentos incertos marcados com `[?]` (`avg_logprob < -1.0` ou `no_speech_prob > 0.6`).
- **Análise** (`analysis/*.md`): relatório estruturado (resumo, pontos-chave, ações, conceitos, métricas, citações…), perfil-dirigido (`--profile`). Saída em PT-BR.
- **Digest** (`digest/*.txt`): versão condensada (~40%) sem CTAs, pronta para colar como contexto.

---

## Modelos

**Whisper (transcrição de áudio)** (`--wm`): `tiny` → `large-v3` (mais rápido → mais preciso); `small` é o padrão equilibrado.

**Ollama ("gerenciador" modelos open-source)** (local, padrão) — customizados via Modelfiles em `ollama/` (CPU-pinned, `num_gpu 0`):

| Modelo | Papel | Tamanho |
|---|---|---|
| `phi4mini-custom` | Formatação | ~2,5 GB |
| `gemma3-4b-custom` | Análise · Prompt · RAG · PT→SQL (**padrão**) | ~3,3 GB |
| `gemma3-1b-custom` | Fallback rápido / baixa-RAM | ~815 MB |
| `qwen7b-custom` | Análise/RAG de máxima qualidade (lento na CPU) | ~4,7 GB |
| `nomic-embed-custom` | Embeddings do RAG (768-dim) | ~275 MB |
| `moondream-custom` | Descrição de imagens (visão) | ~1,7 GB |

**Gemini** (nuvem, opt-in): roteado por prefixo `gemini-*`. Com a janela de 1M tokens, `--analyze`/`--prompt` dispensam chunking. Recomendado: `gemini-2.5-flash`.

---

## Arquitetura

`src/core/` é **puro** (sem Flet) e reutilizável por CLI e GUI; `src/gui/` é a camada Flet; `src/cli/` os subcomandos.

```text
src/
├── transcriber · formatter · analyzer · prompter · llm_factory · llm_utils · utils
├── analysis/      perfis de análise (puro)
├── cli/           1 módulo por subcomando (audio/video/image/document/library/ai/recipes/data) + bus
├── core/          PURO — audio · video · image · document · library · rag · recipes · data
│   └── data/      types · scanner · engine (fronteira DuckDB) · frames (DataFrame, Plano 0) · charts (matplotlib, Plano 1) · nl2sql · validate · convert · profile · store
└── gui/           app (rail + hubs) · home · splash · events · settings · modules/ · theme/ (design system) · views/
```

Cada módulo da GUI é uma entrada na lista `MODULES` (`app.py`); o `control` é construído uma vez e a navegação alterna visibilidade num `ft.Stack`. Saídas vão para `output/`, a origem do índice da Biblioteca e do RAG. Detalhes por subsistema vivem nas *skills* do projeto (`.claude/skills/`) e no `CLAUDE.md`.

---

## Testes

```bash
uv run pytest -m unit            # unitários — rápido, sem ffmpeg/rede/GPU
uv run pytest -m integration     # integração — requer ffmpeg
uv run pytest -n auto            # paralelizado (pytest-xdist)
uv run pytest --cov=src --cov-report=html
```

**1255 testes unitários** (0 falhas); cobertura sobre `src/` (branch on, GUI excluída por não ser testável headless), agregado ~92%. Testes de integração são pulados automaticamente sem `ffmpeg`. Linter: **ruff** — `uv run pytest -m unit` verde + `ruff` limpo antes de qualquer commit.

---

## Atalhos da GUI

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Inicia o pipeline (se a entrada for válida) |
| `Esc` | Cancela o pipeline em andamento |

---

## Roadmap

Entregue: **Tier 0** (legendas, OCR) · **PR4** Vídeo · **PR5/5.1** Documentos + OCR · **PR6/6.6** Biblioteca + entrada flexível · **PR7/7.2** IA (RAG local) + inspetor de índice · **PR8** Receitas · **PR9** Dados (query-first sobre DuckDB) · **PR9.1** gráficos no módulo Dados (matplotlib → PNG) · **Plano 2** painéis analíticos nos hubs (acervo da Biblioteca, saúde do índice + timing por modelo na IA, histórico de execução nas Receitas).

Também entregue — **módulo Imagens (Tier 1+2)**: visor polido (xadrez de transparência, faixa de metadados, tira de lote), controle de **EXIF** (CLI/GUI), aba **Descrição IA** (gemma3-4b vision), inspetor de metadados, **smart crop** por ponto focal, **grade de filtros**, **background replacement** (cor/desfoque/imagem), **watermark avançado** (9-grid/tiling/rotação/QR), **OCR** de imagem e bridge **imagem→PDF**.

A seguir: **PR9.2** encadeamento em estágios · **PR3.1-B** IA de áudio com torch (extra `[ai-audio]`) · mais melhorias em Imagens (batch rename, upscale ONNX, HEIC) · streaming da resposta da IA.
