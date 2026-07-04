# Tier 0 — Lacunas óbvias nos módulos atuais

> Plano de implementação detalhado. **Fazer antes de qualquer módulo novo** (PR6+).
> São três frentes baratas e de alto valor que fecham buracos gritantes nos
> módulos que já existem:
>
> 1. **Legendas `.srt`/`.vtt`** na Transcrição (timestamps já existem) → e
>    **queimar/embutir legenda no vídeo** (une Vídeo × Transcrição).
> 2. **OCR (PR5.1)** — já no roadmap; desbloqueia PDF escaneado → texto → LLM.
> 3. **Cobrir `transcriber.py`** (31% → ~75%) mockando `WhisperModel`.
>
> Princípios mantidos: **torch-free**, **core puro reutilizável por CLI e GUI**,
> **código em inglês / labels em PT-BR**, **Flet 0.85**, **subprocess binário**.

---

## Visão geral e ordem de execução

| Fase | Entrega | Risco | Depende de |
|---|---|---|---|
| **T0.1** | `core/subtitles.py` (puro) + testes | nulo | — |
| **T0.2** | Legendas no `transcriber.transcribe()` + GUI + CLI **e** cobertura de `transcriber.py` | baixo | T0.1 |
| **T0.3** | OCR (PR5.1): `core/document/ocr.py` + card + worker + CLI + testes | médio (dep de sistema) | — |
| **T0.4** | Operação de legenda no Vídeo (mux/queima) + testes | médio (escape ffmpeg) | T0.1 (ideal) |

T0.1–T0.2 e T0.3 são independentes — podem ir em paralelo. T0.4 é a única que se
beneficia de já existir o PR6 (Biblioteca) para puxar o `.srt` facilmente, mas
funciona standalone via FilePicker.

---

## Parte A — Legendas `.srt` / `.vtt` (Transcrição)

### A.1 Por que é quase de graça

`transcriber.transcribe()` **já itera todos os segmentos** com `start`/`end`/`text`
(`faster-whisper` os fornece) e já emite `transcribe_segment` com esses campos.
Hoje esses dados são descartados após escrever o `.txt` corrido. Basta **coletar
as cues no loop existente** e serializar — sem reexecutar o modelo, sem custo de
GPU adicional.

### A.2 Core novo — `src/core/subtitles.py` (puro)

Módulo standalone em `core/` (como `core/ffmpeg.py`, `core/metadata.py`), sem
importar Flet nem faster-whisper. 100% determinístico → unit test trivial.

```python
"""Pure SRT/WebVTT serialization from transcription cues. No external deps."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    """One timed caption line."""
    index: int      # 1-based
    start: float    # seconds
    end: float      # seconds
    text: str


def _format_ts(seconds: float, *, sep: str) -> str:
    """Format seconds as HH:MM:SS<sep>mmm. sep=',' for SRT, '.' for VTT."""
    if seconds < 0:
        seconds = 0.0
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[SubtitleCue]) -> str:
    """Serialize cues to SubRip (.srt) text."""
    blocks = []
    for c in cues:
        blocks.append(
            f"{c.index}\n"
            f"{_format_ts(c.start, sep=',')} --> {_format_ts(c.end, sep=',')}\n"
            f"{c.text.strip()}\n"
        )
    return "\n".join(blocks)


def to_vtt(cues: list[SubtitleCue]) -> str:
    """Serialize cues to WebVTT (.vtt) text."""
    body = []
    for c in cues:
        body.append(
            f"{_format_ts(c.start, sep='.')} --> {_format_ts(c.end, sep='.')}\n"
            f"{c.text.strip()}\n"
        )
    return "WEBVTT\n\n" + "\n".join(body)


_SERIALIZERS = {"srt": to_srt, "vtt": to_vtt}


def write_subtitles(
    cues: list[SubtitleCue],
    out_stem: Path,
    formats: tuple[str, ...] = ("srt",),
) -> list[Path]:
    """Write the requested subtitle files next to out_stem; return their paths."""
    written: list[Path] = []
    for fmt in formats:
        serializer = _SERIALIZERS.get(fmt)
        if serializer is None:
            continue
        out_path = out_stem.with_suffix(f".{fmt}")
        out_path.write_text(serializer(cues), encoding="utf-8")
        written.append(out_path)
    return written
```

> Sem quebra de linha por largura no v1 — os segmentos do Whisper costumam ser
> curtos o bastante. Wrapping por `max_chars`/duas linhas fica como polimento.

### A.3 Integração em `transcriber.transcribe()`

Mudança **mínima e retrocompatível** (novo parâmetro com default vazio → saída
`.txt` e testes existentes inalterados):

```python
def transcribe(..., subtitle_formats: tuple[str, ...] = ()) -> float | None:
    ...
    cues: list[SubtitleCue] = []          # novo
    with output_path.open("w", encoding="utf-8") as f:
        f.write(header)
        for segment in segments:
            text = segment.text.strip()
            ...                            # lógica [?] inalterada
            if subtitle_formats:           # novo — coleta no mesmo loop
                cues.append(SubtitleCue(
                    index=segment_count + 1,
                    start=segment.start, end=segment.end, text=text,
                ))
            ...
    # após o loop:
    if subtitle_formats and cues:          # novo
        from src.core.subtitles import write_subtitles
        from src.utils import TRANSCRIPTIONS_SUBTITLES_DIR
        TRANSCRIPTIONS_SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
        sub_stem = TRANSCRIPTIONS_SUBTITLES_DIR / output_path.stem
        sub_paths = write_subtitles(cues, sub_stem, subtitle_formats)
        _emit("subtitles_done", {"paths": [str(p) for p in sub_paths]})
```

Nova constante em `src/utils.py`:

```python
TRANSCRIPTIONS_SUBTITLES_DIR = OUTPUT_DIR / "transcriptions" / "subtitles"
```

### A.4 Wire-up GUI (módulo Transcrição)

- **Form** (`src/gui/views/form_view.py`): adicionar um `switch_row("Exportar legendas (.srt + .vtt)", ...)` na seção de opções, com `help_icon_for`. Persistir em `settings` (`last_export_subtitles: bool`).
- **`PipelineArgs`** (`src/gui/workers.py`): novo campo `export_subtitles: bool = False`.
- **`run_pipeline`**: passar `subtitle_formats=("srt", "vtt") if args.export_subtitles else ()` para `transcriber.transcribe(...)`.
- **Resultado**: o `subtitles_done` aparece no log; o painel de resultados ganha um `output_card` por arquivo `.srt`/`.vtt` (reusa `output_card`). Com PR6, esses arquivos entram automaticamente na Biblioteca.

### A.5 Wire-up CLI

No parser legado de `transcribe` (`main.py`): `--srt` e `--vtt` (ou `--subtitles` agregando ambos). Repassar a tupla a `transcribe(subtitle_formats=...)`. Mantém a paridade CLI/GUI que o resto do projeto preza.

---

## Parte B — Cobertura de `transcriber.py` (31% → ~75%)

A skill `testing` já aponta: falta cobrir `transcribe()` mockando `WhisperModel`.
A infra de mock serve **simultaneamente** para validar as legendas da Parte A —
um teste, dois ganhos.

### B.1 Padrão de mock

```python
@pytest.mark.unit
def test_transcribe_writes_text_and_flags(tmp_path, mocker):
    from src import transcriber

    class _Seg:
        def __init__(self, start, end, text, lp=-0.2, ns=0.1):
            self.start, self.end, self.text = start, end, text
            self.avg_logprob, self.no_speech_prob = lp, ns

    class _Info:
        language = "pt"
        language_probability = 0.99
        duration = 6.0

    fake_model = mocker.MagicMock()
    fake_model.transcribe.return_value = (
        iter([
            _Seg(0.0, 3.0, "olá mundo"),
            _Seg(3.0, 6.0, "ruído", lp=-2.0),     # dispara [?] (avg_logprob < -1.0)
        ]),
        _Info(),
    )
    # Patch no ponto de USO (import em src.transcriber), não na faster_whisper
    mocker.patch("src.transcriber.WhisperModel", return_value=fake_model)
    mocker.patch("src.transcriber._resolve_device", return_value=("cpu", "int8"))

    out = tmp_path / "t.txt"
    transcriber.transcribe(
        audio_path=tmp_path / "a.mp3", output_path=out,
        meta={"title": "x", "duration": 6}, url="http://x",
        model_size="small", language="pt", threads=2, beam_size=1,
        force_overwrite=True,
    )
    body = out.read_text(encoding="utf-8")
    assert "olá mundo" in body
    assert "[?]" in body                  # segmento de baixa confiança marcado
```

Casos a cobrir (levam de 31% para ~75%):

- Escrita do header + corpo; marcação `[?]` por `avg_logprob < -1.0` **e** por `no_speech_prob > 0.6` (dois ramos).
- Emissão de eventos: `whisper_loading/loaded`, `language_detected`, `transcribe_segment` (N vezes), `transcribe_done` com `flagged_count`.
- **Legendas**: com `subtitle_formats=("srt","vtt")`, verificar que os arquivos são escritos e que `subtitles_done` é emitido — redirecionar `TRANSCRIPTIONS_SUBTITLES_DIR` via `monkeypatch.setattr` para `tmp_path` (padrão de isolamento da skill testing).
- Ramo `force_overwrite=False` + `output_path.exists()` → mockar `builtins.input` retornando `"n"` → retorna `None` sem transcrever.
- `KeyboardInterrupt` no meio → remove arquivo incompleto e `sys.exit(0)` (cobrir com `pytest.raises(SystemExit)` e `fake_model.transcribe.side_effect`/iterator que levanta).

Os timestamps de `core/subtitles.py` ganham seu próprio `tests/core/test_subtitles.py` (unit puro): `_format_ts` em `0.0`, `3661.5`, `59.999` (arredondamento para `01:00.000`); golden de `to_srt`/`to_vtt`; `write_subtitles` filtra formato desconhecido. Alvo ≥ 95%.

---

## Parte C — Legenda no vídeo (Vídeo × Transcrição)

Une os dois módulos: pegar o `.srt` da Transcrição e **embutir (mux)** ou
**queimar (hardcode)** no vídeo.

### C.1 Duas modalidades

| Modo | Comando ffmpeg | Custo | Quando |
|---|---|---|---|
| **soft / mux** (padrão) | `-i video -i subs.srt -c copy -c:s mov_text out.mp4` | **sem reencode** — rápido, leve na MX150 | legenda toggleável no player |
| **hard / burn** | `-vf subtitles=<arquivo> -c:a copy out.mp4` (libx264) | reencoda o vídeo (CPU) | legenda permanente (Shorts/Reels) |

Para `.mkv`, o stream de legenda usa `-c:s srt`; para `.mp4`, `mov_text`.

### C.2 Core novo — `src/core/video/converter.py::add_subtitles`

```python
def add_subtitles(
    src: Path,
    subtitle_path: Path,
    out_dir: Path,
    mode: str = "soft",                # "soft" (mux) | "hard" (burn)
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Mux (soft) or burn-in (hard) a subtitle file into a video via ffmpeg."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(src.stem)}_subbed.mp4"

    if mode == "hard":
        # IMPORTANTE (quirk Windows): o filtro `subtitles` interpreta `:` como
        # separador de argumentos — o `:` do drive (C:) precisaria de escape
        # frágil (`C\:\\...`). Mitigação: rodar o ffmpeg com cwd na pasta da
        # legenda e referenciá-la por BASENAME, eliminando o drive-letter colon.
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-vf", f"subtitles={subtitle_path.name}",
            "-c:v", "libx264", "-crf", "23", "-preset", "medium",
            "-c:a", "copy",
            "-progress", "pipe:1", "-nostats", str(out_path),
        ]
        cwd = subtitle_path.parent
    else:  # soft mux — sem reencode
        cmd = [
            "ffmpeg", "-y", "-i", str(src), "-i", str(subtitle_path),
            "-c", "copy", "-c:s", "mov_text",
            "-progress", "pipe:1", "-nostats", str(out_path),
        ]
        cwd = None

    total_secs = get_video_info(src).duration if progress_cb else None
    return run_ffmpeg(cmd, out_path, total_secs=total_secs, progress_cb=progress_cb, cwd=cwd)
```

> **Ação:** `run_ffmpeg` (`src/core/ffmpeg.py`) precisa aceitar/repassar `cwd` ao
> `subprocess.Popen` (hoje provavelmente não tem o parâmetro). Mudança pequena e
> retrocompatível (`cwd=None` default). Documentar o escape do filtro `subtitles`
> na seção de quirks Windows do `CLAUDE.md` (junto dos quirks de download que já
> estão lá).

### C.3 GUI — 8ª operação do módulo Vídeo

- Card `subtitle` no grid 3-colunas (hoje são 7 ops). `VideoArgs` ganha `subtitle_path: Path | None`, `subtitle_mode: str = "soft"`.
- Bloco condicional: FilePicker para `.srt`/`.vtt` + `segmented_selector("Embutir | Queimar")`.
- `pipeline_log.py` do vídeo: nova operação `subtitle` em `OP_VERBS`/`OP_LABELS`; worker chama `add_subtitles`.
- **Bridge:** no painel de resultados da Transcrição, botão "Embutir no vídeo" só aparece quando há `.srt` — `nav[0]("video", {"file": <video?>, "subtitle": <srt>})`. Como a Transcrição normalmente só tem o áudio, o caminho principal é o usuário escolher vídeo + legenda no módulo Vídeo (ou puxar ambos da Biblioteca/PR6). Por isso T0.4 fica **melhor depois do PR6**, mas não bloqueia.

### C.4 Testes (integração — requer ffmpeg)

Em `tests/core/video/test_converter.py` (já é `integration`): gerar um `.srt`
mínimo em `tmp_path`, rodar `add_subtitles(sample_mp4, srt, mode="soft")` e
`mode="hard"`, assert `out.exists()` e `size > 1000`. O modo `hard` valida o
caminho `cwd`+basename.

---

## Parte D — OCR (PR5.1) — PDF escaneado → texto → LLM

Já especificado no `CLAUDE.md` (extra `[ocr]` com `pytesseract>=0.3` já no
`pyproject`; Tesseract no PATH; card desabilitado com tooltip — padrão
`_UNAVAILABLE` do módulo Imagens). Detalhamento abaixo.

### D.1 Core novo — `src/core/document/ocr.py`

Espelha o padrão de `core/image/background.py` (lazy import + `is_available`) e a
assinatura de `extract_text` (retorna `(Path, int)`).

```python
"""OCR for scanned PDFs via pytesseract. Optional extra [ocr] + Tesseract on PATH."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from src.utils import sanitize_filename

# por = Portuguese, eng = English. Combine with '+': "por+eng".
LANGS = ("por", "eng", "por+eng", "spa")


def is_available() -> bool:
    """True if pytesseract is importable AND the tesseract binary is on PATH."""
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
        return True
    except ImportError:
        return False


def ocr_pdf(
    path: Path,
    output_dir: Path,
    lang: str = "por",
    dpi: int = 300,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[Path, int]:
    """Hybrid extraction: native text per page; OCR fallback for image-only pages.

    For each page: use the embedded text layer if present; otherwise rasterize at
    `dpi` (300 is Tesseract's clean-OCR floor) and run pytesseract. Writes a .txt
    and returns (path, word_count).
    """
    import pymupdf  # hard dep
    import pytesseract
    from PIL import Image
    import io

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))
    total = doc.page_count
    parts: list[str] = []

    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if not text:  # scanned/image-only page → OCR
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang=lang).strip()
        if text:
            parts.append(f"\n\n--- Página {i + 1} ---\n\n{text}")
        if progress_cb:
            progress_cb(i + 1, total)

    doc.close()
    full_text = "".join(parts).strip()
    word_count = len(full_text.split()) if full_text else 0
    out_path = output_dir / f"{sanitize_filename(path.stem)}_ocr.txt"
    out_path.write_text(full_text, encoding="utf-8")
    return out_path, word_count
```

> Alternativa nativa: o pymupdf tem `page.get_textpage_ocr()` (Tesseract via
> `TESSDATA_PREFIX`). Mantenho `pytesseract` por já estar no `pyproject` e dar
> controle direto de `lang`/`dpi`. O fluxo híbrido (texto nativo → OCR só onde
> falta) evita reprocessar páginas que já têm camada de texto.

### D.2 `DocumentArgs` + worker + pipeline_log

- `DocumentArgs`: `ocr_lang: str = "por"`, `ocr_dpi: int = 300`. (`operation = "ocr"`)
- `worker.py` do documento: ramo `ocr` chama `ocr.ocr_pdf(...)`, emite `document_op_done` com `extra_stats={"word_count": n}`.
- `pipeline_log.py`: adicionar `ocr` em `OP_VERBS`/`OP_LABELS` (verbo "Reconhecendo texto", label "OCR").
- Saída no painel: Mode 3 (texto) do visor de documentos (igual a `extract`).

### D.3 GUI — habilitar o card `ocr` (padrão `_UNAVAILABLE`)

Reusar exatamente o padrão de `image/blocks/ai.py`:

```python
from src.core.document.ocr import is_available as _ocr_ok, LANGS

ocr_available = _ocr_ok()

ocr_warning = ft.Text(
    "⚠ Tesseract não encontrado.\nInstale o Tesseract (PATH) e rode: uv sync --extra ocr",
    color=ft.Colors.ERROR, size=Type.small.size, visible=not ocr_available,
)
# card 'ocr' do grid: disabled=not ocr_available + tooltip;
# bloco com Dropdown de idioma (por/eng/por+eng/spa) + slider/seg de DPI (150/300).
```

O card `ocr` já está "reservado" no módulo Documentos — aqui ele deixa de ser
placeholder e passa a desabilitar-se graciosamente quando o Tesseract não está
instalado, em vez de sumir.

### D.4 CLI

`document ocr <pdf> --lang por --dpi 300` (sub-subparser, kebab→snake já tratado).
Diferente do `analyze` (que é só-GUI), o `ocr` **entra na CLI** — é determinístico
e sem LLM.

### D.5 Dependências de sistema

- Extra Python: `uv sync --extra ocr` (já declarado: `pytesseract>=0.3`).
- Binário: **Tesseract no PATH** + language packs (`por.traineddata`, `eng.traineddata`).
  Tratar como o ffmpeg/yt-dlp: documentar no README e checar via `is_available()`
  (não derrubar o app — só desabilitar o card).

### D.6 Testes

- `is_available()`: mockar `shutil.which` (None → False) e o import (`mocker.patch.dict("sys.modules", {"pytesseract": MagicMock()})`).
- `ocr_pdf` caminho **texto nativo**: usar fixture `sample_pdf` (tem texto) → não invoca Tesseract → `word_count > 0`. Unit.
- `ocr_pdf` caminho **OCR**: mockar `pytesseract.image_to_string` retornando `"texto ocr"` e usar um PDF só-imagem (gerar via fixture com `images_to_pdf` de um PNG) → cobre o ramo sem exigir Tesseract no CI. Unit.
- E2E real com Tesseract instalado → marcar `integration` (skip se binário ausente, como o hook de ffmpeg).

### D.7 O ciclo que isso fecha

Depois do OCR, a operação `analyze` (documento) já existente roda sobre o `.txt`
gerado: **PDF escaneado → OCR → texto → LLM**. É exatamente a ponte
"processar → extrair → raciocinar" que o roadmap descreve, agora também para
documentos digitalizados.

---

## Arquivos tocados (resumo)

**Novos:**

```
src/core/subtitles.py                    + (Parte A)
src/core/document/ocr.py                 + (Parte D)
tests/core/test_subtitles.py             +
tests/core/document/test_ocr.py          +
```

**Alterados:**

```
src/transcriber.py                       (subtitle_formats + coleta de cues)
src/utils.py                             (TRANSCRIPTIONS_SUBTITLES_DIR)
src/gui/workers.py                       (PipelineArgs.export_subtitles)
src/gui/views/form_view.py               (switch "Exportar legendas")
src/gui/settings.py                      (last_export_subtitles)
main.py                                  (--srt/--vtt; document ocr)
src/core/ffmpeg.py                       (run_ffmpeg aceita cwd=)
src/core/video/converter.py              (add_subtitles)
src/core/video/args.py                   (subtitle_path, subtitle_mode)
src/gui/modules/video/{form_view,worker,pipeline_log}.py  (op subtitle)
src/core/document/args.py                (ocr_lang, ocr_dpi)
src/gui/modules/document/{form_view,worker,pipeline_log}.py + blocks/ocr_block.py
src/cli/{video,document}.py              (subcomandos)
tests/test_transcriber.py                (mock WhisperModel → 31%→~75%)
tests/core/video/test_converter.py       (add_subtitles)
CLAUDE.md / README.md / skills           (docs)
```

**Dependências novas:** nenhuma (Tesseract é binário de sistema opcional; `pytesseract` já está no extra `[ocr]`).

---

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Escape do filtro `subtitles` no Windows (`C:` → `C\:`) | Rodar ffmpeg com `cwd` na pasta da legenda + basename; documentar no quirks. |
| Retrocompatibilidade da Transcrição | `subtitle_formats=()` default → `.txt` e testes atuais inalterados. |
| Tesseract é dep pesada de sistema + language packs | `is_available()` gateia; card desabilita graciosamente; opcional via extra `[ocr]`. |
| OCR a 300 DPI lento no i5-8265U (PDF longo) | `progress_cb` por página; permitir DPI 150; fila sequencial; só OCR onde falta texto. |
| Segmentos do Whisper longos para legenda | Aceitável no v1 (cue = segmento). Wrapping/`max_chars` fica para polimento. |
| Contenção GPU (Whisper + ffmpeg burn-in) | Burn-in é CPU (libx264); não rodar simultâneo à transcrição — fila já é sequencial. |

---

## Definição de pronto (DoD)

- `uv run pytest -m unit` verde; `core/subtitles.py` ≥ 95%, `transcriber.py` ≥ 70%, `core/document/ocr.py` ≥ 85% (ramos sem Tesseract).
- Ruff limpo; docstrings/logs em inglês; labels PT-BR.
- Transcrição exporta `.srt`/`.vtt` (GUI switch + CLI flags); arquivos aparecem no painel de resultados.
- Vídeo embute/queima legenda (mux e burn) sem `WinError 32` no Windows.
- Card OCR habilita-se quando Tesseract presente; desabilita com aviso quando ausente; `document ocr` na CLI funciona.
- `analyze` roda sobre o `.txt` do OCR (loop PDF escaneado → LLM validado).
- Sem dependência nova obrigatória; projeto permanece torch-free.
- `CLAUDE.md`/`README`/skills atualizados (nova op de vídeo, OCR PR5.1 concluído, legendas, contagem de testes).

---

## Apêndice — Pontos validados nesta análise

- **ffmpeg burn-in**: filtro `-vf "subtitles=arquivo.srt"` reencoda; no Windows o
  `:` do drive quebra o parser de filtro → mitigado com `cwd`+basename. Mux soft
  via `-c copy -c:s mov_text` (mp4) não reencoda.
- **OCR híbrido**: pymupdf `page.get_text()`; se vazio, `get_pixmap(dpi=300)` →
  PIL → `pytesseract.image_to_string(img, lang=...)`. **300 DPI é o piso** para OCR
  limpo (Tesseract foi treinado em scans de 300 DPI); abaixo disso a acurácia cai.
- **`lang`** mapeia para os language packs do Tesseract (`por`, `eng`, `por+eng`).
- **Cobertura de `transcriber.py`**: mock de `WhisperModel` no ponto de import
  (`src.transcriber.WhisperModel`) com `.transcribe()` retornando
  `(iter([segmentos_fake]), info_fake)` — leva de 31% a ~75% e de quebra valida as
  legendas.
