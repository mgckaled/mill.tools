# Plano 3 — Fundação de ML (`core/ml` + acessor de embeddings) — plano de implementação

**Documento de execução — plano de implementação detalhado (teor técnico elevado)**
Data: 23 de junho de 2026 · Roadmap de origem: `docs/ROADMAP.md` (Plano 3) · Fundações: Planos 0/1/2 (✅) · Padrão de referência: skill `architecture`

> **Invocação da skill.** Ao executar, **invoque a skill `architecture`**: núcleo puro (§1), camadas e quem-importa-quem (§2), limites de tamanho/coesão (§3), fluxo core → extra/gate → CLI → GUI → testes (§5), tipar dependência opcional sob `TYPE_CHECKING` (§7), checklist (§8).

> **Princípio do plano.** Espelhar `core/rag/` (gate `is_available()`, injeção de dependências, cache versionado) e **reusar o `VectorStore` já persistido** — sem recalcular embedding nenhum. A entrega é *fundação* (scaffolding + acessor + uma capacidade de prova de vida), não os algoritmos da onda semântica (esses são o Plano 4).

---

## Sumário

1. Objetivo e escopo
2. Achados (código + web) e a sacada da "fundação grátis"
3. Decisões de arquitetura
4. Desenho técnico
   - 4.1 Gate e dependências (`deps.py`)
   - 4.2 `features.py` — o acessor de embeddings (chunk/doc matrix)
   - 4.3 `dedup.py` — prova de vida (numpy puro)
   - 4.4 `store.py` — persistência de modelos versionada
   - 4.5 `types.py`
5. Reuso do RAG (sem recálculo)
6. CLI (prova de vida); GUI deferida ao Plano 4
7. Complexidade, memória e numerics (máquina-alvo)
8. Passos de implementação (commits)
9. Testes
10. Critérios de aceitação
11. Riscos e o que **não** fazer
12. O que destrava

---

## 1. Objetivo e escopo

Erguer o pacote `src/core/ml/` que os Planos 4 (semântico) e 5 (tabular) vão consumir: o **gate** do scikit-learn, o **acessor de embeddings** que transforma o `VectorStore` do RAG em matrizes prontas para ML (nível chunk e nível documento), a **convenção de persistência** de modelos treinados (versionada) e uma **capacidade de prova de vida** (deduplicação por similaridade) que valida o caminho RAG→ML ponta a ponta.

**No escopo:** `core/ml/` (`deps`, `features`, `dedup`, `store`, `types`), extra `[ml]`, CLI de dedup, testes. **Fora do escopo:** classificadores/clustering/regressão (Plano 4/5), qualquer GUI (a superfície semântica nasce no Plano 4), e qualquer recálculo de embeddings.

---

## 2. Achados (código + web) e a sacada da "fundação grátis"

**Inspeção do código.** O `VectorStore` (`core/rag/store.py`) já guarda tudo o que o ML precisa: `vectors: np.ndarray (N, D) float32` + `meta: list[ChunkMeta]` paralelo, com `ChunkMeta(source_path, kind, mtime, chunk_idx, text)`, persistido em `~/.mill-tools/rag/` (`vectors.npz` + `meta.json` + `index_info.json`). `VectorStore.load(dir, dim)` reidrata isso. Logo, o acessor é uma transformação pura sobre estruturas que **já existem**.

**A sacada — a fundação não custa dependência.** O acessor (numpy) e a deduplicação por cosseno (numpy) usam **apenas numpy**, que já é dependência-base (o RAG depende dele). Ou seja, a *fundação de ML* é **torch-free e sklearn-free**. O extra `[ml]` (scikit-learn) só é necessário para os **algoritmos** — classificação, clustering, regressão — que chegam nos Planos 4/5. Isso mantém a base mínima e entrega valor (dedup) sem nenhum `pip install` novo.

**Varredura web — persistência de modelos.** A documentação do scikit-learn é explícita: modelos **não** carregam de forma suportada entre versões diferentes da biblioteca; `joblib` é mais eficiente que `pickle` para arrays numpy grandes; e `skops.io` é a alternativa **segura** (não executa código arbitrário no load, ao contrário do pickle). *Influência:* o `store.py` de modelos grava um **sidecar de versão** (espelhando o `index_info.json` do RAG) e invalida no mismatch; `joblib` no v1, com `skops.io` como caminho de upgrade documentado.

Fontes na seção final.

---

## 3. Decisões de arquitetura

**`core/ml/` espelha `core/rag/`.** Mesma gramática: `is_available()` como gate (lazy import do sklearn), funções puras com dependências injetáveis (diretório do índice, função de carga), cache versionado em `~/.mill-tools/ml/`. Quem já entende o RAG entende o ML.

**Dois níveis de matriz, decididos no acessor.** ML semântico opera sobre **documentos**, mas o `VectorStore` guarda **chunks**. O acessor expõe os dois: `chunk_matrix` (cru) e `document_matrix` (mean-pool por `source_path`, L2-normalizado). A escolha de pooling (média) e normalização (cosseno) é tomada **uma vez**, no acessor, e herdada por todos os consumidores — evita que cada feature do Plano 4 reinvente a agregação.

**Camada:** `core/ml` importa `core/rag` (`VectorStore`, `ChunkMeta`) — `core → core` é permitido (skill §2). Sem Flet, sem DuckDB, sem `print`. sklearn/joblib sob `TYPE_CHECKING` + import preguiçoso.

**Fundação numpy-pura; algoritmos sob `[ml]`.** Acessor e dedup não gateiam (numpy base); só os algoritmos sklearn do Plano 4/5 checam `ml.is_available()`.

---

## 4. Desenho técnico

### 4.1 Gate e dependências (`core/ml/deps.py`)

```python
"""scikit-learn availability gate — mirrors rag.embedder.is_available()."""
from __future__ import annotations

SETUP_HINT = "Instale o extra de ML: uv sync --extra ml"

def is_available() -> bool:
    """True if scikit-learn can be imported (the [ml] extra is installed)."""
    try:
        import sklearn  # noqa: F401  (lazy, import-time only)
        return True
    except ImportError:
        return False
```

`pyproject.toml`: `ml = ["scikit-learn>=1.4"]` (1.4+ porque emite Polars/pandas como saída de transformadores — útil ao Plano 5). `joblib` vem como dependência transitiva do sklearn; `skops` fica como upgrade opcional, **não** adicionado agora.

### 4.2 `core/ml/features.py` — o acessor de embeddings

O coração da fundação. **numpy puro** (sem sklearn). Reusa `VectorStore`.

```python
@dataclass(frozen=True, slots=True)
class DocumentMatrix:
    X: "np.ndarray"          # (M, D) float32, L2-normalized (one row per document)
    source_paths: list[str]  # length M, parallel to X rows
    kinds: list[str]         # length M, the document kind

def chunk_matrix(store) -> tuple["np.ndarray", list["ChunkMeta"]]:
    """Raw chunk-level matrix + parallel metas (no copy beyond the store's)."""
    return store.vectors, store.meta

def document_matrix(store, *, l2_normalize: bool = True) -> DocumentMatrix:
    """Pool chunk vectors into one vector per source document.

    Pooling = mean of the chunk rows sharing a source_path; the mean is then
    (optionally) L2-normalized so downstream cosine/SVM/k-means operate on the
    unit sphere. Document order is first-seen (stable, deterministic).
    """

def load_document_matrix(directory: Path | None = None) -> DocumentMatrix:
    """Load the persisted RAG VectorStore and pool it (default ~/.mill-tools/rag)."""
```

**Detalhes técnicos do pooling.** Para cada `source_path` distinto, agrupa-se os índices de linha; `X_doc[d] = mean(vectors[idx], axis=0)`; se `l2_normalize`, `X_doc[d] /= (‖X_doc[d]‖ + 1e-8)`. Tudo em `float32` (sem promover para float64 — economiza metade da memória e basta para cosseno). A média de vetores já normalizados seguida de re-normalização é o *mean-pooling* canônico para embeddings de sentença/documento; é simples, robusto e determinístico. O `directory` é injetável (default = dir do índice RAG) para testabilidade, como o `connect_fn` do engine e o `embed_fn` do RAG.

### 4.3 `core/ml/dedup.py` — prova de vida (numpy puro)

Demonstra o caminho RAG→ML sem sklearn:

```python
@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    source_paths: list[str]  # documents mutually above the threshold
    score: float             # min pairwise cosine within the group

def near_duplicates(dm: DocumentMatrix, *, threshold: float = 0.95,
                    max_docs: int = 5000) -> list[DuplicateGroup]:
    """Group near-identical documents by cosine similarity over pooled vectors.

    S = dm.X @ dm.X.T  (M×M, vetores já normalizados → produto interno = cosseno);
    pares com S[i, j] >= threshold (i < j) viram arestas; componentes conexas
    são os grupos. Guard quadrático: acima de max_docs, aborta com aviso (o
    O(M²·D) cresce rápido; M> alguns milhares pede blocagem — fica como seam).
    """
```

Saída usável já no Plano 3 (CLI, seção 6) e reaproveitada pela Biblioteca "duplicatas/relacionados" no Plano 4.

### 4.4 `core/ml/store.py` — persistência de modelos versionada

Para o Plano 4/5 treinarem um modelo **uma vez** e reusarem. Convenção (não um modelo ainda):

```python
def model_dir() -> Path:                      # ~/.mill-tools/ml/
def save_model(model, name: str, *, signature: str) -> Path:
    """joblib.dump do modelo + sidecar JSON {sklearn_version, signature, created_at}."""
def load_model(name: str, *, signature: str):
    """Carrega só se o sidecar bater sklearn_version atual E signature; senão None
    (força retreino)."""
```

**Versionamento (da varredura).** O sidecar guarda `sklearn.__version__` e uma `signature` do conjunto de treino (ex.: hash de `(source_paths, mtimes, params)` — o mesmo princípio `(path, mtime)` do cache de `assess`/RAG). `load_model` devolve `None` se a versão do sklearn mudou (pickles não são portáveis entre versões) ou se a assinatura do corpus mudou → o consumidor retreina. `joblib` no v1 (eficiente para arrays); `skops.io` documentado como upgrade seguro.

### 4.5 `core/ml/types.py`

`DocumentMatrix`, `DuplicateGroup` (acima) e o que o Plano 4 acrescentar. Frozen + slots, como o resto do projeto.

---

## 5. Reuso do RAG (sem recálculo)

O fluxo é inteiramente sobre artefatos já existentes:

1. `VectorStore.load(~/.mill-tools/rag)` → `(vectors, meta)` (já persistido pelo RAG).
2. `features.document_matrix(store)` → `DocumentMatrix` (pool + normalização).
3. Consumidores: `dedup.near_duplicates(dm)` agora; no Plano 4, classificadores/clustering sklearn sobre `dm.X`.

Nenhuma chamada ao Ollama, nenhum re-embedding. O acessor é o único ponto que conhece o formato do `VectorStore` — se o store mudar (ex.: migrar para `sqlite-vec`, já citado como caminho no `store.py` do RAG), só `features.py` muda.

---

## 6. CLI (prova de vida); GUI deferida ao Plano 4

Paridade e demonstração via CLI, sem GUI nova nesta etapa (a superfície semântica — "duplicatas"/"relacionados" na Biblioteca, roteamento/escopo na IA — nasce no Plano 4):

```bash
uv run main.py ai dups [--threshold 0.95] [--scope transcription]
```

Carrega o índice, pool, roda `near_duplicates`, imprime os grupos (UTF-8 no stdout, padrão do `cli/ai.py`). Reusa o core direto, sem `CLIEventBus`. Índice ausente → dica para `ai index`.

---

## 7. Complexidade, memória e numerics (máquina-alvo)

**Memória.** `vectors` é `(N, D=768) float32` → ~3 KB/chunk; centenas de milhares de chunks ≈ centenas de MB (o RAG já vive com isso). O `document_matrix` reduz para `(M, 768)` — M = nº de documentos, tipicamente dezenas a poucos milhares → poucos MB. Confortável nos 16 GB.

**Tempo.** O pool é O(N·D) (uma passada). O dedup é `X @ X.T` = O(M²·D); para M até ~poucos milhares é instantâneo na CPU; o `max_docs` guarda contra o crescimento quadrático e marca o ponto onde uma estratégia em blocos (ou `sqlite-vec`/ANN) entraria — **seam documentado, não implementado**.

**Numerics.** Tudo em `float32`; cosseno via produto interno de vetores normalizados (estável, com `+1e-8` no denominador, como o `VectorStore.search`). Determinismo: ordem first-seen no pooling; nos algoritmos do Plano 4, `random_state` fixo. Sem promoção a float64 (metade da memória, precisão suficiente para similaridade).

---

## 8. Passos de implementação (commits)

**Commit 1 — acessor + dedup (numpy puro; sem dependência nova).** `core/ml/{__init__,types,features,dedup}.py` + `tests/core/ml/test_features.py`/`test_dedup.py`. Verde + ruff. Já entrega a capacidade de dedup.

**Commit 2 — gate + extra `[ml]` + store de modelos.** `core/ml/deps.py`, `core/ml/store.py`; `pyproject.toml` extra `[ml]`; testes (`importorskip("sklearn")` no store). Verde + ruff.

**Commit 3 — CLI `ai dups`.** Ramo no `cli/ai.py` + teste de dispatch. Verde + ruff.

Ordem: núcleo numpy primeiro (risco zero, valor imediato), depois o scaffolding sklearn, depois a CLI. GUI fica para o Plano 4.

---

## 9. Testes

**`tests/core/ml/` (espelha `src/`, `__init__.py`):**

- `test_features.py` (numpy, **sem** importorskip): `document_matrix` — pooling correto (vetores de chunk sintéticos com `source_path` conhecido → média esperada por documento), L2-norma unitária quando `l2_normalize=True`, ordem first-seen, `float32` preservado, store vazio → matriz `(0, D)`, doc de 1 chunk → o próprio vetor normalizado. `chunk_matrix` devolve as referências do store. `load_document_matrix` lê um `VectorStore` persistido em `tmp_path` (reusa o round-trip do `store` do RAG).
- `test_dedup.py` (numpy): vetores com duplicatas plantadas (linhas idênticas/quase) → grupo correto no `threshold`; pares abaixo do limiar **não** agrupam; componentes conexas (A≈B, B≈C ⇒ {A,B,C}); `max_docs` excedido → aborta com aviso; matriz vazia → `[]`.
- `test_deps.py`: `is_available()` True com sklearn; False via `mocker.patch.dict(sys.modules, {"sklearn": None})` (padrão do `embedder`).
- `test_store.py` (`importorskip("sklearn")`): `save_model`/`load_model` round-trip em `tmp_path` (passe `model_dir` injetável/monkeypatch); **mismatch de versão** → `load_model` devolve `None` (mockar `sklearn.__version__`); **mismatch de signature** → `None`; sidecar ausente → `None`.

**CLI** — `tests/cli/test_ai_cli.py`: `ai dups` no parser (`--threshold/--scope`); dispatch chama `near_duplicates` (mock); índice vazio → mensagem/`sys.exit`.

Cobertura `core/ml/`: ≥ 90%. Tudo `@pytest.mark.unit` (numpy/sklearn rodam in-process).

---

## 10. Critérios de aceitação

- `core/ml/` espelha `core/rag/` (gate, injeção, cache versionado); puro (sem Flet/DuckDB/`print`); cada arquivo ≤ ~200 linhas.
- Acessor e dedup são **numpy-puros** (sem `[ml]`); reusam `VectorStore` sem recalcular embeddings; só os algoritmos futuros gateiam em `ml.is_available()`.
- Extra `[ml]` (scikit-learn ≥1.4); `store` versiona por `sklearn.__version__` + signature e invalida no mismatch; `joblib` no v1, `skops` documentado.
- `ai dups` funciona ponta a ponta sobre o índice real.
- `uv run pytest -m unit` verde; `ruff` limpo; cobertura `core/ml` ≥ 90%; checklist da skill `architecture` (§8) satisfeito.
- Nenhuma GUI alterada; nenhum recálculo de embedding.

---

## 11. Riscos e o que **não** fazer

**Escopo:** não implementar classificadores/clustering aqui — é Plano 4; a fundação entrega acessor + dedup + scaffolding. **Pooling:** não esconder variações de pooling por consumidor — a decisão é única, no acessor. **Persistência:** não assumir portabilidade de pickle entre versões de sklearn (o sidecar resolve). **Quadrático:** não rodar dedup sem o `max_docs` guard. **Dependência:** não puxar sklearn para o acessor/dedup (eles são numpy-puros — manter assim preserva a "fundação grátis"). **Acoplamento ao store:** todo conhecimento do formato do `VectorStore` fica em `features.py` — se o RAG migrar para `sqlite-vec`, só ali muda.

---

## 12. O que destrava

Concluído o Plano 3, o Plano 4 (onda semântica) apenas **consome** `features.document_matrix`: classificação de tipo (SVM/regressão logística do sklearn sobre `dm.X`), agrupamento temático (k-means/HDBSCAN), recomendação/escopo (cosseno, já no acessor) e a Biblioteca "duplicatas/relacionados" (reusa `dedup`). O `store` versionado guarda os classificadores treinados. Próximo elo: **Plano 4 — Inteligência semântica e textual**.

---

## Fontes

- [Model persistence — scikit-learn (versão, joblib, skops)](https://scikit-learn.org/stable/model_persistence.html)
- [scikit-learn model_persistence.rst (fonte)](https://github.com/scikit-learn/scikit-learn/blob/main/doc/model_persistence.rst)
