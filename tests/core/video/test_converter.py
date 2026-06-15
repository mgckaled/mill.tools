"""Testes de integração — src/core/video/converter.py."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _write_srt(path: Path) -> Path:
    """Write a minimal 2-cue SubRip file at path and return it."""
    path.write_text(
        "1\n00:00:00,000 --> 00:00:01,500\nHello world\n\n"
        "2\n00:00:01,500 --> 00:00:03,000\nSecond line\n",
        encoding="utf-8",
    )
    return path


def test_convert_video_copy_keeps_container(sample_mp4, out_dir):
    """vcodec='copy' deve produzir MP4 sem reencoding."""
    from src.core.video.converter import convert_video

    out = convert_video(sample_mp4, out_dir, container="mp4", vcodec="copy")
    assert out.exists()
    assert out.suffix.lower() == ".mp4"
    assert out.stat().st_size > 1000


def test_convert_video_container_change_to_mkv(sample_mp4, out_dir):
    """Trocar apenas o container deve produzir arquivo .mkv."""
    from src.core.video.converter import convert_video

    out = convert_video(sample_mp4, out_dir, container="mkv", vcodec="copy")
    assert out.exists()
    assert out.suffix.lower() == ".mkv"


def test_trim_video_copy_mode(sample_mp4, out_dir):
    """Recorte com -c copy deve produzir arquivo menor que o original."""
    from src.core.video.converter import trim_video

    out = trim_video(sample_mp4, out_dir, start="0:00", end="0:01", reenc=False)
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.stat().st_size < sample_mp4.stat().st_size


def test_trim_video_reenc_mode(sample_mp4, out_dir):
    """Recorte com reenc=True (libx264) deve produzir vídeo válido."""
    from src.core.video.converter import trim_video

    out = trim_video(sample_mp4, out_dir, start="0:00", end="0:01", reenc=True)
    assert out.exists()
    assert out.stat().st_size > 0


def test_compress_video_produces_mp4(sample_mp4, out_dir):
    """Compressão H.264/CRF deve gerar MP4 (a comparação de tamanho não é confiável em vídeos curtos)."""
    from src.core.video.converter import compress_video

    out = compress_video(sample_mp4, out_dir, crf=28, preset="ultrafast")
    assert out.exists()
    assert out.suffix.lower() == ".mp4"
    assert out.stat().st_size > 0


def test_resize_video_changes_dimensions(sample_mp4, out_dir):
    """Resize deve alterar largura do vídeo (verificada via ffprobe)."""
    from src.core.video.converter import resize_video
    from src.core.video.info import get_video_info

    out = resize_video(sample_mp4, out_dir, width=160, height=0)
    assert out.exists()
    info = get_video_info(out)
    assert info.width == 160
    # Aspect ratio preservado: altura cai proporcionalmente
    assert info.height is not None and info.height < 240


def test_extract_audio_from_video_produces_mp3(sample_mp4, out_dir):
    """Bridge para core/audio/converter — deve gerar MP3."""
    from src.core.video.converter import extract_audio_from_video

    out = extract_audio_from_video(sample_mp4, out_dir, audio_fmt="mp3")
    assert out.exists()
    assert out.suffix.lower() == ".mp3"
    assert out.stat().st_size > 500


def test_make_thumbnail_default_jpg(sample_mp4, out_dir):
    """Thumbnail no tempo default (00:00:01) deve gerar JPG válido."""
    from src.core.video.converter import make_thumbnail

    out = make_thumbnail(sample_mp4, out_dir, time="00:00:01", fmt="jpg")
    assert out.exists()
    assert out.suffix.lower() == ".jpg"
    assert out.stat().st_size > 0


def test_make_thumbnail_png_format(sample_mp4, out_dir):
    """fmt='png' deve gerar arquivo .png."""
    from src.core.video.converter import make_thumbnail

    out = make_thumbnail(sample_mp4, out_dir, time="00:00:00", fmt="png")
    assert out.exists()
    assert out.suffix.lower() == ".png"


def test_make_thumbnail_nonexistent_source_raises(out_dir):
    """Arquivo inexistente deve lançar RuntimeError."""
    from src.core.video.converter import make_thumbnail

    fake = Path("nonexistent_movie.mp4")
    with pytest.raises(RuntimeError, match="Thumbnail"):
        make_thumbnail(fake, out_dir)


def test_convert_video_invalid_codec_falls_back_to_copy(sample_mp4, out_dir):
    """vcodec desconhecido cai no fallback ['-c:v', 'copy'] e gera arquivo válido."""
    from src.core.video.converter import convert_video

    out = convert_video(
        sample_mp4, out_dir, container="mp4", vcodec="unknown_codec_xyz"
    )
    assert out.exists()
    assert out.suffix.lower() == ".mp4"


def test_convert_video_calls_progress_cb(sample_mp4, out_dir):
    """progress_cb deve ser chamado durante a conversão (ratios em [0,1])."""
    from src.core.video.converter import convert_video

    calls: list[float] = []
    out = convert_video(
        sample_mp4,
        out_dir,
        container="mp4",
        vcodec="copy",
        progress_cb=lambda r: calls.append(r),
    )
    assert out.exists()
    assert len(calls) > 0
    assert all(0.0 <= r <= 1.0 for r in calls)


def test_add_subtitles_soft_mux(sample_mp4, out_dir, tmp_path):
    """Soft mux (-c copy + mov_text) deve embutir a legenda sem reencodar."""
    from src.core.video.converter import add_subtitles

    srt = _write_srt(tmp_path / "subs.srt")
    out = add_subtitles(sample_mp4, srt, out_dir, mode="soft")
    assert out.exists()
    assert out.suffix.lower() == ".mp4"
    assert out.stat().st_size > 1000
    assert out.name.endswith("_subbed.mp4")


def test_add_subtitles_hard_burn(sample_mp4, out_dir, tmp_path):
    """Hard burn-in (filtro subtitles + libx264) deve gerar vídeo válido.

    Valida também o caminho cwd+basename do filtro subtitles no Windows.
    """
    from src.core.video.converter import add_subtitles

    srt = _write_srt(tmp_path / "subs.srt")
    out = add_subtitles(sample_mp4, srt, out_dir, mode="hard")
    assert out.exists()
    assert out.suffix.lower() == ".mp4"
    assert out.stat().st_size > 1000


def test_add_subtitles_hard_calls_progress_cb(sample_mp4, out_dir, tmp_path):
    """Burn-in reencoda → progress_cb recebe ratios em [0,1]."""
    from src.core.video.converter import add_subtitles

    srt = _write_srt(tmp_path / "subs.srt")
    calls: list[float] = []
    out = add_subtitles(
        sample_mp4,
        srt,
        out_dir,
        mode="hard",
        progress_cb=lambda r: calls.append(r),
    )
    assert out.exists()
    assert len(calls) > 0
    assert all(0.0 <= r <= 1.0 for r in calls)
