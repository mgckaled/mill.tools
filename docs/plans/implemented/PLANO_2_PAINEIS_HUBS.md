# Plano 2 — Painéis analíticos dos três hubs — plano de implementação

**Documento de execução — plano de implementação detalhado**
Data: 23 de junho de 2026 · Roadmap de origem: `docs/ROADMAP.md` (Plano 2) · Fundações: `docs/plans/implemented/PLANO_0_FUNDACAO_DADOS.md` (✅) e `docs/plans/implemented/PLANO_1_GRAFICOS.md` (✅) · Padrão de referência: skill `architecture`

> **Invocação da skill.** Ao executar, **invoque a skill `architecture`** e siga-a: núcleo puro (§1), camadas (§2), limites de tamanho/coesão e a regra **"divide-se ao tocar"** (§3), decomposição em `tabs/` (§4), fluxo core → (extra/gate) → CLI → GUI → testes (§5), checklist (§8).

> **Alinhamento com Plano 0/1.** Os painéis reusam a fundação: o **gráfico** de cada painel sai pelo caminho do Plano 1 (`charts.render_png` → PNG off-thread, tema injetado); as **agregações** são baratas (dados pequenos) e ficam em Python puro, com Polars (`frames`) opcional. Contrato `QueryResult` e a regra "nenhum DataFrame cruza para a GUI" continuam valendo.

---

## Sumário

1. Por que o Plano 2 é útil (e os caveats)
2. Objetivo e escopo
3. Achados (código + web)
4. Decisões de arquitetura
5. Desenho por hub
   - 5.1 Biblioteca — dashboard do acervo
   - 5.2 IA — saúde do índice + timing por modelo
   - 5.3 Receitas — **pré-requisito: histórico de execução** + painel
6. Onde o código encaixa
7. A ideia inteligente: poucas métricas acionáveis, sem peso
8. Passos de implementação (commits)
9. Testes
10. Critérios de aceitação
11. Riscos, o que **não** fazer e alternativa de sequenciamento
12. O que destrava

---

## 1. Por que o Plano 2 é útil (e os caveats)

**Útil porque:** (a) **custo quase-zero, reuso máximo** — Biblioteca e IA já coletam dados tabulares que ninguém vê; surfaçá-los é só Plano 0/1 sobre o que existe, sem ML nem dependência nova. (b) **Valor concreto para esta máquina** — o painel de *timing por modelo da IA* ajuda a escolher entre `gemma3-4b`/`1b`/`qwen`/`gemini`; a faxina de disco da Biblioteca mostra o que cresce; a saúde do índice RAG mostra quais docs dominam e o que está desatualizado. (c) **Sinergia anti-retrabalho** — ergue a *superfície analítica* (uma aba) em cada hub que os Planos 4 e 7 só estendem, e força a divisão dos builders gigantes `library/view.py` (658) e `ai/view.py` (685) no momento certo (regra "divide-se ao tocar").

**Caveats honestos:** para um app pessoal single-dev, o valor "dashboard" puro é **moderado** (dashboards rendem mais com volume/multiusuário); o ganho mais real e pessoal é o timing da IA. E a **Receitas é um caso à parte** (seção 5.3): não há histórico de execução persistido hoje, então seu painel exige criar essa persistência primeiro. Alternativa de sequenciamento na seção 11.

---

## 2. Objetivo e escopo

Transformar em análise os dados que os três hubs já acumulam, com painéis que respondem a poucas perguntas acionáveis, reusando o gráfico do Plano 1.

**No escopo:** núcleo puro de agregação por hub; persistência nova de histórico de execução de Receitas (pré-requisito); a superfície de painel em cada hub (aba/modo), com a divisão dos builders que isso exige; subcomandos `stats` na CLI para paridade; testes. **Fora do escopo:** ML/previsão (Plano 7), recursos semânticos (Plano 4), qualquer nova fonte de dado externa.

---

## 3. Achados (código + web)

**Inspeção do código — o que cada hub já tem:**

- **Biblioteca:** `scan_library()` → `LibraryItem(path, kind, category, size_bytes, modified, stem, suffix)`. Tudo o que um dashboard precisa (contagens, tamanhos, evolução por data) já está aí.
- **IA:** `core/rag/stats.index_stats()` → `IndexStats(n_docs, n_chunks, dim, embed_model, disk_bytes, updated_at, per_doc)` com `DocStat(source_path, kind, n_chunks, mtime, char_total)`. E `ai_answer_times` (durações por modelo) persistido em `config.json`, já lido em `ai/view.py`.
- **Receitas:** **lacuna confirmada** — não há histórico de execução persistido. O `runner` mantém só `outputs_by_op` em memória durante um run; o `store` persiste apenas *definições* de receita. Logo, o painel de Receitas precisa de uma persistência nova (seção 5.3).

**Varredura web — princípio de design:** dashboards eficazes priorizam **poucas métricas acionáveis** (a referência sugere 5–9), cada uma passando o "teste da decisão" (que ação muda por causa deste número?), e ganham com **contexto** (comparação a meta/período/tendência). *Influência:* cada painel mostra um punhado de números que importam + um gráfico que responde a uma pergunta — nada de "métricas de vaidade".

---

## 4. Decisões de arquitetura

**Agregação em Python puro; gráfico via Plano 1.** Os volumes aqui são minúsculos (catálogo, índice, runs), então as métricas e tabelas são computadas com a stdlib (`collections.Counter`, somas, agrupamento simples) — **sem exigir o extra `[analysis]`** para ver números. Só o **gráfico** usa o caminho do Plano 1 (`charts`, extra `[data-plot]`), gated: sem o extra, o painel mostra números/tabelas e esconde o gráfico. Graceful degradation, base intacta.

**Núcleo de agregação é puro, por hub.** `core/library/analytics.py`, `core/rag/analytics.py`, `core/recipes/history.py` — funções puras que recebem os dados já coletados e devolvem métricas + `QueryResult` (tabelas) e, quando aplicável, um `ChartSpec` para o Plano 1. Nenhum toca Flet.

**Painel = superfície nova nos hubs, dividindo ao tocar.** Adicionar o painel obriga, pela regra da skill `architecture` §3, a extrair os builders grandes para `tabs/`/sub-builders **antes** de acrescentar. É a dívida do Plano −1 sendo paga no momento certo.

**Contrato de GUI inalterado.** Painéis emitem eventos próprios (`*_stats_*`) e exibem `QueryResult` + PNG; nenhum DataFrame cruza para a GUI.

---

## 5. Desenho por hub

### 5.1 Biblioteca — dashboard do acervo

**Dados:** `list[LibraryItem]` de `scan_library()`. **Núcleo** `core/library/analytics.py` (puro): `summary(items)` → contagens por `kind` e por `category`, tamanho total e por kind, item mais antigo/mais novo; `largest(items, n)` → maiores ocupantes; `growth_by_period(items, period="month")` → série temporal a partir de `modified`. Saídas como métricas + `QueryResult`.

**Painel (perguntas acionáveis):** "quanto de cada tipo eu produzo?" (contagens), "o que está enchendo o disco?" (top maiores + tamanho por kind, **gráfico de barras**), "quanto cresci por mês?" (**gráfico de linha** da série temporal). Decisão que cada número habilita: o que apagar/arquivar.

### 5.2 IA — saúde do índice + timing por modelo

**Dados:** `IndexStats`/`DocStat` (já existentes) + `ai_answer_times` (config.json). **Núcleo** `core/rag/analytics.py` (puro): `index_health(stats)` → docs que dominam o índice (top por `n_chunks`), distribuição de `char_total`, docs potencialmente desatualizados (por `mtime`); `model_timings(times_map)` → por modelo: contagem, média, mediana, p90. Saídas como métricas + `QueryResult`.

**Painel:** "quais documentos dominam minhas buscas?" (top por chunks, **barras**), "qual modelo responde mais rápido na minha máquina?" (média/p90 por modelo, **barras** — a métrica de maior valor pessoal). Reaproveita parte do que o `ai stats`/`index_tab.py` já mostram, sem duplicar a lógica de `stats.py`.

### 5.3 Receitas — pré-requisito (histórico) + painel

**Lacuna:** sem dado, sem painel. Então o sub-plano tem **duas partes**.

**Parte A — persistir histórico (capacidade nova, pequena).** `core/recipes/history.py` (puro): `RunRecord(recipe_name, started_at, finished_at, duration, status: "ok"|"error"|"cancelled", n_steps, failed_op: str|None, batch_size: int|None)`; `append_run(record, *, path=...)` grava append-only em `~/.mill-tools/recipe_runs.json` (capado nos últimos N, como `data_assessments.json`); `load_runs(path)`; `aggregate(runs)` → por receita: nº execuções, taxa de sucesso, duração média, passo que mais falha. O **worker** (`gui/modules/recipes/worker.py`) e o **CLI** gravam um `RunRecord` ao observar o evento terminal (`task_done`/`task_error`) — assim o `runner` **puro permanece intocado** (a persistência é efeito colateral da camada de orquestração, não do core de execução).

**Parte B — painel:** "quais receitas são confiáveis?" (taxa de sucesso por receita), "quais são lentas?" (duração média, **barras**), "o que mais quebra?" (passo com mais falhas). Esse histórico é também a matéria-prima do Plano 7 (ML operacional) — construí-lo aqui serve aos dois.

---

## 6. Onde o código encaixa

**Núcleo (puro):** `core/library/analytics.py`, `core/rag/analytics.py`, `core/recipes/history.py`. Cada um ≤ ~200 linhas, uma responsabilidade.

**GUI — dividir ao tocar:**

- **Biblioteca** (`library/view.py`, 658, monolítico): extrair o painel para `library/analytics_panel.py` e oferecer um terceiro modo além de grade/lista (toggle por `visible=` num `Stack`, padrão já usado). Aproveitar para fatiar o builder gigante conforme a skill §4.
- **IA** (`ai/view.py`, 685; já tem `index_tab.py`): adicionar `ai/analytics_tab.py` e plugá-lo no toggle de abas existente (Conversa | Índice | **Painel**) — segue o padrão já estabelecido pelo `index_tab`.
- **Receitas** (`recipes/view.py`, 344): adicionar um modo/aba "Histórico" alimentado por `history.aggregate`.

**CLI (paridade, skill `cli`):** `library stats`, `recipe stats` (novos); `ai stats` **já existe** — estender com o bloco de timing por modelo. Reusam o núcleo direto, sem `CLIEventBus`, UTF-8 no stdout.

---

## 7. A ideia inteligente: poucas métricas acionáveis, sem peso

Três decisões mantêm o Plano 2 leve e fluido.

**Cada painel responde a 2–3 perguntas acionáveis, não despeja dados.** Seguindo o princípio da varredura, cada painel tem um punhado de números que mudam uma decisão (o que apagar, qual modelo usar, qual receita corrigir) + um gráfico. Sem métricas de vaidade.

**Números sem extra; gráfico opcional.** As agregações rodam em Python puro sobre dados minúsculos — o painel funciona mesmo sem `[analysis]`/`[data-plot]`. O gráfico (caminho do Plano 1) aparece se os extras existirem; senão, some graciosamente. A base segue mínima e nada quebra.

**Tudo local e off-thread.** Scan/agregação rodam fora da UI thread (`page.run_task`/thread daemon, padrão do design-system); o gráfico chega como PNG (Plano 1). Nenhum DataFrame ou figura na camada Flet — a tradução para a GUI continua trivial.

---

## 8. Passos de implementação (commits)

**Commit 1 — núcleos puros + CLI.** `library/analytics.py`, `rag/analytics.py`; `recipes/history.py` (RunRecord + append/load/aggregate); `library stats`/`recipe stats` + extensão do `ai stats`; testes de todos. Sem GUI. Verde + ruff.

**Commit 2 — gravação do histórico de Receitas.** Worker/CLI de Receitas gravam `RunRecord` no evento terminal; teste com bus falso. (Runner puro intocado.)

**Commit 3 — painel Biblioteca.** Dividir `library/view.py` ao tocar; `analytics_panel.py`; 3º modo. Smoke manual.

**Commit 4 — painel IA.** `ai/analytics_tab.py` no toggle existente. Smoke manual.

**Commit 5 — painel Receitas.** Modo "Histórico" sobre `history.aggregate`. Smoke manual.

Ordem: núcleos/CLI (testáveis) primeiro; GUI por hub, um commit cada, risco crescente. Suíte verde entre commits.

---

## 9. Testes

**Núcleo (unit, sem GUI):**

- `tests/core/library/test_analytics.py`: `summary`/`largest`/`growth_by_period` sobre `LibraryItem`s sintéticos — contagens por kind/category, tamanho total, série temporal por mês (datas controladas via campo `modified`), bordas (acervo vazio).
- `tests/core/rag/test_analytics.py`: `index_health` sobre `IndexStats`/`DocStat` falsos (top por chunks, desatualizados por mtime); `model_timings` (média/mediana/p90/contagem; mapa vazio; um modelo só).
- `tests/core/recipes/test_history.py`: round-trip `append_run`/`load_runs` em `tmp_path` (passe `path=` explícito, como `store.py`); cap nos últimos N; `aggregate` (taxa de sucesso, duração média, passo que mais falha); arquivo malformado → vazio.

**CLI:** `tests/cli/test_library_cli.py`/`test_data?`/`test_recipe_cli.py`/`test_ai_cli.py`: dispatch de `library stats`/`recipe stats`/`ai stats` estendido (mock dos núcleos; `capsys`).

**Worker de Receitas:** bus falso — ao receber `task_done`/`task_error`, grava um `RunRecord` (mock `history.append_run`); status correto por evento.

**GUI dos painéis:** não testável headless → smoke manual (abrir cada hub, ver números + gráfico, alternar modo). Lógica pura já coberta nos núcleos. Cobertura dos `analytics`/`history`: ≥ 90%.

---

## 10. Critérios de aceitação

- Três núcleos de agregação puros (sem Flet), ≤ ~200 linhas cada; histórico de Receitas persistido em `~/.mill-tools/recipe_runs.json` com runner puro intocado.
- Painéis exibem poucas métricas acionáveis + gráfico opcional (Plano 1); funcionam **sem** os extras (só números) e mostram o gráfico **com** eles.
- Builders grandes divididos ao tocar (`library/view.py`); IA usa o toggle existente; nenhuma outra aba/arquivo fora de escopo alterado.
- CLI `library stats`/`recipe stats` + `ai stats` estendido em paridade.
- Contrato `QueryResult`/eventos preservado; nenhum DataFrame/figura cruza para a GUI; base mínima intacta.
- `uv run pytest -m unit` verde; `ruff` limpo; cobertura dos núcleos ≥ 90%; checklist da skill `architecture` (§8) satisfeito.

---

## 11. Riscos, o que **não** fazer e alternativa de sequenciamento

**Risco/escopo:** o painel de Receitas embute uma capacidade nova (persistência de histórico) — não tratá-la como "só um painel". Não duplicar a lógica de `stats.py` na IA (reusar). Não exigir `[analysis]`/`[data-plot]` para ver números (só para o gráfico). Não inflar `library/view.py`/`ai/view.py` — dividir ao tocar.

**Alternativa de sequenciamento (decisão sua).** Se você valoriza mais *capacidade nova* que dashboards, é defensável **adiar o Plano 2** e ir ao Plano 3 (fundação de ML) + Plano 4 (semântico): quando o Plano 4 adicionar abas de ML aos mesmos hubs, a divisão dos builders e a superfície de painel nasceriam ali, dobrando os painéis analíticos junto. O custo de adiar é baixo; o ganho do Plano 2 agora é sobretudo o timing da IA e a validação da fundação nos hubs. Recomendo um meio-termo: fazer **só o painel de IA (timing)** agora — o de maior valor pessoal e custo mínimo — e adiar Biblioteca/Receitas para quando os hubs forem tocados pelo Plano 4/7.

---

## 12. O que destrava

O Plano 2 valida a fundação (Plano 0/1) nos hubs, cria o **histórico de execução** que o Plano 7 (ML operacional) consome, e estabelece a superfície de painel que os Planos 4/7 estendem. Próximo elo natural: **Plano 3 — fundação de ML** (`core/ml/` + acessor de embeddings), que abre a onda semântica do Plano 4.

---

## Fontes

- [Dashboard Revolution: Why Less Data Often Leads To Better Decisions — Sigma](https://www.sigmacomputing.com/blog/data-analysis-less-more)
- [Vanity Metrics vs. Actionable Insights — AgencyAnalytics](https://agencyanalytics.com/blog/vanity-metrics)
- [Dashboard Design Guide (2026) — Improvado](https://improvado.io/blog/dashboard-design-guide)
