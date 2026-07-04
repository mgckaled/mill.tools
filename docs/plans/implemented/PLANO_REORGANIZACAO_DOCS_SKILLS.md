# Plano — Reorganização da documentação técnica e das skills

> **✅ Implementado (jul/2026).** Registro histórico. Os caminhos na **tabela de movimentação** (Fase 1.2)
> mostram a **origem** (pré-reorganização, hoje inexistentes) — são células de tabela documentando a
> migração, não links vivos. Entrada no changelog: [`docs/HISTORY.md`](../../HISTORY.md).

> **Escopo**: apenas documentação (`CLAUDE.md`, `.claude/skills/`, `docs/`, `.claude/plans/`).
> **Nenhuma linha de código em `src/` ou `tests/` é tocada.** Portanto não há risco de quebrar a suíte —
> o critério de verificação é integridade de referências, não `pytest`.
>
> **Motivação** (relatório da sessão de análise, jul/2026): o conjunto viola o princípio da própria skill
> `architecture` ("sempre que um detalhe pertencer a uma skill, delegue — não duplique"). Três sintomas:
> duplicação CLAUDE.md ↔ skills (quirks do Flet, eventos, regra do spinner em 2–3 lugares), narrativa
> histórica em contexto sempre-carregado (planos ✅ narrados no CLAUDE.md e na seção 9 da architecture),
> e snapshots manuais que envelhecem (tabela de cobertura da skill testing, tabelas de flags da skill cli).
>
> **Números de partida**: `CLAUDE.md` 347 linhas (linhas densíssimas — o maior em tokens) ·
> `architecture` 264 · `cli` 514 · `design-system` 259 · `testing` 921 (anomalia).

---

## Sequência de fases (visão geral)

| Fase | Entrega | Depende de |
|---|---|---|
| 0 | Inventário + branch + baseline de referências | — |
| 1 | Rearranjo dos arquivos de planos (árvore única em `docs/`) | 0 |
| 2 | `docs/HISTORY.md` + convenção "fonte única + ponteiro" | 1 |
| 3 | Skill `testing` dividida (SKILL.md + 3 arquivos de referência) | 2 |
| 4 | Skill `cli` enxugada (padrões ficam, tabelas de flags saem) | 3 |
| 5 | Skill `design-system` dividida (tokens/quirks vs. `events.md`) | 2 |
| 6 | Skill `architecture` sem histórico (seção 9 → HISTORY) | 2 |
| 7 | Nova skill `ml-rag` | 2, 6 |
| 8 | `CLAUDE.md` emagrecido (vira índice + contratos) | 3–7 |
| 9 | Verificação final de integridade | tudo |
| 10 | (Opcional) Automação anti-drift via `poe` | 9 |

Racional da ordem: **mover arquivos primeiro** (Fase 1) para que todas as edições posteriores já apontem
para caminhos definitivos; **criar os destinos** (Fase 2) antes de cortar conteúdo, para que nada seja
apagado sem ter para onde ir; skills em ordem de risco crescente; **CLAUDE.md por último**, porque ele é o
índice que aponta para tudo que as fases anteriores estabilizam.

---

## Fase 0 — Preparação e inventário

**Objetivo**: congelar o estado atual e mapear tudo que referencia os arquivos que vão se mover.

1. Criar branch dedicada: `git checkout -b docs/reorganizacao-skills`.
2. Gerar o inventário de referências cruzadas (guardar a saída como baseline):
   ```bash
   grep -rn --include="*.md" -o "docs/[A-Za-z0-9_/.-]*\.md" CLAUDE.md .claude/skills/ docs/ | sort -u
   grep -rn --include="*.py" "docs/" src/ tests/   # docstrings/comentários que citem docs
   ```
3. Registrar as referências **já quebradas hoje** (confirmadas na análise):
   - `CLAUDE.md` → `docs/STATUS_TIER0.md` (o arquivo está em `.claude/plans/implemented/`).
   - `.claude/skills/architecture/SKILL.md` → `docs/REFATORACAO_PREVIA.md` (idem).
4. Medir baseline de tamanho: `wc -l CLAUDE.md .claude/skills/*/SKILL.md` (comparar na Fase 9).

**Critério de aceite**: baseline salva (pode ser um `docs/new/BASELINE_REORGANIZACAO.txt` temporário).

---

## Fase 1 — Rearranjo dos arquivos de planos

**Objetivo**: uma única árvore de planos sob `docs/`, com estados explícitos (ativo / implementado /
arquivo morto), eliminando os três locais atuais (`docs/` raiz, `docs/plan/`, `.claude/plans/`).

### 1.1 Estrutura-alvo

```
docs/
├── README.md                      # NOVO — mapa da pasta + convenção de estados
├── HISTORY.md                     # NOVO (Fase 2) — changelog de decisões
├── ROADMAP.md                     # ROADMAP_ML_DADOS.md renomeado (roadmap vivo único)
├── reference/                     # documentação de referência (não é plano)
│   ├── MODELOS_IA.md
│   ├── PANDAS_POLARS_DADOS.md
│   └── RELATORIO_CENARIO_TORCH.md
└── plans/
    ├── active/                    # planos ainda não implementados (nasce com este arquivo dentro)
    ├── implemented/               # planos concluídos da era atual (mill.tools multiferramenta)
    └── archive/                   # era pré-mill.tools / material de gênese (ex-.claude/plans/implemented)
        └── refactor/
```

Regra de ciclo de vida (documentar no `docs/README.md`): plano nasce em `plans/active/`, ao concluir
**move** para `plans/implemented/` (com uma linha registrada no `HISTORY.md`). `archive/` é só leitura
histórica — nunca referenciado por CLAUDE.md/skills.

### 1.2 Tabela de movimentação

| De | Para | Nota |
|---|---|---|
| `docs/PLANO_0_FUNDACAO_DADOS.md` | `docs/plans/implemented/` | ✅ concluído |
| `docs/PLANO_1_GRAFICOS.md` | `docs/plans/implemented/` | ✅ |
| `docs/PLANO_2_PAINEIS_HUBS.md` | `docs/plans/implemented/` | ✅ |
| `docs/PLANO_3_FUNDACAO_ML.md` | `docs/plans/implemented/` | ✅ |
| `docs/PLANO_4A_SEMANTICO.md` | `docs/plans/implemented/` | ✅ |
| `docs/PLANO_4B_SUPERVISIONADO_TEXTUAL.md` | `docs/plans/implemented/` | ✅ |
| `docs/PLANO_AUDIO_TIER1.md` | `docs/plans/implemented/` | ✅ |
| `docs/PLANO_AUDIO_TIER2.md` | `docs/plans/implemented/` | ✅ |
| `docs/PLANO_AUDIO_TIER3_RESUMO.md` | `docs/plans/active/` | é backlog de itens avançados, não relatório de concluído |
| `docs/PLANO_HOME_HOVER_EXPAND.md` | `docs/plans/implemented/` | ✅ |
| `docs/plan/PLANO_ML_NOVAS_FEATURES.md` | `docs/plans/implemented/` | ✅ (Tier A + fast-follows) |
| `docs/plan/PLANO_REFINAMENTO_ML_TEXTO_RAG.md` | `docs/plans/implemented/` | ✅ |
| `docs/plan/PLANO_TIMING_MODELOS.md` | `docs/plans/implemented/` | ✅ |
| `docs/ROADMAP_ML_DADOS.md` | `docs/ROADMAP.md` | renomear — vira o roadmap vivo único |
| `docs/MODELOS_IA.md` | `docs/reference/` | referência, não plano |
| `docs/PANDAS_POLARS_DADOS.md` | `docs/reference/` | idem |
| `docs/RELATORIO_CENARIO_TORCH.md` | `docs/reference/` | idem |
| `.claude/plans/implemented/*` (31 arquivos) | `docs/plans/archive/` | era antiga; inclui `refactor/` como subpasta |
| `.claude/plans/new/` (vazia) | **remover** | substituída por `docs/plans/active/` |
| `docs/plan/` (esvaziada) | **remover** | consolidada em `docs/plans/` |
| `docs/new/PLANO_REORGANIZACAO_DOCS_SKILLS.md` (este) | `docs/plans/active/` | mover no início da implementação; remover `docs/new/` ao final |

Correções oportunistas de nome durante o move (só em `archive/`, nada referencia esses arquivos):
`MILL_PR5_DOCUMENTS_PLAN.md.md` → `MILL_PR5_DOCUMENTS_PLAN.md`; `PR4_VIDEO_PLAN.MD` → `PR4_VIDEO_PLAN.md`.

Caso especial: `.claude/plans/implemented/STATUS_TIER0.md` e `REFATORACAO_PREVIA.md`/`PLANO_REFATORACAO_PREVIA.md`
são citados por CLAUDE.md/architecture como se estivessem em `docs/`. Movê-los para `docs/plans/archive/`
**e** atualizar as citações (passo 1.3) — isso conserta as duas referências quebradas de uma vez.

> Usar `git mv` em todos os moves para preservar histórico.

### 1.3 Atualização de referências

Após os moves, varrer e corrigir **todas** as citações (a baseline da Fase 0 é o checklist):

- `CLAUDE.md`: todas as ocorrências de `docs/PLANO_*`, `docs/plan/PLANO_*`, `docs/ROADMAP_ML_DADOS.md`,
  `docs/ROADMAP_*.md`, `docs/STATUS_TIER0.md`.
- `.claude/skills/architecture/SKILL.md`: frontmatter (`docs/ROADMAP_ML_DADOS.md`, `docs/REFATORACAO_PREVIA.md`)
  e corpo (seção 9 — que a Fase 6 vai cortar de qualquer forma, mas manter íntegro até lá).
- `.claude/skills/cli/SKILL.md` e `testing/SKILL.md`: citações a `docs/plan/PLANO_ML_NOVAS_FEATURES.md`.
- Docstrings/comentários em `src/` que citem `docs/` (se o grep da Fase 0 achar algum — corrigir só a string).

**Critério de aceite**: o grep da Fase 0 reexecutado não retorna nenhum caminho inexistente; `docs/` raiz
contém apenas `README.md`, `HISTORY.md`, `ROADMAP.md`, `reference/`, `plans/` (e `new/` até o fim do plano).

---

## Fase 2 — `docs/HISTORY.md` + convenção "fonte única + ponteiro"

**Objetivo**: criar os dois destinos que as fases de corte (3–8) vão usar. Nada é deletado antes disto existir.

### 2.1 `docs/HISTORY.md`

Changelog de decisões e entregas, ordem cronológica inversa, **uma entrada curta por marco** com link para o
plano correspondente em `docs/plans/implemented|archive/`. Popular na criação com o material que hoje infla
outros arquivos:

- A lista de itens ✅ da seção **Roadmap** do `CLAUDE.md` (PR5→Tier A + fast-follows) — 1–3 linhas por item.
- A narrativa da **seção 9** da skill `architecture` (Planos −1 a 4B, Tier A, fast-follows 1 e 2) — condensada;
  o detalhe completo continua nos arquivos de plano, que o HISTORY linka.
- Decisões arquiteturais com justificativa que hoje se repetem em 2 lugares (ex.: `rank-bm25` vs. `bm25s`,
  dHash vs. `imagehash`, "sem PyTorch", "sem NVENC", por que Observatório virou hub) — cada uma vira uma
  entrada "Decisão: …" única, citável por link.

### 2.2 Convenção "fonte única + ponteiro"

Criar `docs/README.md` com o mapa da pasta **e** a tabela de donos por assunto (esta tabela será replicada
de forma resumida no topo do CLAUDE.md na Fase 8):

| Assunto | Fonte única | Todos os demais |
|---|---|---|
| Quirks do Flet 0.85 | skill `design-system` | apontam |
| Contrato de eventos (`PipelineEvent`, payloads) | skill `design-system` (`events.md`) | apontam |
| Regra de ouro do spinner | skill `design-system` | apontam |
| Camadas, limites de tamanho, decomposição | skill `architecture` | apontam |
| Flags de CLI | `--help` do próprio código | skill `cli` só padrões/gotchas |
| Estrutura e mocks de teste | skill `testing` (+ referências) | apontam |
| RAG / ML / NLP / Observatório | skill `ml-rag` (Fase 7) | apontam |
| Histórico e justificativas de decisão | `docs/HISTORY.md` + planos | apontam |
| Roadmap pendente | `docs/ROADMAP.md` | apontam |
| Cobertura de testes | saída do `pytest --cov` | ninguém copia tabela |

**Critério de aceite**: `HISTORY.md` cobre todos os ✅ do CLAUDE.md atual; `README.md` publicado.

---

## Fase 3 — Skill `testing`: dividir e descartar (921 → ~250 linhas no SKILL.md)

**Objetivo**: transformar a anomalia em SKILL.md enxuto + arquivos de referência carregados sob demanda
(mecanismo padrão de skills: arquivos auxiliares na pasta da skill, citados pelo SKILL.md).

### 3.1 Estrutura-alvo

```
.claude/skills/testing/
├── SKILL.md              # ~250 linhas — o "sempre necessário"
├── mocks-media.md        # subprocess/Popen · WhisperModel · urlopen · pytesseract · pymupdf/qrcode
├── mocks-llm-rag-ml.md   # GenericFakeChatModel · core RAG (store/retriever/indexer/bm25) · core ML (3/4A/4B) · core Dados/assess/datacard
└── mocks-gui-cli.md      # bus falso dos workers · padrões de teste de CLI (o _parse(*argv) e os blocos hoje na skill cli)
```

### 3.2 O que fica no SKILL.md

- Regras de estrutura (espelhar `src/`, `__init__.py` vazio, imports absolutos) — **sem** a árvore de arquivos.
- Marcadores (`unit`/`integration`), hook de skip do ffmpeg, plugins pytest.
- Fixtures globais (as duas tabelas function/session-scoped — são estáveis e curtas).
- Templates de teste unit/integration.
- Gotchas de expected values (`sanitize_filename`, `crop_image` ratio, `_save` modo L, bitrate sem "k", autotrim PNG).
- Metas de cobertura (≥90% por módulo, agregado ~88%) + lacunas justificadas (downloaders yt-dlp,
  `[ai-image]`) + a regra do `# pragma: no cover`. **Sem a tabela por módulo.**
- Nota do pymupdf real (unit sem mock) — é regra de projeto, não receita.
- Índice dos três arquivos de referência com uma linha dizendo quando abrir cada um.

### 3.3 O que sai (com destino)

| Conteúdo (linhas aprox. hoje) | Destino |
|---|---|
| Árvore de `tests/` com descrição por arquivo (~100) | **descartado** — derivável do repo (`ls`/Glob). A árvore inclusive tem defeito de manutenção manual: o bloco `image/` aparece duas vezes |
| Tabela de cobertura por módulo (~65) | **descartado** — snapshot manual; `pytest --cov` gera sob demanda (Fase 10 pode automatizar) |
| Receitas de mock de mídia (~180) | `mocks-media.md` |
| Receitas LLM/RAG/ML/Dados (~250) | `mocks-llm-rag-ml.md` |
| Worker GUI + observações de CLI (~90) | `mocks-gui-cli.md` |
| Achados narrativos ("achado real ao escrever os testes" do RRF/lexsort) | manter — mas como nota curta no arquivo de referência pertinente; se houver justificativa longa, vai para `HISTORY.md` com link |

### 3.4 Frontmatter

Reescrever a `description` mencionando os arquivos de referência (para o roteamento continuar disparando
nos mesmos gatilhos: mockar subprocess/Whisper/LangChain/pymupdf etc.).

**Critério de aceite**: SKILL.md ≤ ~300 linhas; nenhum conteúdo técnico perdido (diff conferido); os 3
arquivos de referência citados explicitamente no SKILL.md.

---

## Fase 4 — Skill `cli`: enxugar (514 → ~220 linhas)

**Objetivo**: manter padrões e gotchas (o que não se descobre pelo `--help`), remover o que duplica
`--help`/código, mover receitas de teste para a skill `testing`.

**Fica**: visão geral do dispatcher; estrutura de `src/cli/`; `CLIEventBus` e o padrão
`install_log_handler=False`; `resolve_input` e o ramo `.txt`/`.md`; a taxonomia dos 3 tipos de subcomando
(pipeline+bus: audio/video/image/document/recipe · read-only sem bus: library/ai/data/observatory);
gotchas por subcomando em formato compacto (kebab→snake, UTF-8 no stdout, `--sql` pula IA, `log_activity`
a mockar, multi-input do `data query`); "como adicionar um novo subcomando"; padrões de argparse.

**Sai (com destino)**:

| Conteúdo | Destino |
|---|---|
| Tabelas completas de flags de `audio`/`audio-viz`/`video`/`image`/`document`/`library`/`ai`/`recipe`/`data`/`observatory` (~200 linhas) | **descartado** — duplicam `--help` e a seção Comandos do CLAUDE.md; alto drift. Manter só flags de comportamento não-óbvio (ex.: `--profile` com import lazy, `--scope` path-ou-kind) |
| Blocos "Nos testes…" espalhados por subcomando (~80 linhas) | `testing/mocks-gui-cli.md` (Fase 3) — a skill cli mantém 1 linha de ponteiro |
| Padrão `_parse(*argv)` + exemplo (duplicado literal na skill testing) | fica **só** em `testing/mocks-gui-cli.md` |

**Critério de aceite**: nenhum gotcha (kebab→snake, UTF-8, mocks de `log_activity`, ramos `sys.exit`)
perdido — todos rastreáveis no diff para a skill testing ou para o texto compacto restante.

---

## Fase 5 — Skill `design-system`: dividir tokens/quirks de eventos

**Objetivo**: separar o que é estável (tokens, componentes, quirks) do que muda a cada PR (payloads de
eventos por módulo), e tornar-se a **fonte única** de quirks/spinner.

```
.claude/skills/design-system/
├── SKILL.md      # imports · factories · Cursor · tokens (Color/Space/Radius/Type/Motion/Layout) · tema · help system · controles verificados/quirks
└── events.md     # PipelineEvent · tabelas de payload por módulo · barra de progresso · thread-safety · abas aninhadas · hook do Observatório
```

Passos:
1. Extrair para `events.md` toda a seção "Eventos do pipeline" em diante (payloads genéricos + por módulo,
   barra de progresso, thread safety), mais a nota de abas aninhadas.
2. Consolidar a **regra de ouro do spinner** em um único bloco (hoje aparece na linha da factory `spinner()`
   E na seção de eventos): manter a explicação completa uma vez, e na outra ocorrência deixar uma frase +
   âncora.
3. Incorporar ao SKILL.md qualquer quirk que hoje exista **só** no CLAUDE.md (diff das duas tabelas linha a
   linha — as redações divergem; adotar a mais completa de cada). A partir daqui a skill é a fonte única;
   o CLAUDE.md perde a tabela na Fase 8.
4. Atualizar a `description` do frontmatter mencionando `events.md` (gatilhos: "payload de evento",
   "PipelineEvent", "progress bar").
5. Adicionar em `events.md` uma nota de manutenção: "os campos exatos derivam de `worker.py`/`pipeline_log.py`
   de cada módulo — ao mudar um payload, atualizar aqui no mesmo PR" (o contrato anti-drift).

**Critério de aceite**: união das duas tabelas de quirks (CLAUDE.md + skill) presente no SKILL.md;
`events.md` autocontido; nenhuma menção duplicada da regra do spinner.

---

## Fase 6 — Skill `architecture`: cortar o histórico

**Objetivo**: skill 100% evergreen (264 → ~170 linhas).

1. **Seção 9 ("Ao implementar os planos do roadmap")**: mover a narrativa dos planos ✅ (−1, 0, 1, 2, 3,
   4A, 4B, Tier A e os dois fast-follows) para `docs/HISTORY.md` (Fase 2 já criou as entradas — conferir
   que nada da seção 9 ficou sem entrada correspondente e completar).
2. Substituir a seção 9 por uma seção curta "Planos pendentes" apontando `docs/ROADMAP.md` e
   `docs/plans/active/`, mantendo apenas a orientação operacional que ainda vale para o futuro
   ("Planos 4C–7: cada feature pela seção 5; ao tocar view grande, dividir ao tocar antes de adicionar").
3. Atualizar frontmatter: trocar `docs/ROADMAP_ML_DADOS.md`/`docs/REFATORACAO_PREVIA.md` pelos caminhos
   novos da Fase 1.
4. Seções 1–8 ficam intactas (são o núcleo de valor da skill).

**Critério de aceite**: nenhuma menção a plano concluído no corpo; toda linha removida rastreável no
HISTORY ou no plano arquivado.

---

## Fase 7 — Nova skill `ml-rag`

**Objetivo**: dar dono único ao assunto que mais cresceu e hoje está espalhado por 4 seções do CLAUDE.md
(IA, Observatório, trechos de Biblioteca/Dados), seção 9 da architecture e receitas da testing.

```
.claude/skills/ml-rag/
└── SKILL.md   # ~250–300 linhas
```

Conteúdo (consolidando o que hoje vive no CLAUDE.md — que na Fase 8 passa a só apontar):

- **Mapa dos pacotes**: `core/rag/` (embedder única rede · store `.npz` · busca híbrida BM25+denso via RRF ·
  indexer incremental por `(path, mtime)` · `card_fn` p/ dados · chat com citação `[n]` por documento) ·
  `core/ml/` (features mean-pool · dedup · cluster/labeling/project · recommend/MMR · classify por domínio ·
  store versionado) · `core/text/` (YAKE · TextRank · spaCy NER · glossário EntityRuler) · `core/observatory/`
  (activity/logs/status/model_timing/disk_usage).
- **Regras de fronteira**: embeddings sempre locais; nuvem só opt-in na resposta; `.score` = cosseno denso
  (contrato do aviso fora-de-escopo); IA de dados recebe só schema/cartão, nunca linhas.
- **Gates e extras**: `[ml]`/`[ml-viz]`/`[nlp]` + modelo spaCy à parte; o que é numpy-puro (sem gate).
- **Modelos Ollama**: tabela dos `*-custom`, `num_ctx`, quirk #10176, `LONG_CONTEXT_LOCAL_BUDGETS`.
- **Persistências em `~/.mill-tools/`**: quem grava o quê (rag/ · ml/ · caches JSON · logs do Observatório).
- **Superfícies**: CLI `ai`/`observatory` (ponteiro p/ skill cli), hubs IA/Observatório (ponteiro p/
  design-system), bridge `trigger_reindex`.
- Frontmatter com gatilhos: RAG, embeddings, índice, BM25, cluster, classify, Observatório, Ollama, YAKE, spaCy.

Ajustar as skills irmãs: `architecture` passa a listar `ml-rag` entre as delegações; `testing` aponta para
ela como contexto das receitas de `mocks-llm-rag-ml.md`.

**Critério de aceite**: todo fato de RAG/ML/Observatório do CLAUDE.md atual existe na skill (ou num plano
arquivado linkado); zero fatos novos inventados.

---

## Fase 8 — `CLAUDE.md`: de diário a índice

**Objetivo**: reduzir para ~150–180 linhas *magras* mantendo 100% da capacidade de orientar uma sessão nova.
É a fase de maior impacto em tokens (o arquivo carrega em toda sessão) e só pode rodar depois que as
fontes únicas existem (Fases 3–7).

Estrutura-alvo, seção a seção:

1. **Cabeçalho + o que é o projeto** — mantém (enxugar).
2. **Tabela "fonte única"** — NOVA, resumo da tabela do `docs/README.md` (Fase 2.2): assunto → documento dono.
3. **Stack** — comprimir para lista de dependências + 1 frase de propósito cada. Justificativas de escolha
   ("por que rank-bm25", "por que dHash", cenário torch) → `HISTORY.md`/`docs/reference/`. Manter os avisos
   operacionais curtos (sem PyTorch; encoding 100% CPU).
4. **Estrutura de pastas** — manter a árvore, mas podar as anotações parentéticas longas (o detalhe de cada
   pacote de ML/RAG agora mora na skill `ml-rag`).
5. **Sistema de módulos + seções por módulo** — cada módulo reduz para: propósito (2–4 linhas), contratos
   não-óbvios que uma sessão precisa saber antes de abrir o código (dirs de saída, bridges, quirks Windows
   específicos como PO Token/`.temp.<ext>`/burn-in `cwd`), e ponteiros. **Sai**: payloads de evento
   (→ design-system/events.md), narrativa de migração/decisão (→ HISTORY), detalhes internos de RAG/ML/
   Observatório (→ ml-rag). As seções IA/Observatório/Dados são as que mais encolhem.
6. **Cookies do YouTube** — manter (operacional, não duplicado) — só comprimir.
7. **Comandos** — manter o bloco (é o índice prático da CLI); referência de flags → `--help`/skill cli.
8. **Convenções de código / Testes / Dependências externas** — manter enxuto; detalhes → skills.
9. **Quirks do Flet** — **remover a tabela** (fonte única = design-system desde a Fase 5); deixar 1 linha:
   "Quirks do Flet 0.85 e controles verificados → skill `design-system`". Manter fora da tabela apenas os
   avisos de hardware/GPU (BSOD MX150), que não são design system.
10. **Ollama / LLM pipeline** — comprimir; detalhe → `ml-rag`.
11. **Roadmap** — só pendentes (PR9.2, PR3.1-B, 4C–7, futuro) + link para `HISTORY.md` e `docs/plans/`.

Método de execução sugerido (para a sessão do Claude Code): reescrever seção a seção **com o diff aberto**,
validando a cada corte que o destino (skill/HISTORY/plano) já contém o conteúdo. Nunca cortar sem destino.

**Critério de aceite**: CLAUDE.md sem nenhuma tabela/lista que exista em skill; toda seção com ponteiro
explícito; nenhuma referência quebrada; leitura de ponta a ponta suficiente para orientar uma sessão nova
sem abrir skill nenhuma (as skills são profundidade, não pré-requisito).

---

## Fase 9 — Verificação final

1. Reexecutar o grep da Fase 0 → zero caminhos inexistentes em CLAUDE.md, skills, docs e docstrings.
2. `wc -l` comparado com a baseline — alvos: CLAUDE.md ≤ ~180 · testing ≤ ~300 · cli ≤ ~250 ·
   architecture ≤ ~190 · design-system SKILL.md ≤ ~170 (+ `events.md`).
3. Revisão de conteúdo por amostragem: escolher 10 fatos técnicos críticos (ex.: regra do spinner, kebab→snake,
   PO Token, `_parse(*argv)`, mock do WhisperModel, gate `[nlp]`, RRF/lexsort, `num_ctx=8192`, dirs de saída,
   `install_log_handler=False`) e confirmar que cada um tem exatamente **um** dono e é encontrável a partir
   do CLAUDE.md em ≤ 2 saltos.
4. Teste prático: abrir uma sessão nova do Claude Code e pedir uma tarefa de cada domínio (um teste novo, um
   subcomando novo, um componente de GUI, uma pergunta de RAG) — verificar que as skills disparam e que nada
   essencial ficou órfão.
5. Mover este plano para `docs/plans/implemented/` e apagar `docs/new/` e o arquivo de baseline.
6. Commits pequenos por fase (já feitos ao longo); squash/merge da branch.

---

## Fase 10 (opcional) — Automação anti-drift

Só depois de tudo estável; cada item é independente:

1. **`poe cov-table`** — roda `pytest -m "not integration" --cov=src --cov-report=term-missing` e grava a
   saída em `docs/reference/COVERAGE.txt` (git-ignorado ou atualizado sob demanda) — substitui de vez a
   tentação de recolar a tabela numa skill.
2. **`poe cli-ref`** — script que itera os parsers (`add_*_parser`) e gera `docs/reference/CLI_REFERENCE.md`
   a partir do próprio argparse — a referência completa de flags passa a ser gerada, nunca escrita à mão.
3. **Check de links** — script curto (stdlib) que valida todos os caminhos `docs/…`/`.claude/…` citados em
   `*.md` e falha com lista dos quebrados; pendurar no fluxo de revisão (ou como hook local), garantindo que
   a Fase 9.1 nunca regride.

---

## Resumo de riscos e mitigação

| Risco | Mitigação |
|---|---|
| Perder um fato técnico num corte | Regra "nunca cortar sem destino" (Fases 2 antes de 3–8) + revisão por amostragem (9.3) |
| Referência quebrada pós-move | Baseline de grep (Fase 0) reexecutada na Fase 9; opcionalmente automatizada (Fase 10.3) |
| Skills param de disparar após reescrita do frontmatter | Manter os mesmos termos-gatilho nas `description`; teste prático (9.4) |
| Duplicação voltar com o tempo | Tabela "fonte única + ponteiro" no CLAUDE.md + nota de manutenção no `events.md` |
| Histórico git dos planos se perder | `git mv` em todos os moves |
