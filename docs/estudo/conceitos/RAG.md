# RAG — Geração Aumentada por Recuperação — guia completo do mill.tools

Documento de conceito sobre o RAG (Retrieval-Augmented Generation) do projeto: o que é, por que
existe, e cada etapa do pipeline explicada do zero e aterrada no seu código real de `src/core/rag/`.
Pré-requisito: o doc **[`EMBEDDINGS.md`](EMBEDDINGS.md)** (vetor, cosseno, normalização L2) — aqui
assumimos que "medir similaridade = produto escalar de vetores unitários" já está claro. Glossário no
fim.

---

# PARTE 1 — O que é RAG e por que existe

## 1.1 O problema

Um LLM (modelo de linguagem) sabe muito, mas tem dois limites graves para responder sobre **os seus**
dados: (1) ele **não conhece** seus documentos privados (suas transcrições, PDFs); (2) ele **alucina**
— inventa respostas plausíveis mas falsas quando não sabe. Perguntar "o que o vídeo X disse sobre Y?"
direto a um LLM daria, na melhor hipótese, um chute.

## 1.2 A ideia do RAG

**RAG** resolve isso **injetando o contexto certo na pergunta**. Em vez de confiar na memória do
modelo, o sistema:

1. **Recupera** (retrieval) os trechos mais relevantes dos **seus** documentos para aquela pergunta.
2. **Aumenta** (augment) a pergunta colando esses trechos como contexto.
3. **Gera** (generation) a resposta com o LLM, instruído a usar **apenas** aquele contexto e a
   **citar** de onde tirou cada afirmação.

🔑 A sacada: o LLM deixa de ser a "fonte da verdade" e passa a ser um **redator** que sintetiza um
material que você forneceu. Isso reduz alucinação (ele só tem o contexto real na frente) e torna a
resposta **rastreável** (cada afirmação aponta para um documento seu). É a diferença entre "confie em
mim" e "segundo o documento [2]...".

Um sistema RAG tem três componentes: o **LLM**, o **método de recuperação** e a **fonte de dados**.
No seu projeto: o LLM é local (Ollama) ou nuvem opt-in; a fonte é tudo que você produziu sob
`output/`; e o método de recuperação é o assunto principal deste doc.

---

# PARTE 2 — Visão geral do pipeline

O RAG tem dois momentos, separados no tempo:

**Indexação (offline, quando você adiciona conteúdo):**
```
documento → limpar → CHUNKING (fatiar) → EMBEDDING (cada pedaço → vetor) → guardar no VectorStore
```

**Consulta (online, quando você pergunta):**
```
pergunta → EMBEDDING da pergunta → RECUPERAÇÃO (achar os k pedaços mais relevantes)
         → montar CONTEXTO numerado → LLM responde CITANDO as fontes
```

As Partes 3–7 percorrem cada etapa.

---

# PARTE 3 — Chunking: por que e como fatiar

Um documento inteiro é grande demais para embeddar como um vetor só (perderia detalhe) e para caber no
contexto do LLM. Então ele é **fatiado em pedaços** (chunks). No seu projeto, o `indexer` usa o
`split_text` (um `RecursiveCharacterTextSplitter`) com **1200 caracteres por pedaço e 150 de
sobreposição** (overlap).

🔑 **Por que a sobreposição de 150 caracteres?** Se você cortasse o texto em pedaços perfeitamente
justapostos, uma frase importante partida exatamente na fronteira ficaria "sem casa" — metade num
pedaço, metade no outro, e nenhum dos dois a capturaria bem. A sobreposição faz cada pedaço repetir o
finalzinho do anterior, garantindo que ideias na fronteira apareçam inteiras em pelo menos um pedaço.

🔑 **O efeito colateral da sobreposição** (importante para a Parte 5): pedaços **vizinhos do mesmo
documento** ficam quase idênticos (compartilham 150 caracteres). São "irmãos quase-duplicados" — e
isso vai justificar o passo de diversificação (MMR).

O seu indexer ainda faz duas coisas antes de embeddar (do `PLANO_RAG_ESPACO_EMBEDDING`): passa o texto
por uma **limpeza** (`clean.clean_document_text` — tira marcadores de página de PDF, boilerplate) para
não embeddar lixo como se fosse conteúdo; e prepende a cada pedaço uma **linha de contexto**
(`"{nome} — {tipo}:"`) só no texto enviado ao embedder, para o vetor "saber" de que documento veio o
pedaço. O texto cru do pedaço (`ChunkMeta.text`) fica intacto, para o BM25 e as citações.

---

# PARTE 4 — Recuperação híbrida: dois sinais melhores que um

Esta é a parte mais rica. Recuperar = dada a pergunta, achar os pedaços mais relevantes. O projeto
combina **dois** métodos, porque cada um cobre a fraqueza do outro.

## 4.1 Busca densa (dense) — por significado

É a busca por **embeddings** que você já entende do doc de fundação: embeda a pergunta, mede a
**similaridade de cosseno** contra todos os pedaços, ranqueia. "Densa" porque os vetores de embedding
são densos (768 números, quase todos diferentes de zero). Ela é **forte em significado** — acha o
pedaço certo mesmo sem palavras em comum.

No `store.py`, é a `dense_scores` que vimos no doc de embeddings (produto escalar dos unitários).

🔑 **A fraqueza da busca densa:** ela é **fraca em termos exatos** — nomes próprios, siglas, números,
códigos. "Muad'Dib" ou "RRF" ou "WinError 32" podem não ter um embedding distintivo, e a busca densa
pode não priorizar o pedaço que contém exatamente aquele termo raro. É uma limitação **bem
documentada** do RAG puramente denso.

## 4.2 Busca esparsa (BM25) — por termo exato

A cura para a fraqueza acima é o **BM25**, um método clássico de recuperação por **palavras-chave**.
Ele não entende significado; ele conta **coincidência de termos**, com duas ideias:

- **TF (Term Frequency):** quanto mais vezes um termo da pergunta aparece num documento, mais
  relevante — mas com retornos decrescentes (a 10ª ocorrência importa menos que a 2ª).
- **IDF (Inverse Document Frequency):** termos **raros** no corpus valem mais que termos comuns. "de"
  aparece em tudo (peso baixo); "Muad'Dib" aparece em pouquíssimos (peso alto — é um sinal forte).

BM25 combina os dois e normaliza pelo comprimento do documento. É "esparso" porque opera sobre
contagens de palavras (a maioria zero para qualquer documento).

No seu `bm25.py`:

```python
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)      # "runs" de caracteres de palavra, Unicode-aware

def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())       # minúsculas, sem pontuação

def build_bm25_index(texts): return BM25Okapi([_tokenize(t) for t in texts])
def bm25_score(index, query): return index.get_scores(_tokenize(query))
```

🔑 **Por que tokenizar com regex e não `.split()`?** Um `.split()` simples deixa pontuação grudada:
`"cão."` ≠ `"cão"`, perdendo o casamento no fim de uma frase em silêncio. O `\w+` (Unicode, pega
acentos do PT-BR) extrai só as "palavras", nos dois lados (índice e pergunta). É o **mínimo** para não
corromper o casamento lexical — NLP mais rico (stemming, stopwords) mora em `core/text`, não aqui.

O comentário do arquivo registra até a escolha da biblioteca: `rank_bm25` (só numpy) em vez de `bm25s`
(mais rápido mas puxa scipy), porque a diferença só importa acima de ~1M documentos — longe de um
corpus pessoal. Engenharia proporcional, de novo.

## 4.3 Por que "híbrido"

Denso acha por **sentido**; BM25 acha por **termo exato**. Juntos, cobrem os dois modos de uma
pergunta ser respondida. É o consenso atual: a busca híbrida supera consistentemente cada método
sozinho.

---

# PARTE 5 — Combinar, diversificar, filtrar (o `retriever.py`)

Ter dois rankings (denso e BM25) levanta o problema: como **combiná-los**? E depois, como escolher os
`k` finais? O `retrieve()` faz isso em quatro passos.

## 5.1 Fusão por posição: Reciprocal Rank Fusion (RRF)

🔑 **O problema de somar os scores diretamente:** o cosseno vive em `[-1, 1]`, o BM25 é ilimitado
(pode ir a 15, 30...). Somá-los deixaria o BM25 dominar só pela escala. Normalizar exigiria um
truque ad-hoc frágil. A solução elegante é **ignorar os valores e usar só as posições** (ranks): o
**Reciprocal Rank Fusion**.

Cada método ranqueia os pedaços; cada pedaço ganha, de cada ranking, uma pontuação `1/(k + posição)`;
somam-se as contribuições. Um pedaço que ficou em 1º no denso e 3º no BM25 acumula bastante; um que
ficou mal nos dois, pouco.

No seu `retriever.py`:

```python
_RRF_K = 60      # constante padrão do paper (Cormack et al., 2009) — resultados insensíveis a ela

def _reciprocal_rank_fusion(*score_arrays):
    for scores in score_arrays:
        order = np.lexsort((idx, -scores))    # ordena por score desc, empate → índice menor
        ranks[order] = np.arange(n)           # rank 0 = melhor
        fused += 1.0 / (_RRF_K + ranks + 1)   # a fórmula RRF
    return fused
```

🔑 Dois detalhes finos: o `_RRF_K = 60` é a constante clássica do paper (não ajustada por corpus,
porque o próprio paper mostrou os resultados insensíveis a ela na faixa que importa). E o desempate
por `np.lexsort` (não `argsort[::-1]`) é deliberado: com pouquíssimos candidatos, um sinal totalmente
sem informação (BM25 sem nenhum casamento) poderia, ao ser revertido, cancelar uma preferência clara
do outro sinal. Por isso, quando o BM25 não casa **nada** (`lexical.max() <= 0`), a fusão é
**pulada** e cai no denso puro — para não injetar viés de ordem-de-índice.

## 5.2 Diversificar: Maximal Marginal Relevance (MMR)

Lembra dos "irmãos quase-duplicados" da sobreposição do chunking? Sem cuidado, os `k=6` pedaços
recuperados poderiam ser 3 fatias vizinhas **do mesmo** parágrafo — redundância que desperdiça o
contexto. O **MMR** resolve: em vez de pegar os mais relevantes, ele equilibra **relevância à
pergunta** contra **diferença dos já escolhidos**.

O RRF ranqueia um **pool** maior que `k` (~4×, `_POOL_MULTIPLIER`); o MMR então escolhe `k` desse pool
diversificando. No seu `retriever.py`:

```python
selected = _mmr(relevance, similarity, k, lambda_=_MMR_LAMBDA)   # _MMR_LAMBDA = 0.7
```

e o `_mmr` (reusado de `core/ml/recommend.py`):

```python
def _mmr(relevance, similarity, k, *, lambda_):
    for _ in range(k):
        if not selected:
            scores = relevance
        else:
            redundancy = similarity[:, selected].max(axis=1)      # o quão parecido com os já escolhidos
            scores = lambda_ * relevance - (1 - lambda_) * redundancy
        best = max(remaining, key=lambda i: (scores[i], -i))
        selected.append(best)
```

🔑 A fórmula é `λ·relevância − (1−λ)·redundância`: com `λ=0.7`, prioriza relevância mas penaliza pegar
algo muito parecido com o que já entrou. É **pulado** quando o pool já cabe em `k` ou quando o escopo
é um documento único (ali os pedaços são irmãos por construção — diversificar prejudicaria). Repare
que o MMR ranqueia pelo **score fundido** (RRF), não pelo cosseno puro: reranquear por relevância
densa desfaria em silêncio o resgate do BM25.

## 5.3 O piso de relevância

Um último filtro (`_apply_relevance_floor`): entre a fusão e o MMR, descarta candidatos do pool cujo
**cosseno denso** esteja mais de `δ=0.05` abaixo do melhor do pool. É um **guarda contra
desbalanceamento do corpus**: pedaços de um documento volumoso mas irrelevante ao assunto (os muitos
capítulos de Duna numa pergunta sobre Ollama) entravam no contexto só por serem "o 2º-6º melhor". O
piso os corta — com uma **isenção para o top-1 do BM25**, para não matar o resgate de termo raro que é
a razão de ser do híbrido. É a parte mais sutil do retriever; o comentário do arquivo documenta o
impasse dos dois contratos e por que isentar só o top-1 os reconcilia.

## 5.4 O contrato do `.score` e a cobertura

🔑 Uma regra de fronteira que amarra tudo: o `.score` reportado por cada hit continua sendo o
**cosseno denso** (não o valor fundido nem o do MMR), porque é o que o aviso de "fora de escopo" usa.
E o `retrieve()` devolve também `pool_max_score` — o melhor cosseno entre **todos** os candidatos do
escopo, medido **antes** do piso — para o sinal de cobertura medir o acervo, não o corte.

---

# PARTE 6 — Gerar a resposta com citações (`chat.py`)

Recuperados os pedaços, monta-se o contexto e pede-se ao LLM. Duas peças didáticas.

## 6.1 O contexto numerado

```python
def build_context(retrieved):
    for h in retrieved:
        key = str(Path(h.meta.source_path))
        if key not in number_of:
            sources.append(path)
            number_of[key] = len(sources)       # [n] por DOCUMENTO distinto, não por pedaço
        blocks.append(f"[{number_of[key]}] ({path.name})\n{h.meta.text}")
```

🔑 O número de citação `[n]` é atribuído por **documento distinto**, não por pedaço: vários pedaços do
mesmo arquivo compartilham o mesmo `[n]`. Assim o `[n]` que o modelo cita fica em sincronia com a
lista de fontes mostrada na tela — senão, com 6 pedaços de 4 documentos, o modelo citaria `[5]`/`[6]`
enquanto só existem 4 crachás de fonte.

O **prompt** (`RAG_PROMPT`) é estrito: "responda usando APENAS o contexto, cite as fontes pelo número
`[n]`, e se o contexto não contiver a resposta, diga que não encontrou". É o que segura a alucinação.

## 6.2 Fontes citadas vs. consultadas

Depois da resposta, o projeto distingue duas coisas (do `PLANO_FONTES_E_PISO_RELEVANCIA`):

```python
cited_numbers = set(cited_source_numbers(text, len(sources)))
cited_sources = [s for i, s in enumerate(sources, 1) if i in cited_numbers]
return AnswerResult(text=text, sources=sources, cited_sources=cited_sources)
```

- **`sources`** — toda fonte **consultada** (recuperada para o contexto).
- **`cited_sources`** — o subconjunto que a resposta **de fato citou** via `[n]`.

E o parse dos `[n]` mora num lugar só, defensivo:

```python
_CITATION_RE = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")     # [n], [1, 2], [1][2]

def cited_source_numbers(text, n_sources):
    for group in _CITATION_RE.findall(text):
        for token in re.findall(r"\d+", group):
            n = int(token)
            if 1 <= n <= n_sources and n not in seen:   # ignora números fora da faixa
                seen.append(n)
    return seen
```

🔑 Ele aceita formas agrupadas (`[1, 2]`) e adjacentes (`[1][2]`), e **ignora** números fora da faixa
— então um modelo "criativo" nunca fabrica uma citação que não corresponde a uma fonte real. Se a
resposta não cita nada parseável, `cited_sources` fica vazio e **tudo** vira "consultada, não citada"
— nunca inventa citação. GUI, CLI e Receitas consomem **essa mesma função**; ninguém parseia por
conta própria (fonte única).

---

# PARTE 7 — "A pergunta está no acervo?" (o gate de cobertura)

Antes de responder, o projeto pode avisar quando a pergunta provavelmente **não** é coberta pelo
corpus. Em `ml/recommend.py`:

```python
DEFAULT_IN_CORPUS_THRESHOLD = 0.72

def in_corpus(query_vec, store, *, threshold=DEFAULT_IN_CORPUS_THRESHOLD):
    hits = store.search(query_vec, k=1)          # o melhor pedaço
    best = hits[0].score                          # seu cosseno
    return (best >= threshold, best)
```

🔑 A lógica: se **nem o pedaço mais parecido** passa de `0.72` de cosseno, a pergunta provavelmente
está fora do acervo, e a GUI avisa antes de responder (para o modelo não inventar). O `0.72` **não**
é mágico: o comentário documenta a **calibração** — mediram 10 perguntas claramente cobertas (cosseno
0.7356–0.8684) contra 5 fora (0.6540–0.7115) e escolheram um valor na folga entre as duas faixas,
mais perto da borda de fora (para preferir zero falsos "fora de escopo"). É um limiar **dependente do
modelo de embedding** — por isso é parâmetro, não hardcode. E note: recalibrar exigiu uma reindexação
**real** sob o esquema novo (a primeira tentativa não reindexou de verdade e produziu números
inválidos) — a mesma pegadinha do `force` no indexer.

---

# Glossário

**RAG (Retrieval-Augmented Generation)** — responder perguntas recuperando trechos dos seus documentos
e pedindo ao LLM que sintetize a resposta citando-os.

**Retrieval (recuperação)** — achar os trechos mais relevantes para uma pergunta.

**Alucinação** — quando o LLM inventa uma resposta plausível mas falsa. O RAG a reduz aterrando a
resposta em contexto real.

**Grounding (aterramento)** — restringir a resposta ao contexto fornecido; a base da confiabilidade do
RAG.

**Chunk (pedaço) / chunking** — fatiar um documento em fragmentos (1200 chars) para embeddar e caber
no contexto.

**Overlap (sobreposição)** — os 150 chars repetidos entre pedaços vizinhos, para não partir ideias na
fronteira. Efeito colateral: pedaços vizinhos ficam quase-duplicados.

**Busca densa (dense)** — recuperação por similaridade de embeddings (significado). Forte em sentido,
fraca em termos exatos.

**Busca esparsa / BM25** — recuperação por coincidência de palavras-chave. Forte em termos exatos
(nomes, siglas, números).

**TF (Term Frequency)** — frequência de um termo num documento (com retornos decrescentes).

**IDF (Inverse Document Frequency)** — peso maior para termos raros no corpus, menor para comuns.

**Tokenização** — quebrar texto em "palavras" (tokens). Aqui, `\w+` Unicode, minúsculas, sem
pontuação.

**Busca híbrida** — combinar densa + BM25 para cobrir significado E termo exato.

**RRF (Reciprocal Rank Fusion)** — fundir dois rankings por **posição** (`1/(k+rank)`), não por valor
de score — evita a incompatibilidade de escala entre cosseno e BM25.

**Pool** — o conjunto de candidatos (~4×k) ranqueado pela fusão antes de diversificar.

**MMR (Maximal Marginal Relevance)** — escolher os `k` finais equilibrando relevância à pergunta
contra diferença dos já escolhidos (`λ·relevância − (1−λ)·redundância`), para não encher o contexto de
quase-duplicatas.

**Piso de relevância** — descartar candidatos cujo cosseno denso fica muito abaixo do melhor do pool
(guarda contra corpus desbalanceado), isentando o top-1 do BM25.

**`.score`** — a similaridade de cosseno densa de um hit (contrato: não é o valor fundido/MMR).

**`pool_max_score`** — o melhor cosseno entre todos os candidatos do escopo; alimenta o aviso de
cobertura.

**Contexto** — os trechos recuperados, numerados `[n]` por documento distinto, colados na pergunta.

**Citação `[n]`** — marcador com que o LLM aponta de qual fonte tirou uma afirmação; parseado
defensivamente.

**Fontes consultadas vs. citadas** — todas as recuperadas para o contexto vs. as que a resposta de
fato citou.

**`in_corpus` / limiar 0.72** — gate que avisa quando nem o melhor pedaço é próximo o bastante,
sinalizando pergunta fora do acervo. Limiar calibrado, dependente do modelo.

**`VectorStore` / `embed_fn`** — ver o doc de [`EMBEDDINGS.md`](EMBEDDINGS.md).

---

## Fontes

- [RAG Explained: 10 Steps to Production-Ready Retrieval-Augmented Generation](https://decodethefuture.org/en/rag/)
- [Hybrid Search: BM25, Vector & Reranking Reference](https://www.digitalapplied.com/blog/hybrid-search-bm25-vector-reranking-reference-2026)
- [Retrieval-Augmented Generation Techniques — EmergentMind](https://www.emergentmind.com/topics/rag-based-methods)
- [Reciprocal Rank Fusion (Cormack, Clarke & Buettcher, SIGIR 2009) — referência clássica citada no próprio `retriever.py`]
