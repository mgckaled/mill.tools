---
name: testing
description: Guia para adicionar, corrigir e revisar testes (unitários e de integração) do projeto mill.tools. Invocar quando: escrever novos testes, investigar expected values errados, aumentar cobertura de um módulo, mockar subprocess/ctranslate2/PIL.Image.open/llm_factory/settings/pymupdf/qrcode/urllib/LangChain (GenericFakeChatModel), ou entender por que um teste falha. Também use ao criar fixtures novas (session-scoped ou function-scoped), adicionar testes de integração com ffmpeg, revisar tests/core/ e tests/gui/, ou ajustar config dos plugins (pytest-xdist, pytest-timeout, pytest-clarity, pytest-randomly).
---

# mill.tools — Guia de Testes

## Estrutura de arquivos

```
tests/
├── conftest.py                              # fixtures globais — NÃO duplicar aqui
├── test_utils.py                            # src/utils.py
├── test_transcriber.py                      # src/transcriber.py — transcribe() via WhisperModel mock + legendas
├── test_llm_factory.py                      # src/llm_factory.py
├── test_llm_utils.py                        # src/llm_utils.py — split_text, bypass Gemini
├── test_formatter.py                        # src/formatter.py — paragraph formatting (GenericFakeChatModel)
├── test_analyzer.py                         # src/analyzer.py — structured analysis + merge + translation
├── test_prompter.py                         # src/prompter.py — condensed digest + merge
├── cli/
│   ├── __init__.py
│   ├── test_transcription.py               # unit — resolve_input, build_output_stem, item_label
│   ├── test_audio_cli.py                   # unit — add_audio_parser + run_audio_cli (dispatch)
│   ├── test_video_cli.py                   # unit — sub-subparsers + run_video_cli (dispatch)
│   ├── test_image_cli.py                   # unit — sub-subparsers + run_image_cli (dispatch)
│   ├── test_document_cli.py                # unit — sub-subparsers + run_document_cli (dispatch)
│   ├── test_library_cli.py                 # unit — parser + _parse_since + run_library_cli (scan_library mockado, capsys)
│   ├── test_transcribe_main.py             # unit — main.parse_args + _subtitle_formats_from_args
│   └── test_bus.py                         # unit — CLIEventBus (eventos e formatação)
├── core/
│   ├── __init__.py
│   ├── test_ffmpeg.py                      # unit — run_ffmpeg (subprocess mockado)
│   ├── test_metadata.py                    # unit — format_duration e helpers de metadata
│   ├── test_subtitles.py                   # unit — SubtitleCue + to_srt + to_vtt + write_subtitles
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
│   │   └── test_converter.py               # integration — convert/trim/compress/resize/extract_audio/thumbnail/add_subtitles
│   └── document/
│       ├── test_processor.py               # unit — merge/split/compress/rotate/watermark/stamp/encrypt (pymupdf REAL via sample_pdf)
│       ├── test_converter.py               # unit — pdf_to_images, images_to_pdf, extract_text (pymupdf REAL)
│       ├── test_info.py                    # unit — get_pdf_info, PdfInfo (pymupdf REAL)
│       ├── test_ocr.py                     # unit — ocr_pdf híbrido (pytesseract mockado) + 1 integration real (Tesseract)
│       └── test_qr.py                      # unit — generate_qr (qrcode REAL — gera PNG em disco)
│   └── library/
│       ├── test_scanner.py                 # unit — classify_path, scan_library (árvore falsa), filter_items (kind/category/query/since), sort_items
│       └── test_thumbnails.py              # unit — thumbnail_for (imagem/PDF reais, fallbacks None) + 1 integration (frame de vídeo)
└── gui/
    ├── __init__.py
    ├── test_settings.py                    # unit — src/gui/settings.py
    └── modules/
        ├── audio/test_pipeline_log.py      # unit — resolve_*, fmt_* (download/convert/extract/denoise/normalize)
        ├── image/test_pipeline_log.py      # unit — resolve_*, fmt_* (13 operações)
        ├── video/test_pipeline_log.py      # unit — resolve_*, fmt_* (8 operações, inclui subtitle)
        └── document/test_pipeline_log.py   # unit — resolve_messages, resolve_stage_label, fmt_* builders (13 operações, inclui ocr)
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

### Mock de LangChain (`GenericFakeChatModel`) — para analyzer/formatter/prompter

Os módulos `src/analyzer.py`, `src/formatter.py` e `src/prompter.py` usam
o padrão `chain = ANY_PROMPT | llm` seguido de `chain.invoke({"text": ...})`.
**Não** use `MagicMock` direto — `RunnableSequence` valida que o operando
direito do `|` seja um `Runnable`, e MagicMock falha nessa checagem.

Use `GenericFakeChatModel` de `langchain_core.language_models.fake_chat_models`:
é um `Runnable` real que retorna respostas determinísticas a partir de um
iterador de `AIMessage`.

```python
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


def _fake_llm(*responses: str):
    return GenericFakeChatModel(messages=iter([AIMessage(content=r) for r in responses]))


def test_format_transcription(tmp_path, mocker):
    from src import formatter
    src = tmp_path / "t.txt"
    src.write_text(_HEADER + "\n\nhello.", encoding="utf-8")
    mocker.patch.object(
        formatter, "make_llm",
        return_value=_fake_llm("formatted content"),
    )
    out = formatter.format_transcription(src)
    assert "formatted content" in out
```

Para o analyzer, que chama `make_llm` **duas vezes** (uma para análise
em T=0.4, outra para detecção de idioma em T=0), use `side_effect=[fake1, fake2]`:

```python
mocker.patch.object(
    analyzer, "make_llm",
    side_effect=[
        _fake_llm(json.dumps(analysis_dict, ensure_ascii=False)),   # análise (1ª chamada)
        _fake_llm("pt"),                                            # detecção (2ª chamada)
    ],
)
```

Quando o fluxo precisa de N respostas em sequência (multi-chunk + merge),
empilhe-as na mesma fake e o iterador interno avança a cada `.invoke()`:

```python
_fake_llm(*([partial_json] * n_chunks), merged_json)
```

**Gotcha**: a `GenericFakeChatModel` levanta `StopIteration` se a chain
chamar `.invoke()` mais vezes que o número de mensagens fornecidas. Isso é
útil — falha imediata se você previu errado quantas chamadas o código faz
(ex.: esquecer que single-chunk **não** invoca o merge).

**Isolation de output dirs**: redirecione `TRANSCRIPTIONS_DIGEST_DIR` ou
`TRANSCRIPTIONS_ANALYSIS_DIR` via `monkeypatch.setattr(mod, "ATTR", tmp_path)`
no nível do módulo — esses atributos são lidos só dentro de `analyze()` /
`build_prompt_ready()`, então um fixture autouse não é necessário.

### Mock de `WhisperModel` (faster-whisper) — para testar `transcriber.transcribe`

`src/transcriber.py` instancia `WhisperModel(...)` e chama
`model.transcribe(...)`, que retorna `(segments, info)` onde
`segments` é um **generator lazy** e cada `Segment` expõe
`.start/.end/.text/.avg_logprob/.no_speech_prob`. `info` expõe
`.language/.language_probability/.duration`.

Para mockar sem carregar Whisper (RAM, CUDA, disco), use stand-ins
duck-typed e patche o ponto de import:

```python
class _Seg:
    """Minimal Segment stand-in matching the faster-whisper API surface used."""
    def __init__(self, start, end, text, avg_logprob=-0.2, no_speech_prob=0.1):
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


class _Info:
    def __init__(self, language="pt", language_probability=0.99, duration=6.0):
        self.language = language
        self.language_probability = language_probability
        self.duration = duration


def _patch_whisper(mocker, segments, info=None):
    """Patcha WhisperModel + _resolve_device (evita lookup de GPU)."""
    fake = mocker.MagicMock()
    # IMPORTANTE: iter() — faster-whisper retorna generator, não list.
    # Usar list direto faria o teste passar mas mascara bugs de consumo lazy.
    fake.transcribe.return_value = (iter(segments), info or _Info())
    mocker.patch("src.transcriber.WhisperModel", return_value=fake)
    mocker.patch("src.transcriber._resolve_device", return_value=("cpu", "int8"))
    return fake


@pytest.mark.unit
def test_transcribe_flags_low_logprob(tmp_path, mocker):
    from src.transcriber import transcribe
    _patch_whisper(mocker, [
        _Seg(0.0, 3.0, "ok"),
        _Seg(3.0, 6.0, "ruim", avg_logprob=-2.0),   # < -1.0 → dispara [?]
    ])
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"")
    out = tmp_path / "o.txt"
    transcribe(audio_path=audio, output_path=out, meta={"title":"x","duration":6},
               url="x", model_size="small", language="pt",
               threads=2, beam_size=1, force_overwrite=True)
    assert "ruim [?]" in out.read_text(encoding="utf-8")
```

Gotchas específicos:

- **Patche `src.transcriber.WhisperModel`, não `faster_whisper.WhisperModel`.**
  O `from faster_whisper import WhisperModel` no topo de `transcriber.py`
  vincula o símbolo localmente — só o ponto de uso responde ao patch.
- **`_resolve_device` precisa ser mockado também.** Sem isso, o teste
  tenta consultar `ctranslate2.get_supported_compute_types("cuda")` —
  em CI sem GPU funciona, mas é tempo gasto à toa.
- **Para `KeyboardInterrupt` no meio do loop**, use um generator que
  yielda e depois levanta:
  ```python
  def _raise_after_first():
      yield _Seg(0.0, 3.0, "primeiro")
      raise KeyboardInterrupt
  fake.transcribe.return_value = (_raise_after_first(), _Info())
  ```
  O teste valida com `pytest.raises(SystemExit)` (transcriber chama
  `sys.exit(0)` e remove o arquivo incompleto).
- **Para legendas** (`subtitle_formats=("srt","vtt")`), redirecione
  `src.utils.TRANSCRIPTIONS_SUBTITLES_DIR` via `monkeypatch.setattr`
  para `tmp_path` antes da chamada — o transcriber lê esse atributo
  lazy dentro do `if subtitle_formats and cues:`.

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

O alvo é **≥ 90%** por módulo. Total agregado: **88%** com branch. Estado atual:

| Módulo | Cobertura (com branch) |
|---|---|
| `formatter.py` | **100%** |
| `prompter.py` | **100%** |
| `llm_utils.py` | **100%** |
| `core/subtitles.py` | **100%** |
| `core/audio/normalizer.py` | **100%** |
| `core/audio/info.py` | **100%** |
| `core/ffmpeg.py` | **100%** |
| `core/library/types.py` | **100%** |
| `core/library/thumbnails.py` | **100%** |
| `analyzer.py` | 99% |
| `cli/document.py` | 98% |
| `core/library/scanner.py` | 98% |
| `transcriber.py` | 97% |
| `core/video/converter.py` | 97% (2 partial branches) |
| `cli/video.py` | 97% |
| `core/document/info.py` | 94% (render_first_page_png: except interno) |
| `cli/library.py` | ~93% |
| `core/document/ocr.py` | 97% (2 partial branches) |
| `core/image/downloader.py` | 96% |
| `cli/image.py` | 94% |
| `core/audio/converter.py` | 93% |
| `core/document/converter.py` | 91% |
| `core/image/transform.py` | 91% |
| `core/document/processor.py` | 91% |
| `core/document/qr.py` | 90% |
| `core/image/info.py` | 89% |
| `cli/bus.py` | 82% |
| `utils.py` | 82% |
| `llm_factory.py` | 81% |
| `core/audio/denoiser.py` | 80% |
| `core/metadata.py` | 76% |
| `core/image/converter.py` | 71% |
| `core/image/background.py` | 32% (extra `[ai-image]` — sem teste de uso real) |
| `core/image/describe.py` | 23% (vision LLM — sem teste de uso real) |
| `core/audio/downloader.py` | 14% (yt-dlp não mockado) |
| `core/video/downloader.py` | 12% (yt-dlp não mockado) |

Lacunas conhecidas e justificáveis:
- `audio/downloader.py` + `video/downloader.py` — yt-dlp tem valor real em E2E (que não fazemos). Smoke test de mock daria <40%, retorno pequeno.
- `image/background.py` + `image/describe.py` — extras opcionais `[ai-image]`. Smoke tests de lazy import seriam baratos mas ainda não escritos.

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

### Mock de `pytesseract` (OCR) — `tests/core/document/test_ocr.py`

`core/document/ocr.py` é gateado por `is_available()` (extra `[ocr]` +
binário Tesseract) e importa `pytesseract` **lazy** dentro de `ocr_pdf`.
Os testes unit não dependem da instalação real: mockam o módulo via
`sys.modules` e o resolvedor do binário.

```python
import sys
from unittest.mock import MagicMock

def _patch_tesseract(mocker, ocr_text="texto reconhecido"):
    fake = MagicMock()
    fake.image_to_string.return_value = ocr_text
    mocker.patch.dict(sys.modules, {"pytesseract": fake})
    mocker.patch("src.core.document.ocr._resolve_tesseract_cmd", return_value="tesseract")
    return fake
```

Gotchas:

- **Fluxo híbrido**: páginas com texto nativo (`sample_pdf`) **não**
  invocam `image_to_string` (assert `assert_not_called()`); páginas só-imagem
  (`sample_pdf_with_images`) caem no OCR. pymupdf/PIL rodam de verdade —
  só o `image_to_string` é mockado.
- **`word_count` inclui o cabeçalho** `--- Página N ---` (como `extract_text`);
  não asserte contagens exatas frágeis — use `>= N`.
- **`is_available()` False**: mockar `shutil.which → None` **e**
  `_WINDOWS_FALLBACKS → ()` (a máquina de dev tem o binário no local padrão,
  então o fallback acharia mesmo sem PATH).
- **Integration real**: 1 teste `@pytest.mark.integration` renderiza texto
  num PDF só-imagem e roda Tesseract de verdade; `pytest.skip` se
  `not ocr.is_available()`.
