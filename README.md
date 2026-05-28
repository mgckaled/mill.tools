# yt-transcriber

CLI Python para transcrever vídeos do YouTube em texto corrido e gerar análises estruturadas com LLM local. Usa [faster-whisper](https://github.com/SYSTRAN/faster-whisper) para transcrição e [Ollama](https://ollama.com) + [LangChain](https://www.langchain.com/) para análise. Todo processamento é 100% local.

---

## Requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/download.html) no PATH
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) no PATH
- [Ollama](https://ollama.com/download) (apenas para formatação e análise)

---

## Setup

```bash
git clone https://github.com/your-username/yt-transcriber
cd yt-transcriber
uv sync
```

Para usar formatação e análise, instale o Ollama e configure os modelos:

```bash
# modelo para análise
ollama pull qwen2.5:7b
ollama create qwen7b-custom -f ollama/Modelfile

# modelo para formatação de parágrafos
ollama pull phi4-mini
ollama create phi4mini-custom -f ollama/Modelfile.phi4mini
```

---

## Uso

### Transcrição

```bash
uv run main.py <YOUTUBE_URL> [options]
```

### Transcrição + análise

```bash
uv run main.py <YOUTUBE_URL> --analyze
```

### Análise standalone (sobre transcrição existente)

```bash
uv run -m src transcriptions/raw/transcricao_ovabeV.txt
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
| `--format`      | off               | Insere quebras de parágrafo via LLM local                    |
| `--fm`          | `phi4mini-custom` | Ollama model para formatação de parágrafos                   |
| `--analyze`     | off               | Roda análise estruturada após transcrição                    |
| `--am`          | `qwen7b-custom`   | Ollama model para análise                                    |
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

# whisper medium + modelos customizados
uv run main.py https://www.youtube.com/watch?v=ovabeVoWrA0 --wm medium --fm phi4mini-custom --am qwen7b-custom --format --analyze

# análise standalone sobre transcrição existente
uv run -m src transcriptions/raw/transcricao_ovabeV.txt
```

---

## Estrutura de arquivos

```text
yt-transcriber/
├── main.py                    — entry point, CLI
├── src/
│   ├── __init__.py
│   ├── __main__.py            — entry point do analyzer standalone
│   ├── transcriber.py         — transcrição via faster-whisper
│   ├── formatter.py           — formatação de parágrafos via LLM local
│   ├── analyzer.py            — análise estruturada via LangChain + Ollama
│   └── utils.py               — logging, validação, metadata, download
├── ollama/
│   ├── Modelfile              — config do qwen7b-custom
│   └── Modelfile.phi4mini     — config do phi4mini-custom
├── audios/                    — áudios baixados (.mp3)
└── transcriptions/
    ├── raw/                   — transcrições brutas (.txt)
    └── analysis/              — análises estruturadas (.md)
```

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

A análise (.md) contém: resumo, pontos-chave, conceitos-chave (com definição), ferramentas mencionadas, métricas e ações sugeridas. Se o resultado não estiver em português, é traduzido automaticamente. Quando `--format --analyze` são usados em conjunto, a transcrição formatada é incluída no final do relatório.

---

## Modelos Whisper

| Modelo           | Velocidade | Precisão  |
| ---------------- | ---------- | --------- |
| `tiny`           | mais rápido|  baixa    |
| `small`          | rápido     | boa       |
| `medium`         | moderado   | muito boa |
| `large-v3-turbo` | lento      | excelente |
| `large-v3`       | mais lento | melhor    |

## Modelos Ollama

| Modelo             | Uso          | Tamanho | Qualidade |
| ------------------ | ------------ | ------- | --------- |
| `phi4mini-custom`  | `--format`   | 2.5 GB  | básica    |
| `qwen7b-custom`    | `--analyze`  | 4.7 GB  | boa       |

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
