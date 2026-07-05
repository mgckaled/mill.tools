# Testing — mocks de mídia e binários

Receitas de mock para as fronteiras de mídia/binário: `subprocess`/ffmpeg, `WhisperModel`
(faster-whisper), `urllib`, `yt_dlp.YoutubeDL`, `PIL.Image.open` com contagem de chamadas, `pytesseract`
(OCR) e `pymupdf`/`qrcode`. Abra este arquivo ao escrever/consertar testes que tocam qualquer uma dessas
fronteiras. Padrões genéricos (`mocker` vs `monkeypatch`, isolamento de `settings`) ficam no `SKILL.md`.

---

## Mock de `subprocess.Popen` — para testar pipelines ffmpeg

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

**Cuidado com threading**: `_drain()` em `normalizer.py` lê `proc.stderr` em thread daemon. O iterador
deve ser thread-safe (um simples `iter([b"..."])` funciona). Para `proc.stdout` linhas de progresso,
incluir `b"out_time_us=N\n"` para testar o callback.

---

## Mock de `WhisperModel` (faster-whisper) — para testar `transcriber.transcribe`

`src/transcriber.py` instancia `WhisperModel(...)` e chama `model.transcribe(...)`, que retorna
`(segments, info)` onde `segments` é um **generator lazy** e cada `Segment` expõe
`.start/.end/.text/.avg_logprob/.no_speech_prob`. `info` expõe `.language/.language_probability/.duration`.

Para mockar sem carregar Whisper (RAM, CUDA, disco), use stand-ins duck-typed e patche o ponto de import:

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

- **Patche `src.transcriber.WhisperModel`, não `faster_whisper.WhisperModel`.** O
  `from faster_whisper import WhisperModel` no topo de `transcriber.py` vincula o símbolo localmente —
  só o ponto de uso responde ao patch.
- **`_resolve_device` precisa ser mockado também.** Sem isso, o teste tenta consultar
  `ctranslate2.get_supported_compute_types("cuda")` — em CI sem GPU funciona, mas é tempo gasto à toa.
- **Para `KeyboardInterrupt` no meio do loop**, use um generator que yielda e depois levanta:
  ```python
  def _raise_after_first():
      yield _Seg(0.0, 3.0, "primeiro")
      raise KeyboardInterrupt
  fake.transcribe.return_value = (_raise_after_first(), _Info())
  ```
  O teste valida com `pytest.raises(SystemExit)` (transcriber chama `sys.exit(0)` e remove o arquivo
  incompleto).
- **Para legendas** (`subtitle_formats=("srt","vtt")`), redirecione `src.utils.TRANSCRIPTIONS_SUBTITLES_DIR`
  via `monkeypatch.setattr` para `tmp_path` antes da chamada — o transcriber lê esse atributo lazy dentro
  do `if subtitle_formats and cues:`.

---

## Mock de `urllib.request.urlopen` — para testar download_image

`urlopen` é usado como context manager (`with urlopen(...) as resp`). Substituir por `@contextmanager`
quebra na **segunda chamada** porque generators são single-use. Use `MagicMock` (reusável):

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

Para erros de rede, use `side_effect=ConnectionError("...")` — o downloader empacota qualquer `Exception`
num `ValueError` com mensagem "Falha ao baixar". Para HTML/404 (resposta válida mas não-imagem), passe
bytes de HTML como payload — `Image.open(io.BytesIO(html)).verify()` levanta exceção e o downloader
produz "URL não contém uma imagem válida".

---

## Mock com contagem de chamadas (`side_effect` com lista)

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

## Mock de `pytesseract` (OCR) — `tests/core/document/test_ocr.py`

`core/document/ocr.py` é gateado por `is_available()` (extra `[ocr]` + binário Tesseract) e importa
`pytesseract` **lazy** dentro de `ocr_pdf`. Os testes unit não dependem da instalação real: mockam o
módulo via `sys.modules` e o resolvedor do binário.

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

- **Fluxo híbrido**: páginas com texto nativo (`sample_pdf`) **não** invocam `image_to_string`
  (assert `assert_not_called()`); páginas só-imagem (`sample_pdf_with_images`) caem no OCR. pymupdf/PIL
  rodam de verdade — só o `image_to_string` é mockado.
- **`word_count` inclui o cabeçalho** `--- Página N ---` (como `extract_text`); não asserte contagens
  exatas frágeis — use `>= N`.
- **`is_available()` False**: mockar `shutil.which → None` **e** `_WINDOWS_FALLBACKS → ()` (a máquina de
  dev tem o binário no local padrão, então o fallback acharia mesmo sem PATH).
- **Integration real**: 1 teste `@pytest.mark.integration` renderiza texto num PDF só-imagem e roda
  Tesseract de verdade; `pytest.skip` se `not ocr.is_available()`.

---

## Mock de `yt_dlp.YoutubeDL` — para testar montagem de `ydl_opts`/postprocessors

`core/audio/downloader.py` e `core/video/downloader.py` não têm teste de rede (custo/retorno ruim — ver
`SKILL.md`), mas a **montagem** de `postprocessors`/`ydl_opts` por `fmt`/flag é lógica pura e vale testar.
Substitua a classe inteira (não só `extract_info`) para capturar o dict de opções passado ao construtor:

```python
from pathlib import Path


class _FakeYDL:
    captured_opts: dict | None = None

    def __init__(self, opts):
        self.opts = opts
        _FakeYDL.captured_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        # Deriva tmp_dir do outtmpl já montado pela função — sem tocar rede — e larga
        # um arquivo fake lá, para o move/cleanup real do downloader seguir intacto.
        out_dir = Path(self.opts["outtmpl"]).parent
        fake_file = out_dir / "video.mp3"
        fake_file.write_bytes(b"fake-audio")
        return {"requested_downloads": [{"filepath": str(fake_file)}]}


def test_download_audio_fmt_best_skips_thumbnail(tmp_path, mocker):
    from src.core.audio.downloader import download_audio

    mocker.patch("yt_dlp.YoutubeDL", _FakeYDL)
    out = download_audio("https://example.com/watch", tmp_path, fmt="best")

    opts = _FakeYDL.captured_opts
    assert "EmbedThumbnail" not in [pp["key"] for pp in opts["postprocessors"]]
    assert out.exists()
```

`tempfile.mkdtemp`/`shutil.move`/`shutil.rmtree` do downloader rodam de verdade (I/O local, sem ffmpeg/rede) —
ainda qualifica como `unit`. Ver `tests/core/audio/test_downloader.py`.

---

## Mock de `pymupdf` / `qrcode` — para branches de erro

Os testes de `tests/core/document/` usam **pymupdf real** (ver a regra no `SKILL.md`). Mocke pontualmente
só para cobrir caminhos de erro, lazy imports ou branches de disponibilidade:

```python
import sys
from unittest.mock import MagicMock

mocker.patch.dict("sys.modules", {"pymupdf": MagicMock()})
```

Para `qrcode` (mesmo padrão de lazy import em `qr.py`), o `test_qr.py` também usa a biblioteca real —
gera PNG em disco e valida o tamanho com Pillow. Mockar só faz sentido para cobrir branches de erro:

```python
mocker.patch.dict("sys.modules", {"qrcode": MagicMock(), "qrcode.constants": MagicMock()})
```
