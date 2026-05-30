# mill.tools

Multiferramenta pessoal para processamento de áudio, vídeo e transcrição. O módulo de Transcrição usa [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (100% local, com GPU) e [LangChain](https://www.langchain.com/) para formatação, análise e condensação — com escolha de provider: [Ollama](https://ollama.com) local (default) ou [Google Gemini](https://ai.google.dev/) na nuvem (free tier).

---

## Como funciona

**yt-dlp busca metadados** → **yt-dlp baixa só o áudio em MP3** → **Whisper carrega na GPU (CUDA int8_float32)** → **VAD filtra silêncio e ruído** → **Whisper detecta idioma e transcreve segmento por segmento** → **segmentos de baixa confiança recebem marcador `[?]` no `.txt`** → **`--format`: phi4mini-custom insere quebras de parágrafo sem alterar palavras** → **`--analyze`: qwen7b-custom extrai 10 campos em JSON — `summary`, `key_points`, `action_items`, `key_concepts`, `tools_mentioned`, `metrics`, `quotes`, `assumptions`, `vocabulary`, `sentiment_arc` — traduz para PT-BR se necessário e gera `.md`** → **`--prompt`: qwen7b-custom condensa a transcrição para ~40% do tamanho removendo filler e CTAs, salva em `prompt_ready/`**

---

## Requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/download.html) no PATH
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) no PATH
- [Ollama](https://ollama.com/download) (apenas se usar modelos locais para `--format`/`--analyze`/`--prompt`)
- Chave da [Google AI Studio](https://aistudio.google.com/apikey) (apenas se usar modelos Gemini)
- [Flet](https://flet.dev) — incluído nas dependências do projeto (apenas para a GUI)

---

## Setup

```bash
git clone https://github.com/your-username/yt-transcriber
cd yt-transcriber
uv sync
```

### Opção A — usar modelos locais (Ollama)

Instale o Ollama e configure os modelos:

```bash
# modelo para análise
ollama pull qwen2.5:7b
ollama create qwen7b-custom -f ollama/Modelfile

# modelo para formatação de parágrafos
ollama pull phi4-mini
ollama create phi4mini-custom -f ollama/Modelfile.phi4mini
```

### Opção B — usar Google Gemini (free tier)

1. Gere uma chave em https://aistudio.google.com/apikey
2. Copie `.env.example` para `.env` e cole a chave:

```bash
cp .env.example .env
# edite .env e preencha GOOGLE_API_KEY=...
```

O `.env` é carregado automaticamente sempre que `--fm`, `--am` ou `--pm` receber um nome de modelo iniciado por `gemini`. O Ollama continua sendo o default — nada quebra se você não criar o `.env`.

**Modelo recomendado:** `gemini-2.5-flash` — free tier robusto, contexto de 1M tokens (dispensa chunking), bom em saída JSON estruturada.

---

## Uso

### GUI desktop

```bash
uv run gui.py
```

Abre a interface gráfica com layout split: formulário à esquerda e painel de pipeline à direita. Todos os parâmetros do CLI estão disponíveis na GUI.

### Transcrição (CLI)

```bash
uv run main.py <YOUTUBE_URL> [options]
```

### Transcrição + análise

```bash
uv run main.py <YOUTUBE_URL> --analyze
```

### Análise standalone (sobre transcrição existente)

```bash
uv run -m src output/transcriptions/text/transcricao_ovabeV.txt
```

---

## Flags

| Flag            | Default           | Descrição                                                    |
| --------------- | ----------------- | ------------------------------------------------------------ |
| `--wm`          | `small`           | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v3-turbo`, `large-v3` |
| `--language`    | auto              | Código do idioma (`en`, `pt`, etc.)                          |
| `--threads`     | `2`               | Threads CPU (só em fallback CPU)                             |
| `--beam-size`   | `1`               | Beam size: `1` = rápido, `5` = preciso                       |
| `--output-name` | auto              | Nome customizado do arquivo de saída                         |
| `--format`      | off               | Insere quebras de parágrafo via LLM                          |
| `--fm`          | `phi4mini-custom` | Modelo para formatação — Ollama tag ou `gemini-*`            |
| `--analyze`     | off               | Roda análise estruturada após transcrição                    |
| `--am`          | `qwen7b-custom`   | Modelo para análise — Ollama tag ou `gemini-*`               |
| `--prompt`      | off               | Gera versão condensada para uso como contexto em prompts     |
| `--pm`          | `qwen7b-custom`   | Modelo para condensação — Ollama tag ou `gemini-*`           |
| `--verbose`     | off               | Ativa logging DEBUG                                          |

---

## Exemplos

```bash
# transcrição básica (detecção automática de idioma)
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0

# forçar idioma + maior precisão
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 --language pt --beam-size 3

# transcrição + formatação de parágrafos
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 --format

# transcrição + análise estruturada
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 --analyze

# pipeline completo: formatação + análise com transcrição no relatório
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 --format --analyze

# gerar versão condensada para uso como contexto em prompts
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 --prompt

# whisper medium + modelos customizados
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 --wm medium --fm phi4mini-custom --am qwen7b-custom --format --analyze --prompt

# tudo na nuvem: Whisper local + Gemini nas 3 etapas (requer GOOGLE_API_KEY no .env)
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 \
  --format --fm gemini-2.5-flash \
  --analyze --am gemini-2.5-flash \
  --prompt  --pm gemini-2.5-flash

# híbrido: formatação local rápida + análise mais sofisticada via Gemini
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 --format --analyze --am gemini-2.5-flash

# análise standalone sobre transcrição existente
uv run -m src output/transcriptions/text/transcricao_ovabeV.txt

# análise standalone usando Gemini
uv run -m src output/transcriptions/text/transcricao_ovabeV.txt --model gemini-2.5-flash
```

---

## Estrutura de arquivos

```text
mill-tools/
├── main.py                    — entry point, CLI
├── gui.py                     — entry point, GUI desktop (Flet)
├── .env.example               — template do .env (GOOGLE_API_KEY para Gemini)
├── src/
│   ├── __init__.py
│   ├── __main__.py            — entry point do analyzer standalone
│   ├── transcriber.py         — transcrição via faster-whisper
│   ├── llm_factory.py         — roteia gemini-* → Google, demais → Ollama
│   ├── formatter.py           — formatação de parágrafos via LLM
│   ├── analyzer.py            — análise estruturada via LangChain
│   ├── prompter.py            — condensação para uso como contexto em prompts
│   ├── utils.py               — logging, validação, metadata, download
│   └── gui/
│       ├── app.py             — layout split e ciclo de vida do pipeline
│       ├── events.py          — EventBus, PipelineEvent, LogEventHandler
│       ├── settings.py        — persistência de configurações (~/.mill-tools/)
│       ├── workers.py         — execução do pipeline em thread background
│       └── views/
│           ├── form_view.py   — formulário de configuração
│           ├── progress_view.py — logs em tempo real e barra de progresso
│           └── result_view.py — resultados em abas (Transcrição/Análise/Digest)
├── ollama/
│   ├── Modelfile              — config do qwen7b-custom
│   └── Modelfile.phi4mini     — config do phi4mini-custom
└── output/
    ├── audio/
    │   ├── source/            — áudios baixados de URLs (.mp3)
    │   └── processed/         — áudios processados/convertidos
    ├── video/
    │   └── processed/         — vídeos baixados/convertidos
    └── transcriptions/
        ├── text/              — transcrições brutas (.txt)
        ├── analysis/          — análises estruturadas (.md)
        └── digest/            — versões condensadas para uso como contexto (.txt)
```

> **Arquivos gerados antes da migração** (em `audios/` e `transcriptions/`) continuam acessíveis nos caminhos originais — não foram movidos automaticamente.

---

## GUI desktop

A interface gráfica oferece todos os recursos do CLI em um layout split permanente:

```
┌─ mill.tools ──────────────────────────────────────────────[☀]┐
├──────────────────────┬────────────────────────────────────────┤
│  Vídeo               │  Pipeline    Resultados                │
│  [URL ____________]  │                                        │
│                      │  Inicie o pipeline pelo formulário →   │
│  Transcrição         │  ──────────────────────────────────    │
│  Whisper  [small ▼]  │  [i] Fetching video metadata...        │
│  Idioma   [auto  ▼]  │  [i] Title: Como alcancei meu sonho    │
│  Beam ●──○ 1         │  [»] Audio already exists...           │
│                      │  [*] Loading model 'small' on CUDA...  │
│  ☐ Formatar          │  [~] Transcribing...                   │
│    [phi4mini ▼]      │  [i] Detected language: pt (100%)      │
│                      │  Eu sempre tive um sonho...            │
│  ☑ Analisar          │  ────────────────────────────────      │
│    [gemini   ▼]      │  ╔══ title    : Como alcancei...  ╗    │
│                      │  ║  duration : 00:05:27           ║    │
│  ☐ Prompt-ready      │  ║  elapsed  : 55s                ║    │
│    [gemini   ▼]      │  ╚══════════════════════════════  ╝    │
│                      │  [✓] Pipeline complete.                 │
│  [Google API Key]    │                               [Cancelar]│
│  [⏳ Executando...]  │                                        │
└──────────────────────┴────────────────────────────────────────┘
```

### Funcionalidades da GUI

- **Layout split permanente** — formulário sempre visível à esquerda; sem navegação entre telas
- **Logs em tempo real** com cores por prefixo: `[i]` azul · `[*]` ciano · `[~]` amarelo · `[✓]` verde · `[!]` vermelho · `[»]` cinza · `[d]` cinza escuro
- **Barra de progresso determinada** durante a transcrição — calcula `segment.end / audio_duration`
- **Card de resumo** ao fim da transcrição (título, duração, tempo decorrido, segmentos flagados)
- **Aba Resultados** habilitada automaticamente ao fim do pipeline — com sub-abas Transcrição / Análise / Prompt-ready
- **Copiar conteúdo** e **abrir pasta** diretamente na aba de resultados
- **Dropdowns de modelo** para formatação, análise e prompt-ready
- **Botão Iniciar** desabilita com ampulheta durante execução
- `Ctrl+Enter` inicia o pipeline · `Esc` cancela

### Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Inicia o pipeline (se URL válida) |
| `Esc` | Cancela o pipeline em andamento |

---

## Output

Cada transcrição (.txt) começa com um cabeçalho de metadados:

```text
title:        Claude Design Full Course
channel:      Some Channel
upload_date:  2024-03-15
duration:     02:14:33
language:     en
tags:         design, ai, figma, ...
url:          https://www.youtube.com/watch?v=ovabeVoWrA0

----------------------------------------------------------------

[transcription text...]
```

### Transcrição (`.txt`)

Cabeçalho de metadados seguido do texto corrido. Segmentos onde o Whisper teve baixa confiança são sinalizados com `[?]` diretamente no texto — indicam trechos que merecem revisão manual (ruído, sotaque, vocabulário incomum). O terminal exibe a contagem de segmentos flagados ao final da transcrição.

Critérios de flag: `avg_logprob < -1.0` (probabilidade média dos tokens abaixo do limiar) ou `no_speech_prob > 0.6` (alta chance de o trecho ser silêncio ou ruído).

### Análise (`.md`) — `--analyze`

Relatório estruturado com 10 campos extraídos pelo LLM:

| Campo | Descrição |
| ----- | --------- |
| `summary` | Parágrafo de 3–5 frases resumindo o conteúdo principal |
| `key_points` | 5–10 pontos-chave como frases completas (mín. 12 palavras), explicando o *como* e o *por quê* |
| `action_items` | Passos práticos ou recomendações mencionados no vídeo |
| `key_concepts` | Conceitos técnicos centrais no formato `Termo: definição` |
| `tools_mentioned` | Ferramentas, bibliotecas, plataformas ou tecnologias citadas |
| `metrics` | Números, estatísticas e quantidades com contexto |
| `quotes` | Frases marcantes ou citações quase literais do speaker |
| `assumptions` | Premissas implícitas que o speaker toma como verdade |
| `vocabulary` | Jargões e termos de nicho no formato `Termo: definição` |
| `sentiment_arc` | Evolução do tom ao longo do vídeo em uma frase |

Se o resultado não estiver em português, é traduzido automaticamente para PT-BR. Quando `--format --analyze` são usados em conjunto, a transcrição formatada é incluída no final do relatório.

### Digest (`.txt`) — `--prompt`

Versão condensada da transcrição salva em `output/transcriptions/digest/`, com ~40% do tamanho original. Remove cumprimentos, CTAs, patrocinadores e frases de preenchimento, mantendo todo o conteúdo técnico. Otimizado para ser colado como contexto em qualquer prompt de LLM.

---

## Modelos Whisper

| Modelo           | Velocidade | Precisão  |
| ---------------- | ---------- | --------- |
| `tiny`           | mais rápido|  baixa    |
| `small`          | rápido     | boa       |
| `medium`         | moderado   | muito boa |
| `large-v3-turbo` | lento      | excelente |
| `large-v3`       | mais lento | melhor    |

## Modelos Ollama (locais, default)

| Modelo             | Uso          | Tamanho | Qualidade |
| ------------------ | ------------ | ------- | --------- |
| `phi4mini-custom`  | `--format`   | 2.5 GB  | básica    |
| `qwen7b-custom`    | `--analyze`  | 4.7 GB  | boa       |

## Modelos Gemini (nuvem, free tier)

Para usar Gemini em qualquer uma das três etapas, passe o nome do modelo via `--fm`, `--am` ou `--pm`. Roteamento é por prefixo — qualquer nome começando com `gemini` vai para o Google.

| Modelo                  | Uso recomendado          | Free tier (RPD) | Contexto |
| ----------------------- | ------------------------ | --------------- | -------- |
| `gemini-2.5-flash`      | `--analyze`, `--prompt`  | sim             | 1M       |
| `gemini-2.5-flash-lite` | `--format` (mais rápido) | sim             | 1M       |

Como Gemini tem janela de 1M tokens, o `--analyze` e o `--prompt` **dispensam chunking** quando o provider é Gemini — processam o texto inteiro em uma única chamada, mais coerente e gastando menos requests do RPD. O `--format` mantém chunking porque a tarefa é localizada por parágrafo.

Consulte os limites ativos do seu projeto em <https://aistudio.google.com/rate-limit>. Cotas são por projeto e RPD reseta à meia-noite do horário do Pacífico (≈ 04:00 BRT).

Os modelos customizados são criados a partir dos Modelfiles em `ollama/`. Ajuste os parâmetros conforme o seu hardware:

```text
FROM qwen2.5:7b

# Número de camadas offloadas para GPU (0 = só CPU, -1 = tudo na GPU)
PARAMETER num_gpu 10

# Threads CPU usadas nas camadas que ficam na CPU
PARAMETER num_thread 4

# Tamanho do contexto em tokens (padrão do modelo base se omitido)
PARAMETER num_ctx 4096

# Temperatura: 0.0 = determinístico, 1.0 = criativo
PARAMETER temperature 0.3

# Penaliza repetição de tokens recentes
PARAMETER repeat_penalty 1.1

# System prompt fixo (opcional)
SYSTEM """Você é um assistente especializado em análise de conteúdo."""
```

Depois de editar, recrie o modelo:

```bash
ollama create qwen7b-custom -f ollama/Modelfile
ollama create phi4mini-custom -f ollama/Modelfile.phi4mini
```
