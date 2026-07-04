# Plano de Implementação — PR9: Módulo Dados

> **mill.tools** · 6ª ferramenta na NavigationRail · manipulação de dados estruturados
> Paradigma: **query-first** (a composição vive numa consulta só) · motor **DuckDB** · tradução PT→SQL pela camada de IA existente.

---

## 1. Visão geral e decisão de arquitetura

O módulo **Dados** entra na `NavigationRail` como 6ª ferramenta (não é hub — transforma entrada → saída, como Documentos/Imagens). Diferente dos módulos de blocos, ele **não** oferece operações de clique único: a composição (juntar + filtrar + agrupar + somar + ordenar + moldar o retorno) vive numa **consulta única**, escrita em português (traduzida pela IA) ou na mão.

**Divisão de responsabilidades (princípio central):**

| Ator | Faz | Não faz |
|---|---|---|
| **IA** (`make_llm`/`llm_factory`) | Recebe só o **schema** (nomes/tipos de coluna) + a pergunta → devolve `(sql, explicação_pt)` | Nunca toca nas linhas de dados |
| **DuckDB** | Abre os arquivos do disco, executa a consulta, devolve as linhas | Não "pensa" — só executa |
| **Core (`src/core/data/`)** | Orquestra: scan, runner, conversão, profile, validação | Sem Flet |
| **GUI/CLI** | Coleta entrada, mostra prévia/revisão, salva saída | Sem lógica de dados |

**Consequência de privacidade:** se o usuário escolher Gemini, só os **nomes de coluna** saem da máquina — o conteúdo das tabelas fica 100% local no DuckDB.

---

## 2. Escopo

**Dentro (PR9):**
- Fonte multi-arquivo (chips com contagem de linhas/colunas + nomes de coluna).
- Modo **Português** (NL→SQL com cartão de revisão "entendi assim") e modo **Consulta** (SQL na mão).
- Execução via DuckDB, prévia paginada do resultado.
- Customização de retorno: renomear colunas, escolher formato, salvar em `output/data/`.
- Conversão de formato, profile (relatório textual).
- Integração: Biblioteca, Receitas (`STEP_REGISTRY`), bridge "Conversar sobre" → hub IA.

**Fora (sub-PRs futuros):**
- **Gráficos** (`plot`) — exige `matplotlib` (extra `[data-plot]`); fica para PR9.1.
- Encadeamento em estágios (resultado vira nova fonte) — PR9.2.
- Editor visual de pipeline (descartado: frágil no Flet 0.85).

---

## 3. Dependências novas

- `duckdb` — wheel nativo, embutido, **torch-free**, sem servidor. Única dep essencial.
- `charset-normalizer` — detecção de encoding de CSV (dor clássica no Windows: cp1252/utf-8/BOM/`;` vs `,`).
- Extensão `excel` do DuckDB (ou helper) — só para XLSX (read/write).
- `matplotlib` — **opcional**, extra `[data-plot]`, só no PR9.1.

> 🔍 **Checkpoint context7 (antes da Fase 0):** `resolve-library-id` → `duckdb`; `query-docs` sobre: API Python (`duckdb.connect`, `read_csv_auto`, `read_json`, `read_parquet`, extensão `excel`, `COPY ... TO`), opção `encoding` do leitor CSV, e conexão in-memory read-only. Confirmar versão atual e assinaturas antes de fixar a dep no `pyproject`.

---

## 4. Fases

### Fase 0 — Fundação
- Adicionar `duckdb` + `charset-normalizer` via `uv`. Validar import torch-free.
- Criar `output/data/` no bootstrap de diretórios.
- Definir chaves de config: `last_data_model`, `last_data_format`, `last_data_mode`, `data_query_times` (média móvel, reusa o padrão de `ai_answer_times`).
- Persistência de consultas salvas em `~/.mill-tools/queries.json` (mesmo padrão de `recipes.json`/`prompts.json`).

### Fase 1 — Core puro (`src/core/data/`)

Arquivos (responsabilidade única, no padrão dos outros `core/`):

- **`types.py`** — `DataFile`, `ColumnInfo`, `QueryResult` (linhas + nomes de coluna + tempo + nº de linhas).
- **`scanner.py`** — `scan_file(path) → DataFile` (contagem + colunas/tipos via `DESCRIBE`/`LIMIT 0`, barato). Alimenta os chips e o schema da IA.
- **`engine.py`** — **única fronteira com o DuckDB** (injetável, como o `embedder` do RAG). `run_query(files, sql) → QueryResult`. Registra cada arquivo como view, roda numa **conexão in-memory efêmera** (nada gravável anexado → consulta maliciosa não escreve). Detecta encoding antes de ler CSV.
- **`nl2sql.py`** — `to_sql(schema, pergunta) → (sql, explicacao_pt)` via `make_llm`. Prompt estrito: **só SELECT**, recebe apenas nomes/tipos de coluna. Escapa chaves literais (`{`→`{{`) como nos perfis de análise.
- **`validate.py`** — guarda de segurança: rejeita tudo que não seja SELECT (`COPY`/`ATTACH`/`INSTALL`/`PRAGMA`/DML).
- **`convert.py`** — conversões CSV/TSV/JSON/Parquet/XLSX via `COPY ... TO`.
- **`profile.py`** — relatório textual (linhas, colunas, nulos, cardinalidade, min/máx/média) → texto indexável pelo RAG.

> 🔍 **Checkpoint context7 (durante a Fase 1):** `query-docs` DuckDB sobre registro de DataFrame/arquivo como view, `read_csv` com `encoding`/`delim`/`sample_size`, e `COPY` para cada formato de saída. Confirmar a sintaxe **antes** de escrever `engine.py`/`convert.py`.

> 🧪 **Invoque a skill `testing`** ao escrever os testes de core. Marcar `unit` (DuckDB roda in-process, sem rede/GPU → qualifica como unit, igual ao `numpy`). `nl2sql` testado com `GenericFakeChatModel` (mock de LLM já usado no projeto); `engine`/`convert`/`profile` com DuckDB real e fixtures de CSV/JSON pequenos em `conftest.py`.

### Fase 2 — CLI (`src/cli/data.py`)

> ⌨️ **Invoque a skill `cli`** antes de implementar, para seguir o padrão de subcomando + `CLIEventBus` e a referência de flags.

- Subcomandos: `data query <arquivos...> "<pergunta>" [--sql] [--out csv|xlsx|json|parquet]`, `data convert`, `data profile`.
- `--sql` pula o NL→SQL (usuário fornece a consulta).
- Reusa `CLIEventBus`; stdout em **UTF-8** (nomes com caracteres especiais quebram cp1252).

> 🔍 **Checkpoint context7 (entre Fase 2 e 3):** confirmar quaisquer mudanças recentes de comportamento do leitor CSV/JSON do DuckDB que afetem a paridade CLI↔GUI.

### Fase 3 — GUI (`src/gui/modules/data/`)

> 🎨 **Invoque a skill `design-system`** antes de construir a view, para respeitar tokens, factories de componentes, tabelas de evento e thread-safety.

Arquivos no padrão dos demais módulos:

- **`form_view.py`** — seletor de fonte (`InputSource`/FilePicker) + toggle **`Português | Consulta`** (`visible=` num `Stack`) + caixa de texto + botões **Pré-visualizar** / **Executar**.
- **`worker.py`** — `run_data_query` em thread daemon, `module_id="data"`, emite eventos no `EventBus`.
- **`view.py`** — cartão de revisão "entendi assim" (expansível, com o SQL editável), **prévia paginada** da tabela (`_PAGE_SIZE`, igual à Biblioteca) e o bloco de **customização de retorno** (renomear coluna, dropdown de formato, botões Salvar/Conversar sobre/Salvar como Receita).

Registro: nova entrada em `MODULES` (`app.py`); incluir em `_RAIL_MODULES` (**não** nos `_HUB_IDS`); `icon`/`selected_icon`.

**Quirks Flet 0.85 a respeitar:** `DataTable` paginado com update **escopado** (nunca `page.update()` global); toggle por `visible=` em `Stack`; `ft.Dropdown` usa `on_select` (não `on_change`); cronômetro vivo da consulta via `page.run_task` (async), não thread daemon; se houver PNG (futuro plot), `ft.Image.src` aceita bytes direto.

> 🔍 **Checkpoint context7 (durante a Fase 3):** `resolve-library-id` → `flet`; `query-docs` sobre `DataTable`/`DataColumn`/`DataRow` e `FilePicker` na 0.85, para confirmar a API antes de montar a prévia.

### Fase 4 — Integração com Receitas

- Entradas no `STEP_REGISTRY`: `data.query`, `data.convert`, `data.profile`, com **adaptadores finos** `adapter(inputs, params, ctx) → list[Path]` (chamam o core puro, gravam no dir canônico, normalizam callbacks para `ctx.emit`).
- **Caso sutil:** `data.query` é **multi-input** (vários arquivos) com a consulta como param — análogo ao `video.subtitle`. Documentar.
- Fecha a cadeia: `data.query → ai.answer`, ou `data.convert → data.profile`.

### Fase 5 — Integração com Biblioteca

- `core/library/scanner.py`: mapear `output/data/` → `kind="data"`.
- `thumbnails.py::thumbnail_for`: ícone de tabela para `data` (ou, no PR9.1, preview do PNG do `plot`).

### Fase 6 — Testes, QA e fechamento

> 🧪 **Invoque a skill `testing`** novamente para a suíte de integração e a cobertura.

- `unit`: `scanner`, `engine` (DuckDB real), `nl2sql` (LLM mock), `convert`, `validate`, `profile`, helpers de formatação.
- `uv run pytest -m unit` verde + `ruff` limpo **antes de qualquer commit**.
- Cobertura sobre `src/core/data/` (GUI excluída, não testável headless).

> 🔍 **Checkpoint context7 (durante a Fase 6):** consultar edge-cases conhecidos do DuckDB (tipos de CSV mal-formados, JSON aninhado) para cobrir nos testes.

### Fase 7 — Documentação e config

- Atualizar `CLAUDE.md`: nova seção "Módulo Dados", bloco de comandos, e quaisquer quirks novos descobertos.
- `docs/ROADMAP_*.md`: marcar **PR9** ✅.
- Garantir persistência das chaves de config e dos `queries.json`.

---

## 5. Critérios de aceite (Definition of Done)

1. Consulta em português sobre 2 arquivos (join + filtro + agregação) retorna resultado correto, com cartão de revisão antes da execução.
2. Modo Consulta (SQL na mão) funciona com prévia.
3. Saída salva em `output/data/` nos 4+ formatos e aparece na Biblioteca.
4. Consulta não-SELECT é bloqueada por `validate.py`.
5. `data query`/`convert`/`profile` na CLI com paridade de comportamento.
6. Receita `data.query → ai.answer` executa de ponta a ponta.
7. `pytest -m unit` verde, `ruff` limpo, cobertura de core mantida (~alvo do projeto).

---

## 6. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Encoding de CSV no Windows | `charset-normalizer` + opção `encoding` do DuckDB; testes com CSV cp1252 |
| IA gera SQL errado/perigoso | Cartão de revisão obrigatório + `validate.py` (só SELECT) + conexão in-memory efêmera |
| Modelo local fraco em SQL complexo | Fallback Gemini; SQL sempre editável à mão |
| Prévia de tabela grande trava o Flet | Paginação `_PAGE_SIZE` + update escopado (padrão Biblioteca) |
| XLSX (extensão extra) | Isolar em `convert.py`; degradar com aviso se a extensão faltar |
| Escopo inflar ("Excel pior") | Manter query-first; `plot`/estágios em sub-PRs separados |

---

## 7. Ordenação sugerida

`Fase 0 → 1 (core+testes) → 2 (CLI) → 3 (GUI) → 4 (Receitas) → 5 (Biblioteca) → 6 (QA) → 7 (docs)`.
Cada fase entrega valor isolado e testável. Os checkpoints **context7** precedem toda escrita que dependa de API externa (DuckDB, Flet).
