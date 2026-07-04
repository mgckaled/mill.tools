# PR6 — Módulo Biblioteca (Output Library)

> Plano de implementação detalhado. Corresponde ao **PR6** do roadmap revisado
> (Biblioteca → IA sobre corpus → Receitas). É a **camada de fundação** que
> habilita os PRs seguintes: sem um índice navegável das saídas, "conversar com
> um arquivo", batch LLM e automação não têm sobre o que operar.
>
> Princípios mantidos do projeto: **torch-free**, **sem dependência pesada nova**,
> **core puro reutilizável por CLI e GUI**, **código em inglês / labels em PT-BR**,
> **Flet 0.85**.

---

## 1. Objetivo e justificativa

Hoje cada módulo (Áudio, Vídeo, Imagens, Transcrição, Documentos) escreve em
`output/<kind>/...` e **esquece** o que produziu. Não há, dentro do app, forma de:

- ver tudo que já foi gerado, num só lugar;
- filtrar por tipo/data, buscar por nome;
- reabrir um arquivo ou sua pasta;
- reenviar uma saída para outro módulo (ex.: pegar um `.mp3` baixado e mandar
  para Transcrição) sem refazer o caminho manualmente.

A bridge `Áudio → Transcrição` (`nav[0]("transcription", {"file": path})`) já
prova o padrão de reaproveitamento entre módulos. A Biblioteca **generaliza essa
bridge para qualquer saída histórica**, e vira o substrato de PR7 (IA sobre o
corpus) e PR8 (receitas encadeadas).

### Por que isto antes do módulo de IA

O "chat com arquivo" precisa de uma lista de arquivos para escolher; o batch LLM
precisa de uma seleção; a busca semântica precisa de um corpus enumerado. Todos
consomem exatamente o que a Biblioteca expõe: **um índice tipado das saídas**.
Construir a IA primeiro obrigaria a reimplementar esse índice ad hoc.

---

## 2. Escopo

**Dentro do PR6:**

- Varredura e classificação de tudo sob `output/` num modelo tipado.
- Módulo GUI "Biblioteca": grade de cards com filtro por tipo, busca por nome,
  ordenação, thumbnails sob demanda.
- Ações por item: abrir arquivo, abrir pasta, **enviar para outro módulo**.
- Integração no registry (`app.py`), na Home e na NavigationRail.
- Persistência de preferências (filtro/ordenação) em `config.json`.
- Testes unitários do core (scanner, classificação, filtros).
- (Opcional) paridade CLI: `mill library list`.

**Fora do PR6 (vai para PRs seguintes):**

- Busca semântica / embeddings (PR7 — IA).
- Conversar com o conteúdo (PR7).
- Renomear em lote, mover, deletar arquivos (operações destrutivas — avaliar
  depois; exigem confirmação e undo).
- Tags manuais / coleções do usuário (futuro).

---

## 3. Decisões de arquitetura

| Decisão | Escolha | Justificativa |
|---|---|---|
| Origem da verdade | Varredura de `output/` (constantes de `utils.py`) | Os módulos já gravam lá; não criar um banco paralelo que precise ser mantido em sincronia. |
| Índice persistente | **Rescan on-mount** no v1; cache JSON opcional no PR6.5 | Escala pessoal (dezenas–centenas de arquivos) → rescan é instantâneo. Cache só quando o custo de `stat` aparecer. |
| Atualização ao vivo | Assinar `task_done` no EventBus + rescan ao montar | Evita dependência nova de `watchdog`; reaproveita o pubsub global. |
| Widget da grade | `ft.GridView` (renderização lazy nativa) | Renderiza só o visível + `cache_extent`. Ver §8 para o caveat de performance. |
| Busca | `ft.TextField` + `on_change`, **não** `ft.SearchBar` | `SearchBar` tem histórico de bugs de `on_change`/rebuild de `controls`. Coerente com a postura do projeto (abas manuais em vez de `ft.Tabs`). |
| Thumbnails | Gerados sob demanda em thread, reusando geradores existentes | Não bloquear a UI; reaproveitar `image/info.py`, raster de PDF e frame de vídeo. |
| Abrir arquivo | `os.startfile()` (Windows) | Casa com `subprocess.run(["explorer", dir])` já usado para pastas. |
| Pipeline/worker | **Nenhum** — a Biblioteca é majoritariamente read-only | Não há `worker.py`/`pipeline_log.py` como nos módulos de processamento. As ações disparam navegação ou abertura de arquivo, não pipelines. |
| Dependências novas | **Zero** | stdlib (`os`, `pathlib`, `time`) + Flet + geradores já presentes. |

---

## 4. Estrutura de arquivos

Espelhando a convenção `src/` ↔ `tests/`. Arquivos **novos** marcados com `+`.

```
src/
├── core/
│   └── library/                      +  (core puro — sem Flet)
│       ├── __init__.py               +
│       ├── types.py                  +  LibraryItem (dataclass) + KIND/CATEGORY consts
│       ├── scanner.py                +  scan_library(), classify_path(), filter_items(), sort_items()
│       ├── thumbnails.py             +  thumbnail_for(item) → bytes|None (dispatch por kind)
│       └── index.py                  +  (PR6.5) cache JSON opcional em ~/.mill-tools/
├── gui/
│   └── modules/
│       └── library/                  +
│           ├── __init__.py           +
│           ├── view.py               +  build_library_module(...) → Module
│           └── cards.py              +  build_item_card(item, ...) (factory local do módulo)
└── cli/
    └── library.py                    +  (opcional PR6.x) add_library_parser() + run_library_cli()

tests/
└── core/
    └── library/                      +
        ├── __init__.py               +
        ├── test_scanner.py           +  unit — classify_path, scan, filter/sort
        └── test_thumbnails.py        +  unit — dispatch (image real, fallbacks)
```

Arquivos **alterados**:

- `src/gui/app.py` — registrar o módulo em `MODULES` e passar `nav`.
- `src/gui/home.py` — 6º card; grade vira 3×2 simétrica.
- `src/gui/settings.py` — chaves `last_library_filter`, `last_library_sort`.
- `main.py` + `src/cli/library.py` (se fizer a paridade CLI).
- `CLAUDE.md` / `README.md` / skills — documentação ao final.

---

## 5. Camada core — indexação (`src/core/library/`)

Pura, sem importar Flet, testável de forma isolada (mesma regra dos demais `core/`).

### 5.1 `types.py`

```python
"""Typed model for an item stored under the project's output/ tree."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Logical kinds shown in the Library filter.
KIND_AUDIO         = "audio"
KIND_VIDEO         = "video"
KIND_IMAGE         = "image"
KIND_DOCUMENT      = "document"
KIND_TRANSCRIPTION = "transcription"


@dataclass(frozen=True, slots=True)
class LibraryItem:
    """A single file produced by any module, plus cheap filesystem metadata."""
    path: Path
    kind: str          # one of the KIND_* constants
    category: str      # "source" | "processed" | "text" | "analysis" | "digest"
    size_bytes: int
    modified: float    # st_mtime epoch seconds
    stem: str
    suffix: str        # lowercase, with dot (".mp3")
```

> `frozen=True` + `slots=True` torna o item barato e hashable (útil como chave de
> cache de thumbnail). Nenhum byte de thumbnail vive aqui — metadados apenas.

### 5.2 `scanner.py`

Mapeia cada diretório de saída (constantes já existentes em `utils.py`) para um
par `(kind, category)`, varre, classifica e oferece filtros puros.

```python
"""Filesystem scanner that turns output/ into a typed, filterable index."""
from __future__ import annotations

import logging
from pathlib import Path

from src.core.library.types import (
    LibraryItem, KIND_AUDIO, KIND_VIDEO, KIND_IMAGE, KIND_DOCUMENT, KIND_TRANSCRIPTION,
)
from src.utils import (
    AUDIO_SOURCE_DIR, AUDIO_PROCESSED_DIR,
    VIDEO_SOURCE_DIR, VIDEO_PROCESSED_DIR,
    IMAGE_SOURCE_DIR, IMAGE_PROCESSED_DIR,
    DOCUMENT_SOURCE_DIR, DOCUMENT_PROCESSED_DIR,
    TRANSCRIPTIONS_TEXT_DIR, TRANSCRIPTIONS_ANALYSIS_DIR, TRANSCRIPTIONS_DIGEST_DIR,
)

# Single source of truth: directory → (kind, category).
# Order defines default display priority within a kind.
LIBRARY_ROOTS: list[tuple[Path, str, str]] = [
    (AUDIO_SOURCE_DIR,            KIND_AUDIO,         "source"),
    (AUDIO_PROCESSED_DIR,         KIND_AUDIO,         "processed"),
    (VIDEO_SOURCE_DIR,            KIND_VIDEO,         "source"),
    (VIDEO_PROCESSED_DIR,         KIND_VIDEO,         "processed"),
    (IMAGE_SOURCE_DIR,            KIND_IMAGE,         "source"),
    (IMAGE_PROCESSED_DIR,        KIND_IMAGE,         "processed"),
    (DOCUMENT_SOURCE_DIR,         KIND_DOCUMENT,      "source"),
    (DOCUMENT_PROCESSED_DIR,      KIND_DOCUMENT,      "processed"),
    (TRANSCRIPTIONS_TEXT_DIR,     KIND_TRANSCRIPTION, "text"),
    (TRANSCRIPTIONS_ANALYSIS_DIR, KIND_TRANSCRIPTION, "analysis"),
    (TRANSCRIPTIONS_DIGEST_DIR,   KIND_TRANSCRIPTION, "digest"),
]


def classify_path(path: Path) -> tuple[str, str] | None:
    """Return (kind, category) for a path under a known output directory.

    Pure and unit-testable: derives the logical kind from the directory the
    file lives in, independent of file extension.
    """
    for root, kind, category in LIBRARY_ROOTS:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return kind, category
    return None


def scan_library(roots=LIBRARY_ROOTS) -> list[LibraryItem]:
    """Walk every output directory and build a flat, mtime-desc list of items.

    Missing directories are skipped silently (a fresh install has none yet).
    """
    items: list[LibraryItem] = []
    for root, kind, category in roots:
        if not root.exists():
            continue
        for p in root.iterdir():
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                logging.debug("[d] Skipping unreadable file: %s", p)
                continue
            items.append(LibraryItem(
                path=p, kind=kind, category=category,
                size_bytes=st.st_size, modified=st.st_mtime,
                stem=p.stem, suffix=p.suffix.lower(),
            ))
    items.sort(key=lambda it: it.modified, reverse=True)
    return items


def filter_items(
    items: list[LibraryItem], *,
    kinds: set[str] | None = None,
    query: str | None = None,
    since: float | None = None,
) -> list[LibraryItem]:
    """Pure filter: by kind set, case-insensitive name substring, and min mtime."""
    out = items
    if kinds:
        out = [it for it in out if it.kind in kinds]
    if query:
        q = query.casefold()
        out = [it for it in out if q in it.path.name.casefold()]
    if since is not None:
        out = [it for it in out if it.modified >= since]
    return out


def sort_items(items: list[LibraryItem], *, by: str = "modified", desc: bool = True):
    """Pure sort by 'modified' | 'name' | 'size'."""
    keys = {
        "modified": lambda it: it.modified,
        "name": lambda it: it.path.name.casefold(),
        "size": lambda it: it.size_bytes,
    }
    return sorted(items, key=keys.get(by, keys["modified"]), reverse=desc)
```

Tudo aqui é **determinístico e sem I/O externo além de `stat`** → unit test
trivial (ver §11).

### 5.3 `thumbnails.py`

Dispatch por `kind`, reaproveitando geradores já existentes. Retorna `bytes`
PNG/JPG (que o `ft.Image` 0.85 aceita direto — ver §8) ou `None` para cair no
ícone de tipo.

```python
"""Lazy thumbnail dispatch for Library items. Reuses existing generators."""
from __future__ import annotations

import logging

from src.core.library.types import (
    LibraryItem, KIND_IMAGE, KIND_DOCUMENT, KIND_VIDEO,
)

_THUMB_PX = 256


def thumbnail_for(item: LibraryItem) -> bytes | None:
    """Return preview bytes for an item, or None to fall back to a type icon.

    - image    → src.core.image.info.thumbnail_bytes (already exists)
    - document → first page rasterized via pymupdf (hard dep)
    - video    → single frame via ffmpeg (piped, no temp file)
    - audio / transcription → None (UI shows a type icon)
    """
    try:
        if item.kind == KIND_IMAGE:
            from src.core.image.info import thumbnail_bytes
            return thumbnail_bytes(item.path, max_size=_THUMB_PX)
        if item.kind == KIND_DOCUMENT and item.suffix == ".pdf":
            return _pdf_first_page(item.path)
        if item.kind == KIND_VIDEO:
            return _video_frame(item.path)
    except Exception as exc:  # never let a bad file break the grid
        logging.debug("[d] Thumbnail failed for %s: %s", item.path.name, exc)
    return None
```

> `thumbnail_bytes` já existe em `src/core/image/info.py`. O raster de PDF já
> existe inline em `document/view.py::_rasterize_first_page` — **refatorar para
> `src/core/document/info.py`** (função pública reutilizável) e chamar dos dois
> lugares, eliminando a duplicação. O frame de vídeo pode reusar a lógica de
> `src/core/video/converter.py` (thumbnail) adaptada para `pipe:1` em bytes.
> Áudio/transcrição usam ícone — gerar waveform de áudio aqui seria caro e fica
> para um polimento futuro.

**Cache em memória** (no módulo GUI, não no core): `dict[(path, mtime) → bytes]`,
populado pela thread de thumbnails. Invalidação automática porque a chave inclui
`mtime`.

---

## 6. Camada GUI — módulo Biblioteca (`src/gui/modules/library/`)

Segue o contrato `Module` (`src/gui/modules/base.py`): `control` construído uma
vez, estado preservado entre trocas de aba.

### 6.1 Assinatura e layout

```python
def build_library_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,                       # [navigate_to] — como no módulo Áudio
) -> Module:
    ...
```

Layout (sem o split `form | painel` dos módulos de processamento — aqui é uma
tela cheia de browsing):

```
┌───────────────────────────────────────────────────────────┐
│  [ Todos | Áudio | Vídeo | Imagens | Transcrição | Docs ]  │  ← segmented_selector (filtro por kind)
│  🔎 TextField "Buscar por nome…"        Ordenar: [▼ Data]  │  ← busca + sort
├───────────────────────────────────────────────────────────┤
│  GridView de cards (thumbnail/ícone + nome + badge + meta) │  ← lazy
└───────────────────────────────────────────────────────────┘
```

> (Esquema textual de layout, não um diagrama.)

### 6.2 Grade

```python
grid = ft.GridView(
    expand=True,
    max_extent=220,          # largura-alvo do card; nº de colunas se ajusta
    child_aspect_ratio=0.8,  # cards levemente verticais (thumb + 2 linhas de texto)
    spacing=Space.md,
    run_spacing=Space.md,
    cache_extent=400,        # pré-renderiza um pouco fora da viewport
)
```

`ft.GridView` renderiza apenas o visível + `cache_extent` (lazy nativo — ver §8).

### 6.3 Card de item (`cards.py`)

Factory local do módulo (não no design system global, pois é específico):

- Thumbnail (`ft.Image(thumb_bytes, fit=ft.BoxFit.COVER)`) ou ícone de tipo
  (`ft.Icon`) quando `thumbnail_for` retorna `None`. Cores de acento por kind
  reusam o mapa da Home (`Color.log.ok` para áudio, `Color.log.info` vídeo, etc.).
- Nome do arquivo (truncado), badge de categoria (`source`/`processed`/…),
  tamanho + data (`core/metadata.format_duration`-style helper para bytes/data).
- Clicável via `ft.GestureDetector(mouse_cursor=Cursor.interactive, ...)` —
  **nunca** `ink=True` (quirk documentado). Clique abre o menu de ações (§6.5).

### 6.4 Ciclo de vida e atualização

```python
def _rescan_and_render() -> None:
    items = sort_items(filter_items(scan_library(), kinds=_active_kinds, query=_query),
                       by=_sort_by, desc=True)
    _rebuild_grid(items)               # cria cards; thumbs entram via thread
    _spawn_thumbnail_thread(items)     # popula imagens conforme chegam

def _on_mount(payload: dict) -> None:
    _rescan_and_render()               # saídas novas aparecem ao entrar na aba

def _on_pipeline_done(event) -> None:
    # Assina o EventBus: quando QUALQUER módulo termina, marca para re-scan.
    if isinstance(event, PipelineEvent) and event.type == "task_done":
        _dirty[0] = True               # re-scan no próximo on_mount (barato)
```

A thread de thumbnails segue o padrão do `audio_player` (duas threads + geração
descartável): gera `thumbnail_for(item)` em background e, ao concluir cada um,
faz **update escopado do card** (`card_image.update()`), não `page.update()` —
crucial para a performance (§8). Um contador de geração (`_thumb_gen`) descarta
resultados de um scan anterior, igual ao `_load_generation` do player.

### 6.5 Ações por item (bridges)

Menu/row de ações no card (ou num painel de detalhe ao clicar):

| Ação | Implementação |
|---|---|
| **Abrir** | `os.startfile(path)` (Windows). |
| **Abrir pasta** | `subprocess.run(["explorer", "/select,", str(path)])`. |
| **Enviar para Transcrição** | `nav[0]("transcription", {"file": str(path)})` — só para áudio/vídeo. |
| **Enviar para Áudio** | `nav[0]("audio", {"file": str(path)})` — áudio/vídeo. |
| **Enviar para Imagens** | `nav[0]("image", {"file": str(path)})` — imagens. |
| **Enviar para Documentos** | `nav[0]("document", {"file": str(path)})` — PDFs. |

> **Pré-requisito de bridge:** padronizar `on_mount({"file": path})` em todos os
> módulos-alvo. Hoje **Áudio** (`fill_from_path`) e **Transcrição** já aceitam;
> **Imagens, Vídeo e Documentos precisam ganhar** o mesmo `on_mount` que
> pré-preenche o `InputSource`. Isso é parte do PR6.4 e tem valor além da
> Biblioteca (fortalece todas as bridges futuras).
>
> A navegação respeita o guard `pipeline_running[0]` já existente em
> `navigate_to` — nenhuma mudança no `app.py` além do registro.

---

## 7. Integração no registry e na Home

### 7.1 `app.py`

```python
from src.gui.modules.library.view import build_library_module

_library = build_library_module(page, bus, cancel_event, pipeline_running, nav)

# Ordem da rail — Biblioteca ao final (não altera o módulo default de abertura):
MODULES: list[Module] = [_audio, _video, _image, _transcription, _document, _library]
```

> **Decisão de ordem:** colocar a Biblioteca **por último** na rail evita mudar o
> `initial_module` default (`"transcription"`) e o comportamento de abertura.
> Alternativa a considerar: torná-la o novo hub default. Recomendo manter default
> atual no PR6 e reavaliar quando PR7/PR8 chegarem. Ícone sugerido:
> `ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED` / `_BOOKMARK` (selecionado).

`build_library_module` recebe `nav` (a lista forward-reference já usada por
Áudio/Vídeo) para as bridges. `cancel_event`/`pipeline_running` entram por
simetria de assinatura, mesmo sem pipeline.

### 7.2 `home.py`

O grid atual é 3 (topo) + 2 (centralizados com o truque `expand=2` e spacers).
Com 6 módulos vira **3×2 simétrico**, eliminando o hack:

```python
_MODULE_CARDS.append({
    "id": "library",
    "title": "Biblioteca",
    "icon": ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED,
    "accent": Color.dark.primary,   # dourado — o hub
    "desc": "Tudo que você já gerou, num só lugar",
    "features": [
        "Navegue e busque todas as saídas dos módulos",
        "Filtre por tipo e data; reabra arquivos e pastas",
        "Reenvie qualquer saída para outro módulo num clique",
    ],
})

cards_grid = ft.Column(controls=[
    ft.Row(controls=[cards[0], cards[1], cards[2]], spacing=Space.xl),
    ft.Row(controls=[cards[3], cards[4], cards[5]], spacing=Space.xl),  # simétrico
], spacing=Space.xl, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
```

Remove-se o ajuste `cards[3].expand = 2 / cards[4].expand = 2`.

---

## 8. Especificidades do Flet 0.85 (validadas)

| Ponto | Conclusão | Ação no plano |
|---|---|---|
| `ft.GridView` | Renderização **lazy nativa** (só o visível + `cache_extent`). Aceita `max_extent`/`runs_count`, `child_aspect_ratio`, `spacing`/`run_spacing`. | Usar `GridView` com `max_extent`. |
| Performance com muitos itens (issue **#6270**) | Em **milhares** de itens (4000+), `page.update()` passa de 1s no 0.80+; `Container` aninhado por célula piora. | (1) **Updates escopados** (`card.update()`), nunca `page.update()` na thread de thumbs. (2) **Cap/paginação**: exibir N (ex.: 120) + "Carregar mais". (3) Card enxuto, evitar aninhamento profundo de `Container`. |
| `ft.SearchBar` | Histórico de bugs em `on_change`/`on_submit` e rebuild de `controls`. | **Não usar.** Usar `ft.TextField(on_change=...)` com debounce simples. Coerente com "abas manuais em vez de `ft.Tabs`". |
| `ft.Image.src` aceita `bytes` | Confirmado no 0.85 (já documentado no CLAUDE.md). | Passar bytes do thumbnail direto, sem base64. |
| Trocas frequentes de imagem | `gapless_playback=True` evita flicker. | Aplicar ao `ft.Image` do card ao injetar o thumb. |
| Abrir arquivo no SO | `os.startfile(path)` (Windows). | Casa com o `explorer` já usado para pastas. |
| Container clicável | `ink=True` anula cursor do `GestureDetector`. | Card clicável via `GestureDetector` + `Cursor.interactive`, sem `ink`. |
| `ft.BoxFit` (não `ImageFit`) | Quirk 0.85 já mapeado. | `fit=ft.BoxFit.COVER` no thumbnail. |
| Roteamento | 0.85 introduziu Router, mas o projeto usa visibilidade em `ft.Stack`. | Manter o padrão `navigate_to` existente; **não** migrar para Router neste PR. |

---

## 9. Persistência (`settings.py`)

Acrescentar aos `_DEFAULTS`:

```python
"last_library_filter": "all",     # "all" | "audio" | "video" | "image" | "document" | "transcription"
"last_library_sort":   "modified" # "modified" | "name" | "size"
```

Lidas no `build_library_module` para restaurar o último estado; gravadas via
`settings.set(...)` em cada mudança de filtro/ordenação — mesmo padrão dos
dropdowns de Transcrição.

Cache de thumbnails em disco (PR6.5): `~/.mill-tools/thumb_cache/<sha1(path+mtime)>.png`,
limpável; **opcional**, só se o custo de regenerar (raster PDF / frame ffmpeg)
incomodar na máquina-alvo (MX150).

---

## 10. Paridade CLI (opcional)

Seguindo a skill `cli` (novo subcomando = `add_*_parser` + `run_*_cli` +
entrada em `_NON_TRANSCRIBE_CMDS`):

```bash
uv run main.py library list                       # tabela de tudo
uv run main.py library list --kind audio          # filtra por tipo
uv run main.py library list --since 7d --sort size
```

`run_library_cli` reaproveita `scan_library`/`filter_items`/`sort_items` e imprime
uma tabela (sem GUI). Útil e barato porque o core é o mesmo. Pode ficar para um
PR6.x se o foco inicial for a GUI.

---

## 11. Testes (skill `testing`)

Core é unit-testável; GUI fica fora da cobertura (`omit = src/gui/*`).

`tests/core/library/test_scanner.py` (`@pytest.mark.unit`):

- `classify_path`: cada diretório de `LIBRARY_ROOTS` → `(kind, category)`
  esperado; caminho fora de `output/` → `None`.
- `scan_library`: montar uma **árvore falsa de output** em `tmp_path` e
  redirecionar as constantes via `monkeypatch.setattr` (mesmo padrão do
  isolamento de `settings._CONFIG_FILE` na skill testing). Verificar contagem,
  ordenação por `mtime` desc e skip de diretórios inexistentes.
- `filter_items`: por `kinds`, por `query` (case-insensitive), por `since`;
  combinações.
- `sort_items`: por `name`/`size`/`modified`, asc/desc.

`tests/core/library/test_thumbnails.py` (`@pytest.mark.unit`):

- `thumbnail_for` em imagem real (fixture `jpg_image`) → `bytes` não-vazios
  (reusa `thumbnail_bytes`, já coberto).
- Áudio/transcrição → `None` (fallback de ícone).
- PDF via fixture `sample_pdf` (pymupdf é dep hard → continua `unit`, como os
  testes de `core/document/`).
- Arquivo corrompido → `None` sem propagar exceção (testar o `try/except`).

Regras herdadas: `__init__.py` vazio em `tests/core/library/`; imports do código
testado **dentro** da função de teste; alvo ≥ 90% no core novo.

---

## 12. Convenções a respeitar

- **Inglês** em docstrings/logs/comentários; **PT-BR** só em labels visíveis
  (títulos da Home, textos de ação, badges). Ao tocar `document/view.py` para
  extrair `_rasterize_first_page`, corrigir eventuais docstrings PT → EN na mesma
  passagem.
- `core/library/` **puro** — zero import de Flet.
- Logging via handler dedicado; nunca `print()`.
- Ruff limpo; `uv run pytest -m unit` verde antes de commit.

---

## 13. Faseamento sugerido

| Fase | Entrega | Testável isoladamente |
|---|---|---|
| **PR6.0** | `core/library/` (`types`, `scanner`) + testes unit | ✅ sem GUI |
| **PR6.1** | Módulo GUI read-only: grade com **ícones de tipo**, filtro por kind (`segmented_selector`), registro no `app.py` + Home 3×2 | manual (GUI) |
| **PR6.2** | Busca (`TextField`) + ordenação + filtro por data | core testável |
| **PR6.3** | Thumbnails lazy em thread (refatorar raster PDF p/ `core/document/info.py`; frame de vídeo) | core de thumbs testável |
| **PR6.4** | Ações: Abrir, Abrir pasta, **bridges**; adicionar `on_mount({"file"})` a Imagens/Vídeo/Documentos | — |
| **PR6.5** | Performance: cap/paginação, auto-refresh em `task_done`, cache de thumbs em disco; (opcional) CLI `library list` | core testável |

Cada fase é mergeável sozinha. PR6.0 entrega valor (índice + CLI futura) mesmo
antes de qualquer pixel de GUI.

---

## 14. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| GridView lento com muitos itens (#6270) | Cap/paginação (120/página), updates escopados, card enxuto. Acervo pessoal raramente passa de centenas. |
| Custo de thumbnails (raster PDF, frame ffmpeg) na MX150 | Geração em thread daemon; cache `(path, mtime)`; cache em disco no PR6.5; áudio/transcrição usam ícone. |
| Contenção GPU (Flet + ffmpeg/pymupdf simultâneos) | Thumbnails são CPU (pymupdf raster e ffmpeg frame único são leves); serializar geração numa única thread, não paralelizar. |
| Arquivos deletados fora do app → índice obsoleto | Rescan on-mount; `os.startfile` em caminho ausente tratado com `try/except` + toast. |
| Contrato de bridge divergente entre módulos | Padronizar `on_mount({"file": path})` em todos no PR6.4; cobrir o fill com teste de GUI mínimo onde possível. |
| `SearchBar` bugado | Já evitado — `TextField`. |

---

## 15. Definição de pronto (DoD)

- `uv run pytest -m unit` verde, cobertura do core novo ≥ 90%.
- Ruff sem warnings; docstrings/logs em inglês.
- Módulo aparece na rail e na Home (grade 3×2), abre sem quebrar `navigate_to`
  nem o guard `pipeline_running`.
- É possível: navegar, filtrar por tipo, buscar por nome, ordenar, abrir arquivo,
  abrir pasta e reenviar uma saída para outro módulo.
- Nenhuma dependência nova; projeto permanece torch-free.
- `CLAUDE.md`, `README.md` e skills atualizados (novo módulo, novos arquivos,
  contagem de testes).

---

## Apêndice — Pontos validados nesta análise

- **Flet `GridView` faz lazy rendering nativo** (só o visível + `cache_extent`);
  `max_extent`/`runs_count`/`child_aspect_ratio` confirmados.
- **Bug de performance #6270**: degradação de `page.update()` a partir de ~4000
  itens no Flet 0.80+ → mitigado por cap + updates escopados.
- **`ft.SearchBar`** com histórico de bugs de evento/rebuild → preferir
  `ft.TextField`.
- **`ft.Image.src` aceita bytes** no 0.85 (já registrado no CLAUDE.md), dispensando
  base64 para thumbnails.
