# Machine Learning e NLP clássicos — guia completo do mill.tools

Documento de conceito sobre o Machine Learning "clássico" (sem deep learning pesado, torch-free) e o
NLP textual do projeto: agrupar documentos, mapeá-los em 2D, achar relacionados e outliers,
classificar por perfil, e extrair palavras-chave/resumos/entidades. Cada técnica explicada do zero,
com analogia, e aterrada no seu código real de `src/core/ml/` e `src/core/text/`. Pré-requisito: o doc
**[`EMBEDDINGS.md`](EMBEDDINGS.md)** — quase tudo aqui opera sobre os vetores de documento (mean-pool)
que ele explica. Glossário no fim.

---

# PARTE 1 — O que é Machine Learning (e o que NÃO é aqui)

**Machine Learning (ML)** é fazer um programa **aprender padrões a partir de dados** em vez de você
codificar regras à mão. Duas grandes famílias:

- **Supervisionado:** você dá exemplos **rotulados** (texto → categoria) e o modelo aprende a prever o
  rótulo de exemplos novos. Ex.: classificar um documento como "aula" ou "entrevista".
- **Não-supervisionado:** você dá dados **sem rótulo** e o modelo acha estrutura sozinho. Ex.:
  **agrupar** documentos parecidos sem dizer quais grupos existem.

🔑 **O que o projeto NÃO faz:** deep learning pesado com PyTorch. Tudo aqui é **torch-free** — usa
`scikit-learn` (o extra `[ml]`) e numpy puro. É uma decisão deliberada (não disputar a GPU fraca, app
base leve). O "aprendizado" aqui é sobre os **embeddings que o RAG já produziu**, não treinar uma rede
do zero.

## 1.1 A fundação: tudo roda sobre os vetores de documento

🔑 A ponte com o doc de embeddings: o `ml/features.py` pega o `VectorStore` do RAG e faz o
**mean-pool** (média dos pedaços de cada documento → um vetor por documento), L2-normalizado. Essa
matriz `(M, 768)` — `M` documentos, 768 dimensões — é a **entrada de quase todo o ML clássico**. O ML
não re-embeda nada; ele **reusa** os vetores que o RAG já calculou. É por isso que este doc vem depois
do de embeddings: sem entender "documento = vetor", nada aqui faz sentido.

---

# PARTE 2 — Agrupar documentos (clustering)

**Clustering** = achar grupos naturais nos dados **sem** dizer quais grupos existem. Dado o conjunto
de vetores de documento, quais formam "nuvens" próximas no espaço? Cada nuvem é um assunto.

O seu `cluster.py` oferece dois algoritmos.

## 2.1 HDBSCAN (o padrão)

**HDBSCAN** é baseado em **densidade**: ele acha regiões onde os pontos estão apinhados e as declara
clusters; pontos em regiões vazias viram **ruído** (rótulo `-1`, reusado como "conteúdo isolado/órfão").

🔑 A grande vantagem sobre o k-means: **HDBSCAN descobre sozinho quantos grupos existem** — você não
precisa dizer "quero 5 grupos". E ele lida com clusters de tamanhos/densidades diferentes e admite que
alguns pontos simplesmente não pertencem a grupo nenhum (ruído). Para um acervo pessoal heterogêneo,
isso é o comportamento certo.

```python
def _hdbscan(x, min_cluster_size):
    from sklearn.cluster import HDBSCAN
    model = HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean", copy=True)
    return model.fit_predict(x).astype(int)
```

🔑 Note `metric="euclidean"` sobre vetores **L2-normalizados**. Por que euclidiano e não cosseno? O
comentário do arquivo explica com matemática: para vetores unitários, `‖a−b‖² = 2 − 2·cos(θ)` — a
distância euclidiana é **monótona** no cosseno (uma cresce quando a outra decresce). Então, com os
vetores já normalizados (doc de embeddings, Parte 3), o euclidiano padrão do HDBSCAN **equivale** a
usar cosseno, sem precisar de métrica custom. Um detalhe que só se entende sabendo da normalização.

## 2.2 k-means (a alternativa) e a auto-seleção de k

**k-means** é o clustering clássico: você diz **quantos** grupos quer (`k`), e ele parte os dados em
`k` grupos minimizando a distância de cada ponto ao centro do seu grupo. Simples e rápido, mas exige
saber `k` de antemão e assume grupos "redondos".

E quando você **não** sabe `k`? O projeto pode escolher automaticamente via **silhouette score** —
uma métrica de quão "bem separados e coesos" os grupos ficaram, para cada `k` candidato; vence o `k`
de maior score:

```python
def _auto_k(x, m):
    for k in _AUTO_K_RANGE:          # range(2, 11)
        labels = KMeans(n_clusters=k, random_state=42, n_init="auto").fit_predict(x)
        score = silhouette_score(x, labels)
        if score > best_score:
            best_k, best_score = k, score
    return best_k
```

🔑 Mas a auto-seleção só liga acima de `_MIN_FOR_AUTO_K = 20` documentos. Por quê? A silhouette é
**instável/enviesada** com poucas amostras por cluster candidato (o comentário cita "15-20 por
grupo") e é O(n²). Abaixo desse piso, `k` volta a ser um argumento obrigatório. E `random_state=42`
**semeia** o k-means para o mesmo corpus sempre dar a mesma partição (determinismo — importante para
não confundir o usuário com resultados que mudam a cada clique).

---

# PARTE 3 — Ver o invisível: redução de dimensão (o mapa semântico)

Os vetores têm 768 dimensões. Você não consegue **desenhar** 768 eixos numa tela. Para mostrar o
"mapa" dos seus documentos, é preciso **projetar** de 768D para **2D** preservando ao máximo as
distâncias — quem estava perto no espaço grande deve ficar perto no mapa. Isso é **redução de
dimensionalidade**. O `project.py` oferece três métodos, um trade-off clássico:

- **PCA (padrão):** Análise de Componentes Principais. Acha os eixos de **maior variância** dos dados e
  projeta neles. É **linear, instantâneo e determinístico** — mas pode "borrar" a estrutura local
  (grupos que estavam separados podem se sobrepor no mapa).
- **t-SNE:** ótimo em **separar visualmente** os clusters (revela estrutura local), mas é mais lento e
  pode distorcer distâncias globais. Vem no `[ml]` (não precisa de extra além dele).
- **UMAP:** o "padrão moderno" para embeddings — preserva estrutura **local e global** e é rápido, mas
  precisa do extra `[ml-viz]`.

```python
def project_2d(dm, *, method="pca", ...):
    if method == "pca":  return _pca_2d(dm.X, random_state)
    if method == "tsne": return _tsne_2d(dm.X, random_state, pre_pca_dims)
    if method == "umap": return _umap_2d(dm.X, random_state, pre_pca_dims)
```

🔑 Dois detalhes de engenharia: (1) para UMAP/t-SNE, os vetores são **pré-reduzidos com PCA** para ~50
dims antes (`_maybe_pre_reduce`) — prática consagrada, acelera e estabiliza os dois. (2) **Determinismo
de novo:** PCA ganha uma convenção de sinal (`_fix_signs`) para dois runs darem exatamente o mesmo
mapa, e t-SNE/UMAP rodam com `random_state` fixo. O tema "mesma entrada → mesmo resultado" é uma
obsessão saudável do projeto (o usuário não deve ver o mapa "pular" sem motivo).

---

# PARTE 4 — Relacionados e outliers

## 4.1 Documentos relacionados (`recommend.py`)

"Quais documentos são parecidos com este?" é só **similaridade de cosseno** entre o vetor do documento
âncora e todos os outros — produto escalar dos unitários (doc de embeddings). Mas com um cuidado: um
**cluster apertado de quase-duplicatas** poderia lotar o top-k. Solução: o **MMR** (o mesmo do RAG,
Parte 5.2 do doc de RAG — literalmente a mesma função `_mmr`, reusada), que diversifica os vizinhos.

```python
query_sim = cand_X @ dm.X[i]                 # cosseno do âncora contra todos (produto escalar)
pairwise_sim = cand_X @ cand_X.T             # similaridade entre os candidatos (para o MMR)
order = _mmr(query_sim, pairwise_sim, k, lambda_=lambda_)
```

🔑 Repare como o mesmo conceito (cosseno + MMR) serve a dois usos: recuperar contexto no RAG e sugerir
documentos relacionados na Biblioteca. É a economia conceitual do projeto — poucos motores, muitos
usos.

## 4.2 Detecção de outliers (`IsolationForest`)

No módulo Dados, `detect_outliers` acha linhas "anômalas" numa tabela via **Isolation Forest**. A
intuição do algoritmo é elegante: ele constrói árvores que **separam** pontos aleatoriamente; um ponto
anômalo (muito diferente dos demais) é **isolado com poucos cortes** (fica sozinho num galho raso),
enquanto um ponto normal exige muitos cortes. Quanto mais fácil isolar, mais anômalo. É rápido e não
supervisionado — não precisa de exemplos de "o que é anomalia".

---

# PARTE 5 — Classificar por perfil (zero-shot → supervisionado)

O `classify/` resolve "que tipo de documento é este?" (ex.: perfil de análise: aula, entrevista,
palestra) com uma escada elegante que **escala com o uso**.

## 5.1 Zero-shot por protótipo (funciona desde o primeiro documento)

**Zero-shot** = classificar **sem** exemplos de treino. Como? Você descreve cada categoria com uma
frase-semente ("uma aula, uma explicação didática..."), **embeda** essa frase (vira um **protótipo** —
um vetor que representa a categoria), e classifica um documento pela categoria cujo protótipo está
**mais próximo** (maior cosseno). Nearest-prototype — o vizinho mais próximo entre os protótipos.

🔑 A beleza: funciona **de cara**, sem você rotular nada, porque reusa o mesmo espaço de embedding. A
"margem" (diferença de cosseno para a 2ª categoria) vira uma medida de **incerteza**.

## 5.2 Supervisionado (quando você acumula rótulos)

Conforme você **confirma** perfis, o projeto acumula exemplos rotulados e pode treinar um modelo
**supervisionado** de verdade — um SVM linear calibrado (`LinearSVC` + `CalibratedClassifierCV`) sobre
os vetores. O `inference.py` **despacha** entre os dois:

```python
def classify(doc_vec, *, ..., embed_space_id="?"):
    labels = load_labels(...)
    if labels:
        model = load_model(_model_name(domain), signature=model_signature(labels, embed_space_id), ...)
        if model is not None:
            proba = model.predict_proba(doc_vec.reshape(1, -1))[0]   # ramo SUPERVISIONADO
            ...
            return Classification(..., "supervised")
    P, ids = profile_prototypes(embed_fn, ...)                        # ramo ZERO-SHOT (fallback)
    return classify_zeroshot(doc_vec, P, ids)
```

🔑 A lógica: usa o modelo treinado **se** existir um válido; senão, cai no zero-shot. "Válido" é a
parte sutil — a **assinatura** (`model_signature`) do modelo dobra o `embed_space_id`. Se você trocou
o modelo de embedding ou reindexou sob um esquema novo, a assinatura muda e o modelo antigo é
**descartado** (cai no zero-shot) em vez de prever lixo em silêncio.

## 5.3 A "cegueira ao espaço de embedding" (uma lição transversal)

🔑 Esta é uma das correções mais instrutivas do projeto, e conecta de volta ao doc de embeddings.
Caches de ML (protótipos, modelo supervisionado, mapa semântico) são chaveados por assinaturas. Se
essas assinaturas **não** incluíssem o `embed_space_id`, trocar o modelo de embedding deixaria caches
do espaço **antigo** válidos e prevendo lixo — porque vetores de espaços diferentes não são
comparáveis (doc de embeddings, "um espaço, uma régua"). A correção foi **dobrar o `embed_space_id`**
em toda assinatura de cache. É a materialização prática do princípio abstrato "só compare vetores do
mesmo espaço".

---

# PARTE 6 — NLP textual (`core/text`)

Além do ML sobre vetores, o projeto tem processamento de **linguagem natural** direto sobre o texto —
tudo torch-free, no extra `[nlp]`. Três engines.

## 6.1 Palavras-chave: YAKE (estatístico)

**YAKE** (Yet Another Keyword Extractor) extrai as palavras/frases-chave de um texto usando **só
estatística** do próprio documento — frequência do termo, posição, dispersão — **sem** modelo neural,
sem corpus de treino, sem dicionário. Por isso é minúsculo e offline.

```python
def keyphrases(text, *, lang="pt", top_n=10, ngram=3):
    extractor = yake.KeywordExtractor(lan=lang, n=ngram, top=top_n,
                                      dedup_lim=_DEDUP_LIM, stopwords=_stopwords_for(lang), ...)
    return [(phrase, float(score)) for phrase, score in extractor.extract_keywords(cleaned)]
```

🔑 Duas pegadinhas que o código documenta: (1) no YAKE, **score menor = frase mais relevante** (a
lista vem ascendente — contra-intuitivo). (2) Passar `stopwords=` **substitui** a lista padrão do YAKE
em vez de estendê-la (verificado no fonte instalado, não na doc) — então o projeto primeiro lê a lista
default e faz a **união** com as suas stopwords extras (nomes de mês, "página", "figura"...), senão
desligaria todo o filtro de palavras funcionais do YAKE sem querer.

## 6.2 Resumo extrativo: TextRank (grafo + PageRank)

**Resumo extrativo** = escolher as frases mais importantes do texto (não gera texto novo, "extrai" as
existentes). O método é o **TextRank**, uma aplicação do **PageRank** (o algoritmo do Google para
ranquear páginas) a frases:

1. Quebra o texto em frases.
2. Vetoriza cada frase com **TF-IDF** e monta um **grafo** onde frases parecidas se "conectam"
   (similaridade de cosseno entre elas).
3. Roda **PageRank** por iteração de potência: uma frase é importante se muitas frases importantes se
   parecem com ela (relevância circular, como links entre páginas).
4. Escolhe as frases com **MMR** (para não pegar duas quase-idênticas).

```python
def _textrank_scores(sim):
    transition = sim / row_sums
    scores = np.full(n, 1.0 / n)
    for _ in range(100):                                   # iteração de potência do PageRank
        updated = (1.0 - damping) / n + damping * (transition.T @ scores)
        if np.abs(updated - scores).sum() < 1e-6: break
        scores = updated
    position_bias = 1.0 / (1.0 + np.arange(n))             # prior: frases do início importam mais
    return (1 - _POSITION_BIAS_WEIGHT) * scores + _POSITION_BIAS_WEIGHT * position_bias
```

🔑 Duas decisões didáticas: o projeto **constrói o TextRank à mão** (não usa `sumy`) porque a
biblioteca pronta baixaria dados do `nltk` em runtime, quebrando a promessa offline. E mistura um
**prior de posição** (frases do começo pesam mais) porque transcrições/artigos costumam anunciar o
tema logo no início — algo que o TextRank puro ignora. O `@` de novo é multiplicação de matriz (o
passo do PageRank).

## 6.3 Entidades: spaCy NER (CNN, torch-free)

**NER** (Named Entity Recognition) acha **entidades nomeadas** no texto — pessoas (PER), organizações
(ORG), lugares (LOC), datas — e as rotula. O projeto usa o **spaCy** com o modelo `pt_core_news_sm`.

🔑 A decisão-chave: usa o modelo **CNN** (`_sm`), **não** o `_trf` (transformer). Por quê? O `_trf`
puxaria o PyTorch — proibido no app base. O CNN roda na CPU, torch-free, e é rápido o bastante.
`is_available()` checa **duas** coisas (como o Tesseract do OCR): o pacote spaCy **e** o modelo baixado
à parte — porque o modelo é um download separado (`python -m spacy download pt_core_news_sm`), e faltar
só o modelo dá uma mensagem de erro diferente de faltar o extra inteiro.

Detalhe de robustez que ecoa a regra anti-OOM dos testes: documentos gigantes (um livro, uma
transcrição longa) são **fatiados** antes do NER, porque o spaCy estima ~1GB de RAM por 100.000
caracteres — processar tudo de uma vez estouraria a memória dos 16GB da máquina.

---

# PARTE 7 — Gates e degradação graciosa

🔑 Todo esse ML/NLP vive atrás de **extras opcionais**, e a regra nº 6 do projeto (degradação graciosa)
vale em toda parte: recurso ausente **desabilita o card/flag com uma dica**, nunca quebra o app.

| Extra | Cobre | Gate |
|---|---|---|
| (nenhum) | `features`, `dedup`, `recommend` (numpy puro), BM25 | — |
| `[ml]` | scikit-learn: clustering, PCA/t-SNE, classify, TF-IDF (TextRank), outliers | `deps.is_available()` |
| `[ml-viz]` | UMAP | `umap_available()` |
| `[nlp]` | YAKE + spaCy NER | `is_available()` (pacote **e** modelo) |
| embedder | Ollama nomic-embed | `embedder.is_available()` |

O padrão é sempre o mesmo: **import preguiçoso** (a lib pesada só carrega quando o recurso é acionado —
como no `llm_factory` da espinha) + um `is_available()` que o gate consulta. Assim o app parte rápido e
funciona mesmo sem os extras instalados, só com menos recursos.

---

# Glossário

**Machine Learning (ML)** — programas que aprendem padrões a partir de dados em vez de regras
codificadas à mão.

**Supervisionado** — aprende de exemplos rotulados (texto → categoria) para prever rótulos novos.

**Não-supervisionado** — acha estrutura em dados sem rótulo (ex.: clustering).

**Clustering** — agrupar itens parecidos sem dizer quais grupos existem.

**HDBSCAN** — clustering por densidade que descobre o número de grupos sozinho e marca outliers
(`-1`). Usa distância euclidiana, que sobre vetores normalizados equivale a cosseno.

**k-means** — clustering que parte os dados em `k` grupos (você diz o `k`, ou o projeto o escolhe via
silhouette). Semeado para determinismo.

**Silhouette score** — métrica de quão coesos/separados ficaram os clusters; usada para escolher `k`
automaticamente (só com corpus grande o bastante).

**Redução de dimensionalidade** — projetar vetores de muitas dimensões (768) para poucas (2) para
visualizar, preservando distâncias ao máximo.

**PCA (Análise de Componentes Principais)** — redução linear pelos eixos de maior variância; rápida e
determinística, pode borrar estrutura local.

**t-SNE** — redução não-linear ótima para separar clusters visualmente; mais lenta, distorce
distâncias globais.

**UMAP** — redução moderna que preserva estrutura local e global; rápida, precisa do extra `[ml-viz]`.

**Determinismo (`random_state`, `_fix_signs`)** — garantir que a mesma entrada produza sempre o mesmo
resultado (mapa/partição).

**Cosseno + MMR (relacionados)** — achar documentos parecidos por cosseno e diversificar com MMR (a
mesma função do RAG).

**Isolation Forest** — detecção de outliers: pontos anômalos são isolados com poucos cortes
aleatórios; quanto mais fácil isolar, mais anômalo.

**Zero-shot** — classificar sem exemplos de treino, comparando o documento a **protótipos** (vetores
de frases-semente das categorias); vence o protótipo mais próximo por cosseno.

**Protótipo** — o vetor que representa uma categoria (a frase-semente embeddada).

**Margem** — diferença de cosseno para a 2ª categoria; mede a incerteza da classificação.

**Supervisionado (SVM calibrado)** — modelo treinado (`LinearSVC`+`CalibratedClassifierCV`) sobre
rótulos acumulados; usado quando válido, senão cai no zero-shot.

**Assinatura de modelo / `embed_space_id`** — chave de cache que inclui o espaço de embedding, para um
modelo/cache de um espaço antigo não ser reusado (senão preveria lixo).

**NLP (Processamento de Linguagem Natural)** — técnicas sobre texto (palavras-chave, resumo,
entidades).

**YAKE** — extração de palavras-chave estatística (frequência/posição/dispersão), offline, sem modelo.
Score menor = mais relevante.

**Stopwords** — palavras funcionais comuns ("de", "a", "e") filtradas antes da análise.

**TF-IDF** — pondera termos por frequência no documento × raridade no corpus; base do grafo do
TextRank.

**TextRank** — resumo extrativo aplicando PageRank a um grafo de frases similares.

**PageRank / iteração de potência** — algoritmo que ranqueia nós de um grafo pela importância dos que
apontam para eles; calculado por iterações sucessivas até convergir.

**Resumo extrativo** — selecionar as frases mais importantes existentes (não gera texto novo).

**NER (Named Entity Recognition)** — achar e rotular entidades nomeadas (pessoa, organização, lugar,
data).

**spaCy / modelo CNN vs `_trf`** — biblioteca de NLP; o projeto usa o modelo CNN (`_sm`, torch-free),
nunca o transformer (`_trf`, que puxaria PyTorch).

**Gate / `is_available()` / import preguiçoso** — o mecanismo de degradação graciosa: a lib pesada só
carrega quando usada, e o recurso se desabilita com dica se o extra faltar.

---

## Fontes

- [2.3. Clustering — scikit-learn documentation](https://scikit-learn.org/stable/modules/clustering.html)
- [What Is Unsupervised Learning? — PyUniverse](https://pyuniverse.com/what-is-unsupervised-learning/)
- [BERTopic: Neural topic modeling with a class-based TF-IDF procedure (arXiv)](https://arxiv.org/pdf/2203.05794)
- [Keyword Extraction Methods in NLP — Analytics Vidhya](https://www.analyticsvidhya.com/blog/2022/03/keyword-extraction-methods-from-documents-in-nlp/)
- [The Keyword Quest: Exploring Automatic Keyword Extractors — Medium](https://medium.com/accredian/the-keyword-quest-exploring-automatic-keyword-extractors-db553c6ac229)
