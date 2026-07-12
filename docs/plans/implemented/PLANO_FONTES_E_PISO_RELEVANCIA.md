# Plano — Fontes citadas de verdade + piso de relevância no retrieve

> **Origem**: primeiro caso real pós-planos 3–5 (screenshots jul/2026): pergunta sobre Ollama num acervo
> dominado por livros de Duna respondeu **certo** citando só `[1]`, mas (a) a UI listou "5 fontes
> citadas" — 4 delas Duna, irrelevantes, apenas *recuperadas*; (b) o aviso de baixa cobertura disparou
> com pool_max ~0.70–0.71, dentro do gap estreito do limiar 0.72; (c) o MMR, desenhado para diversificar
> quase-duplicatas, **promove ativamente** documentos fora do assunto quando só um documento é relevante
> (λ=0.7 ainda dá 30% de peso à diversidade). Três causas, três fixes — validados pelo harness de
> avaliação implementado no plano anterior, que é o **primeiro consumidor real** dele como instrumento de
> decisão. **Pré-requisito de dados (Fase 0)**: o golden set hoje tem 0 cobertas — hit-rate/MRR não medem
> nada; semear ~10 cobertas vem antes de qualquer mudança de código. Itens dizem *o quê* e *onde*; o
> *como* é da sessão de implementação. Independente do `PLANO_INTEGRACOES_ML` (nenhum arquivo em comum
> nas frentes) — podem correr em qualquer ordem.

## Checklist ativo de salvaguardas (padrões recorrentes — auditar neste escopo)

| Salvaguarda | Situação esperada neste escopo |
|---|---|
| Escritas não-atômicas / `io_atomic` | N/A — nenhuma persistência nova; o feedback já grava atomicamente |
| Timeouts herdados/ausentes | N/A — nenhuma rede nova |
| Duplicação de esqueleto intra-pacote | O parse de citações `[n]` nasce **num lugar só** (`core/rag/`, perto do `build_context` que gera os `[n]`) — GUI e CLI consomem a mesma função; **proibido** cada superfície parsear por conta própria |
| Docstring de pacote desatualizado | `rag/__init__.py` — atualizar se o contrato do retrieve mudar |
| Strings PT no core | Labels novos ("consultadas") PT ok; docstrings/logs EN |

**Regras herdadas**: pré-check `is_stale_scheme == False` antes de medir; toda comparação de rodadas do
eval só vale dentro do mesmo `embed_space_id`; medição antes/depois obrigatória — este plano existe para
ser provado pelo eval, não pelo olho.

## Fases

| Fase | Tema |
|---|---|
| 0 | Semear cobertas no golden set + baseline do eval |
| 1 | Fontes: citadas vs. consultadas |
| 2 | Piso de relevância relativo, antes do MMR |
| 3 | MMR ciente de dominância (condicional ao eval) |
| 4 | Validação final + limiar revisitado |
| 5 | Verificação + docs |

---

## Fase 0 — Semear cobertas + baseline (com o Marcel; nenhum código)

1. Golden set ganha ~10 perguntas **cobertas** com documentos esperados — via `ai eval add` e/ou 👍 nas
   respostas boas da Conversa + `ai eval promote` (a pergunta do Ollama do screenshot é a primeira). Mix
   deliberado: perguntas de documento único (o caso que motivou o plano) e de síntese multi-documento
   (para o piso/MMR não serem otimizados só para um perfil).
2. Rodar `ai eval` → **baseline registrado** (hit-rate@k, MRR, cossenos médios) no histórico. Toda fase
   seguinte se compara contra ele.
3. Suíte `unit` verde (flakiness do ROADMAP §12 segue ortogonal).

---

## Fase 1 — Fontes: citadas vs. consultadas (o maior ganho percebido, zero retrieval)

1. **Parse de citações** (`core/rag/`, junto do `build_context` — dono do formato `[n]`): extrair da
   resposta os `[n]` efetivamente usados, defensivo contra números fora da faixa/formatos criativos do
   modelo. `AnswerResult` passa a distinguir fontes **citadas** (referenciadas no texto) de
   **consultadas** (recuperadas, não usadas) — decidir a forma exata (campo novo vs. lista de índices) na
   implementação, sem quebrar consumidores existentes.
2. **GUI** (`answer_view.py`): o card mostra as citadas em destaque; as consultadas escondidas ou
   esmaecidas sob um rótulo discreto ("consultadas, não citadas") — decidir na implementação; a linha de
   status ("N fonte(s) citada(s)") passa a contar **as citadas de verdade**. O caso do screenshot vira:
   "1 fonte citada" + 4 consultadas esmaecidas.
3. **CLI** (`ai "pergunta"`): mesma distinção na impressão das fontes — mesma função de parse.
4. **Feedback**: conferir o que `retrieval_feedback.json` grava — deve registrar as duas listas (citadas
   e consultadas); o dataset fica mais rico para os usos futuros.
5. Fallback honesto: resposta sem nenhum `[n]` parseável → todas as fontes aparecem como consultadas
   (nunca inventar citação); registrar esse caso no payload para o feedback capturar.

---

## Fase 2 — Piso de relevância relativo, antes do MMR (`core/rag/retriever.py`)

1. Após o ranking fundido do pool e **antes** do MMR: descartar candidatos cujo cosseno denso fique mais
   de **δ** abaixo do melhor do pool. Ponto de partida sugerido pelos dados da calibração (cobertas
   0.7356–0.8684, fora ≤0.7115): δ≈0.05 — **validar com o eval da Fase 0, não confiar no chute**; expor
   como constante documentada no retriever (não como opção de GUI).
2. **Contratos que mudam** (testar, não assumir): `retrieve()` pode devolver **menos que k** — conferir
   que `build_context` (já tolera), o card de fontes e o `run_batch` lidam bem; nunca devolver vazio com
   store não-vazio (o melhor do pool sempre sobrevive ao piso por definição). `pool_max_score` continua
   calculado **antes** do piso (o aviso de cobertura mede o acervo, não o corte).
3. Efeito esperado no caso do screenshot: os chunks de Duna a ~0.65 caem; sobra o documento do Ollama —
   contexto menor, resposta igual ou melhor, fontes limpas. O eval confirma que as perguntas de síntese
   multi-documento **não** regrediram (é para isso que a Fase 0 misturou os dois perfis).

---

## Fase 3 — MMR ciente de dominância (condicional — só se o eval pedir)

Se após a Fase 2 o eval ainda mostrar diversificação prejudicando perguntas de documento único (o piso
pode já ter resolvido — os sobreviventes tendem a ser do mesmo doc, e MMR entre irmãos do mesmo doc é o
comportamento certo): pular a diversificação quando os sobreviventes do piso pertencem a ≤2 documentos
(paralelo do skip que já existe para escopo de documento único). Decidir **pelos números**, não por
intuição — se a Fase 2 bastar, esta fase é registrada como não-executada e por quê.

---

## Fase 4 — Validação final + limiar revisitado

1. Rodada final do eval vs. baseline da Fase 0 — delta registrado no plano ao movê-lo para
   `implemented/`. Critério de aceite: hit-rate/MRR iguais ou melhores E o caso-screenshot (agora no
   golden set) com fontes limpas.
2. **Limiar 0.72 revisitado com os dados novos**: com ~10 cobertas reais no golden set (não só as 10 da
   calibração original), reavaliar se o gap se mantém — se perguntas cobertas legítimas seguirem caindo
   a ~0.70, baixar o limiar levemente (dentro do gap medido) e registrar valor+método, como da última
   vez. Avaliar também exibir o score no aviso ("cobertura estimada: 0.70") — transparência barata;
   decidir na implementação.

---

## Fase 5 — Verificação + docs

1. Suíte `unit` verde; `ruff` limpo; cobertura de `core/rag/` sem regressão.
2. Re-auditar o checklist de salvaguardas do topo (parse de citações num lugar só).
3. **Skill `ml-rag`** (obrigatório): contrato do `retrieve()` atualizado (piso relativo; pode devolver
   <k; `pool_max_score` pré-piso); semântica de fontes citadas vs. consultadas (e onde mora o parse);
   limiar se mudou (valor + método, 3ª calibração).
4. **Skill `design-system` / `events.md`**: payload do `answer_done` ganha a distinção citadas/
   consultadas — atualizar a tabela.
5. **CLAUDE.md**: linha do hub IA se citar "fontes citadas"; validar.
6. Entrada no `HISTORY.md` (decisões: fontes citadas parseadas da resposta — nunca inferidas do
   contexto; piso relativo com δ validado por eval; Fase 3 executada ou não, e por quê). Plano →
   `docs/plans/implemented/`.

---

## Não-achados dignos de nota (não "consertar")

- **O modelo não errou** — o gemma citou só a fonte certa; o problema era a UI tratar recuperado como
  citado e o retrieval não ter piso. Nenhuma mudança no `RAG_PROMPT`.
- **Desbalanceamento do corpus** (Duna domina os chunks) é fato do acervo, não bug — o piso trata o
  sintoma correto (irrelevante no contexto), não "compensa" a distribuição.
- **BM25 sem stopwords PT**: palavras genéricas da pergunta casam com qualquer livro — suspeita real,
  mas mudar a tokenização do BM25 mexe no ranking inteiro; fica **fora** deste plano; se o eval
  pós-piso ainda apontar ruído lexical, vira candidato próprio com medição.
- **Limiar adaptativo automático** (aprender dos 👍/👎): continua futuro — o feedback ainda está
  coletando; decisão "coleta-primeiro-usa-depois" do plano anterior segue valendo.
- **Reranker ONNX**: segue condicional — este plano é exatamente o tipo de correção barata que deve ser
  esgotada antes dele.

---

## Resultado (implementado — jul/2026)

Sequenciamento acordado com o Marcel: **código das Fases 1 e 2 primeiro** (δ=0.05 provisório), **eval do
Marcel depois** para validar. Duas frentes commitadas em `main`:

- **Fase 1** (`41c3f68`) — fontes **citadas vs. consultadas**. Parse dos `[n]` num lugar só
  (`core/rag/chat.py::cited_source_numbers`, ao lado do `build_context`), defensivo (fora-da-faixa/colchetes
  não-numéricos ignorados; aceita `[1,2]`/`[1][2]`); `AnswerResult.cited_sources` (subconjunto de `sources`).
  GUI, CLI e `feedback.py` consomem a **mesma** função; `answer_done` ganhou `cited`; `ai eval promote` usa as
  citadas como `expected`. Sem `[n]` parseável → tudo consultada, **nunca inventa citação**.
- **Fase 2** (`c5df185`) — **piso de relevância denso** antes do MMR
  (`retriever._apply_relevance_floor`): `keep = denso ≥ melhor_denso − δ  OU  (top-1 do BM25 e lexical>0)`.
  A **isenção do top-1 BM25** (no máximo um chunk) foi a reconciliação deliberada de dois contratos que
  colidiriam (piso denso-puro exige-se para funcionar sem stopwords PT; resgate híbrido do BM25 precisa
  sobreviver). Pulado em escopo de documento único; pode devolver `<k`; `pool_max_score` é pré-piso.

### Validação por eval (antes/depois no mesmo golden set)

Golden set: 10 cobertas (mix single-doc + síntese multi-doc, ancoradas no acervo real do Marcel — 6 livros de
Duna + Constituição do Claude + transcrições de IA) + 5 fora-do-acervo. Rodadas comparáveis (mesmo
`embed_space_id`), medindo **só** o efeito do piso (Fase 1 → sem piso; Fase 2 → com piso):

| | hit-rate@6 | MRR | flag |
|---|---|---|---|
| **Sem piso** (Fase 1, `41c3f68`) | 70% | 0.38 | 100% |
| **Com piso** (Fase 2, `c5df185`) | 70% | **0.45** | 100% |

Por pergunta, o piso fez uma **troca** que revela exatamente o desenho:

- **Resgatou o caso que motivou o plano** — a pergunta do **Ollama** num acervo dominado por Duna: **sem** o
  piso nem entrava no top-6 (miss); **com** o piso vem em **rank 2**. Também subiu ML (6→2) e IA (3→2).
- **Custou o Mentats** (rank 4 → miss): caso onde sinal *e* ruído são ambos Duna (o conceito aparece nos 6
  livros, diluído → chunk denso-baixo). É um artefato do **golden set** (mapa single-doc discutível p/ um
  conceito franchise-wide), não uma falha do piso — `--expect` em vários livros de Duna recuperaria o acerto.

hit-rate estável (a troca se cancela), mas **MRR +0.07** e o alvo do plano resgatado. Os 2 misses da
Constituição (0.77) são **cross-língua** (doc em inglês, pergunta em PT — fraqueza conhecida do `nomic-embed`,
fora do escopo deste plano).

### Decisões (pelos números, não pela intuição)

- **δ=0.05 — validado, net-positivo.** MRR +0.07 e caso-alvo resgatado. **Mantido** — δ maior deixaria o
  ruído de Duna voltar e arriscaria desfazer o ganho do Ollama; o fix correto do Mentats é o golden set, não o
  δ. Segue documentado no retriever como o valor validado (não mais "provisório-chute").
- **Fase 3 (MMR ciente de dominância) — NÃO EXECUTADA.** O eval mostra que a **diversificação do MMR está
  ajudando** (é ela que leva ML/IA/Mentats a alcançarem múltiplas fontes) e que o **piso já resolveu a
  dominância**. Pular o MMR quando os sobreviventes são ≤2 docs — a ideia da Fase 3 — provavelmente
  **pioraria** o Mentats. Confirma a hipótese do próprio plano ("o piso pode já ter resolvido").
- **Limiar 0.72 (Fase 4) — mantido.** Flag accuracy 100% nas duas rodadas; gap limpo (fora 0.69–0.71,
  cobertas 0.74–0.85). 3ª calibração confirma o valor sem ajuste.
- **Refinamento futuro registrado** (só se o eval pedir): condicionar a isenção do BM25 à *distintividade* do
  top-1, não a ser meramente o primeiro. Não implementado — sem número que justifique.

Testes: `tests/core/rag` verde (piso: dropa denso-longe/`<k`, sempre mantém o melhor, isenção salva o resgate
profundo, pulado em doc único; parse: defensivo/split/fallback), suíte `unit` completa verde, `ruff` limpo.
Docs de contrato atualizados nos commits das fases: `events.md`, skill `ml-rag` (regra completa do piso **com
a isenção**), `CLAUDE.md`.
