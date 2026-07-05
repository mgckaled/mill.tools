"""Normalização de loudness via ffmpeg loudnorm (EBU R128 / ITU-R BS.1770-4)."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Callable

from src.core.audio.info import get_duration_ffprobe, get_sample_rate_ffprobe
from src.utils import sanitize_filename

logger = logging.getLogger(__name__)

_TARGET_TP = -1.0  # True Peak máximo (dBFS)
_TARGET_LRA = 11.0  # Loudness Range alvo
_MEASURE_TIMEOUT_S = 1800  # 30 min — generoso o bastante p/ não policiar lentidão


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
    out_path = out_dir / f"{sanitize_filename(src.stem)}_normalized{src.suffix}"

    # Passe 1: medição
    measure_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        (
            f"loudnorm=I={target_lufs}:TP={_TARGET_TP}"
            f":LRA={_TARGET_LRA}:print_format=json"
        ),
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(measure_cmd, capture_output=True, timeout=_MEASURE_TIMEOUT_S)
    stats = (
        _parse_loudnorm_json(r.stderr.decode("utf-8", errors="replace"))
        if r.returncode == 0
        else None
    )

    # Passe 2: aplicação
    source_sample_rate: int | None = None
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
        reason = (
            f"measurement pass exited with code {r.returncode}"
            if r.returncode != 0
            else "measurement pass produced no parsable loudnorm stats"
        )
        logger.warning(
            "%s for %s — falling back to dynamic loudnorm mode, which upsamples "
            "the output to 192 kHz (per ffmpeg docs); forcing source sample rate "
            "to limit the side effect",
            reason,
            src,
        )
        af = f"loudnorm=I={target_lufs}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"
        source_sample_rate = get_sample_rate_ffprobe(src)

    apply_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        af,
    ]
    if source_sample_rate:
        apply_cmd += ["-ar", str(source_sample_rate)]
    apply_cmd += [
        "-progress",
        "pipe:1",
        "-nostats",
        str(out_path),
    ]

    total_secs = get_duration_ffprobe(src) if progress_cb else None
    proc = subprocess.Popen(apply_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stderr_lines: list[str] = []

    def _drain() -> None:
        for raw in proc.stderr:
            stderr_lines.append(raw.decode("utf-8", errors="replace").rstrip())

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
        raise RuntimeError(f"ffmpeg loudnorm retornou {proc.returncode}: {tail}")

    if not out_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado após loudnorm: {out_path}")

    return out_path, stats


def _parse_loudnorm_json(stderr: str) -> dict | None:
    """Extrai o bloco JSON de estatísticas loudnorm do stderr do ffmpeg."""
    lines = stderr.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() == "{"), None)
    if start is None:
        return None
    end = next(
        (i for i, ln in enumerate(lines[start:], start) if ln.strip() == "}"), None
    )
    if end is None:
        return None
    try:
        return json.loads("\n".join(lines[start : end + 1]))
    except json.JSONDecodeError:
        return None
