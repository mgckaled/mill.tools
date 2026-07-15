# Embeddings e Espaço Vetorial — a fundação do RAG e do ML

Documento de conceito, a **base** sobre a qual os guias de RAG e de Machine Learning se apoiam. Se
você entender bem "o que é um vetor", "o que significa dois textos estarem próximos" e "como medimos
essa proximidade", os dois docs seguintes viram quase só aplicação. Tudo é explicado do zero, com
analogia, e aterrado no seu código real de `src/core/rag/` e `src/core/ml/`. Glossário no fim.

> Por que este doc existe separado: o RAG **recupera** por embeddings e o ML clássico do projeto
> (`core/ml/features.py`) faz *mean-pool* **desses mesmos** embeddings. A fundação é comum aos dois —
> então ela mora aqui, uma vez, e os outros dois a referenciam.

---

# PARTE 1 — Vetores, do zero

## 1.1 O que é um vetor

Um **vetor** é só uma **lista ordenada de números**. `[0.2, -0.5, 0.9]` é um vetor de 3 números.
Cada número é uma **coordenada** (ou "componente"); a quantidade de números é a **dimensão** do
vetor — esse exemplo tem dimensão 3.

Geometricamente, um vetor é uma **seta** que sai da origem e aponta para um ponto no espaço. Em 2
dimensões, `[3, 2]` é uma seta que anda 3 para a direita e 2 para cima. Em 3 dimensões, uma seta no
espaço. A partir daí a intuição visual acaba — mas a matemática **não muda** com mais dimensões. É a
ideia-chave para não travar quando aparecer "768 dimensões": você não precisa *visualizar* 768 eixos;
só precisa saber que é uma lista de 768 números e que as mesmas fórmulas valem.

🔑 No seu projeto, os vetores têm **768 dimensões** (`EMBED_DIM = 768` em `embedder.py`). Cada
pedaço de texto vira uma lista de 768 números `float32`.

## 1.2 Duas medidas sobre um vetor: comprimento e direção

Um vetor carrega duas informações:

- **Comprimento (magnitude/norma):** o "tamanho" da seta. A **norma L2** (a mais comum) é o
  comprimento euclidiano — pelo teorema de Pitágoras generalizado: `√(x₁² + x₂² + ... + xₙ²)`. Uma
  seta `[3, 4]` tem norma L2 `√(9+16) = 5`.
- **Direção:** para onde a seta aponta, independentemente de quão longa ela é.

🔑 Guarde essa distinção — ela é o coração de tudo. Para comparar **significado** de textos, o que
importa é a **direção**, não o comprimento (Parte 3).

---

# PARTE 2 — Embeddings: transformar texto em vetor

## 2.1 A ideia

Um **embedding** é um vetor que **representa o significado** de um texto. Um modelo de embedding (uma
rede neural treinada) recebe uma frase e devolve uma lista de números — no seu caso, 768 números —
posicionando aquele texto num **espaço** onde a **posição codifica o sentido**.

A propriedade mágica que o treino garante: **textos com significado parecido ficam próximos** nesse
espaço; textos sobre assuntos diferentes ficam distantes. "cachorro" e "cão" apontam quase para a
mesma direção; "cachorro" e "declaração de imposto" apontam para direções bem diferentes. O modelo
não "entende" como um humano — ele aprendeu, de bilhões de exemplos, a *geometria* das relações entre
palavras e frases.

🔑 **Por que isso é revolucionário para busca?** Busca tradicional casa **palavras exatas** ("cão"
não acha um texto que só diz "cachorro"). Busca por embedding casa **significado**: a pergunta e o
documento podem não compartilhar nenhuma palavra e ainda assim ficarem próximos no espaço, porque
falam da mesma coisa. É o motor do RAG.

## 2.2 O espaço de embedding

Chamamos o conjunto de todas as posições possíveis de **espaço de embedding** (ou espaço vetorial).
Pense num mapa: cada texto é um ponto, e a distância entre pontos mede quão diferentes eles são de
sentido. Um agrupamento de pontos próximos é um "assunto"; uma região vazia entre dois agrupamentos é
a fronteira entre dois temas. O ML clássico do projeto (clustering, mapa semântico) literalmente
explora esse mapa — é por isso que este doc precede o de ML.

🔑 **Um espaço, uma régua.** Todos os vetores precisam vir do **mesmo modelo** para serem
comparáveis — misturar embeddings de modelos diferentes é como comparar coordenadas de dois mapas com
escalas diferentes. Seu projeto leva isso a sério: `embed_space_id` (`"{modelo}:{dim}:{esquema}"`)
identifica o espaço, e trocar o modelo invalida caches — senão você compararia posições de mapas
incompatíveis (voltaremos a isso no doc de ML).

---

# PARTE 3 — Medindo similaridade: o coração de tudo

Como transformamos "estão próximos no espaço" num **número**? Há duas famílias de medida, e entender
a escolha do projeto é entender metade do RAG.

## 3.1 Produto escalar (dot product)

O **produto escalar** de dois vetores multiplica coordenada a coordenada e soma:
`a·b = a₁b₁ + a₂b₂ + ... + aₙbₙ`. Ele mistura **direção e comprimento**: cresce quando os vetores
apontam para o mesmo lado E quando são longos.

## 3.2 Similaridade de cosseno (cosine similarity)

O problema do produto escalar puro: um documento longo pode ter um embedding de **magnitude** maior e
"ganhar" só por ser grande, não por ser mais relevante. A solução é medir **só o ângulo** entre as
setas, ignorando o comprimento. Isso é a **similaridade de cosseno**:

```
cos(θ) = (a·b) / (‖a‖ · ‖b‖)
```

Ou seja: o produto escalar **dividido pelos comprimentos** dos dois vetores. O resultado é o cosseno
do ângulo entre eles, e vive em `[-1, 1]`:

- **1.0** → mesma direção (significado idêntico).
- **0.0** → perpendiculares (sem relação).
- **-1.0** → direções opostas.

🔑 **Por que cosseno e não distância?** Porque significado é **orientação**, não tamanho. Dois textos
sobre o mesmo assunto devem ser "iguais" mesmo que um seja um parágrafo e o outro um livro. Cosseno
mede exatamente isso — a direção pura — descartando a magnitude que só atrapalharia.

## 3.3 O truque da normalização L2

Aqui está a peça de engenharia que amarra tudo. Calcular cosseno toda hora exige dividir pelos
comprimentos — custoso quando você compara uma pergunta contra centenas de milhares de vetores.

O atalho: **pré-normalizar** todos os vetores para comprimento 1 (dividir cada um pela sua própria
norma L2). Um vetor de comprimento 1 é um **vetor unitário**. Depois disso, `‖a‖ = ‖b‖ = 1`, então a
fórmula do cosseno **colapsa** para:

```
cos(θ) = a·b          (quando ‖a‖ = ‖b‖ = 1)
```

🔑 **Ou seja: com vetores normalizados, o cosseno vira um simples produto escalar.** Você paga a
normalização uma vez e, daí em diante, "medir similaridade" é só multiplicar-e-somar — barato e
vetorizável (uma multiplicação de matriz para comparar contra o corpus inteiro de uma vez).

Veja isso **exatamente** no seu `store.py`:

```python
def _normalized_vectors(self) -> np.ndarray:
    """Return the L2-normalized vectors, computed once and cached until mutated."""
    if self._normalized is None:
        self._normalized = self.vectors / (
            np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8
        )
    return self._normalized

def dense_scores(self, query_vec, *, mask=None) -> np.ndarray:
    """Cosine similarity of query_vec against every stored chunk."""
    q = query_vec / (np.linalg.norm(query_vec) + 1e-8)      # normaliza a pergunta
    scores = self._normalized_vectors() @ q                 # produto escalar = cosseno!
    ...
```

Ponto a ponto:
- **`np.linalg.norm(self.vectors, axis=1, keepdims=True)`** calcula o comprimento L2 de cada linha
  (cada vetor).
- **`self.vectors / (norma + 1e-8)`** divide cada vetor pelo seu comprimento → todos viram unitários.
  O `+ 1e-8` é um **guarda contra divisão por zero** (um vetor todo-zero teria norma 0).
- **`self._normalized_vectors() @ q`** é o `@` do numpy — **multiplicação de matriz**. A matriz
  `(N, 768)` de vetores normalizados vezes o vetor-pergunta `(768,)` normalizado devolve `(N,)`: a
  similaridade de cosseno da pergunta contra **cada um** dos N pedaços, tudo numa operação só.
- **Cache (`self._normalized`)**: normaliza uma vez e guarda; só recalcula quando o store muda
  (`add`/`drop_source` zeram o cache). Custo pago uma vez, não por busca.

🔑 Note o comentário no `__init__` do store: os vetores **crus** (`self.vectors`) ficam intactos; a
normalização vive num cache à parte. Motivo: o `ml/features.py` precisa dos vetores crus para o
*mean-pool* antes de normalizar o resultado agregado — normalizar in-place quebraria a matemática do
pooling (Parte 4).

---

# PARTE 4 — De pedaços para documentos: mean-pooling

O RAG guarda um vetor por **pedaço** de texto (chunk). Mas o ML clássico quer raciocinar por
**documento** inteiro (agrupar documentos parecidos, achar outliers). Como transformar N vetores de
pedaço num vetor de documento? **Tirando a média.**

No seu `ml/features.py`:

```python
def document_matrix(store, *, l2_normalize=True) -> DocumentMatrix:
    # agrupa os índices das linhas por documento (source_path)
    rows_by_doc: dict[str, list[int]] = {}
    for i, meta in enumerate(store.meta):
        rows_by_doc.setdefault(meta.source_path, []).append(i)

    pooled = np.empty((len(source_paths), dim), dtype=np.float32)
    for d, source in enumerate(source_paths):
        pooled[d] = store.vectors[rows_by_doc[source]].mean(axis=0)   # média dos pedaços

    if l2_normalize:
        norms = np.linalg.norm(pooled, axis=1, keepdims=True) + 1e-8
        pooled = (pooled / norms).astype(np.float32)                  # normaliza o resultado
    return DocumentMatrix(X=pooled, ...)
```

🔑 **Mean-pooling** = a média dos vetores dos pedaços de um documento é o "vetor-resumo" do documento.
A intuição: se cada pedaço aponta para uma nuance do sentido, a média aponta para o "centro de massa"
semântico do documento. Depois normaliza-se o resultado (L2) para o cosseno voltar a ser produto
escalar entre documentos.

Repare na ordem: pool (média dos **crus**) → **depois** normaliza. É por isso que o store guarda os
vetores crus separados do cache normalizado — se ele já normalizasse in-place, a média seria de
vetores unitários e o "centro de massa" ficaria distorcido. Uma decisão de design sutil que só faz
sentido quando você vê os dois usos (RAG e ML) juntos.

---

# PARTE 5 — O modelo de embedding do projeto (`embedder.py`)

Agora o arquivo que **produz** os vetores. Três decisões didáticas.

## 5.1 Local, na CPU, torch-free

```python
DEFAULT_EMBED_MODEL = "nomic-embed-custom"  # 768-dim, torch-free, CPU-only
EMBED_DIM = 768
```

O projeto usa o **nomic-embed-text** rodando localmente via Ollama, numa build custom fixada na CPU
(`num_gpu 0`). Por quê? Privacidade (o texto nunca sai da máquina para gerar embedding) e não disputar
a GPU fraca (MX150) com o Whisper/Flet. 768 dimensões é um bom equilíbrio: expressivo o bastante para
capturar significado, pequeno o bastante para o índice caber na memória.

🔑 **`embedder.py` é a única fronteira de rede do RAG.** Todo o resto do core recebe a função de
embedding **injetada** (`embed_fn`/`embed_query_fn`) — então dá para testar a lógica de busca sem um
Ollama rodando. É a regra nº 2 do projeto (injeção de dependência) aplicada ao ponto mais "externo"
do RAG.

## 5.2 Os prefixos de tarefa (uma sutileza que muda o espaço)

```python
_NOMIC_DOC_PREFIX = "search_document: "
_NOMIC_QUERY_PREFIX = "search_query: "

def embed_texts(texts, ...):
    doc_prefix, _ = _prefixes_for(model)
    prefixed = [doc_prefix + t for t in texts] if doc_prefix else texts
    ...
def embed_query(text, ...):
    _, query_prefix = _prefixes_for(model)
    vec = _embeddings(model).embed_query(query_prefix + text if query_prefix else text)
```

🔑 O nomic-embed foi **treinado** esperando que documentos venham prefixados com `"search_document: "`
e perguntas com `"search_query: "`. Sem esses prefixos exatos, documento e pergunta caem no mesmo
"espaço sem tarefa" — e aí surge a **assimetria** que mais atrapalha a busca: uma pergunta curta
("o que é RRF?") e um documento longo têm formatos muito diferentes, e o modelo precisa da dica de
tarefa para posicioná-los de forma comparável. É um detalhe minúsculo (dois prefixos de string) com
efeito grande na qualidade da recuperação — e é exatamente o tipo de coisa que "a IA fez e você não
tinha absorvido".

## 5.3 Sub-lotes (batching) e robustez

```python
EMBED_BATCH_SIZE = 16
for start in range(0, total, batch_size):
    batch = client.embed_documents(prefixed[start : start + batch_size])
    out.extend(batch)
    if progress_cb:
        progress_cb(min(start + batch_size, total), total)
```

Um documento longo vira muitos pedaços; mandar todos de uma vez faria um pico de memória no runner do
Ollama (que já morre em máquinas de pouca RAM). Então o embedding é feito em **sub-lotes de 16**,
reusando o mesmo cliente (o modelo fica carregado), com `progress_cb` avisando o andamento — o mesmo
padrão de callback da espinha. E `_check_dim` avisa se o modelo devolver uma largura inesperada (um
quirk conhecido do Ollama que retorna 8192 dims em vez de 768) — porque um índice com largura
inconsistente corromperia a busca por cosseno em silêncio.

---

# PARTE 6 — Onde os vetores moram (`VectorStore`)

O `store.py` é o "banco de dados" de vetores — e é deliberadamente simples: uma **matriz numpy**
`(N, 768)` em memória, com metadados paralelos, persistida em disco como `.npz` (a matriz) + `.json`
(os metadados). A busca é a multiplicação de matriz que vimos na Parte 3.

```python
class VectorStore:
    def __init__(self, dim: int = 768) -> None:
        self.vectors = np.empty((0, dim), dtype=np.float32)   # a matriz (N, D)
        self.meta: list[ChunkMeta] = []                       # metadados paralelos: meta[i] ↔ vectors[i]
        self._normalized = None                               # cache dos unitários
        self._bm25 = None                                     # cache do índice BM25 (doc de RAG)
```

🔑 **Por que numpy e não um banco vetorial "de verdade"?** Porque para um corpus pessoal (centenas de
milhares de pedaços), uma matriz numpy é rápida o suficiente e não adiciona dependência pesada. O
comentário no arquivo já registra o caminho de upgrade (`sqlite-vec`) se a escala um dia exigir — sem
mudar a interface. É engenharia proporcional ao problema, não over-engineering.

O `store` também tolera corrupção (um `.npz` truncado vira store vazio + aviso, não uma exceção crua)
e valida a largura dos vetores na entrada — os mesmos cuidados de robustez que você viu no
`ffmpeg.py`, agora do lado dos dados.

---

# Glossário

**Vetor** — uma lista ordenada de números. Geometricamente, uma seta da origem a um ponto.

**Coordenada / componente** — cada número de um vetor.

**Dimensão** — a quantidade de números de um vetor. No projeto, 768.

**Magnitude / norma / norma L2** — o comprimento de um vetor: `√(x₁²+...+xₙ²)`. Mede o "tamanho" da
seta.

**Direção** — para onde a seta aponta, independentemente do comprimento. É o que carrega o
*significado* num embedding.

**Embedding** — um vetor que representa o significado de um texto, produzido por um modelo treinado.
Textos de sentido parecido ficam próximos no espaço.

**Espaço de embedding / espaço vetorial** — o "mapa" onde cada texto é um ponto e a distância mede
diferença de significado. Vetores só são comparáveis se vierem do mesmo modelo.

**Modelo de embedding** — a rede neural que converte texto → vetor. Aqui, `nomic-embed-text` local
via Ollama.

**Produto escalar (dot product)** — `a₁b₁+...+aₙbₙ`. Mistura direção e comprimento.

**Similaridade de cosseno** — o cosseno do ângulo entre dois vetores: `(a·b)/(‖a‖‖b‖)`, em `[-1, 1]`.
Mede só a direção (significado), ignorando o comprimento. 1 = idêntico, 0 = sem relação.

**Vetor unitário** — vetor de comprimento 1.

**Normalização L2** — dividir um vetor por sua norma L2 para torná-lo unitário. Depois disso, cosseno
= produto escalar (mais barato). Padrão em `store.dense_scores` e `features.document_matrix`.

**Mean-pooling** — tirar a média dos vetores dos pedaços de um documento para obter um único
vetor-resumo do documento. Feito nos vetores crus, normalizado depois.

**`float32`** — números de ponto flutuante de 32 bits. Metade da memória do `float64`, com precisão
suficiente para similaridade.

**Chunk (pedaço)** — um fragmento de um documento; a unidade que o RAG embedda e guarda (detalhe no
doc de RAG).

**`VectorStore`** — a matriz numpy `(N, D)` + metadados que guarda os embeddings, com busca por
cosseno e persistência `.npz`/`.json`.

**`embed_space_id`** — identificador do espaço de embedding (`"{modelo}:{dim}:{esquema}"`); garante
que não se compare vetores de modelos/esquemas diferentes.

**Prefixo de tarefa** — as strings `"search_document: "`/`"search_query: "` que o nomic-embed espera
para posicionar documentos e perguntas de forma comparável.

**Injeção de `embed_fn`** — passar a função de embedding como parâmetro (em vez de o core chamar o
Ollama direto), o que mantém a lógica testável sem rede.

**Matriz** — uma tabela de números (aqui, `(N, 768)`). `A @ b` (numpy) é a multiplicação de matriz,
que compara a pergunta contra todos os vetores de uma vez.

---

## Fontes

- [Understanding Text Similarity with Embeddings and Cosine Similarity — DEV](https://dev.to/venu171/understanding-text-similarity-with-embeddings-and-cosine-similarity-5aon)
- [Vector Similarity Explained — Pinecone](https://www.pinecone.io/learn/vector-similarity/)
- [Distance Metrics — Qdrant](https://qdrant.tech/course/essentials/day-1/distance-metrics/)
- [L2 Distance vs Cosine Similarity: The Hidden Connection — Medium](https://medium.com/@ishankgera.work/l2-distance-vs-cosine-similarity-the-hidden-connection-35c1ae121392)
- [Similarity Metrics for Vector Search — Zilliz](https://zilliz.com/blog/similarity-metrics-for-vector-search)
