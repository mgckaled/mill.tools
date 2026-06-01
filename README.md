<div align="center">

<img src="assets/logo/mill-logo-wordmark.png" alt="mill.tools" width="380">

**Multiferramenta pessoal para áudio, vídeo e transcrição — local-first, com GUI e CLI.**

![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9)
![Flet](https://img.shields.io/badge/GUI-Flet%200.85-02569B)
![Whisper](https://img.shields.io/badge/faster--whisper-GPU-FFB000)

</div>

---

## Visão geral

**mill.tools** é uma multiferramenta extensível, organizada em **módulos** acessíveis por uma barra lateral na GUI desktop (e via CLI). A transcrição roda **100% local** com [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (aceleração GPU, sem PyTorch) e usa [LangChain](https://www.langchain.com/) para formatação, análise e condensação — com escolha de provider: [Ollama](https://ollama.com) local (padrão) ou [Google Gemini](https://ai.google.dev/) na nuvem (free tier).

### Recursos

- 🎙️ **Transcrição local** com Whisper (faster-whisper / GPU), detecção automática de idioma e marcação de trechos de baixa confiança.
- 🧠 **Pós-processamento por LLM** — formatação em parágrafos, análise estruturada (10 campos) e digest condensado para uso como contexto.
- 🔀 **Provider flexível** — Ollama local por padrão; Gemini na nuvem por prefixo de modelo, sem mudar o fluxo.
- 🎵 **Módulo Áudio** — download (YouTube, SoundCloud, etc. via yt-dlp), conversão e extração de áudio, em fila, com capa/metadados embutidos.
- 🖼️ **Módulo Imagens** — conversão entre 8 formatos (JPG, PNG, WebP, AVIF, TIFF, BMP, GIF, ICO), controle de qualidade e visor de pré-visualização integrado.
- 🖥️ **GUI desktop** (Flet) com acompanhamento em tempo real estilo CLI, barra de progresso determinada e spinner animado.
- 🔗 **Bridge Áudio → Transcrição** — botão "Transcrever este arquivo" envia o arquivo processado diretamente para o módulo de Transcrição.
- 🎨 **Design System** — paleta unificada com acento dourado, suporte a temas claro/escuro e contraste WCAG 2.1.
- ℹ️ **Ajuda contextual** — ícone ⓘ em todos os controles: tooltip no hover, modal com detalhes ao clicar.

### Módulos

| Módulo | Status | O que faz |
|---|---|---|
| **Transcrição** | ✅ | Whisper local + formatação/análise/digest via LLM |
| **Áudio** | ✅ | Download, conversão e extração de áudio (fila, capa/metadados) |
| **Vídeo** | 🚧 | Download/conversão/extração (planejado — PR4) |
| **Imagens** | ✅ | Conversão de formato/qualidade, download de URL, visor de pré-visualização (PR-IMG-1) |

---

## Requisitos

- [Python 3.13+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/download.html) no PATH
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) no PATH
- [Ollama](https://ollama.com/download) — apenas se usar modelos locais (`--format`/`--analyze`/`--prompt`)
- Chave da [Google AI Studio](https://aistudio.google.com/apikey) — apenas se usar modelos Gemini

---

## Instalação

```bash
git clone https://github.com/your-username/mill-tools
cd mill-tools
uv sync
```

### Opção A — modelos locais (Ollama)

```bash
# análise
ollama pull qwen2.5:7b
ollama create qwen7b-custom -f ollama/Modelfile

# formatação de parágrafos
ollama pull phi4-mini
ollama create phi4mini-custom -f ollama/Modelfile.phi4mini
```

### Opção B — Google Gemini (free tier)

```bash
cp .env.example .env       # edite e preencha GOOGLE_API_KEY=...
```

O `.env` é carregado automaticamente quando `--fm`, `--am` ou `--pm` recebe um modelo iniciado por `gemini`. O Ollama continua sendo o padrão — nada quebra se você não criar o `.env`. **Modelo recomendado:** `gemini-2.5-flash` (free tier robusto, contexto de 1M tokens, boa saída JSON).

---

## Uso

### GUI desktop

```bash
uv run gui.py
```

Abre com uma splash screen animada e, em seguida, a interface com **barra lateral de módulos** (NavigationRail). Cada módulo tem layout split: formulário à esquerda, painel de acompanhamento (log em tempo real + barra de progresso + spinner) à direita.

Durante um pipeline em execução a troca de módulo é bloqueada — os logs e a barra de progresso são preservados mesmo ao navegar entre módulos.

### CLI — Transcrição

```bash
# básico (idioma automático)
uv run main.py <YOUTUBE_URL>

# + formatação e análise
uv run main.py <YOUTUBE_URL> --format --analyze

# análise standalone (sobre transcrição existente)
uv run -m src output/transcriptions/text/transcricao_ovabeV.txt
```

### Referência de flags

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
| `--prompt`      | off               | Gera versão condensada (digest)                              |
| `--pm`          | `qwen7b-custom`   | Modelo para condensação — Ollama tag ou `gemini-*`           |
| `--verbose`     | off               | Ativa logging DEBUG                                          |

### Exemplos

```bash
# forçar idioma + maior precisão
uv run main.py <URL> --language pt --beam-size 3

# pipeline completo: formatação + análise (transcrição incluída no relatório)
uv run main.py <URL> --format --analyze

# tudo na nuvem: Whisper local + Gemini nas 3 etapas (requer GOOGLE_API_KEY)
uv run main.py <URL> \
  --format  --fm gemini-2.5-flash \
  --analyze --am gemini-2.5-flash \
  --prompt  --pm gemini-2.5-flash

# híbrido: formatação local rápida + análise sofisticada via Gemini
uv run main.py <URL> --format --analyze --am gemini-2.5-flash

# análise standalone usando Gemini
uv run -m src output/transcriptions/text/transcricao_ovabeV.txt --model gemini-2.5-flash
```

---

## Saídas

Tudo é gravado em `output/`, organizado por tipo.

### Transcrição — `output/transcriptions/text/*.txt`

Cabeçalho de metadados seguido do texto corrido:

```text
title:        Claude Design Full Course
channel:      Some Channel
upload_date:  2024-03-15
duration:     02:14:33
language:     en
url:          https://www.youtube.com/watch?v=ovabeVoWrA0
----------------------------------------------------------------
[transcription text...]
```

Segmentos de baixa confiança são marcados com `[?]` no texto (revisão manual sugerida). Critérios: `avg_logprob < -1.0` ou `no_speech_prob > 0.6`. O total de flags é exibido ao final.

### Análise — `output/transcriptions/analysis/*.md` (`--analyze`)

Relatório estruturado com 10 campos extraídos pelo LLM:

| Campo | Descrição |
| ----- | --------- |
| `summary` | Resumo de 3–5 frases do conteúdo principal |
| `key_points` | 5–10 pontos-chave (frases completas, o *como* e o *porquê*) |
| `action_items` | Passos práticos ou recomendações |
| `key_concepts` | Conceitos centrais no formato `Termo: definição` |
| `tools_mentioned` | Ferramentas, bibliotecas, plataformas citadas |
| `metrics` | Números e estatísticas com contexto |
| `quotes` | Frases marcantes / citações |
| `assumptions` | Premissas implícitas do speaker |
| `vocabulary` | Jargões no formato `Termo: definição` |
| `sentiment_arc` | Evolução do tom em uma frase |

Resultados fora do português são traduzidos automaticamente para PT-BR. Com `--format --analyze`, a transcrição formatada é incluída no fim do relatório.

### Digest — `output/transcriptions/digest/*.txt` (`--prompt`)

Versão condensada (~40% do tamanho), sem cumprimentos/CTAs/patrocinadores, mantendo todo o conteúdo técnico. Otimizada para colar como contexto em prompts de LLM.

### Áudio — `output/audio/`

Downloads em `source/`; conversões/extrações em `processed/`.

### Imagens — `output/image/`

Downloads de URL em `source/`; imagens convertidas em `processed/`.

---

## Modelos

### Whisper

| Modelo           | Velocidade  | Precisão  |
| ---------------- | ----------- | --------- |
| `tiny`           | mais rápido | baixa     |
| `small`          | rápido      | boa       |
| `medium`         | moderado    | muito boa |
| `large-v3-turbo` | lento       | excelente |
| `large-v3`       | mais lento  | melhor    |

### Ollama (local, padrão)

| Modelo            | Uso          | Tamanho | Qualidade |
| ----------------- | ------------ | ------- | --------- |
| `phi4mini-custom` | `--format`   | 2.5 GB  | básica    |
| `qwen7b-custom`   | `--analyze`  | 4.7 GB  | boa       |

Os modelos customizados vêm dos Modelfiles em `ollama/`. Ajuste conforme o hardware (`num_gpu`, `num_thread`, `num_ctx`, `temperature`) e recrie:

```bash
ollama create qwen7b-custom -f ollama/Modelfile
ollama create phi4mini-custom -f ollama/Modelfile.phi4mini
```

### Gemini (nuvem, free tier)

Roteamento por prefixo: qualquer nome começando com `gemini` vai para o Google. Como a janela é de 1M tokens, `--analyze` e `--prompt` **dispensam chunking** com Gemini (processam o texto inteiro de uma vez); `--format` mantém chunking por ser tarefa localizada.

| Modelo                  | Uso recomendado          | Free tier | Contexto |
| ----------------------- | ------------------------ | --------- | -------- |
| `gemini-2.5-flash`      | `--analyze`, `--prompt`  | sim       | 1M       |
| `gemini-2.5-flash-lite` | `--format` (mais rápido) | sim       | 1M       |

Limites do projeto em <https://aistudio.google.com/rate-limit> (RPD reseta à meia-noite do Pacífico, ≈ 04:00 BRT).

---

## Design System

A GUI usa um Design System interno em `src/gui/theme/`, construído sobre o Material 3 do Flet 0.85. Todos os módulos consomem as mesmas fábricas — adicionar um novo módulo não requer reinventar botões, cores ou espaçamento.

### Paleta

| Token | Dark | Light | Uso |
|---|---|---|---|
| `primary` | `#F4A63C` | `#E0982F` | Acento único — botões, foco, seleção ativa |
| `bg` | `#101012` | `#F6F8FB` | Fundo da janela |
| `surface` | `#1E1E22` | `#FFFFFF` | Painéis e cards |
| `outline` | `#5A5A62` | `#7890A0` | Bordas de containers |
| `outline_variant` | `#36363C` | `#AEBCC8` | Divisórias hairline |

Fonte de UI: **Verdana**. Fonte mono (log): **JetBrains Mono** / **Consolas** (escala tipográfica `mono`).

### Componentes disponíveis

| Fábrica | Módulo | Descrição |
|---|---|---|
| `primary_button` | `buttons` | Ação primária — herda dourado do tema |
| `secondary_button` | `buttons` | Ação secundária — contorno |
| `danger_button` | `buttons` | Ação destrutiva — vermelho semântico |
| `action_button` | `buttons` | Ação de link/secundária — azul info por padrão, acento configurável |
| `segmented_selector` | `buttons` | Grade de chips clicáveis (formato, bitrate…) |
| `output_card` | `cards` | Card de saída — borda colorida, ícone, nome, botão abrir pasta |
| `labeled_field` | `inputs` | Rótulo + controle + helper + ⓘ opcional |
| `switch_row` | `inputs` | Switch com cor ativa do tema |
| `slider_row` | `inputs` | Slider com rótulo + ⓘ opcional |
| `log_line` | `feedback` | Linha de log monoespaçada com cor por prefixo |
| `spinner` | `feedback` | Cata-vento animado — retorna `(control, start, stop)` |
| `summary_card` | `feedback` | Card de resumo ao fim do pipeline |
| `section_title` | `feedback` | Título de seção de resultados |
| `section_label` | `layout` | Rótulo de seção simples (sem ⓘ) |
| `section` | `layout` | Grupo rótulo + controles + ⓘ opcional |
| `hairline` | `layout` | Divisória fina 1px |
| `module_scaffold` | `layout` | Layout split form \| painel |
| `help_icon` | `help` | ⓘ com tooltip estilizado e modal opcional |
| `help_icon_for` | `help` | Lookup no registro central por chave |

### Ajuda contextual (ⓘ)

O arquivo `src/gui/help_content.py` centraliza todo o conteúdo de ajuda, separado da UI. Cada controle recebe uma **chave** (`"módulo.campo"`) — nenhuma string de ajuda fica espalhada nos formulários.

**Comportamento:**
- **Hover** → tooltip estilizado (fundo `surface_container`, bordas arredondadas, 300 ms de delay)
- **Clique** (apenas quando há texto longo) → `AlertDialog` com título e corpo detalhado

**Chaves disponíveis:**

| Chave | Tooltip | Modal |
|---|---|---|
| `transcription.whisper_model` | Visão geral dos modelos | ✅ Tabela completa + nota de hardware |
| `transcription.beam_size` | Resumo do beam search | ✅ Explicação técnica |
| `transcription.language` | Quando fixar o idioma | — |
| `transcription.format` | O que faz o formatter | — |
| `transcription.analyze` | O que gera a análise | — |
| `transcription.prompt` | O que é o digest | — |
| `transcription.model_stage` | Local vs nuvem | — |
| `audio.input` | URL vs arquivo local | — |
| `audio.format` | 'best' vs conversão | — |
| `audio.bitrate` | Resumo do bitrate | ✅ Quando usar cada valor |
| `audio.embed_meta` | O que é embutido | — |
| `image.input` | URL direta vs arquivo local | — |
| `image.format` | Lossy vs lossless, AVIF | — |
| `image.quality` | Quando e quanto comprimir | — |

Para adicionar ajuda a um novo controle: inserir a chave em `HELP_SHORT` (e opcionalmente `HELP_LONG`) e passar `help_key=` para a fábrica correspondente.

---

## Estrutura do projeto

```text
mill-tools/
├── main.py              — entry point CLI
├── gui.py               — entry point GUI (splash → app)
├── src/
│   ├── transcriber.py · formatter.py · analyzer.py · prompter.py · llm_factory.py · utils.py
│   ├── core/
│   │   ├── audio/       — downloader, converter, info (lógica pura, sem Flet)
│   │   └── image/       — downloader, converter, info (Pillow; lógica pura, sem Flet)
│   └── gui/
│       ├── app.py       — NavigationRail + registry de módulos + navigate_to
│       ├── splash.py    — animação de entrada (moinho + fade)
│       ├── assets.py    — helpers de imagem (b64, WINDOW_ICON)
│       ├── events.py    — EventBus, PipelineEvent (com module_id)
│       ├── settings.py  — persistência em ~/.mill-tools/config.json
│       ├── workers.py   — pipeline de Transcrição (thread daemon)
│       ├── help_content.py — registro central de tooltips e modais (HELP_SHORT/LONG)
│       ├── components/  — input_source.py (URL + FilePicker, allow_multiple, url_hint)
│       ├── modules/     — base.py + transcription/ · audio/ · video/ · image/
│       ├── theme/       — Design System
│       │   ├── tokens.py    — Color, Type, Space, Radius, Motion, Layout
│       │   ├── theme.py     — build_theme() + apply_theme()
│       │   └── components/  — buttons, inputs, feedback, layout, help, cards
│       └── views/       — form_view · progress_view · result_view
├── assets/
│   ├── logo/            — símbolo e wordmark (SVG/PNG)
│   └── icons/           — mill.ico, mill-512.png
├── ollama/              — Modelfiles
├── docs/                — planos de implementação
└── output/
    ├── audio/           — source/ (downloads) · processed/ (conversões)
    ├── image/           — source/ (downloads de URL) · processed/ (convertidas)
    ├── video/
    └── transcriptions/  — text/ · analysis/ · digest/
```

---

## Atalhos da GUI

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Inicia o pipeline (se a entrada for válida) |
| `Esc` | Cancela o pipeline em andamento |

---

## Roadmap

- **PR3.1** — IA de áudio opcional (denoise via DeepFilterNet; stems via Demucs a avaliar), isolada em extra que não afeta o app base.
- **PR4** — Módulo Vídeo (download/conversão/extração, análogo ao Áudio).
- **Futuro** — melhorias no Módulo Imagens (batch rename, redimensionamento, crop); Módulo de Imagens com IA (upscale/remoção de fundo).
