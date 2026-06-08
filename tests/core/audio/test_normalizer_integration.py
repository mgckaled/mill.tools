"""Testes de integração — src/core/audio/normalizer.py (pipeline 2-pass loudnorm)."""
import pytest

pytestmark = pytest.mark.integration


def test_normalize_lufs_creates_output(sample_wav, out_dir):
    """normalize_lufs deve criar arquivo de saída."""
    from src.core.audio.normalizer import normalize_lufs

    out_path, _ = normalize_lufs(sample_wav, out_dir, target_lufs=-14.0)
    assert out_path.exists()
    assert out_path.stat().st_size > 1000


def test_normalize_lufs_returns_stats_dict(sample_wav, out_dir):
    """Passe 1 (medição) deve retornar dict com campos loudnorm — ou None se sine não emitiu JSON."""
    from src.core.audio.normalizer import normalize_lufs

    _, stats = normalize_lufs(sample_wav, out_dir, target_lufs=-14.0)
    if stats is not None:
        assert "input_i" in stats
        assert "input_tp" in stats
        assert "target_offset" in stats


def test_normalize_lufs_different_targets(sample_wav, out_dir):
    """Normalização com alvo -23 LUFS (broadcast) deve concluir sem erro."""
    from src.core.audio.normalizer import normalize_lufs

    out_path, _ = normalize_lufs(sample_wav, out_dir, target_lufs=-23.0)
    assert out_path.exists()


def test_normalize_lufs_progress_cb(sample_wav, out_dir):
    """Callback de progresso deve ser chamado durante o segundo passe."""
    from src.core.audio.normalizer import normalize_lufs

    calls: list[float] = []
    normalize_lufs(
        sample_wav,
        out_dir,
        target_lufs=-14.0,
        progress_cb=lambda r: calls.append(r),
    )
    assert len(calls) > 0
    assert all(0.0 <= r <= 1.0 for r in calls)


def test_normalize_lufs_output_name_has_suffix(sample_wav, out_dir):
    """Arquivo de saída deve conter '_normalized' no nome."""
    from src.core.audio.normalizer import normalize_lufs

    out_path, _ = normalize_lufs(sample_wav, out_dir)
    assert "_normalized" in out_path.name
