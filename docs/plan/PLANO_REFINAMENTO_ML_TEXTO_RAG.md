# Refinamento de qualidade — `core/ml` + `core/text` + RAG — plano de implementação

**Documento de execução — plano de implementação (teor técnico elevado)**
Data: 1 de julho de 2026 · Escopo: refinar a lógica já implementada nos Planos 3/4A/4B (`docs/PLANO_3_FUNDACAO_ML.md`, `docs/PLANO_4A_SEMANTICO.md`, `docs/PLANO_4B_SUPERVISIONADO_TEXTUAL.md`) e no RAG (PR7) · Restrição: **zero dependência nova** — só recursos mais elaborados de `scikit-learn`, `numpy`, `yake` e `spaCy`, já instalados.

> **Origem.** Este plano nasceu de uma pergunta direta: dá para ganhar qualidade/performance só refinando a lógica de ML existente, sem trazer biblioteca nova? A resposta é sim — os itens abaixo foram verificados por leitura do código atual **e** por pesquisa técnica dirigida (Context7 + web) sobre cada dependência já instalada, o que **corrigiu duas hipóteses iniciais** (documentado na seção 2).

---

## Sumário

1. Objetivo e escopo
2. Correções da pesquisa em relação à hipótese inicial
3. Tier 1 — correções (bug de recall + eficiência)
4. Tier 2 — ganho direto de qualidade
5. Tier 3 — ganho com guarda-corpo (parâmetros sensíveis ao tamanho do corpus)
6. Tier 4 — registrado, **não implementado nesta rodada**
7. Passos de implementação (commits por tier)
8. Testes
9. Critérios de aceitação
10. Riscos e o que **não** fazer
11. Tabela-resumo
12. Fontes

---

## 1. Objetivo e escopo

Nenhuma capacidade nova nasce aqui — este plano refina a **qualidade e a eficiência** de capacidades já entregues: pooling de embeddings (`core/ml/features.py`), clustering/projeção (`cluster.py`/`project.py`), classificação (`classify.py`), recomendação (`recommend.py`), extração de palavras-chave (`text/keywords.py`), resumo (`text/summarize.py`), entidades (`text/entities.py`) e recuperação do RAG (`rag/retriever.py`/`rag/store.py`).

**No escopo:** os itens dos Tiers 1–3 (seções 3–5), todos sem dependência nova. **Fora do escopo:** qualquer item do Tier 4 (seção 6) — registrado para referência futura, não agendado. **Fora do escopo também:** as features de ML inteiramente novas discutidas anteriormente (Planos 5/6/7 do `docs/ROADMAP_ML_DADOS.md` — tabular, mídia, operacional) — este plano é só refinamento do que já existe.

---

## 2. Correções da pesquisa em relação à hipótese inicial

A pesquisa técnica (scikit-learn/YAKE/spaCy oficiais + literatura) corrigiu duas suposições da lista original de 7 pontos:

- **HDBSCAN incremental não é viável sem dependência nova.** `prediction_data=True` + `approximate_predict()`/`membership_vector()` existem **apenas** no pacote standalone `hdbscan` (`scikit-learn-contrib/hdbscan`) — a classe `sklearn.cluster.HDBSCAN` (a que o projeto usa, dentro do `[ml]`) só expõe `fit`/`fit_predict`/`dbscan_clustering`, sem predição para pontos novos. Por isso este item vira Tier 4 (fora de escopo desta rodada).
- **O `dedupFunc` do YAKE não tem opção `"jaccard"`.** As opções reais são `leve` (Levenshtein), `jaro` e `seqm` (sequence matcher) — corrigido no item 2.3.

A pesquisa também **confirmou como já correta** uma escolha existente (`CalibratedClassifierCV(method="sigmoid")` em `classify.py` — Tier 4, sem ação) e trouxe um achado **não previsto**: a busca escopada do RAG filtra depois de rankear em vez de antes — um bug de recall real, não cosmético (Tier 1.1).

---

## 3. Tier 1 — correções (bug de recall + eficiência) ✅

**Implementado** (commit `fc98a9f`, `src/core/rag/store.py` + `retriever.py`, testes em `tests/core/rag/test_store.py`/`test_retriever.py`). `uv run pytest -m unit` verde (1289 passed) + `ruff` limpo.

### 3.1 Pré-filtro por escopo antes de rankear

**Arquivo:** `src/core/rag/retriever.py:41-46`, `src/core/rag/store.py` (`VectorStore.search`).

**Problema.** `retrieve(scope=...)` busca o top-`k*3` **global** e só depois descarta o que não pertence ao escopo:

```python
hits = store.search(embed_query_fn(query), k=k * 3 if scope else k)
if scope:
    hits = [h for h in hits if h.meta.source_path == scope or h.meta.kind == scope][:k]
```

Um escopo por `source_path` (a "conversa sobre este documento" da GUI) é um filtro **seletivo** — poucos chunks pertencem a ele entre milhares no índice. A prática documentada em busca vetorial é filtrar por metadado **antes** de rankear justamente quando o filtro é seletivo; pós-filtro (buscar top-k' global e filtrar depois) tem recall ruim quando `k'` não é grande o bastante — e não há garantia de que `k*3` sempre baste. Resultado prático hoje: perguntas escopadas a um documento pouco "competitivo" globalmente podem devolver menos de `k` trechos, ou nenhum, mesmo quando o documento tem conteúdo relevante.

**Correção.** Estender `VectorStore.search` com uma máscara booleana opcional, aplicada **antes** do `argsort`:

```python
def search(
    self, query_vec: np.ndarray, k: int = 6, *, mask: np.ndarray | None = None
) -> list[RetrievedChunk]:
    """Return the top-k chunks by cosine similarity, optionally restricted to `mask`."""
```

`retriever.retrieve()` monta a máscara a partir de `store.meta` (`source_path == scope or kind == scope`) e passa direto — sem widen-then-filter, sem risco de recall perdido, e sem mudar a assinatura pública de `retrieve()`.

### 3.2 Cache de normalização em `VectorStore.search`

**Arquivo:** `src/core/rag/store.py:57-58`.

**Problema.** Toda chamada de busca recalcula a normalização da matriz inteira:

```python
mat = self.vectors / (np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8)
```

O(N·D) desperdiçado a cada pergunta ao RAG — a prática padrão em mecanismos de busca vetorial é normalizar uma vez e cachear.

**Correção — com uma ressalva importante.** `features.document_matrix()` faz a média dos vetores **brutos** de `store.vectors` antes de normalizar o pooled (Plano 3) — se `self.vectors` fosse normalizado na origem, a matemática de pooling mudaria sutilmente. Por isso o cache deve ser um atributo **separado**, só para busca:

```python
def __init__(self, dim: int = 768) -> None:
    ...
    self._normalized: np.ndarray | None = None  # lazy cache, invalidated by add()/drop_source()

def _normalized_vectors(self) -> np.ndarray:
    if self._normalized is None:
        self._normalized = self.vectors / (
            np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8
        )
    return self._normalized
```

`add()` e `drop_source()` zeram `self._normalized = None`. `self.vectors` continua cru — nenhuma mudança de comportamento em `features.py`.

---

## 4. Tier 2 — ganho direto de qualidade

### 4.1 MMR (Maximal Marginal Relevance) em `recommend.py` e `summarize.py`

**Arquivos:** `src/core/ml/recommend.py:49-57` (`related()`), `src/core/text/summarize.py:77` (`extractive_summary()`).

Ambas as funções hoje pegam o top-k por **score bruto** sobre uma matriz de similaridade já calculada — `related()` pode recomendar 5 documentos quase idênticos entre si; `extractive_summary()` pode escolher duas frases quase redundantes, desperdiçando a cota de sentenças.

**Fórmula** (Carbonell & Goldstein, 1998):

```
MMR = argmax_{i ∈ R\S} [ λ · Sim(i, âncora) − (1−λ) · max_{j ∈ S} Sim(i, j) ]
```

`S` = já selecionados, `R` = candidatos restantes, λ ≈ 0.5–0.7 (relevância vs. diversidade). É um laço guloso simples sobre uma matriz de cosseno **que ambas as funções já montam** — `numpy` puro, sem sklearn adicional.

```python
def mmr(
    query_sim: np.ndarray,      # (n,) relevância de cada candidato ao ponto de ancoragem
    pairwise_sim: np.ndarray,   # (n, n) similaridade candidato-candidato
    k: int,
    *, lambda_: float = 0.6,
) -> list[int]:
    """Greedy MMR selection: balances relevance against redundancy with already-picked items."""
```

**Decisão de arquitetura — duplicar, não compartilhar.** `core/text` é deliberadamente independente de `core/ml` (documentado no `CLAUDE.md` e no `PLANO_4B`). Criar um import cruzado por ~15 linhas de numpy quebraria essa fronteira; a função `mmr()` deve ser **duplicada** em `core/ml/recommend.py` e `core/text/summarize.py` — pequena o bastante para isso ser um custo aceitável.

### 4.2 c-TF-IDF com mais alcance

**Arquivo:** `src/core/ml/labeling.py:171` (`CountVectorizer`), `:188-200` (`_ctfidf`).

Hoje `CountVectorizer(stop_words=list(_STOPWORDS))` usa só unigramas (`ngram_range` default `(1,1)`). A documentação oficial do BERTopic recomenda `ngram_range=(1,3)` para corpora de frases curtas — produz rótulos de cluster como "aprendizado de máquina" em vez de só "aprendizado".

Bônus, mesma fórmula: o refinamento `reduce_frequent_words` do BERTopic troca `tf` por `sqrt(tf)` antes de multiplicar pelo IDF — reduz o peso residual de palavras comuns que sobrevivem à lista de stopwords. Em `_ctfidf()`:

```python
tf = counts / np.where(tokens_per_class == 0, 1, tokens_per_class)
tf = np.sqrt(tf)  # reduce_frequent_words (BERTopic)
```

### 4.3 Parâmetros do YAKE

**Arquivo:** `src/core/text/keywords.py:51` (`yake.KeywordExtractor(lan=lang, n=ngram, top=top_n)`).

- `dedupLim` (implícito em 0.9, o default) → baixar para ~0.7–0.8: limiar de similaridade de string acima do qual duas frases candidatas são consideradas duplicatas.
- `dedupFunc` (implícito em `"seqm"`, o default) → manter `"seqm"` (sequence matcher) em vez de tentar `"jaccard"`, que **não existe** nesta API; as opções reais são `leve`/`jaro`/`seqm`.
- `windowsSize` (implícito em 1) → 2–3: janela de co-ocorrência maior, mais adequada à sintaxe livre do português.

```python
extractor = yake.KeywordExtractor(
    lan=lang, n=ngram, top=top_n, dedupLim=0.75, dedupFunc="seqm", windowsSize=2
)
```

### 4.4 TextRank: `sublinear_tf` + viés de posição

**Arquivo:** `src/core/text/summarize.py:83-106` (`_textrank_scores`).

- `TfidfVectorizer(sublinear_tf=True)` — amortece frequência (escala log), prática padrão de TextRank para não deixar sentenças repetitivas dominarem a matriz de similaridade.
- **Viés de posição** (lead bias / "PositionRank"): somar ao score do PageRank um peso decrescente pela posição da sentença no texto. A literatura registra "TextRank puro" como fraco por ignorar posição — relevante para transcrições, que tendem a ter estrutura de abertura/fechamento.

```python
position_bias = np.array([1.0 / (1.0 + i) for i in range(n)])
position_bias /= position_bias.sum()
scores = 0.85 * pagerank_scores + 0.15 * position_bias  # peso a calibrar
```

LexRank foi cogitado como alternativa (mais robusto a ruído de fala) mas a pesquisa não achou evidência disso — descartado.

### 4.5 spaCy `EntityRuler` para termos de domínio

**Arquivo:** `src/core/text/entities.py`.

```python
if "entity_ruler" not in nlp.pipe_names:
    ruler = nlp.add_pipe("entity_ruler", before="ner")
    ruler.add_patterns(DOMAIN_PATTERNS)
```

Overhead baixo (casamento de padrão, não inferência); `overwrite_ents=False` (default) deixa o ruler complementar o NER estatístico sem sobrescrever — entidades sobrepostas resolvidas por comprimento (mais longa vence). **Único item do Tier 2 que exige trabalho de conteúdo antes do código**: uma lista de termos de domínio (nomes de modelo, siglas técnicas) que o `pt_core_news_sm` erra ou não reconhece — levantar essa lista é pré-requisito, não é uma tarefa de programação.

---

## 5. Tier 3 — ganho com guarda-corpo

### 5.1 `sklearn.manifold.TSNE` como 3º método de projeção

**Arquivo:** `src/core/ml/project.py` (`project_2d`).

Ao contrário do UMAP (extra `[ml-viz]` à parte), o `TSNE` já vem dentro do **`[ml]`** — o único ganho de projeção "de graça" para quem só tem o extra base. Restrição dura confirmada pela doc oficial: `perplexity` deve ser menor que `n_samples` (erro se violado, não apenas degradação). Heurística segura: `perplexity = min(30, (n_amostras - 1) / 3)`.

```python
def _tsne_2d(x: np.ndarray, random_state: int, pre_pca_dims: int) -> np.ndarray:
    from sklearn.manifold import TSNE
    x_pre = _maybe_pre_reduce(x, pre_pca_dims, random_state)  # mesmo padrão do UMAP
    perplexity = min(30, max(2, (len(x) - 1) / 3))
    return TSNE(
        n_components=2, random_state=random_state, perplexity=perplexity, init="pca"
    ).fit_transform(x_pre).astype(np.float32)
```

`method="tsne"` some ao `if/elif` de `project_2d`, gated só por `is_available()` (o `[ml]` já cobre).

### 5.2 Seleção automática de k via `silhouette_score`

**Arquivo:** `src/core/ml/cluster.py` (`_kmeans`).

Hoje `k` é sempre manual. Testar uma faixa (2 a `min(10, m-1)`) e escolher o maior `silhouette_score` é prática padrão, **mas** a doc oficial e a literatura alertam: o score fica instável abaixo de ~15–20 amostras por cluster candidato, é enviesado para clusters convexos/de densidade uniforme (nem sempre o caso num acervo pessoal) e custa O(n²) (irrelevante no nosso volume).

**Guarda-corpo:** só ativar auto-k quando `m` for grande o bastante para a faixa testada fazer sentido (ex.: `m >= 20`); abaixo disso, manter o comportamento atual (exigir `k` manual, `ValueError` se ausente).

```python
def _auto_k(x: np.ndarray, m: int, k_range: range = range(2, 11)) -> int:
    from sklearn.metrics import silhouette_score
    from sklearn.cluster import KMeans
    best_k, best_score = 2, -1.0
    for k in k_range:
        if k >= m:
            break
        labels = KMeans(n_clusters=k, random_state=_RANDOM_STATE, n_init="auto").fit_predict(x)
        score = silhouette_score(x, labels)
        if score > best_score:
            best_k, best_score = k, score
    return best_k
```

`_kmeans(x, k=None, m=...)` passa a aceitar `k=None` **somente** quando `m >= _MIN_FOR_AUTO_K` (ex. 20); caso contrário, mantém o erro atual pedindo `k` explícito.

---

## 6. Tier 4 — registrado, **não implementado nesta rodada**

| Item | Situação | Motivo |
|---|---|---|
| **All-but-the-top** no pooling (`features.py`) | Experimental/condicional | Técnica real (Mu, Bhattacharya & Viswanath, ICLR 2018) para reduzir anisotropia de embeddings poolados, mas o paper assume vocabulários de centenas de milhares de itens; com um acervo pessoal de dezenas a poucos milhares de documentos e D=768, a estimativa das componentes principais fica estatisticamente instável — pode remover sinal semântico real em vez de ruído de frequência. Se algum dia implementado: só como opção não-padrão, removendo no máximo 1–2 componentes, e só acima de um piso de corpus (~200+ documentos). |
| **Pooling ponderado pelo tamanho do chunk** (`features.py`) | Seguro, mas fora desta rodada | Diferente do item acima, não tem o problema estatístico de PCA em amostra pequena — é uma média ponderada simples. Fica fora só por escopo desta rodada; é o candidato mais natural para um Tier 2 futuro caso o pooling simples se mostre insuficiente na prática. |
| **`PCA(whiten=True)`** (`project.py`) | Rejeitado | No scatter do mapa semântico, um eixo dominar por carregar mais variância costuma ser sinal genuíno da estrutura do corpus; whitening apagaria essa informação de importância relativa. Não implementar. |
| **`CalibratedClassifierCV(method="sigmoid")`** (`classify.py`) | Confirmado correto — nenhuma ação | A doc oficial do scikit-learn desaconselha `isotonic` com poucas amostras de calibração (≪1000) por tender a overfit; `classify.py` usa `min_per_class=2` e `cv=min(5, min_class_count)`, ordens de grandeza abaixo disso — sigmoid é a escolha certa enquanto os rótulos por classe forem poucos. Nota para o futuro: scikit-learn ≥1.8 introduziu `method="temperature"` (calibração multiclasse nativa via softmax) — reavaliar só após upgrade de versão. |
| **HDBSCAN incremental** (`prediction_data`/`approximate_predict`) | Fora de escopo — exige dependência nova | Só existe no pacote standalone `hdbscan`, não em `sklearn.cluster.HDBSCAN` (o que o projeto usa). Se este recurso for desejado no futuro, é um plano à parte que abre mão da restrição "zero dependência nova" desta rodada. |

---

## 7. Passos de implementação (commits por tier)

**Tier 1 (commit único ou dois pequenos):** `rag/store.py` (máscara em `search` + cache de normalização) + `rag/retriever.py` (monta a máscara a partir do escopo) → `uv run pytest -m unit` verde antes de seguir.

**Tier 2 (um commit por engine, ou agrupado):** `ml/recommend.py` + `text/summarize.py` (MMR duplicado) · `ml/labeling.py` (ngram + sqrt) · `text/keywords.py` (params YAKE) · `text/summarize.py` (sublinear_tf + lead bias, mesmo commit do MMR ali) · `text/entities.py` (EntityRuler — só depois de levantar a lista de termos, pode ficar para o final do tier). `uv run pytest -m unit` verde entre cada um.

**Tier 3 (um commit por item):** `ml/project.py` (TSNE) · `ml/cluster.py` (auto-k). `uv run pytest -m unit` verde.

Ordem entre tiers: 1 → 2 → 3, cada um validado antes do próximo — nenhum item de um tier depende de um tier posterior.

---

## 8. Testes

Cada item ganha teste(s) `@pytest.mark.unit` espelhando `tests/core/ml/`/`tests/core/text/`/`tests/core/rag/` existentes:

- **1.1** ✅ — `test_retriever.py`: escopo restritivo (documento com poucos chunks fora do top global) devolve `k` resultados quando existem `k` chunks naquele escopo; sem regressão no caminho sem escopo. Implementado como `test_retrieve_scope_returns_full_k_even_when_outranked_globally`.
- **1.2** ✅ — `test_store.py`: resultado de `search()` idêntico antes/depois do cache; cache invalidado após `add()`/`drop_source()` (comparar por identidade do array, não só valor). Implementado como `test_search_caches_normalized_vectors` + `test_add_invalidates_normalized_cache` + `test_drop_source_invalidates_normalized_cache` + os 3 testes de máscara.
- **2.1** — `test_recommend.py`/`test_summarize.py`: `mmr()` com candidatos sintéticos redundantes → seleção diversificada difere do top-k bruto quando há redundância; com candidatos já diversos, resultado coincide com top-k puro (regressão zero quando não há redundância).
- **2.2** — `test_labeling.py`: rótulo de cluster sintético com bigrama discriminativo aparece no resultado (não aparecia com `ngram_range=(1,1)`).
- **2.3** — `test_keywords.py` (`importorskip("yake")`): frases quase-duplicadas não aparecem duas vezes no top-N com os novos parâmetros.
- **2.4** — `test_summarize.py`: sentença inicial ganha score maior que uma sentença de conteúdo idêntico no meio do texto (efeito do lead bias).
- **3.1** — `test_project.py`: `method="tsne"` não lança com N pequeno (perplexity clampada); coordenadas `(M, 2)` float32.
- **3.2** — `test_cluster.py`: `k=None` com `m` grande escolhe um k plausível (testar com blobs sintéticos de k conhecido); `k=None` com `m` pequeno ainda lança `ValueError` (comportamento preservado).

Cobertura mantida ≥ 90% em `core/ml`/`core/text` (padrão já estabelecido nos Planos 3/4).

---

## 9. Critérios de aceitação

- Nenhuma dependência nova em `pyproject.toml`.
- `uv run pytest -m unit` verde e `ruff` limpo após cada tier.
- Tier 1: busca escopada nunca devolve menos resultados do que existem no escopo (até `k`); `VectorStore.search()` não recalcula norma em chamadas repetidas sem mutação.
- Tier 2: MMR reduz redundância mensurável em `related()`/`extractive_summary()` sem regressão no caso sem redundância; rótulos de cluster passam a incluir bigramas/trigramas quando discriminativos; YAKE não retorna frases quase-duplicadas com os novos parâmetros.
- Tier 3: TSNE disponível como opção sem exigir `[ml-viz]`; auto-k só ativa acima do piso de corpus definido, com fallback ao comportamento manual abaixo dele.
- Tier 4 permanece **não implementado** — nenhum destes itens deve aparecer em código nesta rodada.

---

## 10. Riscos e o que **não** fazer

Não aplicar all-but-the-top (Tier 4.1) como padrão — o risco estatístico em corpus pequeno é real e documentado. Não normalizar `self.vectors` em `VectorStore` na origem — quebraria a semântica de pooling do Plano 3; o cache de normalização é um atributo à parte. Não compartilhar a função `mmr()` entre `core/ml` e `core/text` via import cruzado — duplicar as ~15 linhas respeita a independência já decidida entre os dois pacotes. Não ativar auto-k sem piso mínimo de corpus — silhouette é instável em N pequeno. Não perseguir HDBSCAN incremental sem antes decidir, à parte, abrir mão da restrição de zero dependência nova.

---

## 11. Tabela-resumo

| # | Item | Arquivo | Tier | Risco | Esforço | Status |
|---|---|---|---|---|---|---|
| 1.1 | Pré-filtro por escopo antes de rankear | `rag/retriever.py`, `rag/store.py` | 1 | Baixo | Baixo | ✅ Implementado |
| 1.2 | Cache de normalização na busca | `rag/store.py` | 1 | Baixo | Baixo | ✅ Implementado |
| 2.1 | MMR em recommend + summarize | `ml/recommend.py`, `text/summarize.py` | 2 | Baixo | Baixo-Médio | Pendente |
| 2.2 | c-TF-IDF ngram(1,3) + sqrt(tf) | `ml/labeling.py` | 2 | Baixo | Baixo | Pendente |
| 2.3 | YAKE dedupLim/dedupFunc/windowsSize | `text/keywords.py` | 2 | Baixo | Baixo | Pendente |
| 2.4 | TextRank sublinear_tf + lead bias | `text/summarize.py` | 2 | Baixo | Médio | Pendente |
| 2.5 | spaCy EntityRuler | `text/entities.py` | 2 | Baixo | Médio (+ conteúdo) | Pendente |
| 3.1 | TSNE como 3º método | `ml/project.py` | 3 | Baixo-Médio | Médio | Pendente |
| 3.2 | Auto-k via silhouette | `ml/cluster.py` | 3 | Médio | Médio | Pendente |
| 4.1 | All-but-the-top | `ml/features.py` | 4 | Alto | — (não implementado) | Não fazer agora |
| 4.2 | Pooling ponderado por tamanho | `ml/features.py` | 4 | Baixo | — (não implementado) | Não fazer agora |
| 4.3 | PCA whiten | `ml/project.py` | 4 | — | Rejeitado | Rejeitado |
| 4.4 | CalibratedClassifierCV sigmoid | `ml/classify.py` | 4 | — | Já correto | Sem ação |
| 4.5 | HDBSCAN incremental | `ml/cluster.py` | 4 | — | Fora de escopo (dep. nova) | Fora de escopo |

---

## 12. Fontes

- [MMR — Diversity in Recommendations](https://aayushmnit.com/posts/2025-12-25-DiversityMMRPart1/DiversityMMRPart1.html) · [Maximal Marginal Relevance — Grokipedia](https://grokipedia.com/page/Maximal_Marginal_Relevance)
- [YAKE — Getting Started](https://liaad.github.io/yake/docs/-getting-started) · [yake.py — LIAAD/yake](https://github.com/LIAAD/yake/blob/master/yake/yake.py)
- [Biased TextRank (arXiv 2011.01026)](https://arxiv.org/pdf/2011.01026) · [LexRank — Erkan & Radev](https://www.cs.cmu.edu/afs/cs/project/jair/pub/volume22/erkan04a-html/erkan04a.html) · [Hybrid TF-IDF+TextRank](https://philarchive.org/archive/SHAHET-5)
- [spaCy — Rule-based matching](https://spacy.io/usage/rule-based-matching) · [spaCy API — EntityRuler](https://spacy.io/api/entityruler)
- [BERTopic — c-TF-IDF](https://maartengr.github.io/BERTopic/getting_started/ctfidf/ctfidf.html) · [BERTopic — Vectorizers](https://maartengr.github.io/BERTopic/getting_started/vectorizers/vectorizers.html)
- [Pre-filtering vs Post-filtering em busca vetorial](https://apxml.com/courses/advanced-vector-search-llms/chapter-2-optimizing-vector-search-performance/advanced-filtering-strategies) · [The Achilles Heel of Vector Search: Filters](https://yudhiesh.github.io/2025/05/09/the-achilles-heel-of-vector-search-filters/)
- [All-but-the-Top (ICLR 2018)](https://openreview.net/pdf?id=HkuGJ3kCb) · [Survey de sentence embeddings (SIF)](https://ar5iv.labs.arxiv.org/html/1702.01417)
- [sklearn.manifold.TSNE](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.TSNE.html)
- [sklearn.metrics.silhouette_score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html) · [Limitações do silhouette score](https://blog.dailydoseofds.com/p/the-limitation-of-silhouette-score)
- [hdbscan — prediction tutorial (pacote standalone)](https://hdbscan.readthedocs.io/en/latest/prediction_tutorial.html) · [sklearn.cluster.HDBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html)
- [sklearn.calibration.CalibratedClassifierCV](https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html)
- [sklearn.decomposition.PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html)
