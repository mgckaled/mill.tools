# Plano de Implementação — Parte 1: Testes Unitários

> **Escopo:** funções puras e módulos sem dependências externas (sem ffmpeg, sem Whisper, sem rede).
> Todos os testes desta parte rodam em qualquer máquina com `uv run pytest -m "not integration"`.

---

## 1. Dependências de desenvolvimento

Adicionar ao `pyproject.toml` (seção `[dependency-groups]` ou `[tool.uv.dev-dependencies]`):

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-cov>=5.0",
    "pytest-mock>=3.14",
]
```

Instalar:

```bash
uv sync --group dev
```

---

## 2. Configuração do pytest no `pyproject.toml`

Adicionar ao final do `pyproject.toml` existente:

```toml
[tool.pytest.ini_options]
minversion = "8.0"
pythonpath = ["src", "."]   # resolve "from src.utils import ..." sem instalar o pacote
testpaths  = ["tests"]
addopts    = [
    "-ra",               # mostra razões de falha/skip no resumo final
    "-q",                # output compacto
    "--strict-markers",  # erro se marker não registrado
    "--tb=short",        # tracebacks curtos
]
markers = [
    "unit: testes unitários — sem dependências externas",
    "integration: requer ffmpeg, arquivos reais ou rede — skip com -m 'not integration'",
]

[tool.coverage.run]
source = ["src"]
omit   = ["src/gui/*"]   # GUI Flet não é testável de forma headless

[tool.coverage.report]
show_missing = true
skip_covered = false
```

---

## 3. Estrutura de pastas a criar

```
tests/
├── conftest.py            ← fixtures globais (imagens sintéticas, tmp config)
├── unit/                  ← (opcional) subpasta para separar por tipo de pytest marker
│   └── .gitkeep
├── test_utils.py
├── test_transcriber.py
├── test_llm_factory.py
├── gui/
│   ├── __init__.py
│   ├── test_settings.py
│   └── modules/
│       ├── __init__.py
│       ├── audio/
│       │   ├── __init__.py
│       │   └── test_pipeline_log.py
│       └── image/
│           ├── __init__.py
│           └── test_pipeline_log.py
└── core/
    ├── __init__.py
    ├── audio/
    │   ├── __init__.py
    │   └── test_normalizer_parser.py
    └── image/
        ├── __init__.py
        └── test_transform.py
```

> Adicionar `__init__.py` vazios em cada subpasta de `tests/` para evitar conflitos de import com o `src/` layout.

---

## 4. `tests/conftest.py` — fixtures globais

```python
"""Fixtures compartilhadas entre todos os testes."""
import io
from pathlib import Path

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Imagens sintéticas — geradas em memória, sem arquivo no disco
# ---------------------------------------------------------------------------

def _make_rgb_jpg(tmp_path: Path, width: int = 200, height: int = 150, name: str = "sample.jpg") -> Path:
    """Cria um JPEG RGB simples com gradiente de cor."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    path = tmp_path / name
    img.save(path, format="JPEG", quality=85)
    return path


def _make_rgba_png(tmp_path: Path, width: int = 100, height: int = 100, name: str = "sample.png") -> Path:
    """Cria um PNG RGBA com transparência."""
    img = Image.new("RGBA", (width, height), color=(255, 0, 0, 128))
    path = tmp_path / name
    img.save(path, format="PNG")
    return path


@pytest.fixture
def jpg_image(tmp_path: Path) -> Path:
    """Fixture: JPEG RGB 200×150."""
    return _make_rgb_jpg(tmp_path)


@pytest.fixture
def png_image(tmp_path: Path) -> Path:
    """Fixture: PNG RGBA 100×100."""
    return _make_rgba_png(tmp_path)


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    """Diretório de saída limpo por teste."""
    d = tmp_path / "output"
    d.mkdir()
    return d
```

---

## 5. `tests/test_utils.py` — `sanitize_filename` e helpers

`sanitize_filename` é o candidato de maior prioridade: 8 regexes, usada em todos os paths de saída do projeto.

### Casos a cobrir

```python
import pytest
from src.utils import sanitize_filename, format_duration, extract_video_id, format_metadata

# ── sanitize_filename ────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("title, expected", [
    # Separadores de seção → hífen
    ("Título | Parte 2",           "Título-Parte_2"),
    ("Título · Parte 2",           "Título-Parte_2"),
    ("Título – Parte 2",           "Título-Parte_2"),
    ("Título — Parte 2",           "Título-Parte_2"),
    # Dois pontos largos
    ("Python：Tutorial",           "Python-Tutorial"),
    # Chars inválidos Windows
    ('arquivo<>bad"name',          "arquivobadname"),
    ("path/with\\slash",           "pathwithslash"),
    ("name?with*wildcards",        "namewithwildcards"),
    # Pontuação exclamação/interrogação
    ("Título incrível!",           "Título_incrível"),
    ("Como funciona？",             "Como_funciona"),
    # Espaços → underscore
    ("palavra com espaço",         "palavra_com_espaço"),
    ("  espaço  nas  bordas  ",    "espaço__nas__bordas"),   # múltiplos → underscore
    # Acentos preservados (NTFS suporta)
    ("Programação Orientada",      "Programação_Orientada"),
    # Hífens com espaço → hífen simples
    ("A - B - C",                  "A-B-C"),
    # Múltiplos underscores / hífens colapsados
    ("a___b",                      "a_b"),
    ("a---b",                      "a-b"),
    # String vazia após sanitização
    ("!!!",                        ""),
    # Preserva números e maiúsculas
    ("Python 3.13 Tutorial",       "Python_313_Tutorial"),  # ponto é char inválido? não — não está em _SANITIZE_INVALID
])
def test_sanitize_filename_parametrize(title, expected):
    assert sanitize_filename(title) == expected


@pytest.mark.unit
def test_sanitize_filename_strip_leading_trailing():
    """Resultado nunca começa ou termina com '-', '_' ou '.'."""
    result = sanitize_filename("  - título -  ")
    assert not result.startswith(("-", "_", "."))
    assert not result.endswith(("-", "_", "."))


# ── format_duration ──────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("seconds, expected", [
    (0,     "00:00:00"),
    (59,    "00:00:59"),
    (60,    "00:01:00"),
    (3599,  "00:59:59"),
    (3600,  "01:00:00"),
    (7384,  "02:03:04"),
    (86400, "24:00:00"),  # 1 dia
])
def test_format_duration(seconds, expected):
    from src.utils import format_duration
    assert format_duration(seconds) == expected


# ── extract_video_id ─────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("url, expected_len", [
    ("https://www.youtube.com/watch?v=ovabeVoWrA0", 6),
    ("https://youtu.be/ovabeVoWrA0",                6),
    ("https://youtu.be/dQw4w9WgXcQ",                6),
])
def test_extract_video_id_length(url, expected_len):
    from src.utils import extract_video_id
    result = extract_video_id(url)
    assert len(result) == expected_len
    assert result.isalnum()  # só letras e dígitos


@pytest.mark.unit
def test_extract_video_id_consistency():
    """Mesma URL sempre retorna mesmo slug."""
    from src.utils import extract_video_id
    url = "https://youtu.be/dQw4w9WgXcQ"
    assert extract_video_id(url) == extract_video_id(url)


# ── format_metadata ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_format_metadata_contains_required_fields():
    from src.utils import format_metadata
    meta = {
        "title": "Test Video",
        "uploader": "Test Channel",
        "upload_date": "20240115",
        "duration": 125,
        "tags": ["python", "test"],
    }
    result = format_metadata(meta, "https://youtu.be/abc123", detected_language="pt")
    assert "Test Video" in result
    assert "Test Channel" in result
    assert "2024-01-15" in result
    assert "00:02:05" in result
    assert "pt" in result
    assert "python, test" in result
    assert "-" * 64 in result  # separador obrigatório


@pytest.mark.unit
def test_format_metadata_missing_fields_use_na():
    from src.utils import format_metadata
    result = format_metadata({}, "https://youtu.be/abc123")
    assert "n/a" in result
```

---

## 6. `tests/test_transcriber.py` — helpers puros

```python
import pytest


# ── format_elapsed ───────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("seconds, expected", [
    (0,      "0s"),
    (5,      "5s"),
    (59,     "59s"),
    (60,     "1m 00s"),
    (90,     "1m 30s"),
    (3600,   "1h 00m 00s"),
    (3661,   "1h 01m 01s"),
    (7384,   "2h 03m 04s"),
])
def test_format_elapsed(seconds, expected):
    from src.transcriber import format_elapsed
    assert format_elapsed(seconds) == expected


# ── _resolve_device ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_resolve_device_cuda_fallback(mocker):
    """Se ctranslate2 lança RuntimeError, deve retornar CPU."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        side_effect=RuntimeError("no CUDA"),
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cpu"
    assert compute == "int8"


@pytest.mark.unit
def test_resolve_device_cuda_int8_float32(mocker):
    """Se int8_float32 disponível em CUDA, deve preferir CUDA."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        return_value=["int8_float32", "float32"],
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cuda"
    assert compute == "int8_float32"


@pytest.mark.unit
def test_resolve_device_cuda_float32_fallback(mocker):
    """Se apenas float32 disponível em CUDA, usa float32."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        return_value=["float32"],
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cuda"
    assert compute == "float32"
```

---

## 7. `tests/test_llm_factory.py` — roteamento de provider

```python
import os
import pytest


@pytest.mark.unit
@pytest.mark.parametrize("model, expected", [
    ("gemini-2.5-flash", True),
    ("gemini-1.5-pro",   True),
    ("GEMINI-test",      True),
    ("qwen7b-custom",    False),
    ("phi4mini-custom",  False),
    ("ollama-model",     False),
    ("",                 False),
])
def test_is_gemini(model, expected):
    from src.llm_factory import is_gemini_model
    assert is_gemini_model(model) == expected


@pytest.mark.unit
def test_make_llm_gemini_raises_without_api_key(monkeypatch):
    """make_llm para gemini sem GOOGLE_API_KEY deve lançar RuntimeError."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    # Patch load_dotenv para não ler .env real do disco
    monkeypatch.setattr("src.llm_factory.load_dotenv", lambda *a, **kw: None)
    from src.llm_factory import make_llm
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        make_llm("gemini-2.5-flash")


@pytest.mark.unit
def test_make_llm_routes_ollama(mocker):
    """make_llm para nome sem prefixo 'gemini' deve instanciar ChatOllama."""
    mock_ollama = mocker.patch("src.llm_factory._make_ollama")
    from src.llm_factory import make_llm
    make_llm("qwen7b-custom", temperature=0.4)
    mock_ollama.assert_called_once_with("qwen7b-custom", 0.4)


@pytest.mark.unit
def test_make_llm_routes_gemini(mocker, monkeypatch):
    """make_llm para 'gemini-*' deve chamar _make_gemini."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-test")
    mock_gemini = mocker.patch("src.llm_factory._make_gemini")
    from src.llm_factory import make_llm
    make_llm("gemini-2.5-flash", temperature=0.0)
    mock_gemini.assert_called_once_with("gemini-2.5-flash", 0.0)
```

---

## 8. `tests/gui/test_settings.py` — persistência de configurações

O truque aqui é redirecionar `_CONFIG_DIR` e `_CONFIG_FILE` para o `tmp_path` do pytest via `monkeypatch`.

```python
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_config(tmp_path: Path, monkeypatch):
    """Redireciona o módulo settings para usar tmp_path em vez de ~/.mill-tools."""
    cfg_dir  = tmp_path / ".mill-tools"
    cfg_file = cfg_dir / "config.json"
    import src.gui.settings as settings_mod
    monkeypatch.setattr(settings_mod, "_CONFIG_DIR",  cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_file)


@pytest.mark.unit
def test_load_returns_defaults_when_no_file():
    from src.gui import settings
    data = settings.load()
    assert data["last_whisper_model"] == "small"
    assert data["theme_mode"] == "dark"
    assert data["last_beam_size"] == 1


@pytest.mark.unit
def test_save_and_load_roundtrip():
    from src.gui import settings
    settings.save({"last_whisper_model": "large-v3", "theme_mode": "light"})
    data = settings.load()
    assert data["last_whisper_model"] == "large-v3"
    assert data["theme_mode"] == "light"
    # Defaults para chaves não salvas devem ser completados
    assert "last_beam_size" in data


@pytest.mark.unit
def test_get_existing_key():
    from src.gui import settings
    settings.save({"last_language": "pt"})
    assert settings.get("last_language") == "pt"


@pytest.mark.unit
def test_get_missing_key_returns_default_param():
    from src.gui import settings
    assert settings.get("chave_inexistente", "fallback") == "fallback"


@pytest.mark.unit
def test_set_updates_single_key():
    from src.gui import settings
    settings.set("last_beam_size", 5)
    assert settings.get("last_beam_size") == 5


@pytest.mark.unit
def test_load_handles_corrupted_json(tmp_path: Path, monkeypatch):
    """Arquivo JSON corrompido deve retornar defaults sem lançar exceção."""
    cfg_dir  = tmp_path / ".mill-tools"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "config.json"
    cfg_file.write_text("{ invalid json }", encoding="utf-8")
    import src.gui.settings as settings_mod
    monkeypatch.setattr(settings_mod, "_CONFIG_DIR",  cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_file)
    data = settings_mod.load()
    assert data["last_whisper_model"] == "small"  # default
```

---

## 9. `tests/core/audio/test_normalizer_parser.py` — parser do stderr ffmpeg

`_parse_loudnorm_json` é uma função interna crítica: se falhar silenciosamente, o segundo passe do ffmpeg usará parâmetros errados.

```python
import pytest
from src.core.audio.normalizer import _parse_loudnorm_json


# Bloco JSON real extraído de uma execução real do ffmpeg loudnorm
_REAL_STDERR = """\
[Parsed_loudnorm_0 @ 0x...] Input Integrated:    -18.3 LUFS
{
    "input_i" : "-18.27",
    "input_tp" : "-3.21",
    "input_lra" : "8.10",
    "input_thresh" : "-28.36",
    "output_i" : "-14.00",
    "output_tp" : "-1.15",
    "output_lra" : "7.95",
    "output_thresh" : "-24.09",
    "normalization_type" : "dynamic",
    "target_offset" : "0.15"
}
size=       0kB time=00:00:10.38 bitrate=   0.0kbits/s speed= 108x
"""


@pytest.mark.unit
def test_parse_loudnorm_json_valid():
    result = _parse_loudnorm_json(_REAL_STDERR)
    assert result is not None
    assert result["input_i"] == "-18.27"
    assert result["input_tp"] == "-3.21"
    assert result["target_offset"] == "0.15"


@pytest.mark.unit
def test_parse_loudnorm_json_all_keys_present():
    result = _parse_loudnorm_json(_REAL_STDERR)
    expected_keys = {
        "input_i", "input_tp", "input_lra", "input_thresh",
        "output_i", "output_tp", "output_lra", "output_thresh",
        "normalization_type", "target_offset",
    }
    assert expected_keys.issubset(result.keys())


@pytest.mark.unit
def test_parse_loudnorm_json_no_json_block():
    """stderr sem bloco JSON deve retornar None sem lançar exceção."""
    result = _parse_loudnorm_json("ffmpeg version 6.1\nSome other output\n")
    assert result is None


@pytest.mark.unit
def test_parse_loudnorm_json_empty_string():
    assert _parse_loudnorm_json("") is None


@pytest.mark.unit
def test_parse_loudnorm_json_malformed_json():
    stderr = "{\n  invalid_json_here\n}\n"
    result = _parse_loudnorm_json(stderr)
    assert result is None


@pytest.mark.unit
def test_parse_loudnorm_json_partial_block():
    """Bloco JSON abre mas não fecha — deve retornar None."""
    stderr = "{\n  \"input_i\": \"-18.27\"\n"  # sem fechar
    result = _parse_loudnorm_json(stderr)
    assert result is None
```

---

## 10. `tests/core/image/test_transform.py` — 9 funções de transformação PIL

Todas as funções são puras (entrada: `Path`, saída: `Path`). Use as fixtures `jpg_image`, `png_image` e `out_dir` do `conftest.py`.

### Estratégia geral por função

Para cada função, verificar:
1. O arquivo de saída foi criado
2. As dimensões/modo de saída são os esperados (via `PIL.Image.open`)
3. Edge cases específicos da lógica

```python
import pytest
from pathlib import Path
from PIL import Image


# ── resize_image ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_resize_contain_respects_aspect_ratio(jpg_image, out_dir):
    from src.core.image.transform import resize_image
    out = resize_image(
        jpg_image, out_dir,
        resize_mode="contain", width=100, height=100,
        scale_pct=100.0, out_fmt=None, quality=85,
    )
    assert out.exists()
    with Image.open(out) as im:
        assert im.width <= 100
        assert im.height <= 100


@pytest.mark.unit
def test_resize_exact_ignores_aspect_ratio(jpg_image, out_dir):
    from src.core.image.transform import resize_image
    out = resize_image(
        jpg_image, out_dir,
        resize_mode="exact", width=50, height=80,
        scale_pct=100.0, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (50, 80)


@pytest.mark.unit
def test_resize_scale_pct(jpg_image, out_dir):
    from src.core.image.transform import resize_image
    with Image.open(jpg_image) as src:
        orig_w, orig_h = src.size
    out = resize_image(
        jpg_image, out_dir,
        resize_mode="scale_pct", width=None, height=None,
        scale_pct=50.0, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.width == orig_w // 2
        assert im.height == orig_h // 2


@pytest.mark.unit
def test_resize_converts_format(jpg_image, out_dir):
    """Conversão de formato junto com resize."""
    from src.core.image.transform import resize_image
    out = resize_image(
        jpg_image, out_dir,
        resize_mode="contain", width=100, height=100,
        scale_pct=100.0, out_fmt="png", quality=85,
    )
    assert out.suffix.lower() == ".png"


# ── crop_image ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_crop_manual(jpg_image, out_dir):
    from src.core.image.transform import crop_image
    out = crop_image(
        jpg_image, out_dir,
        crop_mode="manual", left=10, top=10,
        crop_width=50, crop_height=50,
        ratio="4:3", trim_color="#ffffff",
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (50, 50)


@pytest.mark.unit
def test_crop_ratio_16_9(jpg_image, out_dir):
    from src.core.image.transform import crop_image
    out = crop_image(
        jpg_image, out_dir,
        crop_mode="ratio", left=0, top=0,
        crop_width=0, crop_height=0,
        ratio="16:9", trim_color="#ffffff",
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        w, h = im.size
        ratio = w / h
        assert abs(ratio - 16 / 9) < 0.1


@pytest.mark.unit
def test_crop_autotrim_white_bg(tmp_path, out_dir):
    """Auto-trim remove bordas brancas."""
    from src.core.image.transform import crop_image
    # Cria imagem com borda branca grossa
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 79, 79], fill=(0, 0, 200))
    src = tmp_path / "white_border.jpg"
    img.save(src)
    out = crop_image(
        src, out_dir,
        crop_mode="autotrim", left=0, top=0,
        crop_width=0, crop_height=0,
        ratio="1:1", trim_color="#ffffff",
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        # Resultado deve ser menor que a imagem original
        assert im.width < 100
        assert im.height < 100


# ── rotate_image ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("angle, expected_size", [
    (0,   (200, 150)),
    (90,  (150, 200)),
    (180, (200, 150)),
    (270, (150, 200)),
])
def test_rotate_angle_swaps_dimensions(jpg_image, out_dir, angle, expected_size):
    from src.core.image.transform import rotate_image
    out = rotate_image(
        jpg_image, out_dir,
        angle=angle, flip_h=False, flip_v=False,
        exif_auto=False, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == expected_size


@pytest.mark.unit
def test_rotate_flip_horizontal(jpg_image, out_dir):
    from src.core.image.transform import rotate_image
    out = rotate_image(
        jpg_image, out_dir,
        angle=0, flip_h=True, flip_v=False,
        exif_auto=False, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        # Dimensões preservadas após flip horizontal
        assert im.size == (200, 150)


# ── add_border ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_add_border_increases_size(jpg_image, out_dir):
    from src.core.image.transform import add_border
    out = add_border(
        jpg_image, out_dir,
        padding=10, color="#000000",
        fill_alpha=False, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.width == 220   # 200 + 10*2
        assert im.height == 170  # 150 + 10*2


@pytest.mark.unit
def test_add_border_to_png_rgba(png_image, out_dir):
    """PNG RGBA com fill_alpha=True deve converter para RGB antes da borda."""
    from src.core.image.transform import add_border
    out = add_border(
        png_image, out_dir,
        padding=5, color="#ffffff",
        fill_alpha=True, out_fmt="png", quality=85,
    )
    assert out.exists()


# ── adjust_image ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_adjust_identity_does_not_crash(jpg_image, out_dir):
    """Todos os valores em 1.0 (identidade) não deve alterar dimensões."""
    from src.core.image.transform import adjust_image
    out = adjust_image(
        jpg_image, out_dir,
        brightness=1.0, contrast=1.0, color=1.0, sharpness=1.0,
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (200, 150)


@pytest.mark.unit
@pytest.mark.parametrize("brightness", [0.5, 1.5, 2.0])
def test_adjust_brightness_variants(jpg_image, out_dir, brightness):
    from src.core.image.transform import adjust_image
    out = adjust_image(
        jpg_image, out_dir,
        brightness=brightness, contrast=1.0, color=1.0, sharpness=1.0,
        out_fmt=None, quality=85,
    )
    assert out.exists()


# ── apply_filter ──────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("filter_type", [
    "blur", "sharpen", "autocontrast", "equalize", "grayscale",
])
def test_apply_filter_all_types(jpg_image, out_dir, filter_type):
    from src.core.image.transform import apply_filter
    out = apply_filter(
        jpg_image, out_dir,
        filter_type=filter_type, out_fmt=None, quality=85,
    )
    assert out.exists()


@pytest.mark.unit
def test_apply_filter_grayscale_mode(jpg_image, out_dir):
    from src.core.image.transform import apply_filter
    out = apply_filter(
        jpg_image, out_dir,
        filter_type="grayscale", out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.mode == "L"


# ── make_favicon ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_make_favicon_creates_ico(jpg_image, out_dir):
    from src.core.image.transform import make_favicon
    out = make_favicon(jpg_image, out_dir, sizes=[16, 32, 48])
    assert out.exists()
    assert out.suffix.lower() == ".ico"


# ── make_contact_sheet ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_make_contact_sheet_single_image(jpg_image, out_dir):
    from src.core.image.transform import make_contact_sheet
    out = make_contact_sheet(
        [jpg_image], out_dir,
        cols=3, thumb_size=100, gap=5,
        bg_color="#cccccc", out_fmt="jpg", quality=85,
    )
    assert out.exists()


@pytest.mark.unit
def test_make_contact_sheet_empty_list_raises(out_dir):
    from src.core.image.transform import make_contact_sheet
    with pytest.raises(ValueError, match="Nenhum arquivo válido"):
        make_contact_sheet(
            [], out_dir,
            cols=3, thumb_size=100, gap=5,
            bg_color="#ffffff", out_fmt="jpg", quality=85,
        )


@pytest.mark.unit
def test_make_contact_sheet_invalid_files_ignored(jpg_image, tmp_path, out_dir):
    """Arquivos inválidos são ignorados; válidos são processados."""
    invalid = tmp_path / "not_an_image.txt"
    invalid.write_text("not an image")
    from src.core.image.transform import make_contact_sheet
    out = make_contact_sheet(
        [invalid, jpg_image], out_dir,
        cols=2, thumb_size=80, gap=4,
        bg_color="#ffffff", out_fmt="png", quality=85,
    )
    assert out.exists()


# ── _out_path (anti-colisão) ──────────────────────────────────────────────────

@pytest.mark.unit
def test_out_path_no_collision(jpg_image, out_dir):
    """Segunda chamada com mesmo src deve gerar nome diferente."""
    from src.core.image.transform import _out_path
    p1 = _out_path(jpg_image, out_dir, None)
    p1.touch()  # simula que o primeiro já foi criado
    p2 = _out_path(jpg_image, out_dir, None)
    assert p1 != p2


# ── _wm_coords (helper watermark) ─────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("position, expected", [
    ("top-left",     (10, 10)),
    ("top-right",    (170, 10)),   # 200 - 20 - 10 = 170
    ("bottom-left",  (10, 120)),   # 150 - 20 - 10 = 120
    ("center",       (90, 65)),    # (200-20)//2=90, (150-20)//2=65
    ("bottom-right", (170, 120)),
])
def test_wm_coords(position, expected):
    from src.core.image.transform import _wm_coords
    result = _wm_coords(iw=200, ih=150, ww=20, wh=20, position=position, margin=10)
    assert result == expected
```

---

## 11. Como executar

```bash
# Apenas testes unitários (sem ffmpeg, sem rede)
uv run pytest -m unit -v

# Todos os testes não-integração (inclui não-marcados também)
uv run pytest -m "not integration" -v

# Com relatório de cobertura
uv run pytest -m "not integration" --cov=src --cov-report=term-missing

# Um arquivo específico
uv run pytest tests/test_utils.py -v

# Filtrar por nome de teste
uv run pytest -k "sanitize" -v
```

---

## 12. Ordem de implementação sugerida

| Passo | Arquivo | Justificativa |
|-------|---------|---------------|
| 1 | `pyproject.toml` — config pytest | Pré-requisito de tudo |
| 2 | `tests/conftest.py` | Fixtures usadas por vários testes |
| 3 | `tests/test_utils.py` | Maior risco, maior cobertura imediata |
| 4 | `tests/core/image/test_transform.py` | Módulo mais testável, 9 funções puras |
| 5 | `tests/gui/test_settings.py` | Persistência crítica para todos os módulos |
| 6 | `tests/core/audio/test_normalizer_parser.py` | Parser crítico, sem dependência de ffmpeg |
| 7 | `tests/test_transcriber.py` | Helpers + mock de ctranslate2 |
| 8 | `tests/test_llm_factory.py` | Roteamento de LLM + mock |
| 9 | `tests/gui/modules/*/test_pipeline_log.py` | Vocabulário dos módulos (builders `fmt_*`) |

---

## Referências

- [Pytest Good Integration Practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [How to use fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [pytest tmp_path](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [pytest-mock docs](https://pytest-mock.readthedocs.io/en/latest/)
- [Pytest Best Practices 2026](https://qaskills.sh/blog/pytest-best-practices-2026)
- [Testing Image Generation — jacobian.org](https://jacobian.org/til/testing-image-generation/)
