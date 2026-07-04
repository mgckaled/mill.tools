# PR7 — Módulo IA / Conteúdo (RAG local sobre o corpus)

> Plano de implementação detalhado. Corresponde ao **PR7** do roadmap revisado
> (Biblioteca → **IA sobre corpus** → Receitas). Promove o LLM de
> pós-processamento embutido (em Transcrição/Imagens/Documentos) a **módulo de
> primeira classe** que opera sobre o acervo indexado pela Biblioteca (PR6).
>
> **Reframe consciente:** não é "mais uma caixa de chat" — é **RAG sobre o seu
> próprio conteúdo processado, 100% local**. O diferencial frente a
> ChatGPT/Claude/Open WebUI é estar ancorado nas suas transcrições, análises,
> textos de PDF e descrições de imagem — sem mandar nada para a nuvem (salvo se
> você optar por Gemini no passo de resposta).
>
> Princípios mantidos: **torch-free**, **core puro reutilizável por CLI e GUI**,
> **código em inglês / labels em PT-BR**, **Flet 0.85**, **roteamento de provider
> via `llm_factory`**.
>
> **Dependência de PR6:** o indexador consome `scan_library()`/`LibraryItem`. PR7
> pode ser construído em paralelo se essas duas peças do core da Biblioteca
> (`src/core/library/`) forem entregues primeiro (fase PR6.0).

---

## 1. Objetivo e justificativa

Hoje o LLM só existe **acoplado** a um módulo: formata/analisa transcrição,
descreve imagem, analisa PDF. Não há porta de entrada para **perguntar sobre o
que você já produziu**. PR7 abre essa porta com RAG (Retrieval-Augmented
Generation):

1. **Indexa** o corpus textual da Biblioteca (transcrições, análises, digests,
   texto extraído/OCR de PDF, descrições de imagem) em vetores de embedding.
2. **Recupera** os trechos mais relevantes para uma pergunta (busca semântica).
3. **Responde** com um LLM local (Ollama) ou em nuvem (Gemini opt-in),
   **citando as fontes** (itens da Biblioteca).

Tudo reaproveita a infra que **já existe**: `llm_factory.make_llm` (Ollama/Gemini),
`llm_utils.split_text` (chunking), o padrão `chain = prompt | llm` de
`analyzer.py`/`prompter.py`, o `EventBus`, o `run_queue_pipeline` e o design system.

### Por que isto depois da Biblioteca

RAG precisa de um corpus **enumerado e tipado** para indexar. `scan_library()`
(PR6) entrega exatamente isso. Construir a IA antes obrigaria a reimplementar a
varredura ad hoc.

---

## 2. Escopo

**Dentro do PR7:**

- Índice semântico local sobre saídas **textuais** (transcrição, análise, digest,
  texto de PDF, OCR, descrição de imagem).
- Embeddings via **Ollama** (`nomic-embed-text`, 768-dim, torch-free).
- Vector store leve (numpy `.npz` + metadados JSON; sem dep pesada).
- **Conversar com** um documento específico **ou com todo o acervo** (RAG com
  citação de fontes).
- **Prompt library** (prompts salvos) + **templates** (ata de reunião, e-mail,
  resumo executivo) aplicados a um documento/contexto.
- **Batch LLM**: rodar um prompt sobre uma seleção de itens (reusa
  `run_queue_pipeline`).
- Indexação incremental (só reembeda arquivos novos/alterados, por `mtime`).
- Integração no registry, Home e rail; bridge da Biblioteca ("Conversar sobre").
- Paridade CLI: `mill ai`.

**Fora do PR7 (futuro):**

- Embeddings de **imagem** (busca visual) — só texto agora.
- Conhecimento **externo**/web — estritamente o corpus local.
- Memória de conversa multi-turno persistente além da sessão (v1: histórico de
  sessão simples).
- ANN/FAISS — numpy basta na escala pessoal (ver §3).

---

## 3. Decisões de arquitetura

| Decisão | Escolha | Justificativa |
|---|---|---|
| Embeddings | Ollama **`nomic-embed-text`** (768-dim) via `langchain_ollama.OllamaEmbeddings` | Torch-free; **mesmo pacote** `langchain-ollama` já usado por `ChatOllama`; modelo pequeno (~270 MB), CPU-friendly. **Zero dep nova.** |
| Provider de embedding | **Sempre local** (Ollama) | O corpus é o ponto; mandar tudo para embedding na nuvem mataria a privacidade. Gemini não embeda aqui. |
| Provider de resposta | `llm_factory.make_llm` (Ollama **ou** Gemini opt-in) | Reaproveita o roteamento por prefixo existente. Gemini só no passo de resposta, com aviso de privacidade. |
| Vector store | **numpy** `(N, D)` em `.npz` + `meta.json` em `~/.mill-tools/rag/` | numpy cosseno aguenta ~200–500k chunks; acervo pessoal sobra. `sqlite-vec` fica como upgrade documentado. numpy já está no ambiente (stack de áudio) — declarar explícito no `pyproject`. |
| Chunking | `src/llm_utils.split_text` (já existe) | Consistência com analyzer/prompter; mesmo bypass de contexto longo p/ Gemini. |
| Fonte do índice | `scan_library()` (PR6), filtrando kinds textuais | Não duplicar varredura. |
| Incremental | Chave `(path, mtime, chunk_idx)`; só reembeda o que mudou | Custo de embedding é one-time amortizado; reconciliação remove chunks de arquivos apagados. |
| Recuperação | Cosseno top-k (numpy), com filtro de escopo (1 doc / kind / tudo) | Determinístico, testável, sub-ms na escala pessoal. |
| Resposta | Prompt estrito "responda só pelo CONTEXTO + cite fontes; senão diga que não achou" | Reduz alucinação; mostra rastreabilidade. |
| GPU | Embed model com `num_gpu 0` (CPU), como o `moondream-custom` | Não disputar os 2 GB da MX150 com o Whisper/Flet. |
| Dep nova | **Apenas `numpy` explícito** no `pyproject` (já resolvido no env) | Permanece torch-free, sem FAISS/Chroma. |

---

## 4. Estrutura de arquivos

Espelhando a convenção `src/` ↔ `tests/`. Novos com `+`.

```
src/
├── core/
│   └── rag/                          +  (core puro — sem Flet)
│       ├── __init__.py               +
│       ├── types.py                  +  Chunk, ChunkMeta, RetrievedChunk, AnswerResult
│       ├── embedder.py               +  embed_texts()/embed_query() via OllamaEmbeddings; is_available()
│       ├── store.py                  +  VectorStore: matriz numpy + meta; add/search/persist/load
│       ├── indexer.py                +  build_index(items, ...) — chunk+embed+store, incremental
│       ├── retriever.py              +  retrieve(query, k, scope) → list[RetrievedChunk]
│       ├── chat.py                   +  answer(query, ...) — RAG: retrieve → prompt|llm → AnswerResult
│       └── templates.py              +  prompt library + structured templates (ata/email/resumo)
├── gui/
│   └── modules/
│       └── ai/                       +
│           ├── __init__.py           +
│           ├── view.py               +  build_ai_module(...) → Module
│           ├── form_view.py          +  query input + scope + model dropdown + prompt-library
│           ├── worker.py             +  start_ai_pipeline (index/answer em thread)
│           └── pipeline_log.py       +  vocab: index_*, embed_progress, retrieve_*, answer_*
└── cli/
    └── ai.py                         +  add_ai_parser() + run_ai_cli()  ("ai" em _NON_TRANSCRIBE_CMDS)

tests/
└── core/
    └── rag/                          +
        ├── __init__.py               +
        ├── test_store.py             +  unit — cosseno, persist/load (numpy determinístico)
        ├── test_retriever.py         +  unit — top-k com embed_fn mockado
        ├── test_indexer.py           +  unit — chunking, incremental por mtime, reconciliação
        ├── test_chat.py              +  unit — RAG com GenericFakeChatModel + retriever mockado
        └── test_templates.py         +  unit — render de templates
```

Arquivos **alterados:** `src/gui/app.py` (registro), `src/gui/home.py` (7º card —
ver §7), `src/gui/settings.py` (chaves), `main.py` (dispatch `ai`), `pyproject.toml`
(numpy explícito), `CLAUDE.md`/`README`/skills.

---

## 5. Camada core — `src/core/rag/`

Pura, sem Flet. O único I/O externo é a chamada de embedding ao Ollama (isolada em
`embedder.py` e **injetável** como `embed_fn` para manter o resto testável sem rede).

### 5.1 `types.py`

```python
"""Typed models for the local RAG layer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChunkMeta:
    """Metadata for one embedded chunk (parallel to a row in the vector matrix)."""
    source_path: str   # the Library item the chunk came from
    kind: str          # "transcription" | "analysis" | "document" | ...
    mtime: float       # source mtime when embedded (for incremental refresh)
    chunk_idx: int
    text: str          # the chunk text (kept for retrieval/context building)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    meta: ChunkMeta
    score: float       # cosine similarity 0..1


@dataclass(frozen=True, slots=True)
class AnswerResult:
    text: str
    sources: list[Path]    # distinct source items cited
```

### 5.2 `embedder.py`

```python
"""Local embeddings via Ollama. The only network touchpoint of the RAG core."""
from __future__ import annotations

import logging

import numpy as np

DEFAULT_EMBED_MODEL = "nomic-embed-text"   # 768-dim, torch-free, CPU-friendly
EMBED_DIM = 768


def is_available(model: str = DEFAULT_EMBED_MODEL) -> bool:
    """True if langchain-ollama is importable and the embed model answers."""
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        return False
    try:
        OllamaEmbeddings(model=model).embed_query("ping")
        return True
    except Exception as exc:               # Ollama down or model not pulled
        logging.debug("[d] Embedder unavailable: %s", exc)
        return False


def embed_texts(texts: list[str], model: str = DEFAULT_EMBED_MODEL) -> np.ndarray:
    """Return an (N, EMBED_DIM) float32 matrix for the given texts."""
    from langchain_ollama import OllamaEmbeddings
    vecs = OllamaEmbeddings(model=model).embed_documents(texts)
    arr = np.asarray(vecs, dtype=np.float32)
    if arr.ndim == 2 and arr.shape[1] != EMBED_DIM:
        logging.warning("[!] Unexpected embedding dim %d (expected %d) — check the model.",
                        arr.shape[1], EMBED_DIM)
    return arr


def embed_query(text: str, model: str = DEFAULT_EMBED_MODEL) -> np.ndarray:
    """Return a (EMBED_DIM,) float32 vector for a single query."""
    from langchain_ollama import OllamaEmbeddings
    return np.asarray(OllamaEmbeddings(model=model).embed_query(text), dtype=np.float32)
```

> Validado: `OllamaEmbeddings(model="nomic-embed-text")` expõe
> `embed_query`/`embed_documents` e produz **768 dims**. Há um quirk conhecido
> (Ollama #10176) de configs que devolvem 8192 — por isso o `assert`/warning de
> dimensão acima.

### 5.3 `store.py`

```python
"""Tiny numpy-backed vector store. No new heavy dependency."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.core.rag.types import ChunkMeta, RetrievedChunk


class VectorStore:
    """In-memory cosine store with npz + json persistence."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.vectors = np.empty((0, dim), dtype=np.float32)
        self.meta: list[ChunkMeta] = []

    def add(self, vecs: np.ndarray, metas: list[ChunkMeta]) -> None:
        self.vectors = np.vstack([self.vectors, vecs]) if len(self.vectors) else vecs
        self.meta.extend(metas)

    def drop_source(self, source_path: str) -> None:
        """Remove all chunks of one source (apagado/alterado)."""
        keep = [i for i, m in enumerate(self.meta) if m.source_path != source_path]
        self.vectors = self.vectors[keep] if keep else np.empty((0, self.dim), np.float32)
        self.meta = [self.meta[i] for i in keep]

    def search(self, query_vec: np.ndarray, k: int = 6) -> list[RetrievedChunk]:
        if len(self.vectors) == 0:
            return []
        mat = self.vectors / (np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8)
        q = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        scores = mat @ q
        top = np.argsort(scores)[::-1][:k]
        return [RetrievedChunk(self.meta[i], float(scores[i])) for i in top]

    def persist(self, dir: Path) -> None:
        dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(dir / "vectors.npz", vectors=self.vectors)
        (dir / "meta.json").write_text(
            json.dumps([m.__dict__ for m in self.meta], ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, dir: Path, dim: int = 768) -> "VectorStore":
        store = cls(dim)
        if (dir / "vectors.npz").exists():
            store.vectors = np.load(dir / "vectors.npz")["vectors"].astype(np.float32)
            raw = json.loads((dir / "meta.json").read_text(encoding="utf-8"))
            store.meta = [ChunkMeta(**m) for m in raw]
        return store
```

### 5.4 `indexer.py`

```python
"""Incremental indexing of the Library corpus into the vector store."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.core.rag.types import ChunkMeta
from src.core.rag.store import VectorStore
from src.llm_utils import split_text

# Which Library kinds carry indexable text.
TEXT_KINDS = {"transcription", "document"}   # + image descriptions (.txt) when present
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


def _read_indexable_text(item) -> str:
    """Return the plain text body of a Library item (strip transcription header)."""
    raw = Path(item.path).read_text(encoding="utf-8", errors="replace")
    sep = "-" * 64
    return raw.split(sep, 1)[1].strip() if sep in raw else raw.strip()


def build_index(
    items: list,                       # list[LibraryItem] from scan_library()
    store: VectorStore,
    embed_fn: Callable[[list[str]], "np.ndarray"],
    *,
    progress_cb: Callable[[int, int], None] | None = None,
) -> VectorStore:
    """Embed new/changed text items; skip unchanged; drop deleted. Returns store."""
    indexed = {(m.source_path, m.mtime) for m in store.meta}
    text_items = [it for it in items
                  if it.kind in TEXT_KINDS and it.suffix in (".txt", ".md")]
    total = len(text_items)

    for n, item in enumerate(text_items, 1):
        key = (str(item.path), item.modified)
        if key in indexed:                       # unchanged → skip
            continue
        store.drop_source(str(item.path))        # changed → replace old chunks
        chunks = split_text(_read_indexable_text(item),
                            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
                            model_name="local")   # non-gemini → real chunking
        if chunks:
            vecs = embed_fn(chunks)
            metas = [ChunkMeta(str(item.path), item.kind, item.modified, i, c)
                     for i, c in enumerate(chunks)]
            store.add(vecs, metas)
        if progress_cb:
            progress_cb(n, total)

    # Reconciliation: drop chunks whose source no longer exists.
    alive = {str(it.path) for it in items}
    for gone in {m.source_path for m in store.meta} - alive:
        store.drop_source(gone)
    return store
```

### 5.5 `retriever.py` + `chat.py`

```python
# retriever.py
def retrieve(query, store, embed_query_fn, *, k=6, scope=None) -> list[RetrievedChunk]:
    """Embed the query and return top-k chunks, optionally filtered by scope.

    scope: None → whole corpus; a source_path str → that single document;
    a kind str → restrict to one kind.
    """
    hits = store.search(embed_query_fn(query), k=k * 3 if scope else k)
    if scope:
        hits = [h for h in hits
                if h.meta.source_path == scope or h.meta.kind == scope][:k]
    return hits
```

```python
# chat.py
from langchain_core.prompts import ChatPromptTemplate
from src.llm_factory import make_llm, is_gemini_model

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Você responde perguntas usando APENAS o CONTEXTO fornecido (trechos de "
     "documentos do usuário). Cite as fontes pelo número [n]. Se o contexto não "
     "contiver a resposta, diga claramente que não encontrou. Responda em "
     "português brasileiro, de forma objetiva."),
    ("human", "CONTEXTO:\n{context}\n\nPERGUNTA: {question}"),
])


def answer(query, retrieved, *, model_name="qwen7b-custom", on_event=None) -> "AnswerResult":
    """Build a cited context block from retrieved chunks and ask the LLM."""
    blocks, sources = [], []
    for i, h in enumerate(retrieved, 1):
        blocks.append(f"[{i}] ({Path(h.meta.source_path).name})\n{h.meta.text}")
        sources.append(Path(h.meta.source_path))
    context = "\n\n".join(blocks) if blocks else "(sem contexto)"
    chain = RAG_PROMPT | make_llm(model_name, temperature=0.2)
    resp = chain.invoke({"context": context, "question": query})
    return AnswerResult(text=resp.content, sources=list(dict.fromkeys(sources)))
```

> Bypass Gemini: com `is_gemini_model(model_name)` True, dá para aumentar `k`
> (contexto de 1M token) e reduzir o risco de cortar trechos — mesma heurística
> de `analyzer.py`/`prompter.py`.

### 5.6 `templates.py`

Dicionário de **prompts salvos** (resumir, traduzir, reescrever formal) e
**templates estruturados** (ata de reunião, e-mail, resumo executivo), cada um um
`ChatPromptTemplate` aplicado a um documento selecionado ou ao contexto recuperado.
Persistência editável em `~/.mill-tools/prompts.json` (defaults embutidos + os do
usuário).

---

## 6. Camada GUI — módulo IA (`src/gui/modules/ai/`)

Segue o contrato `Module`. Layout split, como os módulos de processamento:

```
┌────────────────────────┬──────────────────────────────────────┐
│ FORM (380px)           │  PAINEL                                │
│ • Escopo: [Este doc |  │  • Resposta (área rolável)             │
│   Acervo | Por tipo]   │  • Fontes citadas (output_card → item) │
│ • Modelo: [qwen7b | …] │  • Histórico da sessão                 │
│ • Prompt-library (chips)│  • Status do índice + "Reindexar"     │
│ • TextField pergunta   │  • barra/spinner do EventBus           │
│ • [Perguntar]          │                                        │
└────────────────────────┴──────────────────────────────────────┘
```

> (Esquema textual de layout, não um diagrama.)

- **Form** (`form_view.py`): `segmented_selector` de escopo, `Dropdown` de modelo
  (`qwen7b-custom`, `gemini-2.5-flash`), chips da prompt-library, `TextField`
  multiline de pergunta, `primary_button("Perguntar")`. Avisos de privacidade
  quando Gemini selecionado (mesmo padrão opt-in do resto).
- **Worker** (`worker.py`): em thread daemon. Dois fluxos:
  1. **Indexar**: `scan_library()` → `build_index(..., embed_fn, progress_cb)` →
     `store.persist()`. Emite progresso por chunk (`embed_progress`).
  2. **Responder**: `retrieve()` → `answer()`. Emite `answer_start`/`answer_done`.
  Reusa `EventBus`; `pipeline_log.py` traduz os eventos para o painel.
- **Resposta**: área rolável (`ft.ListView` lazy). **Streaming opcional** (PR7.4):
  `chain.stream()` do langchain atualizando a última linha via o padrão
  `mutable=True` que já existe (usado no progresso do yt-dlp).
- **Fontes**: cada item citado vira um `output_card` clicável → abre o arquivo /
  navega para a Biblioteca.
- **Estado do índice**: label "N documentos · M chunks · atualizado às HH:MM" +
  botão "Reindexar". Card desabilitado com aviso se `embedder.is_available()` for
  False ("⚠ Ollama/`nomic-embed-text` indisponível. Rode: `ollama pull nomic-embed-text`").
- **Bridge da Biblioteca (PR6):** "Conversar sobre" um item →
  `nav[0]("ai", {"file": path, "scope": path})` — o `on_mount` pré-seleciona o
  escopo "Este documento".

---

## 7. Integração no registry e na Home

### 7.1 `app.py`

> **Atualizado ao precedente do PR6 (hub no AppBar):** a IA é um módulo "meta"
> (opera sobre o corpus), como a Biblioteca — então **fica fora da rail** e ganha
> um **botão-hub no AppBar**, em vez de virar destino da NavigationRail. A rail
> permanece com as **5 ferramentas de processamento**.

```python
from src.gui.modules.ai.view import build_ai_module
_ai = build_ai_module(page, bus, cancel_event, pipeline_running, nav)

# IA continua em MODULES (Stack + navigate_to), mas FORA da rail —
# reusa a maquinaria do PR6: _RAIL_MODULES / _rail_index / botão no AppBar.
MODULES = [_audio, _video, _image, _transcription, _document, _library, _ai]
_RAIL_MODULES = [m for m in MODULES if m.id not in ("library", "ai")]  # rail = 5 ferramentas
```

- `_ai` recebe `nav` (bridges) e `pipeline_running` (índice/resposta bloqueiam a
  navegação, como os demais workers). Ícone sugerido: `ft.Icons.AUTO_AWESOME` /
  `_OUTLINED` (ou `PSYCHOLOGY`).
- No AppBar, adicionar um `TextButton` **"IA"** ao lado do botão **"Biblioteca"**
  (dourado quando ativo); `_rail_index("ai")` retorna `None` (rail deselecionada),
  igual ao tratamento de `library`.

### 7.2 `home.py` — launcher com 7 cards

A **rail não muda** (segue com 5 ferramentas); a IA entra como **hub no AppBar**,
como a Biblioteca. A Home é o *launcher* e mostra um card por módulo, incluindo os
hubs — então passa de 6 (PR6) para **7 cards** (5 ferramentas + Biblioteca + IA).
Layout sugerido: **4 + 3** (com spacers centralizando a fileira de 3, reusando o
truque de `expand` já existente). A narrativa por seções ("processar / acervo /
inteligência") pode ser reavaliada no PR8, quando chega o 8º card.

---

## 8. Especificidades do Flet 0.85

Reaproveita o que foi validado no PR6 (GridView lazy só onde houver grade; evitar
`SearchBar`; `ft.Image` aceita bytes; `os.startfile`; `ink=True` proibido;
`Cursor.*`). Específico do PR7:

| Ponto | Conclusão |
|---|---|
| Área de resposta rolável | `ft.ListView(auto_scroll=True)` — lazy, mesmo padrão do log dos outros módulos. |
| Resposta em streaming | `chain.stream()` (langchain) + atualização da última linha via `mutable=True` (padrão já existente no log). v1 pode ser `invoke()` único (sem streaming) para simplicidade. |
| Progresso de indexação | `progress_update(current/total)` por chunk embedado — barra determinada, igual ao áudio. |
| Bloqueio de navegação | `pipeline_running[0]` durante index/answer (guard já existe no `navigate_to`). |
| Markdown na resposta | `ft.Markdown` (0.85) para renderizar a resposta com citações `[n]`. |

---

## 9. Persistência

`settings.py` (`_DEFAULTS`):

```python
"last_ai_model":   "qwen7b-custom",
"last_ai_scope":   "all",            # "all" | "single" | "<kind>"
"last_embed_model": "nomic-embed-text",
```

- **Índice vetorial:** `~/.mill-tools/rag/vectors.npz` + `meta.json`.
- **Prompt library:** `~/.mill-tools/prompts.json` (defaults + custom do usuário).
- Mesma pasta `~/.mill-tools/` já usada por `config.json` — nada de novo no projeto.

---

## 10. Paridade CLI

Seguindo a skill `cli` (novo subcomando = `add_ai_parser` + `run_ai_cli` + entrada
em `_NON_TRANSCRIBE_CMDS`):

```bash
uv run main.py ai index                              # (re)indexa o corpus
uv run main.py ai "o que eu disse sobre faster-whisper?"   # pergunta ao acervo
uv run main.py ai "resuma" --scope output/transcriptions/text/x.txt
uv run main.py ai "..." --model gemini-2.5-flash --k 8
```

`run_ai_cli` reaproveita `scan_library`/`build_index`/`retrieve`/`answer` com um
`CLIEventBus` (sem GUI). Útil e barato — o core é o mesmo da GUI.

---

## 11. Testes (skill `testing`)

O core é unit-testável injetando `embed_fn`/`embed_query_fn` (sem Ollama real) e
mockando o LLM com `GenericFakeChatModel` (padrão de `analyzer.py`). GUI fora da
cobertura (`omit = src/gui/*`).

- `test_store.py`: `add`/`search` com vetores fixos (cosseno determinístico —
  vetor idêntico → score ≈ 1.0; ortogonal → ≈ 0); `drop_source`; `persist`/`load`
  round-trip em `tmp_path`.
- `test_retriever.py`: `embed_query_fn` mockado retornando vetor fixo → ordem top-k
  esperada; filtro de `scope` (1 doc / kind).
- `test_indexer.py`: corpus falso em `tmp_path` (LibraryItems sintéticos) +
  `embed_fn` mockado (retorna `np.ones`); asserta contagem de chunks, **skip
  incremental** ao reexecutar com mesmo `mtime`, **reembedding** ao mudar `mtime`,
  e **reconciliação** (arquivo removido → chunks somem). Mockar `split_text`? Não —
  é real e barato.
- `test_chat.py`: `answer(query, retrieved_fake, model_name=...)` com
  `make_llm` mockado via `GenericFakeChatModel` (como `test_analyzer.py`); asserta
  que o contexto numerado `[n]` é montado e que `sources` deduplica os paths.
- `test_templates.py`: render de cada template → estrutura de prompt esperada.
- `embedder.is_available()`: mockar import de `langchain_ollama` e a chamada
  (`mocker.patch(... OllamaEmbeddings)`), cobrir ramos disponível/indisponível.

Alvo ≥ 90% no core novo (exceto a linha de chamada real de rede em `embedder`,
que recebe `# pragma: no cover` onde fizer sentido).

---

## 12. Convenções a respeitar

- `core/rag/` **puro** — sem Flet; única dependência de runtime externo isolada em
  `embedder.py` e injetável como `embed_fn`.
- Inglês em docstrings/logs; PT-BR só em labels e prompts visíveis ao usuário.
- Reusar `make_llm`, `split_text`, `EventBus`, `run_queue_pipeline`,
  design system — **não** reimplementar.
- Logging dedicado; nunca `print()`. Ruff limpo; `uv run pytest -m unit` verde.

---

## 13. Faseamento sugerido

| Fase | Entrega | Testável isolado |
|---|---|---|
| **PR7.0** | `core/rag/` (`types`, `store`, `retriever`, `embedder`) + testes | ✅ sem GUI |
| **PR7.1** | `indexer` sobre o corpus da Biblioteca + CLI `ai index` / `ai "q"` | ✅ core |
| **PR7.2** | Módulo GUI: pergunta + escopo + resposta com fontes citadas; status/reindexar | manual (GUI) |
| **PR7.3** | Prompt library + templates (ata/e-mail/resumo) | ✅ core |
| **PR7.4** | Batch LLM sobre seleção (reusa `run_queue_pipeline`) + streaming de resposta | parcial |

PR7.0–7.1 entregam valor via CLI mesmo antes de qualquer pixel de GUI.

---

## 14. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Embed model não baixado | `embedder.is_available()` gateia; mensagem "rode `ollama pull nomic-embed-text`". |
| Indexar corpus grande é lento na CPU (i5-8265U) | Incremental por `mtime`; `progress_cb`; one-time amortizado; fila sequencial. |
| Contenção GPU (embed + Whisper/Flet) | Embed model com `num_gpu 0` (CPU), como `moondream-custom`. |
| Privacidade ao escolher Gemini | Embeddings **sempre locais**; aviso explícito de que os trechos recuperados vão à nuvem só no passo de resposta com Gemini (opt-in). |
| Alucinação | Prompt estrito "responda só pelo contexto + cite"; mostrar fontes; "não encontrei" quando retrieval vazio. |
| Índice obsoleto (arquivos apagados) | Reconciliação em `build_index` (drop de chunks órfãos); reindexar on-demand. |
| Quirk de dimensão do embedding (Ollama #10176) | `assert`/warning de `EMBED_DIM` em `embed_texts`. |
| numpy não declarado explicitamente | Adicionar `numpy` ao `pyproject` (já no env via stack de áudio). |
| Escala futura (>200k chunks) | Caminho de upgrade documentado para `sqlite-vec` sem trocar a interface do `VectorStore`. |

---

## 15. Definição de pronto (DoD)

- `uv run pytest -m unit` verde; cobertura do core novo ≥ 90%.
- Ruff limpo; docstrings/logs em inglês; labels/prompts PT-BR.
- Módulo IA como hub no AppBar (fora da rail) e card na Home (layout 7 cards), respeitando o guard
  `pipeline_running`.
- É possível: indexar o corpus, perguntar ao acervo **ou** a um documento, ver a
  resposta **com fontes citadas** clicáveis, reindexar incrementalmente, usar a
  prompt-library e ao menos um template estruturado.
- CLI `mill ai index` / `mill ai "pergunta"` funcionam.
- Embeddings 100% locais; Gemini só opt-in no passo de resposta, com aviso.
- Sem dependência pesada nova (só `numpy` explícito); projeto permanece torch-free.
- `CLAUDE.md`/`README`/skills atualizados (novo módulo, `core/rag/`, contagem de testes).

---

## Apêndice — Pontos validados nesta análise

- **`langchain_ollama.OllamaEmbeddings`** existe no **mesmo pacote** já usado
  (`ChatOllama`): `OllamaEmbeddings(model="nomic-embed-text")` com
  `embed_query`/`embed_documents`. **`nomic-embed-text` → 768 dims**, torch-free
  (roda no Ollama via llama.cpp).
- **Vector store**: numpy + SQLite/BLOB serve bem **até ~200–500k chunks**; acima
  disso, `sqlite-vec` (SIMD, C-level) é o upgrade natural. Para escala pessoal,
  **numpy cosseno puro basta** e mantém zero dep pesada.
- **Reuso máximo da infra existente**: `make_llm` (roteamento Ollama/Gemini),
  `split_text` (chunking + bypass Gemini), `EventBus`, `run_queue_pipeline`,
  design system — PR7 não introduz um segundo "jeito de falar com LLM".
