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

**mill.tools** é uma caixa de ferramentas pessoal para quem trabalha com áudio, vídeo e imagens — tudo rodando diretamente no seu computador, sem enviar arquivos para servidores externos, sem assinaturas e sem limites de uso.

A ferramenta é organizada em **módulos independentes**, cada um especializado em uma categoria de tarefa. Você os acessa por uma interface visual (aplicativo desktop) ou pela linha de comando. Os módulos também se integram: após baixar e converter um áudio, por exemplo, um clique já o envia para transcrição.

### O que você pode fazer

- 🎙️ **Transcrever áudio e vídeo** — converta fala em texto usando o mesmo modelo de reconhecimento de voz da OpenAI (Whisper), acelerado pela placa de vídeo do seu computador. O idioma é detectado automaticamente, e trechos de baixa confiança ficam marcados para revisão.

- 🧠 **Transformar transcrições em conhecimento** — após transcrever, a inteligência artificial organiza o texto em parágrafos legíveis, extrai um resumo estruturado com pontos-chave, tópicos, citações e conclusões, e ainda gera uma versão compacta pronta para colar como contexto em outros sistemas de IA.

- 🎵 **Baixar e converter áudio** — faça download de áudio do YouTube, SoundCloud e centenas de outras plataformas, ou converta e extraia faixas de arquivos de vídeo locais. Formatos de saída: MP3, WAV, M4A, OGG, OPUS e mais, com capa e metadados embutidos automaticamente.

- 🖼️ **Processar imagens em lote** — 12 operações disponíveis: converter formatos, redimensionar, recortar, girar, aplicar filtros e ajustes de cor, adicionar marca d'água ou borda, gerar favicon `.ico`, montar colagens — e com IA: remover o fundo automaticamente e gerar descrições textuais detalhadas da imagem. Tudo com visor Antes/Depois integrado.

- 🔀 **Escolher onde a IA roda** — por padrão, todos os modelos de linguagem funcionam 100% offline via [Ollama](https://ollama.com) (nenhum dado sai do computador). Para quem prefere, o [Google Gemini](https://ai.google.dev/) gratuito está disponível como alternativa na nuvem — basta escolher o modelo na interface.

### Módulos

| Módulo | Status | Descrição |
|---|---|---|
| **Transcrição** | ✅ Disponível | Whisper local com pós-processamento por IA: parágrafos, análise estruturada e resumo |
| **Áudio** | ✅ Disponível | Download de plataformas, conversão de formatos e extração de faixas, em fila com metadados |
| **Imagens** | ✅ Disponível | 12 operações: manipulação, conversão, remoção de fundo e descrição por IA vision |
| **Vídeo** | 🚧 Em breve | Download, conversão e extração de vídeo (próxima versão) |

### Destaques técnicos

| Característica | Detalhe |
|---|---|
| Transcrição local | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + ctranslate2, aceleração GPU, sem PyTorch |
| Sem dependência de nuvem | Ollama local por padrão; Gemini como opção opt-in por prefixo de modelo |
| Remoção de fundo | rembg + ONNX Runtime, 100% CPU, sem GPU dedicada |
| Interface desktop | [Flet 0.85](https://flet.dev) (Flutter/Windows) com log em tempo real e design system próprio |
| Ajuda contextual | Ícone ⓘ em todos os controles — tooltip no hover, modal detalhado ao clicar |

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

# descrição de imagens (módulo Imagens → Descrever)
ollama pull moondream
ollama create moondream-custom -f ollama/Modelfile.vision
```

### Extras opcionais

```bash
# remoção de fundo (módulo Imagens → Remover fundo)
uv sync --extra ai-image
```

> O app base funciona sem os extras. A operação "Remover fundo" fica com card desabilitado enquanto `[ai-image]` não estiver instalado.

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

Downloads de URL em `source/`; imagens processadas em `processed/`.

---

## Módulo Imagens — operações disponíveis

| Operação | O que faz |
|---|---|
| **Converter** | Converte entre 8 formatos: JPG, PNG, WebP, AVIF, TIFF, BMP, GIF, ICO |
| **Redimensionar** | Caber (proporcional), Exato (força dimensões) ou Escala % |
| **Cortar** | Manual (px), Proporção (16:9, 4:3…) ou Auto-trim (remove borda por cor) |
| **Girar** | Ângulo 90°/180°/270°, espelhamento H/V, correção automática EXIF |
| **Marca d'água** | Texto ou imagem sobreposta, com posição e opacidade configuráveis |
| **Borda** | Borda sólida configurável, com opção de preencher alpha pela cor |
| **Ajustes** | Brilho, contraste, saturação e nitidez (sliders 0.1–2.0) |
| **Filtros** | Blur, Nitidez, Autocontraste, Equalizar, Escala de cinza |
| **Favicon** | Gera `.ico` com múltiplas resoluções embutidas (16–256 px) |
| **Colagem** | Monta grade de miniaturas de N imagens em uma única saída |
| **Remover fundo** | Remove o fundo via rembg/ONNX (CPU). Saída sempre PNG com alpha. 5 modelos: u2net, u2netp, silueta, isnet, humano. Requer `uv sync --extra ai-image`. |
| **Descrever** | Envia a imagem a um modelo Ollama vision e salva a descrição como `.txt`. Modelos: moondream-custom (padrão), llava:7b, minicpm-v. |

O visor **Before/After** mostra a imagem original e o resultado lado a lado. Para "Descrever" (saída texto), o visor permanece em single-pane com a imagem de entrada.

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
- **Hover** → tooltip estilizado (300 ms de delay)
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
| `image.resize` | Modos de redimensionamento | — |
| `image.crop` | Modos de corte | — |
| `image.rotate` | Ângulo, flip e EXIF | — |
| `image.watermark` | Texto vs imagem, opacidade | — |
| `image.border` | Padding, cor e alpha | — |
| `image.adjust` | Sliders de ajuste | — |
| `image.filter` | Tipos de filtro | — |
| `image.favicon` | Tamanhos e formato .ico | — |
| `image.contact_sheet` | Grade N→1 | — |
| `image.rembg_model` | Resumo dos 5 modelos | ✅ Tamanho, uso ideal e onde são baixados |
| `image.describe_model` | Resumo dos modelos vision | ✅ RAM, velocidade e setup de cada um |
| `image.describe_prompt` | Como usar o prompt customizado | — |

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
│   │   └── image/       — downloader, converter, transform, info (Pillow; lógica pura, sem Flet)
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
    ├── image/           — source/ (downloads de URL) · processed/ (processadas)
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
- **Futuro** — melhorias no Módulo Imagens (batch rename, redimensionamento guiado); IA de imagens (upscale).
