# Plano — Correções RAG/ML (2ª rodada, pós-avaliação de produto)

> **Origem**: avaliação profunda de produto+acurácia do ML/RAG (sessão Cowork, jul/2026 —
> [`docs/reference/AVALIACAO_ML_RAG_FABLE5.md`](../../reference/AVALIACAO_ML_RAG_FABLE5.md), §2.5 e §3).
> Distinta da 1ª rodada ([`PLANO_CORRECOES_QUARTETO_ML.md`](../implemented/PLANO_CORRECOES_QUARTETO_ML.md),
> já implementada): aquela foi revisão de código arquivo-a-arquivo; esta corrige contratos e arestas que só
> apareceram olhando o produto de ponta a ponta. Itens dizem *o quê* e *onde*; o *como* é da sessão de
> implementação (agentes + context7 quando indicado). Todos os itens são pequenos — cabe em 1 sessão.

## Checklist ativo de salvaguardas (padrões recorrentes — auditar neste escopo)

| Salvaguarda | Situação esperada neste escopo |
|---|---|
| Escritas não-atômicas / `io_atomic` | Auditar o item 2.1 (`VectorStore.load` tolerante) — a *escrita* já é atômica em grupo; aqui é o lado da leitura |
| Timeouts herdados/ausentes | Item 2.2 (ping do embedder) mexe justamente num gate de disponibilidade — manter `AVAILABILITY_TIMEOUT`, nunca herdar `EMBED_TIMEOUT` |
| Duplicação de esqueleto intra-pacote | Verificar que o tratamento de erro por item do `run_batch` (1.2) reusa o padrão do `_index_one` (log + skip), não um segundo estilo |
| Docstring de pacote desatualizado | `rag/__init__.py` e `ml/classify/` — conferir após as fases |
| Strings PT no core | Mensagens user-facing novas (erro por documento no batch) podem ser PT (exceção formalizada); docstrings/logs em EN |

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline |
| 1 | Contratos de resultado (low_confidence, batch) |
| 2 | Robustez (load tolerante, ping, cancel_event) |
| 3 | Seeds bilíngues dos protótipos |
| 4 | Miudezas + convenções |
| 5 | Verificação + docs |

---

## Fase 0 — Baseline

Suíte `unit` verde; anotar cobertura atual de `core/rag/` e `core/ml/classify/` (a 1ª rodada fechou em ~98%
no quarteto — não regredir).

---

## Fase 1 — Contratos de resultado

1. **[BUG de contrato] `low_confidence` lê o melhor *fundido*, não o melhor denso**
   (`gui/modules/ai/worker.py::run_ai_answer`). `hits` vem ordenado pelo RRF — `hits[0].score` não é
   necessariamente o maior cosseno denso do top-k; quando o BM25 promove um chunk lexical forte porém
   semanticamente mediano, o aviso de fora-de-escopo dispara com o corpus cobrindo bem a pergunta.
   Fix: `best_score = max(h.score for h in hits)`. **Atenção**: a regra de fronteira nº 2 da skill
   `ml-rag` descreve o comportamento antigo ("deriva do `hits[0].score`") — atualizar a skill na Fase 5.
   Teste: hits com ordem fundida ≠ ordem densa → flag correto.
2. **[BUG com perda de trabalho] `run_batch` sem isolamento de falha por documento**
   (`core/rag/batch.py`). O `answer()` roda sem proteção dentro do loop — um erro de LLM no documento N
   aborta o `ai --batch` inteiro e perde os N−1 resultados anteriores. Envolver por fonte (log warning +
   resultado com campo de erro em `BatchResult`, ou skip registrado — decidir na implementação, mantendo o
   contrato de ordem e o `cancel_is_set` intactos). O consumidor único hoje é `cli/ai.py --batch` —
   ajustar a impressão para diferenciar sucesso/falha por documento. Teste: 3 fontes, a 2ª falha → 1ª e 3ª
   presentes.

---

## Fase 2 — Robustez

1. **`VectorStore.load` tolera `meta.json` ausente, mas não corrompido** (`core/rag/store.py`). Um
   `meta.json` truncado ou `vectors.npz` inválido levanta cru (`ValueError`/`BadZipFile`) — na GUI vira
   `task_error` críptico, no CLI traceback. Estender o tratamento existente (warn + índice vazio) para
   malformação — paridade com o que `classify/prototypes._load_prototypes` já faz. Teste: npz truncado e
   json inválido → store vazio + warning, sem exceção.
2. **Ping do embedder em toda pergunta** (`gui/modules/ai/worker.py::run_ai_answer` +
   `core/rag/embedder.py`). `is_available()` faz um `embed_query("ping")` real antes de cada resposta —
   uma ida extra ao Ollama por pergunta da Conversa. Escolher na implementação: cachear a disponibilidade
   por curto período (TTL ~60 s, no embedder) **ou** remover o pré-check do fluxo quente e mapear a falha
   do `embed_query` real para o `SETUP_HINT`. Os fluxos frios (reindex, status board do Observatório)
   mantêm o gate explícito.
3. **`cancel_event` morto em `run_ai_answer`/`run_ai_command`** (`gui/modules/ai/worker.py`). O parâmetro
   é recebido e nunca checado — promessa vazia de cancelamento. Decidir: checar entre os estágios
   (retrieve → answer) e emitir o cancelamento no padrão dos outros workers, **ou** remover o parâmetro.
   Não fingir cancelar o `chain.invoke` em si (não é interrompível hoje) — documentar o limite escolhido.

---

## Fase 3 — Seeds bilíngues dos protótipos

**`_DATA_DOMAIN_SEEDS` / `_DOCUMENT_TYPE_SEEDS` são 100% EN contra um corpus majoritariamente PT-BR**
(`core/ml/classify/prototypes.py`) — e o `nomic-embed` é fraco cross-língua, então os domínios
`data`/`document` operam com margens artificialmente baixas. Tornar os seeds bilíngues (frase EN + frase
PT no mesmo texto de protótipo, ex.: `"Invoice or receipt. Nota fiscal ou recibo. Valores, impostos,
parcelas."`). A assinatura de cache (`_seeds_signature`) invalida sozinha ao mudar o texto — **zero
migração**. Os seeds de perfil de transcrição (derivados de `label`+`source_hint`, já PT) não são tocados.
Teste: assinatura muda; classify zero-shot continua funcionando com o cache regenerado.

---

## Fase 4 — Miudezas + convenções

1. **`embed_query` grava `model_timings.json` a cada chamada** (`core/rag/embedder.py`). Hoje inócuo
   (1 pergunta = 1 escrita), mas o plano de Conversa multi-turno adicionará uma 2ª chamada por pergunta —
   deixar preparado: aplicar a mesma soma-antes-de-gravar do `embed_texts` quando houver mais de um
   `embed_query` no mesmo fluxo, ou registrar como aceito se a implementação julgar prematuro (anotar no
   plano da Conversa, então).
2. **[Convenção]** Docstrings/comentários PT→EN nos arquivos tocados (regra "corrigir na mesma passagem").

---

## Fase 5 — Verificação + docs

1. Suíte `unit` verde; `ruff` limpo; cobertura de `core/rag/`/`core/ml/classify/` sem regressão.
2. Re-auditar o checklist de salvaguardas do topo.
3. **Skill `ml-rag`** (obrigatório): (a) regra de fronteira nº 2 — o `low_confidence` agora deriva do
   **max** dos cossenos densos do top-k, não de `hits[0]`; (b) anotar que as alternativas de embed
   `bge-m3`/`mxbai-embed-large` foram **descartadas por decisão** (dimensão >1000 — dobra memória do
   índice e quebra a suposição 768), para a menção não virar convite a drift; (c) `run_batch` — registrar
   o novo contrato de falha por documento.
4. **CLAUDE.md**: conferir §Módulo IA / §hubs — nada do afirmado deve mudar, mas validar.
5. Entrada no `HISTORY.md` (decisões: contrato do low_confidence; seeds bilíngues; embeds alternativos
   descartados por dimensão). Plano → `docs/plans/implemented/`.

---

## Não-achados dignos de nota (não "consertar")

- O `.score` reportado por chunk **continua o cosseno denso** — o fix 1.1 muda só a agregação no worker,
  não o contrato do `RetrievedChunk`.
- O fallback denso-puro quando o BM25 não tem match (`lexical.max() <= 0`) está correto — não tocar.
- `batch.run_batch` manter o seam `cancel_is_set` como está (nenhum chamador cancelável ainda — o plano
  de integrações é quem cria um).
- `DEFAULT_IN_CORPUS_THRESHOLD = 0.35` **não** é recalibrado aqui — isso pertence ao plano da reindexação
  versionada (prefixos do nomic), quando os cossenos mudam de faixa.
