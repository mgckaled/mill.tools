# Avaliação profunda — ML & RAG (Fable 5, jul/2026)

Leitura arquivo-a-arquivo de `core/rag`, `core/ml`, `core/text`, `core/observatory` e das superfícies
que os consomem (`gui/modules/ai/worker.py`, `gui/modules/observatory/index_worker.py`, `cli/ai.py`,
`gui/views/profile_section.py`, `core/library/tags.py`, `core/recipes/registry/ai.py`), guiada pelas
skills `architecture` e `ml-rag`. Complementa (não repete) o plano do quarteto ML já implementado.

---

## 1. Estado geral

A base está sólida e as correções do quarteto se sustentam no código: injeção de `embed_fn`/`card_fn`
consistente, RRF com `lexsort` e fallback denso quando o BM25 não tem match, indexação incremental com
paths resolvidos simetricamente, `embed_space_id` dobrado nas assinaturas de protótipos/SVM, escrita
atômica em grupo, gates com timeout curto. O desenho "RAG persiste → `features` pool → todo o ML lê de
graça" continua sendo o maior acerto arquitetural: cada motor novo custa quase zero embedding.

O que segue são as arestas que sobraram — ordenadas por impacto.

---

## 2. Acurácia do RAG (a pergunta mais importante)

### 2.1 ⭐ Prefixos de tarefa do nomic-embed — o maior ganho barato disponível

O `nomic-embed-text` foi **treinado com prefixos de instrução**: documentos devem ser embeddados como
`search_document: <texto>` e consultas como `search_query: <texto>`. Nem o `Modelfile.nomic` nem o
`embedder.py` adicionam prefixo algum — hoje índice e query entram crus. A documentação do próprio
modelo trata o prefixo como obrigatório para retrieval; sem ele, documento e pergunta caem no mesmo
espaço "sem tarefa" e a assimetria pergunta-curta → documento-longo (exatamente o caso do RAG) é o que
mais degrada. É provavelmente a causa silenciosa de recuperações medianas que o RRF/BM25 vem compensando.

- **Fix**: prefixar em `embed_texts` (`search_document: `) e `embed_query` (`search_query: `), apenas
  quando o modelo é da família nomic (mapa `model → (doc_prefix, query_prefix)`; `bge-m3` não usa,
  `mxbai-embed-large` usa `Represent this sentence...` só na query).
- **Implicação**: exige reindexação e **muda o espaço** — o marcador de esquema de prefixo precisa
  entrar no `index_info.json` e compor o `embed_space_id` (senão protótipos/SVM/limiar continuam
  válidos num espaço que mudou por baixo — a mesma classe de bug M2 que vocês já corrigiram).
- **Bônus**: recalibrar `DEFAULT_IN_CORPUS_THRESHOLD` depois (os cossenos absolutos mudam de faixa).

### 2.2 Pergunta de acompanhamento não é reescrita (Conversa é multi-turno só na tela)

O `answer_view` exibe uma conversa, mas `chat.answer()` recebe apenas a pergunta corrente — nenhum
histórico chega ao retrieval nem ao prompt. Um "e sobre a segunda parte?" embedda literalmente essa
frase e recupera lixo. Fix clássico e barato: **condensação de query** — um passo curto no LLM local
reescreve a pergunta como standalone usando os últimos 1–2 turnos, e só o resultado vai para
`retrieve()`. Opcionalmente, incluir o último par pergunta/resposta no prompt do `answer` (o
`num_ctx=8192` comporta). É o item de UX/acurácia mais visível para o usuário depois do 2.1.

### 2.3 Pool maior + MMR sobre chunks recuperados

`retrieve()` devolve o top-6 fundido direto. Com overlap de 150 chars e vários chunks do mesmo
documento, o contexto frequentemente gasta 2–3 slots com trechos quase idênticos. O `_mmr` já existe
em `recommend.py`: recuperar um pool de ~20–24 pelo RRF e diversificar para `k` com MMR sobre os
vetores dos chunks (λ≈0.7) — mais documentos distintos no contexto, mesma latência de LLM. Alternativa
mínima: cap de chunks por documento no top-k (ex.: máx. 3) quando o escopo é o corpus inteiro.

### 2.4 Contexto do documento dentro do chunk embeddado

O chunk é embeddado sem saber de onde veio: uma pergunta que menciona o título do vídeo/documento só
acha o chunk se o título vazar no texto. Prependar uma linha curta de contexto ao texto do chunk **na
hora de embeddar** (`{nome do arquivo sem sufixo} — {kind}:\n{chunk}`) é a versão barata de
"contextual chunk headers" e melhora consultas por tópico/título. O texto exibido/enviado ao LLM pode
continuar o original (guardar o header só no vetor, ou aceitar a linha extra no contexto — inofensiva).
Exige reindexação → **empacotar junto com o 2.1 numa única reindexação versionada**.

### 2.5 `low_confidence` usa o cosseno do melhor *fundido*, não o melhor denso

`run_ai_answer` deriva `low_confidence` de `hits[0].score`. Só que `hits` vem ordenado pelo RRF — o
primeiro da fusão não é necessariamente o de maior cosseno denso. Quando o BM25 promove um chunk
lexicalmente forte porém semanticamente mediano, o aviso de fora-de-escopo dispara com o corpus
cobrindo bem a pergunta. Fix de uma linha: `best_score = max(h.score for h in hits)`.

### 2.6 Limiar fora-de-escopo por modelo de embedding

`DEFAULT_IN_CORPUS_THRESHOLD = 0.35` é calibrado para o nomic. A skill documenta `bge-m3`/`mxbai`
como alternativas — trocar o modelo descalibra o aviso em silêncio. Mapa `embed_model → threshold`
(com default conservador para modelo desconhecido), lido do mesmo lugar do `embed_space_id`.

### 2.7 `k` fixo em 6 na GUI

O CLI expõe `--k`; a Conversa não. Um controle discreto (4/6/8/12) no formulário do hub de IA custa
pouco e ajuda em corpus grande (mais contexto) e em máquina lenta (menos).

### 2.8 Harness de avaliação — sem ele, todo ajuste é cego

Nada mede a qualidade de recuperação hoje. Um conjunto pequeno de *golden questions*
(`~/.mill-tools/rag_eval.json`: pergunta → documento(s) que devem aparecer no top-k), rodado por um
botão no Observatório (aba Índice/RAG) e pelo CLI (`ai eval`), reportando hit-rate@k e MRR. É o que
permite afirmar que 2.1–2.4 melhoraram algo — e detectar regressão ao trocar modelo/parâmetro.
Encaixa perfeitamente no espírito read-only+ação-própria do Observatório.

> **Não recomendo agora**: reranker neural (cross-encoder puxa torch — conflita com a decisão base),
> HyDE/multi-query (2 chamadas extras de LLM local por pergunta; só considerar se 2.1–2.3 não
> bastarem), e trocar o RRF por fusão ponderada (o `_RRF_K=60` é insensível por literatura — deixar).

---

## 3. Bugs e arestas ainda presentes

1. **`batch.run_batch` sem isolamento de falha por documento** (`rag/batch.py`): o `answer()` roda sem
   try/except dentro do loop — um erro de LLM no documento 47 aborta o `ai --batch` inteiro e perde os
   46 resultados anteriores. Envolver por fonte e devolver `BatchResult` com campo de erro (ou
   registrar em `observatory/logs`), mantendo o contrato de ordem.
2. **`cancel_event` morto em `run_ai_answer`/`run_ai_command`** (`gui/modules/ai/worker.py`): o
   parâmetro é recebido e nunca checado — não há como cancelar uma resposta presa num modelo lento.
   Checar entre retrieve → answer já ajudaria; ou remover o parâmetro para não prometer o que não faz.
3. **`VectorStore.load` tolera `meta.json` ausente, mas não corrompido**: um `meta.json` truncado ou
   `vectors.npz` inválido levanta cru (`ValueError`/`BadZipFile`) — na GUI vira um `task_error`
   críptico; no CLI, traceback. Estender o mesmo tratamento "warn + índice vazio" para malformação
   (paridade com o que `_load_prototypes` já faz com `BadZipFile`).
4. **Seeds de protótipos em inglês contra corpus PT** (`classify/prototypes.py`): `_DATA_DOMAIN_SEEDS`
   e `_DOCUMENT_TYPE_SEEDS` são 100% EN, mas os documentos/cartões são majoritariamente PT-BR — e o
   nomic é fraco cross-língua. Os domínios `data`/`document` devem estar operando com margens
   artificialmente baixas. Seeds bilíngues ("Invoice or receipt. Nota fiscal ou recibo. Valores,
   impostos, ...") são mudança de 10 linhas; a assinatura de cache já invalida sozinha ao mudar o
   texto. Os seeds de perfil de transcrição (derivados de `label`+`source_hint` PT) não têm o problema.
5. **Ping do embedder em toda pergunta** (`run_ai_answer`): `is_available()` faz um
   `embed_query("ping")` real antes de cada resposta — uma ida extra ao Ollama por pergunta. Cachear a
   disponibilidade por ~60s, ou simplesmente deixar o `embed_query` real falhar e mapear o erro para o
   `SETUP_HINT` (o gate continua nos fluxos frios: reindex, status board).
6. **`embed_query` grava `model_timings.json` a cada pergunta**: uma reescrita de arquivo por query.
   Hoje inócuo (1 pergunta = 1 escrita), mas se a Conversa ganhar condensação de query (2.2), viram 2
   escritas por pergunta — aplicar a mesma soma-antes-de-gravar do `embed_texts`.

Nenhum destes é grave sozinho; 1 e 3 são os únicos com perda real de trabalho/dados do usuário.

---

## 4. Explorar mais os recursos entre ferramentas e hubs

**Busca lexical na Biblioteca** (proposta anterior — confirmo que continua quase de graça): o
`VectorStore` já mantém `_bm25` em cache e `bm25_scores()` aceita máscara. Uma caixa "frase exata" na
Biblioteca que consulta o índice BM25 e destaca o trecho no `file_viewer` cobre o caso "onde eu ouvi
*isso*?" sem LLM, sem embedding e sem UI nova complexa.

**Timestamps nas citações — a ponte que falta entre Transcrição, IA e Áudio**: `ChunkMeta` não carrega
tempo; o Whisper produz segmentos com timestamps que hoje se perdem no `.txt` final. Persistindo um
sidecar leve de segmentos (`<stem>.segments.json`: `[{start, end, char_offset}]`) na transcrição, o
indexer mapeia o offset do chunk → faixa de tempo, e a citação `[2]` vira `[2] aula.txt @ 12:34` com
ação "abrir no player" (bridge Biblioteca→Áudio já existe como padrão). Transforma o RAG de "achou o
documento" em "achou o minuto" — para o perfil `lecture`, é a feature mais valiosa da lista inteira.

**Receitas mal aproveitam o mundo IA/texto**: o registry `ai.py` só tem `ai.answer`. Passos
`text.summary` (TextRank), `text.keywords` (YAKE) e `ai.batch` (o `run_batch` — hoje sem nenhum
chamador de GUI e com o seam de cancelamento já pronto) habilitam receitas 100% locais e sem LLM:
`URL → áudio → transcrição → resumo extrativo + keyphrases` num clique. Adaptadores finos, core pronto.

**Glossário de entidades sem porta de entrada**: `entity_glossary.json` funciona mas é edição manual de
JSON. Duas frentes: (a) seção no diálogo de Configurações (listar/adicionar/remover padrões — nota: o
singleton por idioma exige limpar `_NLP_CACHE` ao salvar); (b) sugestão automática de candidatos — termos
capitalizados frequentes no corpus que o NER estatístico não rotula são exatamente o jargão de domínio
que o glossário existe para cobrir.

**Auto-tags como filtro clicável**: as tags YAKE aparecem na busca da Biblioteca, mas viram valor de
verdade como chips clicáveis (filtrar por tag) e como linha extra no cartão de dados/contexto do chunk
(sinergia com 2.4).

---

## 5. Novas features

**Capítulos automáticos** (proposta anterior — endosso com rota concreta): não precisa nem de
clustering global — a segmentação por tópico cai naturalmente da queda de cosseno entre janelas de
chunks adjacentes do próprio índice (tudo já embeddado); TextRank/YAKE nomeiam cada segmento. Com o
sidecar de timestamps do §4, exporta capítulos de YouTube (`00:00 Introdução`), marcadores no Markdown
e índice navegável no visor. Sinergia total: timestamps + capítulos + citações com tempo compõem o
mesmo investimento.

**Rename inteligente em lote** (proposta anterior — mantida): OCR/describe/keywords → nome sugerido;
o batch rename do roadmap vira caso particular. Sem observação nova.

**Feedback de resposta (👍/👎) na Conversa**: um toque por resposta, gravado em
`~/.mill-tools/retrieval_feedback.json` (pergunta, fontes, score, veredicto). Não requer nenhum ML
agora — mas cria o dataset que futuramente calibra o limiar fora-de-escopo por corpus real e alimenta a
aba de Atividade do Observatório. Custo mínimo, opcionalidade máxima.

---

## 6. Parâmetros ML — o que muda, o que fica, o que entra

Os 4 atuais estão bem escolhidos e a decisão de lê-los das constantes reais (nunca cópia) está correta —
manter. Avaliação individual: dedup 0.95 e distância dHash 8 são conservadores e adequados; piso de
auto-k 20 tem justificativa estatística documentada; λ=0.6 do MMR é o valor canônico.

Candidatos a **entrar no painel** (transparência, e dois deles editáveis):

| Parâmetro | Valor | Proposta |
|---|---|---|
| Limiar fora-de-escopo | 0.35 | **editável**, por modelo de embedding (§2.6) |
| k de recuperação (Conversa) | 6 | **editável** na GUI (§2.7) |
| Chunk size / overlap | 1200/150 | exibir read-only + nota "mudar exige reindexação" |
| Pool do MMR (`related`) | 200 | exibir read-only |
| Teto de sentenças do resumo | 400 | exibir read-only |
| Peso do viés de posição (TextRank) | 0.15 | exibir read-only |

`_RRF_K=60` deve continuar **fora** do painel — a insensibilidade é documentada no próprio código; expor
convidaria ajuste sem efeito. Implicação geral: qualquer parâmetro que altere **o que é embeddado**
(chunk size, prefixos, header de contexto) precisa compor a assinatura do índice/caches — o projeto já
tem o padrão (`embed_space_id`); é só estendê-lo, nunca criar um segundo mecanismo.

---

## 7. Arquivos em `~/.mill-tools/` — avaliação

**O que está bom**: o scanner genérico do `disk_usage` (store novo aparece sozinho) é a decisão que
torna tudo abaixo barato; escrita atômica em grupo nos pares npz/json; caches keyed por
`(path, mtime)`/assinatura são consistentes entre si.

**O que pode mudar**: a dualidade `ai_answer_times` (config.json) × `model_timings.json` está
documentada como paralela sem dual-write — aceitável, mas na próxima vez que alguém tocar a estimativa
de "tempo típico" da Conversa, vale derivá-la do `model_timings.json` (filtro `domain="llm"`, janela
das últimas 5) e aposentar a chave do config.json, eliminando a segunda fonte.

**Arquivos novos propostos**: `rag_eval.json` (golden questions + últimos resultados — §2.8) e
`retrieval_feedback.json` (§5). Ambos append-only com cap, no padrão de `ml_activity.json`.
`chat_history.json` só se/quando a condensação de query (2.2) evoluir para sessões persistentes.

**Implicações**: zero mudança no Observatório (o scanner os lista sozinho); ambos devem registrar o
`embed_space_id` vigente em cada entrada, senão uma reindexação com modelo novo torna o histórico de
avaliação incomparável em silêncio.

---

## 8. Priorização sugerida

1. **Reindexação versionada única**: prefixos do nomic (2.1) + header de contexto no chunk (2.4) +
   marcador de esquema no `index_info`/`embed_space_id` + recalibração do limiar (2.6). Um plano só.
2. **Correções pontuais baratas**: `low_confidence` via max denso (2.5), isolamento de falha no
   `run_batch` (§3.1), load tolerante a corrupção (§3.3), seeds bilíngues (§3.4).
3. **Condensação de query + pool/MMR** (2.2, 2.3) — a Conversa vira conversa de verdade.
4. **Harness de avaliação** (2.8) — antes de qualquer ajuste fino adicional.
5. **Busca lexical na Biblioteca** e **passos text.* nas Receitas** (§4) — vitórias rápidas.
6. **Timestamps + capítulos** (§4/§5) — o maior investimento e o maior retorno de produto.
