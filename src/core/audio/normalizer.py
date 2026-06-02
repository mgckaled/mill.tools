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

    # Passe 1: medição
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

    # Passe 2: aplicação
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
                ratio = min(
                    int(line.strip().split("=", 1)[1]) / 1_000_000 / total_secs, 1.0
                )
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
    end = next((i for i, ln in enumerate(lines[start:], start) if ln.strip() == "}"), None)
    if end is None:
        return None
    try:
        return json.loads("\n".join(lines[start : end + 1]))
    except json.JSONDecodeError:
        return None
