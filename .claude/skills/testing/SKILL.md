---
name: testing
description: Guia para adicionar, corrigir e revisar testes unitários do projeto mill.tools. Invocar quando: escrever novos testes, investigar expected values errados, aumentar cobertura de um módulo, mockar dependências externas (ctranslate2, PIL.Image.open, llm_factory, settings), ou entender por que um teste falha. Também use ao criar fixtures novas ou revisar tests/core/ e tests/gui/.
---

# mill.tools — Guia de Testes Unitários

## Estrutura de arquivos

```
tests/
├── conftest.py                          # fixtures globais — NÃO duplicar aqui
├── test_utils.py                        # src/utils.py
├── test_transcriber.py                  # src/transcriber.py
├── test_llm_factory.py                  # src/llm_factory.py
├── gui/
│   ├── __init__.py
│   ├── test_settings.py                 # src/gui/settings.py
│   └── modules/*/test_pipeline_log.py  # builders fmt_* (pendente)
└── core/
    ├── audio/test_normalizer_parser.py  # _parse_loudnorm_json
    └── image/test_transform.py          # 9 funções puras Pillow
```

Regras de estrutura:
- Espelhar `src/` em `tests/` — `src/core/image/transform.py` → `tests/core/image/test_transform.py`
- Cada subpasta de `tests/` precisa de `__init__.py` vazio (evita conflito de import com src/)
- Imports dentro dos testes: `from src.modulo import funcao` (nunca import relativo)

---

## Fixtures globais (`tests/conftest.py`)

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

---

## Template de novo arquivo de teste

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
uv run pytest tests/core/image/test_transform.py \
    --cov=src.core.image.transform --cov-report=term-missing

# Cobertura geral (exclui src/gui/ automaticamente via pyproject.toml)
uv run pytest -m "not integration" --cov=src --cov-report=term-missing
```

O alvo é **≥ 90%** por módulo de `src/core/`. Linhas difíceis de cobrir sem dependências externas (ffmpeg, GPU) devem ser marcadas como `# pragma: no cover` somente se for impossível testar sem infra.
