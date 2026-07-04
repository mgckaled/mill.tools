# Plano de Refatoração — Prioridade Média e Baixa

> **Alvo:** mill.tools · **Execução:** via Claude Code
> **Escopo:** consolidação de duplicação em `core/` e no pipeline LLM (média), limpeza de dívida na Transcrição, e melhorias de manutenibilidade/testabilidade (baixa).
> **Regra de ouro:** `src/core/` permanece puro (sem Flet). `subprocess` sempre em **modo binário** (sem `text=True`) — decodificar com `.decode('utf-8', errors='replace')`. Rodar `uv run pytest -m unit` ao fim de cada etapa.

> ⚠️ **Coordenação com `REFACTORING.md` e Plano 1.** Sequência global: CLI Fase 0 → CLI Fase 2 → Refactor A (Plano 1) → CLI Fase 1 → Refactor B (Plano 1) → CLI Fases 3–5 → os refactors deste doc. **O antigo F2 saiu** (absorvido pela CLI Fase 0); **F3 depende da CLI Fase 2 + Refactor A.**

---

## PRIORIDADE MÉDIA

## Refactor C — `_run_ffmpeg` compartilhado (`core/ffmpeg.py`)

### Problema

`src/core/audio/converter.py::_run_ffmpeg_with_progress` e `src/core/video/converter.py::_run_ffmpeg` são praticamente idênticos: `Popen` binário, thread de drain do stderr (cap 100 linhas), parse de `out_time_us=` do stdout para ratio, `wait()`, checagem de `returncode` e de existência do `out_path`, `RuntimeError`/`FileNotFoundError`. A **única** diferença é a fonte da duração total:

- áudio: `get_duration_ffprobe(src)`
- vídeo: `get_video_info(src).duration`

### Objetivo

Um runner ffmpeg único, recebendo a duração (ou um provider) por parâmetro, mantendo `core/` puro.

### Arquivos

**Novo:** `src/core/ffmpeg.py`
**Modificados:** `src/core/audio/converter.py`, `src/core/video/converter.py`

### Desenho

```python
# src/core/ffmpeg.py
from __future__ import annotations
import subprocess, threading
from pathlib import Path
from typing import Callable

def run_ffmpeg(
    cmd: list[str],
    out_path: Path,
    *,
    total_secs: float | None = None,
    progress_cb: Callable[[float], None] | None = None,
    stderr_tail: int = 100,
) -> Path:
    """Executa ffmpeg em modo binário com progresso via -progress pipe:1.

    Lê out_time_us= do stdout; chama progress_cb(ratio) se total_secs for dado.
    Sobe RuntimeError com o tail do stderr em returncode != 0, e FileNotFoundError
    se o arquivo de saída não existir ao final.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr_lines: list[str] = []

    def _drain() -> None:
        for raw in proc.stderr:
            stderr_lines.append(raw.decode("utf-8", errors="replace").rstrip())
            if len(stderr_lines) > stderr_tail:
                del stderr_lines[:-stderr_tail]

    threading.Thread(target=_drain, daemon=True).start()

    for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace").strip()
        if line.startswith("out_time_us=") and progress_cb and total_secs:
            try:
                ratio = min(int(line.split("=", 1)[1]) / 1_000_000 / total_secs, 1.0)
                progress_cb(ratio)
            except (ValueError, IndexError):
                pass

    proc.wait()
    if proc.returncode != 0:
        tail = "\n".join(stderr_lines[-10:]) if stderr_lines else "(sem detalhes)"
        raise RuntimeError(f"ffmpeg retornou {proc.returncode}: {tail}")
    if not out_path.exists():
        raise FileNotFoundError(f"ffmpeg concluiu mas arquivo não encontrado: {out_path}")
    return out_path
```

### Passos

1. Criar `src/core/ffmpeg.py` com `run_ffmpeg` (corpo acima).
2. Em `audio/converter.py`: trocar `_run_ffmpeg_with_progress` por um wrapper fino que calcula `total_secs = get_duration_ffprobe(src) if progress_cb else None` e chama `run_ffmpeg(...)`. Manter o nome interno (`_run_ffmpeg_with_progress`) como wrapper para não tocar nos call sites, **ou** ajustar os call sites — preferir ajustar (mais limpo).
3. Em `video/converter.py`: idem, `total_secs = get_video_info(src).duration if progress_cb else None`.
4. Remover os corpos duplicados.

### Riscos

- Modo binário obrigatório (já é). Não introduzir `text=True`.
- Vídeo chamava `get_video_info(src)` dentro do runner; agora o caller faz isso. Evitar chamar `get_video_info` duas vezes por operação se já foi chamado antes (otimização opcional, não bloqueante).

### Verificação

- `uv run pytest -m unit -v` e `uv run pytest -m integration -v` (requer ffmpeg no PATH) — `test_converter.py` (áudio), `test_normalizer_integration.py`, `test_info.py` (vídeo) cobrem o caminho.
- Critério: ambos os converters usam `core.ffmpeg.run_ffmpeg`; zero duplicação do loop de progresso.

---

## Refactor D — `split_text` compartilhado no pipeline LLM

### Problema

`src/formatter.py`, `src/analyzer.py` e `src/prompter.py` instanciam `RecursiveCharacterTextSplitter` de forma idêntica (mesmos `separators`, só mudam `chunk_size`/`overlap`), cada um com seu log `[d] Splitting...`. `analyzer._split_text` ainda adiciona o bypass para modelos de contexto longo (Gemini → 1 chunk) e o short-circuit `len(text) <= CHUNK_SIZE`.

### Objetivo

Um helper único de chunking, parametrizado, preservando o bypass Gemini.

### Arquivos

**Novo:** `src/llm_utils.py` (ou adicionar a `src/llm_factory.py`, que já centraliza roteamento de modelo).
**Modificados:** `src/formatter.py`, `src/analyzer.py`, `src/prompter.py`.

### Desenho

```python
# src/llm_utils.py
from __future__ import annotations
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.llm_factory import is_gemini_model

_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

def split_text(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    model_name: str | None = None,
    bypass_long_context: bool = False,
) -> list[str]:
    """Divide texto em chunks com RecursiveCharacterTextSplitter.

    Se bypass_long_context e model_name for de contexto longo (Gemini),
    retorna [text] (1 chamada, sem merge). Também retorna [text] se já couber.
    """
    if bypass_long_context and model_name and is_gemini_model(model_name):
        logging.debug("[d] Long context — chunking ignorado (%d chars)", len(text))
        return [text]
    if len(text) <= chunk_size:
        return [text]
    logging.debug("[d] Splitting: chunk_size=%d | overlap=%d", chunk_size, chunk_overlap)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=_SEPARATORS,
    )
    return splitter.split_text(text)
```

### Passos

1. Criar `src/llm_utils.py`.
2. `analyzer._split_text(text, model_name)` → chama `split_text(text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, model_name=model_name, bypass_long_context=True)`. Manter o wrapper `_split_text` se os call sites internos forem muitos.
3. `formatter`/`prompter` → trocar a instanciação local por `split_text(text, chunk_size=FORMAT_CHUNK_SIZE/PROMPT_CHUNK_SIZE, chunk_overlap=...)` (sem bypass).
4. Manter as constantes de tamanho em cada módulo (são parte da configuração de cada estágio — não centralizar).

### Riscos

- Cuidado com import circular: `llm_utils` importa `is_gemini_model` de `llm_factory`; garantir que `llm_factory` **não** importe `llm_utils`.
- Não alterar `separators` nem a semântica do bypass — o analyzer depende disso para coerência/quota.

### Verificação

- `uv run pytest -m unit -v` (há `test_llm_factory.py`; considerar adicionar `test_llm_utils.py` cobrindo: texto curto → 1 chunk; Gemini+bypass → 1 chunk; texto longo Ollama → N chunks).
- Critério: uma só definição de splitter; comportamento de chunking inalterado.

---

## Refactor E — Limpar `progress_view.py` e migrar Transcrição ao padrão `pipeline_log`

### Problema

`src/gui/views/progress_view.py` (645 linhas) carrega o **único `TODO` do repositório**: `# --- eventos legados de Transcrição (TODO(PR3): remover) ---`. A Transcrição é o único módulo que **não** adotou o padrão `pipeline_log.resolve_messages()` / `resolve_stage_label()` usado por audio/video/image; em vez disso, `_resolve_messages` (166 linhas) trata os eventos de transcrição inline. Resultado: dois mecanismos coexistindo no mesmo arquivo.

### Objetivo

Criar `src/gui/modules/transcription/pipeline_log.py` no mesmo molde dos outros módulos e mover a tradução dos eventos de transcrição para lá, enxugando `progress_view._resolve_messages` ao passthrough genérico.

### Arquivos

**Novo:** `src/gui/modules/transcription/pipeline_log.py`
**Modificados:** `src/gui/views/progress_view.py`, possivelmente `src/gui/workers.py` (worker de transcrição) e `src/gui/modules/transcription/view.py`.

### Passos

1. Estudar os outros `pipeline_log.py` (audio/video/image) como referência de assinatura: constantes `OP_VERBS`/`OP_LABELS`, builders `fmt_*`, `resolve_messages(event)` e `resolve_stage_label(event)`.
2. Inventariar os eventos de transcrição tratados em `_resolve_messages`: `metadata_start/done`, `audio_cached`, `download_start/done`, `whisper_loading/loaded`, `transcribe_started`, `language_detected`, `transcribe_segment`, `transcribe_summary`, `format_*`, `analyze_*`, `translation_*`, `prompt_*` (lista no CLAUDE.md).
3. Mover cada caso para `transcription/pipeline_log.py::resolve_messages`, preservando exatamente as strings exibidas.
4. Em `progress_view.py`: substituir o bloco legado por `resolve_messages` despachado pelo `module_id`/`owner_id` do painel (mesmo mecanismo já usado pelos outros módulos). Remover o comentário `TODO(PR3)`.
5. Conferir a barra determinada da transcrição (`transcribe_segment.end / audio_duration`) — essa lógica de **progresso** pode permanecer em `progress_view`; só a tradução de **mensagens** migra.

### Riscos

- Alto volume de strings — qualquer divergência muda o que o usuário vê. Comparar saída antes/depois lado a lado.
- Não quebrar o escopo por `owner_id`: o painel de transcrição deve continuar ignorando eventos de outros módulos.
- `workers.py` (transcrição) ainda usa stage `"pipeline"`/`module_id="transcription"`; manter consistência.

### Verificação

- `uv run pytest -m unit -v`.
- Smoke manual: `uv run main.py <URL> --format --analyze` (CLI não usa progress_view) **e** `uv run gui.py` → módulo Transcrição → rodar pipeline completo e comparar o log com o comportamento atual (idealmente capturar o log antes da refatoração).
- Critério: `progress_view.py` significativamente menor, `_resolve_messages` reduzido a passthrough genérico, zero `TODO(PR3)`, Transcrição alinhada ao padrão dos demais módulos.

---

## PRIORIDADE BAIXA

## Refactor F — Manutenibilidade e testabilidade

### F1 — `build_audio_player` (231 linhas) → mover lógica para a classe `AudioPlayer`

`src/gui/components/audio_player.py::build_audio_player` é uma função-fábrica com uma closure gigante misturando construção de UI (play/pause/seek/anel de carregamento) e lógica de decodificação/playback (ffmpeg → PCM → sounddevice em thread).

- **Objetivo:** a classe `AudioPlayer` já existe — mover para ela o estado e os métodos de decodificação/playback/seek; `build_audio_player` fica só com a montagem dos controles e o *wiring* de callbacks.
- **Quirks:** `ft.Audio` não existe no 0.85 (por isso sounddevice+ffmpeg); `on_change_end` para o seek (não `on_change`); um `update()` por evento.
- **Verificação:** smoke manual no módulo Áudio — tocar/pausar/seek após um pipeline; confirmar o anel de carregamento e o carregamento automático em `_on_done`.

### F2 — ~~Mover `download_audio` para `core/`~~ → ABSORVIDO pela CLI Fase 0

❌ **Removido deste plano.** Confirmado no código: existem dois `download_audio` — `src/utils.py:227` usando `subprocess.run(..., text=True)` (bug cp1252) e `src/core/audio/downloader.py:19` (correto, modo binário). A **CLI Fase 0** (`REFACTORING.md`) já deleta `utils.download_audio` e migra todos os call sites para `src/core/audio/downloader.download_audio`. Nada a fazer aqui — não duplicar o esforço.

### F3 — Tornar a lógica dos workers testável

> 🔗 **Pré-requisito: CLI Fase 2 + Refactor A (Plano 1).** A Fase 2 tira os `*Args` da GUI e o Refactor A transforma o corpo do loop em `process_item` com `emit` injetável — as duas coisas que tornam os workers testáveis sem Flet.

Hoje `src/gui/` é excluído da cobertura (Flet não é testável headless), mas os workers contêm orquestração real (sequência de operações, decisão download/extract/convert por extensão, contagem de falhas). Após o Refactor A (Plano 1), o `process_item` de cada módulo é uma função quase pura (recebe `emit` injetável).

- **Objetivo:** adicionar testes unitários para `process_item`/runner passando um `emit` fake (lista de eventos) e mocks dos `core.*` (via `pytest-mock`), asserts sobre a sequência de eventos emitidos e os `output_paths`. Marcar como `unit`.
- **Arquivos:** `tests/gui/modules/{audio,video,image}/test_worker.py`.
- **Verificação:** `uv run pytest -m unit -v`; conferir que a cobertura passa a incluir a lógica dos workers (ajustar `--cov` se `src/gui` estiver hard-excluído na config).

---

## Ordem de execução sugerida

1. **C** (ffmpeg) — isolado em `core/`, bem coberto por testes de integração; baixo risco.
2. **D** (split_text) — isolado, testável; baixo risco.
3. **E** (progress_view / transcrição) — maior, mais sensível a strings; fazer com captura de log antes/depois.
4. **F1** (AudioPlayer) — incremental, independente.
5. **F3** (testar workers) — **depende da CLI Fase 2 + Refactor A** (Plano 1).

> **F2 saiu** — absorvido pela CLI Fase 0.

Commit a cada etapa, sempre após `uv run pytest -m unit`.
