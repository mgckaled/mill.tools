# Plano 0 — Fundação de dados (camada Polars/pandas sobre o DuckDB)

**Documento de execução — plano de implementação detalhado**
Data: 23 de junho de 2026 · Roadmap de origem: `docs/ROADMAP.md` (Plano 0) · Padrão de referência: skill `architecture`

> **Invocação da skill.** Ao executar este plano, **invoque a skill `architecture`** (`.claude/skills/architecture/SKILL.md`) e siga-a à risca: núcleo puro (seção 1), camadas e quem-importa-quem (seção 2), limites de tamanho/coesão (seção 3), padrões de decomposição (seção 4), fluxo de feature de ponta a ponta — core → extra/gate → CLI → GUI → testes (seção 5), e o checklist de revisão (seção 8). Este plano é a aplicação concreta daquele guia ao Plano 0.

---

## Sumário

1. Objetivo e escopo
2. Achados da varredura web (e como influenciam a fundação)
3. Decisões de arquitetura
4. O desenho: `frames.py` como **única fronteira de DataFrame**
5. A mudança mínima no `engine.py` (caminho zero-copy)
6. Dependências (extra `[analysis]`, import preguiçoso, gate)
7. A ideia inteligente: preservar a tradução fluida para a GUI
8. Passos de implementação (commits ordenados)
9. Testes (o quê, como, casos)
10. Critérios de aceitação
11. Riscos e o que **não** fazer agora
12. O que esta fundação destrava

---

## 1. Objetivo e escopo

Criar a "camada de acabamento" que leva o resultado de uma consulta DuckDB para uma tabela de trabalho em memória (Polars por padrão) e de volta, com Polars adotado como padrão e a conversão para pandas reservada à fronteira de ML/gráficos. É a fundação dos Planos 1 (gráficos), 5 (ML tabular) e dos painéis analíticos (Plano 2).

**No escopo:** um módulo novo `src/core/data/frames.py` (puro), uma adição mínima ao `engine.py` (saída Arrow para handoff zero-copy), o extra opcional de dependências, e os testes. **Fora do escopo:** qualquer mudança de comportamento visível, qualquer alteração no contrato de eventos da GUI, e qualquer feature de usuário (gráficos, ML — esses são Planos 1+). O Plano 0 é **puramente aditivo**: adiciona capacidade ao núcleo sem mexer no fluxo `data query` atual.

---

## 2. Achados da varredura web (e como influenciam a fundação)

A varredura confirmou o desenho e trouxe quatro influências concretas.

**DuckDB ↔ Polars é zero-copy via Apache Arrow.** Ambos usam o formato colunar Arrow, então um resultado do DuckDB vira um DataFrame Polars sem serialização — o DuckDB produz *record batches* Arrow que o Polars consome por referência. *Influência:* a fundação deve oferecer um caminho Arrow (DuckDB → Arrow → Polars), não só o caminho via linhas, para que transformações sobre resultados grandes não paguem a ida-e-volta por tuplas de Python.

**Polars está maduro para produção (1.x desde jul/2024; em 2026 com API estável e motor de *streaming* para dados maiores que a RAM).** *Influência:* adotar Polars como padrão é seguro; e a fundação deve deixar um *seam* para o caminho lazy/streaming (`scan_*`) sem comprometer-se a usá-lo já — o DuckDB já faz leitura out-of-core, então streaming Polars é complemento, não necessidade imediata.

**A interoperabilidade Polars↔pandas é por conversão explícita (`.to_pandas()` é rápido), não por internals compartilhados; matplotlib/scikit-learn esperam pandas/NumPy (sklearn 1.4+ já emite Polars).** *Influência:* confirma a regra "Polars no miolo, pandas na cauda" — a fundação expõe `to_pandas()` como ponto único de conversão de borda, usado só pelos Planos 1/5.

**Existe o `narwhals` — camada agnóstica de DataFrame (aceita Polars, pandas, pyarrow e até relações DuckDB; usada por Altair/Plotly/scikit-lego).** *Influência:* é uma alternativa elegante para escrever código agnóstico de backend, **mas é over-engineering para o Plano 0** de um app single-dev com Polars como padrão. Fica **deferido e documentado** (seção 11), com critério claro de quando adotá-lo.

Fontes na seção final.

---

## 3. Decisões de arquitetura

**Polars é o padrão do miolo.** Todas as transformações intermediárias da camada usam Polars. pandas só aparece via `to_pandas()` explícito, na borda de ML (Planos 3/5) e de gráficos matplotlib (Plano 1).

**`frames.py` é a única fronteira de DataFrame** — espelhando o `engine.py`, que é a única fronteira do DuckDB. Só o `frames.py` importa Polars/pandas; o resto do núcleo de dados nunca vê um objeto DataFrame. Isso mantém a importação preguiçosa isolada num único arquivo e permite trocar a tecnologia (ex.: adotar narwhals depois) mexendo em **um** lugar.

**O contrato com a GUI continua `QueryResult`** (`columns: list[str]`, `rows: list[tuple]`, `elapsed`, `n_rows`). Nenhum DataFrame cruza a fronteira para a GUI ou para o *event bus*. É a decisão central de "não atrapalhar a tradução para a GUI" (seção 7).

**Dependências entram como extra opcional `[analysis]`, com import preguiçoso e gate** `is_available()`, na convenção de `[ai-image]`/`[ocr]` (skill `architecture`, seção 7). A base segue mínima e o fluxo `data query` atual roda sem o extra.

**narwhals fica deferido** (seção 11).

---

## 4. O desenho: `frames.py` como única fronteira de DataFrame

Arquivo novo `src/core/data/frames.py` (puro; ≤ ~250 linhas; teto de core na skill `architecture`). API proposta:

| Função | Assinatura | Papel |
|---|---|---|
| `is_available()` | `() -> bool` | Gate: Polars importável. Lazy. Espelha `embedder.is_available()` |
| `to_polars(result)` | `(QueryResult) -> "pl.DataFrame"` | Constrói Polars a partir de `columns`+`rows` (caminho universal; funciona sobre o que já existe hoje) |
| `from_arrow(table)` | `(pa.Table) -> "pl.DataFrame"` | Embrulha um Arrow Table em Polars (zero-copy). Usado com a saída Arrow do engine |
| `to_result(df, *, limit=None)` | `("pl.DataFrame", int\|None) -> QueryResult` | **Polars → contrato da GUI.** Materializa `columns`/`rows`/`n_rows`. Único ponto que devolve DataFrame ao mundo da GUI |
| `to_pandas(df)` | `("pl.DataFrame") -> "pd.DataFrame"` | Conversão de borda para ML/gráficos. pandas lazy. Único ponto pandas |
| `optimize(df)` | `("pl.DataFrame") -> "pl.DataFrame"` | Boas práticas do artefato 2: `shrink_dtype()` + categóricos para strings de baixa cardinalidade |
| `describe(df)` | `("pl.DataFrame") -> QueryResult` | Estatísticas rápidas (`df.describe()`) já no contrato da GUI — reutilizável por perfis/analytics |

Princípios do arquivo: todas as funções recebem/retornam tipos do projeto (`QueryResult`) ou DataFrames; **nenhuma** toca DuckDB (isso é do engine) nem Flet (isso é da GUI); os imports de `polars`/`pandas`/`pyarrow` são **function-local** (preguiçosos); anotações de tipo de DataFrame ficam como string (`"pl.DataFrame"`) para não exigir o import no topo. Docstrings em inglês (skill `architecture`, seção 1).

**Seam de futuro (não implementar agora, só deixar o lugar):** `scan(path) -> "pl.LazyFrame"` para o caminho lazy/streaming. Documentar como ponto de extensão; o DuckDB já cobre out-of-core, então isso só entra se algum plano precisar de transformação Polars nativa sobre arquivo grande.

---

## 5. A mudança mínima no `engine.py` (caminho zero-copy)

O `engine.py` permanece a **única fronteira DuckDB** e continua sem importar Polars. A única adição é uma função que devolve **Arrow** (nativo do DuckDB), para o `frames.from_arrow` converter em Polars sem cópia:

```python
def run_query_arrow(files, sql, *, connect_fn=_connect):
    """Validate, register views, execute and return a pyarrow.Table (zero-copy seam to Polars)."""
    ensure_select(sql)
    con = connect_fn()
    try:
        register_views(con, files)
        return con.execute(sql).fetch_arrow_table()
    finally:
        con.close()
```

Assim a separação se mantém limpa: **engine faz DuckDB→Arrow; frames faz Arrow→Polars.** O caminho por linhas (`run_query` → `to_polars`) continua existindo para quem não precisa do zero-copy. Esta adição é opcional ao Plano 0 mínimo (pode ser um segundo commit — seção 8).

---

## 6. Dependências (extra `[analysis]`, lazy, gate)

No `pyproject.toml`, um extra novo:

```toml
[project.optional-dependencies]
analysis = ["polars>=1.0", "pandas>=2.0", "pyarrow>=15"]
```

`polars` é o padrão do miolo; `pandas` é a borda de ML/gráficos; `pyarrow` habilita o handoff Arrow (DuckDB `fetch_arrow_table` + `pl.from_arrow`). Instalação: `uv sync --extra analysis`. O `frames.is_available()` é o gate; os recursos que dependerem da camada (Planos 1/5/2) desabilitam graciosamente quando o extra falta — exatamente como o card de remoção de fundo hoje.

> **Por que extra e não dependência-base.** Coerência com a filosofia de base mínima do projeto (skill `architecture`, seção 7) e com o fato de o fluxo `data query` atual não precisar de DataFrame algum. Se preferir simplicidade a leveza, é defensável promover `polars`/`pandas` à base — decisão sua; o plano assume o extra por padrão.

---

## 7. A ideia inteligente: preservar a tradução fluida para a GUI

O risco real ao introduzir DataFrames é "vazar" objetos Polars/pandas para a camada Flet e para o *event bus*, complicando a serialização, a thread-safety e o componente de tabela. A fundação evita isso por desenho, com três regras:

**Primeira — o *event bus* e a GUI só falam `QueryResult`.** Os eventos `data_result`/`data_*` continuam carregando `columns: list[str]` + `rows: list[tuple]`; a `table_view.py` e o `DataTable` paginado **não mudam**. O DataFrame vive e morre dentro do núcleo; a conversão de saída é o `frames.to_result(df)`. Resultado: a tradução para a GUI permanece idêntica à de hoje.

**Segunda — gráficos viram PNG, não objetos de plotagem.** Flet não embute Altair/Vega com facilidade; então (no Plano 1) o gráfico será renderizado a **bytes PNG** via matplotlib e exibido num `ft.Image`, exatamente como a waveform do player e os thumbnails da Biblioteca já fazem. O `frames` entrega o DataFrame; o construtor de gráfico faz `to_pandas` e devolve PNG. `frames` permanece agnóstico de plotagem.

**Terceira — todo trabalho pesado de Polars roda fora da UI thread.** As conversões/transformações são puras e síncronas em `frames`; quem escolhe a thread é o *worker* do módulo Dados, via `page.run_task` + `asyncio.to_thread` (padrão já documentado na skill `design-system` para DuckDB/LLM). Nada de DataFrame na UI thread.

Em uma frase: **o DataFrame é uma capacidade interna do núcleo; a GUI nunca o vê.** É isso que mantém a tradução para a interface tão fluida quanto hoje.

---

## 8. Passos de implementação (commits ordenados)

**Commit 1 — camada base (sem mexer no engine, sem GUI; risco mínimo).**

1. `pyproject.toml`: adicionar o extra `[analysis]`.
2. Criar `src/core/data/frames.py` com `is_available`, `to_polars(result)`, `to_result(df, limit)`, `to_pandas(df)`, `optimize(df)`, `describe(df)` — imports preguiçosos, docstrings EN.
3. Criar `tests/core/data/test_frames.py` (seção 9).
4. Rodar `uv run pytest -m unit` (verde) + `ruff` (limpo).

**Commit 2 — caminho zero-copy (Arrow).**

5. `engine.py`: adicionar `run_query_arrow(...)`.
6. `frames.py`: adicionar `from_arrow(table)`.
7. Testes de paridade: `run_query` (linhas) e `run_query_arrow → from_arrow → to_result` produzem o **mesmo** `QueryResult`.
8. Verde + ruff.

**(Opcional, futuro) Commit 3 — seam lazy:** `frames.scan(path)` só se/quando um plano precisar; não fazer preventivamente (regra "divide-se ao tocar").

Cada commit é pequeno, com a suíte verde antes e depois. Nada toca o `data/view.py`/`worker.py` — a fundação é consumida pelos planos seguintes, não cabeada agora.

---

## 9. Testes

`tests/core/data/test_frames.py`, marcados `@pytest.mark.unit` (Polars/DuckDB rodam in-process, sem rede/ffmpeg/GPU — qualificam como unit, como os demais testes de dados). Como `polars`/`pandas`/`pyarrow` são extra, usar `pytest.importorskip("polars")` no topo do módulo (degrada com skip elegante se o extra faltar, padrão de `pymupdf` na skill `testing`). Reaproveitar as fixtures de `tests/core/data/conftest.py` (`csv_sales`, `csv_people_cp1252`, `json_file`). Imports dentro das funções; espelhar `src/`.

Casos a cobrir:

- **Gate** — `is_available()` True com Polars presente; False com `mocker.patch.dict(sys.modules, {"polars": None})` (padrão do `embedder`).
- **Round-trip `QueryResult` → Polars → `QueryResult`** — `to_result(to_polars(r))` preserva `columns`, `rows` e `n_rows`; cobrir tipos: inteiros, floats, strings, booleanos, datas e **nulos** (None preservado, sem virar NaN espúrio).
- **Paridade de caminhos** — para o mesmo SQL, `run_query(...)` (linhas) e `from_arrow(run_query_arrow(...))` → `to_result(...)` produzem `QueryResult` idênticos (prova que o caminho zero-copy concorda com o caminho por linhas).
- **`to_pandas`** — Polars → pandas com mesma forma/colunas/valores; confirma import lazy de pandas (não importado no topo).
- **`optimize`** — `shrink_dtype` reduz larguras quando aplicável e preserva valores; coluna de strings repetidas vira categórica; valores inalterados.
- **`describe`** — devolve um `QueryResult` com as estatísticas esperadas (contagem, média etc.) para um CSV conhecido.
- **`to_result(limit=...)`** — respeita o teto de linhas; `n_rows` reflete o materializado.
- **Bordas** — resultado vazio (0 linhas), uma só coluna, coluna inteiramente nula, strings unicode/pt-BR (o engine já normaliza encoding; garantir que a camada não corrompe).

Lógica pura → ganha teste de verdade aqui; é cobertura nova que o módulo não tinha. Meta de cobertura do `frames.py`: ≥ 90% (alvo do projeto na skill `testing`).

---

## 10. Critérios de aceitação (Definition of Done)

- `frames.py` existe, é puro (sem Flet/DuckDB), com imports preguiçosos e gate; ≤ ~250 linhas.
- `engine.py` ganhou apenas `run_query_arrow` e continua sem importar Polars.
- Extra `[analysis]` no `pyproject.toml`; `uv sync --extra analysis` funciona.
- O contrato de GUI/eventos (`QueryResult`, `data_result`) está **inalterado**; o fluxo `data query` atual roda sem o extra.
- `tests/core/data/test_frames.py` cobre os casos da seção 9; `uv run pytest -m unit` verde; `ruff` limpo; cobertura de `frames.py` ≥ 90%.
- Nenhuma mudança em `data/view.py`/`worker.py`/`table_view.py`.
- Checklist de revisão da skill `architecture` (seção 8) satisfeito.

---

## 11. Riscos e o que **não** fazer agora

O risco principal é *escopo*: a tentação de já cabear gráficos ou ML aqui. Não fazer — isso é Plano 1/5; a fundação só entrega capacidade + testes. Segundo risco: vazar DataFrame para a GUI — evitado pela regra da seção 7 (a GUI só vê `QueryResult`).

**narwhals — deferido conscientemente.** É elegante, mas adicioná-lo agora traz uma abstração e uma dependência que não se pagam num app com Polars como padrão único. Critério para reconsiderar no futuro: se a fundação precisar suportar **mais de um backend de DataFrame de forma intercambiável** (ex.: oferecer pandas E Polars ao usuário, ou aceitar relações DuckDB/pyarrow diretamente em muitos módulos). Enquanto o padrão for "Polars no miolo, pandas só na borda", `to_pandas()` explícito é mais simples e transparente que uma camada agnóstica. Se adotado depois, o impacto fica **contido em `frames.py`** — que é exatamente o motivo de centralizar tudo ali.

**Streaming/lazy Polars — não agora.** O DuckDB já lê out-of-core; o `scan()` lazy fica como seam documentado, a implementar só sob demanda real.

---

## 12. O que esta fundação destrava

Concluído o Plano 0, os planos seguintes apenas **consomem** `frames`: o Plano 1 faz `to_pandas` + matplotlib → PNG para os gráficos; o Plano 2 monta os painéis dos hubs sobre `QueryResult`/`describe`; o Plano 5 leva o resultado a `to_pandas` para alimentar scikit-learn/XGBoost. Todos reutilizam a mesma fronteira única, com a conversão de borda num só lugar — exatamente o desenho "fundação pequena uma vez, sem retrabalho" que rege o roadmap.

---

## Fontes

- [Integration with Polars — DuckDB (guia oficial)](https://duckdb.org/docs/lts/guides/python/polars)
- [Polars Integration — duckdb/duckdb-python (DeepWiki)](https://deepwiki.com/duckdb/duckdb-python/4.2-polars-integration)
- [Announcing Polars 1.0 — pola.rs](https://pola.rs/posts/announcing-polars-1/)
- [Streaming — Polars user guide](https://docs.pola.rs/user-guide/concepts/streaming/)
- [Polars vs Pandas in 2026: Performance Benchmarks](https://www.danilchenko.dev/posts/polars-vs-pandas/)
- [Polars has a new lightweight plotting backend — pola.rs](https://pola.rs/posts/lightweight_plotting/)
- [narwhals — compatibility layer between dataframe libraries (GitHub)](https://github.com/narwhals-dev/narwhals)
- [Writing DataFrame-Agnostic Python Code With Narwhals — Real Python](https://realpython.com/narwhals-python/)

---

## Notas de execução (pós-implementação · 26 jun 2026)

Dois ajustes que o plano não previu, descobertos só ao executar contra as versões reais
(polars 1.42, pandas 3.0.3, pyarrow 24, DuckDB 1.5.4):

1. **`to_result` fixa `elapsed=0.0`.** O `QueryResult` carrega um campo `elapsed`, mas
   `to_result(df)` é conversão pura (nenhuma consulta roda), então não há tempo a medir.
   Consequência prática: o **teste de paridade** (seção 9) compara apenas
   `columns`/`rows`/`n_rows` entre o caminho por linhas e o caminho Arrow — **não** `elapsed`,
   que legitimamente difere (o `run_query` mede; o `to_result` não).
2. **DuckDB depreciou `fetch_arrow_table()`.** O método mostrado na seção 5 emite
   `DeprecationWarning` na versão instalada e aponta o substituto `to_arrow_table()`. O
   `run_query_arrow` usa **`con.execute(sql).to_arrow_table()`** — sem warning e à prova de
   futuro; o contrato (devolver um `pyarrow.Table`) é idêntico.

E uma propriedade arquitetural confirmada: **a fronteira ficou genuinamente única.** pyarrow
vive **só sob `TYPE_CHECKING`** no `engine.py` e no `frames.py`; o `engine` segue DuckDB-puro
e o `frames` é o único arquivo que toca Polars/pandas. Nenhum outro arquivo importa `frames`
(fundação aditiva). Trocar a tecnologia de DataFrame depois (ex.: adotar narwhals, seção 11)
fica contido em **um** arquivo — exatamente o motivo de centralizar ali.
