# Plano de Implementação — Parte 2: Testes de Integração

> **Pré-requisito:** Parte 1 concluída (pyproject.toml configurado, conftest.py criado, dependências instaladas).
> **Escopo:** módulos que chamam subprocessos reais (ffmpeg, ffprobe) e operações de I/O com arquivos de mídia.
> Estes testes são marcados com `@pytest.mark.integration` e pulados em CIs sem ffmpeg.

---

## 1. Dependências adicionais

Nenhuma dependência nova de código. Porém os seguintes binários devem estar no PATH do ambiente de teste:

- `ffmpeg` (verificar com `ffmpeg -version`)
- `ffprobe` (parte do pacote ffmpeg)

Para confirmar num script de CI:

```bash
ffmpeg -version | head -1
ffprobe -version | head -1
```

---

## 2. Fixtures de arquivos de mídia

### 2.1 Geração programática dos fixtures (sem arquivos binários no git)

Os arquivos de fixture são **gerados via ffmpeg/Pillow** no momento da sessão de teste. Assim o repositório não guarda binários — apenas código.

Adicionar ao `tests/conftest.py` (complementando o que já existe da Parte 1):

```python
import subprocess
from pathlib import Path

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Fixtures de áudio — geradas via ffmpeg (sine wave)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """WAV mono 44100Hz 3 segundos — gerado via ffmpeg com sine wave 440Hz."""
    out = tmp_path_factory.mktemp("fixtures") / "sample.wav"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-ar", "44100", "-ac", "1",
        str(out),
    ], check=True, capture_output=True)
    return out


@pytest.fixture(scope="session")
def sample_mp3(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """MP3 mono 128kbps 3 segundos — gerado via ffmpeg com sine wave."""
    out = tmp_path_factory.mktemp("fixtures") / "sample.mp3"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-ar", "44100", "-ac", "1",
        "-ab", "128k",
        str(out),
    ], check=True, capture_output=True)
    return out


@pytest.fixture(scope="session")
def sample_mp4(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """MP4 com vídeo colorido 3s e áudio sine 440Hz — mínimo viável para testes de vídeo."""
    out = tmp_path_factory.mktemp("fixtures") / "sample.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-t", "3",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "51",
        "-c:a", "aac", "-b:a", "64k",
        str(out),
    ], check=True, capture_output=True)
    return out


# ---------------------------------------------------------------------------
# Fixtures de imagem — geradas via Pillow (reutilizadas da Parte 1 em scope="session")
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def session_jpg(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """JPEG RGB 640×480 reutilizável em escopo de sessão (mais eficiente)."""
    out = tmp_path_factory.mktemp("fixtures") / "session_sample.jpg"
    img = Image.new("RGB", (640, 480), color=(80, 120, 200))
    img.save(out, format="JPEG", quality=85)
    return out
```

> **Por que `scope="session"`?** Os fixtures de geração de arquivos são caros (ffmpeg, I/O). Com escopo de sessão, são criados uma vez e reaproveitados por todos os testes da sessão. Para testes que modificam o arquivo de entrada, use `tmp_path` local para copiar antes de operar.

---

## 3. Marcador e skip automático

Adicionar ao `tests/conftest.py`:

```python
def pytest_collection_modifyitems(config, items):
    """Pula automaticamente testes de integração se ffmpeg não estiver no PATH."""
    import shutil
    if shutil.which("ffmpeg") is None:
        skip_no_ffmpeg = pytest.mark.skip(reason="ffmpeg não encontrado no PATH")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip_no_ffmpeg)
```

---

## 4. `tests/core/audio/test_converter.py`

```python
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_convert_audio_wav_to_mp3(sample_wav, out_dir):
    """Conversão WAV → MP3 deve produzir arquivo de saída válido."""
    from src.core.audio.converter import convert_audio
    out = convert_audio(sample_wav, out_dir, fmt="mp3", bitrate="128k")
    assert out.exists()
    assert out.suffix.lower() == ".mp3"
    assert out.stat().st_size > 1000  # arquivo não vazio


def test_convert_audio_wav_to_ogg(sample_wav, out_dir):
    from src.core.audio.converter import convert_audio
    out = convert_audio(sample_wav, out_dir, fmt="ogg")
    assert out.exists()
    assert out.suffix.lower() == ".ogg"


def test_convert_audio_calls_progress_cb(sample_wav, out_dir):
    """progress_cb deve ser chamado ao menos uma vez durante conversão."""
    from src.core.audio.converter import convert_audio
    calls = []
    out = convert_audio(
        sample_wav, out_dir, fmt="mp3", bitrate="128k",
        progress_cb=lambda ratio: calls.append(ratio),
    )
    assert out.exists()
    assert len(calls) > 0
    # Ratio deve estar entre 0 e 1
    assert all(0.0 <= r <= 1.0 for r in calls)


def test_extract_audio_from_mp4(sample_mp4, out_dir):
    """Extração de áudio de MP4 deve produzir MP3 válido."""
    from src.core.audio.converter import extract_audio
    out = extract_audio(sample_mp4, out_dir, fmt="mp3")
    assert out.exists()
    assert out.suffix.lower() == ".mp3"
    assert out.stat().st_size > 500


def test_convert_audio_invalid_format_raises(sample_wav, out_dir):
    """Formato desconhecido deve lançar RuntimeError (ffmpeg retorna erro)."""
    from src.core.audio.converter import convert_audio
    with pytest.raises(RuntimeError):
        convert_audio(sample_wav, out_dir, fmt="xyz_invalid_format")


def test_convert_audio_nonexistent_file_raises(out_dir):
    """Arquivo de entrada inexistente deve lançar RuntimeError."""
    from src.core.audio.converter import convert_audio
    fake = Path("/nonexistent/path/audio.wav")
    with pytest.raises((RuntimeError, FileNotFoundError)):
        convert_audio(fake, out_dir, fmt="mp3")
```

---

## 5. `tests/core/audio/test_normalizer_integration.py`

> Nota: este arquivo cobre o pipeline completo de `normalize_lufs`. Os testes do **parser** (`_parse_loudnorm_json`) estão na Parte 1, sem dependência de ffmpeg.

```python
import pytest

pytestmark = pytest.mark.integration


def test_normalize_lufs_creates_output(sample_wav, out_dir):
    """normalize_lufs deve criar arquivo de saída."""
    from src.core.audio.normalizer import normalize_lufs
    out_path, stats = normalize_lufs(sample_wav, out_dir, target_lufs=-14.0)
    assert out_path.exists()
    assert out_path.stat().st_size > 1000


def test_normalize_lufs_returns_stats_dict(sample_wav, out_dir):
    """Passe 1 (medição) deve retornar dict com campos loudnorm."""
    from src.core.audio.normalizer import normalize_lufs
    _, stats = normalize_lufs(sample_wav, out_dir, target_lufs=-14.0)
    # stats pode ser None se ffmpeg não emitiu JSON (sine wave pode não ter loudnorm adequado)
    # mas se não for None, deve ter as chaves esperadas
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
    calls = []
    normalize_lufs(
        sample_wav, out_dir, target_lufs=-14.0,
        progress_cb=lambda r: calls.append(r),
    )
    assert len(calls) > 0
    assert all(0.0 <= r <= 1.0 for r in calls)


def test_normalize_lufs_output_name_has_suffix(sample_wav, out_dir):
    """Arquivo de saída deve conter '_normalized' no nome."""
    from src.core.audio.normalizer import normalize_lufs
    out_path, _ = normalize_lufs(sample_wav, out_dir)
    assert "_normalized" in out_path.name
```

---

## 6. `tests/core/audio/test_denoiser.py`

```python
import pytest

pytestmark = pytest.mark.integration


def test_denoise_creates_output(sample_wav, out_dir):
    """denoise deve criar arquivo WAV de saída."""
    from src.core.audio.denoiser import denoise
    out = denoise(sample_wav, out_dir)
    assert out.exists()
    assert out.suffix.lower() == ".wav"


def test_denoise_output_not_empty(sample_wav, out_dir):
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
    from src.core.audio.denoiser import denoise
    out = denoise(sample_wav, out_dir)
    assert "_denoised" in out.name
```

---

## 7. `tests/core/audio/test_info.py`

```python
import pytest

pytestmark = pytest.mark.integration


def test_get_duration_ffprobe_wav(sample_wav):
    """ffprobe deve retornar duração próxima de 3.0s para o fixture WAV."""
    from src.core.audio.info import get_duration_ffprobe
    duration = get_duration_ffprobe(sample_wav)
    assert duration is not None
    assert 2.5 <= duration <= 3.5


def test_get_duration_ffprobe_mp3(sample_mp3):
    from src.core.audio.info import get_duration_ffprobe
    duration = get_duration_ffprobe(sample_mp3)
    assert duration is not None
    assert 2.5 <= duration <= 3.5


def test_get_duration_ffprobe_mp4(sample_mp4):
    from src.core.audio.info import get_duration_ffprobe
    duration = get_duration_ffprobe(sample_mp4)
    assert duration is not None
    assert 2.5 <= duration <= 3.5


def test_get_duration_ffprobe_nonexistent_returns_none():
    """Arquivo inexistente não deve lançar exceção — retorna None."""
    from pathlib import Path
    from src.core.audio.info import get_duration_ffprobe
    result = get_duration_ffprobe(Path("/nonexistent/file.wav"))
    assert result is None
```

---

## 8. `tests/core/image/test_converter.py`

```python
import pytest
from PIL import Image

pytestmark = pytest.mark.integration


def test_convert_jpg_to_png(session_jpg, out_dir):
    """Conversão JPEG → PNG deve produzir arquivo PNG válido."""
    from src.core.image.converter import convert_image
    out = convert_image(session_jpg, out_dir, out_fmt="png", quality=85)
    assert out.exists()
    assert out.suffix.lower() == ".png"
    with Image.open(out) as im:
        assert im.format == "PNG"


def test_convert_jpg_to_webp(session_jpg, out_dir):
    from src.core.image.converter import convert_image
    out = convert_image(session_jpg, out_dir, out_fmt="webp", quality=80)
    assert out.exists()
    assert out.suffix.lower() == ".webp"


def test_convert_preserves_dimensions(session_jpg, out_dir):
    """Conversão de formato não deve alterar as dimensões."""
    from src.core.image.converter import convert_image
    with Image.open(session_jpg) as orig:
        orig_size = orig.size
    out = convert_image(session_jpg, out_dir, out_fmt="png", quality=85)
    with Image.open(out) as im:
        assert im.size == orig_size


def test_convert_rgba_to_jpg_flattens_alpha(tmp_path, out_dir):
    """PNG RGBA convertido para JPEG deve resultar em imagem RGB (sem canal alpha)."""
    from src.core.image.converter import convert_image
    png = tmp_path / "rgba.png"
    Image.new("RGBA", (50, 50), (255, 0, 0, 128)).save(png)
    out = convert_image(png, out_dir, out_fmt="jpg", quality=85)
    with Image.open(out) as im:
        assert im.mode == "RGB"
```

---

## 9. `tests/core/image/test_info.py`

```python
import pytest
from pathlib import Path
from PIL import Image

pytestmark = pytest.mark.integration


def test_image_info_returns_dict(session_jpg):
    from src.core.image.info import image_info
    info = image_info(session_jpg)
    assert isinstance(info, dict)
    assert "width" in info
    assert "height" in info
    assert info["width"] == 640
    assert info["height"] == 480


def test_image_info_format_field(session_jpg):
    from src.core.image.info import image_info
    info = image_info(session_jpg)
    assert info.get("format", "").upper() in ("JPEG", "JPG")


def test_thumbnail_bytes_returns_bytes(session_jpg):
    from src.core.image.info import thumbnail_bytes
    result = thumbnail_bytes(session_jpg, size=64)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_thumbnail_bytes_is_valid_image(session_jpg):
    """Bytes retornados devem ser uma imagem válida."""
    import io
    from src.core.image.info import thumbnail_bytes
    data = thumbnail_bytes(session_jpg, size=64)
    with Image.open(io.BytesIO(data)) as thumb:
        assert thumb.width <= 64
        assert thumb.height <= 64
```

---

## 10. `tests/core/video/test_info.py`

```python
import pytest

pytestmark = pytest.mark.integration


def test_get_video_info_returns_dataclass(sample_mp4):
    from src.core.video.info import get_video_info
    info = get_video_info(sample_mp4)
    assert info is not None
    assert hasattr(info, "width")
    assert hasattr(info, "height")
    assert hasattr(info, "duration")


def test_get_video_info_dimensions(sample_mp4):
    """Fixture MP4 é 320×240."""
    from src.core.video.info import get_video_info
    info = get_video_info(sample_mp4)
    assert info.width == 320
    assert info.height == 240


def test_get_video_info_duration(sample_mp4):
    from src.core.video.info import get_video_info
    info = get_video_info(sample_mp4)
    assert 2.5 <= info.duration <= 3.5


def test_get_video_info_nonexistent_returns_none_or_raises():
    """Arquivo inexistente deve retornar None ou lançar exceção conhecida."""
    from pathlib import Path
    from src.core.video.info import get_video_info
    result = get_video_info(Path("/nonexistent/video.mp4"))
    # Aceita None ou exceção — o importante é não travar silenciosamente
    assert result is None
```

---

## 11. Pipeline end-to-end de áudio (smoke test)

Testa o encadeamento completo: WAV → denoise → normalize, que é o pipeline real do módulo Áudio.

Criar em `tests/core/audio/test_pipeline_e2e.py`:

```python
import pytest

pytestmark = pytest.mark.integration


def test_full_audio_pipeline_denoise_then_normalize(sample_wav, tmp_path):
    """Smoke test: denoise → normalize encadeados devem produzir arquivo final."""
    from src.core.audio.denoiser import denoiser_out = denoise(sample_wav, tmp_path / "denoised")
    from src.core.audio.normalizer import normalize_lufs
    final, stats = normalize_lufs(denoised_out, tmp_path / "normalized", target_lufs=-14.0)
    assert final.exists()
    assert final.stat().st_size > 500
```

> **Nota:** corrija o import acima para `from src.core.audio.denoiser import denoise` ao implementar.

---

## 12. Estrutura final de pastas `tests/`

```
tests/
├── conftest.py                          ← fixtures globais (Parte 1 + Parte 2)
├── test_utils.py                        ← Parte 1
├── test_transcriber.py                  ← Parte 1
├── test_llm_factory.py                  ← Parte 1
├── core/
│   ├── __init__.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── test_normalizer_parser.py    ← Parte 1 (sem ffmpeg)
│   │   ├── test_converter.py            ← Parte 2
│   │   ├── test_normalizer_integration.py ← Parte 2
│   │   ├── test_denoiser.py             ← Parte 2
│   │   ├── test_info.py                 ← Parte 2
│   │   └── test_pipeline_e2e.py         ← Parte 2
│   ├── image/
│   │   ├── __init__.py
│   │   ├── test_transform.py            ← Parte 1
│   │   ├── test_converter.py            ← Parte 2
│   │   └── test_info.py                 ← Parte 2
│   └── video/
│       ├── __init__.py
│       └── test_info.py                 ← Parte 2
└── gui/
    ├── __init__.py
    ├── test_settings.py                 ← Parte 1
    └── modules/
        ├── __init__.py
        ├── audio/
        │   ├── __init__.py
        │   └── test_pipeline_log.py     ← Parte 1
        └── image/
            ├── __init__.py
            └── test_pipeline_log.py     ← Parte 1
```

---

## 13. Como executar

```bash
# Apenas integração
uv run pytest -m integration -v

# Tudo (unit + integration)
uv run pytest -v

# Apenas integração de áudio
uv run pytest tests/core/audio/ -m integration -v

# Com cobertura total
uv run pytest --cov=src --cov-report=term-missing --cov-report=html

# Paralelo com pytest-xdist (opcional — adicionar ao pyproject.toml se quiser)
uv run pytest -n auto
```

---

## 14. Considerações sobre CI

Se for configurar um pipeline de CI (GitHub Actions, etc.):

```yaml
# .github/workflows/tests.yml — referência (não criar agora)
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --group dev
      - run: uv run pytest -m "not integration" --cov=src

  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install ffmpeg
        run: sudo apt-get install -y ffmpeg
      - run: uv sync --group dev
      - run: uv run pytest -m integration
```

O job `unit` é rápido (<30s) e roda em todo PR. O job `integration` roda separado e é permitido ser mais lento.

---

## 15. Ordem de implementação sugerida

| Passo | Arquivo | Justificativa |
|-------|---------|---------------|
| 1 | `conftest.py` — fixtures de sessão | Pré-requisito: sample_wav, sample_mp4 |
| 2 | `core/audio/test_info.py` | Mais simples: apenas ffprobe, sem escrita |
| 3 | `core/audio/test_converter.py` | Cobre convert_audio + extract_audio |
| 4 | `core/audio/test_normalizer_integration.py` | Pipeline 2-pass loudnorm |
| 5 | `core/audio/test_denoiser.py` | Cobre noisereduce + soundfile |
| 6 | `core/audio/test_pipeline_e2e.py` | Smoke test encadeado |
| 7 | `core/image/test_converter.py` | Conversão de formato PIL |
| 8 | `core/image/test_info.py` | image_info + thumbnail_bytes |
| 9 | `core/video/test_info.py` | VideoInfo via ffprobe |

---

## Referências

- [Pytest Good Integration Practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [pytest tmp_path e tmp_path_factory](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [pytest-with-eric: tmp_path guide](https://pytest-with-eric.com/pytest-best-practices/pytest-tmp-path/)
- [ffmpeg lavfi sine source](https://ffmpeg.org/ffmpeg-filters.html#sine)
- [Pytest Best Practices 2026](https://qaskills.sh/blog/pytest-best-practices-2026)
