# PR3.1-A: AUDIO

## Plano de implementação — PR3.1-A: Normalizar + Reduzir Ruído

### Arquitetura de execução

As duas operações são **pós-processamentos encadeados** que rodam após a operação principal (download/convert/extract). O usuário ativa cada um via switch no formulário.

```
item (URL ou local)
  → operação principal  (download / convert / extract)   ← já existe
  → [se denoise=True]   → denoiser.denoise()              ← novo
  → [se normalize=True] → normalizer.normalize_lufs()     ← novo
  → emit audio_op_done com output_path final
```

---

### Arquivos a criar/modificar

```
src/core/audio/
  denoiser.py           ← CRIAR
  normalizer.py         ← CRIAR

src/gui/modules/audio/
  pipeline_log.py       ← CRIAR  (padrão modules/image/pipeline_log.py)
  form_view.py          ← MODIFICAR
  worker.py             ← MODIFICAR
  view.py               ← MODIFICAR

src/gui/
  help_content.py       ← MODIFICAR

pyproject.toml          ← MODIFICAR
```

---

### 1. Dependências

`pyproject.toml` — adicionar em `[project.dependencies]`:

```toml
"noisereduce>=3.0",   # spectral gating; scipy + numpy, sem ML
"soundfile>=0.12",    # leitura/escrita de áudio PCM (não vem com faster-whisper)
```

Sem novo extra. Ambas são scipy-based, entram na base como Pillow entrou para imagens.

---

### 2. `src/core/audio/denoiser.py` — CRIAR

```python
"""Redução de ruído espectral via noisereduce (spectral gating, CPU-only)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def is_available() -> bool:
    """True se noisereduce e soundfile estiverem instalados."""
    try:
        import noisereduce  # noqa: F401
        import soundfile    # noqa: F401
        return True
    except ImportError:
        return False


def denoise(src: Path, out_dir: Path, stationary: bool = True) -> Path:
    """Atenua ruído de fundo estacionário via spectral gating.

    Decodifica qualquer formato para WAV temporário via ffmpeg,
    processa com noisereduce e salva resultado em WAV.

    Args:
        src: Arquivo de áudio (qualquer formato suportado pelo ffmpeg).
        out_dir: Diretório de saída.
        stationary: True = ruído constante (fan, hum). False = adaptativo.

    Returns:
        Path do arquivo denoised (.wav).
    """
    import numpy as np
    import noisereduce as nr
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Decodifica para WAV PCM temporário (lida com MP3/M4A/qualquer fmt) ──
    tmp_wav = out_dir / f".tmp_denoise_{src.stem}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "0", str(tmp_wav)],
        check=True,
        capture_output=True,
    )

    try:
        audio, sr = sf.read(str(tmp_wav))

        if audio.ndim == 2:
            # Estéreo: processa canal por canal e reconstrói
            channels = [
                nr.reduce_noise(y=audio[:, c], sr=sr, stationary=stationary)
                for c in range(audio.shape[1])
            ]
            denoised = np.stack(channels, axis=1)
        else:
            denoised = nr.reduce_noise(y=audio, sr=sr, stationary=stationary)

        out_path = out_dir / f"{src.stem}_denoised.wav"
        sf.write(str(out_path), denoised, sr)
    finally:
        tmp_wav.unlink(missing_ok=True)

    return out_path
```

---

### 3. `src/core/audio/normalizer.py` — CRIAR

Usa dois passes do `ffmpeg loudnorm`: primeiro mede o loudness integrado, depois aplica ganho linear preciso.

```python
"""Normalização de loudness via ffmpeg loudnorm (EBU R128 / ITU-R BS.1770-4)."""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Callable

from src.core.audio.info import get_duration_ffprobe

_TARGET_TP  = -1.0   # True Peak máximo (dBFS)
_TARGET_LRA = 11.0   # Loudness Range alvo


def normalize_lufs(
    src: Path,
    out_dir: Path,
    target_lufs: float = -14.0,
    progress_cb: Callable[[float], None] | None = None,
) -> tuple[Path, dict | None]:
    """Normaliza loudness integrado para target_lufs (EBU R128, dois passes).

    Args:
        src: Arquivo de entrada (qualquer formato ffmpeg).
        out_dir: Diretório de saída.
        target_lufs: Alvo em LUFS (ex: -14.0 streaming, -23.0 broadcast).
        progress_cb: Chamado com float 0.0-1.0 durante o segundo passe.

    Returns:
        Tupla (out_path, stats_dict | None).
        stats_dict contém os valores medidos (input_i, input_tp, input_lra…).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_normalized{src.suffix}"

    # ── Passe 1: medição ──────────────────────────────────────────────────
    measure_cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-af", (
            f"loudnorm=I={target_lufs}:TP={_TARGET_TP}"
            f":LRA={_TARGET_LRA}:print_format=json"
        ),
        "-f", "null", "-",
    ]
    r = subprocess.run(measure_cmd, capture_output=True, text=True)
    stats = _parse_loudnorm_json(r.stderr)

    # ── Passe 2: aplicação ────────────────────────────────────────────────
    if stats:
        af = (
            f"loudnorm=I={target_lufs}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"
            f":measured_I={stats['input_i']}"
            f":measured_LRA={stats['input_lra']}"
            f":measured_TP={stats['input_tp']}"
            f":measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}"
            f":linear=true"
        )
    else:
        # Fallback passe único (menos preciso, sem clipagem crítica)
        af = f"loudnorm=I={target_lufs}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"

    apply_cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-af", af,
        "-progress", "pipe:1", "-nostats",
        str(out_path),
    ]

    total_secs = get_duration_ffprobe(src) if progress_cb else None
    proc = subprocess.Popen(
        apply_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    stderr_lines: list[str] = []

    def _drain() -> None:
        for line in proc.stderr:
            stderr_lines.append(line.rstrip())

    threading.Thread(target=_drain, daemon=True).start()

    for line in proc.stdout:
        if line.strip().startswith("out_time_us=") and progress_cb and total_secs:
            try:
                ratio = min(int(line.strip().split("=", 1)[1]) / 1_000_000 / total_secs, 1.0)
                progress_cb(ratio)
            except (ValueError, IndexError):
                pass

    proc.wait()
    if proc.returncode != 0:
        tail = "\n".join(stderr_lines[-10:]) if stderr_lines else "(sem detalhes)"
        raise RuntimeError(f"ffmpeg loudnorm retornou {proc.returncode}: {tail}")

    if not out_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado após loudnorm: {out_path}")

    return out_path, stats


def _parse_loudnorm_json(stderr: str) -> dict | None:
    """Extrai o bloco JSON de estatísticas loudnorm do stderr do ffmpeg."""
    lines = stderr.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == "{"), None)
    if start is None:
        return None
    end = next((i for i, l in enumerate(lines[start:], start) if l.strip() == "}"), None)
    if end is None:
        return None
    try:
        return json.loads("\n".join(lines[start : end + 1]))
    except json.JSONDecodeError:
        return None
```

> **Nota de design:** `normalize_lufs` retorna `(path, stats)` para que o worker possa emitir `fmt_normalize_measured(il, lra, tp)` com os valores reais medidos no log.

---

### 4. `src/gui/modules/audio/pipeline_log.py` — CRIAR

Segue exatamente o padrão de `modules/image/pipeline_log.py`. Cobre as 5 operações do módulo (download, convert, extract já existentes + denoise + normalize novos).

```python
"""Vocabulário de mensagens do pipeline de áudio.

Importado por:
  worker.py  — fmt_* para emit("log", ...)
  view.py    — resolve_* para PipelineEvent → display
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import PipelineEvent


# ─── Constantes ────────────────────────────────────────────────────────────────

OP_VERBS: dict[str, str] = {
    "download":  "Baixando",
    "convert":   "Convertendo",
    "extract":   "Extraindo áudio",
    "denoise":   "Reduzindo ruído",
    "normalize": "Normalizando volume",
}

OP_LABELS: dict[str, str] = {
    "download":  "Baixando...",
    "convert":   "Convertendo...",
    "extract":   "Extraindo áudio...",
    "denoise":   "Reduzindo ruído (spectral)...",
    "normalize": "Normalizando (loudnorm — 2 passes)...",
}


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1_048_576:
        return f"{b / 1024:.0f} KB"
    return f"{b / 1_048_576:.1f} MB"


def _relative_output_dir(path_str: str) -> str:
    try:
        parts = Path(path_str).parent.parts
        idx = next(i for i, p in enumerate(parts) if p == "output")
        return "/".join(parts[idx:]) + "/"
    except (StopIteration, Exception):
        return str(Path(path_str).parent)


# ─── Builders — informação geral ──────────────────────────────────────────────

def fmt_audio_info(name: str, duration: float | None, size_bytes: int) -> str:
    dur = f"{duration:.1f}s" if duration else "duração desconhecida"
    return f"[i] {name} | {dur} | {_fmt_size(size_bytes)}"


# ─── Builders — denoise ────────────────────────────────────────────────────────

def fmt_denoise_start(name: str) -> str:
    return f"[*] Spectral gating: {name}…"


def fmt_denoise_detail(stationary: bool) -> str:
    mode = "estacionário (rápido)" if stationary else "adaptativo (mais lento)"
    return f"[i] Modo: {mode}"


# ─── Builders — normalize ─────────────────────────────────────────────────────

def fmt_normalize_start(name: str) -> str:
    return f"[*] Loudnorm — passe 1 (medição): {name}…"


def fmt_normalize_detail(target_lufs: float) -> str:
    return f"[i] Alvo: {target_lufs:.1f} LUFS | TP: {-1.0} dBFS | LRA: 11 LU"


def fmt_normalize_measured(stats: dict) -> str:
    il  = stats.get("input_i",   "?")
    lra = stats.get("input_lra", "?")
    tp  = stats.get("input_tp",  "?")
    return f"[i] Medido: IL={il} LUFS | LRA={lra} LU | TP={tp} dBTP"


def fmt_normalize_apply(name: str) -> str:
    return f"[*] Loudnorm — passe 2 (aplicação): {name}…"


def fmt_normalize_fallback() -> str:
    return "[»] Medição indisponível — usando passo único (menos preciso)"


# ─── Resolvers (view.py) ──────────────────────────────────────────────────────

def resolve_messages(event: "PipelineEvent") -> list[str]:
    p = event.payload
    match event.type:
        case "audio_op_start":
            op   = p.get("operation", "")
            name = p.get("item_name", "")
            verb = OP_VERBS.get(op, "Processando")
            return [f"[~] {verb}: {name}"]
        case "audio_op_done":
            path    = p.get("output_path", "")
            elapsed = p.get("elapsed", "")
            idx     = p.get("item_idx", 1)
            total   = p.get("total", 1)
            src_sz  = p.get("src_size_bytes", 0)
            out_sz  = p.get("out_size_bytes", 0)
            name    = Path(path).name if path else path
            sz      = f" | {_fmt_size(src_sz)} → {_fmt_size(out_sz)}" if src_sz and out_sz else ""
            prefix  = f"{idx}/{total} — " if total > 1 else ""
            folder  = _relative_output_dir(path)
            return [
                f"[✓] {prefix}Salvo: {name} ({elapsed}){sz}",
                f"[i] Pasta: {folder}",
            ]
        case "task_done":
            paths = p.get("output_paths", [])
            return [f"[✓] Concluído — {len(paths)} arquivo(s) gerado(s)."]
        case "task_error":
            return [f"[!] {p.get('message', 'erro desconhecido')}"]
        case "log":
            msg = p.get("message", "")
            return [msg] if msg else []
        case _:
            return []


def resolve_stage_label(event: "PipelineEvent") -> str | None:
    p = event.payload
    match event.type:
        case "progress_start":
            return "Iniciando..."
        case "queue_progress":
            cur  = p.get("current_item", "?")
            tot  = p.get("total_items",  "?")
            name = p.get("item_name", "")
            return f"Item {cur}/{tot}" + (f" — {name}" if name else "")
        case "audio_op_start":
            return OP_LABELS.get(p.get("operation", ""), "Processando...")
        case "audio_op_done":
            idx = p.get("item_idx", 1)
            tot = p.get("total",    1)
            return f"Item {idx}/{tot} concluído." if tot > 1 else "Concluído."
        case "task_done":
            return "Pipeline concluído!"
        case "task_error":
            return "Erro no pipeline."
        case _:
            return None
```

---

### 5. `form_view.py` — MODIFICAR

**5.1 Expandir `AudioArgs`:**

```python
@dataclass
class AudioArgs:
    items: list[InputItem] = field(default_factory=list)
    fmt: str = "mp3"
    quality: str = "best"
    embed_meta: bool = True
    # PR3.1 — pós-processamento:
    denoise: bool = False
    normalize: bool = False
    normalize_target_lufs: float = -14.0
```

**5.2 Nova seção após Bitrate, antes do botão Iniciar** (usando DS corretamente):

```python
# ── Switches de pós-processamento ─────────────────────────────────────

denoise_switch = ft.Switch(
    label="Reduzir ruído (spectral gating)",
    value=cfg.get("last_audio_denoise", False),
    label_text_style=ft.TextStyle(size=13),
    active_color=ft.Colors.PRIMARY,
)

normalize_switch = ft.Switch(
    label="Normalizar volume (loudnorm)",
    value=cfg.get("last_audio_normalize", False),
    label_text_style=ft.TextStyle(size=13),
    active_color=ft.Colors.PRIMARY,
)

# Slider de LUFS — aparece apenas quando normalize ligado
lufs_values: list[float] = [cfg.get("last_audio_lufs", -14.0)]

def _on_lufs_change(e) -> None:
    lufs_values[0] = e.control.value

lufs_slider, _, _set_lufs_disabled = slider_row(
    label="Alvo (LUFS)",
    value=lufs_values[0],
    min_val=-23.0,
    max_val=-6.0,
    divisions=17,          # steps de 1 LUFS
    on_change=_on_lufs_change,
    help_key="audio.normalize_lufs",
    page=page,
)

lufs_block = ft.Container(
    content=lufs_slider,
    visible=bool(normalize_switch.value),
    animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
)

def _on_normalize_change(e) -> None:
    lufs_block.visible = bool(e.control.value)
    if lufs_block.page:
        lufs_block.update()

normalize_switch.on_change = _on_normalize_change
```

No layout, inserir entre a seção de Bitrate e o botão Iniciar:

```python
section(
    "Pós-processamento",
    ft.Row([denoise_switch,  help_icon_for("audio.denoise",    page) or ft.Container()],
           spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ft.Row([normalize_switch, help_icon_for("audio.normalize", page) or ft.Container()],
           spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    lufs_block,
),
```

**5.3 Atualizar `_on_start_click()`:**

```python
settings.save({
    ...,
    "last_audio_denoise":   denoise_switch.value,
    "last_audio_normalize": normalize_switch.value,
    "last_audio_lufs":      lufs_values[0],
})
on_start(AudioArgs(
    ...,
    denoise=bool(denoise_switch.value),
    normalize=bool(normalize_switch.value),
    normalize_target_lufs=lufs_values[0],
))
```

**5.4 Atualizar `_set_running()`:**

```python
denoise_switch.disabled   = running
normalize_switch.disabled = running
_set_lufs_disabled(running)
```

---

### 6. `worker.py` — MODIFICAR

**6.1 Novos imports:**

```python
from src.core.audio.denoiser import denoise as _denoise_audio, is_available as _denoise_available
from src.core.audio.normalizer import normalize_lufs as _normalize_lufs
from src.gui.modules.audio import pipeline_log
```

**6.2 Bloco pós-processamento** (inserir após `out_path` ser definido e antes do `emit("audio_op_done")`):

```python
# ── Pós: Denoise ──────────────────────────────────────────────────────
if args.denoise:
    if not _denoise_available():
        emit("log", payload={"message": "[!] noisereduce não instalado — ignorando denoise."})
    else:
        emit("audio_op_start", payload={
            "operation": "denoise",
            "item_name": out_path.name,
            "item_idx": idx,
            "total": total,
        })
        emit("log", payload={"message": pipeline_log.fmt_denoise_start(out_path.name)})
        emit("log", payload={"message": pipeline_log.fmt_denoise_detail(stationary=True)})
        out_path = _denoise_audio(out_path, AUDIO_PROCESSED_DIR)

# ── Pós: Normalize ────────────────────────────────────────────────────
if args.normalize:
    emit("audio_op_start", payload={
        "operation": "normalize",
        "item_name": out_path.name,
        "item_idx": idx,
        "total": total,
    })
    emit("log", payload={"message": pipeline_log.fmt_normalize_start(out_path.name)})
    emit("log", payload={"message": pipeline_log.fmt_normalize_detail(args.normalize_target_lufs)})

    def _norm_cb(ratio: float) -> None:
        emit("progress_update", payload={"current": ratio})

    out_path, stats = _normalize_lufs(
        out_path, AUDIO_PROCESSED_DIR, args.normalize_target_lufs, _norm_cb
    )

    if stats:
        emit("log", payload={"message": pipeline_log.fmt_normalize_measured(stats)})
    else:
        emit("log", payload={"message": pipeline_log.fmt_normalize_fallback()})
```

**6.3 Atualizar `emit("audio_op_done")`** — adicionar tamanhos e usar `pipeline_log`:

```python
elapsed = time() - t0
output_paths.append(str(out_path))
emit("audio_op_done", payload={
    "output_path":    str(out_path),
    "elapsed":        f"{elapsed:.1f}s",
    "item_idx":       idx,
    "total":          total,
    "src_size_bytes": original_src_size,   # tamanho do arquivo antes de tudo
    "out_size_bytes": out_path.stat().st_size,
})
```

> Guarde `original_src_size = src.stat().st_size` antes dos passos pós-processamento para o diff mostrar o ganho real no log.

---

### 7. `view.py` — MODIFICAR

Importar e delegar ao `pipeline_log` nos handlers de evento do ProgressPanel — substituir qualquer lógica inline de log por:

```python
from src.gui.modules.audio import pipeline_log

# No subscriber:
messages = pipeline_log.resolve_messages(event)
label    = pipeline_log.resolve_stage_label(event)
```

---

### 8. `help_content.py` — MODIFICAR

```python
# HELP_SHORT:
"audio.denoise":        "Atenua ruído de fundo constante (ventilador, hum, chiado de fita) via spectral gating.",
"audio.normalize":      "Ajusta o volume para um nível consistente em LUFS. Não distorce nem clipa.",
"audio.normalize_lufs": "Alvo de loudness. −14 LUFS: streaming. −23 LUFS: broadcast. −16 a −18 LUFS: podcasts.",

# HELP_LONG:
"audio.denoise": (
    "Redução de Ruído — Spectral Gating",
    "Analisa o espectro do áudio e atenua as frequências que se comportam como ruído estacionário. "
    "Bom para ventiladores, ar-condicionado, hum de fio e chiado de fita. "
    "A saída é sempre WAV para não perder qualidade no passo intermediário.",
),
"audio.normalize": (
    "Normalização de Volume — EBU R128",
    "Usa o filtro loudnorm do ffmpeg em dois passos: primeiro mede o loudness integrado (LUFS), "
    "depois aplica ganho linear para atingir o alvo preservando o True Peak (máx. −1 dBFS). "
    "−14 LUFS é o padrão de Spotify, Apple Music e YouTube. "
    "−23 LUFS é o padrão de broadcast (TV/rádio). Podcasts geralmente usam −16 a −18 LUFS.",
),
```

---

### 9. Checklist de implementação

**Fase 1 — Core (sem GUI, testável isolado)**
- [ ] Criar `src/core/audio/denoiser.py`
- [ ] Criar `src/core/audio/normalizer.py`
- [ ] Adicionar `noisereduce>=3.0` e `soundfile>=0.12` em `pyproject.toml`
- [ ] `uv sync` e testar as funções com um arquivo WAV real no REPL

**Fase 2 — Vocabulário**
- [ ] Criar `src/gui/modules/audio/pipeline_log.py` com os 5 `OP_VERBS`/`OP_LABELS`
- [ ] Implementar todos os `fmt_*` builders
- [ ] Implementar `resolve_messages()` e `resolve_stage_label()`

**Fase 3 — Worker**
- [ ] Expandir `AudioArgs` (3 novos campos)
- [ ] Adicionar imports de `denoiser`, `normalizer`, `pipeline_log` no `worker.py`
- [ ] Guardar `original_src_size` antes dos pós-processos
- [ ] Inserir blocos denoise + normalize após `out_path`
- [ ] Atualizar `emit("audio_op_done")` com tamanhos
- [ ] Verificar que `pipeline_running[0]` é resetado em todos os caminhos (success/error/cancel)

**Fase 4 — Formulário**
- [ ] Expandir `AudioArgs` no `form_view.py`
- [ ] Criar `denoise_switch` + `help_icon_for("audio.denoise")`
- [ ] Criar `normalize_switch` + `help_icon_for("audio.normalize")`
- [ ] Criar `lufs_block` com `slider_row` (−23 a −6, 17 divisões) + `animate_opacity`
- [ ] Conectar `on_change` do normalize_switch à visibilidade do `lufs_block`
- [ ] Salvar/restaurar estado nos 3 novos campos via `settings`
- [ ] Atualizar `_set_running()` para desabilitar os novos controles

**Fase 5 — View e help**
- [ ] Importar e usar `pipeline_log` no `view.py`
- [ ] Adicionar as 3 chaves em `help_content.py` (`HELP_SHORT` + `HELP_LONG`)

**Fase 6 — Testes manuais**
- [ ] Download URL → normalize
- [ ] Download URL → denoise → normalize (encadeado)
- [ ] Arquivo local → denoise apenas
- [ ] Arquivo local → normalize apenas
- [ ] Cancelar durante denoise (verificar thread não vaza)
- [ ] Cancelar durante o passe 1 do loudnorm (processo ffmpeg termina limpo)
- [ ] `noisereduce` não instalado → log `[!]` claro, pipeline continua