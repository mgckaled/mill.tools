"""Smoke test de integração — pipeline completo: denoise → normalize."""

import pytest

pytestmark = pytest.mark.integration


def test_full_audio_pipeline_denoise_then_normalize(sample_wav, tmp_path):
    """Smoke test: denoise → normalize encadeados devem produzir arquivo final."""
    from src.core.audio.denoiser import denoise
    from src.core.audio.normalizer import normalize_lufs

    denoised_out = denoise(sample_wav, tmp_path / "denoised")
    final, _ = normalize_lufs(denoised_out, tmp_path / "normalized", target_lufs=-14.0)

    assert final.exists()
    assert final.stat().st_size > 500
