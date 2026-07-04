# MILL PR5 — Módulo Documentos

**Status:** planejado  
**Dependência:** PR4 ✅ (Vídeo concluído)  
**Skills de referência:** `design-system`, `cli`, `testing`

---

## Visão geral

Quinto módulo da GUI mill.tools. Foco em manipulação de PDFs para uso pessoal e administrativo — tudo local, sem dependência de nuvem, torch-free, CPU-only.

O módulo segue a mesma arquitetura dos módulos existentes (Áudio, Vídeo, Imagens): operações selecionadas via card grid, pipeline em thread daemon, log em tempo real, visor de resultado e bridge para outros módulos.

**Diferencial em relação aos outros módulos:** o visor de resultado é *adaptativo* — muda de modo conforme a operação, pois PDFs não têm comparação pixel a pixel natural como imagens.

---

## Dependências novas

```toml
# pyproject.toml — adicionar em [project.dependencies]
pymupdf >= 1.24       # core: merge/split/compress/rotate/watermark/stamp/encrypt/rasterize/extract
qrcode >= 7.4         # geração de QR code (sem deps pesadas)

# [project.optional-dependencies]
[project.optional-dependencies.ocr]
pytesseract >= 0.3    # extra [ocr] — requer tesseract.exe no PATH (PR5.1)
```

`pymupdf` é uma biblioteca Python pura instalada via `uv sync` — não é binário externo. Logo, todos os testes do módulo são `@pytest.mark.unit` (sem skip automático em CI).

`qrcode` depende somente de `Pillow`, que já está no projeto.

Tesseract (OCR) fica como PR5.1 — não bloqueia o lançamento do PR5 base.

---

## Estrutura de arquivos

```
src/
├── core/
│   └── document/
│       ├── __init__.py
│       ├── args.py          — DocumentArgs dataclass
│       ├── processor.py     — merge, split, compress, rotate, watermark, stamp, encrypt
│       ├── converter.py     — pdf_to_images, images_to_pdf, extract_text
│       ├── qr.py            — generate_qr()
│       └── info.py          — PdfInfo dataclass + get_pdf_info()
├── cli/
│   └── document.py          — add_document_parser() + run_document_cli()
└── gui/
    └── modules/
        └── document/
            ├── __init__.py
            ├── form_view.py — build_document_form_view() → (ft.Column, DocumentFormRefs)
            ├── worker.py    — run_document_pipeline()
            ├── view.py      — build_document_view() → Module
            ├── pipeline_log.py
            └── blocks/
                ├── __init__.py
                ├── merge_block.py
                ├── split_block.py
                ├── compress_block.py
                ├── rotate_block.py
                ├── watermark_block.py
                ├── stamp_block.py
                ├── encrypt_block.py
                ├── pdf_to_images_block.py
                ├── images_to_pdf_block.py
                ├── extract_text_block.py
                ├── analyze_block.py
                └── qr_block.py

tests/
├── core/
│   └── document/
│       ├── __init__.py
│       ├── test_processor.py
│       ├── test_converter.py
│       ├── test_info.py
│       └── test_qr.py
├── cli/
│   └── test_document_cli.py
└── gui/
    └── modules/
        └── document/
            └── test_pipeline_log.py
```

Saída em `output/document/source/` (inputs copiados) e `output/document/processed/` (resultados).

---

## Fase 1 — Core (`src/core/document/`)

### `args.py` — DocumentArgs

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocumentArgs:
    # --- input / output ---
    input_paths: list[Path] = field(default_factory=list)
    operation: str = "merge"          # ver lista de operações abaixo
    output_dir: Path = Path("output/document/processed")

    # --- split ---
    pages: str = ""                   # ex.: "1-3,5,8-"  (1-indexed, incluso)

    # --- compress ---
    image_quality: int = 75           # 50–95

    # --- rotate ---
    angle: int = 90                   # 90 | 180 | 270
    rotate_pages: str = "all"         # "all" ou "1,3,5"

    # --- watermark ---
    watermark_text: str = ""
    watermark_opacity: float = 0.3    # 0.1–0.9
    watermark_position: str = "center"  # center | top | bottom

    # --- stamp ---
    stamp_text: str = "RASCUNHO"      # PAGO | RASCUNHO | CONFIDENCIAL | custom

    # --- encrypt ---
    password: str = ""

    # --- pdf_to_images ---
    image_fmt: str = "jpg"            # jpg | png
    dpi: int = 150                    # 72 | 96 | 150 | 300

    # --- qr ---
    qr_data: str = ""
    qr_size: int = 300                # px
    qr_fmt: str = "png"               # png | jpg | svg

    # --- analyze ---
    analyze_model: str = "qwen7b-custom"  # qwen7b-custom | gemini-2.5-flash
```

**Operações válidas:**
`merge`, `split`, `compress`, `rotate`, `watermark`, `stamp`, `encrypt`,
`pdf_to_images`, `images_to_pdf`, `extract_text`, `analyze`, `qr`

---

### `info.py` — PdfInfo + get_pdf_info()

```python
@dataclass
class PdfInfo:
    page_count: int
    file_size_bytes: int
    title: str
    author: str
    has_text: bool          # False = PDF escaneado (sem texto embutido)
    first_page_thumb: bytes | None  # PNG bytes ~72dpi para o visor

def get_pdf_info(path: Path) -> PdfInfo: ...
```

`first_page_thumb` é gerado com `fitz.Matrix(1.0, 1.0)` (~72 dpi) — leve, apenas para preview.
`has_text` verifica se `page.get_text().strip()` retorna conteúdo em pelo menos uma página.

---

### `processor.py` — Funções de manipulação

Todas as funções retornam `Path` (exceto `split_pdf` que retorna `list[Path]`).

```python
def merge_pdfs(paths: list[Path], output_dir: Path) -> Path
def split_pdf(path: Path, pages: str, output_dir: Path) -> list[Path]
def compress_pdf(path: Path, output_dir: Path, image_quality: int = 75) -> Path
def rotate_pdf(path: Path, output_dir: Path, angle: int = 90, pages: str = "all") -> Path
def watermark_pdf(path: Path, output_dir: Path, text: str, opacity: float = 0.3,
                  position: str = "center") -> Path
def stamp_pdf(path: Path, output_dir: Path, text: str) -> Path
def encrypt_pdf(path: Path, output_dir: Path, password: str) -> Path
```

**Helper interno — `_parse_page_ranges(spec: str, total: int) -> list[int]`**

Converte notação humana para índices 0-based do pymupdf:

| Entrada   | total=10 | Saída (0-indexed) |
| --------- | -------- | ----------------- |
| `"1-3"`   | 10       | `[0, 1, 2]`       |
| `"1-3,5"` | 10       | `[0, 1, 2, 4]`    |
| `"8-"`    | 10       | `[7, 8, 9]`       |
| `"all"`   | 10       | `[0..9]`          |
| `"2"`     | 10       | `[1]`             |

Validações: índice fora do range levanta `ValueError` com mensagem descritiva.

**Marca d'água vs Carimbo:**
- `watermark_pdf` — texto diagonal, opacidade configurável, fonte pequena, toda a página
- `stamp_pdf` — texto grande centralizado, sem opacidade, fonte bold, visual de carimbo

Ambos usam `page.insert_text()` ou `page.draw_rect()` + `page.insert_text()` do pymupdf.

---

### `converter.py` — Conversão de formato

```python
def pdf_to_images(path: Path, output_dir: Path,
                  fmt: str = "jpg", dpi: int = 150,
                  progress_cb: Callable[[int, int], None] | None = None) -> list[Path]

def images_to_pdf(paths: list[Path], output_dir: Path,
                  output_name: str = "") -> Path

def extract_text(path: Path, output_dir: Path) -> tuple[Path, int]
# retorna (txt_path, word_count)
```

`pdf_to_images` aceita `progress_cb(current_page, total_pages)` — usado pelo worker para emitir `mutable=True` no log.

`images_to_pdf` usa `Pillow.save(..., "PDF", save_all=True, append_images=[...])` — já disponível no projeto.

`extract_text` usa `fitz.open().get_text("text")` por página, concatenando com separadores de página (`\n\n--- Página N ---\n\n`).

---

### `qr.py` — Geração de QR Code

```python
def generate_qr(data: str, output_dir: Path,
                size: int = 300, fmt: str = "png") -> Path
```

Usa `qrcode.make(data)` com `box_size` calculado para atingir `size` px.
Salva com `sanitize_filename()` derivado dos primeiros 30 chars de `data`.

---

## Fase 2 — Testes (`tests/core/document/` + `tests/cli/` + `tests/gui/`)

> Referência: skill `testing` — todos os testes são `@pytest.mark.unit`.
> pymupdf é dependência Python (não binário externo) → sem skip automático.

### Fixtures novas em `tests/conftest.py`

Adicionar ao bloco de fixtures session-scoped:

```python
@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory):
    """3-page PDF with extractable text — generated via pymupdf."""
    import fitz
    tmp = tmp_path_factory.mktemp("pdfs")
    path = tmp / "sample.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}\nTest content for extraction.")
    doc.save(str(path))
    doc.close()
    return path

@pytest.fixture(scope="session")
def sample_pdf_with_images(tmp_path_factory, session_jpg):
    """PDF with an embedded JPEG — used by compress tests."""
    import fitz
    tmp = tmp_path_factory.mktemp("pdfs")
    path = tmp / "with_images.pdf"
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, 500, 400)
    page.insert_image(rect, filename=str(session_jpg))
    doc.save(str(path))
    doc.close()
    return path
```

Estas fixtures dependem de `fitz` (pymupdf) e `session_jpg` (já existente). Não dependem de ffmpeg.

---

### `tests/core/document/test_processor.py` — 11 testes unit

```python
import pytest
pytestmark = pytest.mark.unit


def test_merge_two_pdfs_page_count_is_sum(sample_pdf, out_dir): ...
    # merge([sample_pdf, sample_pdf]) → 6 páginas

def test_merge_preserves_input_order(sample_pdf, out_dir): ...
    # texto da pág. 1 do resultado == texto da pág. 1 do primeiro input

def test_split_by_page_range(sample_pdf, out_dir): ...
    # split("1-2") → 1 arquivo com 2 páginas

def test_split_single_page(sample_pdf, out_dir): ...
    # split("2") → 1 arquivo com 1 página

def test_compress_output_smaller_than_input(sample_pdf_with_images, out_dir): ...
    # compress(quality=50) → output < input

def test_compress_returns_valid_pdf(sample_pdf_with_images, out_dir): ...
    # fitz.open(output) não lança exceção

def test_rotate_90_changes_page_orientation(sample_pdf, out_dir): ...
    # página 1 do output tem rotation == 90

def test_rotate_applies_to_all_pages(sample_pdf, out_dir): ...
    # todas as 3 páginas têm rotation == 90

def test_watermark_text_embeds_in_output(sample_pdf, out_dir): ...
    # output existe e tem mesmo page_count

def test_stamp_text_embeds_in_output(sample_pdf, out_dir): ...
    # output existe e tem mesmo page_count

def test_encrypt_file_requires_password(sample_pdf, out_dir): ...
    # fitz.open(output) → doc.is_encrypted == True
    # doc.authenticate(correct_pw) retorna != 0
```

---

### `tests/core/document/test_converter.py` — 7 testes unit

```python
def test_pdf_to_images_page_count_matches(sample_pdf, out_dir): ...
    # 3 páginas → 3 arquivos

def test_pdf_to_images_output_jpg(sample_pdf, out_dir): ...
    # todos os arquivos são .jpg

def test_pdf_to_images_output_png(sample_pdf, out_dir): ...
    # fmt="png" → todos os arquivos são .png

def test_images_to_pdf_creates_file(session_jpg, out_dir): ...
    # [jpg, jpg, jpg] → 1 arquivo .pdf

def test_images_to_pdf_page_count_matches_inputs(session_jpg, out_dir): ...
    # 3 jpgs → PDF com 3 páginas

def test_extract_text_returns_nonempty_string(sample_pdf, out_dir): ...
    # txt_path.read_text() contém "Page 1"

def test_extract_text_returns_empty_for_image_only_pdf(sample_pdf_with_images, out_dir): ...
    # word_count == 0
```

---

### `tests/core/document/test_info.py` — 5 testes unit

```python
def test_get_pdf_info_returns_dataclass(sample_pdf): ...
def test_get_pdf_info_page_count(sample_pdf): ...
    # info.page_count == 3

def test_get_pdf_info_file_size(sample_pdf): ...
    # info.file_size_bytes > 0

def test_get_pdf_info_has_text_true(sample_pdf): ...
    # info.has_text == True

def test_get_pdf_info_has_text_false(sample_pdf_with_images): ...
    # info.has_text == False
```

---

### `tests/core/document/test_qr.py` — 5 testes unit

```python
def test_generate_qr_creates_image_file(out_dir): ...
def test_generate_qr_png_format(out_dir): ...
def test_generate_qr_respects_size_parameter(out_dir): ...
    # Image.open(path).size aprox. (300, 300)

def test_generate_qr_url_input(out_dir): ...
def test_generate_qr_plain_text_input(out_dir): ...
```

---

### `tests/cli/test_document_cli.py` — 13 testes unit

> Padrão da skill `cli`: criar `_parse(*argv)` local com parser isolado.

```python
def _parse(*argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_document_parser(sub)
    return parser.parse_args(["document", *argv])


def test_merge_defaults(): ...
    # ns.document_op == "merge"

def test_merge_accepts_multiple_files(): ...
    # nargs="+" em ns.files

def test_split_pages_flag(): ...
    # _parse("split", "doc.pdf", "--pages", "1-3") → ns.pages == "1-3"

def test_compress_image_quality_flag(): ...
def test_rotate_angle_flag(): ...
def test_watermark_text_flag(): ...
def test_watermark_opacity_flag(): ...
def test_stamp_text_flag(): ...
def test_encrypt_password_flag(): ...
def test_extract_defaults(): ...
def test_qr_url_input(): ...
def test_pdf_to_images_fmt_flag(): ...
def test_func_callable_for_all_ops(): ...
    # parametrizado: todos os sub-subcomandos têm ns.func callable
```

---

### `tests/gui/modules/document/test_pipeline_log.py` — 10 testes unit

> Mesmo padrão de `tests/gui/modules/audio/test_pipeline_log.py`

```python
def test_resolve_stage_label_for_all_operations(): ...
    # parametrizado: todas as 12 ops retornam string não-vazia

def test_fmt_op_start_includes_item_name(): ...
def test_fmt_op_start_includes_page_count(): ...
def test_fmt_op_done_shows_size_reduction_for_compress(): ...
    # extra_stats={"size_reduction_pct": 75.0} → "−75%" no log

def test_fmt_op_done_shows_elapsed(): ...
def test_fmt_op_done_merge_shows_page_total(): ...
def test_fmt_op_done_split_shows_file_count(): ...
def test_resolve_messages_op_start(): ...
def test_resolve_messages_op_done(): ...
def test_resolve_messages_op_error(): ...
```

---

### Contagem total de testes

| Arquivo                | Testes | Marcador     |
| ---------------------- | ------ | ------------ |
| `test_processor.py`    | 11     | `unit`       |
| `test_converter.py`    | 7      | `unit`       |
| `test_info.py`         | 5      | `unit`       |
| `test_qr.py`           | 5      | `unit`       |
| `test_document_cli.py` | 13     | `unit`       |
| `test_pipeline_log.py` | 10     | `unit`       |
| **Total PR5**          | **51** | todos `unit` |

Projeto sai de 207 para **~258 testes**.

PR5.1 (OCR) acrescentará ~5 testes `@pytest.mark.integration` com skip automático se `tesseract` não estiver no PATH — usando o hook existente em `conftest.py`.

---

## Fase 3 — CLI (`src/cli/document.py`)

> Referência: skill `cli` — padrão sub-subparsers igual a `video.py` e `image.py`.

### Registro em `main.py`

```python
_NON_TRANSCRIBE_CMDS = frozenset({"audio", "video", "image", "document"})
```

Em `_dispatch_other`: importar e registrar `add_document_parser` e `run_document_cli`.

### Estrutura do parser

```python
def add_document_parser(subparsers) -> None:
    doc_p = subparsers.add_parser("document", help="Manipulação de documentos PDF")
    doc_sub = doc_p.add_subparsers(dest="document_op", required=True)
    doc_p.set_defaults(func=run_document_cli)

    _add_merge(doc_sub)
    _add_split(doc_sub)
    _add_compress(doc_sub)
    _add_rotate(doc_sub)
    _add_watermark(doc_sub)
    _add_stamp(doc_sub)
    _add_encrypt(doc_sub)
    _add_extract(doc_sub)
    _add_pdf_to_images(doc_sub)
    _add_images_to_pdf(doc_sub)
    _add_qr(doc_sub)
```

### Referência de sub-subcomandos e flags

| Operação        | Entrada              | Flags principais                                       |
| --------------- | -------------------- | ------------------------------------------------------ |
| `merge`         | `files…` (nargs="+") | —                                                      |
| `split`         | `file`               | `--pages "1-3,5"`                                      |
| `compress`      | `file`               | `--image-quality 75`                                   |
| `rotate`        | `file`               | `--angle 90`, `--pages all`                            |
| `watermark`     | `file`               | `--text "CONF."`, `--opacity 0.3`, `--position center` |
| `stamp`         | `file`               | `--text "PAGO"`                                        |
| `encrypt`       | `file`               | `--password "senha"`                                   |
| `extract`       | `file`               | —                                                      |
| `pdf-to-images` | `file`               | `--fmt jpg`, `--dpi 150`                               |
| `images-to-pdf` | `files…` (nargs="+") | `--name "saida"`                                       |
| `qr`            | `data` (positional)  | `--size 300`, `--fmt png`                              |

Mapeamento de hífen: `"pdf-to-images"` → `"pdf_to_images"` em `DocumentArgs.operation`
(mesmo padrão de `"extract-audio"` → `"extract_audio"` no vídeo).

### Exemplos de uso

```bash
uv run main.py document merge a.pdf b.pdf c.pdf
uv run main.py document split doc.pdf --pages "1-3,5"
uv run main.py document compress doc.pdf --image-quality 60
uv run main.py document rotate doc.pdf --angle 90 --pages "1,3"
uv run main.py document watermark doc.pdf --text "CONFIDENCIAL" --opacity 0.3
uv run main.py document stamp doc.pdf --text "PAGO"
uv run main.py document encrypt doc.pdf --password "senha"
uv run main.py document extract doc.pdf
uv run main.py document pdf-to-images doc.pdf --fmt jpg --dpi 150
uv run main.py document images-to-pdf *.jpg --name "album"
uv run main.py document qr "https://example.com" --size 300 --fmt png
```

---

## Fase 4 — GUI: worker + form_view + blocks

### `worker.py` — run_document_pipeline()

Segue exatamente o padrão de `src/gui/modules/audio/worker.py`:
- Recebe `(args: DocumentArgs, bus: EventBus, cancel: threading.Event, install_log_handler: bool = True)`
- Retorna `bool` (sucesso/falha)
- Emite eventos via `bus.emit()`
- `finally` garante `pipeline_running[0] = False`

Para `analyze`: chama `extract_text()` primeiro, depois reutiliza `src/analyzer.py` diretamente — zero retrabalho.

### `form_view.py` — build_document_form_view()

> Referência: skill `design-system` — usar todas as factories do DS.

**Seletor de operação:** `segmented_selector` em grid 4×3 (12 operações).

```
[ Unir        ] [ Dividir     ] [ Comprimir   ]
[ Girar       ] [ Marca d'água] [ Carimbo     ]
[ Criptografar] [ PDF→Imagens ] [ Imagens→PDF ]
[ Extrair texto] [ Analisar   ] [ QR Code     ]
```

**Entrada:** `InputSource` (URL + FilePicker). `allow_multiple=True` para `merge` e `images_to_pdf`.
Para as demais, validação no worker limita ao primeiro arquivo.

**Blocos condicionais:** cada operação exibe seu bloco de parâmetros com `visible=` / `animate_opacity` — mesmo padrão do módulo Vídeo.

**`DocumentFormRefs`:** NamedTuple com `get_*` callables para todos os campos.

### `blocks/` — controles por operação

| Block                 | Controles DS                                                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `merge_block`         | (sem parâmetros extras)                                                                                                                                 |
| `split_block`         | `labeled_field("Páginas", ft.TextField)` + `help_icon_for("document.pages", page)`                                                                      |
| `compress_block`      | `slider_row("Qualidade da imagem", 50, 95, ...)` + `help_icon_for("document.image_quality", page)`                                                      |
| `rotate_block`        | `segmented_selector([90°, 180°, 270°])` + `labeled_field("Páginas")`                                                                                    |
| `watermark_block`     | `labeled_field("Texto")` + `slider_row("Opacidade", 0.1, 0.9)` + seletor posição                                                                        |
| `stamp_block`         | `segmented_selector([PAGO, RASCUNHO, CONFIDENCIAL, Personalizado])` + campo custom                                                                      |
| `encrypt_block`       | `labeled_field("Senha", ft.TextField(password=True))` + `help_icon_for("document.password", page)`                                                      |
| `pdf_to_images_block` | `segmented_selector([JPG, PNG])` + `segmented_selector([72, 96, 150, 300] dpi)` + `help_icon_for("document.dpi", page)`                                 |
| `images_to_pdf_block` | `labeled_field("Nome do arquivo de saída")`                                                                                                             |
| `extract_text_block`  | (sem parâmetros)                                                                                                                                        |
| `analyze_block`       | `segmented_selector([qwen7b-custom, gemini-2.5-flash])` + `help_icon_for("document.analyze_model", page)`                                               |
| `qr_block`            | `labeled_field("Conteúdo / URL")` + `slider_row("Tamanho px", 100, 600)` + `segmented_selector([PNG, JPG])` + `help_icon_for("document.qr_size", page)` |

---

## Fase 5 — GUI: view + visor adaptativo

### `view.py` — build_document_view()

```python
Module(
    id="document",
    label="Documentos",
    icon=ft.Icons.DESCRIPTION,
    selected_icon=ft.Icons.DESCRIPTION,
    control=build_document_view(page),
    on_mount=_on_mount,
    on_unmount=lambda: None,
)
```

### Eventos do pipeline

`module_id = "document"`, `stage = "document"`

| Evento              | Payload                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------ |
| `document_op_start` | `operation, item_name, item_idx, total, page_count`                                        |
| `document_op_done`  | `output_path, elapsed, item_idx, total, src_size_bytes, out_size_bytes, extra_stats: dict` |
| `document_op_error` | `item_name, message`                                                                       |

`extra_stats` por operação:

| Operação        | Campos extras                                            |
| --------------- | -------------------------------------------------------- |
| `merge`         | `page_total: int, file_count: int`                       |
| `split`         | `output_files: list[str], page_counts: list[int]`        |
| `compress`      | `size_reduction_pct: float`                              |
| `pdf_to_images` | `image_count: int, resolution: str` (ex.: `"1240×1754"`) |
| `extract_text`  | `word_count: int`                                        |
| `qr`            | `qr_data_preview: str` (primeiros 40 chars)              |

### Visor adaptativo — 3 modos

O visor ocupa o painel direito, gerenciado por `visible=` num `ft.Stack`.

```python
# Classificação por modo — usada em view.py e pipeline_log.py
_VISUAL_OPS     = {"rotate", "watermark", "stamp"}
_STRUCTURAL_OPS = {"merge", "split", "compress", "encrypt"}
_SINGLE_OPS     = {"pdf_to_images", "images_to_pdf", "extract_text", "analyze", "qr"}
```

---

#### Modo 1 — Split de miniaturas

**Operações:** `rotate`, `watermark`, `stamp`

Miniatura página 1 antes × depois em `ft.Row`. Igual ao módulo Imagens.

```python
def _rasterize_first_page(path: Path) -> bytes:
    """Rasterize first page at ~72dpi → PNG bytes for preview."""
    doc = fitz.open(str(path))
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
    return pix.tobytes("png")
```

Labels "Antes" / "Depois" em `Type.tiny` sobre cada pane.

---

#### Modo 2 — Card de metadados diff

**Operações:** `merge`, `split`, `compress`, `encrypt`

`summary_card` com conteúdo dinâmico por operação:

**merge:**
```
📄  merged.pdf
3 arquivos  ·  67 páginas  →  1 arquivo  ·  67 páginas
```

**split:**
```
📄  contrato_2024.pdf  →  3 arquivos
  contrato_p1-3.pdf   3 pág.  ·  1,1 MB
  contrato_p5.pdf     1 pág.  ·  0,4 MB
  contrato_p10-20.pdf 11 pág. ·  4,2 MB
```

**compress:**
```
📄  relatorio.pdf
12,4 MB  →  3,1 MB  ·  −75%
```
Percentual em `Color.log.ok` (verde) se redução > 20%; `Color.log.work` (dourado) se < 20%.

**encrypt:**
```
🔒  contrato_2024.pdf
Documento protegido com senha
```
Ícone em `Color.log.ok`.

---

#### Modo 3 — Single pane adaptado

**pdf_to_images:** grade N×3 de miniaturas com número de página sobreposto (`Type.tiny`). Rolagem vertical se N > 6.

**images_to_pdf:** miniatura da primeira página gerada via `_rasterize_first_page` + page count + file size.

**extract_text:** painel de texto monoespaçado scrollável (`Type.mono`, `Color.log.text`). Primeiros 500 chars do `.txt`. `action_button("Analisar com IA")` abaixo — dispara operação `analyze` em sequência.

**analyze:** reutiliza `result_view.py` da Transcrição. Apenas a aba "Análise" é exibida.

**qr:** `ft.Image` centralizado com a imagem QR gerada. `output_card` abaixo.

---

### Pré-visualização do input

Antes do pipeline rodar, o painel direito exibe sempre:

```
[miniatura pág. 1 — ~200×280px]
nome_do_arquivo.pdf
N páginas  ·  X,X MB
```

Para entradas múltiplas: miniatura do primeiro item + "N arquivos selecionados".
Para entradas não-PDF: ícone genérico `ft.Icons.DESCRIPTION` + "N arquivos selecionados".

---

### `pipeline_log.py` — sequências de log

> `worker.py` importa `fmt_*` para `bus.emit("log", ...)`.
> `view.py` / `progress_view.py` importa `resolve_messages()` / `resolve_stage_label()`.

**merge:**
```
[i] {N} arquivos selecionados · {total_pages} páginas no total
[*] Lendo {filename} · {n} pág.
[~] Unindo documentos…
[✓] {output_name} · {pages} páginas · {size_mb} MB ({elapsed}s)
```

**split:**
```
[i] {filename} · {page_count} páginas
[~] Extraindo páginas {spec}…
[✓] {n} arquivos gerados · {total_extracted} páginas ({elapsed}s)
[»] {file1}  ·  {n1} pág.  ·  {size1} MB
[»] {file2}  ·  {n2} pág.  ·  {size2} MB
```

**compress:**
```
[i] {filename} · {page_count} páginas · {src_size} MB
[~] Recomprimindo imagens embutidas (qualidade {quality}%)…
[✓] {src_size} MB → {out_size} MB · −{pct}% ({elapsed}s)
```

**rotate:**
```
[i] {filename} · {page_count} páginas
[~] Girando {pages_desc} em {angle}°…
[✓] Concluído ({elapsed}s)
```
`pages_desc`: "todas as páginas" ou "páginas {spec}".

**watermark:**
```
[i] {filename} · {page_count} páginas
[~] Aplicando marca d'água "{text}" em todas as páginas (opacidade {pct}%)…
[✓] Concluído ({elapsed}s)
```

**stamp:**
```
[i] {filename} · {page_count} páginas
[~] Aplicando carimbo "{text}" em todas as páginas…
[✓] Concluído ({elapsed}s)
```

**encrypt:**
```
[i] {filename} · {page_count} páginas · {src_size} MB
[~] Criptografando documento…
[✓] Documento protegido com senha ({elapsed}s)
```

**pdf_to_images:**
```
[i] {filename} · {page_count} páginas
[~] Rasterizando página {current}/{total}…     ← mutable=True
[✓] {n} imagens geradas · {fmt.upper()} {resolution}px ({elapsed}s)
```

**images_to_pdf:**
```
[i] {n} imagens selecionadas
[*] Adicionando {filename} ({current}/{total})…   ← mutable=True
[✓] {output_name} · {n} páginas · {size} MB ({elapsed}s)
```

**extract_text:**
```
[i] {filename} · {page_count} páginas
[~] Extraindo texto…
[»] {page_count} páginas · ~{word_count} palavras
[✓] {output_name}.txt · {size_kb} KB ({elapsed}s)
[i] Clique em "Analisar com IA" para processar o conteúdo
```
Último `[i]` suprimido se `word_count < 50`.

**analyze:**
```
[i] {filename} · {page_count} páginas
[*] Extraindo texto do documento…
[»] ~{word_count} palavras extraídas
[*] Carregando modelo {model}…
[~] Analisando chunk {i}/{total}…
[*] Traduzindo para PT-BR…
[✓] Análise concluída ({elapsed}s) — {output_name}_analysis.md
```
Reutiliza eventos `analyze_*` e `translation_*` já existentes — zero retrabalho no `progress_view.py`.

**qr:**
```
[~] Gerando QR code…
[»] Conteúdo: {data_preview}
[»] {size}×{size}px
[✓] {output_name}.{fmt} · {size_kb} KB ({elapsed}s)
```

---

## Fase 6 — Home Screen

### 5º card

```python
# src/gui/home.py — adicionar à lista de cards
{
    "id": "document",
    "label": "Documentos",
    "icon": ft.Icons.DESCRIPTION,
    "description": (
        "12 operações para PDFs — une, divide, comprime, protege com senha, "
        "adiciona marcas, extrai texto e analisa com IA."
    ),
}
```

### Ajuste de layout (2×2 → 3+2)

Com 5 módulos em fullscreen:

- **Linha 1:** Áudio · Vídeo · Imagens (3 cards, `ft.Row(alignment=SPACE_EVENLY)`)
- **Linha 2:** Transcrição · Documentos (2 cards, `ft.Row(alignment=CENTER)`)

Alternativa mais simples: `ft.Wrap(spacing=Space.xl, run_spacing=Space.xl)` com os 5 cards — auto-layout sem lógica de linhas.

---

## Fase 7 — Integrações e documentação

### `src/gui/app.py`

```python
from src.gui.modules.document.view import build_document_view

# Adicionar ao MODULES list:
Module(
    id="document",
    label="Documentos",
    icon=ft.Icons.DESCRIPTION,
    selected_icon=ft.Icons.DESCRIPTION,
    control=build_document_view(page),
    on_mount=_document_on_mount,
    on_unmount=lambda: None,
)
```

### `src/gui/help_content.py` — chaves novas

```python
# HELP_SHORT
"document.input":          "Selecione um ou mais PDFs — ou uma URL direta para download.",
"document.operation":      "Escolha a operação a realizar sobre o(s) documento(s).",
"document.pages":          'Intervalo de páginas: "1-3,5,8-" = págs. 1, 2, 3, 5, 8 até o fim.',
"document.image_quality":  "Qualidade das imagens recomprimidas. 75 = boa relação tamanho/qualidade.",
"document.watermark":      "Marca d'água sutil em diagonal sobre todas as páginas.",
"document.stamp":          "Carimbo em destaque centralizado na página: PAGO, RASCUNHO, etc.",
"document.password":       "Criptografia AES-256. Guarde a senha — não é possível recuperá-la.",
"document.dpi":            "Resolução da rasterização. 150 = boa qualidade; 300 = imprimir.",
"document.qr_size":        "Tamanho do QR code gerado em pixels.",
"document.analyze_model":  "Modelo para análise do conteúdo extraído. Local ou Gemini.",

# HELP_LONG (modais)
"document.pages": (
    "Formato de intervalo de páginas",
    '1-3     → páginas 1, 2, 3\n'
    '1,3,5   → páginas 1, 3, 5\n'
    '8-      → página 8 até o fim\n'
    '1-3,5,8- → combinação\n\n'
    'Numeração começa em 1.'
),
"document.password": (
    "Criptografia de PDF",
    "O documento é protegido com AES-256 (padrão PDF 1.7).\n\n"
    "Não há como recuperar a senha esquecida — "
    "guarde-a em um gerenciador de senhas."
),
"document.dpi": (
    "Resolução de rasterização",
    "72 dpi  → tela, arquivos menores\n"
    "96 dpi  → padrão web\n"
    "150 dpi → boa qualidade, equilíbrio\n"
    "300 dpi → impressão profissional\n\n"
    "A cada dobro de DPI, o tamanho do arquivo quadruplica."
),
```

### `CLAUDE.md`

Adicionar seção "Módulo Documentos" após "Módulo Vídeo", seguindo o mesmo padrão de documentação: operações, core, GUI, pipeline_log, saída, eventos e bridges.

### `README.md`

Tabela de módulos — antes do lançamento:
```markdown
| **Documentos** | 🚧 Em breve | 12 operações para PDFs: unir, dividir, comprimir, proteger, extrair texto e analisar com IA |
```

Após lançamento: `✅ Disponível`.

Roadmap:
```markdown
- **PR5** ✅ — Módulo Documentos: 12 operações PDF + visor adaptativo + bridge Transcrição/Imagens.
```

---

## Design System — checklist de conformidade

> Referência: skill `design-system`

- [ ] `segmented_selector` para seleção de operação (grid 4×3)
- [ ] `labeled_field` para todos os campos de texto
- [ ] `slider_row` para qualidade, opacidade, tamanho QR, DPI
- [ ] `section()` para agrupar controles por tema no formulário
- [ ] `output_card` para cada arquivo de resultado
- [ ] `summary_card` para o card de metadados diff (Modo 2)
- [ ] `log_line` no pipeline_log — prefixos `[i]` `[*]` `[~]` `[✓]` `[!]` `[»]`
- [ ] `spinner()` factory — não criar animação própria
- [ ] `Cursor.interactive` em todos os elementos clicáveis
- [ ] **Nunca** `ink=True` em containers clicáveis
- [ ] `Color.log.*` para cores semânticas no log
- [ ] `module_scaffold(form, panel)` para o layout split
- [ ] `help_icon_for(key, page)` — chaves registradas em `help_content.py` antes de usar
- [ ] Não usar `ft.Colors.SURFACE_VARIANT` — usar `ft.Colors.SURFACE` ou `Color.dark.surface_variant`
- [ ] Toggle de visibilidade via `visible=` num `ft.Stack` — nunca reatribuir `Container.content`
- [ ] Um único `page.update()` por evento de pubsub

---

## Fases de implementação

| Fase  | Escopo                                                               | Pré-requisito | Validação                                         |
| ----- | -------------------------------------------------------------------- | ------------- | ------------------------------------------------- |
| **1** | `src/core/document/` — args, info, processor, converter, qr          | —             | `uv run pytest tests/core/document/ -v`           |
| **2** | Fixtures em `conftest.py` + todos os arquivos de teste               | Fase 1        | `uv run pytest -m unit -v`                        |
| **3** | `src/cli/document.py` + registro em `main.py`                        | Fase 1        | `uv run pytest tests/cli/test_document_cli.py -v` |
| **4** | `src/gui/modules/document/` — worker + form_view + blocks            | Fase 1        | inspeção manual da GUI                            |
| **5** | `src/gui/modules/document/` — view + visor adaptativo + pipeline_log | Fase 4        | inspeção manual completa do módulo                |
| **6** | `src/gui/home.py` — 5º card + ajuste de layout                       | Fase 5        | inspeção manual da Home Screen                    |
| **7** | `app.py` + `help_content.py` + `CLAUDE.md` + `README.md`             | Fase 5        | `uv run pytest -m unit -v` (suíte completa)       |

A GUI funciona a partir da **Fase 5**. O módulo não aparece na NavigationRail até a Fase 7 (registro em `app.py`).

---

## PR5.1 — OCR (pós-lançamento, sem data)

- `src/core/document/ocr.py` — `ocr_pdf(path, output_dir, lang="por+eng") -> tuple[Path, int]`
- Extra `[ocr]` em `pyproject.toml` — `pytesseract >= 0.3`
- Dependência de sistema: `tesseract.exe` no PATH → adicionado a `check_dependencies()`
- Card `ocr` no form_view desabilitado com tooltip quando extra não instalado (padrão `_UNAVAILABLE` do módulo Imagens)
- ~5 testes `@pytest.mark.integration` com skip automático se Tesseract ausente
- Log:
  ```
  [i] {filename} · {page_count} páginas (PDF escaneado)
  [*] Rasterizando página {current}/{total}…     ← mutable=True
  [~] Reconhecendo texto (página {current}/{total})…
  [✓] {output_name}.txt · {word_count} palavras ({elapsed}s)
  ```