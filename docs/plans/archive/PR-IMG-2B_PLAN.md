# mill.tools — PR-IMG-2B: Remover Fundo + Descrever Imagem

> **Pré-requisito: PR-IMG-2A implementado e funcionando.**
> Adiciona **duas** operações ao sistema já existente: `remove_bg` (rembg CPU/ONNX) e `describe` (Ollama vision).
> Nenhum arquivo é refatorado — apenas extensões pontuais.
>
> **DS:** consultar skill `design-system` (`.claude/skills/design-system/SKILL.md`) durante a implementação
> para factories, tokens, cursor conventions e help system.

---

## Base deixada pelo PR-IMG-2A

- `_OPS`, `_make_card`, `_select_op`, `_refresh_cards` — grid extensível
- `match args.operation` no worker + `_resolve_messages` / `_resolve_stage_label` — `"remove_bg"` já tem entry
- Before/After viewer — funciona para ops imagem→imagem; para `describe` (saída texto) fica em single-pane
- `_param_blocks` — dict `{op_id: ft.Column}` registrado antes do loop de refresh

---

## 1. Arquivos

**Novos:**
```
src/core/image/background.py
src/core/image/describe.py
ollama/Modelfile.vision
```

**Modificados:**
```
pyproject.toml                          ← extra [ai-image]
src/gui/modules/image/form_view.py      ← +2 entries em _OPS + 2 blocos de parâmetros
src/gui/modules/image/worker.py         ← +2 dispatches + _run_batch_rembg + _run_describe
src/gui/help_content.py                 ← +3 chaves
```

---

## 2. `ImageArgs` — campos novos

```python
# remove_bg
rembg_model: str = "u2net"

# describe
describe_model:  str = "moondream-custom"
describe_prompt: str = ""   # vazio = prompt PT-BR padrão
```

---

## 3. `src/core/image/background.py`

```python
"""Remoção de fundo via rembg (CPU/ONNX). Imports sempre lazy."""
from __future__ import annotations
from pathlib import Path

MODELS = ("u2net", "u2netp", "silueta", "isnet-general-use", "u2net_human_seg")

_MODEL_LABELS: dict[str, str] = {
    "u2net":             "u2net",
    "u2netp":            "u2netp",
    "silueta":           "silueta",
    "isnet-general-use": "isnet",
    "u2net_human_seg":   "humano",
}


def is_available() -> bool:
    """True se rembg + onnxruntime instalados."""
    try:
        import rembg  # noqa: F401
        return True
    except ImportError:
        return False


def create_session(model: str = "u2net"):
    """Cria sessão rembg. 1ª vez: faz download para ~/.u2net/."""
    import rembg
    return rembg.new_session(model)


def remove_background(src: Path, out_dir: Path, session) -> Path:
    """Remove fundo; salva PNG com alpha em out_dir."""
    import rembg
    from PIL import Image
    from src.core.image.transform import _out_path

    with Image.open(src) as im:
        result = rembg.remove(im, session=session)

    out_path = _out_path(src, out_dir, "png")
    result.save(out_path, format="PNG")
    return out_path
```

> **Threads ONNX:** não setar `OMP_NUM_THREADS` — ONNX Runtime usa defaults do SO.
> Ajuste fino de threads é feito via Modelfile para modelos Ollama; rembg não tem Modelfile.

---

## 4. `src/core/image/describe.py`

```python
"""Descrição de imagem via Ollama vision (LangChain). Import lazy."""
from __future__ import annotations
import base64
from pathlib import Path

_DEFAULT_PROMPT = (
    "Descreva detalhadamente o que está nesta imagem em português: "
    "objetos presentes, contexto, cores dominantes, texto visível (se houver)."
)


def is_available() -> bool:
    """True se langchain_ollama instalado (já é dep do projeto)."""
    try:
        from langchain_ollama import ChatOllama  # noqa: F401
        return True
    except ImportError:
        return False


def describe_image(src: Path, model: str = "moondream-custom", prompt: str = "") -> str:
    """Envia imagem ao modelo Ollama vision e retorna descrição em texto.

    Args:
        src: Caminho do arquivo de imagem.
        model: Nome do modelo Ollama (deve ter capacidade vision).
        prompt: Prompt customizado; vazio = padrão PT-BR.

    Returns:
        Texto da descrição gerada pelo modelo.
    """
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage

    with open(src, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    suffix = src.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix

    llm = ChatOllama(model=model)
    message = HumanMessage(content=[
        {"type": "text", "text": prompt or _DEFAULT_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{img_b64}"}},
    ])
    response = llm.invoke([message])
    return response.content


def save_description(src: Path, out_dir: Path, text: str) -> Path:
    """Salva descrição como <stem>_description.txt em out_dir."""
    out_path = out_dir / f"{src.stem}_description.txt"
    # Resolve colisão de nome
    i = 1
    while out_path.exists():
        out_path = out_dir / f"{src.stem}_description_{i}.txt"
        i += 1
    out_path.write_text(text, encoding="utf-8")
    return out_path
```

---

## 5. `ollama/Modelfile.vision`

```
FROM moondream:latest
PARAMETER num_thread 4
PARAMETER num_gpu 0
```

**Setup (uma vez):**
```bash
ollama pull moondream
ollama create moondream-custom -f ollama/Modelfile.vision
```

> `num_gpu 0` força CPU puro (MX150 2GB VRAM insuficiente para modelos vision).
> `num_thread 4` — padrão do projeto (i5-8265U, 4 cores físicos).
> Outros modelos testáveis: `llava:7b` (mais capaz, ~4GB RAM), `minicpm-v`.

---

## 6. `pyproject.toml`

```toml
[project.optional-dependencies]
ai-image = ["rembg[cpu]>=2.0.50"]
# describe não precisa de extra — langchain_ollama já é dep do projeto
```

---

## 7. `form_view.py` — extensões

### 7.1 `_OPS` — 2 novas entradas

```python
("remove_bg", ft.Icons.AUTO_FIX_HIGH,        "Remover\nfundo"),
("describe",  ft.Icons.DESCRIPTION_OUTLINED,  "Descrever"),
```

### 7.2 Card com disponibilidade dinâmica (`_make_card`)

```python
from src.core.image.background import is_available as _rembg_ok
from src.core.image.describe   import is_available as _describe_ok  # sempre True

_UNAVAILABLE: dict[str, str] = {}
if not _rembg_ok():
    _UNAVAILABLE["remove_bg"] = "Instale com: uv sync --extra ai-image"

# Dentro de _make_card, após criar `ctr`:
if op_id in _UNAVAILABLE:
    ctr.tooltip = _UNAVAILABLE[op_id]
    ctr.disabled = True
    ic.color  = ft.Colors.ON_SURFACE_VARIANT
    tx.color  = ft.Colors.ON_SURFACE_VARIANT
    ctr.on_click = None
```

### 7.3 Bloco `remove_bg`

```python
from src.core.image.background import is_available as _rembg_ok, MODELS as _REMBG_MODELS

_rembg_available = _rembg_ok()

_rembg_warning = ft.Text(
    "⚠ Extra não instalado.\nExecute: uv sync --extra ai-image",
    color=ft.Colors.ERROR,
    size=Type.small.size,
    visible=not _rembg_available,
)

# segmented_selector: IDs como options, dict de labels para display
_rembg_grid, _get_rembg_model, _set_rembg_disabled = segmented_selector(
    list(_REMBG_MODELS),
    "u2net",
    page,
    labels={
        "u2net":             "u2net",
        "u2netp":            "u2netp",
        "silueta":           "silueta",
        "isnet-general-use": "isnet",
        "u2net_human_seg":   "humano",
    },
    columns=5,
)
_set_rembg_disabled(not _rembg_available)

rembg_block = ft.Column(
    visible=False,
    spacing=Space.sm,
    controls=[
        _rembg_warning,
        section("Modelo", _rembg_grid, help_key="image.rembg_model", page=page),
        ft.Text(
            "Saída: sempre PNG com transparência",
            size=Type.small.size,
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
        ),
    ],
)
_param_blocks["remove_bg"] = rembg_block
```

### 7.4 Bloco `describe`

```python
_DESCRIBE_MODELS = ["moondream-custom", "llava:7b", "minicpm-v"]

_desc_grid, _get_desc_model, _set_desc_disabled = segmented_selector(
    _DESCRIBE_MODELS,
    "moondream-custom",
    page,
    columns=3,
)

_desc_prompt_tf = ft.TextField(
    hint_text="Prompt customizado (vazio = padrão PT-BR)",
    text_size=Type.caption.size,
    height=38,
    content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
    border_color=ft.Colors.OUTLINE_VARIANT,
    focused_border_color=ft.Colors.PRIMARY,
    expand=True,
)

describe_block = ft.Column(
    visible=False,
    spacing=Space.sm,
    controls=[
        section("Modelo vision", _desc_grid, help_key="image.describe_model", page=page),
        labeled_field("Prompt", _desc_prompt_tf, help_key="image.describe_prompt", page=page),
        ft.Text(
            "Saída: .txt salvo em output/image/processed/",
            size=Type.small.size,
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
        ),
    ],
)
_param_blocks["describe"] = describe_block
```

### 7.5 `_on_start_click` — campos adicionais

```python
rembg_model   = _get_rembg_model() if op == "remove_bg" else "u2net",
describe_model = _get_desc_model() if op == "describe"   else "moondream-custom",
describe_prompt = (_desc_prompt_tf.value or "").strip() if op == "describe" else "",
```

### 7.6 `_set_running` — desabilitar seletores de IA

```python
_set_rembg_disabled(running or not _rembg_available)
_set_desc_disabled(running)
```

### 7.7 Formato de saída — `describe` sem bloco de formato

Em `_refresh_format_block`:
```python
_fmt_section.visible = op not in ("favicon", "describe")
```

---

## 8. `worker.py` — extensões

### 8.1 Imports adicionais

```python
from src.core.image.background import is_available, create_session, remove_background
from src.core.image.describe   import describe_image, save_description
```

### 8.2 Checks antes do loop (junto com `contact_sheet`)

```python
if args.operation == "remove_bg":
    return _run_batch_rembg(args, bus, cancel_event, emit)
if args.operation == "describe":
    return _run_batch_describe(args, bus, cancel_event, emit)
```

### 8.3 `_run_batch_rembg`

```python
def _run_batch_rembg(args, bus, cancel_event, emit) -> bool:
    if not is_available():
        emit("task_error", payload={"message": "Extra [ai-image] não instalado. Execute: uv sync --extra ai-image"})
        return False

    emit("log", payload={"message": f"[i] Carregando modelo '{args.rembg_model}' (1ª vez: baixa para ~/.u2net/)…"})
    try:
        session = create_session(args.rembg_model)
    except Exception as exc:
        emit("task_error", payload={"message": f"Falha ao carregar modelo rembg: {exc}"})
        return False

    emit("progress_start")
    output_paths, failed_count, total = [], 0, len(args.items)

    for idx, item in enumerate(args.items, 1):
        if cancel_event.is_set():
            emit("task_error", payload={"message": "Cancelado."}); return False

        item_name = _item_label(item)
        emit("queue_progress", payload={"current_item": idx, "total_items": total, "item_name": item_name})
        t0 = time()
        try:
            if item.kind == "url":
                emit("image_op_start", payload={"operation": "download", "item_name": item_name, "item_idx": idx, "total_items": total})
                src = download_image(item.value, IMAGE_SOURCE_DIR)
            else:
                src = Path(item.value)

            input_thumb = _make_thumb(src)
            emit("image_op_start", payload={"operation": "remove_bg", "item_name": src.name,
                                             "thumb": input_thumb, "item_idx": idx, "total_items": total})

            out_path = remove_background(src, IMAGE_PROCESSED_DIR, session)
            output_paths.append(str(out_path))
            emit("image_op_done", payload={
                "output_path": str(out_path), "thumb": _make_thumb(out_path),
                "elapsed": f"{time()-t0:.1f}s", "item_idx": idx, "total_items": total,
                "src_size_bytes": src.stat().st_size, "out_size_bytes": out_path.stat().st_size,
            })
        except Exception as exc:
            failed_count += 1
            logger.warning("[!] Erro em '%s': %s", item_name, exc)
            emit("image_op_error", payload={"item_name": item_name, "message": str(exc)})

        if cancel_event.is_set():
            emit("task_error", payload={"message": "Cancelado."}); return False

    emit("task_done", payload={"output_paths": output_paths, "failed_count": failed_count})
    return len(output_paths) > 0
```

### 8.4 `_run_batch_describe`

```python
def _run_batch_describe(args, bus, cancel_event, emit) -> bool:
    emit("progress_start")
    output_paths, failed_count, total = [], 0, len(args.items)

    for idx, item in enumerate(args.items, 1):
        if cancel_event.is_set():
            emit("task_error", payload={"message": "Cancelado."}); return False

        item_name = _item_label(item)
        emit("queue_progress", payload={"current_item": idx, "total_items": total, "item_name": item_name})
        t0 = time()
        try:
            src = Path(item.value) if item.kind == "local" else download_image(item.value, IMAGE_SOURCE_DIR)
            input_thumb = _make_thumb(src)

            emit("image_op_start", payload={"operation": "describe", "item_name": src.name,
                                             "thumb": input_thumb, "item_idx": idx, "total_items": total})
            emit("log", payload={"message": f"[i] Analisando com {args.describe_model}…"})

            text = describe_image(src, model=args.describe_model, prompt=args.describe_prompt)
            out_path = save_description(src, IMAGE_PROCESSED_DIR, text)
            output_paths.append(str(out_path))

            # Emite descrição linha a linha no log
            for line in text.splitlines():
                if line.strip():
                    emit("log", payload={"message": line})

            emit("image_op_done", payload={
                "output_path": str(out_path),
                "thumb": None,          # sem output de imagem — viewer mantém single-pane
                "elapsed": f"{time()-t0:.1f}s", "item_idx": idx, "total_items": total,
                "src_size_bytes": src.stat().st_size, "out_size_bytes": out_path.stat().st_size,
            })
        except Exception as exc:
            failed_count += 1
            logger.warning("[!] Erro em '%s': %s", item_name, exc)
            emit("image_op_error", payload={"item_name": item_name, "message": str(exc)})

        if cancel_event.is_set():
            emit("task_error", payload={"message": "Cancelado."}); return False

    emit("task_done", payload={"output_paths": output_paths, "failed_count": failed_count})
    return len(output_paths) > 0
```

---

## 9. `_resolve_messages` / `_resolve_stage_label` (view.py)

As entradas de `"remove_bg"` já existem. Adicionar `"describe"`:

```python
# Em _OP_VERBS:
"describe": "Analisando",

# Em _OP_LABELS:
"describe": "Analisando imagem…",
```

---

## 10. `help_content.py`

```python
"image.rembg_model":    "u2net: geral (padrão, ~170MB). u2netp: rápido e leve (~4MB). silueta: compacto (~43MB). isnet: recortes precisos. humano: otimizado para pessoas. Todos rodam na CPU; 1ª execução baixa o modelo.",
"image.describe_model": "Modelo Ollama com suporte a visão. moondream-custom: leve e rápido (recomendado). llava:7b: mais capaz, mais lento. Configure num_thread em ollama/Modelfile.vision.",
"image.describe_prompt": "Instrução enviada ao modelo. Vazio = descrição geral em português (objetos, contexto, cores, texto visível).",
```

---

## 11. Checklist

### Core
- [ ] `src/core/image/background.py` — sem OMP_NUM_THREADS hardcoded
- [ ] `src/core/image/describe.py`
- [ ] `ollama/Modelfile.vision` + instruções de setup no README/CLAUDE.md

### Deps
- [ ] `pyproject.toml`: extra `[ai-image] = ["rembg[cpu]>=2.0.50"]`
- [ ] `ollama pull moondream && ollama create moondream-custom -f ollama/Modelfile.vision`

### GUI
- [ ] `ImageArgs`: campos `rembg_model`, `describe_model`, `describe_prompt`
- [ ] `_OPS`: entradas `remove_bg` e `describe`
- [ ] `_make_card`: guard de disponibilidade para `remove_bg`
- [ ] `rembg_block`: warning + segmented_selector (IDs como options, labels dict) + `_param_blocks["remove_bg"]`
- [ ] `describe_block`: model selector + prompt field + `_param_blocks["describe"]`
- [ ] `_set_running`: chama `_set_rembg_disabled` e `_set_desc_disabled`
- [ ] `_refresh_format_block`: `describe` e `favicon` sem bloco de formato
- [ ] `worker.py`: imports + checks + `_run_batch_rembg` + `_run_batch_describe`
- [ ] `_OP_VERBS` / `_OP_LABELS`: entry `"describe"`

### Help
- [ ] `help_content.py`: chaves `image.rembg_model`, `image.describe_model`, `image.describe_prompt`

---

## 12. Smoke tests

### remove_bg
- [ ] **Sem extra:** card "Remover fundo" desabilitado com tooltip; demais ops normais
- [ ] `uv sync --extra ai-image` → instala sem erro
- [ ] **1ª remoção:** log de download de modelo; PNG transparente em `output/image/processed/`
- [ ] **Before/After:** before = foto original; after = recorte sobre surface
- [ ] **Lote 3 imgs:** fila progride; sessão rembg reusada entre itens
- [ ] **Trocar modelo:** próxima execução cria nova sessão

### describe
- [ ] **Sem moondream-custom:** erro claro no log ao tentar executar
- [ ] **Execução normal:** log `[i] Analisando…` → linhas da descrição no log → `.txt` salvo
- [ ] **Before/After:** viewer fica em single-pane (input), sem Depois (saída é texto)
- [ ] **Prompt customizado:** resposta reflete o prompt enviado
- [ ] **Lote 2 imgs:** dois `.txt` independentes gerados
