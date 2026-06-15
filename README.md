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

**mill.tools** é uma caixa de ferramentas pessoal para quem trabalha com áudio, vídeo, imagens e documentos — tudo rodando diretamente no seu computador, sem enviar arquivos para servidores externos, sem assinaturas e sem limites de uso.

A ferramenta é organizada em **módulos independentes**, cada um especializado em uma categoria de tarefa. Você os acessa por uma interface visual (aplicativo desktop) ou pela linha de comando. Os módulos também se integram: após baixar e converter um áudio, por exemplo, um clique já o envia para transcrição.

### O que você pode fazer

- 🎙️ **Transcrever áudio e vídeo** — converta fala em texto usando o mesmo modelo de reconhecimento de voz da OpenAI (Whisper), acelerado pela placa de vídeo do seu computador. O idioma é detectado automaticamente, e trechos de baixa confiança ficam marcados para revisão.

- 🧠 **Transformar transcrições em conhecimento** — após transcrever, a inteligência artificial organiza o texto em parágrafos legíveis, extrai um resumo estruturado com pontos-chave, tópicos, citações e conclusões, e ainda gera uma versão compacta pronta para colar como contexto em outros sistemas de IA.

- 🎵 **Baixar, converter e pós-processar áudio** — faça download de áudio do YouTube, SoundCloud e centenas de outras plataformas, ou converta e extraia faixas de arquivos de vídeo locais. Formatos de saída: MP3, WAV, M4A, OGG, OPUS e mais, com capa e metadados embutidos automaticamente. Pós-processamento opcional em fila: **redução de ruído** (spectral gating, CPU) e **normalização de loudness** (EBU R128 — −14 LUFS streaming, −23 broadcast, configurável).

- 🖼️ **Processar imagens em lote** — 12 operações disponíveis: converter formatos, redimensionar, recortar, girar, aplicar filtros e ajustes de cor, adicionar marca d'água ou borda, gerar favicon `.ico`, montar colagens — e com IA: remover o fundo automaticamente e gerar descrições textuais detalhadas da imagem. Tudo com visor Antes/Depois integrado.

- 📄 **Manipular documentos PDF** — 12 operações: juntar, dividir, comprimir, girar, aplicar marca d'água ou carimbo (PAGO/RASCUNHO/CONFIDENCIAL), criptografar com AES-256, extrair texto, rasterizar páginas em imagens, montar PDF a partir de imagens, gerar QR codes e analisar conteúdo com IA. 100% local via pymupdf.

- 📚 **Reunir tudo num só lugar** — a Biblioteca indexa automaticamente tudo que você já gerou (áudios, vídeos, imagens, transcrições e documentos) numa grade visual com miniaturas. Filtre por tipo e data, busque por nome, reabra um arquivo ou sua pasta, e reenvie qualquer saída para outro módulo num clique — por exemplo, mandar um áudio baixado direto para a Transcrição.

- 🔀 **Escolher onde a IA roda** — por padrão, todos os modelos de linguagem funcionam 100% offline via [Ollama](https://ollama.com) (nenhum dado sai do computador). Para quem prefere, o [Google Gemini](https://ai.google.dev/) gratuito está disponível como alternativa na nuvem — basta escolher o modelo na interface.

### Módulos

| Módulo | Status | Descrição |
|---|---|---|
| **Transcrição** | ✅ Disponível | Whisper local com pós-processamento por IA: parágrafos, análise estruturada e resumo |
| **Áudio** | ✅ Disponível | Download, conversão e extração de faixas em fila; pós-processamento: denoise spectral + normalize loudnorm (EBU R128) |
| **Imagens** | ✅ Disponível | 12 operações: manipulação, conversão, remoção de fundo e descrição por IA vision |
| **Vídeo** | ✅ Disponível | 7 operações: download, conversão, corte, compressão, redimensionamento, extração de áudio e thumbnail |
| **Documentos** | ✅ Disponível | 12 operações PDF: merge, split, compress, rotate, watermark, stamp, encrypt, extract, pdf-to-images, images-to-pdf, QR e análise por IA |
| **Biblioteca** | ✅ Disponível | Hub navegável de todas as saídas: grade com thumbnails, filtro por tipo, busca, ordenação e período; abrir arquivo/pasta e reenviar para outro módulo num clique |

### Destaques técnicos

| Característica | Detalhe |
|---|---|
| Processamento de vídeo | yt-dlp (download) + ffmpeg CPU-only: libx264, libx265, libvpx-vp9 — sem NVENC |
| Transcrição local | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + ctranslate2, aceleração GPU, sem PyTorch |
| Sem dependência de nuvem | Ollama local por padrão; Gemini como opção opt-in por prefixo de modelo |
| Pós-processamento de áudio | noisereduce (spectral gating, CPU) + ffmpeg loudnorm (EBU R128, 2 passes); torch-free, base deps |
| Remoção de fundo | rembg + ONNX Runtime, 100% CPU, sem GPU dedicada |
| Manipulação de PDF | [pymupdf](https://pymupdf.readthedocs.io) — merge/split/compress/rotate/watermark/stamp/encrypt/rasterização, 100% local |
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
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) + language packs (`por`, `eng`) — apenas para a operação **OCR** de Documentos (extra `[ocr]`). Detectado no PATH ou em `C:\Program Files\Tesseract-OCR`; o card OCR desabilita-se graciosamente se ausente.

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

Abre maximizado com uma splash screen animada, seguida de uma **Home Screen** com 6 cards de módulo (grade 3×2) — clique em qualquer card para entrar diretamente no módulo escolhido. O AppBar exibe a wordmark "mill.tools", o botão **Biblioteca** (o hub de saídas) e os botões "Home" e "Splash" para navegar de volta a qualquer momento.

Cada módulo tem layout split: formulário à esquerda, painel de acompanhamento (log em tempo real + barra de progresso + spinner) à direita. Durante um pipeline em execução a troca de módulo é bloqueada — os logs e a barra de progresso são preservados mesmo ao navegar entre módulos.

### CLI — Transcrição

```bash
# básico (idioma automático)
uv run main.py <YOUTUBE_URL>

# + formatação e análise
uv run main.py <YOUTUBE_URL> --format --analyze

# análise standalone (sobre transcrição existente)
uv run -m src output/transcriptions/text/transcricao_ovabeV.txt
```

### CLI — Áudio

```bash
# download do YouTube com pós-processamento
uv run main.py audio <URL> --fmt mp3 --quality 320 --denoise --normalize

# converter arquivo local
uv run main.py audio audio.wav --fmt ogg --quality 192

# extrair áudio de vídeo local
uv run main.py audio video.mp4 --fmt m4a
```

### CLI — Vídeo

```bash
uv run main.py video download <URL> --quality 1080 --container mp4
uv run main.py video convert video.mkv --codec h264 --container mp4
uv run main.py video trim video.mp4 --start 0:30 --end 2:15
uv run main.py video compress video.mp4 --crf 23 --preset medium
uv run main.py video extract-audio video.mp4 --fmt mp3
uv run main.py video thumbnail video.mp4 --time 00:00:05 --fmt jpg
uv run main.py video subtitle video.mp4 --subs legenda.srt --mode soft
```

### CLI — Imagens

```bash
uv run main.py image convert photo.jpg --fmt webp --quality 85
uv run main.py image resize photo.jpg --mode contain --width 1920
uv run main.py image crop photo.jpg --mode ratio --ratio 16:9
uv run main.py image watermark photo.jpg --text "© 2025" --opacity 0.5
uv run main.py image contact-sheet *.jpg --cols 4 --thumb 200
uv run main.py image remove-bg photo.png --model u2net
uv run main.py image describe photo.jpg --model moondream-custom
```

### CLI — Documentos

```bash
# juntar, dividir, comprimir
uv run main.py document merge a.pdf b.pdf c.pdf
uv run main.py document split doc.pdf --pages "1-3,5,8-"
uv run main.py document compress doc.pdf --image-quality 60

# anotações
uv run main.py document rotate doc.pdf --angle 90 --pages "1,3"
uv run main.py document watermark doc.pdf --text "CONFIDENCIAL" --opacity 0.3
uv run main.py document stamp doc.pdf --text "PAGO"

# proteção e conversão
uv run main.py document encrypt doc.pdf --password "senha"
uv run main.py document extract doc.pdf
uv run main.py document ocr scanned.pdf --lang por --dpi 300
uv run main.py document pdf-to-images doc.pdf --fmt jpg --dpi 150
uv run main.py document images-to-pdf *.jpg --name "album"
uv run main.py document qr "https://example.com" --size 300 --fmt png
```

### CLI — Biblioteca

```bash
# lista tudo que está em output/ como tabela
uv run main.py library list

# filtra por tipo, período e ordenação
uv run main.py library list --kind audio
uv run main.py library list --since 7d --sort size
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

### Vídeo — `output/video/`

Downloads de URL em `source/`; vídeos processados (convert, trim, compress, resize, thumbnail) e áudios extraídos em `processed/`.

### Documentos — `output/document/`

Todos os arquivos processados em `processed/`. Nomes de saída incluem sufixo da operação (ex.: `doc_compressed.pdf`, `doc_p1-3.pdf`, `doc_rotated90.pdf`). Operação `pdf_to_images` gera `stem_p001.jpg`, `stem_p002.jpg`… Operação `extract` gera `stem_text.txt`.

---

## Módulo Documentos — operações disponíveis

| Operação | Entrada | O que faz |
|---|---|---|
| **Juntar** | múltiplos PDFs | Mescla N arquivos em um único PDF, na ordem fornecida |
| **Dividir** | PDF | Extrai páginas por intervalo (ex.: `1-3,5,8-`). Cada faixa contígua vira um arquivo separado |
| **Comprimir** | PDF | Reimprimir imagens embutidas em JPEG (qualidade configurável 50–95) e limpa objetos mortos |
| **Girar** | PDF | Rotaciona páginas selecionadas em 90°, 180° ou 270° |
| **Marca d'água** | PDF | Texto diagonal semitransparente em todas as páginas (opacidade e posição configuráveis) |
| **Carimbo** | PDF | Texto em destaque centralizado (PAGO, RASCUNHO, CONFIDENCIAL ou personalizado) |
| **Criptografar** | PDF | Protege o arquivo com AES-256 (senha de usuário e proprietário) |
| **Extrair texto** | PDF | Extrai todo o texto para `.txt`. `has_text=False` indica PDF escaneado (sem texto embutido) |
| **OCR** | PDF | Reconhece texto de PDFs escaneados via Tesseract (idioma e DPI configuráveis). Híbrido: usa texto nativo quando existe; OCR só nas páginas-imagem. Requer Tesseract instalado |
| **PDF → Imagens** | PDF | Rasteriza cada página em JPG ou PNG. DPI configurável: 72 / 96 / 150 / 300 |
| **Imagens → PDF** | imagens | Combina N imagens JPEG/PNG em um único PDF, uma por página |
| **QR Code** | texto/URL | Gera QR code em PNG ou JPG. Tamanho aproximado em pixels configurável |
| **Analisar** | PDF | Extrai texto e envia para análise LLM (local via Ollama ou Google Gemini). Apenas na GUI |

---

## Módulo Vídeo — operações disponíveis

| Operação | Entrada | O que faz |
|---|---|---|
| **Baixar** | URL | Download via yt-dlp, resolução máx. configurável (360p–4K), containers MP4/MKV/WebM |
| **Converter** | arquivo local | Muda container e/ou codec. `copy` = sem reencoding (rápido). H.264 / H.265 / VP9 disponíveis |
| **Recortar** | arquivo local | Corta trecho por tempo (`HH:MM:SS`). Modo rápido (copy, no keyframe) ou frame-preciso (reencoda) |
| **Comprimir** | arquivo local | Reencoda com H.264/CRF (18–28). CRF 18 = alta qualidade; CRF 28 = menor tamanho |
| **Redimensionar** | arquivo local | Ajusta resolução preservando aspect ratio. Deixe um eixo em branco para calcular automaticamente |
| **Extrair áudio** | arquivo local | Extrai faixa de áudio em MP3/M4A/WAV. Resultado aparece com botões "Transcrever" e "Processar no Áudio" |
| **Thumbnail** | arquivo local | Captura um frame específico (`HH:MM:SS`) como JPG ou PNG |
| **Legenda** | arquivo local | Insere uma legenda `.srt`/`.vtt` no vídeo: **Embutir** (mux, faixa toggleável, sem reencode) ou **Queimar** (burn-in permanente, reencoda em H.264) |

Encoding 100% CPU — sem NVENC (decisão definitiva). Preset e CRF configuráveis no formulário.

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

## Módulo Biblioteca

A Biblioteca é o hub que reúne tudo que os outros módulos já produziram em `output/`. Diferente das ferramentas de processamento, ela vive **no AppBar** (ao lado do wordmark), não na NavigationRail — e abre uma tela cheia com uma grade de cards.

| Recurso | O que faz |
|---|---|
| **Grade com thumbnails** | Cards com miniatura sob demanda: imagem (Pillow), 1ª página de PDF (pymupdf) ou frame de vídeo (ffmpeg). Áudio e texto usam ícone do tipo. |
| **Filtrar por tipo** | Chips Todos / Áudio / Vídeo / Imagens / Transcrição / Documentos. |
| **Filtrar por categoria** | Todas / Origem (downloads) / Processado (saídas geradas). |
| **Buscar e ordenar** | Busca por nome (com debounce) + ordenação por data, nome ou tamanho. |
| **Filtrar por período** | Qualquer data / últimas 24h / 7 dias / 30 dias. |
| **Abrir** | Abre o arquivo no programa padrão do sistema ou revela sua pasta no explorador. |
| **Reenviar para outro módulo** | Bridges num clique: áudio/vídeo → Transcrição ou Áudio; imagem → Imagens; PDF → Documentos. |

A lista é recarregada ao abrir a Biblioteca e quando um pipeline termina. A grade exibe até 120 itens por vez, com botão "Carregar mais". Preferências de filtro e ordenação são lembradas entre sessões. Há paridade na CLI via `uv run main.py library list`.

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
| `video.input` | URL vs arquivo local | — |
| `video.operation` | Quando usar copy vs reencoding | — |
| `video.resolution` | Impacto no tamanho do download | — |
| `video.embed_meta` | O que é embutido | — |
| `video.codec` | Resumo dos codecs disponíveis | ✅ copy / H.264 / H.265 / VP9 — trade-offs |
| `video.trim` | Rápido vs frame-preciso | — |
| `video.crf` | Guia rápido de valores CRF | ✅ 18–28 — qualidade vs tamanho |
| `video.preset` | Velocidade vs compressão | — |
| `video.resize` | Aspect ratio e eixo automático | — |
| `audio.input` | URL vs arquivo local | — |
| `audio.format` | 'best' vs conversão | — |
| `audio.bitrate` | Resumo do bitrate | ✅ Quando usar cada valor |
| `audio.embed_meta` | O que é embutido | — |
| `audio.denoise` | Spectral gating: quando usar | ✅ Como funciona o algoritmo |
| `audio.normalize` | EBU R128: alvos por plataforma | ✅ Streaming / broadcast / podcast |
| `audio.normalize_lufs` | Guia rápido de alvos LUFS | — |
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
| `document.input` | Formatos suportados, URL vs arquivo local | — |
| `document.operation` | Descrição das 12 operações | — |
| `document.pages` | Sintaxe de intervalos de página | ✅ Exemplos: `1-3`, `5`, `8-` |
| `document.image_quality` | Qualidade JPEG para compressão de imagens embutidas | — |
| `document.watermark` | Marca d'água diagonal — opacidade e posição | — |
| `document.stamp` | Carimbo em destaque — textos pré-definidos | — |
| `document.password` | Proteção AES-256 — permissões preservadas | ✅ Detalhes de permissão |
| `document.dpi` | Resolução de rasterização em DPI | ✅ Qualidade vs tamanho |
| `document.qr_size` | Tamanho em pixels do QR code gerado | — |
| `document.analyze_model` | LLM local (Ollama) ou Gemini para análise do texto extraído | — |
| `library` | O que a Biblioteca reúne e como navegá-la | ✅ Filtros, ações, bridges e CLI |

Para adicionar ajuda a um novo controle: inserir a chave em `HELP_SHORT` (e opcionalmente `HELP_LONG`) e passar `help_key=` para a fábrica correspondente.

---

## Estrutura do projeto

```text
mill-tools/
├── main.py              — entry point CLI
├── gui.py               — entry point GUI (splash → home → app, maximizado)
├── src/
│   ├── transcriber.py · formatter.py · analyzer.py · prompter.py · llm_factory.py · utils.py
│   ├── core/
│   │   ├── audio/       — downloader, converter, denoiser, normalizer, info (lógica pura, sem Flet)
│   │   ├── video/       — downloader (yt-dlp), converter (ffmpeg), info (ffprobe)
│   │   ├── image/       — downloader, converter, transform, info (Pillow; lógica pura, sem Flet)
│   │   ├── document/    — processor (pymupdf), converter, qr, info (PdfInfo + render_first_page_png)
│   │   └── library/     — types (LibraryItem), scanner (output/ → índice), thumbnails (dispatch por kind)
│   └── gui/
│       ├── app.py       — NavigationRail (5 tools) + Biblioteca no AppBar + registry + navigate_to
│       ├── splash.py    — animação de entrada (moinho + fade)
│       ├── home.py      — Home Screen: 6 cards de módulo (3×2) + moinho animado ao fundo
│       ├── assets.py    — helpers de imagem (b64, WINDOW_ICON)
│       ├── events.py    — EventBus, PipelineEvent (com module_id)
│       ├── settings.py  — persistência em ~/.mill-tools/config.json
│       ├── workers.py   — pipeline de Transcrição (thread daemon)
│       ├── help_content.py — registro central de tooltips e modais (HELP_SHORT/LONG)
│       ├── components/  — input_source.py (URL + FilePicker, allow_multiple, url_hint)
│       ├── modules/     — base.py + transcription/ · audio/ · video/ · image/ · document/ · library/
│       │                  (processamento: form_view, worker, view, pipeline_log; library: view + cards, read-only)
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
└── output/             — origem do índice da Biblioteca
    ├── audio/           — source/ (downloads) · processed/ (conversões)
    ├── image/           — source/ (downloads de URL) · processed/ (processadas)
    ├── video/           — source/ · processed/
    ├── document/        — processed/
    └── transcriptions/  — text/ · analysis/ · digest/
```

---

## Atalhos da GUI

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Inicia o pipeline (se a entrada for válida) |
| `Esc` | Cancela o pipeline em andamento |

---

## Testes

A suíte cobre `src/core/`, `src/cli/`, os `pipeline_log` da GUI e o pipeline LLM (`analyzer`/`formatter`/`prompter`) em duas camadas, totalizando **525 testes** (0 falhas) e **88% de cobertura** (com branch).

| Camada | Marcador | Requer | O que cobre |
|---|---|---|---|
| **Unitários** | `@pytest.mark.unit` | Python puro | Funções puras, parsers, roteamento LLM, settings, mocks de subprocess |
| **Integração** | `@pytest.mark.integration` | `ffmpeg` no PATH | Conversão/extração real de áudio e vídeo, normalização, denoise, ffprobe, Pillow I/O |

Testes de integração são **pulados automaticamente** em ambientes sem `ffmpeg` (CI, máquinas limpas).

```bash
# Unitários apenas — rápido, sem ffmpeg (~5s)
uv run pytest -m unit -v

# Integração apenas — requer ffmpeg
uv run pytest -m integration -v

# Suíte completa
uv run pytest -v

# Paralelizada (pytest-xdist)
uv run pytest -n auto

# Cobertura HTML em htmlcov/
uv run pytest --cov=src --cov-report=html
```

Plugins ativos: `pytest-randomly` (ordem aleatória — `--randomly-seed=N` para reproduzir), `pytest-timeout` (60s default), `pytest-clarity` (diffs melhores), `pytest-xdist` (paralelização opcional).

---

## Roadmap

- **Home Screen** ✅ — Tela inicial entre splash e app: cards de módulo, moinho animado ao fundo, botões "Home" e "Splash" no AppBar, transições suavizadas. App abre maximizado.
- **PR3.1-A** ✅ — Pós-processamento de áudio: redução de ruído (spectral gating, CPU) e normalização de loudness (EBU R128). Sem torch, sem extra.
- **PR3.1-B** — IA de áudio com torch (extra `[ai-audio]`): DeepFilterNet (denoise neural); Demucs (separação de stems) a avaliar.
- **PR4** ✅ — Módulo Vídeo: 7 operações (download, convert, trim, compress, resize, extract_audio, thumbnail). CPU-only, fila sequencial, bridge → Transcrição/Áudio.
- **PR5** ✅ — Módulo Documentos: 12 operações PDF/QR (merge, split, compress, rotate, watermark, stamp, encrypt, extract, pdf-to-images, images-to-pdf, qr, analyze). Core pymupdf, 100% local.
- **PR5.1** ✅ — OCR: análise de PDFs escaneados via pytesseract (extra `[ocr]`, requer Tesseract no PATH).
- **PR6** ✅ — Módulo Biblioteca: índice navegável de `output/` (core puro), grade com thumbnails, filtro/busca/ordenação/período, abrir arquivo/pasta, bridges para outros módulos, paginação + auto-refresh e CLI `library list`. Hub no AppBar. Fundação para IA sobre o corpus e receitas encadeadas.
- **Futuro** — melhorias no Módulo Imagens (batch rename, upscale); IA sobre a Biblioteca (busca semântica, conversar com arquivos).
