"""Testes de integração — src/core/audio/denoiser.py."""
import pytest

pytestmark = pytest.mark.integration


def test_denoise_creates_output(sample_wav, out_dir):
    """denoise deve criar arquivo WAV de saída."""
    from src.core.audio.denoiser import denoise

    out = denoise(sample_wav, out_dir)
    assert out.exists()
    assert out.suffix.lower() == ".wav"


def test_denoise_output_not_empty(sample_wav, out_dir):
    """Arquivo denoised não deve ser vazio."""
    from src.core.audio.denoiser import denoise

    out = denoise(sample_wav, out_dir)
    assert out.stat().st_size > 1000


def test_denoise_preserves_sample_rate(sample_wav, out_dir):
    """Taxa de amostragem deve ser preservada após denoise."""
    import soundfile as sf

    from src.core.audio.denoiser import denoise

    _, original_sr = sf.read(str(sample_wav))
    out = denoise(sample_wav, out_dir)
    _, denoised_sr = sf.read(str(out))
    assert original_sr == denoised_sr


def test_denoise_output_name_has_suffix(sample_wav, out_dir):
    """Arquivo de saída deve conter '_denoised' no nome."""
    from src.core.audio.denoiser import denoise

    out = denoise(sample_wav, out_dir)
    assert "_denoised" in out.name


def test_denoise_stereo_creates_output(sample_wav_stereo, out_dir):
    """Branch estéreo (audio.ndim == 2): cada canal é processado separadamente."""
    from src.core.audio.denoiser import denoise

    out = denoise(sample_wav_stereo, out_dir)
    assert out.exists()
    assert out.suffix.lower() == ".wav"
    assert out.stat().st_size > 1000


def test_denoise_stereo_preserves_channels(sample_wav_stereo, out_dir):
    """Arquivo denoised estéreo deve preservar o número de canais."""
    import soundfile as sf

    from src.core.audio.denoiser import denoise

    out = denoise(sample_wav_stereo, out_dir)
    assert sf.info(str(out)).channels == sf.info(str(sample_wav_stereo)).channels
