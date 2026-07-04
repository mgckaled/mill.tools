---
name: architecture
description: Guia de arquitetura e estrutura de código do mill.tools — camadas (core/cli/gui), regras de
  pureza e injeção de dependências, limites de tamanho e coesão por arquivo, padrões de decomposição
  (blocks/ · tabs/ · index_tab · pipeline_log · _state), fluxo de "adicionar feature de ponta a ponta"
  (core → extra/gate → CLI → GUI → testes) e como adicionar um módulo novo. Invocar ao criar/editar
  módulos, mover código entre camadas, decidir onde um arquivo novo deve morar, dividir arquivos grandes
  ou de baixa coesão, adicionar um extra opcional com gate, ou implementar qualquer plano do roadmap
  (docs/ROADMAP_ML_DADOS.md, docs/REFATORACAO_PREVIA.md). Para detalhes de subcomandos use a skill `cli`;
  de componentes/eventos de GUI use `design-system`; de testes use `testing` — esta skill orquestra e delega.
---

# mill.tools — Arquitetura e Estrutura de Código

Esta skill é o **orquestrador estrutural** do projeto. Ela define onde o código mora, quão grande pode ser
e como crescer sem desvirtuar do padrão. Os detalhes de cada domínio ficam nas skills irmãs:

- **`cli`** — subcomandos, argparse, `CLIEventBus`, testes de CLI.
- **`design-system`** — componentes de GUI, tokens, quirks do Flet 0.85, eventos `PipelineEvent`, thread-safety.
- **`testing`** — estrutura de testes, fixtures, mocks, cobertura.

Sempre que um detalhe pertencer a uma delas, **delegue** — não duplique aqui.

---

## 1. Princípios invioláveis

Estes são os contratos que não se quebram. Violação = revisão reprovada.

1. **`src/core/` é PURO** — sem `import flet`, sem estado de UI, sem `print`. Reutilizável por CLI e GUI.
   Se uma função de core precisa "avisar progresso", ela recebe um callback/emit por parâmetro — nunca
   conhece o `EventBus` nem o `page`.
2. **Injeção de dependências na fronteira de rede/modelo.** A única função que toca a rede/modelo é
   injetável, como `embed_fn` no RAG, `make_llm_fn` no `assess`, o motor no módulo Dados. O resto é
   unit-testável sem Ollama/DuckDB/ffmpeg.
3. **Idioma do código em inglês** — docstrings, logs, comentários, nomes. Português **só** em textos
   visíveis da GUI (labels). Ao tocar um arquivo com PT em docstring/log, corrigir para EN na mesma passagem.
4. **Logging via handler dedicado — nunca `print()`** para logs.
5. **`subprocess` sempre em modo binário** (sem `text=True`); decodificar com `.decode("utf-8", errors="replace")`.
6. **Degradação graciosa de extras** — recurso opcional ausente desabilita o card/flag com dica, nunca quebra.

---

## 2. Camadas: onde cada coisa mora e quem pode importar quem

```plaintext
src/
├── core/   PURO — lógica reutilizável (audio · video · image · document · library · rag · recipes · data · [ml])
├── cli/    1 módulo por subcomando + bus.py (CLIEventBus)
└── gui/    camada Flet — app · home · modules/ · views/ · components/ · theme/
```

**Regra de importação (direção única):**

| Camada  | PODE importar                      | NUNCA importa                                                                    |
| ------- | ---------------------------------- | -------------------------------------------------------------------------------- |
| `core/` | outros `core/`, stdlib, libs puras | `gui/`, `cli/`, `flet`                                                           |
| `cli/`  | `core/`, `cli/bus.py`              | `gui/` (exceto reusar `gui/modules/<m>/worker.py` puro, que não depende de Flet) |
| `gui/`  | `core/`, `gui/*`                   | —                                                                                |

> O worker (`gui/modules/<m>/worker.py`) **não depende de Flet** — emite por `bus.emit(...)`. Por isso a CLI
> pode reusá-lo. Mantenha-o assim: lógica de orquestração + emit, zero controles Flet.

**Superfícies de evento (não misturar):**

- CLI → `CLIEventBus` (tqdm), `install_log_handler=False`. Ver skill `cli`.
- GUI → `PipelineEvent(type, stage, payload, module_id)` via `page.pubsub`. Ver skill `design-system`.

Antes de criar um arquivo, pergunte: **"isto é lógica pura?"** Se sim, vai em `core/`. Só amarração de UI
vai em `gui/`. Só tradução de `Namespace`→Args vai em `cli/`.

---

## 3. Limites de tamanho e coesão

A régua combina **tamanho** e **coesão** — os dois sintomas juntos é que reprovam (ver
`docs/REFATORACAO_PREVIA.md`).

| Tipo de arquivo                                  | Alvo         | Teto (refatorar acima) |
| ------------------------------------------------ | ------------ | ---------------------- |
| Builder de GUI (`build_X_module`/`build_X_view`) | ≤ 400 linhas | ~500                   |
| Módulo de `core/`                                | ≤ 300 linhas | ~400                   |
| Worker / form_view                               | ≤ 350 linhas | ~450                   |

**Coesão (vale mesmo abaixo do teto):** um arquivo = **uma** responsabilidade. Sinais de baixa coesão que
exigem divisão independentemente do tamanho:

- Uma função-builder com muitas closures cobrindo **abas/seções distintas** (ex.: o antigo
  `data/view.py` com 47 closures e 3 abas).
- Um arquivo que reúne adaptadores/handlers de **vários módulos** (ex.: o antigo `recipes/registry.py`
  com 33 adaptadores de 7 módulos).
- Comentários de seção (`# ----`) que claramente separam "mundos" diferentes no mesmo arquivo.

**Regra operacional "divide-se ao tocar":** não refatore preventivamente a base inteira (isso é retrabalho).
Divida um arquivo grande **no momento** em que um plano for estendê-lo, ou quando ele já estourou o teto hoje.

---

## 4. Padrões de decomposição já consagrados no projeto

Não invente padrão novo — estes já existem e são testados. Ao dividir, use o que couber:

| Padrão                                                                                     | Onde já existe                                                        | Quando usar                                           |
| ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- | ----------------------------------------------------- |
| **`blocks/`** — `build_X_block(page) → (ft.Column, XRefs)` (XRefs = NamedTuple de `get_*`) | `gui/modules/image/blocks/`, `document/blocks/`                       | Quebrar um formulário grande em blocos independentes  |
| **`tabs/`** — `build_X_tab(...) → (controle, refs/handlers)`                               | proposto p/ `data/view.py` (`query_tab`/`preview_tab`/`analysis_tab`) | Quebrar um painel multi-aba                           |
| **`index_tab.py`** — uma aba extraída para arquivo próprio                                 | `gui/modules/ai/index_tab.py`                                         | Aba pesada/autônoma dentro de um hub                  |
| **`_state.py`** — estado transversal compartilhado entre abas/blocos                       | proposto p/ `data/` (cronômetros, `_scoped_update`, seleção de fonte) | Estado que várias abas dividem                        |
| **`pipeline_log.py`** — separa "o que emitir" (`fmt_*`) de "como exibir" (`resolve_*`)     | todos os módulos                                                      | Sempre que houver eventos/log de pipeline             |
| **`registry/<módulo>.py`** + `__init__` que monta o registro                               | proposto p/ `recipes/registry/`                                       | Coleções de adaptadores/handlers de múltiplos módulos |

Princípio comum: cada sub-builder **devolve o controle e seus acessores/handlers**; o builder principal só
monta o estado compartilhado e encaixa as partes. O builder principal deve ficar enxuto (centenas, não milhares).

---

## 5. Adicionar uma feature de ponta a ponta (checklist)

Toda feature nova nasce com as duas interfaces e segue esta ordem. Marque cada item:

1. **Núcleo puro** em `src/core/<área>/` — função(ões) sem Flet, com a dependência de rede/modelo
   **injetável**. Docstrings em EN.
2. **Dependência nova?** → extra opcional no `pyproject.toml` (`[ml]`, `[ml-audio]`, …) + **import preguiçoso**
   (dentro da função, não no topo) + **gate** `is_available()` no padrão de `embedder.is_available()` /
   `ocr.is_available()`.
3. **Cache?** → `~/.mill-tools/...`, chaveado por `(path, mtime)`, no padrão de `data_assessments.json`.
4. **CLI** — subcomando ou flag novo seguindo a skill `cli` (parser + runner; `CLIEventBus` se houver progresso;
   `install_log_handler=False`; UTF-8 no stdout se imprimir nomes de arquivo).
5. **GUI** — nova operação/aba seguindo a skill `design-system` (worker emite com `module_id` correto;
   eventos no padrão das tabelas de `PipelineEvent`; regra de ouro do spinner; abas manuais `visible=`).
6. **Testes** — espelhar `src/` em `tests/`, `@pytest.mark.unit`, mocks no padrão da skill `testing`.
   Lógica pura ganha teste; amarração Flet não é testável headless → extrair a lógica pura para testá-la.
7. **Saídas** — gravar no dir canônico do módulo sob `output/` (alimenta Biblioteca e RAG).
8. **Verde antes de commitar** — `uv run pytest -m unit` + `ruff` limpos.

Se a feature **não couber** em nenhum módulo existente, vá para a seção 6.

---

## 6. Adicionar um módulo novo de GUI

`MODULES` (em `gui/app.py`) é fonte única — adicionar módulo = **uma entrada** na lista. Passos:

1. Pasta `gui/modules/<novo>/` com o padrão: `form_view.py` · `worker.py` · `view.py` · `pipeline_log.py`
   (e `blocks/`/`tabs/` se o formulário/painel for grande — ver seção 4).
2. Uma `Module` (dataclass de `modules/base.py`): `id/label/icon/selected_icon/control/on_mount/on_unmount`.
   O `control` é construído **uma vez** (trocar de aba não destrói estado).
3. `navigate_to(module_id, payload)` alterna **visibilidade** num `ft.Stack` (nunca reatribui `content` —
   quebra o patcher do Flet 0.85).
4. Escopo de eventos: o painel ignora `module_id` ≠ `owner_id`. Hubs são auto-contidos.
5. CLI correspondente (skill `cli`) + testes (skill `testing`).

Ferramenta entra na `NavigationRail`; hub entra no `AppBar` (excluído de `_RAIL_MODULES` via `_HUB_IDS`).

---

## 7. Convenções de dependências e extras

- Dependência pesada/opcional → **extra** no `pyproject.toml`, nunca no base. Núcleo clássico de ML: `[ml]`;
  extração de mídia mais pesada: extras próprios (`[ml-audio]`, `[ml-image]`), como `[ai-image]`/`[ocr]` hoje.
- **Import preguiçoso** sempre (carregar só ao acionar o recurso) — preserva a partida rápida.
- **Tipar dependência opcional sem importá-la em runtime**: com `from __future__ import annotations`,
  importe-a sob `if TYPE_CHECKING:` — as anotações nunca são avaliadas e o runtime continua sem o import.
  Padrão em `core/data/frames.py` e `core/data/engine.py` (polars/pandas/pyarrow do extra `[analysis]`).
- **Gate** `is_available()` resolve a dependência (pacote + binário/serviço) e o card/flag desabilita com dica.
- Linhas impossíveis de cobrir sem desinstalar dependências → `# pragma: no cover` (ver skill `testing`).

---

## 8. Checklist de revisão (antes de commitar)

- [ ] `core/` tocado continua **puro** (sem Flet/`print`); dependência de rede/modelo **injetável**.
- [ ] Nenhum arquivo novo/editado passou do teto da seção 3; baixa coesão → dividido pelo padrão da seção 4.
- [ ] Builder de GUI grande foi quebrado em `blocks/`/`tabs/` em vez de inchar.
- [ ] Extra opcional + import preguiçoso + gate, se houver dependência nova.
- [ ] CLI **e** GUI cobertas; eventos com `module_id` certo.
- [ ] Testes espelham `src/`; `uv run pytest -m unit` verde; `ruff` limpo.
- [ ] Docstrings/logs/comentários em EN nos trechos tocados (PT→EN oportunista).
- [ ] Saídas no dir canônico sob `output/`.

---

## 9. Ao implementar os planos do roadmap

Para `docs/ROADMAP_ML_DADOS.md`, esta skill é o ponto de partida de cada plano:

- **Plano −1 (refatoração prévia)** — aplicar a seção 4 a `data/view.py` (→ `tabs/`) e `recipes/registry.py`
  (→ `registry/<módulo>.py`); fixar a regra da seção 3 no `CLAUDE.md`. Ver `docs/REFATORACAO_PREVIA.md`.
- **Plano 0 (fundação de dados) ✅** — `core/data/frames.py` é a **única fronteira de DataFrame** (espelha o
  `engine.py`): Polars no miolo, pandas só na borda (`to_pandas`), handoff **Arrow zero-copy** via
  `engine.run_query_arrow`. polars/pandas/pyarrow só sob `TYPE_CHECKING` (extra `[analysis]`); o `engine`
  segue DuckDB-puro e a GUI só fala `QueryResult`. Ver `docs/PLANO_0_FUNDACAO_DADOS.md`.
- **Plano 1 (gráficos) ✅** — apenas **consome** o `frames` (gráfico = `to_pandas`→matplotlib→**PNG** num `ft.Image`).
- **Plano 2 (painéis dos hubs) ✅** — núcleos de agregação puros, um por hub (`core/library/analytics.py` ·
  `core/rag/analytics.py` · `core/recipes/history.py`), devolvendo métricas + `QueryResult`; **números em stdlib**
  (sem extra), **gráfico opcional** via o helper de GUI `gui/modules/_charts.py` (`QueryResult`→PNG, gated). Painéis
  como **modo/aba novo** (seção 4), dividindo ao tocar (`library/analytics_panel.py`, `ai/analytics_tab.py`,
  `recipes/history_tab.py`) — sem inflar os builders. Histórico de Receitas: persistência nova efeito-colateral da
  **orquestração** (worker/CLI gravam `RunRecord` no evento terminal); o `runner` puro fica intocado.
  Ver `docs/PLANO_2_PAINEIS_HUBS.md`.
- **Plano 3 (fundação de ML) ✅** — pacote puro `core/ml/` espelhando `core/rag/`: acessor de embeddings
  (`features.py`, **numpy-puro**) que faz mean-pool do `VectorStore` em vetores de documento (única decisão
  de pooling/normalização, herdada pelos consumidores); dedup por cosseno (`dedup.py`, prova de vida);
  gate `[ml]` (`deps.is_available`) e persistência de modelos versionada por `sklearn.__version__`+signature
  (`store.py`, invalida no mismatch — joblib v1). Acessor/dedup **não** gateiam (só os algoritmos do Plano 4/5).
  CLI `ai dups`; GUI deferida ao Plano 4. Ver `docs/PLANO_3_FUNDACAO_ML.md`.
- **Plano 4A (semântico não-supervisionado) ✅** — só geometria de embeddings, reusa `features.document_matrix`
  (Plano 3) e o `charts` (Plano 1). Núcleo `core/ml/`: `cluster` (HDBSCAN/k-means), `labeling` (c-TF-IDF),
  `project` (PCA default / UMAP sob `[ml-viz]`), `recommend` (related/in_corpus, **numpy-puro, sem gate**),
  `cache` (mapa versionado por `corpus_signature`), `mapviz` (orquestra → PNG). `charts` ganhou
  `render_category_scatter` (**estendido, não duplicado** — segue a única fronteira matplotlib). GUI: Biblioteca
  modo **Mapa** (`semantic_map_panel.py`, "divide-se ao tocar" — `view.py` só pluga no Stack) + aviso de
  fora-de-escopo na IA; CLI `ai topics`/`map`/`related`. Nenhuma dep obrigatória nova (só `[ml-viz]`).
  Ver `docs/PLANO_4A_SEMANTICO.md`.
- **Plano 4B (supervisionado + textual) ✅** — a camada que precisa de **rótulo** ou de **NLP textual**.
  `core/ml/classify.py` (zero-shot por protótipo de perfil → supervisionado `LinearSVC`+`CalibratedClassifierCV`
  conforme rótulos chegam; reusa `features`/`store`). Pacote novo `core/text/` (puro, **independente do
  `core/ml`**): `keywords` (YAKE), `summarize` (TextRank self-contained sobre `TfidfVectorizer`), `entities`
  (spaCy NER CNN, gate de pacote+modelo como o Tesseract), `reader`/`lang`. Extra `[nlp]`; resumo/classificação
  sem dep nova. "Divide-se ao tocar" aplicado: `form_view` fatiado (`form_env`/`profile_section`), Insights como
  `insights_panel`, auto-tags em `core/library/tags.py` + `filter_items(tag_index=…)`. Rótulo de ouro capturado
  pelo **worker** (`record_label`), nunca por etapa de rotulagem dedicada. CLI `ai classify/keywords/summary/
  entities`. Entrega os motores que o **Plano 4C** vai compor. Ver `docs/PLANO_4B_SUPERVISIONADO_TEXTUAL.md`.
- **Planos 4C–7** — cada feature pela seção 5; ao tocar `ai/view.py`/`library/view.py`/builder de Receitas,
  **dividir ao tocar** (seção 3) antes de adicionar a aba/recurso.
- **Novas features de ML — Tier A ✅** — busca híbrida (BM25+RRF, `rank-bm25` **base**, não atrás de extra —
  a busca densa do RAG já é incondicional); outliers tabulares (`core/data/ml.py`, `IsolationForest`);
  dedup de imagens via **dHash hand-rolled** (`core/image/dhash.py`, zero dep — correção em relação ao
  plano original, que cogitava o pacote `imagehash`/scipy); `classify.py` **parametrizado por `domain`**
  (mesmas funções, chaveadas por prefixo de arquivo — domínio default preserva os nomes pré-existentes,
  zero invalidação de cache). **Novo pacote `core/observatory/`** (puro, cross-módulo: `activity.py` log
  append-only + `status.py` agregador read-only) e **4º hub GUI** (`gui/modules/observatory/`) — promovido
  de "aba de outro hub" para hub próprio ao aplicar a própria definição de hub desta skill ("opera sobre
  as saídas de todos os módulos"): a superfície cobre RAG/Biblioteca/Transcrição/Dados/Receitas, não só
  um deles. Stepper reusável (`gui/modules/_stepper.py`) + hook `mapviz.build_semantic_map(on_stage=…)`
  prontos; wiring nas 3 telas de origem (RAG/Mapa/Insights) requer ponte thread-safe (`page.pubsub`) por
  causa de `asyncio.to_thread` — deixado para uma passagem dedicada. CLI `observatory status/activity`,
  `library dedup-images`, `data outliers`. Ver `docs/plan/PLANO_ML_NOVAS_FEATURES.md`.
  - **Fast-follow — GUI write-through + Status ampliado ✅** — fechou o gap em que só a CLI gravava em
    `log_activity` (a aba Atividade ficava vazia para quem só usa a GUI): `views/profile_section.py` e
    `gui/workers.py` passaram a gravar eventos de auto-sugestão/confirmação de perfil. Novo
    `core/observatory/logs.py` (mesmo padrão de `activity.py`, cap 100) alimentado por um **hook central**
    em `gui/events.py::EventBus.emit()` — todo `task_error` da GUI (exceto cancelamentos) vira uma entrada,
    sem tocar nenhum `worker.py` — prova de que o `page.pubsub.send_all()` já é um broadcast page-wide (o
    mesmo mecanismo que `app.py::_on_pipeline_cursor` já usava). `status.py` ganhou `ollama_inventory()`
    (consulta `ollama.Client().list()` — pacote promovido a dependência direta), `binary_statuses()`
    (`shutil.which` + o resolvedor de Tesseract existente), `cloud_provider_statuses()` (reusa
    `llm_factory._load_env_once()`, mesmo precedente de `core/data/nl2sql.py` importando `llm_factory`
    direto de `core/`) e 4 gates novos (`[ocr]`/`[ai-image]`/`[analysis]`/`[data-plot]` — dois deles não
    tinham `SETUP_HINT` ainda). Hub reordenado para Status primeiro (visão de conjunto antes do feed).
  - **Fast-follow 2 — perf fix + Índice/RAG aninhado ✅** — a aba Status travava a UI por 7-12s (leituras
    síncronas na UI thread: cold-import de vários extras opcionais + `ollama.Client().list()` sem
    timeout); movidas p/ thread daemon (mesmo padrão já provado em `ai/view.py::_refresh_status`) com
    placeholder "Carregando…" + `Client(timeout=5)`. Separação estrutural aplicando a seção 4 desta
    skill um nível mais fundo: Índice e Painel saíram do hub de IA (que agora é só Conversa,
    `ai/view.py` perdeu a maquinaria de abas) e viraram uma aba **aninhada** "Índice/RAG" no
    Observatório — mesmo padrão `Row(TextButton)+Stack` do nível de topo, repetido dentro de um único
    `(control, apply)` (`observatory/rag_tab.py`), sem suporte especial do framework nem necessário.
    3 sub-abas: Índice/Painel (relocados, arquivos renomeados — `analytics_tab.py` →
    `rag_analytics_tab.py` — não reescritos) + **Uso de disco** (nova, `core/observatory/
    disk_usage.py` — scanner genérico de `~/.mill-tools/`, agora incluindo `rag/`). "Reindexar" na
    aba Índice não roda pipeline no Observatório (que segue read-only) — bridgeia via `nav` pro hub
    de IA, que dispara o reindex ao montar com `{"trigger_reindex": True}`. Índice/RAG é a nova
    aba padrão/primeira. CLI ganhou `observatory disk-usage`.
