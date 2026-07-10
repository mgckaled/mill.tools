# Plano — Harness de avaliação do RAG (golden questions + feedback da Conversa)

> **Origem**: avaliação profunda ML/RAG (sessão Cowork, jul/2026 —
> [`docs/reference/AVALIACAO_ML_RAG_FABLE5.md`](../../reference/AVALIACAO_ML_RAG_FABLE5.md), §2.8, §5 e
> §7). Os planos de espaço de embedding e Conversa multi-turno (ambos implementados) mudaram retrieval e
> limiar medindo com snapshots manuais descartáveis — este plano cria o instrumento **permanente**: um
> conjunto pequeno de *golden questions* com resposta esperada, rodável do Observatório e do CLI,
> reportando hit-rate@k e MRR; mais o feedback 👍/👎 na Conversa, que começa a coletar o dataset real de
> uso. É **pré-requisito declarado** para qualquer ajuste fino futuro (reranker ONNX, mudança de chunking,
> troca de modelo) — sem ele, todo ajuste é cego. Itens dizem *o quê* e *onde*; o *como* é da sessão de
> implementação. **Avaliação é retrieval-only por desenho**: nenhuma chamada de LLM — determinística,
> rápida e barata; julgar a *resposta* gerada (LLM-as-judge) fica explicitamente fora de escopo.

## Checklist ativo de salvaguardas (padrões recorrentes — auditar neste escopo)

| Salvaguarda | Situação esperada neste escopo |
|---|---|
| Escritas não-atômicas / `io_atomic` | As duas persistências novas nascem atômicas; o log de feedback **reusa `observatory/_jsonlog.py`** (append com cap), não inventa um terceiro formato |
| Timeouts herdados/ausentes | A rodada de avaliação embedda N queries — usa o caminho normal do `embed_query` (timeouts existentes); pré-check de disponibilidade com `AVAILABILITY_TIMEOUT`, nunca `EMBED_TIMEOUT` |
| Duplicação de esqueleto intra-pacote | Worker+view da rodada no Observatório seguem o padrão do `index_worker.py` (mesmo `module_id="observatory"`, botão + progresso + Cancelar) — não criar um segundo estilo de pipeline no hub |
| Docstring de pacote desatualizado | `rag/__init__.py` ganha o módulo novo — atualizar |
| Strings PT no core | Labels/relatório user-facing em PT ok; docstrings/logs EN |

**Regra transversal (lição do §7 da avaliação)**: toda entrada persistida — rodada de avaliação e item de
feedback — grava o `embed_space_id` vigente; sem isso, uma reindexação com esquema/modelo novo torna o
histórico incomparável em silêncio. E toda rodada começa com o pré-check `is_stale_scheme == False`
(lição do detour do plano de espaço de embedding) — avaliar contra índice em esquema antigo mede artefato.

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline |
| 1 | Core: `rag/eval.py` — golden set, runner, métricas |
| 2 | Persistências (golden set + histórico de rodadas + feedback) |
| 3 | CLI `ai eval` |
| 4 | Observatório: seção Avaliação (worker + view) |
| 5 | Feedback 👍/👎 na Conversa |
| 6 | Verificação + docs |

---

## Fase 0 — Baseline

Suíte `unit` verde (com a pendência de flakiness sob ordem aleatória já registrada no ROADMAP §12 —
ortogonal, não bloqueia; se uma falha intermitente aparecer, conferir contra a lista de lá antes de
investigar como regressão deste plano). Pré-check `is_stale_scheme == False` no índice real.

---

## Fase 1 — Core: `core/rag/eval.py` (novo, puro)

1. **Golden set tipado**: dois tipos de pergunta — **coberta** (`pergunta` + 1..N documentos esperados,
   por path) e **fora-do-acervo** (`pergunta` sem documento esperado — o acerto é o flag de baixa
   cobertura disparar). Os 15 itens da calibração do limiar (10 cobertas + 5 fora) são o seed natural.
2. **Runner injetável** (`embed_query_fn`/store, mesmo padrão do retriever — unit-testável sem Ollama):
   para cada pergunta, roda o `retrieve()` real (pool+MMR, o pipeline de produção — avaliar outro caminho
   mediria outra coisa) com a pergunta **crua** (condensação é de conversa; golden questions são
   standalone por definição) e coleta hits + `pool_max_score`.
3. **Métricas por rodada**: hit-rate@k (documento esperado entre as fontes distintas dos hits), MRR sobre
   documentos (posição da primeira fonte esperada), média de `pool_max_score` das cobertas vs. das
   fora-do-acervo (monitora o gap do limiar 0.72 ao longo do tempo), e acurácia do flag fora-do-acervo.
   `k` da rodada = o mesmo default da Conversa; registrar no resultado.
4. Resultado tipado da rodada carrega: métricas, `embed_space_id`, esquema, `k`, nº de docs/chunks do
   índice e timestamp — o suficiente para comparar duas rodadas honestamente.

---

## Fase 2 — Persistências (`~/.mill-tools/`)

1. **`rag_eval.json`**: golden set + histórico de rodadas (cap pequeno, ex.: últimas 20 — descarta a mais
   antiga, formato já validado pelo `model_timing`). Escrita atômica. Dono: `rag/eval.py`.
2. **`retrieval_feedback.json`**: log append-only de feedback da Conversa via
   **`observatory/_jsonlog.py`** (cap ~200, padrão `ml_activity.json`). Cada entrada: `query` (original),
   `search_query` (o que foi buscado — a distinção criada no plano da Conversa), fontes citadas,
   `pool_max_score`, `low_confidence`, veredicto (👍/👎), modelo de resposta, `embed_space_id`. Dono do
   arquivo: um módulo pequeno em `core/rag/` (não `observatory/` — o pacote de lá segue read-only; o
   `_jsonlog` é só o helper genérico).
3. Ambos aparecem sozinhos no disk_usage do Observatório (scanner genérico — verificar, não implementar).
4. Atualizar a tabela de persistências da skill `ml-rag` na Fase 6.

---

## Fase 3 — CLI `ai eval` (skill `cli` para padrões)

Subcomando com três ações mínimas: **rodar** (relatório da rodada + delta contra a rodada anterior
comparável — mesmo `embed_space_id`; rodadas de espaços diferentes são mostradas como incomparáveis, não
como regressão), **listar** o golden set, e **adicionar** uma pergunta (coberta com path, ou
fora-do-acervo). Read-only exceto pelas escritas próprias; `install_log_handler=False`; UTF-8 no stdout
(imprime paths). Sem `CLIEventBus` se a rodada for rápida o bastante para dispensar barra — decidir na
implementação pelo tamanho real do golden set.

---

## Fase 4 — Observatório: seção Avaliação

Na aba Índice/RAG (que já é a exceção "dono do recurso roda o próprio pipeline"): seção com o resumo da
última rodada (métricas + delta contra a anterior comparável + aviso de incomparável quando o
`embed_space_id` mudou) e botão **Rodar avaliação** — worker próprio no padrão exato do
`index_worker.py` (`module_id="observatory"`, progresso por pergunta, Cancelar entre perguntas via o seam
padrão). Gate do embedder antes de rodar (com `use_cache` fresco, não o TTL da Conversa). Registrar a
conclusão no `ml_activity` (padrão: quem grava é o worker, nunca o core). Eventos novos → `events.md` na
Fase 6.

---

## Fase 5 — Feedback 👍/👎 na Conversa

1. Dois botões discretos por card de turno respondido (`answer_view.py`) — um toque, sem diálogo;
   feedback dado desabilita os botões do card (sem edição — é sinal, não revisão). Grava a entrada da
   Fase 2.2 e registra no `ml_activity`.
2. **Promover 👍 a golden question** (opcional, se couber na sessão): um 👍 cujo turno tem fontes citadas
   é um candidato pronto (pergunta = `search_query`, esperado = fontes) — ação "promover" no CLI
   (`ai eval` add a partir do feedback) basta; **não** construir UI de curadoria agora.
3. O que **não** fazer: nenhum uso automático do feedback (recalibração de limiar, treino de reranker) —
   este plano só coleta; os usos são planos futuros, com o dataset já existindo.

---

## Fase 6 — Verificação + docs

1. Suíte `unit` verde; `ruff` limpo; cobertura de `core/rag/` sem regressão (baseline 99%).
2. Re-auditar o checklist de salvaguardas do topo (em especial: `_jsonlog` reusado; `embed_space_id` em
   toda entrada persistida; `observatory/` core continua read-only).
3. **Skill `ml-rag`** (obrigatório): seção nova do `eval.py` (contratos: retrieval-only, pergunta crua,
   comparabilidade por `embed_space_id`); tabela de persistências ganha `rag_eval.json` e
   `retrieval_feedback.json`; feedback documentado como coleta-sem-uso-automático.
4. **Skill `cli`**: subcomando `ai eval` registrado nos padrões de lá. **Skill `design-system` /
   `events.md`**: eventos da rodada no Observatório + payload do feedback na Conversa.
5. **CLAUDE.md**: bloco de comandos ganha `ai eval`; §hubs — linha do Observatório menciona a seção
   Avaliação se o texto atual enumerar as seções; validar.
6. **ROADMAP.md**: marcar o harness como entregue onde a avaliação o listou; a decisão sobre o reranker
   ONNX permanece lá como condicional ("só se o eval mostrar teto de retrieval").
7. Entrada no `HISTORY.md` (decisões: avaliação retrieval-only sem LLM; pergunta crua sem condensação;
   comparabilidade por `embed_space_id`; feedback coleta-primeiro-usa-depois). Plano →
   `docs/plans/implemented/`.

---

## Não-achados dignos de nota (não "consertar")

- **LLM-as-judge / avaliação da resposta gerada**: fora de escopo por desenho — caro, não-determinístico
  e mede outra coisa (geração, não retrieval). Se um dia entrar, é plano próprio.
- **Benchmark IR completo** (nDCG, corpus sintético, queries geradas): sobre-engenharia para um acervo
  pessoal — 15–30 golden questions honestas valem mais.
- A condensação de query **não** é avaliada aqui (golden questions são standalone); avaliar reescritas de
  follow-up exigiria golden *conversas* — registrar como ideia futura se a prática pedir.
- O flakiness da suíte sob ordem aleatória (ROADMAP §12) segue como pendência própria — a pista do
  `_CONFIG_DIR` cacheado no import de `gui/settings.py` merece micro-plano de investigação dedicado, não
  um side-fix aqui.
