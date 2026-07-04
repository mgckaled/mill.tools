# CLI Refactoring Plan

Plano de refatoração para expandir o suporte de CLI além do módulo de Transcrição,
alinhando a estrutura com a arquitetura modular já existente na GUI.

---

## Motivação

Atualmente só o módulo de Transcrição tem uma CLI (`main.py`). Os demais módulos
(Áudio, Vídeo, Imagens) existem como código core puro em `src/core/` mas só são
acessíveis pela GUI. Além disso, a CLI de Transcrição tem problemas acumulados desde
a época do projeto `yt-transcriber` que precisam ser corrigidos antes de escalar.

---

## Problemas identificados na CLI atual

| Arquivo | Problema |
|---|---|
| `utils.download_audio` | Chama `yt-dlp` via `subprocess.run(text=True)` — bug cp1252/UTF-8 no Windows. Duplica `src/core/audio/downloader.py`, que já é correto. |
| `utils.validate_url` | Só aceita YouTube. O projeto suporta qualquer fonte yt-dlp. |
| `utils.extract_video_id` | Trunca para 6 chars — colisão em uso intenso. |
| `main.py` `output_stem` | Prefixo `transcricao_` — português no código (viola convenção). |
| `main.py` | Só aceita URL. Arquivos de áudio locais não funcionam pela CLI. |
| `utils.py` | Mistura responsabilidades: paths, logging, validação YouTube, metadados de transcrição. |
| `src/gui/modules/*/form_view.py` | `AudioArgs`, `VideoArgs`, `ImageArgs` vivem na GUI — importar qualquer um arrasta Flet. Pior: cada um tem `items: list[InputItem]` e `InputItem` está em `input_source.py`, que importa `flet` — logo o dataclass de dados também precisa sair da GUI (ver Fase 2). |

---

## Arquitetura-alvo

```
main.py                            — dispatcher fino (argparse subparsers)
src/
├── cli/
│   ├── __init__.py
│   ├── bus.py                     — CLIEventBus: adapta PipelineEvents → tqdm + logging
│   ├── transcription.py           — subcomando transcribe + build_output_stem, resolve_input (metadata vai p/ core)
│   ├── audio.py                   — subcomando audio
│   ├── video.py                   — subcomando video
│   └── image.py                   — subcomando image
├── core/
│   ├── io_types.py                — InputItem (kind/value), sem Flet — extraído de input_source.py
│   ├── metadata.py                — fetch_metadata, format_metadata, format_duration (GUI+CLI)
│   ├── audio/
│   │   ├── args.py                — AudioArgs (extraído de gui/modules/audio/form_view.py)
│   │   └── ... (existente)
│   ├── video/
│   │   ├── args.py                — VideoArgs (extraído de gui/modules/video/form_view.py)
│   │   └── ... (existente)
│   └── image/
│       ├── args.py                — ImageArgs (extraído de gui/modules/image/form_view.py)
│       └── ... (existente)
└── utils.py                       — escopo restrito: paths, sanitize_filename,
                                     setup_logging, check_dependencies, TqdmLoggingHandler
```

### Invariantes arquiteturais

- `src/core/` — Python puro, sem Flet, sem CLI. Reutilizável por GUI e CLI.
- `src/cli/` — sem Flet. Depende apenas de `src/core/` e `src/utils.py`.
- `src/gui/` — pode depender de `src/core/` e `src/cli/bus.py` (apenas para tipar o bus), nunca o contrário.
- Workers da GUI (`src/gui/modules/*/worker.py`) são reutilizados pela CLI via `CLIEventBus`. Zero duplicação de lógica de pipeline.
- `subprocess` sempre em **modo binário** (`Popen`/`run` sem `text=True`). Decodificar com `.decode('utf-8', errors='replace')`. Invariante em todo o projeto.
- **Dados vs. widget:** `InputItem` (dataclass kind/value) vive em `src/core/io_types.py`; `InputSource`/`build_input_source` (widget Flet) ficam na GUI. Os `*Args` importam `InputItem` do core.
- **Helpers compartilhados de transcrição** (`fetch_metadata`, `format_metadata`, `format_duration`) vivem em `src/core/metadata.py` — usados por `src/transcriber.py` e `src/gui/workers.py`. **Nunca** em `src/cli/`, senão core/GUI importariam de cli (inversão de camada).

---

## Fases de implementação

### Fase 0 — Refatoração da CLI de Transcrição *(imediata)*

Corrige os problemas existentes e estabelece o padrão para as fases seguintes.

**`src/cli/__init__.py`** — cria pacote vazio.

> ⚠️ **Correção (camadas):** `fetch_metadata`, `format_metadata` e `format_duration` são usados por `src/transcriber.py` (core) e `src/gui/workers.py` — então vão para **`src/core/metadata.py`**, NÃO para `cli/`. Em `cli/transcription.py` ficam só os helpers específicos de CLI.

**`src/core/metadata.py`** (novo) — helpers compartilhados migrados de `utils.py`:
- `fetch_metadata(url)` — busca metadados via yt-dlp
- `format_metadata(meta, url, detected_language)` — formata cabeçalho do .txt
- `format_duration(seconds)` — utilitário de formatação de tempo

**`src/cli/transcription.py`** — apenas helpers específicos de CLI:
- `build_output_stem(meta, custom_name)` — substitui `extract_video_id` + o prefixo `transcricao_`. Usa `sanitize_filename(meta["title"])` como padrão, com fallback para `transcription_{timestamp}`.
- `resolve_input(value)` — detecta se o argumento é URL ou arquivo local, retornando `(kind, path_or_url)`.

**`utils.py`** — após migração:
- `download_audio` → **deletar** (substituída por `src/core/audio/downloader.download_audio`)
- `validate_url` → **deletar** (yt-dlp lança erro descritivo naturalmente)
- `extract_video_id` → **deletar** (substituída por `build_output_stem`)
- `fetch_metadata`, `format_metadata`, `format_duration` → **mover para `src/core/metadata.py`**; atualizar imports em `src/transcriber.py` (linha 15) e `src/gui/workers.py` (linha 21)

> 🧪 **Testes (obrigatório nesta fase):** `tests/test_utils.py` importa `format_duration, extract_video_id, format_metadata` de `src.utils` (linha 2) e **quebra no import** após a migração. Na mesma fase: remover os testes de `extract_video_id`; mover os de `format_duration`/`format_metadata` para `tests/core/test_metadata.py`; adicionar `tests/cli/test_transcription.py` (`build_output_stem`, `resolve_input`). Encerrar a fase com `uv run pytest` verde.

**`main.py`** — alterações:
- Importar de `src/cli/transcription` em vez de `src/utils`
- Usar `src/core/audio/downloader.download_audio` com `progress_hook` (tqdm no terminal)
- Aceitar arquivo local como argumento (além de URL)
- Subcomando `transcribe` preparando para fases futuras (`main.py transcribe URL`)
  - Compatibilidade retroativa: se nenhum subcomando for reconhecido, tratar o primeiro arg como URL para não quebrar uso existente

---

### Fase 1 — CLIEventBus

**`src/cli/bus.py`** — adaptador que implementa a interface do `EventBus` da GUI:

```python
class CLIEventBus:
    def emit(self, type: str, stage: str, payload: dict, module_id: str = "") -> None: ...
```

Mapeamento de eventos:

| Evento | Comportamento na CLI |
|---|---|
| `progress_start` | Inicializa barra tqdm indeterminada |
| `progress_update` | Atualiza tqdm com `current` (0.0–1.0) |
| `queue_progress` | Imprime `[N/M] item_name` via `tqdm.write` |
| `log` | `tqdm.write(message)` — `mutable=True` sobrescreve a linha anterior |
| `task_done` | Fecha tqdm + imprime caminhos de saída |
| `task_error` | Fecha tqdm + `logging.error(message)` |
| `audio_op_start` / `video_op_start` / `image_op_start` | `tqdm.write` com label da operação |
| `audio_op_done` / `video_op_done` / `image_op_done` | `tqdm.write` com elapsed + tamanhos |

Isso permite que os workers da GUI (`run_audio_pipeline`, `run_video_pipeline`, etc.)
sejam chamados direto pela CLI, passando um `CLIEventBus` no lugar do `EventBus` do Flet.

---

### Fase 2 — Extração dos Args

> 🔗 **Passo 0 desta fase (pré-requisito): extrair `InputItem`.** Os três `*Args` têm `items: list[InputItem]`, e `InputItem` está em `src/gui/components/input_source.py`, que importa `flet`. Mover os Args para `core/` sem mover `InputItem` arrastaria Flet para o core (viola a invariante). Então primeiro: extrair o **dataclass** `InputItem` (kind/value) para `src/core/io_types.py`; manter `InputSource`/`build_input_source` (widget) na GUI, importando `InputItem` do core. Atualizar imports em `input_source.py`, nos três `form_view.py` e nos três `worker.py`.

Depois, para cada módulo, extrair o dataclass de configuração para fora da GUI:

| Origem (atual) | Destino |
|---|---|
| `src/gui/modules/audio/form_view.py :: AudioArgs` | `src/core/audio/args.py` |
| `src/gui/modules/video/form_view.py :: VideoArgs` | `src/core/video/args.py` |
| `src/gui/modules/image/form_view.py :: ImageArgs` | `src/core/image/args.py` |

Atualizar imports em **dois** lugares por módulo: `form_view.py` **e** `worker.py` (cada `worker.py` faz hoje `from src.gui.modules.<m>.form_view import <M>Args` → passa a importar de `src/core/<m>/args.py`). É mecânico, mas não é "só mover a definição".

---

### Fase 3 — Subcomando `audio`

**`src/cli/audio.py`**:
- `add_audio_parser(subparsers)` — registra o subcomando `audio` com seus args
- `run_audio_cli(args)` — monta `AudioArgs`, instancia `CLIEventBus`, chama `run_audio_pipeline()`

Auto-detecção de operação pelo tipo do input:
- URL → `download`
- Arquivo de vídeo (`.mp4`, `.mkv`, `.webm`, …) → `extract`
- Arquivo de áudio → `convert`

```bash
uv run main.py audio URL [--fmt mp3] [--quality 320] [--no-meta] [--denoise] [--normalize -14]
uv run main.py audio arquivo.wav [--fmt mp3] [--bitrate 192] [--denoise]
uv run main.py audio video.mp4 [--fmt mp3]
```

---

### Fase 4 — Subcomando `video`

**`src/cli/video.py`** com subcomandos por operação:

```bash
uv run main.py video download URL [--quality 1080p]
uv run main.py video convert FILE [--codec h264] [--container mp4]
uv run main.py video trim FILE --start 0:30 [--end 2:00] [--reenc]
uv run main.py video compress FILE [--crf 23] [--preset medium]
uv run main.py video resize FILE [--width 1280] [--height 720]
uv run main.py video extract-audio FILE [--fmt mp3]
uv run main.py video thumbnail FILE [--time 0:01] [--fmt jpg]
```

Reutiliza `run_video_pipeline()` via `CLIEventBus`. `VideoArgs` extraído em Fase 2.

---

### Fase 5 — Subcomando `image`

**`src/cli/image.py`** com subcomandos por operação:

```bash
uv run main.py image convert FILE [--fmt webp] [--quality 85]
uv run main.py image resize FILE [--width 1920] [--mode contain]
uv run main.py image crop FILE [--mode ratio] [--ratio 16:9]
uv run main.py image rotate FILE [--angle 90] [--flip-h] [--flip-v]
uv run main.py image watermark FILE --text "© 2025" [--position bottom-right]
uv run main.py image adjust FILE [--brightness 1.2] [--contrast 1.1]
uv run main.py image remove-bg FILE
uv run main.py image describe FILE [--model moondream-custom]
```

Operações com params complexos (`watermark` com imagem, `crop` manual, `contact_sheet`)
são os menos prioritários — avaliar custo/benefício de CLI vs script direto.

---

## Decisões transversais (valem para todas as fases)

**Execução síncrona na CLI.** A CLI chama `run_<m>_pipeline(args, bus, cancel_event)` diretamente — **nunca** as variantes `start_<m>_pipeline` (daemon thread + `on_finish`, próprias da GUI). Roda na main thread, tqdm na main thread.

**`cancel_event` na CLI.** A assinatura exige um `threading.Event`. Sem botão de cancelar, passar um `threading.Event()` nunca setado — ou ligá-lo ao `SIGINT` (Ctrl+C) para cancelamento gracioso.

**Logging — evitar duplicação.** `setup_logging()` faz `logging.root.handlers = [TqdmLoggingHandler()]`; os workers dão `addHandler(LogEventHandler)` (reencaminha logs como eventos `log` ao bus). Em CLI isso imprimiria cada linha duas vezes (TqdmLoggingHandler direto + CLIEventBus→`tqdm.write`). Decisão: o `LogEventHandler` é específico da GUI — dar ao worker um parâmetro `install_log_handler: bool = True` e, na CLI, passar `False`, confiando no `TqdmLoggingHandler`.

**Extras opcionais de imagem na CLI.** `remove-bg` (rembg, extra `[ai-image]`) e `describe` (Ollama vision) podem não estar disponíveis. O CLI deve checar (`is_available()` / `create_session()`) e emitir erro claro ("instale o extra `[ai-image]`" / "Ollama indisponível") em vez de stacktrace — espelhando a GUI, que desabilita o card.

**Manter `CLAUDE.md` em dia.** A refatoração muda os comandos de CLI documentados e o escopo de `utils.py`. Ao fim de cada fase, atualizar as seções relevantes do `CLAUDE.md` (Estrutura, Comandos, nova camada `src/cli/`). `check_dependencies()` deve rodar nos novos subcomandos.

## Testes

A suíte (pytest, marcadores `unit`/`integration`) é o critério de regressão. **Antes de criar a branch, rodar `uv run pytest` e confirmar verde** — é o baseline.

Por fase:

- **Fase 0:** `tests/test_utils.py` quebra no import (ver nota na Fase 0). Remover testes de `extract_video_id`; mover `format_duration`/`format_metadata` para `tests/core/test_metadata.py`; criar `tests/cli/test_transcription.py` (`build_output_stem`, `resolve_input`).
- **Fase 1:** `tests/cli/test_bus.py` — alimentar o `CLIEventBus` com cada tipo de evento da tabela e asserir a saída (capturar stdout/`tqdm.write`); confirmar que `mutable=True` sobrescreve a linha.
- **Fase 2:** os Args ficam testáveis sem Flet — `tests/core/<m>/test_args.py` (defaults + validação).
- **Fases 3–5:** parsing de cada subcomando (`argparse` → `*Args` esperado) com mocks dos `core.*`; reaproveitar os testes de pipeline existentes.
- `tests/cli/` e `tests/core/` precisam de `__init__.py` (espelhar a estrutura de `src/`). Marcar `unit` o que não toca ffmpeg/rede/GPU.

## Estado final de `utils.py`

Após a Fase 0, `utils.py` contém apenas:

```python
# Paths de output (PROJECT_ROOT, OUTPUT_DIR, AUDIO_SOURCE_DIR, ...)
# sanitize_filename()
# TqdmLoggingHandler
# setup_logging()
# check_dependencies()
```

Metadados compartilhados (`fetch_metadata`/`format_metadata`/`format_duration`) migram para `src/core/metadata.py`; apenas os helpers específicos de CLI (`build_output_stem`, `resolve_input`) ficam em `src/cli/transcription.py`. `download_audio`, `validate_url` e `extract_video_id` são deletados.

---

## Ordem de implementação recomendada

```
Fase 0  →  Fase 1  →  Fase 2  →  Fase 3  →  Fase 4  →  Fase 5
  │           │           │
  │           │           └─ Pré-requisito para Fases 3–5
  │           └─ Pré-requisito para Fases 3–5
  └─ Autossuficiente, entregável imediato
```

Fase 0 pode ser feita e commitada independentemente.
Fases 1 e 2 são pré-requisitos paralelos — podem ser feitas juntas.
Fases 3, 4, 5 são independentes entre si após Fases 1 e 2.

---

## Branch e rollout

Maior mudança do projeto até aqui — fazer numa branch dedicada.

- **Antes de ramificar:** `uv run pytest` verde (baseline de regressão).
- **Branch:** `refactor/cli-modular` (ou similar), a partir da branch principal atual.
- **Commits:** um por fase, cada fase mergeable de forma independente. A Fase 0 é entregável sozinha (corrige bugs reais da CLI).
- **`uv run pytest -m unit` ao fim de cada fase**; suíte completa antes de abrir o PR.
- **Checklist de regressão da CLI** (compatibilidade retroativa — devem continuar funcionando):
  - `uv run main.py <URL>`
  - `uv run main.py <URL> --format --analyze`
  - `uv run main.py <URL> --analyze --am gemini-2.5-flash`
  - `uv run -m src output/transcriptions/text/<file>.txt`
  - A nova forma `uv run main.py transcribe <URL>` e o fallback "primeiro arg = URL" devem coexistir.
- **Coordenação com os outros planos nesta pasta** (`PLANO-1-prioridade-alta.md`, `PLANO-2-prioridade-media-baixa.md`): após a Fase 2, o Refactor A (runner dos workers) e o B (quebra do `image/form_view.py`) ficam destravados. Sequência global: **CLI Fase 0 → CLI Fase 2 → Refactor A → CLI Fase 1 → Refactor B → CLI Fases 3–5**.
