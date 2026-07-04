# Plano de implementação — Plano −1 (refatoração prévia)

**Documento de execução — passos detalhados, separado do roadmap de features**
Data: 23 de junho de 2026 · Diagnóstico de origem: `docs/REFATORACAO_PREVIA.md` · Padrão de referência: skill `architecture` (`.claude/skills/architecture/SKILL.md`)

> **Por que separado do roadmap.** Este é trabalho **estrutural e preservador de comportamento** — move código, não muda o que ele faz. Misturá-lo com o roadmap de features (`docs/ROADMAP_ML_DADOS.md`), que **adiciona** comportamento, confundiria revisão e histórico. Por isso o Plano −1 vive sozinho, com seus próprios commits e critérios de aceitação. Ele precede o Plano 0, mas é independente dele (toca arquivos diferentes) e pode até rodar em paralelo.

> **Governança.** Toda decisão estrutural abaixo segue a skill `architecture`: limites de tamanho/coesão (seção 3 da skill), padrões de decomposição `blocks/`·`tabs/`·`_state`·`registry/<módulo>` (seção 4) e a regra "divide-se ao tocar". Ao executar, **invoque a skill `architecture`** como referência.

---

## Sumário

1. Escopo e princípios de execução
2. Ordem de execução e por quê
3. Tarefa R — dividir `core/recipes/registry.py` em pacote
4. Tarefa V — decompor `gui/modules/data/view.py`
5. Tarefa C — fixar a convenção (CLAUDE.md + skill)
6. Critérios de aceitação (Definition of Done)
7. Riscos, validação e rollback
8. Estimativa e checklist final

---

## 1. Escopo e princípios de execução

O Plano −1 toca **exatamente dois arquivos** de produção, mais a documentação de convenção. Nada de comportamento muda.

Princípios que valem em todas as tarefas:

A refatoração é **preservadora de comportamento**: a rede de proteção é a suíte existente (913 testes unitários, `uv run pytest -m unit` verde, `ruff` limpo) — regra do projeto. Cada tarefa é entregue em **commit próprio e pequeno**, com a suíte verde antes e depois, jamais num único commitão. A **API pública não muda**: imports externos como `from src.core.recipes.registry import STEP_REGISTRY` continuam válidos após a divisão. E o que **não** está no escopo (os demais arquivos grandes — `ai/view.py`, `library/view.py`, `audio_player.py` etc.) permanece intocado, pela regra "divide-se ao tocar".

---

## 2. Ordem de execução e por quê

Duas tarefas independentes, executadas nesta ordem:

**Primeiro a Tarefa R (registry), depois a Tarefa V (data/view).** A razão é o risco: o `registry` **já tem testes** (`tests/core/recipes/test_registry.py`), então a divisão é validada automaticamente — é a refatoração mais segura, ideal para começar e calibrar o processo. O `data/view.py` é a camada Flet, **não testável headless**, logo mais arriscada e merece ser feita depois, com a confiança já adquirida. A **Tarefa C (convenção)** acompanha, idealmente no mesmo commit da Tarefa R ou logo após.

Nenhuma das três bloqueia o Plano 0; mas todas devem preceder os planos que **estendem** esses arquivos (Planos 1 e 5 inflariam `data/view.py`; Planos 5 e 7, o `registry`).

---

## 3. Tarefa R — dividir `core/recipes/registry.py` em pacote

**Estado atual.** 733 linhas: 33 adaptadores de 7 módulos (áudio, vídeo, transcrição/IA, documentos, imagem, dados) seguidos do dicionário `STEP_REGISTRY` (linhas 622–733). Baixa coesão clássica — adaptadores de mundos diferentes no mesmo arquivo.

**Estrutura-alvo (padrão `registry/<módulo>`).**

```
src/core/recipes/registry/
├── __init__.py         # monta STEP_REGISTRY e re-exporta símbolos públicos
├── audio.py            # 5 adapters + AUDIO_STEPS
├── video.py            # 7 adapters + VIDEO_STEPS  (inclui o multi-input video.subtitle)
├── transcription.py    # transcribe/format/analyze/prompt + TRANSCRIPTION_STEPS
├── ai.py               # ai.answer + AI_STEPS
├── document.py         # 11 adapters + DOCUMENT_STEPS
├── image.py            # convert/resize + IMAGE_STEPS
└── data.py             # query/convert/profile + DATA_STEPS
```

**Passos.**

1. Criar o diretório `src/core/recipes/registry/` e remover `registry.py` na mesma operação (preferir `git mv` por arquivo de origem para preservar histórico onde possível; na prática, criar os novos e apagar o antigo num só commit).
2. Em cada submódulo, colar os adaptadores daquele grupo **sem alterar uma linha do corpo** (eles já fazem `from X import Y` function-local; mover o arquivo não muda efeito de import) e declarar o dicionário do grupo, por exemplo:
   ```python
   AUDIO_STEPS: dict[str, StepSpec] = {
       "audio.download": StepSpec(_audio_download, frozenset({KIND_URL}), KIND_AUDIO, "Baixar áudio"),
       # ... os 5 do grupo
   }
   ```
   O cabeçalho/docstring explicativo do arquivo original migra para o `__init__.py`.
3. No `__init__.py`, montar a **fonte única** a partir dos grupos e manter a compatibilidade de import:
   ```python
   from src.core.recipes.registry.audio import AUDIO_STEPS
   from src.core.recipes.registry.video import VIDEO_STEPS
   # ... demais grupos
   STEP_REGISTRY: dict[str, StepSpec] = {
       **AUDIO_STEPS, **VIDEO_STEPS, **TRANSCRIPTION_STEPS, **AI_STEPS,
       **DOCUMENT_STEPS, **IMAGE_STEPS, **DATA_STEPS,
   }
   ```
   Como `registry` passa a ser pacote, `from src.core.recipes.registry import STEP_REGISTRY` continua resolvendo pelo `__init__` — **runner, validate e os testes externos não mudam**.
4. **Impacto nos testes (mínimo).** A maioria de `test_registry.py` acessa via `STEP_REGISTRY[key].adapter(...)` — intacto. Os adaptadores reais são mockados **na origem do core** (`mocker.patch("src.core.audio.normalizer.normalize_lufs", ...)`) — também intacto, pois a origem não se moveu. Apenas os poucos pontos que alcançam um adaptador privado pelo módulo (`import src.core.recipes.registry as reg; reg._video_subtitle`) precisam apontar para o submódulo novo (`from src.core.recipes.registry.video import _video_subtitle`) — uma correção de 1 linha por ocorrência (há ~3). Opcionalmente, espelhar `test_registry.py` em `tests/core/recipes/registry/test_<módulo>.py`, conforme a skill `testing`; não é obrigatório nesta tarefa.
5. Rodar `uv run pytest tests/core/recipes -m unit` (verde) e `ruff` (limpo).

**Atenção.** Manter `ai.answer` em `registry/ai.py` (hoje ele está agrupado sob "transcription/LLM" no arquivo, mas pertence ao mundo IA). O `STEP_REGISTRY` final deve ter **exatamente as mesmas chaves e specs** de antes — a divisão é puramente de organização.

---

## 4. Tarefa V — decompor `gui/modules/data/view.py`

**Estado atual.** 1.368 linhas: uma única função `build_data_module` com 47 closures cobrindo 3 abas (Consulta, Pré-visualização, Análise com IA), estado compartilhado e a barra de abas.

**O desafio real (não é recortar-e-colar).** As closures compartilham **estado mutável** — listas como `_result_rows`, `_has_result`, `_tab`, mais helpers `_toast`/`_scoped_update` e o cronômetro. Mover uma aba para outro arquivo quebra essas capturas. A solução, alinhada ao padrão `blocks/`, é introduzir um **contexto compartilhado** passado a cada construtor de aba.

**Estrutura-alvo (padrão `tabs/` + `_state`).**

```
src/gui/modules/data/
├── view.py            # build_data_module enxuto: monta contexto, abas, barra e ciclo de vida
├── _state.py          # DataViewContext (estado + toast/scoped_update/timer) + _tab_empty_state + lógica pura
└── tabs/
    ├── __init__.py
    ├── query_tab.py     # build_query_tab(ctx) -> QueryTab  (view + footer + handlers de evento)
    ├── preview_tab.py   # build_preview_tab(ctx) -> PreviewTab (view + on_enter + handlers)
    └── analysis_tab.py  # build_analysis_tab(ctx) -> AnalysisTab (view + on_enter + handlers)
```

**Passos.**

1. **Criar `_state.py`** com um `DataViewContext` (dataclass) carregando o que hoje é estado compartilhado: `page`, `bus`, `form`, `nav`, `embed_model`, e as listas de estado (`result_columns`, `result_rows`, `page_idx`, `rename_fields`, `last_saved`, `action`, `pending_model`, `last_error`, `last_failed_sql`, `has_result`, `tab`). Mover para cá os helpers transversais `toast()` e `scoped_update()` (regra de ouro do spinner — ver skill `design-system`), os auxiliares do cronômetro e o `_tab_empty_state`. Mover também a **seleção de fonte compartilhada** (`_file_by_name`, `_refresh_source_selectors`), usada por Pré-visualização e Análise.
2. **Extrair a lógica pura** que hoje está enterrada em closures e é testável sem Flet — por exemplo `_effective_sql`/`_save_stem`/`_renames` (montagem de SQL e mapa de renomeação) e a aritmética de paginação (`_go_prev`/`_go_next`/`_cell`). Colocá-las como funções puras em `_state.py` (ou um `_logic.py`) e **escrever testes unitários** para elas — ganho líquido de cobertura que a versão monolítica não tinha.
3. **`query_tab.py`** — receber `ctx`, construir o `consulta_view` e o `footer`, e abrigar as closures da Consulta (handlers do formulário `on_run`/`on_preview`/`on_refine_with_ai`; estado do painel `begin`/`end`/`show_review`; tabela de resultado `render_table`/paginação/`build_rename_fields`/`show_result`; ações `on_save`/`on_converse`/`on_save_recipe`/`open_folder`). Retornar um objeto `QueryTab` expondo `view`, `footer` e os **handlers de evento** que a `view.py` precisa rotear (`on_sql_ready`, `on_result`, `on_saved`).
4. **`preview_tab.py`** — abrigar `refresh_sheet_dd`, `load_preview`, `on_preview_file_change`, `preview_file`, `on_index`, `end_index` e os handlers de progresso de indexação. Expor `view`, `on_enter()` (chamado ao ativar a aba) e os handlers `data_index_*`.
5. **`analysis_tab.py`** — abrigar `assess_tick`, `on_assess`, `end_assess`, `load_assessment_cache`. Expor `view`, `on_enter()` e os handlers `data_assess_*`.
6. **`view.py` (enxuto)** — `build_data_module` passa a: (a) montar o `DataViewContext`; (b) chamar os três `build_*_tab(ctx)`; (c) construir a barra de abas e o `_show_tab` (que alterna `visible=` no `Stack` e chama `tab.on_enter()` da aba ativada — preservando o comportamento atual de carregar prévia/avaliação ao entrar); (d) **assinar o bus uma vez** e distribuir cada evento `data_*` ao handler da aba correta por tipo de evento (mantém o módulo auto-contido, padrão da skill `design-system`); (e) montar o `control` (form 380px | divisor | painel) e devolver o `Module`. Alvo: **≤ 300 linhas**.
7. **Preservar as regras de GUI** ao mover: a "regra de ouro" do spinner (`page.update()` **antes** de `start()`), o `scoped_update` durante a animação e o `module_id="data"` nos eventos seguem inalterados — apenas mudam de arquivo. Referência: skill `design-system`.

**Validação (sem teste headless).** Além dos testes das funções puras extraídas no passo 2, fazer um **teste de fumaça manual**: abrir o módulo Dados, executar uma consulta em PT, paginar o resultado, renomear coluna e salvar; alternar para Pré-visualização (carrega a fonte, seletor de aba XLSX, botão Indexar no RAG); alternar para Análise com IA (avaliar, cronômetro ao vivo). Conferir que o estado é preservado ao trocar de aba (o `control` é construído uma vez — padrão `Module`).

---

## 5. Tarefa C — fixar a convenção (CLAUDE.md + skill)

A skill `architecture` já carrega a regra de tamanho/coesão, mas convém deixá-la também visível no `CLAUDE.md`, em "Convenções de código". Trecho proposto para colar:

```markdown
- **Tamanho e coesão de arquivo** (governado pela skill `architecture`): builder de GUI ≤ ~400–500 linhas; módulo de `core/` ≤ ~300–400. Um arquivo = uma responsabilidade. Builder/aba/seção que cresce → extrair via `blocks/`/`tabs/`/`registry/<módulo>` (sub-builder devolve `(controle, refs/handlers)`). Regra "divide-se ao tocar": dividir no momento em que um plano estende o arquivo, não preventivamente.
```

E concluir a instalação da skill (bloqueada nesta sessão por estar sob `.claude/`):

```powershell
move docs\architecture-SKILL.md .claude\skills\architecture\SKILL.md
```

---

## 6. Critérios de aceitação (Definition of Done)

**Tarefa R concluída quando:** `registry/` é pacote com um submódulo por área; `STEP_REGISTRY` tem exatamente as mesmas chaves/specs de antes; `from ...registry import STEP_REGISTRY` segue funcionando; `tests/core/recipes` verde; `ruff` limpo; nenhum arquivo do pacote acima de ~200 linhas.

**Tarefa V concluída quando:** `view.py` ≤ ~300 linhas e contém só montagem/roteamento; cada `tabs/*.py` é coeso (uma aba); `_state.py` concentra estado e lógica pura; novas funções puras têm teste unitário; `uv run pytest -m unit` verde; `ruff` limpo; teste de fumaça manual aprovado nas três abas.

**Tarefa C concluída quando:** o trecho de convenção está no `CLAUDE.md`; a skill `architecture` está em `.claude/skills/architecture/SKILL.md` e referenciada na linha-índice de skills (já feito).

---

## 7. Riscos, validação e rollback

O principal risco está na Tarefa V, por falta de teste automatizado da camada Flet. Mitigações: extrair e testar a lógica pura (passo V.2), mover comportamento **sem editá-lo**, e o roteiro de fumaça manual da seção 4. Risco secundário: capturar mal o estado compartilhado ao introduzir o `DataViewContext` — mitigado por mover o estado para o contexto **antes** de recortar as abas, validando a Consulta isoladamente primeiro, depois Pré-visualização, depois Análise.

Rollback é trivial porque cada tarefa é um commit pequeno e isolado: `git revert <commit>` desfaz a refatoração sem afetar o resto. Recomenda-se, na Tarefa V, **commits intermediários por aba** (extrair Consulta → verde → extrair Pré-visualização → verde → extrair Análise → verde), em vez de uma única reescrita.

---

## 8. Estimativa e checklist final

A Tarefa R é pequena e de baixo risco (mecânica, com testes cobrindo). A Tarefa V é média e exige cuidado manual, melhor fatiada em três commits por aba. A Tarefa C é trivial.

Checklist de fechamento do Plano −1 — **CONCLUÍDO** (commits `291e59a` R+C, `7ce41d4` V; 975 testes unit verdes, +25):

- [x] R: `registry/` dividido (um submódulo por área; nada acima de ~190 linhas); `STEP_REGISTRY` idêntico em conteúdo; `ai.answer` movido para `registry/ai.py`; testes de recipes verdes.
- [x] V: `data/view.py` 1.368 → 239 linhas; `tabs/` + `_state.py` criados; lógica pura testada (25 testes novos); fumaça manual da GUI aprovada.
- [x] C: convenção no `CLAUDE.md`; skill `architecture` instalada em `.claude/skills/`.
- [x] `uv run pytest -m unit` verde e `ruff` limpo (no escopo tocado) após cada tarefa.
- [x] Roadmap (`docs/ROADMAP_ML_DADOS.md`) intocado — features continuam separadas desta refatoração.

> **Exceção aceita conscientemente:** `tabs/query_tab.py` ficou em 725 linhas, acima do teto ~500, por ser a aba mais rica e de coesão alta (uma só responsabilidade). Não dividida agora para evitar rewiring `blocks/` sem validação headless. Marcada como candidata a `blocks/` pela regra "divide-se ao tocar" — dividir quando o `query_tab` for naturalmente alterado ou quando houver caminho de validação.
>
> **Dívida de documentação (menor):** os arquivos `architecture` (skill), `CLAUDE.md` (árvore de `Estrutura`) e `REFATORACAO_PREVIA.md` ainda descrevem `tabs/` e `registry/<módulo>` como "proposto" — agora são reais. Atualizar o termo para "implementado" quando convier.

Concluído o Plano −1, os Planos 1, 2, 4, 5 e 7 passam a **adicionar** um arquivo de aba/adaptador novo em vez de inflar um arquivo gigante — exatamente o que a regra "divide-se ao tocar" da skill `architecture` garante daqui para frente.
