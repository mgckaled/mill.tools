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
- 🖥️ **GUI desktop** (Flet) com acompanhamento em tempo real estilo CLI, e **CLI** completa para automação.

### Módulos

| Módulo | Status | O que faz |
|---|---|---|
| **Transcrição** | ✅ | Whisper local + formatação/análise/digest via LLM |
| **Áudio** | ✅ | Download, conversão e extração de áudio (fila, capa/metadados) |
| **Vídeo** | 🚧 | Download/conversão/extração (planejado — PR4) |
| **Imagens** | 🗺️ | Manipulação/conversão (pesquisa em `docs/`) |

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

Abre a interface com **barra lateral de módulos**. Cada módulo tem layout split: formulário à esquerda, painel de acompanhamento (logs em tempo real + barra de progresso) à direita.

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

## Estrutura do projeto

```text
mill-tools/
├── main.py              — entry point CLI
├── gui.py               — entry point GUI (splash → app)
├── src/
│   ├── transcriber.py · formatter.py · analyzer.py · prompter.py · llm_factory.py · utils.py
│   ├── core/audio/      — downloader, converter, info (lógica pura, sem Flet)
│   └── gui/
│       ├── app.py · splash.py · assets.py · events.py · settings.py · workers.py
│       ├── components/  — input_source.py (URL + FilePicker)
│       ├── modules/     — base.py + transcription/ · audio/ · video/
│       └── views/       — form_view · progress_view · result_view
├── assets/
│   ├── logo/            — símbolo e wordmark (SVG/PNG)
│   └── icons/           — mill.ico, mill-512.png
├── ollama/              — Modelfiles
├── docs/                — planos de implementação
└── output/              — audio/ · video/ · transcriptions/{text,analysis,digest}
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
- **PR4** — Módulo Vídeo (download/conversão/extração).
- **Futuro** — Módulo Imagens (manipulação/conversão com Pillow).
