# PR7.2 — Inspetor de Índice (RAG), botão "Indexar no RAG" e ETA da Transcrição

> Extensão do **PR7** (Módulo IA / RAG local). Sem dependência nova, **torch-free**.
> Reaproveita o core puro `src/core/rag/`, o `EventBus`/`CLIEventBus`, o design
> system e os padrões de worker já existentes. Faseado **PR7.2.0 → PR7.2.5**,
> **um commit por fase**.

## Contexto e motivação

Hoje o módulo IA só expõe do índice uma linha de status enxuta
(`view.py`): `28 documento(s) · 4.654 chunk(s) · atualizado 20:45`. O usuário
está "cego" quanto ao conteúdo do índice (quais documentos, quantos chunks por
documento, dimensão, modelo, tamanho em disco) e quanto à previsão de término de
uma transcrição longa na GUI. Esta extensão fecha essas lacunas:

1. **Estatísticas do índice no core** (puro, testável) — `index_stats()`.
2. **CLI `ai stats`** — expõe o item 1 no terminal.
3. **Linha de status com data completa** — `28 docs · 4.654 chunks · 20 jun 20:45`.
4. **Aba "Índice"** no módulo IA — inspetor rolável (cabeçalho global + tabela
   por documento + drill-down de chunks), separado do visor de respostas.
5. **Botão "Indexar no RAG"** nos painéis de resultado dos módulos produtores
   (Transcrição, Documentos→Analisar, Receitas) — indexação **por escolha**,
   disparada ao concluir um processamento (não automática).
6. **ETA na Transcrição** (GUI) — previsão de término abaixo da última linha
   transcrita.

### Decisões de produto já confirmadas com o usuário

- O inspetor do índice deve ser uma **aba separada** (padrão "abas manuais" do
  projeto), com rolagem própria, para **não disputar** com o visor de respostas.
- A linha de status deve ficar **curta**: `28 docs · 4.654 chunks · 20 jun 20:45`.
  As informações detalhadas vão **na aba** (item 4).
- O botão de indexar ao concluir deve ser uma **escolha (botão)** que **aparece
  quando o processamento termina**, **em cada módulo produtor**.
- Incluir também o comando **CLI `ai stats`** reaproveitando o mesmo core.
- ETA: implementar (a barra determinada já usa `end/audio_duration`, então o
  número já existe — falta exibir como tempo restante).

### Fora de escopo (registrado para o futuro)

- `large-v3-turbo` / `large-v3` **CPU-only com `threads=4`** — intenção futura;
  exigirá um override de device em `transcriber.py` (hoje `_resolve_device`
  auto-detecta CUDA). Não implementar agora.
- Troca para modelo de embedding **multilíngue** (`bge-m3`, `mxbai-embed-large`,
  1024-dim) — só se a recuperação em PT/cross-language se mostrar fraca; **exige
  reindexação completa** (dimensão muda 768 → 1024, índice atual fica
  incompatível). Não implementar agora.

## Princípios de arquitetura (herdados do projeto)

- **Core puro e testável**: toda lógica de estatística/formatação vai para
  `src/core/rag/` (sem Flet), com teste unit. A GUI **não é testável headless**
  (Flet) — as views ficam "burras" e consomem o core.
- **Convenção de idioma**: docstrings, logs, comentários e strings internas em
  **inglês**; apenas labels/textos visíveis da GUI em **português**.
- **`subprocess` em modo binário** (não aplicável aqui, mas manter a regra ao
  tocar qualquer core que chame binários).
- **Um commit por fase**; rodar `uv run pytest -m unit` e `uv run ruff` antes de
  fechar cada fase.

### Quirks do Flet 0.85 relevantes (ver skill `design-system`)

- **Sem `ft.Tabs`/`ft.Tab`** → abas manuais: `TextButton` + alternância de
  `visible=` num `ft.Stack` (padrão dos hubs no AppBar e do toggle Rodar|Construir
  em Receitas).
- **Listas grandes** → `ft.ListView` paginado + "Carregar mais" (padrão do modo
  lista da Biblioteca). **Nunca** renderizar 4.654 linhas de uma vez.
- **`is_available()` e leitura de disco fora da UI thread** (padrão `_refresh_status`
  em `ai/view.py`): rodar num `threading.Thread(daemon=True)` e fazer `update()`
  **escopado** (nunca `page.update()` em cascata).
- **Toast**: `page.open(ft.SnackBar(content=..., duration=...))`.
- **Modal**: `page.show_dialog(dlg)` / `page.pop_dialog()`.
- **Não existem** `ft.Colors.SURFACE_VARIANT`/`SURFACE_CONTAINER` — usar
  `ft.Colors.SURFACE` ou `Color.dark.surface_variant`.
- **`ft.Dropdown`** usa `on_select` (não `on_change`).
- Factories do DS: `secondary_button`, `action_button`, `summary_card`,
  `section_label`, `hairline`, `output_card`, `help_icon_for`, `spinner`,
  `log_line`; tokens `Color`, `Type`, `Space`, `Radius`, `IconSize`, `Layout`.

---

## Fase PR7.2.0 — Core: `index_stats()` + persistir o modelo de embedding

**Objetivo:** descrever o índice de forma pura e honesta, reutilizável por GUI e
CLI.

### Arquivos

- **Novo** `src/core/rag/stats.py`
- **Editar** `src/core/rag/store.py` — persistir sidecar com o modelo de embedding
- **Novo** `tests/core/rag/test_stats.py`

### `src/core/rag/stats.py`

Dataclasses `frozen=True, slots=True` (padrão do core RAG) e função pura:

```python
@dataclass(frozen=True, slots=True)
class DocStat:
    source_path: str
    kind: str            # transcription | document | image
    n_chunks: int
    mtime: float         # source mtime (from ChunkMeta.mtime)
    char_total: int      # soma de len(chunk.text) do documento

@dataclass(frozen=True, slots=True)
class IndexStats:
    n_docs: int
    n_chunks: int
    dim: int             # largura dos vetores (0 se índice ausente)
    embed_model: str     # do sidecar index_info.json; "?" se ausente
    disk_bytes: int      # vectors.npz + meta.json (+ index_info.json)
    updated_at: float | None  # mtime de vectors.npz; None se ausente
    per_doc: tuple[DocStat, ...]  # ordenado por n_chunks desc, depois nome

def index_stats(directory: Path) -> IndexStats:
    """Read the persisted index and summarize it. Pure, no Ollama/network."""
```

Implementação:

- Lê `meta.json` (lista de `ChunkMeta` serializado) → agrega por `source_path`
  para `per_doc` (`n_chunks`, `mtime`, `char_total`), conta `n_docs`/`n_chunks`.
- `dim`: carregar a shape de `vectors.npz` **sem** materializar a matriz inteira
  se possível (`np.load(...)["vectors"].shape[1]`); aceitável carregar — o índice
  pessoal é pequeno. `0` se ausente.
- `disk_bytes`: soma de `stat().st_size` dos arquivos presentes.
- `updated_at`: `(directory / "vectors.npz").stat().st_mtime` ou `None`.
- `embed_model`: lê de `index_info.json` (ver abaixo); `"?"` se ausente
  (índices criados antes desta fase).
- **Índice ausente** (sem `meta.json`): retorna `IndexStats` zerado
  (`n_docs=0, ...`, `per_doc=()`).

Helper de formatação **puro** (consumido pela GUI na Fase 3 e pela CLI na Fase 2):

```python
def fmt_status_line(stats: IndexStats) -> str:
    """'28 docs · 4.654 chunks · 20 jun 20:45' — PT month abbrev, dot thousands."""
```

- Milhar com **ponto** via formatação manual (`f"{n:,}".replace(",", ".")`).
- Mês abreviado em **PT-BR** via mapa manual (`_PT_MONTHS = ["jan", "fev", ...]`)
  — **não** depender de `locale`/`%b` (não garante "jun" em qualquer ambiente).
- Sem timestamp (índice vazio): `"Índice vazio"`.

### `src/core/rag/store.py`

No `persist(directory)`, **além** de `vectors.npz` e `meta.json`, gravar:

```python
(directory / "index_info.json").write_text(
    json.dumps({"embed_model": <modelo>, "dim": self.dim,
                "created_at": time.time()}, ensure_ascii=False),
    encoding="utf-8",
)
```

Como o `VectorStore` hoje **não conhece** o nome do modelo, há duas opções —
escolher a mais simples na implementação:

- **(A, recomendada)** adicionar um parâmetro opcional `embed_model: str | None`
  a `persist()` e passá-lo nos call sites (`ai/worker.py::run_ai_index` e
  `cli/ai.py::_build`), onde o modelo já é conhecido (`embed_model`/`DEFAULT_EMBED_MODEL`).
- (B) gravar o sidecar **fora** do store, nos dois call sites, após `persist()`.

Manter `dim` no sidecar permite, no futuro, detectar mismatch de dimensão
(quirk Ollama #10176) sem carregar a matriz.

> **Compatibilidade:** índices existentes não têm `index_info.json`. `index_stats`
> trata ausência como `embed_model="?"`. Nenhuma migração forçada — o sidecar
> nasce no primeiro reindex.

### Testes (`tests/core/rag/test_stats.py`, `@pytest.mark.unit`)

- Cria um `VectorStore` com vetores estreitos (dim 3–8) e N chunks de M fontes,
  `persist()` em `tmp_path`, chama `index_stats(tmp_path)` e assere
  `n_docs`/`n_chunks`/`dim`/`per_doc` (contagens e ordenação), `embed_model` lido
  do sidecar, `disk_bytes > 0`, `updated_at` não-nulo.
- Índice ausente (`tmp_path` vazio) → stats zerado, `per_doc == ()`.
- `fmt_status_line`: milhar com ponto (`3000 → "3.000"`), mês PT correto, ramo
  "Índice vazio".
- Padrão de mock de `index_dir`: `monkeypatch.setattr(Path, "home", classmethod(
  lambda cls: tmp_path))` **ou** passar `directory` explícito (preferir
  `directory` explícito nos testes de `stats`).

### Critério de aceite

- `uv run pytest tests/core/rag/test_stats.py -v` verde.
- `index_stats` 100% (ou ≥ 98%) em `--cov=src.core.rag.stats`.

---

## Fase PR7.2.1 — CLI `ai stats`

**Objetivo:** expor a Fase 0 no terminal, reaproveitando o core.

### Arquivos

- **Editar** `src/cli/ai.py`
- **Editar** `.claude/skills/cli/SKILL.md` (documentar o subcomando)
- **Editar** `tests/cli/test_ai_cli.py`

### `src/cli/ai.py`

- Adicionar sentinela `_STATS_CMD = "stats"` (mesmo padrão de `_INDEX_CMD`).
- Em `run_ai_cli`, **antes** do dispatch index/ask/batch:
  ```python
  if ns.query == _STATS_CMD:
      _stats()
      return
  ```
- `_stats()`:
  - `from src.core.rag.indexer import index_dir`
  - `from src.core.rag.stats import index_stats`
  - `stats = index_stats(index_dir())`
  - Índice vazio (`stats.n_chunks == 0`): imprime
    `'Índice vazio. Rode "uv run main.py ai index" primeiro.'` e retorna (sem
    `sys.exit`, pois `stats` é só leitura).
  - Senão imprime: cabeçalho (docs, chunks, dim, modelo, tamanho legível,
    atualizado em, caminho) + tabela por documento (nome · kind · #chunks · data).
  - `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` **já** é feito
    no topo de `run_ai_cli` — reaproveitar (nomes com `｜`).
- Atualizar a docstring do módulo e o `help` do positional `query` para
  mencionar `stats`.

### Testes (`tests/cli/test_ai_cli.py`)

- `_parse("stats")` → `ns.query == "stats"`, `callable(ns.func)`.
- Runner: `monkeypatch` `src.cli.ai.index_dir`/`index_stats` (ou
  `index_dir → tmp_path` com um índice real persistido) + `capsys`; validar que
  imprime as contagens e a tabela; ramo índice-vazio imprime a dica.

### Critério de aceite

- `uv run main.py ai stats` imprime o resumo do índice.
- `uv run pytest tests/cli/test_ai_cli.py -v` verde.

---

## Fase PR7.2.2 — Linha de status com data completa

**Objetivo:** `28 docs · 4.654 chunks · 20 jun 20:45`.

### Arquivos

- **Editar** `src/gui/modules/ai/view.py` (`_refresh_status`, ~linha 176–182)

### Mudança

- Substituir a construção atual da string pela chamada ao helper puro
  `fmt_status_line(stats)` da Fase 0. Para isso, `_refresh_status` passa a
  computar `stats = index_stats(index_dir())` (já roda **fora** da UI thread) em
  vez de ler `meta.json` à mão.
- Manter o ramo "indisponível" (`embedder.is_available` False) com o
  `SETUP_HINT`, como hoje.
- Reaproveitar `stats` para a aba da Fase 4 (mesma chamada).

> Sem teste novo (GUI). A lógica já está coberta em `test_stats.py`.

### Critério de aceite

- A linha de status mostra `… · 20 jun 20:45` (mês PT, milhar com ponto).

---

## Fase PR7.2.3 — Aba "Índice" no módulo IA (inspetor RAG)

**Objetivo:** painel rolável dedicado ao índice, separado do visor de respostas.

### Arquivos

- **Editar** `src/gui/modules/ai/view.py` (principal)
- (apoio) `src/gui/modules/ai/form_view.py` se necessário

### Estrutura do painel direito (hoje uma `ft.Column` única)

Transformar o `panel` num **toggle de abas manuais** `Conversa | Índice`:

- Cabeçalho do painel: `ft.Row` com dois `TextButton` (dourado no ativo — reusar
  o estilo de botão-hub, ou `action_button` com `accent=Color.PRIMARY`),
  alternando `visible=` de dois containers num `ft.Stack`.
- **Conversa** = exatamente o conteúdo atual (`status_row` + `hairline` +
  `progress_row` + `status_detail` + `session_area`). **Não** quebrar o
  `_on_event`/`_refresh_status`/`_on_ask` existentes.
- **Índice** = `ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)` com:
  - **Cabeçalho global** (`summary_card` + `section_label`): nº docs, nº chunks,
    dim (768), modelo de embedding, tamanho em disco (legível: KB/MB), caminho
    (`~/.mill-tools/rag/`, mono), atualizado em (data completa). Botão
    **Reindexar** pode ser reutilizado/duplicado aqui.
  - **Tabela agregada por documento** num `ft.ListView` **paginado**
    (`_PAGE_SIZE = 120` + "Carregar mais", como a Biblioteca): colunas
    `documento · kind · #chunks · data · tamanho`. Render **por documento**
    (de `stats.per_doc`), nunca por chunk. Truncar nome com `tooltip` do valor
    completo. Ícone de tipo por `kind`.
  - **Drill-down (opcional, v1 simples):** botão/linha "ver chunks" abre um
    `ft.AlertDialog` (`page.show_dialog`) listando os chunks daquele documento
    (preview de `text` + índice do chunk). Os textos vêm do `meta.json`; para o
    drill-down, ler os chunks do documento selecionado sob demanda (uma função
    auxiliar no core, ex. `chunks_for(directory, source_path) -> list[(idx, text)]`,
    pura e testável — **adicionar a `stats.py`** se o drill-down entrar no v1).
- **Carregamento fora da UI thread**: estender `_refresh_status` (ou um novo
  `_refresh_index_tab`) para preencher o cabeçalho e a tabela a partir do mesmo
  `index_stats`. Update **escopado** nos controles afetados (nunca `page.update()`
  global). Recalcular ao entrar na aba e após `index_done`/`task_done`.

### Persistência

- Opcional: `last_ai_tab` (`conversa|indice`) em `config.json` para lembrar a aba
  ativa. Não essencial.

### Testes

- Lógica de dados já coberta em `test_stats.py` (Fase 0). Se o drill-down usar
  `chunks_for`, adicionar teste unit dela. A view em si não é testável headless.

### Critério de aceite

- Toggle `Conversa | Índice` funciona sem quebrar a conversa.
- Aba Índice lista os documentos do índice com contagem de chunks, dim, modelo,
  tamanho e data; paginação funciona; drill-down (se incluído) abre o modal.

### Pontos a confirmar na implementação

- Reler a montagem exata de `panel`/`control` (`view.py` ~520–553) e do
  `form_view` para encaixar o toggle sem reatribuir `Container.content` (usar
  `visible=` num `Stack`).

---

## Fase PR7.2.4 — Botão "Indexar no RAG" nos módulos produtores

**Objetivo:** ao concluir um processamento que gera texto, oferecer indexação
**por escolha**, em cada módulo produtor.

### Arquivos

- **Novo** `src/gui/modules/ai/index_button.py` — factory compartilhado
- **Editar** painéis de resultado de:
  - **Transcrição** — `src/gui/views/result_view.py`
  - **Documentos → Analisar** — `src/gui/modules/document/view.py`
  - **Receitas** — `src/gui/modules/recipes/view.py`

### `index_button.py`

```python
def rag_index_button(page, *, on_started=None, on_finished=None) -> ft.Control:
    """Botão 'Indexar no RAG' (incremental). Dispara start_ai_index, mostra
    estado inline e um SnackBar ao concluir. Desabilita com tooltip quando
    embedder.is_available() é False (padrão _UNAVAILABLE)."""
```

Comportamento:

- Usa `secondary_button("Indexar no RAG", icon=ft.Icons.STORAGE_OUTLINED)`.
- No clique: cria um `EventBus`/`cancel_event` próprios (ou reaproveita o bus do
  módulo com `module_id="ai"` ignorado pelo `ProgressPanel` local) e chama
  `start_ai_index(bus, cancel_event, embed_model=<default/config>, on_finish=...)`
  (worker já existente; indexação **incremental** — pula inalterados).
- Estado inline: troca o label para "Indexando…" + desabilita; ao concluir,
  `page.open(ft.SnackBar(...))` ("Índice atualizado: +N chunks") e reabilita.
- **Gate de disponibilidade fora da UI thread**: checar `embedder.is_available()`
  num thread daemon; se False, botão desabilitado com `tooltip` = `SETUP_HINT`.
- Como o índice roda fora do módulo IA, **não** há `ProgressPanel` — o feedback é
  inline + toast; a aba Índice (Fase 3) reflete o resultado quando o usuário
  abrir a IA.

### Inserção nos painéis de resultado

- Mostrar o botão **somente quando há saída textual** indexável:
  - **Transcrição**: aba Transcrição/Análise/Digest concluída (`.txt`/`.md`).
  - **Documentos**: operação `analyze`/`extract`/`ocr` que gerou texto.
  - **Receitas**: quando algum `output_card` é texto (`.txt`/`.md`).
- Posicionar junto aos `output_card`/ações "Abrir pasta"/"Abrir arquivo".

### Persistência

- Opcional: lembrar preferência do usuário (ex. `rag_autoindex_hint_dismissed`).
  Não essencial no v1.

### Testes

- O disparo usa `start_ai_index` (worker já testado em
  `tests/gui/modules/ai/test_worker.py`). O factory é GUI — manter a lógica
  mínima; sem teste headless.

### Critério de aceite

- Ao concluir uma transcrição/análise/receita textual, aparece "Indexar no RAG";
  clicar indexa incrementalmente e mostra toast; desabilitado com dica quando o
  embedder está indisponível.

### Pontos a confirmar na implementação

- Ler `result_view.py` e os `view.py` de Documentos/Receitas para achar o ponto
  exato de inserção e o tipo de saída (oferecer só para saída textual).

---

## Fase PR7.2.5 — ETA na Transcrição (GUI) + ordem do tqdm na CLI

**Objetivo:** acabar com a cegueira de previsão de término na GUI; garantir que a
barra da CLI fique abaixo da última linha transcrita.

### Arquivos

- **Editar** `src/gui/views/progress_view.py`
- **Editar** `src/gui/modules/transcription/pipeline_log.py`
- (talvez) **Novo** helper puro de ETA (ex. em `pipeline_log.py` ou `eta.py`)
- **Editar** `tests/gui/modules/transcription/` (teste do helper de ETA)

### Cálculo (eventos já existentes — ver `transcriber.py`)

- `transcribe_started` → guardar `t0 = time.monotonic()` (wall clock de início).
- `language_detected` → guardar `audio_duration = payload["audio_duration"]`
  (= `info.duration`, pós-detecção; **não** usar `meta.duration`).
- `transcribe_segment` → `frac = end / audio_duration`;
  `eta = decorrido * (1 - frac) / frac`; `speed = end / decorrido` (× tempo-real).
- **Suavização**: só exibir após `frac >= 0.05` (ou após N segmentos) — o início
  é ruidoso (carga do modelo, VAD, primeiro beam).
- Exibir um rótulo **abaixo da última linha transcrita**:
  `"≈ 10 min restantes · 0,85× tempo-real"`. A barra determinada já usa
  `end/audio_duration` — é o mesmo número convertido em tempo.

### Helper puro (para teste unit)

```python
def format_eta(t0_elapsed: float, end: float, audio_duration: float) -> str | None:
    """Return 'restantes ~Xm Ys · Z× tempo-real' or None when too early/invalid."""
```

- Reutilizar `format_elapsed` (de `transcriber.py`) para o tempo restante.
- `None` quando `audio_duration <= 0` ou `frac < limiar`.

### CLI

- O tqdm interno de `transcriber.transcribe` já mostra `[decorrido<restante,
  velocidade]`. Garantir que os logs do pipeline saiam via `tqdm.write` (o
  `CLIEventBus` já faz isso) para a barra ficar colada no rodapé. **Provavelmente
  já funciona** — apenas confirmar e ajustar só se necessário (não introduzir
  regressão).

### Testes (`tests/gui/modules/transcription/`, `@pytest.mark.unit`)

- `format_eta`: entradas (decorrido, end, audio_duration) → string esperada;
  ramos `None` (cedo demais / duração inválida); arredondamento.

### Critério de aceite

- Durante uma transcrição na GUI, aparece um rótulo de tempo restante (após ~5%)
  abaixo da última linha transcrita, com fator de velocidade.
- `uv run pytest -k eta -v` verde.

---

## Ordem de execução e validação

1. **PR7.2.0** Core `index_stats()` + sidecar de modelo (fundação, testável).
2. **PR7.2.1** CLI `ai stats`.
3. **PR7.2.2** Linha de status com data completa.
4. **PR7.2.3** Aba "Índice" no módulo IA.
5. **PR7.2.4** Botão "Indexar no RAG" nos módulos produtores.
6. **PR7.2.5** ETA na Transcrição.

Em **cada** fase, antes de fechar o commit:

```bash
uv run pytest -m unit -v          # regra do projeto: unit verde antes de commit
uv run ruff check .               # linter
```

Para as fases com core novo, conferir cobertura do módulo tocado:

```bash
uv run pytest tests/core/rag/test_stats.py --cov=src.core.rag.stats --cov-report=term-missing
```

Alvo de cobertura por módulo novo: **≥ 90%** (idealmente 100% no `stats.py`,
seguindo o restante de `core/rag/`).

## Resumo de arquivos por fase

| Fase | Novos | Editados |
|---|---|---|
| 7.2.0 | `src/core/rag/stats.py`, `tests/core/rag/test_stats.py` | `src/core/rag/store.py` |
| 7.2.1 | — | `src/cli/ai.py`, `.claude/skills/cli/SKILL.md`, `tests/cli/test_ai_cli.py` |
| 7.2.2 | — | `src/gui/modules/ai/view.py` |
| 7.2.3 | — | `src/gui/modules/ai/view.py` (+ `form_view.py` se preciso) |
| 7.2.4 | `src/gui/modules/ai/index_button.py` | `src/gui/views/result_view.py`, `src/gui/modules/document/view.py`, `src/gui/modules/recipes/view.py` |
| 7.2.5 | (helper de ETA) | `src/gui/views/progress_view.py`, `src/gui/modules/transcription/pipeline_log.py`, testes em `tests/gui/modules/transcription/` |

## Atualização de documentação ao final

- Acrescentar uma entrada **PR7.2** na seção **Roadmap** do `CLAUDE.md`
  (resumo das 6 fases) e, se aplicável, atualizar a descrição do **Módulo IA**
  (aba Índice, status com data completa) e do **Módulo Transcrição** (ETA).
- Atualizar o `help_content.py` (chaves de ⓘ) caso a aba Índice ganhe ajuda.
