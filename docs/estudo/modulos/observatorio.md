# Hub Observatório — o painel cross-módulo de ML (Sessão 5)

Delta doc. O Observatório é o hub que **observa** toda a maquinaria de ML/RAG: status dos gates, logs,
atividade, tempos de resposta, saúde do índice. É quase todo **read-only** — com duas exceções
importantes que rodam pipelines.

> **Base:** [`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md) (os motores),
> [`../conceitos/RAG.md`](../conceitos/RAG.md) (índice + avaliação), [`ia.md`](ia.md) (o hub vizinho),
> [`../conceitos/EVENTOS.md`](../conceitos/EVENTOS.md) (os pipelines das exceções),
> [`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) (abas aninhadas).

## Por que um hub próprio (e não uma aba do IA)

🔑 A superfície de ML cobre RAG **e** Biblioteca **e** Transcrição **e** Dados **e** Receitas — aninhá-la
no hub IA seria um descasamento semântico (o IA é só RAG). Por isso o Observatório é um hub à parte,
transversal. Ele agrega o que já existe nos outros módulos, sem lógica nova.

## `core/observatory/` é 100% read-only

O pacote puro (`activity`/`logs`/`status`/`model_timing`/`disk_usage`) só **lê e agrega** — ele nunca
roda um pipeline. Quem grava nos logs são os **workers/CLI runners** no ponto de conclusão (RAG dedup/
classify, Dados outliers...), **nunca** as funções puras de `core/ml`/`core/text`. É a regra de
fronteira: funções puras não escrevem log; o worker registra a atividade quando termina. Detalhe em
[`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md) §Persistências.

## As 5 abas

`Índice/RAG · Status · Atividade · Logs · Tempo de resposta`. Elas expõem o que os logs de
`~/.mill-tools/` acumularam:

- **Status** — os 9 gates (`[ml]`, `[nlp]`, embedder, binários...), a presença de chaves de nuvem (só
  presença, nunca o valor), o inventário Ollama.
- **Atividade** / **Logs** — os dois logs append-only: sucessos cross-módulo (`ml_activity.json`) e
  falhas (`ml_logs.json`, alimentado pelo hook central de `task_error` em `events.py` — Sessão 3 §2.2).
- **Tempo de resposta** — a latência por `(domínio, modelo)` que o `_TimingCallback` do `llm_factory`
  ([`../arquivos/llm_factory.md`](../arquivos/llm_factory.md)) instrumentou em toda chamada.

O selo de novidades no AppBar (`last_ml_activity_seen`) conta quantas atividades você ainda não viu — um
snapshot barato recomputado ao visitar o hub.

## As duas exceções que **rodam pipelines**

Aqui o Observatório deixa de ser só leitura. A aba **Índice/RAG** é aninhada
(`Índice·Avaliação·Painel·Uso de disco`), e duas sub-abas têm worker próprio:

### Índice — a reindexação

O botão **Reindexar** roda o próprio pipeline (`gui/modules/observatory/index_worker.py`,
`module_id="observatory"`, com progresso + Cancelar), no mesmo padrão de um módulo-ferramenta (Sessão 2/3).
🔑 É **aqui** que a reindexação mora (o hub IA só aponta para cá). O `build_index` recebe
`force=is_stale_scheme(...)` — porque uma mudança de esquema não move o mtime dos arquivos, e sem
`force` o botão só mentiria no sidecar sem reembeddar (o bug real do
[`../conceitos/EMBEDDINGS.md`](../conceitos/EMBEDDINGS.md)/RAG).

### Avaliação — o harness retrieval-only

A sub-aba **Avaliação** roda o harness de avaliação do RAG: um **golden set** de perguntas (cobertas e
fora-do-acervo) contra o `retrieve()` de produção, medindo **hit-rate@k / MRR** e a acurácia do flag de
cobertura. 🔑 É **retrieval-only** — nenhuma chamada de LLM (determinístico, rápido, barato; julgar a
resposta gerada fica fora de escopo por desenho). Roda com progresso/Cancelar, `module_id="observatory"`,
recusando índice vazio ou esquema antigo (avaliar um índice stale mediria artefato).

🔑 A lição de arquitetura: `core/observatory/` continua **puro read-only**; os **pipelines** (reindex,
eval) vivem só na camada `gui/`. Ou seja, o "escrever" não contamina o pacote puro — ele fica na borda,
como todo pipeline.

---

# Perguntas de fixação

1. Por que o Observatório é um hub separado do IA, e não uma aba dele?
2. `core/observatory/` é read-only. Então quem **grava** nos logs de atividade/falha, e em que momento?
3. As abas Status/Tempo de resposta exibem dados que outros componentes produziram. De onde vêm os
   tempos de resposta? (dica: `_TimingCallback` do `llm_factory`)
4. Duas sub-abas rodam pipelines de verdade. Quais, e por que a reindexação mora aqui e não no hub IA?
5. A Avaliação é "retrieval-only". O que isso significa, e por que **não** chamar o LLM para julgar a
   resposta foi uma decisão de desenho?
