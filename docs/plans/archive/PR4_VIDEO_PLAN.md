# PR4

## Plano de implementação — PR4: Módulo Vídeo

> **Design System:** antes de criar qualquer componente GUI, ler `.claude/skills/design-system/SKILL.md` (ou invocar `Skill("design-system")`) para carregar factories, tokens e convenções de cursor corretas.
> Consultar `src/gui/modules/image/pipeline_log.py` como referência canônica para o vocabulário de mensagens.

---

### Premissas

- **Sem NVENC** — decisão definitiva. Encoding 100% CPU (`libx264`, `libx265`, `libvpx-vp9`).
- Nenhum pacote Python novo — `ffmpeg` (subprocess) + `yt-dlp` (já instalado).
- Módulo Vídeo é o análogo direto do módulo Áudio: mesma arquitetura de worker, eventos, fila, `pipeline_log`.
- O placeholder `src/gui/modules/video/view.py` já existe — substituir o conteúdo.

---

### Arquivos a criar/modificar

```
src/core/video/
  __init__.py           ← CRIAR
  downloader.py         ← CRIAR
  converter.py          ← CRIAR
  info.py               ← CRIAR

src/gui/modules/video/
  __init__.py           ← JÁ EXISTE (manter)
  form_view.py          ← CRIAR
  worker.py             ← CRIAR
  view.py               ← MODIFICAR (substituir placeholder)
  pipeline_log.py       ← CRIAR

src/gui/
  help_content.py       ← MODIFICAR
  app.py                ← MODIFICAR (registrar módulo na NavigationRail)
```

---

### Operações do módulo (7 operações)

| ID              | Nome exibido      | Entrada | Core                       |
| --------------- | ----------------- | ------- | -------------------------- |
| `download`      | Baixar vídeo      | URL     | `yt-dlp`                   |
| `convert`       | Converter formato | local   | `ffmpeg -c:v ... -c:a ...` |
| `trim`          | Recortar          | local   | `ffmpeg -ss -to`           |
| `compress`      | Comprimir         | local   | `ffmpeg -crf`              |
| `resize`        | Redimensionar     | local   | `ffmpeg -vf scale`         |
| `extract_audio` | Extrair áudio     | local   | `ffmpeg -vn` (bridge)      |
| `thumbnail`     | Gerar thumbnail   | local   | `ffmpeg -vframes 1`        |

**Detecção automática de operação por tipo de entrada:**
- URL → força `download`
- Arquivo local → operação escolhida pelo usuário

---

### 1. `src/core/video/info.py` — CRIAR

```python
"""Inspeção de arquivos de vídeo via ffprobe."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class VideoInfo:
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    vcodec: str | None
    acodec: str | None
    size_bytes: int


def get_video_info(src: Path) -> VideoInfo:
    """Retorna metadados via ffprobe (streams de vídeo e áudio)."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(src),
            ],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        a = next((s for s in streams if s.get("codec_type") == "audio"), {})

        fps = None
        r_fps = v.get("r_frame_rate", "")
        if "/" in r_fps:
            num, den = r_fps.split("/")
            fps = float(num) / float(den) if float(den) else None

        return VideoInfo(
            duration=float(fmt.get("duration", 0)) or None,
            width=v.get("width"),
            height=v.get("height"),
            fps=fps,
            vcodec=v.get("codec_name"),
            acodec=a.get("codec_name"),
            size_bytes=int(fmt.get("size", 0)),
        )
    except Exception:
        return VideoInfo(None, None, None, None, None, None, 0)
```

---

### 2. `src/core/video/downloader.py` — CRIAR

```python
"""Download de vídeo via yt-dlp com suporte a progresso e metadados."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Callable
import yt_dlp

logger = logging.getLogger(__name__)

# Resoluções máximas permitidas
_RESOLUTIONS = {"best": None, "2160": 2160, "1080": 1080, "720": 720, "480": 480, "360": 360}

# Formatos de container preferidos
_NO_COVER_FMTS = {"webm", "mkv"}


def download_video(
    url: str,
    out_dir: Path,
    resolution: str = "1080",
    container: str = "mp4",
    embed_meta: bool = True,
    progress_hook: Callable[[dict], None] | None = None,
) -> Path:
    """Baixa vídeo de URL para out_dir.

    Args:
        url: URL do YouTube, etc.
        out_dir: Diretório de saída.
        resolution: Resolução máxima ("best", "2160", "1080", "720", "480", "360").
        container: Container de saída ("mp4", "mkv", "webm").
        embed_meta: Embutir metadados.
        progress_hook: Chamado com dict yt-dlp.

    Returns:
        Path do arquivo baixado.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Format string yt-dlp ──────────────────────────────────────────────
    max_h = _RESOLUTIONS.get(resolution)
    if max_h:
        if container == "webm":
            fmt = (
                f"bestvideo[height<={max_h}][vcodec^=vp]+bestaudio[acodec^=opus]"
                f"/bestvideo[height<={max_h}]+bestaudio/best[height<={max_h}]"
            )
        else:
            fmt = (
                f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={max_h}]+bestaudio/best[height<={max_h}]"
            )
    else:
        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

    postprocessors: list[dict] = []
    if container == "mp4":
        postprocessors.append({"key": "FFmpegVideoConvertor", "preferedformat": "mp4"})
    if embed_meta:
        postprocessors.append({"key": "FFmpegMetadata"})

    final_path: list[str] = []

    def _pp_hook(d: dict) -> None:
        if d.get("status") == "finished":
            fp = d.get("info_dict", {}).get("filepath") or d.get("filepath", "")
            if fp:
                final_path.append(fp)

    ydl_opts = {
        "format": fmt,
        "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
        "postprocessors": postprocessors,
        "postprocessor_hooks": [_pp_hook],
        "progress_hooks": [progress_hook] if progress_hook else [],
        "merge_output_format": container,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if final_path and Path(final_path[-1]).exists():
        return Path(final_path[-1])

    if info:
        downloads = info.get("requested_downloads", [])
        if downloads:
            fp = downloads[0].get("filepath", "")
            if fp and Path(fp).exists():
                return Path(fp)

    files = sorted(
        (f for f in out_dir.iterdir() if f.is_file()),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    if files:
        return files[0]

    raise FileNotFoundError(f"Download concluído mas arquivo não encontrado em: {out_dir}")
```

---

### 3. `src/core/video/converter.py` — CRIAR

Cada função espelha o padrão de `src/core/audio/converter.py`: recebe `src`, `out_dir`, parâmetros, `progress_cb` opcional, retorna `Path`.

```python
"""Operações de vídeo via ffmpeg: convert, trim, compress, resize, thumbnail, extract_audio."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

from src.core.video.info import get_video_info

# Codecs disponíveis (sem NVENC — decisão definitiva)
VCODEC_MAP = {
    "copy":  ["-c:v", "copy"],
    "h264":  ["-c:v", "libx264", "-preset", "medium"],
    "h265":  ["-c:v", "libx265", "-preset", "medium"],
    "vp9":   ["-c:v", "libvpx-vp9"],
}
CONTAINER_EXT = {"mp4": "mp4", "mkv": "mkv", "webm": "webm", "avi": "avi"}


def _run_ffmpeg(
    cmd: list[str],
    src: Path,
    out_path: Path,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Executa ffmpeg com progresso estruturado via -progress pipe:1."""
    info = get_video_info(src)
    total_secs = info.duration if progress_cb else None

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

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
        raise RuntimeError(f"ffmpeg retornou {proc.returncode}: {tail}")

    if not out_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {out_path}")

    return out_path


def convert_video(
    src: Path, out_dir: Path,
    container: str = "mp4",
    vcodec: str = "copy",
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Converte container e/ou codec. 'copy' = sem reencoding (rápido)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = CONTAINER_EXT.get(container, "mp4")
    out_path = out_dir / f"{src.stem}_converted.{ext}"
    codec_flags = VCODEC_MAP.get(vcodec, ["-c:v", "copy"])
    cmd = ["ffmpeg", "-y", "-i", str(src)] + codec_flags + ["-c:a", "copy",
           "-progress", "pipe:1", "-nostats", str(out_path)]
    return _run_ffmpeg(cmd, src, out_path, progress_cb)


def trim_video(
    src: Path, out_dir: Path,
    start: str = "", end: str = "",
    reenc: bool = False,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Recorta vídeo entre start e end (formato HH:MM:SS ou SS).
    
    reenc=False usa -c copy (rápido, corte no keyframe mais próximo).
    reenc=True usa libx264 (lento, corte frame-preciso).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_trimmed{src.suffix}"

    cmd = ["ffmpeg", "-y"]
    if start:
        cmd += ["-ss", start]
    cmd += ["-i", str(src)]
    if end:
        cmd += ["-to", end]

    if reenc:
        cmd += ["-c:v", "libx264", "-c:a", "aac"]
    else:
        cmd += ["-c", "copy"]

    cmd += ["-progress", "pipe:1", "-nostats", str(out_path)]
    return _run_ffmpeg(cmd, src, out_path, progress_cb)


def compress_video(
    src: Path, out_dir: Path,
    crf: int = 23,
    preset: str = "medium",
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Reencoda com H.264/CRF para reduzir tamanho.
    
    crf: 18 (alta qualidade) → 28 (alta compressão). Padrão 23.
    preset: ultrafast, fast, medium, slow (qualidade vs velocidade).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_compressed.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        "-c:a", "aac", "-b:a", "128k",
        "-progress", "pipe:1", "-nostats",
        str(out_path),
    ]
    return _run_ffmpeg(cmd, src, out_path, progress_cb)


def resize_video(
    src: Path, out_dir: Path,
    width: int = 0, height: int = 0,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Redimensiona vídeo preservando aspect ratio.
    
    Passar apenas width ou height: o outro eixo usa -2 (múltiplo de 2 compatível).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_resized.mp4"
    w = width if width else -2
    h = height if height else -2
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale={w}:{h}",
        "-c:v", "libx264", "-crf", "23",
        "-c:a", "copy",
        "-progress", "pipe:1", "-nostats",
        str(out_path),
    ]
    return _run_ffmpeg(cmd, src, out_path, progress_cb)


def extract_audio_from_video(
    src: Path, out_dir: Path,
    audio_fmt: str = "mp3",
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Extrai faixa de áudio do vídeo.
    
    Wrapper sobre src/core/audio/converter.py::extract_audio para consistência.
    """
    from src.core.audio.converter import extract_audio
    return extract_audio(src, out_dir, fmt=audio_fmt, progress_cb=progress_cb)


def make_thumbnail(
    src: Path, out_dir: Path,
    time: str = "00:00:01",
    fmt: str = "jpg",
) -> Path:
    """Extrai um frame do vídeo como imagem."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_thumb.{fmt}"
    cmd = [
        "ffmpeg", "-y",
        "-ss", time,
        "-i", str(src),
        "-vframes", "1",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"Thumbnail falhou para {src.name}")
    return out_path
```

---

### 4. `src/gui/modules/video/pipeline_log.py` — CRIAR

Segue exatamente o padrão de `modules/image/pipeline_log.py`.

```python
"""Vocabulário de mensagens do pipeline de vídeo."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.events import PipelineEvent

OP_VERBS: dict[str, str] = {
    "download":      "Baixando",
    "convert":       "Convertendo",
    "trim":          "Recortando",
    "compress":      "Comprimindo",
    "resize":        "Redimensionando",
    "extract_audio": "Extraindo áudio",
    "thumbnail":     "Gerando thumbnail",
}

OP_LABELS: dict[str, str] = {
    "download":      "Baixando vídeo...",
    "convert":       "Convertendo formato...",
    "trim":          "Recortando (ffmpeg)...",
    "compress":      "Comprimindo (H.264/CRF)...",
    "resize":        "Redimensionando...",
    "extract_audio": "Extraindo áudio...",
    "thumbnail":     "Gerando thumbnail...",
}

def _fmt_size(b: int) -> str:
    if b < 1024: return f"{b} B"
    if b < 1_048_576: return f"{b/1024:.0f} KB"
    return f"{b/1_048_576:.1f} MB"

def _relative_output_dir(path_str: str) -> str:
    try:
        parts = Path(path_str).parent.parts
        idx = next(i for i, p in enumerate(parts) if p == "output")
        return "/".join(parts[idx:]) + "/"
    except Exception:
        return str(Path(path_str).parent)

# ── Builders ──────────────────────────────────────────────────────────────────

def fmt_video_info(info) -> str:
    """[i] resolução | fps | codec_v/codec_a | tamanho"""
    res = f"{info.width}×{info.height}" if info.width else "?"
    fps = f"{info.fps:.1f}fps" if info.fps else "?"
    vc  = info.vcodec or "?"
    ac  = info.acodec or "?"
    sz  = _fmt_size(info.size_bytes)
    dur = f"{info.duration:.1f}s" if info.duration else "?"
    return f"[i] {res} | {fps} | {vc}/{ac} | {dur} | {sz}"

def fmt_download_detail(resolution: str, container: str) -> str:
    res = f"máx. {resolution}p" if resolution != "best" else "melhor disponível"
    return f"[i] Resolução: {res} | Container: {container.upper()}"

def fmt_convert_detail(vcodec: str, container: str) -> str:
    codec_labels = {"copy": "sem reencoding (copy)", "h264": "H.264 (libx264)",
                    "h265": "H.265 (libx265)", "vp9": "VP9 (libvpx-vp9)"}
    return f"[i] Codec: {codec_labels.get(vcodec, vcodec)} → {container.upper()}"

def fmt_trim_detail(start: str, end: str, reenc: bool) -> str:
    s = start or "início"
    e = end   or "fim"
    mode = "frame-preciso (reenc)" if reenc else "rápido (copy)"
    return f"[i] Corte: {s} → {e} | Modo: {mode}"

def fmt_compress_detail(crf: int, preset: str) -> str:
    q = "alta" if crf <= 18 else ("boa" if crf <= 23 else "comprimida")
    return f"[i] CRF: {crf} (qualidade {q}) | Preset: {preset}"

def fmt_resize_detail(width: int, height: int) -> str:
    w = str(width)  if width  else "auto"
    h = str(height) if height else "auto"
    return f"[i] Dimensões: {w}×{h} (aspect ratio preservado)"

def fmt_thumbnail_detail(time: str, fmt: str) -> str:
    return f"[i] Frame em {time} → .{fmt.upper()}"

# ── Resolvers ─────────────────────────────────────────────────────────────────

def resolve_messages(event: "PipelineEvent") -> list[str]:
    p = event.payload
    match event.type:
        case "video_op_start":
            verb = OP_VERBS.get(p.get("operation", ""), "Processando")
            return [f"[~] {verb}: {p.get('item_name', '')}"]
        case "video_op_done":
            path   = p.get("output_path", "")
            name   = Path(path).name if path else path
            elapsed = p.get("elapsed", "")
            idx, tot = p.get("item_idx", 1), p.get("total", 1)
            src_sz, out_sz = p.get("src_size_bytes", 0), p.get("out_size_bytes", 0)
            sz     = f" | {_fmt_size(src_sz)} → {_fmt_size(out_sz)}" if src_sz and out_sz else ""
            prefix = f"{idx}/{tot} — " if tot > 1 else ""
            return [
                f"[✓] {prefix}Salvo: {name} ({elapsed}){sz}",
                f"[i] Pasta: {_relative_output_dir(path)}",
            ]
        case "video_op_error":
            return [f"[!] Erro em '{p.get('item_name', '')}': {p.get('message', '')}"]
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
        case "progress_start":  return "Iniciando..."
        case "queue_progress":
            cur, tot = p.get("current_item", "?"), p.get("total_items", "?")
            name = p.get("item_name", "")
            return f"Item {cur}/{tot}" + (f" — {name}" if name else "")
        case "video_op_start":  return OP_LABELS.get(p.get("operation", ""), "Processando...")
        case "video_op_done":
            idx, tot = p.get("item_idx", 1), p.get("total", 1)
            return f"Item {idx}/{tot} concluído." if tot > 1 else "Concluído."
        case "video_op_error":  return "Erro — continuando fila..."
        case "task_done":       return "Pipeline concluído!"
        case "task_error":      return "Erro no pipeline."
        case _:                 return None
```

---

### 5. `VideoArgs` e `form_view.py` — CRIAR

**`VideoArgs`:**

```python
@dataclass
class VideoArgs:
    items: list[InputItem] = field(default_factory=list)
    operation: str = "download"      # download|convert|trim|compress|resize|extract_audio|thumbnail

    # Download
    resolution: str = "1080"         # "best"|"2160"|"1080"|"720"|"480"|"360"
    container: str = "mp4"           # "mp4"|"mkv"|"webm"
    embed_meta: bool = True

    # Convert
    vcodec: str = "copy"             # "copy"|"h264"|"h265"|"vp9"
    out_container: str = "mp4"

    # Trim
    trim_start: str = ""             # "HH:MM:SS" ou ""
    trim_end: str = ""
    trim_reenc: bool = False

    # Compress
    crf: int = 23                    # 18–28
    preset: str = "medium"           # ultrafast|fast|medium|slow

    # Resize
    resize_width: int = 0
    resize_height: int = 0

    # Thumbnail
    thumb_time: str = "00:00:01"
    thumb_fmt: str = "jpg"

    # Extract audio
    audio_fmt: str = "mp3"
```

**Estrutura visual do formulário** (DS: `section()`, `segmented_selector()`, `labeled_field()`, `switch_row()`, `hairline()`, `help_icon_for()`):

```
┌─────────────────────────────────────────┐
│  Entrada          [URL + FilePicker]    ⓘ│
│  ─────────────────────────────────────── │
│  Operação                               ⓘ│
│  [Download] [Converter] [Recortar]        │
│  [Comprimir] [Redimensionar]              │
│  [Extrair áudio] [Thumbnail]              │
│  ─────────────────────────────────────── │
│  ← bloco condicional por operação →       │
│  ─────────────────────────────────────── │
│                             [Iniciar →]   │
└─────────────────────────────────────────┘
```

**Blocos condicionais** — cada bloco é um `ft.Container(visible=..., animate_opacity=...)`:

| Operação        | Controles visíveis                                                                                         |
| --------------- | ---------------------------------------------------------------------------------------------------------- |
| `download`      | `segmented_selector` resolução (best/2160/1080/720/480/360) + container (MP4/MKV/WebM) + switch embed_meta |
| `convert`       | `segmented_selector` codec (copy/H.264/H.265/VP9) + container                                              |
| `trim`          | dois `ft.TextField` (Início / Fim) + `switch_row` "Corte frame-preciso"                                    |
| `compress`      | `slider_row` CRF (18–28) + `segmented_selector` preset                                                     |
| `resize`        | dois `ft.TextField` (Largura / Altura) — helper "deixe 0 para preservar"                                   |
| `extract_audio` | `segmented_selector` formato áudio (mp3/m4a/wav)                                                           |
| `thumbnail`     | `ft.TextField` tempo + `segmented_selector` formato (jpg/png)                                              |

**Observação de UX importante (Flet 0.85):** blocos condicionais devem usar `toggle visible` dentro de `ft.Stack` ou `ft.Column`. Nunca reatribuir `content` em runtime — usar `visible=`. Animar com `animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN)`.

---

### 6. `worker.py` — CRIAR

Segue exatamente o padrão de `modules/audio/worker.py`. Pontos-chave:

```python
_MODULE_ID = "video"

def emit(type, stage="video", payload=None):
    bus.emit(type, stage, payload or {}, module_id=_MODULE_ID)

# Para cada item:
emit("video_op_start", payload={
    "operation": args.operation,
    "item_name": item_name,
    "item_idx": idx,
    "total": total,
})

# Log de metadados antes da operação:
info = get_video_info(src)
emit("log", payload={"message": pipeline_log.fmt_video_info(info)})
emit("log", payload={"message": pipeline_log.fmt_XXX_detail(...)})

# Dispatch por operação (match/case):
match args.operation:
    case "download":  out_path = download_video(...)
    case "convert":   out_path = convert_video(...)
    case "trim":      out_path = trim_video(...)
    case "compress":  out_path = compress_video(...)
    case "resize":    out_path = resize_video(...)
    case "extract_audio": out_path = extract_audio_from_video(...)
    case "thumbnail": out_path = make_thumbnail(...)

emit("video_op_done", payload={
    "output_path": str(out_path),
    "elapsed": f"{elapsed:.1f}s",
    "item_idx": idx,
    "total": total,
    "src_size_bytes": src.stat().st_size if src.exists() else 0,
    "out_size_bytes": out_path.stat().st_size,
})
```

**Bridge `extract_audio` → Transcrição e Áudio:**

```python
# Em view.py, no _render_video_results():
if p.suffix in {".mp3", ".wav", ".m4a", ".flac"}:
    extra.append(action_button("Transcrever", ..., on_click=lambda _: nav[0]("transcription", {"file": str(p)})))
    extra.append(action_button("Processar no Áudio", ..., on_click=lambda _: nav[0]("audio", {"file": str(p)})))
```

---

### 7. `view.py` — substituir placeholder

Mesmo padrão de `modules/audio/view.py`:

```python
def build_video_module(page, bus, cancel_event, pipeline_running, nav) -> Module:
    ...
    return Module(
        id="video",
        label="Vídeo",
        icon=ft.Icons.VIDEO_FILE_OUTLINED,
        selected_icon=ft.Icons.VIDEO_FILE,
        control=control,
        on_mount=_on_mount,   # suporte ao bridge Áudio → Vídeo futuramente
    )
```

---

### 8. `app.py` — registrar módulo

O módulo Vídeo deve aparecer entre Áudio e Imagens na `NavigationRail` (conforme CLAUDE.md: Áudio → Vídeo → Imagens → Transcrição):

```python
# Em MODULES (app.py), substituir o placeholder existente:
from src.gui.modules.video.view import build_video_module

# Na lista MODULES, posição 2 (entre Áudio e Imagens):
build_video_module(page, bus, cancel_event, pipeline_running, nav)
```

---

### 9. `help_content.py` — novas chaves

```python
# HELP_SHORT:
"video.input":       "URL ou arquivo local. URL → download. Arquivo → operação selecionada.",
"video.operation":   "O que fazer com o vídeo. 'Converter' sem reencoding usa -c copy (rápido).",
"video.resolution":  "Resolução máxima do download. Resoluções maiores = arquivo maior.",
"video.codec":       "'copy' preserva codec original sem reencoding (rápido, sem perda). H.264 é o mais compatível.",
"video.trim":        "Recorta um trecho. 'Corte rápido' usa -c copy (impreciso no keyframe). 'Frame-preciso' reencoda.",
"video.crf":         "Fator de qualidade do H.264. 18 = alta qualidade. 23 = padrão. 28 = arquivo menor.",
"video.preset":      "Velocidade de encoding H.264. 'medium' é o equilíbrio. 'slow' = arquivo menor, espera mais.",
"video.resize":      "Redimensiona mantendo aspect ratio. Deixe largura ou altura em 0 para calcular automaticamente.",

# HELP_LONG:
"video.codec": (
    "Codec de Vídeo",
    "'copy' é o modo mais rápido: o ffmpeg apenas remonta o container sem reprocessar o vídeo. "
    "H.264 (libx264) é o codec mais compatível para reprodução em qualquer dispositivo. "
    "H.265 (libx265) gera arquivos ~50% menores que H.264 com a mesma qualidade, mas o encoding é ~3× mais lento. "
    "VP9 é ideal para WebM/web, com boa compressão e formato aberto.",
),
"video.crf": (
    "CRF — Constant Rate Factor",
    "Controla a qualidade do encoding H.264. Valores menores = melhor qualidade = arquivo maior. "
    "18: praticamente imperceptível vs original. 23: padrão do ffmpeg, boa qualidade. "
    "28: compressão visível, arquivo pequeno. Para arquivamento use 18–20; para compartilhamento use 23–26.",
),
```

---

### 10. Checklist de implementação

**Fase 1 — Core (sem GUI)**
- [ ] Criar `src/core/video/__init__.py`
- [ ] Criar `src/core/video/info.py` + testar `get_video_info()` com um MP4 local
- [ ] Criar `src/core/video/downloader.py` + testar download 720p de URL
- [ ] Criar `src/core/video/converter.py` + testar cada função individualmente
- [ ] Verificar que `extract_audio_from_video` reutiliza `src/core/audio/converter.py` sem duplicação

**Fase 2 — Pipeline log**
- [ ] Criar `src/gui/modules/video/pipeline_log.py`
- [ ] Todos `OP_VERBS`/`OP_LABELS` para 7 operações
- [ ] Todos `fmt_*` builders + `resolve_messages()` + `resolve_stage_label()`

**Fase 3 — Worker**
- [ ] Criar `src/gui/modules/video/worker.py` com `run_video_pipeline()` e `start_video_pipeline()`
- [ ] Dispatch `match args.operation` para todas as 7 operações
- [ ] `progress_cb` → `emit("progress_update")` em convert/trim/compress/resize
- [ ] Log de metadados antes de cada operação via `fmt_video_info()`
- [ ] Verificar reset de `pipeline_running[0]` em `finally`

**Fase 4 — Formulário**
- [ ] Criar `VideoArgs` com todos os campos
- [ ] `build_video_form()` com `segmented_selector` de operação (7 opções, 3 colunas)
- [ ] 7 blocos condicionais com `visible=` + `animate_opacity`
- [ ] Controles de `download`: resolução + container + embed_meta
- [ ] Controles de `trim`: dois `TextField` + switch reenc + validação de formato `HH:MM:SS`
- [ ] Controles de `compress`: slider CRF (18–28) + segmented preset
- [ ] Restantes (convert, resize, extract_audio, thumbnail)
- [ ] `_set_running()` desabilita todos os controles
- [ ] Persistência via `settings.load()`/`settings.save()`

**Fase 5 — View e registro**
- [ ] Substituir placeholder em `src/gui/modules/video/view.py`
- [ ] Bridge: `extract_audio` result → botões Transcrever + Processar no Áudio
- [ ] Registrar módulo em `app.py` (posição 2: entre Áudio e Imagens)
- [ ] Chaves `help_content.py`

**Fase 6 — Testes manuais**
- [ ] Download URL 1080p → MP4
- [ ] Download URL 720p → MKV
- [ ] Convert local → H.264
- [ ] Trim 00:00:10 → 00:00:30 (copy + reenc)
- [ ] Compress CRF 26 → verificar redução de tamanho no log
- [ ] Resize 1280×0 (calcula altura)
- [ ] Extract audio → bridge para Transcrição
- [ ] Thumbnail frame 00:00:05
- [ ] Cancelar durante download
- [ ] Cancelar durante compress (processo ffmpeg termina limpo)
- [ ] Fila com 2 itens locais → ambos processados sequencialmente
