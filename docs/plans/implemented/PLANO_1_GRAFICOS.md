# Plano 1 — Gráficos (realiza o PR9.1) — plano de implementação

**Documento de execução — plano de implementação detalhado**
Data: 23 de junho de 2026 · Roadmap de origem: `docs/ROADMAP.md` (Plano 1 / PR9.1) · Fundação: `docs/plans/implemented/PLANO_0_FUNDACAO_DADOS.md` (✅ entregue) · Padrão de referência: skill `architecture`

> **Invocação da skill.** Ao executar, **invoque a skill `architecture`** (`.claude/skills/architecture/SKILL.md`) e siga-a: núcleo puro (§1), camadas (§2), limites de tamanho/coesão (§3), decomposição em `tabs/` (§4), fluxo core → extra/gate → CLI → GUI → testes (§5), tipar dependência opcional sob `TYPE_CHECKING` (§7) e checklist (§8). Este plano é a aplicação concreta daquele guia ao PR9.1.

> **Alinhamento com o Plano 0 (commits `6a31314`, `5e3ef4a`, `a4f44be`).** Os gráficos são o **primeiro consumidor real** da fundação: usam `frames.to_pandas` (borda matplotlib) e o caminho zero-copy `engine.run_query_arrow → frames.from_arrow`. O extra `[analysis]` (polars/pandas/pyarrow) já existe; este plano acrescenta `[data-plot]` (matplotlib). O contrato de GUI (`QueryResult`) e a regra "nenhum DataFrame cruza para a GUI" continuam valendo.

---

## Sumário

1. Objetivo e escopo
2. Achados da varredura web (e como influenciam o desenho)
3. Decisões de arquitetura
4. O desenho: `core/data/charts.py` (único ponto matplotlib)
5. Reuso da fundação do Plano 0
6. GUI: a aba `tabs/plot_tab.py` + 4ª aba + worker + eventos
7. CLI: subcomando `data plot`
8. Dependências (extra `[data-plot]`, gate, lazy, `TYPE_CHECKING`)
9. A ideia inteligente: gráfico fluido na GUI sem atrapalhar
10. Passos de implementação (commits ordenados)
11. Testes
12. Critérios de aceitação
13. Riscos e o que **não** fazer agora
14. O que destrava / relação com o roadmap

---

## 1. Objetivo e escopo

Adicionar visualizações ao módulo Dados: a partir do resultado de uma consulta, gerar um gráfico (barras, linha, histograma, dispersão), exibi-lo na GUI e salvá-lo como artefato. É o item `plot` já previsto no roadmap (PR9.1), assentado diretamente sobre a fundação do Plano 0.

**No escopo:** um núcleo puro `src/core/data/charts.py` (a única fronteira com o matplotlib), a aba `tabs/plot_tab.py`, a quarta aba no `view.py`, o par `run_data_plot`/`start_plot` no worker, os eventos correspondentes, o subcomando `data plot` na CLI, o extra `[data-plot]` e os testes. **Fora do escopo:** ML (Plano 5), painéis dos hubs (Plano 2), gráficos interativos/Altair. Quatro tipos de gráfico no v1; pizza fica deliberadamente de fora (má prática para comparação).

---

## 2. Achados da varredura web (e como influenciam o desenho)

**Renderizar matplotlib fora da UI thread exige a API orientada a objetos (não o `pyplot`).** O backend `Agg` permite trabalhar em figuras separadas em threads separadas, mas o `pyplot` mantém estado global e **não é thread-safe**. *Influência:* o `charts.py` usará `matplotlib.use("Agg")` + `Figure()` + `FigureCanvasAgg` diretamente, nunca `plt.*` — porque o render roda numa thread daemon do worker (como DuckDB/LLM já fazem).

**O Flet tem um controle nativo `MatplotlibChart`, mas ele re-desenha a figura a cada `page.update()` (custo de performance) e teve bugs reportados; a alternativa é exportar a figura e exibi-la como imagem.** *Influência:* **não** usaremos o `MatplotlibChart` — seu re-desenho a cada `update` conflita diretamente com a disciplina de **update escopado** e a **regra de ouro do spinner** do módulo (skill `design-system`). Em vez disso, renderizamos a figura para **bytes PNG** e exibimos num `ft.Image` (que no Flet 0.85 aceita `Union[str, bytes]`) — exatamente o padrão já usado para waveform e thumbnails. Mais previsível, sem re-desenho parasita, e ainda gera um artefato salvável.

**A escolha automática de tipo de gráfico é, na prática, uma heurística por tipo de coluna** (categórica no eixo x → barras; temporal/ordenada → linha; uma coluna numérica → histograma; duas numéricas → dispersão), considerando também o número de linhas/variáveis. *Influência:* o `charts.py` terá um `suggest_spec(...)` puro que propõe o gráfico a partir do esquema do resultado, dando ao usuário um gráfico sensato com um clique e permitindo sobrepor (tipo/x/y).

Fontes na seção final.

---

## 3. Decisões de arquitetura

**`charts.py` é a única fronteira com o matplotlib** — espelhando `engine.py` (única fronteira DuckDB) e `frames.py` (única fronteira de DataFrame). Só ele importa matplotlib, sempre de forma preguiçosa, com `Agg` + API OO. O resto do projeto nunca toca o matplotlib.

**Gráfico vira PNG, não objeto de plotagem.** A GUI recebe **bytes PNG** (via evento) e os exibe num `ft.Image`; o contrato de eventos ganha apenas `data_plot_*`. Nenhuma figura matplotlib nem DataFrame cruza para a camada Flet.

**Reuso da fundação do Plano 0.** Para fidelidade, o gráfico é renderizado sobre o **resultado completo** da consulta (não a prévia truncada de 200 linhas): o worker re-executa via `engine.run_query_arrow` (zero-copy) → `frames.from_arrow` → `frames.to_pandas` → `charts.render_png`. Este é o primeiro uso real do caminho Arrow entregue no Plano 0.

**Paradigma query-first: sem agregação escondida.** O módulo Dados compõe na consulta ("total por cliente" já agrega no SQL). O gráfico, portanto, **plota o resultado como está** — não re-agrega por baixo dos panos. Isso mantém a coerência do módulo e o gráfico previsível: o que você vê na tabela é o que vira gráfico.

**Extra `[data-plot]` (matplotlib), com gate e import preguiçoso** (skill `architecture` §7), na convenção de `[analysis]`/`[ai-image]`. Plotar exige `[analysis]` (para o frame) **e** `[data-plot]` (para o matplotlib); ausente qualquer um, a aba Gráfico desabilita com dica.

---

## 4. O desenho: `core/data/charts.py` (único ponto matplotlib)

Arquivo novo, puro, ≤ ~280 linhas (teto de core na skill `architecture`). API proposta:

| Símbolo | Assinatura | Papel |
|---|---|---|
| `is_available()` | `() -> bool` | Gate: matplotlib importável. Lazy. Espelha `frames.is_available()` |
| `ChartSpec` | dataclass `kind, x, y, title` (kind ∈ {`bar`,`line`,`hist`,`scatter`}) | Especificação pura do gráfico |
| `ChartPalette` | dataclass `bg, fg, accent, grid, muted` (defaults neutros) | Cores; a GUI passa as do tema escuro — mantém o core sem importar tokens da GUI |
| `suggest_spec(schema)` | `(list[tuple[str, str]]) -> ChartSpec` | Heurística: a partir de `(coluna, tipo)` propõe kind + x/y |
| `render_png(df, spec, *, palette=...)` | `("pd.DataFrame", ChartSpec, ChartPalette) -> bytes` | **Único ponto matplotlib.** `Figure`+`FigureCanvasAgg` (sem `pyplot`), desenha conforme `spec`, devolve PNG |

Princípios: `render_png` recebe um **pandas DataFrame** (a borda já convertida por `frames.to_pandas`) — assim `charts.py` não importa Polars; importa só matplotlib (lazy) e usa pandas pela tipagem. `Figure`/`FigureCanvasAgg` diretos (thread-safe); nada de `plt.*`. As cores chegam por `ChartPalette` (a GUI injeta o tema escuro; o core tem defaults), mantendo o núcleo livre de `src.gui`. Tipagem de matplotlib/pandas sob `TYPE_CHECKING`. Docstrings em inglês.

`suggest_spec` (puro, muito testável) aplica a heurística da varredura: uma coluna categórica + uma numérica → `bar`; coluna temporal/ordenada + numérica → `line`; uma única numérica → `hist`; duas numéricas → `scatter`; sem coluna numérica → cai para `bar` de contagem ou retorna um `ChartSpec` "indecidível" que a GUI traduz em dica.

---

## 5. Reuso da fundação do Plano 0

O fluxo de geração reaproveita exatamente o que o Plano 0 entregou, sem duplicar nada:

1. `engine.run_query_arrow(files, sql)` → `pyarrow.Table` (zero-copy; entregue no commit `5e3ef4a`).
2. `frames.from_arrow(table)` → `pl.DataFrame`.
3. `frames.to_pandas(df)` → `pd.DataFrame` (a borda matplotlib, ponto único de pandas).
4. `charts.render_png(pdf, spec, palette=...)` → `bytes`.

Para resultados já em memória/pequenos, o caminho por linhas (`frames.to_polars(result)`) também serve; mas o caminho Arrow é o preferido para fidelidade sobre o resultado completo. O esquema para `suggest_spec` sai dos dtypes do frame Polars (`df.schema`), sem inferência manual.

---

## 6. GUI: a aba `tabs/plot_tab.py` + 4ª aba + worker + eventos

Segue o padrão de decomposição que o Plano −1 deixou pronto (uma aba = um arquivo).

**`tabs/plot_tab.py` — `build_plot_tab(ctx) -> PlotTab`.** Recebe o `DataViewContext` (já compartilha o resultado/efetivo SQL/arquivos entre abas). Conteúdo: controles compactos (dropdown de tipo + seletores de coluna x/y, pré-preenchidos por `suggest_spec`), botão "Gerar gráfico", um `ft.Image` para o PNG e um botão "Salvar PNG". Empty state quando não há resultado. Expõe `view`, `on_enter()` (pré-seleciona a partir do resultado atual) e os handlers `data_plot_*`.

**`view.py` (casca, 239 linhas) — adicionar a 4ª aba.** Incluir o `TextButton` "Gráfico", estender `_show_tab` para `"plot"` (alterna `visible=` no `Stack`, chama `plot.on_enter()`), e rotear os eventos `data_plot_*` para o handler da aba. São adições pequenas e localizadas — não inflam o `view.py` porque a lógica vive em `plot_tab.py` (padrão `tabs/`).

**`worker.py` — `run_data_plot` + `start_plot`** (par, como os demais `run_*`/`start_*`). `run_data_plot(bus, files, sql, spec, palette)` roda numa thread daemon (`_spawn`): `run_query_arrow → from_arrow → to_pandas → render_png`, salva o PNG em `output/data/` e emite `data_plot_done` com os bytes + caminho. Gate antes (matplotlib + frames disponíveis) → senão `data_plot_error` com `SETUP_HINT`.

**Eventos** (acrescentar às tabelas do design-system, `module_id="data"`): `data_plot_start`, `data_plot_done` (`png: bytes`, `output_path`), `data_plot_error` (`message`). O handler de `data_plot_done` roda na UI thread (callback do pubsub), seta `image.src = png` e faz **update escopado** (não `page.update()` global, para não interromper o spinner — regra de ouro). Spinner durante o render segue a regra de ouro (`page.update()` antes de `start()`).

Arquivos **intocados**: `query_tab.py`, `preview_tab.py`, `analysis_tab.py`, `table_view.py`, `form_view.py`. `_state.py` ganha, no máximo, um campo de cache do último PNG, se necessário.

---

## 7. CLI: subcomando `data plot`

Paridade CLI/GUI (skill `architecture` §5; skill `cli`). Reusa o core direto, sem `CLIEventBus`:

```bash
uv run main.py data plot <arquivos...> "<pergunta|SQL>" [--sql] [--kind bar|line|hist|scatter] [--x COL] [--y COL] [--out grafico.png]
```

`run_data_cli` ganha o ramo `plot`: resolve a consulta (reusa `_query`/`nl2sql`), roda `run_query_arrow → from_arrow → to_pandas`, monta o `ChartSpec` (de `--kind/--x/--y` ou `suggest_spec`) e grava o PNG via `charts.render_png` em `output/data/`. Gate com mensagem clara se faltar o extra.

---

## 8. Dependências (extra `[data-plot]`, gate, lazy, `TYPE_CHECKING`)

```toml
[project.optional-dependencies]
data-plot = ["matplotlib>=3.8"]
```

Plotar requer `[analysis]` (frame) **e** `[data-plot]` (matplotlib): `uv sync --extra analysis --extra data-plot`. O `charts.is_available()` checa matplotlib; a aba/flag só habilita com ambos (`frames.is_available() and charts.is_available()`). Import de matplotlib é function-local; a tipagem fica sob `TYPE_CHECKING` (padrão fixado na skill `architecture` §7 no Plano 0). A base segue mínima.

---

## 9. A ideia inteligente: gráfico fluido na GUI sem atrapalhar

Três decisões mantêm a tradução para a interface tão simples quanto a de hoje.

**O gráfico trafega como PNG, renderizado fora da UI thread.** O worker usa `Figure`+`FigureCanvasAgg` (Agg, sem `pyplot` — thread-safe) numa thread daemon e emite `data_plot_done(png, path)`; a UI só troca o `src` de um `ft.Image`. Nada de figura matplotlib viva na árvore Flet, nada de `MatplotlibChart` re-desenhando a cada `update`. É o mesmo padrão de bytes da waveform e dos thumbnails — previsível e já validado no projeto.

**O gráfico nasce com o tema da GUI.** A GUI injeta uma `ChartPalette` com as cores do tema escuro (fundo, dourado de acento, grade), de modo que o gráfico combine com a interface — sem o core importar tokens da GUI (as cores chegam por parâmetro).

**O gráfico é um artefato real.** O PNG é salvo em `output/data/`, então fica acessível pela Biblioteca e reaproveitável fora do app. (Nuance menor: a Biblioteca hoje classifica `output/data/` como `kind="data"`; mostrar miniatura de imagem para PNGs ali é um ajuste opcional de acompanhamento, não bloqueante.)

Resumo: **o matplotlib é uma capacidade interna do núcleo; a GUI só recebe bytes.** A fluidez da interface não muda.

---

## 10. Passos de implementação (commits ordenados)

**Commit 1 — núcleo (puro, sem GUI; risco mínimo).** `pyproject.toml` extra `[data-plot]`; `src/core/data/charts.py` (`is_available`, `ChartSpec`, `ChartPalette`, `suggest_spec`, `render_png`); `tests/core/data/test_charts.py`. Verde + ruff.

**Commit 2 — CLI (testável; paridade).** Ramo `plot` em `cli/data.py`; teste de dispatch em `tests/cli/test_data_cli.py`. Verde + ruff.

**Commit 3 — GUI (manual smoke).** `tabs/plot_tab.py`; 4ª aba no `view.py`; `run_data_plot`/`start_plot` no `worker.py`; eventos `data_plot_*` no `pipeline_log`/tabelas do design-system. Teste do worker com bus falso (mock `charts.render_png`). Smoke manual.

Ordem core → CLI → GUI (skill `architecture` §5), risco crescente por último. Suíte verde entre commits.

---

## 11. Testes

**Core — `tests/core/data/test_charts.py`** (`@pytest.mark.unit`, `pytest.importorskip("matplotlib")`; render Agg é headless, qualifica como unit; fixtures de `tests/core/data/conftest.py`):

- **Gate** `is_available()`: True com matplotlib; False via `mocker.patch.dict(sys.modules, {"matplotlib": None})`.
- **`suggest_spec`** (puro): categórica+numérica → `bar` com x/y certos; temporal/ordenada+numérica → `line`; uma numérica → `hist`; duas numéricas → `scatter`; sem numérica → fallback previsível.
- **`render_png`**: devolve bytes com assinatura PNG (`\x89PNG`), não vazios, abríveis por Pillow (asserir dimensões > 0) — um caso por `kind`. Determinístico em forma.
- **Paleta**: render com `ChartPalette` custom roda sem erro (cores aplicadas).
- **Thread-safety (smoke)**: dois `render_png` concorrentes em threads produzem PNGs válidos (prova o uso de `Figure`/`FigureCanvasAgg`, não `pyplot`).
- **Bordas**: resultado vazio (mensagem/placeholder, sem estourar); coluna única; `spec` com coluna inexistente → erro claro.

**CLI** — `tests/cli/test_data_cli.py`: `plot` no parser (`--kind/--x/--y/--out`); `run_data_cli` despacha para o render (mock `src.core.data.charts.render_png`); `--sql` não chama `to_sql`; arquivo inexistente → `sys.exit(1)`.

**GUI worker** — `tests/gui/modules/data/test_worker.py` (bus falso): `run_data_plot` emite `data_plot_start`→`data_plot_done` com `png`/`output_path` (mock `engine.run_query_arrow`/`frames.*`/`charts.render_png`); gate ausente → `data_plot_error`. A `plot_tab` em si (Flet) não é testável headless → smoke manual: rodar consulta, abrir Gráfico, ver sugestão automática, trocar tipo/x/y, gerar, salvar PNG.

Meta de cobertura de `charts.py`: ≥ 90% (alvo do projeto).

---

## 12. Critérios de aceitação (Definition of Done)

- `charts.py` puro (sem Flet/DuckDB/Polars), matplotlib lazy + `Agg`/OO + `TYPE_CHECKING`; gate; ≤ ~280 linhas.
- Reusa `run_query_arrow`/`frames.*` do Plano 0; sem reimplementar leitura/conversão.
- Aba Gráfico funciona: sugestão automática + override + PNG na GUI + salvar em `output/data/`; tema escuro aplicado.
- CLI `data plot` em paridade.
- Extra `[data-plot]`; plotar exige `[analysis]`+`[data-plot]`; desabilita graciosamente sem eles; base intacta.
- Contrato `QueryResult`/eventos preservado; só **acrescenta** `data_plot_*`; nenhum DataFrame/figura cruza para a GUI.
- `view.py` continua enxuto (4ª aba só roteia; lógica em `plot_tab.py`); `query_tab`/`preview_tab`/`analysis_tab`/`table_view`/`form_view` intocados.
- `uv run pytest -m unit` verde; `ruff` limpo; cobertura `charts.py` ≥ 90%; checklist da skill `architecture` (§8) satisfeito.

---

## 13. Riscos e o que **não** fazer agora

O risco técnico central é o **threading do matplotlib**: usar `pyplot` numa thread daemon causaria corrupção de estado global. Mitigação: `Figure`/`FigureCanvasAgg` exclusivamente, coberto por teste de concorrência. Risco de escopo: não implementar gráficos interativos (Altair/Plotly), nem o `MatplotlibChart` do Flet, nem re-agregação escondida — tudo isso contraria as decisões da seção 3. Não tocar `query_tab.py` (já é exceção de tamanho do Plano −1) — a aba Gráfico é arquivo próprio. Streaming/lazy não se aplica (o resultado da consulta já é reduzido).

---

## 14. O que destrava / relação com o roadmap

O Plano 1 fecha o PR9.1 e estabelece o **padrão de visualização** (render PNG off-thread, tema injetado, artefato salvo) que o Plano 2 (painéis dos hubs) reutiliza para seus gráficos de Biblioteca/IA/Receitas — sem reinventar a roda. Também valida, na prática, o caminho zero-copy do Plano 0 com um consumidor real. Próximo elo da cadeia: **Plano 2 — painéis analíticos dos três hubs**, que combina a camada de dados (Plano 0) com este padrão de gráfico.

---

## Fontes

- [Backends — Matplotlib (Agg, threading)](https://matplotlib.org/stable/users/explain/figure/backends.html)
- [CanvasAgg demo — Matplotlib (FigureCanvasAgg sem pyplot)](https://matplotlib.org/stable/gallery/user_interfaces/canvasagg.html)
- [Matplotlib FAQ (threading / non-GUI backend)](https://matplotlib.org/stable/users/faq.html)
- [MatplotlibChart — Flet (controle nativo)](https://flet.dev/docs/controls/matplotlibchart/)
- [Flet issue #6295 — problemas do MatplotlibChart](https://github.com/flet-dev/flet/issues/6295)
- [Essential Chart Types for Data Visualization — Atlassian](https://www.atlassian.com/data/charts/essential-chart-types-for-data-visualization)
- [Data Visualization – How to Pick the Right Chart Type? — eazyBI](https://eazybi.com/blog/data-visualization-and-chart-types)
