# Plano 4A — Inteligência semântica não-supervisionada (mapa + clusters) — plano de implementação

**Documento de execução — plano de implementação detalhado (teor técnico elevado)**
Data: 23 de junho de 2026 · Roadmap de origem: `docs/ROADMAP.md` (Plano 4, parte A) · Fundações: Planos 0/1/2/3 (✅) · Padrão de referência: skill `architecture`

> **Invocação da skill.** Ao executar, **invoque a skill `architecture`**: núcleo puro (§1), camadas (§2), limites/coesão e "divide-se ao tocar" (§3), `tabs/`/sub-builders (§4), fluxo core → extra/gate → CLI → GUI → testes (§5), `TYPE_CHECKING` (§7), checklist (§8).

> **Por que 4A separado do 4B.** O Plano 4 é a maior onda; partido por **técnica**. O **4A é não-supervisionado** — só geometria de embeddings (cluster, projeção, vizinhança), **sem rótulos e sem treino**, reusando `ml.features.document_matrix` (Plano 3) e o `charts` (Plano 1). O **4B** (separado) traz a classificação **supervisionada** (rótulos + `ml.store`) e os recursos textuais com deps novas (YAKE/sumy/spaCy). 4A não adiciona dependência **obrigatória** (roda sobre `[ml]` já instalado); só uma opcional (`[ml-viz]` para UMAP).

---

## Sumário

1. Objetivo e escopo
2. Achados da varredura web (decisões técnicas)
3. Decisões de arquitetura
4. Desenho técnico do núcleo (`core/ml/`)
   - 4.1 `cluster.py` — agrupamento (HDBSCAN/k-means)
   - 4.2 `project.py` — projeção 2D (PCA/UMAP)
   - 4.3 `labeling.py` — rótulo de cluster (c-TF-IDF)
   - 4.4 `recommend.py` — relacionados + escopo (cosseno)
   - 4.5 cache versionado e `types.py`
5. O mapa semântico (reuso do `charts` do Plano 1)
6. GUI (Biblioteca + IA) e CLI
7. Dependências, complexidade, numerics
8. Extensões opcionais (seams)
9. Passos de implementação (commits)
10. Testes
11. Critérios de aceitação
12. Riscos e o que **não** fazer
13. O que destrava (4B)

---

## 1. Objetivo e escopo

Entregar a camada semântica que **não precisa de rótulos**: descobrir os temas do acervo (clustering), nomeá-los automaticamente (c-TF-IDF), desenhar o **mapa semântico** (projeção 2D → PNG), recomendar documentos relacionados e detectar perguntas fora do corpus. Tudo sobre os embeddings já calculados (acessor do Plano 3).

**No escopo:** núcleo `core/ml/{cluster,project,labeling,recommend}.py` + `types`; extensão mínima do `charts` (scatter colorido por categoria); superfície na Biblioteca (modo **Mapa**) e na IA (aviso de fora-de-escopo); CLI (`ai topics`/`ai map`/`ai related`); extra opcional `[ml-viz]`; testes. **Fora do escopo:** classificação supervisionada, rótulos do usuário, NER/keywords/resumo textual (tudo isso é o 4B).

---

## 2. Achados da varredura web (decisões técnicas)

**Clustering com k desconhecido → HDBSCAN (default), k-means (opcional).** A varredura confirma: HDBSCAN **descobre o número de clusters sozinho**, lida com densidades variadas e formas arbitrárias, e marca ruído com rótulo **`-1`** — que reaproveitamos como "conteúdo órfão/isolado". Está em `sklearn.cluster.HDBSCAN` desde a 1.3 (**sem dependência nova** além do `[ml]`). k-means fica como alternativa quando se quer um nº fixo de grupos (exige `k`, sem ruído, assume clusters esféricos).

**Projeção 2D → PCA (default, sem extra); UMAP (opcional, melhor).** PCA é linear, instantânea, determinística e já vem no sklearn, mas "borra" estrutura local; UMAP preserva estrutura local+global e é o padrão moderno para embeddings, porém exige `umap-learn` (+`numba`). Decisão: **PCA por padrão** (zero dep nova) e **UMAP atrás de `[ml-viz]`** para o mapa mais bonito. Técnica reconhecida: usar **PCA como pré-redução** (ex.: →50D) antes do UMAP acelera e estabiliza — seam documentado.

**Rótulo de cluster → c-TF-IDF (BERTopic).** Em vez de TF-IDF ingênuo ou YAKE por cluster, usa-se **class-based TF-IDF**: cada cluster vira "um documento", e os termos pontuados são os **frequentes no cluster e raros no resto** — exatamente o que distingue um tema do outro. Implementável com `CountVectorizer` do sklearn + a fórmula c-TF-IDF (sem puxar o pacote BERTopic).

Fontes na seção final.

---

## 3. Decisões de arquitetura

**Tudo consome `features.document_matrix` (Plano 3).** Cluster, projeção, recomendação operam sobre `dm.X` (M×D, já L2-normalizado, ordem first-seen) — **sem recalcular embedding**. O acessor continua o único ponto que conhece o `VectorStore`.

**O mapa é PNG, pela fronteira do Plano 1.** O `charts` (`Figure`+`FigureCanvasAgg`, off-thread, paleta escura) é a **única fronteira matplotlib**; 4A apenas **estende** o `scatter` para colorir por categoria (cluster) e anotar centroides. Nenhum DataFrame/figura cruza para a GUI — só bytes PNG, como Plano 1/2.

**Núcleo puro, gate granular.** `core/ml/*` sem Flet/DuckDB. Cluster/projeção/labeling usam sklearn → gateiam em `ml.is_available()` (`[ml]`). Recomendação/escopo são **numpy-puros** (cosseno) → sem gate. UMAP gateia em `[ml-viz]`.

**Cache versionado (reuso do Plano 3).** Resultado de cluster+projeção+rótulos é caro o bastante para cachear: grava em `~/.mill-tools/ml/` com **signature do corpus** `(source_paths, mtimes)` + versões (`sklearn`, e `umap` se usado). Recalcula só quando o índice muda — mesmo princípio do `store` do Plano 3 e do cache de `assess`.

**"Divide-se ao tocar."** A Biblioteca já ganhou o modo **Painel** no Plano 2; 4A adiciona o modo **Mapa** num arquivo próprio (`library/semantic_map_panel.py`), sem inflar `library/view.py`.

---

## 4. Desenho técnico do núcleo (`core/ml/`)

### 4.1 `cluster.py` — agrupamento

```python
@dataclass(frozen=True, slots=True)
class ClusterResult:
    labels: "np.ndarray"     # (M,) int; -1 = noise/outlier (HDBSCAN)
    method: str              # "hdbscan" | "kmeans"
    n_clusters: int          # distinct labels excluding -1
    n_noise: int             # count of label == -1

def cluster_documents(dm, *, method="hdbscan", min_cluster_size=None,
                      k=None) -> ClusterResult:
    """Cluster pooled doc vectors. HDBSCAN (auto-k, noise=-1) by default;
    k-means when a fixed k is given. Lazy sklearn import; gated by is_available()."""
```

**Detalhes:** HDBSCAN com `metric="euclidean"` sobre vetores **L2-normalizados** ≈ cosseno (a distância euclidiana ao quadrado entre unit vectors é `2−2·cos`). `min_cluster_size` default heurístico `max(2, M // 50)` (ajustável). `labels == -1` → órfãos. Determinístico. k-means exige `k` e `random_state=42` (sem ruído; centroides). M pequeno (≤ ~poucos milhares) → instantâneo.

### 4.2 `project.py` — projeção 2D

```python
def project_2d(dm, *, method="pca", random_state=42,
               pre_pca_dims=50) -> "np.ndarray":  # (M, 2)
    """Project doc vectors to 2D for the semantic map.
    PCA (default, sklearn, free, deterministic) or UMAP (gated [ml-viz], better).
    For UMAP, optionally pre-reduce with PCA to pre_pca_dims for speed/stability."""
```

**Detalhes:** PCA(2) com **convenção de sinal** (fixar o sinal de cada componente pelo maior valor absoluto) → saída reprodutível bit-a-bit. UMAP via `[ml-viz]`, `random_state` fixo, `metric="cosine"`; PCA→50D antes (recomendação da varredura) quando M e D forem grandes. PCA pode "borrar" — por isso UMAP é o upgrade visual.

### 4.3 `labeling.py` — rótulo de cluster (c-TF-IDF)

```python
def label_clusters(doc_texts: list[str], labels: "np.ndarray",
                   *, top_n=5) -> dict[int, list[str]]:
    """Top-n discriminative terms per cluster via class-based TF-IDF (BERTopic).
    Concatenate each cluster's doc texts into one pseudo-document; score terms
    frequent in-cluster but rare across clusters; return the top_n per label."""
```

**Detalhes:** `doc_texts[d]` = concatenação dos chunks do documento `d` (de `ChunkMeta.text`, agrupados por `source_path` no acessor). c-TF-IDF: tf por classe (cluster) via `CountVectorizer`; idf = `log(1 + média_de_tokens_por_classe / freq_global_do_termo)`. Stopwords PT/EN simples (lista própria — sem dep nova). Ignora o cluster `-1` (órfãos). Saída: `{cluster_id: ["faster-whisper", "gpu", "transcrição", ...]}` → vira o **nome** do cluster na GUI/mapa.

### 4.4 `recommend.py` — relacionados + escopo (numpy puro)

```python
def related(dm, source_path: str, *, k=5) -> list[tuple[str, float]]:
    """Top-k documents most similar to source_path (cosine = dot of unit vectors)."""

def in_corpus(query_vec, store, *, threshold=0.35) -> tuple[bool, float]:
    """True if the best chunk cosine >= threshold (else the question is out of corpus)."""
```

**Detalhes:** `related` reusa `dm.X` normalizado: `scores = dm.X @ dm.X[i]`, exclui o próprio, top-k. `in_corpus` reusa `VectorStore.search` (top-1 score vs `threshold`); `threshold` é dependente do modelo de embedding → exposto como parâmetro/config, com default conservador calibrável. Ambos **sem sklearn**.

### 4.5 cache versionado e `types.py`

`types.py`: `ClusterResult`, `SemanticMap(coords, labels, cluster_names, source_paths, kinds)`. Cache: `corpus_signature(metas) -> str` (hash estável de `(source_path, mtime)` ordenados) + sidecar com versões; `load_map(sig)`/`save_map(map, sig)` em `~/.mill-tools/ml/`, invalida no mismatch (reusa o padrão do `store` do Plano 3).

---

## 5. O mapa semântico (reuso do `charts` do Plano 1)

O mapa é um **scatter** de `coords (M,2)`, colorido por `cluster_name`, com os **centroides anotados** pelos rótulos c-TF-IDF. Construção: monta-se um `pd.DataFrame{x, y, cluster, kind, name}` e chama-se o `charts`:

- Extensão mínima do `charts` (mantendo-o a única fronteira matplotlib): `scatter` passa a aceitar uma coluna `color` categórica (cores discretas da `ChartPalette`, legenda) e uma lista opcional de anotações `(x, y, text)` para rotular centroides. Nada de novo fora do `charts`.
- Render off-thread → PNG → `ft.Image` (padrão Plano 1/2). Salvo em `output/data/` (ou `output/` de IA) como artefato. Tema escuro via `ChartPalette` injetada.

Resultado: um "mapa de tudo que você já produziu", cada nuvem rotulada pelo seu tema, órfãos (cluster `-1`) em cinza. É a feature-vitrine que valida visualmente toda a cadeia Plano 0→3.

---

## 6. GUI (Biblioteca + IA) e CLI

**Biblioteca — modo Mapa (`library/semantic_map_panel.py`).** Novo modo (Grade·Lista·Painel·**Mapa**) no toggle existente. Mostra: o PNG do mapa + uma lista lateral de clusters (nome c-TF-IDF · contagem · documento-âncora) + ação **"Relacionados"** por item (usa `recommend.related`). Worker roda cluster+projeção+labeling off-thread (`page.run_task`+`asyncio.to_thread`), com gate de extras (sem `[ml]` → modo desabilitado com `SETUP_HINT`); usa o cache (não recomputa se o índice não mudou).

**IA — aviso de fora-de-escopo.** No fluxo de resposta, antes de gerar, `in_corpus(query_vec, store)`; se abaixo do limiar, a UI avisa "o acervo provavelmente não cobre isso" (ganho direto de confiabilidade), deixando o usuário seguir ou não. Pequena adição ao worker/`view` da IA.

**CLI (paridade, `cli/ai.py`):** `ai topics` (lista clusters + rótulos + tamanho), `ai map [--method pca|umap] [--out]` (gera o PNG), `ai related <path> [--k]`. Read-only, reusam o core, UTF-8. `ai dups` (Plano 3) já existe.

---

## 7. Dependências, complexidade, numerics

**Dependências.** Headline roda em `[ml]` (já instalado): HDBSCAN, k-means, PCA, `CountVectorizer`. **Nenhuma dep obrigatória nova.** Opcional: `[ml-viz] = ["umap-learn"]` só para a projeção UMAP. Imports preguiçosos; tipagem sob `TYPE_CHECKING`.

**Complexidade/memória (máquina-alvo).** `dm.X` = (M, 768) float32, M = docs (dezenas–milhares) → poucos MB. HDBSCAN ~O(M log M); PCA(2) O(M·D); c-TF-IDF O(total de tokens); `related` O(M·D). Tudo instantâneo na CPU para o porte pessoal. O custo real é a leitura/pool do índice — cacheado por signature.

**Numerics/determinismo.** float32; cosseno via produto interno de unit vectors; HDBSCAN determinístico; PCA determinística com convenção de sinal; UMAP com `random_state`. Órfãos = `label −1`, tratados explicitamente (excluídos de rótulos e centroides).

---

## 8. Extensões opcionais (seams)

Documentadas, **não** implementadas agora (entram quando pedidas, regra "divide-se ao tocar"):

- **Conteúdo órfão/isolado:** já temos `label == -1` do HDBSCAN — basta uma vista "isolados" na Biblioteca. Quase grátis.
- **"Você já falou sobre isso":** ao indexar um doc novo, rodar `related`/`dedup` e avisar sobreposição. Reusa `recommend`/`dedup`.
- **Âncora temática (medoid):** por cluster, o doc de maior similaridade média intra-cluster (`argmax` das somas de linha do bloco) como representante + mini-digest.
- **Agrupamento do índice por tópico na IA:** o mesmo `ClusterResult` exibido como navegação temática na aba Índice.
- **Linha do tempo semântica:** cruzar `cluster` × `mtime` (Plano 2) → temas por período.

---

## 9. Passos de implementação (commits)

**Commit 1 — núcleo numpy-puro.** `recommend.py` (related/in_corpus) + `types.py` (ClusterResult/SemanticMap) + testes. Sem dep, risco mínimo.

**Commit 2 — cluster + labeling (sklearn `[ml]`).** `cluster.py` (HDBSCAN/k-means) + `labeling.py` (c-TF-IDF) + cache por signature + testes (`importorskip("sklearn")`).

**Commit 3 — projeção + extensão do `charts`.** `project.py` (PCA; UMAP gated `[ml-viz]`) + `scatter` colorido/anotado no `charts` + testes.

**Commit 4 — CLI.** `ai topics`/`ai map`/`ai related` + testes de dispatch.

**Commit 5 — GUI Biblioteca (modo Mapa) + aviso de escopo na IA.** Smoke manual (construct-smoke + abrir o app, gerar mapa, ver rótulos/relacionados).

**Commit 6 — docs.** Registrar no `CLAUDE.md`/README/skills (padrão dos planos anteriores).

Ordem: núcleo testável → CLI → GUI; risco crescente; suíte verde entre commits.

---

## 10. Testes

**`tests/core/ml/`:**

- `test_recommend.py` (numpy): `related` — vizinhos plantados retornam no topo, exclui o próprio, respeita `k`; `in_corpus` — score acima/abaixo do limiar; store vazio.
- `test_cluster.py` (`importorskip("sklearn")`): blobs sintéticos bem separados → `n_clusters` esperado; pontos de ruído → `-1` e `n_noise`; k-means com `k` fixo; M<min_cluster_size → tudo ruído (borda).
- `test_labeling.py` (`importorskip("sklearn")`): clusters com vocabulário distinto → termos discriminativos corretos no topo; cluster `-1` ignorado; stopwords removidas.
- `test_project.py`: PCA → shape `(M,2)`, **determinismo** (duas execuções idênticas via convenção de sinal); UMAP `importorskip("umap")` → shape correto.
- `test_cache.py`: `corpus_signature` estável a reordenação; `save_map`/`load_map` round-trip em `tmp_path`; mismatch de signature/versão → `None`.

**`charts`:** `test_charts.py` ganha o caso `scatter` com `color` categórico + anotações → PNG válido (assinatura, abre no Pillow).

**CLI:** `tests/cli/test_ai_cli.py`: `topics`/`map`/`related` no parser + dispatch (mock do core); índice vazio → mensagem.

**GUI:** não headless → construct-smoke (`build_*` com `MagicMock`) + smoke manual. Cobertura dos núcleos novos: ≥ 90%.

---

## 11. Critérios de aceitação

- `core/ml/{cluster,project,labeling,recommend}.py` puros; recomendação/escopo **numpy** (sem gate); cluster/projeção/labeling gated em `[ml]`; UMAP em `[ml-viz]`.
- Reusa `features.document_matrix` (sem recalcular embedding) e o `charts` do Plano 1 (única fronteira matplotlib estendida minimamente).
- Mapa semântico gera PNG com clusters coloridos + centroides rotulados por c-TF-IDF; órfãos (`-1`) tratados; cache por signature evita recomputo.
- Biblioteca modo **Mapa** + "Relacionados"; IA com aviso de fora-de-escopo; CLI `topics`/`map`/`related`.
- **Nenhuma dep obrigatória nova** (só `[ml-viz]` opcional); contrato `QueryResult`/eventos preservado; nenhum DataFrame/figura cruza para a GUI.
- `uv run pytest -m unit` verde; `ruff` limpo; cobertura ≥ 90%; checklist da skill `architecture` (§8) satisfeito; `library/view.py` não inflado (modo Mapa em arquivo próprio).

---

## 12. Riscos e o que **não** fazer

**Escopo:** nada de classificação supervisionada/rótulos/NER/keywords aqui — é o 4B. **Pooling/normalização:** não reimplementar — vêm do acessor (Plano 3). **Matplotlib:** não criar segunda fronteira — estender o `charts`. **UMAP:** não torná-lo obrigatório (PCA é o default sem dep). **Quadrático:** `related`/cluster são O(M·…); para M grande, o cache + o `max_docs` do `dedup` valem como guarda — não rodar em loop por item sem cache. **Escopo (threshold):** não cravar τ — é dependente do embedding; expor e calibrar.

---

## 13. O que destrava (4B)

Com a geometria pronta, o **Plano 4B** acrescenta a camada **supervisionada e textual**: classificação de tipo (SVM/regressão logística do sklearn sobre `dm.X`, com rótulos e o `store` versionado do Plano 3), palavras-chave (YAKE), resumo extractivo (sumy) e NER (spaCy) — com a decisão de **origem dos rótulos** (heurística por pasta de `output/` / `kind` existente / rotulagem leve do usuário) tratada lá. O 4A já entrega, sozinho, o mapa, os temas nomeados e os relacionados.

---

## Fontes

- [HDBSCAN — scikit-learn (auto-k, noise=-1)](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html)
- [t-SNE vs UMAP vs PCA: Dimension Reduction — MetricGate](https://metricgate.com/blogs/dimensionality-reduction-tsne-vs-umap-vs-pca/)
- [PCA vs UMAP for HDBSCAN & t-SNE — GDELT (pré-redução PCA)](https://blog.gdeltproject.org/visualizing-an-entire-day-of-global-news-coverage-technical-experiments-pca-vs-umap-for-hdbscan-t-sne-dimensionality-reduction/)
- [c-TF-IDF — BERTopic (rótulo de cluster)](https://maartengr.github.io/BERTopic/getting_started/ctfidf/ctfidf.html)
- [BERTopic: class-based TF-IDF (paper)](https://arxiv.org/pdf/2203.05794)
