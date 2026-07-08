---
name: testing
description: Guia para adicionar, corrigir e revisar testes (unitários e de integração) do projeto mill.tools. Invocar quando: escrever novos testes, investigar expected values errados, aumentar cobertura de um módulo, ou mockar qualquer fronteira. Receitas de mock ficam em 3 arquivos de referência citados aqui — mocks-media.md (subprocess/ffmpeg, WhisperModel, urllib, pytesseract, pymupdf/qrcode), mocks-llm-rag-ml.md (GenericFakeChatModel/LangChain, core RAG, core ML, core Dados/assess/datacard, core Receitas) e mocks-gui-cli.md (workers da GUI com bus falso, testes de CLI). Também use ao criar fixtures novas (session/function-scoped), adicionar testes de integração com ffmpeg, revisar tests/core/ e tests/gui/, ou ajustar config dos plugins (pytest-xdist, pytest-timeout, pytest-clarity, pytest-randomly).
---

# mill.tools — Guia de Testes

Este SKILL.md é o "sempre necessário". As **receitas de mock** (as maiores) moram em três arquivos de
referência na pasta desta skill — abra o que casar com a fronteira que você está testando:

| Arquivo | Abra quando testar… |
|---|---|
| [`mocks-media.md`](mocks-media.md) | `subprocess`/ffmpeg, `WhisperModel` (faster-whisper), `urllib`, `PIL.Image.open` (call-count), `pytesseract`, `pymupdf`/`qrcode` |
| [`mocks-llm-rag-ml.md`](mocks-llm-rag-ml.md) | LangChain (`GenericFakeChatModel`), core RAG (`src/core/rag/`), core ML (`src/core/ml/`, Planos 3/4A/4B), core Dados (`assess`/`datacard`/`ml`), core Receitas |
| [`mocks-gui-cli.md`](mocks-gui-cli.md) | workers da GUI (bus falso), testes de CLI (`_parse`, runner, kebab→snake) |

> Contexto das camadas de RAG/ML/Observatório → skill `ml-rag`. Onde o código mora e limites de tamanho →
> skill `architecture`.

---

## Estrutura de arquivos

A árvore de `tests/` **espelha `src/`** e é derivável do repo (`ls`/Glob) — não é reproduzida aqui.
`src/core/audio/normalizer.py` → `tests/core/audio/test_normalizer_unit.py`.

Regras de estrutura:
- Espelhar `src/` em `tests/`.
- **Exceção — subpacote interno com API flat via `__init__`**: quando um módulo grande é dividido em
  arquivos internos (ex.: `core/image/transform.py` → pacote `transform/` com `_shared.py`/`watermark.py`/
  `ops.py`, reexportados por `__init__.py`), os testes **não** precisam espelhar os arquivos internos —
  continuam testando a API pública via `from src.core.image.transform import X` num único
  `tests/core/image/test_transform.py`. Espelhar 1:1 só faz sentido quando cada arquivo interno tem
  responsabilidade e testes genuinamente independentes.
- Cada subpasta de `tests/` precisa de `__init__.py` vazio (evita conflito de import com `src/`).
- Imports dentro dos testes: `from src.modulo import funcao` (nunca import relativo), e **dentro** da função
  de teste (não no topo) — isola falha de import.
- Nome do teste descreve o **comportamento**, não a implementação.

---

## Marcadores e plugins

- **Marcadores**: `unit` (Python puro — sem ffmpeg/rede/GPU; DuckDB e pymupdf in-process **qualificam** como
  unit) · `integration` (requer ffmpeg). `pytest_collection_modifyitems` em `conftest.py` **pula
  automaticamente** qualquer `@pytest.mark.integration` se `ffmpeg` não estiver no PATH (CI sem ffmpeg).
- **Regra de commit**: `uv run pytest -m unit` verde **antes de commitar** + `ruff` limpo. Cobertura sobre
  `src/` (branch on), excluindo `src/gui/` (Flet não testável headless).
- **Plugins**: `pytest-randomly` (ordem aleatória — `--randomly-seed=NNN` reproduz), `pytest-timeout` (60s
  default), `pytest-xdist` (`-n auto`), `pytest-clarity` (diffs legíveis).

---

## ⚠️ Testes NÃO podem travar a máquina (OOM) — regra dura

Um teste que faz o processo Python crescer sem limite estoura a RAM (dev = 16 GB), **trava o Windows e fecha
o VSCode sem aviso** — inaceitável, custa tempo e dinheiro. `pytest-timeout` (60 s) **não protege**: o
swap/OOM trava a máquina *antes* do timeout disparar. Prevenir é obrigatório; ao escrever/revisar qualquer
teste, cheque os padrões abaixo.

**Causa nº 1 — travessia recursiva descendo em `MagicMock`** (o bug que travou a máquina, `test_rag_tab.py`).
Um `MagicMock` fabrica um filho novo a cada acesso de atributo, então `m.controls`/`m.content` nunca esgota.
Um helper que anda a árvore de controles Flet por `.controls`/`.content` recursivamente e encontra um mock
**enterrado na árvore** (ex.: `spinner()` trocado por `MagicMock()` num `_no_spin`, que vira filho de um
`Row`) recursa/gera mocks para sempre → 1–6 GB em segundos. Regra: **helper de travessia PARA em mocks**.

```python
from unittest.mock import NonCallableMock

def _walk(control):
    yield control
    if isinstance(control, NonCallableMock):
        return  # nunca descer num mock (fabrica filhos infinitos → OOM)
    for attr in ("controls", "content"):
        ...
```

O sintoma é traiçoeiro: um `next(...)` que acha o alvo **antes** do mock na ordem de travessia passa; só o
que procura um alvo **depois** do mock explode. Não confie em "passou isolado" — rode a suíte inteira.

**Outros padrões de OOM a vigiar:**
- `while <cond>` onde `<cond>` vem de um mock — `MagicMock()` é sempre truthy → laço infinito; se o corpo
  acumula em lista/str vira OOM (senão só trava a CPU até o timeout).
- `for x in mock_iteravel` onde o mock recebeu um iterador **infinito** (`itertools.count/repeat/cycle` como
  `return_value`/`side_effect`) e o código acumula (`full_text += ...`).
- Modelo real carregado por mock incompleto (Whisper/spaCy/UMAP/embeddings) — confirme sempre que a fronteira
  pesada está de fato mockada; ver os 3 arquivos de referência.

**Diagnosticar com segurança (sem travar):** nunca rode a suíte "crua" para caçar o culpado. Rode sob um
guarda que **mata o processo em ~3 GB** (bem abaixo do travamento), registrando o teste corrente: uma thread
daemon amostra o RSS (`ctypes` → `psapi.GetProcessMemoryInfo`, `WorkingSetSize`) a cada ~20 ms e chama
`os._exit()` ao cruzar o teto, imprimindo o `nodeid` (hook `pytest_runtest_logstart`) + o **delta** de RSS
por teste (pico − início) para achar o *alocador*, não só onde cruzou o teto. Rode `-n0 -p no:randomly` para
atribuição determinística.

---

## Fixtures globais (`tests/conftest.py`)

Não duplicar estas fixtures nos testes.

### Function-scoped (padrão — limpas por teste)

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

### Session-scoped (geradas uma vez via ffmpeg/Pillow — só para `@pytest.mark.integration`)

| Fixture | O que fornece |
|---|---|
| `sample_wav` | `Path` → WAV mono 44100 Hz 3 s (sine 440 Hz) via ffmpeg lavfi |
| `sample_mp3` | `Path` → MP3 mono 128 kbps 3 s via ffmpeg lavfi |
| `sample_mp4` | `Path` → MP4 320×240 3 s (vídeo azul + áudio sine) via ffmpeg |
| `sample_wav_stereo` | `Path` → WAV estéreo 44100 Hz 3 s (sine 440 Hz, 2 canais) via ffmpeg |
| `session_jpg` | `Path` → JPEG RGB 640×480 via Pillow |

Não use fixtures session-scoped em testes unitários (não devem depender de ffmpeg). São **somente leitura** —
para testes que modificam a entrada, copie com `shutil.copy` para `tmp_path`.

Fixtures de dados (`csv_sales`, `csv_people_cp1252`, `json_file`) e de PDF (`sample_pdf`,
`sample_pdf_with_images`) são locais aos respectivos `conftest.py` de subpasta.

---

## Templates de novos arquivos de teste

### Teste unitário (sem ffmpeg, sem I/O real)

```python
import pytest


@pytest.mark.unit
def test_nome_descritivo(fixture_se_necessario):
    from src.modulo import funcao_alvo
    resultado = funcao_alvo(entrada)
    assert resultado == esperado
```

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

Rodar só integração: `uv run pytest -m integration -v`.

---

## Gotchas críticos — expected values

### `sanitize_filename` (src/utils.py)

O ponto `.` **não está em `_SANITIZE_INVALID`** — é preservado:
```python
sanitize_filename("Python 3.13 Tutorial")  # → "Python_3.13_Tutorial" não "Python_313_Tutorial"
```
`\s+` já colapsa múltiplos espaços em único `_`: `sanitize_filename("  a  b  ")` → `"a_b"` não `"a__b"`.

### `crop_image` modo `ratio` — branch `if target_h > ih`

Dispara quando `iw * rh / rw > ih` (imagem **mais larga** que a proporção pedida). Com `jpg_image` (200×150)
e ratio `"1:1"`: `target_h = int(200*1/1) = 200 > 150` → resultado 150×150. Uma portrait (100×200) com ratio
`"16:9"` **não** dispara (`target_h = 56 < 200`).

### `_save` e o modo `L` (grayscale)

`_save()` converte qualquer modo ≠ RGB para RGB ao salvar JPEG. Um teste que verifica `im.mode == "L"`
**precisa usar `out_fmt="png"`** (PNG preserva L; JPEG converteria para RGB).

### `convert_audio` — bitrate sem "k"

`convert_audio` acrescenta "k" internamente (`f"{bitrate}k"`). Passar `"128k"` gera `"128kk"` (erro ffmpeg).
Passe `bitrate="128"`.

### `autotrim` com artefatos JPEG

`ImageChops.difference` em JPEG pode ter pixels não-zero em áreas "brancas" por artefatos de compressão.
Imagens de teste para autotrim devem ser salvas como **PNG** (`src = tmp_path / "border.png"`, nunca `.jpg`).

---

## Padrões de mock genéricos

As receitas específicas por fronteira estão nos 3 arquivos de referência (tabela no topo). Estes são os dois
mecanismos de base e o isolamento de config:

```python
def test_algo(mocker):
    mocker.patch("ctranslate2.get_supported_compute_types", return_value=["float32"])
    mocker.patch("src.llm_factory._make_ollama")            # retorna MagicMock
    mocker.patch("src.modulo.funcao", side_effect=OSError("falha"))

def test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    monkeypatch.setattr("src.llm_factory.load_dotenv", lambda *a, **kw: None)
```

**Isolamento de `src/gui/settings.py`** (usa `_CONFIG_DIR`/`_CONFIG_FILE` globais — redirecionar antes de
`load()`/`save()`):
```python
@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    import src.gui.settings as mod
    monkeypatch.setattr(mod, "_CONFIG_DIR",  tmp_path / ".mill-tools")
    monkeypatch.setattr(mod, "_CONFIG_FILE", tmp_path / ".mill-tools" / "config.json")
```

---

## Cobertura

```bash
# Cobertura de um módulo específico (usar pontos, não barras)
uv run pytest tests/core/audio/test_normalizer_unit.py \
    --cov=src.core.audio.normalizer --cov-report=term-missing

# Cobertura unitária apenas (rápido, sem ffmpeg)
uv run pytest -m "not integration" --cov=src --cov-report=term-missing
```

Alvo **≥ 90%** por módulo; agregado **~88%** com branch. **Não** mantemos uma tabela de cobertura por módulo
aqui — ela é snapshot manual que envelhece; o `--cov-report=term-missing` gera o estado real sob demanda.

Lacunas conhecidas e justificáveis (não perseguir):
- `audio/downloader.py` + `video/downloader.py` — yt-dlp só tem valor real em E2E (que não fazemos); smoke
  de mock daria <40%, retorno pequeno.
- `image/background.py` + `image/describe.py` — extras opcionais `[ai-image]`/vision LLM, sem teste de uso real.

Linhas impossíveis de cobrir sem desinstalar dependências (ex.: branch `ImportError` de `is_available()`) →
`# pragma: no cover`.

---

## Regra de projeto: pymupdf/DuckDB são usados de verdade nos testes `unit`

Os testes de `tests/core/document/` **não mockam pymupdf** — usam as fixtures `sample_pdf` /
`sample_pdf_with_images` (com `pytest.importorskip("pymupdf")`), que geram PDFs reais em disco. O mesmo vale
para DuckDB em `tests/core/data/`. Justificativa: ambos são dependência **hard** (não opcional) e nenhum
desses testes toca ffmpeg/rede/GPU — logo ficam corretamente marcados como `unit` e exercem o comportamento
real (`merge_pdfs`, `split_pdf`, `run_query`, …).

Mocke pymupdf/qrcode/DuckDB **pontualmente** só para cobrir caminhos de erro ou branches de disponibilidade —
receitas em [`mocks-media.md`](mocks-media.md) e [`mocks-llm-rag-ml.md`](mocks-llm-rag-ml.md).
