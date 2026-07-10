# Plano — Conversa multi-turno (condensação de query + pool/MMR + k na GUI)

> **Origem**: avaliação profunda ML/RAG (sessão Cowork, jul/2026 —
> [`docs/reference/AVALIACAO_ML_RAG_FABLE5.md`](../../reference/AVALIACAO_ML_RAG_FABLE5.md), §2.2, §2.3,
> §2.7). A Conversa do hub de IA é multi-turno **só na tela**: o `answer_view` renderiza um card por
> turno, mas `chat.answer()` recebe apenas a pergunta corrente — um "e sobre a segunda parte?" embedda
> literalmente essa frase e recupera lixo. Este plano fecha a lacuna com condensação de query, diversifica
> o contexto com pool+MMR e expõe o `k` na GUI. **Pré-requisito**: `PLANO_RAG_ESPACO_EMBEDDING`
> **implementado** — três consequências dele estão incorporadas abaixo: o limiar recalibrado (0.72) tem
> gap estreito (~0.024) e torna a condensação sensível a paráfrase ruim (Fases 0.3 e 3.2); o header
> contextual `{stem} — {kind}` nos vetores cria sinergia com a resolução de referências no prompt de
> condensação (Fase 1.1); e o detour do `force=`/esquema exige pré-check de `is_stale_scheme` antes de
> qualquer medição (Fase 0.1). Itens dizem *o quê* e *onde*; o *como* é da sessão de implementação
> (agentes + context7 quando indicado). Superfícies de GUI seguem a skill `design-system` (eventos em
> `events.md`, regra de ouro do spinner).

## Checklist ativo de salvaguardas (padrões recorrentes — auditar neste escopo)

| Salvaguarda | Situação esperada neste escopo |
|---|---|
| Escritas não-atômicas / `io_atomic` | N/A — nenhuma persistência nova (histórico vive em memória da view; `last_ai_k` via `gui/settings` existente) |
| Timeouts herdados/ausentes | A condensação é uma chamada de LLM local — herda o caminho do `make_llm` (timing incluído); falha/lentidão **nunca** bloqueia a resposta (fallback = pergunta crua) |
| Duplicação de esqueleto intra-pacote | O MMR **não** ganha 3ª cópia: `recommend._mmr` e `summarize._mmr` já existem (a duplicação text↔ml é decisão registrada); o retriever deve reusar o de `core/ml/recommend` — mesmo pacote-mundo, sem nova exceção de camada |
| Docstring de pacote desatualizado | `rag/__init__.py` e docstrings de `retriever`/`chat` — atualizar |
| Strings PT no core | Prompt de condensação é instrução de modelo em PT (padrão do `RAG_PROMPT`/`nl2sql` — ok); labels novos da GUI em PT; docstrings/logs EN |

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline |
| 1 | Condensação de query (core) |
| 2 | Histórico no worker + GUI da condensação |
| 3 | Pool + MMR no retrieve |
| 4 | `k` exposto na GUI |
| 5 | Verificação + docs |

---

## Fase 0 — Baseline

1. **Pré-check de esquema** (lição do detour do plano anterior): confirmar `stats.is_stale_scheme(...) ==
   False` antes de qualquer medição — um baseline medido contra índice em esquema antigo é exatamente o
   artefato que contaminou a primeira calibração do limiar.
2. Suíte `unit` verde. Roteiro manual de 3 conversas de teste com follow-ups reais ("e o que mais?",
   "explica melhor o segundo ponto") contra o corpus atual — o antes/depois da Fase 2 se mede com elas.
3. **Sensibilidade do limiar a perguntas condensadas**: o 0.72 foi calibrado com perguntas *cruas* e o gap
   entre coberto/fora é estreito (~0.024 — cobertas 0.7356+, fora até 0.7115). Medir algumas reescritas
   plausíveis de follow-up contra o limiar; se a distribuição de frases geradas por LLM cair
   sistematicamente mais baixa, registrar — a mitigação estrutural é o max-sobre-o-pool da Fase 3.2.

---

## Fase 1 — Condensação de query (core)

1. **Função nova em `core/rag/`** (módulo próprio, ex.: `condense.py` — `chat.py` está saudável, não
   inchar): recebe a pergunta corrente + os últimos 1–2 turnos `(pergunta, resposta)` e devolve a pergunta
   reescrita como standalone, via LLM local (`make_llm`, temperatura baixa). Padrão de prompt estrito em
   PT + parsing defensivo, análogo ao `nl2sql`/`nl2cli` (sem retry — aqui a falha tem fallback natural).
   **Sinergia com o header contextual** (`{stem} — {kind}` já nos vetores desde o plano anterior): o
   prompt deve instruir a resolução de referências anafóricas para o nome real do documento quando ele
   estiver disponível no histórico ("esse vídeo" → o stem citado nas fontes do turno anterior) — é onde
   o ganho dos dois planos se multiplica. As fontes de cada turno já estão no payload; incluí-las no
   contexto da condensação é barato.
2. **Contratos**: primeira pergunta da sessão (histórico vazio) → **não chama o LLM**, devolve a pergunta
   crua (zero custo no caso comum); qualquer falha/exceção da condensação → fallback para a pergunta crua
   com log warning — a Conversa **nunca** deixa de responder por causa da condensação.
3. A pergunta condensada alimenta **o retrieval e o prompt do answer** (uma reescrita, dois usos).
   Incluir o último turno também no prompt do `answer` é opcional — decidir na implementação medindo o
   orçamento (`num_ctx=8192` com k chunks de 1200 chars; não estourar).
4. **Timing (decisão registrada)**: a condensação adiciona 1 chamada de LLM + 1 `embed_query` por
   pergunta, cada qual gravando em `model_timings.json`. O formato atual (cap com descarte do mais
   antigo) foi **confirmado como adequado pelo Marcel** — nenhuma mudança no `model_timing`; o item 4.1
   do `PLANO_CORRECOES_RAG_ML_2` encerra-se como "aceito".

---

## Fase 2 — Histórico no worker + GUI da condensação

1. **`gui/modules/ai/worker.py::run_ai_answer`** ganha `history` (lista pura de pares `(q, a)` — o worker
   continua Flet-free). Quem mantém e recorta o histórico (últimos 2 turnos bastam) é a view/estado da
   Conversa; **"Nova conversa"** (`_clear_conversation`) zera — é a fronteira de sessão, já existe.
2. **Três representações visíveis** (componentes existentes, nada novo no design system):
   a. estágio no ticker — "condensando pergunta…" — antes do retrieve (regra de ouro do spinner: a
      latência extra tem que ser visível);
   b. linha no log de pipeline (`pipeline_log.fmt_query_condensed`, padrão dos `fmt_*`);
   c. legenda discreta no card do turno — "buscou por: *…*" — **só quando** a reescrita difere da
      pergunta original (transparência; o usuário percebe na hora quando a condensação errou).
3. **Eventos**: payload do `answer_start`/turno ganha o campo da query condensada — registrar a mudança
   na tabela de payloads do `events.md` (skill `design-system`) na Fase 5.

---

## Fase 3 — Pool + MMR no retrieve (`core/rag/retriever.py`)

1. `retrieve()` passa a ranquear um **pool** maior pela fusão RRF (default ~4×k, ex.: 24) e diversificar
   para `k` com MMR sobre os vetores dos chunks (λ≈0.7 — mais conservador que o 0.6 de documentos, porque
   aqui relevância importa mais que variedade), reusando `recommend._mmr`. Com overlap de 150 chars,
   chunks vizinhos do mesmo documento são quase-duplicatas — hoje comem 2–3 dos 6 slots do contexto.
2. **Contratos preservados + `low_confidence` sobre o pool** (testar, não assumir): `.score` continua o
   cosseno denso; a ordem devolvida é a do MMR. `low_confidence` passa a derivar do **max denso sobre o
   pool** (~24 candidatos), não só sobre os k finais — com o limiar 0.72 num gap de ~0.024, o max sobre
   um pool maior é mais estável e é a mitigação estrutural para a sensibilidade da Fase 0.3 (decidir na
   implementação como expor: o retriever devolve o max do pool no resultado, ou o worker consulta o pool
   antes do corte). Escopo de documento único (`scope=path`) tende a ter só chunks irmãos: verificar que
   o MMR não degrada esse caso (se degradar, diversificar só quando o escopo é corpus/kind).
3. Comportamento com store pequeno (pool ≥ nº de chunks) → idêntico ao atual; teste de regressão.

---

## Fase 4 — `k` exposto na GUI

Controle discreto no formulário da Conversa (`gui/modules/ai/form_view.py`) — `segmented_selector`
(4 · 6 · 8 · 12), persistido em `last_ai_k` via `gui/settings` (mesmo padrão de `last_ai_scope`),
desabilitado no modo Comandos CLI junto com os demais controles RAG-only. O CLI já tem `--k`; nenhuma
mudança lá.

---

## Fase 5 — Verificação + docs

1. Suíte `unit` verde; `ruff` limpo; cobertura de `core/rag/` sem regressão (baseline 99%); roteiro manual
   da Fase 0 revisitado (follow-ups agora recuperam o assunto certo).
2. Re-auditar o checklist de salvaguardas do topo.
3. **Skill `ml-rag`** (obrigatório): `chat`/`condense` documentados (contratos: primeira pergunta sem LLM;
   fallback nunca bloqueia); `retriever` documentado com pool+MMR (e o `.score` intacto); a regra de
   fronteira do `low_confidence` muda pela 2ª vez (era `hits[0]` → virou max sobre hits na 2ª rodada →
   vira **max sobre o pool** aqui) — atualizar a frase exata na skill; nota do timing aceito.
4. **Skill `design-system` / `events.md`** (obrigatório): estágio novo do ticker + campos novos de payload
   da Conversa.
5. **CLAUDE.md**: §hubs — a descrição do hub de IA ("Corpus é a Conversa…") deve continuar válida;
   validar e ajustar se a frase citar comportamento single-turn.
6. Entrada no `HISTORY.md` (decisões: condensação com fallback-nunca-bloqueia; pool+MMR com λ próprio;
   histórico em memória da view — sem persistência de sessões, registrada como fora de escopo). Plano →
   `docs/plans/implemented/`.

---

## Não-achados dignos de nota (não "consertar")

- **Persistência de sessões de chat** (`chat_history.json`) fica **fora de escopo** deliberadamente — o
  histórico vive em memória e morre com "Nova conversa"/fechar o app. Se um dia houver demanda, é plano
  próprio (a avaliação já registrou a ideia).
- `run_ai_command` (Comandos CLI) não ganha histórico — o modo é stateless por natureza (decisão da 2ª
  rodada sobre o `cancel_event` dele segue valendo).
- O `RAG_PROMPT` estrito (responder só do contexto, citar `[n]`) não muda — a condensação acontece antes,
  não relaxa o grounding.
- `batch.run_batch` não é tocado — instrução única por documento não tem turno.
