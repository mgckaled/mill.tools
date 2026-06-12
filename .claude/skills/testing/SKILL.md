---
name: testing
description: Guia para adicionar, corrigir e revisar testes (unitários e de integração) do projeto mill.tools. Invocar quando: escrever novos testes, investigar expected values errados, aumentar cobertura de um módulo, mockar subprocess/ctranslate2/PIL.Image.open/llm_factory/settings/pymupdf/qrcode, ou entender por que um teste falha. Também use ao criar fixtures novas (session-scoped ou function-scoped), adicionar testes de integração com ffmpeg, ou revisar tests/core/ e tests/gui/.
---

# mill.tools — Guia de Testes

## Estrutura de arquivos

```
tests/
├── conftest.py                              # fixtures globais — NÃO duplicar aqui
├── test_utils.py                            # src/utils.py
├── test_transcriber.py                      # src/transcriber.py
├── test_llm_factory.py                      # src/llm_factory.py
├── test_llm_utils.py                        # src/llm_utils.py — split_text, bypass Gemini
├── cli/
│   ├── __init__.py
│   ├── test_transcription.py               # unit — resolve_input, build_output_stem, item_label
│   ├── test_audio_cli.py                   # unit — add_audio_parser + run_audio_cli (dispatch)
│   ├── test_video_cli.py                   # unit — sub-subparsers + run_video_cli (dispatch)
│   ├── test_image_cli.py                   # unit — sub-subparsers + run_image_cli (dispatch)
│   ├── test_document_cli.py                # unit — sub-subparsers + run_document_cli (dispatch)
│   └── test_bus.py                         # unit — CLIEventBus (eventos e formatação)
├── core/
│   ├── __init__.py
│   ├── test_ffmpeg.py                      # unit — run_ffmpeg (subprocess mockado)
│   ├── test_metadata.py                    # unit — format_duration e helpers de metadata
│   ├── audio/
│   │   ├── test_normalizer_parser.py       # unit — _parse_loudnorm_json (sem ffmpeg)
│   │   ├── test_normalizer_unit.py         # unit — normalize_lufs (subprocess mockado)
│   │   ├── test_converter.py               # integration — convert_audio, extract_audio
│   │   ├── test_normalizer_integration.py  # integration — normalize_lufs 2-pass
│   │   ├── test_denoiser.py                # integration — denoise mono e estéreo
│   │   ├── test_info.py                    # integration — get_duration_ffprobe
│   │   └── test_pipeline_e2e.py            # integration — smoke test denoise→normalize
│   ├── image/
│   │   ├── test_transform.py               # unit — 9 funções puras Pillow
│   │   ├── test_converter.py               # unit — convert_image (PIL puro)
│   │   ├── test_info.py                    # unit — image_info, thumbnail_bytes (PIL puro)
│   │   └── test_downloader.py              # unit — download_image (urllib mockado)
│   ├── video/
│   │   ├── test_info.py                    # integration — get_video_info (VideoInfo dataclass)
│   │   └── test_converter.py               # integration — convert/trim/compress/resize/extract_audio/thumbnail
│   └── document/
│       ├── test_processor.py               # unit — merge/split/compress/rotate/watermark/stamp/encrypt (pymupdf REAL via sample_pdf)
│       ├── test_converter.py               # unit — pdf_to_images, images_to_pdf, extract_text (pymupdf REAL)
│       ├── test_info.py                    # unit — get_pdf_info, PdfInfo (pymupdf REAL)
│       └── test_qr.py                      # unit — generate_qr (qrcode REAL — gera PNG em disco)
└── gui/
    ├── __init__.py
    ├── test_settings.py                    # unit — src/gui/settings.py
    └── modules/
        ├── audio/test_pipeline_log.py      # unit — resolve_*, fmt_* (download/convert/extract/denoise/normalize)
        ├── image/test_pipeline_log.py      # unit — resolve_*, fmt_* (13 operações)
        ├── video/test_pipeline_log.py      # unit — resolve_*, fmt_* (7 operações)
        └── document/test_pipeline_log.py   # unit — resolve_messages, resolve_stage_label, fmt_* builders
```

> **Nota sobre `unit` no módulo document**: ao contrário do que a tabela
> sugeria em versões antigas desta skill, `tests/core/document/` **não
> mocka pymupdf**. As fixtures `sample_pdf` e `sample_pdf_with_images`
> (em `conftest.py`) usam `pytest.importorskip("pymupdf")` e geram PDFs
> reais em disco. Mantemos o marcador `unit` porque pymupdf é dependência
> hard (não opcional) e não há `ffmpeg`/rede/GPU envolvidos — o hook de
> skip do conftest não precisa pular esses testes.

Regras de estrutura:
- Espelhar `src/` em `tests/` — `src/core/image/transform.py` → `tests/core/image/test_transform.py`
- Cada subpasta de `tests/` precisa de `__init__.py` vazio (evita conflito de import com src/)
- Imports dentro dos testes: `from src.modulo import funcao` (nunca import relativo)

---

## Fixtures globais (`tests/conftest.py`)

### Fixtures function-scoped (padrão — limpas por teste)

| Fixture | O que fornece |
|---|---|
| `jpg_image` | `Path` → JPEG RGB 200×150 em `tmp_path` |
| `png_image` | `Path` → PNG RGBA 100×100 em `tmp_path` |
| `out_dir` | `Path` → `tmp_path/output/` já criado |

Para imagens especiais (palette, grayscale, retratos), criar localmente dentro do teste com `tmp_path`:
```python
img = Image.new("RGB", (50, 200), (100, 100, 100))
src = tmp_path / "portrait.png"
img.save(src)
```

### Fixtures session-scoped (geradas uma vez por sessão via ffmpeg/Pillow)

| Fixture | O que fornece |
|---|---|
| `sample_wav` | `Path` → WAV mono 44100 Hz 3 s (sine 440 Hz) via ffmpeg lavfi |
| `sample_mp3` | `Path` → MP3 mono 128 kbps 3 s via ffmpeg lavfi |
| `sample_mp4` | `Path` → MP4 320×240 3 s (vídeo azul + áudio sine) via ffmpeg |
| `sample_wav_stereo` | `Path` → WAV estéreo 44100 Hz 3 s (sine 440 Hz, 2 canais) via ffmpeg |
| `session_jpg` | `Path` → JPEG RGB 640×480 via Pillow |

Estas fixtures só existem para testes de integração marcados com `@pytest.mark.integration`.
Não as use em testes unitários — eles não devem depender de ffmpeg.

### Hook de skip automático

`pytest_collection_modifyitems` em `conftest.py` pula automaticamente qualquer teste `@pytest.mark.integration` se `ffmpeg` não estiver no PATH (ex.: CI sem ffmpeg).

---

## Padrão de teste de CLI (`tests/cli/`)

Nunca chamar `sys.argv` diretamente — criar `_parse(*argv)` local com parser isolado:

```python
def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_audio_parser(sub)
    return parser.parse_args(["audio", *argv])

@pytest.mark.unit
def test_defaults():
    ns = _parse("https://youtu.be/abc")
    assert ns.fmt == "mp3"
    assert callable(ns.func)
```

Para testar o **runner** (a função `run_*_cli` que traduz `Namespace` →
`XxxArgs` e dispara a pipeline), mocke a função de pipeline no
**caminho onde ela é importada** (não onde é definida — embora aqui
seja o mesmo arquivo) e a verificação de dependências:

```python
def test_run_audio_cli_dispatches_to_pipeline(mocker):
    mocker.patch("src.utils.check_dependencies")  # ou "src.utils.setup_logging" no doc
    mock_pipeline = mocker.patch(
        "src.gui.modules.audio.worker.run_audio_pipeline",
        return_value=True,
    )
    ns = _parse("https://youtu.be/abc", "--normalize", "--lufs", "-16")
    ns.func(ns)
    assert mock_pipeline.called
    args = mock_pipeline.call_args.args[0]   # AudioArgs construído pelo runner
    assert args.normalize is True
    assert args.normalize_target_lufs == -16.0
```

Caminhos das pipelines a mockar:

| CLI         | Função a mockar                                     |
|-------------|-----------------------------------------------------|
| `audio`     | `src.gui.modules.audio.worker.run_audio_pipeline`   |
| `video`     | `src.gui.modules.video.worker.run_video_pipeline`   |
| `image`     | `src.gui.modules.image.worker.run_image_pipeline`   |
| `document`  | `src.gui.modules.document.worker.run_document_pipeline` |

Quando o runner retorna `False`, ele chama `sys.exit(1)`. Para cobrir
esse caminho, use `pytest.raises(SystemExit)` (apenas `audio`/`video`/
`image` têm essa branch — `document` não).

Gotcha kebab → snake: operações como `extract-audio` (CLI) viram
`extract_audio` em `VideoArgs.operation`. `pdf-to-images` vira
`pdf_to_images`. `contact-sheet` vira `contact_sheet`. Sempre asserte
o nome em `snake_case` no `Args` construído.

`_pipeline_runner.item_label` é testável diretamente — sempre verificar que `kind="local"` retorna `Path(value).name` e `kind="url"` retorna o `netloc` (ver `tests/cli/test_transcription.py`).

---

## Templates de novos arquivos de teste

### Teste unitário (sem ffmpeg, sem I/O real)

```python
import pytest
# from pathlib import Path  # se precisar de Path
# from PIL import Image     # se testar Pillow


@pytest.mark.unit
def test_nome_descritivo(fixture_se_necessario):
    from src.modulo import funcao_alvo
    resultado = funcao_alvo(entrada)
    assert resultado == esperado
```

Regras:
- Todo teste unitário deve ter `@pytest.mark.unit`
- Imports do código testado **dentro** da função de teste (não no topo) — isola falha de import
- Nome do teste descreve o comportamento, não a implementação

### Teste de integração (requer ffmpeg)

```python
import pytest

pytestmark = pytest.mark.integration  # aplica a todos no módulo


def test_nome_descritivo(sample_wav, out_dir):
    from src.core.audio.converter import convert_audio
    out = convert_audio(sample_wav, out_dir, fmt="mp3", bitrate="128")
    assert out.exists()
    assert out.stat().st_size > 1000
```

Regras:
- Usar `pytestmark = pytest.mark.integration` no nível do módulo (não por função)
- Fixtures session-scoped (`sample_wav`, `sample_mp4`, `session_jpg`) são somente leitura — não escrever nelas
- Para testes que modificam entrada, copiar o fixture com `shutil.copy` para `tmp_path`
- Rodar isoladamente com `uv run pytest -m integration -v`

---

## Gotchas críticos — expected values

### `sanitize_filename` (src/utils.py)

O ponto `.` **não está em `_SANITIZE_INVALID`** — é preservado:
```python
sanitize_filename("Python 3.13 Tutorial")  # → "Python_3.13_Tutorial" não "Python_313_Tutorial"
```

`\s+` já colapsa múltiplos espaços em único `_`:
```python
sanitize_filename("  a  b  ")  # → "a_b" não "a__b"
```

### `crop_image` modo `ratio` — branch `if target_h > ih`

A branch dispara quando `iw * rh / rw > ih`, ou seja, quando a imagem é **mais larga** que a proporção pedida. Exemplo com `jpg_image` (200×150) e ratio `"1:1"`:
- `target_h = int(200 * 1/1) = 200 > 150` → branch dispara → resultado: 150×150

Uma imagem portrait (100×200) com ratio `"16:9"` **não dispara** a branch (target_h = 56 < 200).

### `_save` e o modo `L` (grayscale)

`_save()` converte qualquer modo que não seja RGB para RGB ao salvar como JPEG. Um teste que verifica `im.mode == "L"` **precisa usar `out_fmt="png"`**:
```python
out = apply_filter(src, out_dir, filter_type="grayscale", out_fmt="png", quality=85)
with Image.open(out) as im:
    assert im.mode == "L"  # ✓ PNG preserva L; JPEG converteria para RGB
```

### `convert_audio` — bitrate sem "k"

`convert_audio` acrescenta "k" internamente: `f"{bitrate}k"`. Passar `"128k"` resulta em `"128kk"` (erro ffmpeg):
```python
# ERRADO — gera -b:a 128kk
convert_audio(src, out_dir, fmt="mp3", bitrate="128k")

# CORRETO — gera -b:a 128k
convert_audio(src, out_dir, fmt="mp3", bitrate="128")
```

### `autotrim` com artefatos JPEG

`ImageChops.difference` em imagens JPEG pode ter pixels não-zero em áreas "brancas" por artefatos de compressão. Imagens de teste para autotrim devem ser salvas como **PNG**:
```python
src = tmp_path / "border.png"  # ← .png, nunca .jpg para autotrim
img.save(src)
```

---

## Padrões de mock

### `mocker` (pytest-mock) — para substituir funções/módulos

```python
def test_algo(mocker):
    # Substituir função em módulo já importado
    mocker.patch("ctranslate2.get_supported_compute_types", return_value=["float32"])
    mocker.patch("src.llm_factory._make_ollama")  # retorna MagicMock
    mock = mocker.patch("src.modulo.funcao", side_effect=OSError("falha"))
```

### `monkeypatch` — para env vars e atributos de módulo

```python
def test_algo(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("src.llm_factory.load_dotenv", lambda *a, **kw: None)
    # Para módulos já importados:
    import src.gui.settings as mod
    monkeypatch.setattr(mod, "_CONFIG_FILE", tmp_path / "config.json")
```

### Isolamento de `src/gui/settings.py`

O módulo usa `_CONFIG_DIR` e `_CONFIG_FILE` como globais. Redirecionar antes de chamar `load()`/`save()`:
```python
@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    import src.gui.settings as mod
    monkeypatch.setattr(mod, "_CONFIG_DIR",  tmp_path / ".mill-tools")
    monkeypatch.setattr(mod, "_CONFIG_FILE", tmp_path / ".mill-tools" / "config.json")
```

### Mock de `subprocess.Popen` — para testar pipelines ffmpeg

Útil para cobrir branches de erro em `converter.py`, `normalizer.py` e `denoiser.py` sem rodar ffmpeg real:

```python
def _mock_popen(mocker, returncode: int, stdout: list[bytes] = None, stderr: list[bytes] = None):
    proc = mocker.MagicMock()
    proc.stdout = iter(stdout or [])   # iterável de bytes (cada linha = um item)
    proc.stderr = iter(stderr or [])
    proc.returncode = returncode
    proc.wait.return_value = None
    return proc


# Falha no segundo passe (returncode != 0)
mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0, stderr=b"...", stdout=b""))
mock_proc = _mock_popen(mocker, returncode=1, stderr=[b"encoder error\n"])
mocker.patch("subprocess.Popen", return_value=mock_proc)

# Múltiplos calls sequenciais a subprocess.run (ex.: pass 1 + ffprobe):
mocker.patch("subprocess.run", side_effect=[
    mocker.Mock(returncode=0, stderr=LOUDNORM_JSON, stdout=b""),  # pass 1
    mocker.Mock(returncode=0, stdout=b"3.0\n", stderr=b""),       # ffprobe
])
```

**Cuidado com threading**: `_drain()` em `normalizer.py` lê `proc.stderr` em thread daemon. O iterador deve ser thread-safe (um simples `iter([b"..."])` funciona). Para `proc.stdout` linhas de progresso, incluir `b"out_time_us=N\n"` para testar o callback.

### Mock de `urllib.request.urlopen` — para testar download_image

`urlopen` é usado como context manager (`with urlopen(...) as resp`).
Substituir por `@contextmanager` quebra na **segunda chamada** porque
generators são single-use. Use `MagicMock` (reusável):

```python
from unittest.mock import MagicMock

def _fake_urlopen(payload: bytes) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = payload
    cm.__exit__.return_value = False
    return cm

def test_download_image(mocker, out_dir):
    from src.core.image.downloader import download_image
    mocker.patch("urllib.request.urlopen", return_value=_fake_urlopen(png_bytes))
    out = download_image("https://example.com/img.png", out_dir)
    assert out.exists()
```

Para erros de rede, use `side_effect=ConnectionError("...")` — o
downloader empacota qualquer `Exception` num `ValueError` com
mensagem "Falha ao baixar". Para HTML/404 (resposta válida mas não-imagem),
passe bytes de HTML como payload — `Image.open(io.BytesIO(html)).verify()`
levanta exceção e o downloader produz "URL não contém uma imagem válida".

### Mock com contagem de chamadas (`side_effect` com lista)

Para fazer `Image.open` falhar apenas na segunda chamada:
```python
from PIL import Image as PILImage
original = PILImage.open
n = {"count": 0}

def selective(path, *a, **kw):
    n["count"] += 1
    if n["count"] == 2:
        raise OSError("falha simulada")
    return original(path, *a, **kw)

mocker.patch("PIL.Image.open", side_effect=selective)
```

---

## Verificar cobertura de um módulo

```bash
# Cobertura de um módulo específico (usar pontos, não barras)
uv run pytest tests/core/audio/test_normalizer_unit.py \
    --cov=src.core.audio.normalizer --cov-report=term-missing

# Cobertura unitária apenas (rápido, sem ffmpeg)
uv run pytest -m "not integration" --cov=src --cov-report=term-missing

# Cobertura completa (unit + integration — requer ffmpeg)
uv run pytest --cov=src --cov-report=term-missing
```

O alvo é **≥ 90%** por módulo de `src/core/`. Estado atual:

| Módulo | Cobertura |
|---|---|
| `core/audio/normalizer.py` | **100%** |
| `core/audio/info.py` | **100%** |
| `core/ffmpeg.py` | **100%** |
| `core/video/converter.py` | **100%** |
| `core/document/info.py` | **100%** |
| `llm_utils.py` | **100%** |
| `core/image/downloader.py` | 98% |
| `core/audio/converter.py` | 96% |
| `core/document/converter.py` | 95% |
| `core/document/qr.py` | 95% |
| `core/document/processor.py` | 94% |
| `core/image/transform.py` | 94% |
| `core/image/info.py` | 94% |
| `core/video/info.py` | 93% |
| `core/image/converter.py` | 79% |
| `core/audio/denoiser.py` | 79% |
| `core/image/background.py` | 32% (extra `[ai-image]` — sem teste de uso real) |
| `core/image/describe.py` | 24% (vision LLM — sem teste de uso real) |
| `core/audio/downloader.py` | 20% (yt-dlp não mockado) |
| `core/video/downloader.py` | 18% (yt-dlp não mockado) |

Lacunas conhecidas: `audio/downloader.py` e `video/downloader.py` (yt-dlp);
`image/background.py` e `describe.py` (extras opcionais). Smoke tests
de lazy import seriam baratos mas ainda não foram escritos.

### pymupdf nos testes do módulo document — uso REAL via fixture

Os testes em `tests/core/document/` **não mockam pymupdf** — usam as
fixtures de sessão `sample_pdf` e `sample_pdf_with_images` (em
`conftest.py`), que geram PDFs reais em disco com
`pytest.importorskip("pymupdf")` no topo (skip elegante se a
dependência sumir).

Justificativa: `pymupdf` é dependência hard do projeto (não está num
extra opcional), e nenhum desses testes depende de ffmpeg/rede/GPU.
Portanto eles ficam corretamente marcados como `unit` e exercitam
o comportamento real de `merge_pdfs`, `split_pdf`, `compress_pdf`,
`pdf_to_images`, etc.

Se você precisar testar uma função document **sem** invocar
operações reais (caminho de erro, lazy imports, branches de
disponibilidade), mocke pontualmente via `mocker.patch.dict`:

```python
import sys
from unittest.mock import MagicMock

mocker.patch.dict("sys.modules", {"pymupdf": MagicMock()})
```

Para `qrcode` (mesmo padrão de lazy import em `qr.py`) o `test_qr.py`
também usa a biblioteca real — gera PNG em disco e valida o tamanho
da imagem com Pillow. Mockar só faz sentido para cobrir branches de
erro:

```python
mocker.patch.dict("sys.modules", {"qrcode": MagicMock(), "qrcode.constants": MagicMock()})
```

Linhas impossíveis de cobrir sem desinstalar dependências (ex.: `is_available()` no `denoiser.py` — branch `ImportError`) devem ser marcadas como `# pragma: no cover`.
