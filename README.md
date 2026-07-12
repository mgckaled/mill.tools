<div align="center">

<img src="assets/logo/mill-logo-wordmark.png" alt="mill.tools" width="380">

**Multiferramenta pessoal, local-first, para áudio, vídeo, imagens, documentos, dados e transcrição — com GUI desktop e CLI.**

![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9)
![Flet](https://img.shields.io/badge/GUI-Flet%200.85-02569B)
![Windows](https://img.shields.io/badge/Windows-10%2B-0078D4)
![faster-whisper](https://img.shields.io/badge/faster--whisper-GPU-FFB000)
![Ollama](https://img.shields.io/badge/Ollama-local-000000?logo=ollama&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-opt--in-8E75B2?logo=googlegemini&logoColor=white)
![GLM](https://img.shields.io/badge/GLM-opt--in-3B82F6)
![DuckDB](https://img.shields.io/badge/DuckDB-embutido-FFF000?logo=duckdb&logoColor=black)
![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?logo=scikitlearn&logoColor=white)

![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue)
![Tests](https://img.shields.io/badge/tests-1.2k%2B%20unit-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)
![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
![torch-free](https://img.shields.io/badge/PyTorch-free-success?logo=pytorch&logoColor=white)
![privacy](https://img.shields.io/badge/dados-nunca%20saem%20da%20m%C3%A1quina-success)

</div>

---

**Índice** · [O que é](#o-que-é) · [Comece em 5 minutos](#comece-em-5-minutos) · [Módulos](#módulos) · [Primeiro uso](#primeiro-uso) · [Instalação completa](#instalação-completa) · [CLI](#cli) · [Destaques técnicos](#destaques-técnicos) · [Saídas](#saídas) · [Modelos](#modelos) · [Arquitetura](#arquitetura--testes) · [Roadmap](#roadmap) · [Licença](#licença)

---

## O que é

**mill.tools** processa mídia, documentos e dados **diretamente no seu computador** — sem enviar arquivos para servidores, sem assinatura e sem limite de uso. Três ideias resumem o app:

- **Local por padrão.** Transcrição, IA, busca e análise rodam na sua máquina (via [Ollama](https://ollama.com)). Nuvem ([Gemini](https://ai.google.dev/) / [GLM](https://z.ai/model-api)) só se você ativar, e só na etapa de resposta — seus arquivos nunca sobem.
- **Módulos que se alimentam.** Cada ferramenta faz uma coisa bem-feita, e a saída de uma vira entrada da outra: um áudio baixado segue para a transcrição com um clique, e a cadeia inteira (`URL → áudio → transcrever → analisar`) cabe numa receita.
- **Seu acervo vira conhecimento.** Tudo que você produz é indexado localmente: pergunte em português ao seu próprio material (RAG — busca por significado + resposta citando as fontes) e navegue por temas, duplicatas e relacionados.

Acesse por uma **GUI desktop** (Flet/Flutter) ou pela **CLI** — paridade de comportamento entre as duas.

---

## Comece em 5 minutos

Pré-requisitos mínimos: [Python 3.13+](https://www.python.org/), [uv](https://docs.astral.sh/uv/), [ffmpeg](https://ffmpeg.org/download.html) e [yt-dlp](https://github.com/yt-dlp/yt-dlp) no PATH, [Ollama](https://ollama.com/download) instalado.

```bash
git clone https://github.com/mgckaled/mill.tools
cd mill.tools
uv sync

# dois modelos locais bastam para começar (resposta/análise + busca do acervo)
ollama pull gemma3:4b        && ollama create gemma3-4b-custom   -f ollama/Modelfile.gemma3-4b
ollama pull nomic-embed-text && ollama create nomic-embed-custom -f ollama/Modelfile.nomic

uv run gui.py
```

Pronto: cole uma URL do YouTube no módulo **Transcrição** e veja o texto sair. Os demais modelos, extras e chaves de nuvem são opcionais — [instalação completa](#instalação-completa) abaixo.

---

## Módulos

Seis **ferramentas** de processamento e quatro **hubs** que operam sobre as saídas de todas elas. Cada linha abre nos detalhes.

| Módulo | Tipo | Em uma linha |
|---|---|---|
| **Transcrição** | Ferramenta | Vídeo, áudio ou URL → texto (Whisper local, GPU), com formatação, análise e digest por IA |
| **Áudio** | Ferramenta | Baixe, converta e trate áudio: silêncio, ruído, velocidade, loudness — com player A/B |
| **Vídeo** | Ferramenta | Baixe, converta, corte, comprima, redimensione e legende vídeos |
| **Imagens** | Ferramenta | Converta, edite, marque d'água, remova fundo, extraia texto e descreva imagens com IA |
| **Documentos** | Ferramenta | 13 operações de PDF e QR — 100% local, incluindo OCR de PDF escaneado |
| **Dados** | Ferramenta | Consulte planilhas e CSVs **em português** (a IA traduz para SQL) ou SQL direto; gráficos |
| **Biblioteca** | Hub | Tudo que você produziu, navegável: thumbnails, busca, painel do acervo e mapa semântico |
| **IA** | Hub | Converse com o seu acervo (respostas com fontes) ou peça o comando de CLI em português |
| **Receitas** | Hub | Automação: cadeias entre módulos com presets, construtor validado e histórico |
| **Observatório** | Hub | Central de ML: saúde do índice, avaliação do RAG, atividade, falhas e tempos por modelo |

<details>
<summary><b>Transcrição</b> — detalhes</summary>

Whisper local ([faster-whisper](https://github.com/SYSTRAN/faster-whisper), GPU) sobre **URL**, **áudio/vídeo local** ou **texto** (`.txt`/`.md` pula o Whisper e vai direto à IA). Pós-processamento opcional por IA: quebra de parágrafos, **análise estruturada** dirigida por perfil (aula, reunião, entrevista…, com auto-sugestão de perfil) e **digest** condensado (~40%). Aba **Insights**: palavras-chave, resumo extrativo e entidades — instantâneos, sem LLM. Segmentos incertos são marcados com `[?]`.

</details>

<details>
<summary><b>Áudio</b> — detalhes</summary>

Download (yt-dlp), conversão e extração de faixas em fila; pós-processamento encadeável: remoção de silêncio, denoise (spectral gating), velocidade sem alterar o tom (`atempo`), normalização de loudness (EBU R128), downmix mono e reamostragem. **Presets de uma tecla** (Transcrição/Podcast/Música), reprodutor com **A/B antes/depois** e aba **Visualizar** (waveform/espectrograma → PNG).

</details>

<details>
<summary><b>Vídeo</b> — detalhes</summary>

8 operações: download, convert, trim, compress, resize, extract-audio, thumbnail e legenda (soft mux ou burn-in). Encoding 100% CPU (libx264/libx265/libvpx-vp9) — sem NVENC, por decisão.

</details>

<details>
<summary><b>Imagens</b> — detalhes</summary>

Toggle **Edição | Descrição IA**. Edição: convert, resize, **smart crop** (ponto focal), rotate, **watermark** (texto/imagem/QR, 9-grid, tiling, rotação), border, adjust, **grade de filtros**, favicon, colagem, **remoção/troca de fundo** (rembg) e **OCR** (Tesseract). Controle de **EXIF** (privacidade/copyright), visor Antes/Depois (xadrez de transparência, metadados, lote navegável) e bridge **imagem→PDF**. Descrição por visão (local ou Gemini/GLM opt-in) com 6 presets de estilo.

</details>

<details>
<summary><b>Documentos</b> — detalhes</summary>

13 operações PDF/QR via [pymupdf](https://pymupdf.readthedocs.io): merge, split, compress, rotate, watermark, stamp, encrypt, extract, **OCR híbrido** (usa a camada de texto nativa; só rasteriza páginas escaneadas), pdf↔imagens, QR e análise. Fecha o ciclo *PDF escaneado → OCR → texto → análise por IA*.

</details>

<details>
<summary><b>Dados</b> — detalhes</summary>

Consulte CSV/TSV/JSON/Parquet/XLSX em **português** — a IA traduz para SQL vendo **só o schema** (nomes e tipos de coluna; as linhas nunca saem da máquina) — ou escreva SQL direto. Motor [DuckDB](https://duckdb.org) embutido. 4 abas: Consulta, Pré-visualização, Análise com IA e **Gráfico** (barras/linha/histograma/dispersão). Detecção de linhas atípicas (IsolationForest).

</details>

<details>
<summary><b>Biblioteca</b> — detalhes</summary>

Índice navegável de tudo em `output/`: grade com thumbnails, lista, **painel analítico** (acervo por tipo/tamanho/crescimento) e **mapa semântico** (temas agrupados automaticamente). Filtro, busca (com auto-tags por conteúdo), ordenação, abrir arquivo/pasta e reenviar a outro módulo com um clique. Dedup de imagens quase-idênticas (dHash).

</details>

<details>
<summary><b>IA</b> — detalhes</summary>

Duas conversas num toggle. **Corpus**: RAG local sobre o seu acervo — pergunta em português, resposta citando as fontes `[n]`, **multi-turno de verdade** (perguntas de acompanhamento são reescritas antes da busca — o card mostra "buscou por:"), aviso quando o acervo não cobre o assunto, escopo (tudo/kind/documento), contexto ajustável (4–12 trechos) e feedback 👍/👎 por resposta. **Comandos CLI**: descreva a tarefa em português e receba o comando `uv run main.py ...` exato — gerado por introspecção dos parsers reais, validado, nunca executado. Embeddings sempre locais; Gemini/GLM opt-in só na resposta.

</details>

<details>
<summary><b>Receitas</b> — detalhes</summary>

Cadeias lineares nomeadas entre módulos (`URL → baixar áudio → transcrever → analisar`). Presets prontos + construtor com validação ao vivo, execução em lote e **histórico** (confiabilidade/velocidade por receita).

</details>

<details>
<summary><b>Observatório</b> — detalhes</summary>

Central de ML de todo o app, 5 abas. **Índice/RAG** (aninhada — Índice: inspetor e **reindexação**; **Avaliação**: harness de qualidade do RAG com golden questions, hit-rate e MRR; Painel: quais documentos dominam o índice; Uso de disco). **Status** (gates de extras, modelos Ollama, binários, provedores de nuvem, classificadores, parâmetros em vigor). **Atividade** (feed do que o ML fez em qualquer módulo). **Logs** (falhas recentes). **Tempo de resposta** (por modelo, badge nuvem/local). Leitura em quase tudo — os únicos pipelines que rodam aqui são os do próprio índice (reindexar/avaliar).

</details>

---

## Primeiro uso

**Na GUI** (`uv run gui.py`): splash → Home → **Transcrição**. Cole uma URL do YouTube, escolha o modelo Whisper (`small` é o equilíbrio) e clique em Iniciar — o painel direito mostra log e progresso ao vivo. Marque **Analisar** para receber também um relatório estruturado em Markdown. Depois, abra o hub **IA** e pergunte algo sobre o que acabou de transcrever — a resposta vem com a fonte citada.

**Na CLI**, o mesmo fluxo em uma linha:

```bash
uv run main.py transcribe "https://youtu.be/..." --format --analyze --profile lecture
```

As saídas ficam em `output/` ([estrutura](#saídas)) e alimentam automaticamente a Biblioteca e o índice da IA.

---

## Instalação completa

### Requisitos

| Requisito | Necessário para |
|---|---|
| [Python 3.13+](https://www.python.org/) · [uv](https://docs.astral.sh/uv/) | Tudo |
| [ffmpeg](https://ffmpeg.org/download.html) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) (no PATH) | Áudio, Vídeo, Transcrição |
| [Ollama](https://ollama.com/download) | IA local (formatação, análise, RAG, PT→SQL) |
| Chave [Google AI Studio](https://aistudio.google.com/apikey) | Modelos Gemini (opcional) |
| Chave [z.ai](https://z.ai/model-api) | Modelos GLM/Zhipu (opcional) |
| [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) + packs `por`/`eng` | OCR (extra `[ocr]`) |
| Modelos spaCy `pt_core_news_sm` / `en_core_web_sm` | NER do `[nlp]` (download à parte, como o Tesseract) |

DuckDB e a extensão `excel` (XLSX) são embutidos — sem instalação separada.

### Modelos locais (Ollama)

Além dos dois do [quickstart](#comece-em-5-minutos):

```bash
# formatação de parágrafos (Transcrição)
ollama pull phi4-mini    && ollama create phi4mini-custom  -f ollama/Modelfile.phi4mini
# análise / RAG de máxima qualidade (lento na CPU)
ollama pull qwen2.5:7b   && ollama create qwen7b-custom    -f ollama/Modelfile
# fallback rápido / baixa-RAM
ollama pull gemma3:1b    && ollama create gemma3-1b-custom -f ollama/Modelfile.gemma3-1b
# descrição de imagens (visão)
ollama pull moondream    && ollama create moondream-custom -f ollama/Modelfile.vision
```

### Extras opcionais

```bash
uv sync --extra ai-image   # remoção de fundo (Imagens)
uv sync --extra ocr        # OCR de PDFs escaneados (requer Tesseract no PATH)
uv sync --extra analysis --extra data-plot  # DataFrames + gráficos no módulo Dados
uv sync --extra ml         # clustering/tópicos/mapa semântico; dups/related rodam sem ele
uv sync --extra ml-viz     # projeção UMAP do mapa (opcional; PCA é o default)
uv sync --extra nlp        # keyphrases (YAKE) + entidades (spaCy NER)
uv run python -m spacy download pt_core_news_sm   # modelo de NER PT
uv run python -m spacy download en_core_web_sm    # opcional-recomendado p/ material em inglês
```

> O app base funciona sem os extras — os recursos correspondentes desabilitam-se graciosamente, com a dica de instalação no lugar.

### Modelos em nuvem (opcionais, free tier)

```bash
cp .env.example .env       # preencha GOOGLE_API_KEY=... e/ou ZHIPU_API_KEY=...
```

O `.env` é carregado quando um modelo começa com `gemini` ou `glm`; nada quebra sem ele. **Gemini**: chave no [Google AI Studio](https://aistudio.google.com/apikey); recomendado `gemini-2.5-flash` (1M tokens). **GLM**: chave no [z.ai](https://z.ai/model-api) (portal internacional — não use `open.bigmodel.cn`); recomendado `glm-4.7-flash` (200K tokens, tier grátis recorrente).

---

## CLI

Os comandos que resolvem 90% do dia a dia:

```bash
uv run main.py transcribe <URL|video.mp4|notas.txt> --format --analyze --profile lecture
uv run main.py audio podcast.mp3 --trim-silence --denoise --normalize   # limpeza completa de áudio
uv run main.py video download <URL> --quality 1080 --container mp4
uv run main.py image remove-bg foto.png --bg-mode blur
uv run main.py document ocr scanned.pdf --lang por
uv run main.py data query vendas.csv "total por cliente, do maior para o menor" --out xlsx
uv run main.py ai "o que eu disse sobre faster-whisper?"                # pergunta ao acervo
uv run main.py ai --cmd "corta o silêncio do podcast.mp3 e acelera 1.25x"  # NL→CLI: imprime o comando
uv run main.py recipe run "YouTube → transcrição completa" "https://youtu.be/..."
```

<details>
<summary><b>Referência completa por módulo</b></summary>

```bash
# Áudio — download/conversão/extração + pós-processamento
uv run main.py audio <URL|arquivo> --fmt mp3 --quality 320 --denoise --normalize
uv run main.py audio aula.mp4 --mono --sample-rate 16000 --trim-silence   # pronto p/ transcrição
uv run main.py audio podcast.mp3 --speed 1.5                              # 1,5× sem alterar o tom
uv run main.py audio-viz musica.mp3 --spectrogram                         # waveform/espectrograma PNG

# Vídeo — download | convert | trim | compress | resize | extract-audio | thumbnail | subtitle
uv run main.py video subtitle video.mp4 --subs legenda.srt --mode soft

# Imagens — convert | resize | crop | rotate | watermark | border | adjust | filter |
#           favicon | contact-sheet | remove-bg | describe | exif | ocr
uv run main.py image convert photo.jpg --fmt webp --quality 85
uv run main.py image crop photo.jpg --mode focal --ratio 1:1 --focal-x 0.5 --focal-y 0.35
uv run main.py image watermark photo.jpg --mode qr --text "https://mill.tools" --position bottom-right
uv run main.py image exif photo.jpg --strip-gps          # privacidade (remove localização)
uv run main.py image ocr captura.png --lang por          # texto → .txt indexável no RAG

# Documentos — merge | split | compress | rotate | watermark | stamp | encrypt | extract |
#              ocr | pdf-to-images | images-to-pdf | qr
uv run main.py document split doc.pdf --pages "1-3,5,8-"

# Dados — consulta em PT ou SQL; converte, perfila, plota, acha atípicos
uv run main.py data query dados.parquet "SELECT * FROM dados LIMIT 10" --sql
uv run main.py data convert dados.csv --out parquet
uv run main.py data profile dados.csv
uv run main.py data plot vendas.csv "total por produto" --kind bar
uv run main.py data outliers vendas.csv --contamination 0.05

# Biblioteca — índice de output/ como tabela (+ dashboard e dedup de imagens)
uv run main.py library list --kind audio --since 7d --sort size
uv run main.py library stats --top 10
uv run main.py library dedup-images --max-distance 8

# IA — RAG local (busca híbrida BM25+denso, cita fontes) + ML semântico + avaliação
uv run main.py ai index
uv run main.py ai "pergunta" --scope arquivo.txt --k 8 --model gemini-2.5-flash
uv run main.py ai stats | ai dups | ai topics | ai map | ai related <path>
uv run main.py ai classify|keywords|summary|entities <path>
uv run main.py ai eval            # roda a avaliação do RAG (golden questions)
uv run main.py ai eval add --question "..." --expect <arquivo>

# Receitas
uv run main.py recipe list | recipe run "<nome>" <URL_OR_FILE> | recipe stats

# Observatório (leitura)
uv run main.py observatory status | activity --limit 15 | logs | disk-usage
```

**Flags da Transcrição**: `--wm` (modelo Whisper, `small` default) · `--language` (auto) · `--beam-size` (1=rápido, 5=preciso) · `--format`/`--fm` · `--analyze`/`--am` · `--profile` · `--prompt`/`--pm` · `--verbose`. Modelos `gemini-*`/`glm-*` nas flags de IA roteiam para a nuvem (exigem a chave correspondente).

</details>

> **Cookies do YouTube (anti-bot)**: se aparecer "Sign in to confirm you're not a bot", ative os cookies do navegador em **Configurações** (opt-in, lidos localmente). Atenção: cookies de conta logada podem fazer o YouTube exigir *PO Token* e o download falhar — nesse caso, desative-os.

---

## Destaques técnicos

| Característica | Detalhe |
|---|---|
| Transcrição local | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + ctranslate2, aceleração GPU, **sem PyTorch** |
| RAG local | embeddings Ollama (`nomic-embed-text` com prefixos de tarefa, CPU), vector store numpy, busca **híbrida** (cosseno + [BM25](https://github.com/dorianbrown/rank_bm25) via Reciprocal Rank Fusion), **conversa multi-turno** (condensação de pergunta local), diversificação MMR do contexto, resposta com fontes `[n]` e **avaliação embutida** (golden questions → hit-rate/MRR) |
| Dados | [DuckDB](https://duckdb.org) in-process, torch-free; PT→SQL pela IA vendo só o schema — as linhas nunca saem da máquina |
| ML local | `core/ml` **torch-free** sobre os embeddings do RAG (sem recálculo): duplicatas/relacionados por cosseno + **MMR** (numpy puro); clustering (HDBSCAN/k-means auto-k), rótulos c-TF-IDF e mapa 2D (PCA/t-SNE) via [scikit-learn](https://scikit-learn.org) (`[ml]`); UMAP opcional (`[ml-viz]`); **classificação zero-shot→supervisionada** por domínio; outliers (IsolationForest); dedup de imagens (dHash) |
| NLP textual | `core/text` **torch-free** (`[nlp]`): keyphrases ([YAKE](https://github.com/LIAAD/yake)), resumo extrativo (TextRank self-contained, com limpeza de boilerplate) e entidades ([spaCy](https://spacy.io) CNN, PT/EN, glossário de domínio opcional) |
| Áudio | noisereduce (spectral gating, CPU) + ffmpeg loudnorm (EBU R128, 2 passes), silenceremove e atempo |
| Vídeo | yt-dlp + ffmpeg CPU-only (libx264/libx265/libvpx-vp9) — sem NVENC |
| Imagens | Pillow (transforms, EXIF, smart crop, watermark/QR, filtros) + rembg/ONNX (CPU); OCR Tesseract (`[ocr]`); visão via Ollama ou nuvem opt-in |
| Documentos | [pymupdf](https://pymupdf.readthedocs.io) + Tesseract (OCR híbrido, opcional) |
| Interface | [Flet 0.85](https://flet.dev) (Flutter desktop): log em tempo real, design system próprio, ajuda contextual (ⓘ) |
| IA | Ollama local por padrão; Gemini/GLM opt-in por prefixo de modelo (`gemini-*`/`glm-*`) |

> **Decisão consciente: sem PyTorch.** O app base é torch-free. IA de áudio com torch (DeepFilterNet/Demucs) ficaria isolada num extra opcional.

---

## Saídas

Tudo é gravado em `output/`, organizado por tipo — e é daí que a Biblioteca e o índice da IA se alimentam:

```text
output/
├── audio/          source/ (downloads) · processed/ (conversões, extrações)
├── video/          source/ · processed/
├── image/          source/ · processed/
├── document/       processed/
├── data/           consultas, conversões e perfis do módulo Dados
└── transcriptions/ text/ · analysis/ (--analyze) · digest/ (--prompt) · subtitles/
```

- **Transcrição** (`text/*.txt`): cabeçalho de metadados + texto; segmentos incertos marcados com `[?]`.
- **Análise** (`analysis/*.md`): relatório estruturado perfil-dirigido, em PT-BR.
- **Digest** (`digest/*.txt`): versão condensada (~40%), pronta para colar como contexto.

---

## Modelos

**Whisper** (`--wm`): `tiny` → `large-v3` (mais rápido → mais preciso); `small` é o padrão equilibrado.

**Ollama** (local, padrão) — customizados via Modelfiles em `ollama/` (CPU-pinned, `num_gpu 0`):

| Modelo | Papel | Tamanho |
|---|---|---|
| `gemma3-4b-custom` | Análise · Digest · RAG · PT→SQL (**padrão**) | ~3,3 GB |
| `nomic-embed-custom` | Embeddings do RAG (768-dim) | ~275 MB |
| `phi4mini-custom` | Formatação de parágrafos | ~2,5 GB |
| `gemma3-1b-custom` | Fallback rápido / baixa-RAM | ~815 MB |
| `qwen7b-custom` | Análise/RAG de máxima qualidade (lento na CPU) | ~4,7 GB |
| `moondream-custom` | Descrição de imagens (visão) | ~1,7 GB |

**Gemini** (nuvem, opt-in): prefixo `gemini-*`; janela de 1M tokens dispensa chunking; `gemini-2.5-flash` recomendado — também descreve imagens (multimodal nativo).

**GLM/Zhipu** (nuvem, opt-in): prefixo `glm-*`, via API OpenAI-compatible; 200K tokens; `glm-4.7-flash` recomendado (tier grátis recorrente) e `glm-4.6v-flash` para visão.

---

## Arquitetura · Testes

`src/core/` é **puro** (sem Flet, dependências de rede/modelo injetáveis) e reutilizável por CLI e GUI; `src/gui/` é a camada Flet; `src/cli/` os subcomandos.

```text
src/
├── transcriber · formatter · analyzer · prompter · llm_factory · llm_utils
├── analysis/   perfis de análise (puro)
├── core/       PURO — audio · video · image · document · library · rag · ml · text · observatory · recipes · data
├── cli/        1 módulo por subcomando + bus
└── gui/        app (rail + hubs) · home · splash · modules/ · theme/ · views/
```

```bash
uv run pytest -m unit            # unitários — rápido, sem ffmpeg/rede/GPU
uv run pytest -m integration     # integração — requer ffmpeg
uv run pytest --cov=src --cov-report=html
```

**1,2 mil+ testes unitários**, cobertura agregada >90% (branch on; GUI excluída por não ser testável headless). Linter **ruff**; suíte verde + ruff limpo antes de qualquer commit. Documentação de desenvolvimento: [`CLAUDE.md`](CLAUDE.md), [`docs/`](docs/README.md) e as skills em `.claude/skills/`.

---

## Atalhos da GUI

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Inicia o pipeline (se a entrada for válida) |
| `Esc` | Cancela o pipeline em andamento |

---

## Roadmap

A seguir: **PR9.2** encadeamento em estágios nas Receitas · **PR3.1-B** IA de áudio com torch (extra isolado `[ai-audio]`) · melhorias em Imagens (batch rename, upscale ONNX, HEIC) · streaming da resposta da IA · timestamps nas citações do RAG + capítulos automáticos de transcrição.

Histórico completo de marcos e decisões: [`docs/HISTORY.md`](docs/HISTORY.md) · planos: [`docs/plans/`](docs/plans/).

---

## Licença

[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/) — uso pessoal e não-comercial livre.
