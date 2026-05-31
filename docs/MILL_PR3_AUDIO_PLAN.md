# mill.tools — PR3 (Fase B): Módulo Áudio — Núcleo

> Detalhamento do **núcleo** do módulo Áudio, consumindo os contratos da Fase A (Module,
> InputSource, eventos genéricos, fila sequencial, bridge) e respeitando o hardware
> (MX150 2GB, GPU compartilhada com Whisper). IA de áudio **não** entra aqui — vai para o
> PR3.1 (ver §8).

## Decisões travadas (para implementação)

- **Escopo do núcleo:** download + conversão + extração de áudio (via `yt-dlp` + `ffmpeg`).
- **Embutir capa + metadados no download:** **ligado por padrão**, com opção de desligar.
- **IA de áudio (denoise/stems):** **fora do PR3** — vira PR3.1 (a elaborar depois).
- **Arrastar arquivo do SO:** **fora de escopo, em definitivo** (não nativo no Flet; decidido
  não incluir em nenhum momento). Entrada = **link + seletor de arquivos**.
- **Acompanhamento:** **reaproveitar** o `ProgressPanel`/eventos genéricos existentes (uma
  view de acompanhamento específica de áudio fica como refino futuro, não no PR3).
- **Bridge Áudio → Transcrição:** **incluído**.

---

## 1. Opções de áudio (inspiradas no cobalt)

O `yt-dlp` que você já usa cobre os mesmos serviços do cobalt (YouTube, SoundCloud, TikTok,
X, Instagram, Vimeo, Reddit…), então a cobertura vem de graça. Adotar as opções de áudio:

| Opção | Como em mill.tools |
|---|---|
| Modo "só áudio" | `yt-dlp -f bestaudio` + extração |
| Formato: best/mp3/ogg/wav/opus | `best` = mantém codec da fonte (sem reencode/perda); demais convertem via ffmpeg |
| Bitrate: 320/256/128/96/64 kb/s | só aplica em formato lossy; **avisar** na UI que não melhora a fonte |
| "prefer better quality" (YouTube) | seleção de formato bestaudio no yt-dlp |
| **Embutir metadados + capa** | `yt-dlp --embed-metadata --embed-thumbnail` (+ffmpeg) — **default ligado** |

> Fora do núcleo: faixa de dublagem/idioma, "original sound" do TikTok e legendas — não
> entram (são de vídeo/nicho).

---

## 2. Operações do núcleo

1. **Baixar** (URL → áudio): formato + bitrate + qualidade + **embutir capa/metadados (default ON)**
2. **Converter** áudio local: formato + bitrate
3. **Extrair** áudio de vídeo local

> Capa embutida: funciona bem em mp3 (ID3 APIC) e m4a; em ogg/opus o suporte a cover art é
> mais irregular — quando o container não suportar, embutir só os metadados e seguir sem
> falhar (log informativo).

---

## 3. Entrada de áudio — 2 fontes

| Fonte | Suporte Flet | Status |
|---|---|---|
| **Link** (URL de vídeo/áudio) | nativo (`TextField`) | ✅ PR3 |
| **Selecionar arquivos** | nativo (`FilePicker`, `allow_multiple=True`) | ✅ PR3 |
| ~~Arrastar do SO~~ | não-nativo | ❌ fora de escopo (definitivo) |

Ambas populam o mesmo **InputSource** (contrato da Fase A):
`InputItem(kind="url"|"local", value=str)` — `local` pula o downloader e vai direto para
conversão/extração; `url` baixa primeiro.

---

## 4. Estrutura de código

### Core (puro, sem Flet)
```
src/core/audio/
├── __init__.py
├── downloader.py   ← yt-dlp: URL → output/audio/source/ (formato/qualidade/metadata+capa)
├── converter.py    ← ffmpeg: formato + bitrate; extrair áudio de vídeo
└── info.py         ← metadados/duração/formato do arquivo ou URL
```

Assinaturas principais:
```python
# downloader.py
def download_audio(url: str, out_dir: Path, fmt: str = "mp3", quality: str = "best",
                   embed_meta: bool = True, progress_hook=None) -> Path: ...
                   # embed_meta=True por padrão (capa + metadados)

# converter.py
def convert_audio(src: Path, out_dir: Path, fmt: str, bitrate: str | None,
                  progress_cb=None) -> Path: ...
def extract_audio(video: Path, out_dir: Path, fmt: str = "mp3",
                  progress_cb=None) -> Path: ...   # saída em output/audio/processed/
```

### GUI (módulo na sidebar — substitui o placeholder)
```
src/gui/modules/audio/
├── __init__.py
├── form_view.py   ← InputSource + operação + formato + bitrate + qualidade
│                     + switch "Embutir capa e metadados" (default ON)
├── worker.py      ← roda em thread; emite os eventos genéricos do PR2
└── view.py        ← build_audio_module() → Module
```

### Saída (já prevista)
- Downloads → `output/audio/source/`
- Convertidos/extraídos → `output/audio/processed/`

---

## 5. Acompanhamento estilo CLI (reuso)

Reaproveita o `ProgressPanel` e o **contrato de eventos genéricos** (+`queue_progress`) da
Fase A — o log dá a cadência/histórico tipo CLI que já existe. O worker de áudio só **mapeia**
o progresso para os eventos:

| Operação | Fonte de progresso → evento genérico |
|---|---|
| Download (yt-dlp) | `progress_hooks` → `{downloaded_bytes, total_bytes}` → `progress_update(cur,total)` |
| Conversão/Extração (ffmpeg) | parse de `time=HH:MM:SS` no stderr vs duração → `progress_update` |
| Fila (lote) | `queue_progress(item_idx, total, nome)` → label "Item 2/5 — arquivo.mp3" |

A fila é **sequencial** (serializa CPU/ffmpeg e a GPU), coerente com o hardware.

> Refino futuro (não-PR3): uma view de acompanhamento específica de áudio. Por ora, o painel
> compartilhado atende.

---

## 6. Bridge Áudio → Transcrição

Botão "Transcrever este arquivo" → `navigate_to("transcription", {"file": path})`, que
preenche o InputSource do módulo de Transcrição. Mesmo mecanismo do populador manual — sem
duplicação.

---

## 7. Dependências e `check_dependencies()`

- `yt-dlp`, `ffmpeg` — já verificados; estender a checagem para os **codecs** usados
  (mp3/aac/opus) e formatos de saída.
- Sem novas dependências pesadas no núcleo (nada de torch — isso é PR3.1).

---

## 8. Fora do núcleo → roadmap PR3.1 (IA de áudio)

A elaborar num plano separado depois do núcleo validado. Resumo da pesquisa para referência:

- **Ollama não serve** para áudio (é LLM/visão; entrada de áudio é só feature-request).
  Continua no papel atual de analisar transcrição.
- **Hugging Face** é a fonte dos pesos, mas via `transformers` puxa **PyTorch (~1GB+)** —
  contraria a escolha de ctranslate2. Usar pacotes dedicados, não a stack inteira.
- Candidatos: **DeepFilterNet** (denoise/realce de voz, tempo real em CPU — bom pré-processo
  antes de transcrever) e **Demucs** (stems; quer GPU 3GB+, MX150 2GB é apertado).
- **Decisão sobre Demucs (stems): adiada para a elaboração do PR3.1.**
- Quando vier: isolar tudo num **extra opcional** do `uv` (`mill-tools[ai-audio]`), manter o
  app base torch-free, e **serializar** com a GPU do Whisper.

---

## 9. Decisão em aberto (única)
- **Lote recursivo:** aceitar uma pasta inteira (+ subpastas) como entrada, ou só seleção
  múltipla de arquivos no PR3? (recomendo seleção múltipla agora; pasta recursiva depois)

## Checklist PR3 (núcleo)
- [ ] `src/core/audio/downloader.py` (com `embed_meta=True` default), `converter.py`, `info.py`
- [ ] `src/gui/components/input_source.py` (link + FilePicker `allow_multiple`)
- [ ] `src/gui/modules/audio/{form_view,worker,view}.py` (substitui placeholder; switch capa/metadados ON)
- [ ] Worker mapeia progresso (yt-dlp hook / ffmpeg stderr) → eventos genéricos + `queue_progress`
- [ ] Fila sequencial; saída em `output/audio/{source,processed}`
- [ ] Bridge "Transcrever este arquivo" via `navigate_to`
- [ ] `check_dependencies()` estende verificação de codecs ffmpeg
- [ ] Embutir capa/metadados no download (default ON, desligável); fallback gracioso quando o container não suportar capa
- [ ] Smoke test: baixar URL (mp3 128k, com capa/metadados), converter wav→mp3, extrair áudio de vídeo local, lote de 3 itens

## Sources
- [cobalt — repositório/serviços e modos](https://github.com/imputnet/cobalt)
- [DeepFilterNet — denoise em tempo real na CPU](https://github.com/Rikorose/DeepFilterNet) (PR3.1)
- [Demucs — separação de stems (requisitos GPU/CPU)](https://github.com/facebookresearch/demucs) (PR3.1)
- [Ollama — entrada de áudio é feature request (#11798)](https://github.com/ollama/ollama/issues/11798)
