"""Redução de ruído espectral via noisereduce (spectral gating, CPU-only)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

_DECODE_TIMEOUT_S = 1800  # 30 min — generoso o bastante p/ não policiar lentidão


def is_available() -> bool:
    """True se noisereduce e soundfile estiverem instalados."""
    try:
        import noisereduce  # noqa: F401
        import soundfile  # noqa: F401

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

    # Decodifica para WAV PCM temporário (lida com MP3/M4A/qualquer fmt). Nome
    # único (mkstemp) evita colisão entre execuções concorrentes no mesmo stem.
    fd, tmp_wav_str = tempfile.mkstemp(
        suffix=".wav", prefix=f".tmp_denoise_{src.stem}_", dir=out_dir
    )
    os.close(fd)
    tmp_wav = Path(tmp_wav_str)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), str(tmp_wav)],
        check=True,
        capture_output=True,
        timeout=_DECODE_TIMEOUT_S,
    )

    try:
        meta = sf.info(str(tmp_wav))
        # float32 corta pela metade o pico de RAM de sf.read frente ao default
        # float64 — relevante p/ áudio longo (2h estéreo ≈ 5GB em float64).
        audio, sr = sf.read(str(tmp_wav), dtype="float32")

        if audio.ndim == 2:
            channels = [
                nr.reduce_noise(y=audio[:, c], sr=sr, stationary=stationary)
                for c in range(audio.shape[1])
            ]
            denoised = np.stack(channels, axis=1)
        else:
            denoised = nr.reduce_noise(y=audio, sr=sr, stationary=stationary)

        out_path = out_dir / f"{src.stem}_denoised.wav"
        # Preserva o subtype original (PCM_16, PCM_24…) para não degradar bit depth
        sf.write(str(out_path), denoised, sr, subtype=meta.subtype)
    finally:
        tmp_wav.unlink(missing_ok=True)

    return out_path
