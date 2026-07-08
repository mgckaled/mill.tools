# Plano — Espaço de embedding versionado (prefixos do nomic + chunk contextual + reindexação)

> **Origem**: avaliação profunda ML/RAG (sessão Cowork, jul/2026 —
> [`docs/reference/AVALIACAO_ML_RAG_FABLE5.md`](../../reference/AVALIACAO_ML_RAG_FABLE5.md), §2.1, §2.4,
> §2.6). O achado nº 1 da avaliação: o `nomic-embed-text` foi **treinado com prefixos de tarefa**
> (`search_document:` para corpus, `search_query:` para consultas) e o embedder envia tudo cru — o maior
> ganho de acurácia barato disponível. Este plano agrupa **tudo que muda o que é embeddado** numa única
> reindexação versionada: prefixos, header contextual de chunk e a adoção do `core/text/clean.py` no
> indexer (fronteira registrada no ROADMAP pelo `PLANO_INSIGHTS_QUALIDADE`, já implementado).
> **Pré-requisitos (ambos implementados)**: `PLANO_CORRECOES_RAG_ML_2` (contratos corrigidos) e
> `PLANO_INSIGHTS_QUALIDADE` (`clean.py` existe). Itens dizem *o quê* e *onde*; o *como* é da sessão de
> implementação (agentes + context7 — a Fase 1 é de verificação guiada obrigatória).

## Checklist ativo de salvaguardas (padrões recorrentes — auditar neste escopo)

| Salvaguarda | Situação esperada neste escopo |
|---|---|
| Escritas não-atômicas / `io_atomic` | `index_info.json` já é escrito em grupo atômico via `store.persist` — o campo novo entra no mesmo grupo, nunca em escrita separada |
| Timeouts herdados/ausentes | N/A — nenhum gate novo; o embedder mantém `AVAILABILITY_TIMEOUT`/`EMBED_TIMEOUT` como estão |
| Duplicação de esqueleto intra-pacote | O mapa modelo→prefixos vive **só** no `embedder.py` (fonte única); o esquema de versionamento reusa o `embed_space_id` existente — **proibido** criar um segundo mecanismo de assinatura |
| Docstring de pacote desatualizado | `rag/__init__.py` e docstring do `embedder.py` — atualizar com o esquema de prefixos |
| Strings PT no core | Mensagem "índice em esquema antigo — reindexe" é user-facing → PT ok; docstrings/logs EN |

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline |
| 1 | Verificações guiadas (prefixos do nomic, LangChain) |
| 2 | Prefixos de tarefa no embedder |
| 3 | Chunk contextual + limpeza na indexação |
| 4 | Versionamento do esquema + invalidação de caches |
| 5 | Reindexação + recalibração do limiar |
| 6 | Verificação + docs |

---

## Fase 0 — Baseline

Suíte `unit` verde. Antes de mexer em qualquer coisa, guardar um **snapshot de referência do retrieval
atual**: ~10 perguntas reais contra o corpus atual com os top-k e scores anotados (manual ou script
descartável). É o único jeito de comparar antes/depois sem o harness de avaliação (plano futuro) — sem
isso, a melhoria dos prefixos fica anedótica.

---

## Fase 1 — Verificações guiadas (context7 — o resultado define detalhes do fix)

1. **Strings exatas dos prefixos do nomic**: confirmar na doc oficial do `nomic-embed-text` os prefixos de
   retrieval (`search_document: ` / `search_query: `, com espaço) e se valem para a versão servida pelo
   Ollama. Confirmar também que nem o Ollama nem o `langchain_ollama.OllamaEmbeddings` adicionam prefixo
   por conta própria (senão duplicaríamos).
2. **Alternativas registradas**: `bge-m3`/`mxbai` já foram **descartados por decisão** (dimensão >1000 —
   registrado no HISTORY pela 2ª rodada). O mapa de prefixos nasce só com a família nomic; modelo fora do
   mapa → sem prefixo (comportamento atual), nunca erro.

---

## Fase 2 — Prefixos de tarefa no embedder (`core/rag/embedder.py`)

1. Mapa `modelo → (doc_prefix, query_prefix)` no embedder (fonte única), aplicado em `embed_texts`
   (documento) e `embed_query` (consulta). Chaveado por família (qualquer tag contendo `nomic`), para
   cobrir `nomic-embed-custom` e variantes.
2. O ping de `is_available()` e os textos de protótipo do classify (`profile_prototypes` chama `embed_fn`)
   passam pelo mesmo caminho de `embed_texts` — conferir que os protótipos recebem o prefixo de
   **documento** (eles são comparados contra vetores de documento) e que isso acontece sem mudança nos
   call sites (a injeção de `embed_fn` já encaminha para `embed_texts`).

---

## Fase 3 — Chunk contextual + limpeza na indexação (`core/rag/indexer.py`)

1. **Adoção do `clean.py`**: `_read_indexable_text` passa a limpar o corpo via
   `core/text/clean.clean_document_text` — os marcadores `--- Página N ---` e o boilerplate param de ser
   embeddados nos chunks (hoje poluem retrieval e BM25). Resolve o ponteiro deixado no ROADMAP.
2. **Header contextual de chunk**: na hora de embeddar, prepender ao texto do chunk uma linha curta de
   contexto (`{stem do arquivo} — {kind}`). **Contrato**: `ChunkMeta.text` continua o texto original —
   o header entra **só no vetor** (o que também preserva o BM25, construído sobre `m.text`, sem tokens
   artificiais de nome de arquivo). Implementação natural: compor `header + chunk` apenas na lista passada
   ao `embed_fn`.
3. Ambos exigem reindexação — é exatamente por isso que moram neste plano e não nos anteriores.

---

## Fase 4 — Versionamento do esquema + invalidação de caches

1. **Marcador de esquema**: campo novo no `index_info.json` (ex.: `embed_scheme: 2` ou descrição
   `"nomic-prefix+ctx-header+clean"` — decidir na implementação) gravado por `store.persist`; índice
   antigo sem o campo → esquema 1.
2. **`rag/stats.embed_space_id`** passa a dobrar o esquema (ex.: `"{modelo}:{dim}:{esquema}"`). Como
   protótipos e SVM do classify **já** dobram o `embed_space_id` nas assinaturas (correção M2 da 1ª
   rodada), a invalidação deles vem de graça — verificar com teste, não assumir.
3. **[AUDITORIA] Mapa semântico (`ml/cache.py` / `corpus_signature`)**: conferir se a assinatura do mapa
   é derivada de `(path, mtime)` dos documentos — nesse caso uma reindexação com esquema novo **não** a
   mudaria (mesmos arquivos, vetores diferentes) e o mapa cacheado ficaria silenciosamente do espaço
   antigo. Se confirmado, dobrar o `embed_space_id` também ali. Mesmo pente-fino para qualquer outro
   cache derivado de vetores.
4. **Detecção de índice em esquema antigo**: o status do índice (linha read-only no hub de IA + aba
   Índice/RAG do Observatório, via `stats`/`analytics`) deve sinalizar "índice em esquema antigo —
   reindexe" quando `embed_scheme` do sidecar ≠ esquema atual do código. A migração é o botão Reindexar
   existente — **nenhum fluxo de migração novo**.

---

## Fase 5 — Reindexação + recalibração do limiar

1. Reindexar o corpus real (botão do Observatório) e repetir o snapshot da Fase 0 — comparar top-k e
   scores; registrar o antes/depois no plano ao movê-lo para `implemented/`.
2. **Recalibrar `DEFAULT_IN_CORPUS_THRESHOLD`** (`core/ml/recommend.py`, hoje 0.35, calibrado para o
   espaço sem prefixo): com prefixos, os cossenos absolutos mudam de faixa. Método simples e documentado:
   medir o melhor cosseno denso de perguntas claramente cobertas vs. claramente fora do corpus (as do
   snapshot servem) e escolher um piso conservador entre as duas faixas. Registrar o valor e o método no
   comentário da constante.

---

## Fase 6 — Verificação + docs

1. Suíte `unit` verde; `ruff` limpo; cobertura de `core/rag/` sem regressão (baseline 99%).
2. Re-auditar o checklist de salvaguardas do topo (em especial: nenhum segundo mecanismo de assinatura).
3. **Skill `ml-rag`** (obrigatório): seção do embedder ganha o esquema de prefixos e o mapa por família;
   `indexer` ganha a limpeza + header contextual (com o contrato "header só no vetor, `ChunkMeta.text`
   intacto, BM25 preservado"); `embed_space_id` documentado com o componente de esquema; limiar
   recalibrado com valor novo.
4. **CLAUDE.md**: conferir §hubs/IA — a linha sobre o RAG local não deve mudar; validar.
5. **ROADMAP.md**: remover o ponteiro "adotar `clean.py` no indexer" (resolvido aqui).
6. Entrada no `HISTORY.md` (decisões: prefixos de tarefa por família de modelo; header contextual só no
   vetor; esquema versionado dentro do `embed_space_id`; limiar recalibrado — valor e método). Plano →
   `docs/plans/implemented/`.

---

## Não-achados dignos de nota (não "consertar")

- `_RRF_K = 60` e a fusão RRF ficam como estão — a literatura registra insensibilidade; nada neste plano
  muda o ranking híbrido em si.
- `CHUNK_SIZE`/`CHUNK_OVERLAP` (1200/150) **não** mudam aqui — mudá-los também invalidaria o índice, mas
  não há evidência de problema; se um dia mudarem, o mecanismo de esquema criado aqui já os cobre.
- O contrato `.score = cosseno denso` permanece intocado.
- Pool maior + MMR no retrieve **não** entram aqui — pertencem ao `PLANO_CONVERSA_MULTITURNO` (não mexem
  no que é embeddado; não exigem reindexação).

---

## Resultado (Fase 5, 08/07/2026)

Reindexação real do acervo pessoal (85 docs, 14.844 chunks — livros de Duna, transcrições de vídeo
técnico/IA, "Claude's Constitution", cheatsheets), confirmada pelo sidecar
(`embed_scheme: "nomic-prefix+ctx-header+clean"`). Backup do índice pré-reindexação preservado em
`~/.mill-tools/rag_backup_pre_fase5_esquema_novo` (fora do controle de versão; o usuário decide quando
descartar).

**Snapshot antes/depois** (10 perguntas reais, top-8 por `retrieve()`): os documentos recuperados no
top-k se mantiveram os mesmos antes e depois, sem regressão visível nem ganho visível de relevância
neste corpus pequeno — o valor desta fase é a correção estrutural (prefixos aplicados corretamente,
marcadores de página fora do texto embeddado, header contextual), não um salto de acurácia mensurável
com este método/amostra.

**Recalibração do limiar — achado honesto**: medido o melhor cosseno denso (mesmo caminho de
`in_corpus()`) para 10 perguntas claramente cobertas pelo acervo vs. 5 claramente fora dele (culinária,
manutenção de carro, xadrez, imposto de renda, adestramento de cachorro). As duas faixas **se
sobrepõem** (cobertas: 0.7045–0.8688; fora: 0.6502–0.7321) — o `nomic-embed-text` tem um piso de cosseno
alto para textos PT-BR curtos não relacionados, e a média antes/depois da reindexação quase não mudou
(~0.79 → 0.80), então não houve alargamento observável da separação entre classes por causa dos
prefixos. O valor antigo (0.35) nunca disparava o aviso — nem antes nem depois desta reindexação — era um
no-op funcional. Escolhido **0.68** (`core/ml/recommend.DEFAULT_IN_CORPUS_THRESHOLD`): margem abaixo do
mínimo medido no acervo, priorizando zero alarme falso de "fora do acervo" sobre pergunta real coberta
(o erro mais custoso num RAG pessoal) sobre capturar toda pergunta fora do acervo — ainda assim captura
as 2 das 5 perguntas fora do acervo que pontuaram abaixo de 0.70 na amostra. Ver comentário da constante
para o método completo.
