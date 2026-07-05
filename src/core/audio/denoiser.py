"""Spectral noise reduction via noisereduce (spectral gating, CPU-only)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

_DECODE_TIMEOUT_S = 1800  # 30 min — generous enough to not police slowness


def is_available() -> bool:
    """True if noisereduce and soundfile are installed."""
    try:
        import noisereduce  # noqa: F401
        import soundfile  # noqa: F401

        return True
    except ImportError:
        return False


def denoise(src: Path, out_dir: Path, stationary: bool = True) -> Path:
    """Attenuate steady background noise via spectral gating.

    Decodes any format to a temporary WAV via ffmpeg, processes it with
    noisereduce and writes the result as WAV.

    Args:
        src: Audio file (any ffmpeg-supported format).
        out_dir: Output directory.
        stationary: True = constant noise (fan, hum). False = adaptive.

    Returns:
        Path of the denoised file (.wav).
    """
    import numpy as np
    import noisereduce as nr
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)

    # Decode to a temporary PCM WAV (handles MP3/M4A/any fmt). Unique name
    # (mkstemp) avoids collisions between concurrent runs on the same stem.
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
        # float32 halves sf.read's peak RAM vs. the float64 default — matters
        # for long audio (2h stereo ≈ 5GB at float64).
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
        # Preserves the original subtype (PCM_16, PCM_24…) to avoid degrading bit depth
        sf.write(str(out_path), denoised, sr, subtype=meta.subtype)
    finally:
        tmp_wav.unlink(missing_ok=True)

    return out_path
