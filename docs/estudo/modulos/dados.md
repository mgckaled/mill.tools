# Módulo Dados — o que muda em relação à fatia do Vídeo

Delta doc. O Dados é a **ferramenta mais diferente** de todas: motor SQL, uma fronteira de privacidade
rígida, e o padrão de trabalho assíncrono na UI. É também a ponte natural para o mundo de ML.

> **Base:** [`../arquivos/sessao2-vertical-video.md`](../arquivos/sessao2-vertical-video.md),
> [`../conceitos/FLET_GUI.md`](../conceitos/FLET_GUI.md) §3.3 (async na UI),
> [`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) (`tabs/`+`_state`),
> [`../conceitos/RAG.md`](../conceitos/RAG.md)/[`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md)
> (cartão de dados, nl2sql, outliers).

## O que é igual (e o que não é)

É a 6ª **ferramenta** (transforma entrada→saída, **não** é hub). O esqueleto de módulo continua, mas a
composição não vive num formulário de opções — vive numa **consulta única** (query-first), em português
(traduzida pela IA) ou escrita à mão. A GUI tem 4 abas (Consulta·Pré-visualização·Análise·Gráfico).

## Novidade 1 — o motor DuckDB como fronteira única

`core/data/engine.py` é a **única** fronteira com o DuckDB (um banco SQL in-process, torch-free),
injetável (como o `embed_fn` do RAG e o `progress_cb` da espinha — a mesma regra nº 2). Cada consulta
roda numa conexão **efêmera, em memória, read-only**. 🔑 DuckDB in-process qualifica como `unit` nos
testes (sem rede/GPU) — por isso os testes de `tests/core/data/` usam DuckDB **de verdade**, como
Imagem/Documentos usam Pillow/pymupdf.

## Novidade 2 — a fronteira de privacidade (a lição central)

Este é o conceito mais importante do módulo. Quando você pergunta em português, a IA traduz para SQL —
mas **a IA vê só o *schema*** (nomes e tipos de coluna), **nunca as linhas**. Do `core/data/nl2sql.py`:

```python
"""Translate a Portuguese question into a read-only SQL query.
This is the *only* place the LLM is involved in the data module, and it never
sees a data row — just the table/column schema (names and types)."""
```

🔑 Por quê? Se você usar um modelo de **nuvem** (Gemini/GLM), só os **nomes de coluna** saem da
máquina, nunca os seus dados. A IA devolve `{"sql", "explicacao"}`; o SQL roda **localmente** no
DuckDB, contra as linhas reais, que nunca viajaram. É privacidade por desenho — a mesma filosofia do
"embeddings sempre locais" do RAG, aplicada a tabelas.

## Novidade 3 — o guarda `ensure_select` (só leitura)

Antes de qualquer SQL tocar o DuckDB, `core/data/validate.py` rejeita o que não for leitura pura:

```python
_ALLOWED_LEADING = ("select", "with", "from", "describe", "summarize", "pivot", ...)
_FORBIDDEN = ("attach", "copy", "install", "insert", "update", "delete", "create",
              "drop", "alter", "export", "import", "pragma", ...)
```

🔑 É uma **lista de permissão** (o comando deve começar com um token de leitura) + uma **lista de
proibição** (a mera presença de `copy`/`insert`/`attach` etc. reprova). Mesmo o DuckDB rodando numa
conexão sem banco gravável, um `COPY ... TO` poderia tocar o disco — o `ensure_select` é a primeira
linha de defesa. É "deliberadamente rombudo" (o comentário diz): pega falsos positivos raros, mas o
usuário pode editar o SQL à mão. Segurança acima de conveniência.

## Novidade 4 — trabalho pesado assíncrono na UI

Rodar uma consulta DuckDB ou uma tradução por LLM demora. Mas (diferente do ffmpeg) não é um processo
externo com `progress_cb` — é trabalho Python que **bloquearia** a thread da UI. A solução é o padrão
do [`../conceitos/FLET_GUI.md`](../conceitos/FLET_GUI.md) §3.3: `page.run_task(coro)` +
`await asyncio.to_thread(fn, ...)`. 🔑 **Nem thread daemon** (o `update` não repinta) **nem bloquear a
UI** — roda no loop da UI via corrotina, e depois do `await` o `update()` repinta. É o terceiro modo de
concorrência que você vê (thread daemon no Vídeo/Áudio; async-na-UI aqui), cada um para um tipo de
trabalho.

## Novidade 5 — decomposição em `tabs/` + `_state.py`

O painel de 4 abas é o exemplo canônico de `tabs/`
([`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) §4): cada aba é um `build_X_tab → (controle,
refs)`, e o estado transversal (cronômetros, seleção de fonte, `_scoped_update`) vive em
`data/_state.py`.

## Novidade 6 — as integrações (a ponte para ML)

O Dados se conecta a quase tudo: Receitas (`data.query/convert/profile/outliers`), Biblioteca
(`kind="data"`), RAG (indexação pelo **cartão de dados** — nunca as linhas cruas) e `ml.py`
(`detect_outliers` via IsolationForest). O **cartão de dados** (`datacard.py`) é como uma tabela entra
no RAG sem expor dados: um resumo indexável. Detalhe em
[`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md) §4.2 (outliers) e
[`../conceitos/RAG.md`](../conceitos/RAG.md) (indexação por cartão).

---

# Perguntas de fixação (comparativas)

1. Quando você pergunta em português no módulo Dados, o que **exatamente** a IA recebe? O que ela
   **nunca** vê? Por que isso protege seus dados mesmo usando um modelo de nuvem?
2. O DuckDB já roda numa conexão read-only. Por que ainda existe o `ensure_select`? Dê um exemplo de
   SQL que ele bloqueia e por quê.
3. O Vídeo roda o pipeline numa thread daemon; o Dados usa `page.run_task` + `asyncio.to_thread`. Por
   que a diferença? (dica: processo externo vs. trabalho Python que bloqueia)
4. Por que o RAG indexa uma tabela pelo "cartão de dados" e não pelas linhas? Ligue à fronteira de
   privacidade.
5. O motor DuckDB é "injetável". Que outra fronteira do projeto segue a mesma regra, e o que isso
   permite nos testes?

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. A IA recebe **só o schema** (nomes e tipos de coluna) e devolve `(sql, explicação)`. Ela **nunca**
   vê uma linha. Mesmo com modelo de nuvem, só nomes de coluna saem da máquina — o SQL roda
   localmente contra os dados reais.
2. Porque mesmo numa conexão read-only, um `COPY ... TO` poderia tocar o disco. O `ensure_select`
   rejeita por lista de permissão (só começos de leitura) + lista de proibição (`copy`, `insert`,
   `attach`...). Ex.: `COPY (SELECT ...) TO 'x.csv'` é bloqueado.
3. O ffmpeg é **processo externo** — thread daemon + eventos funcionam. DuckDB/LLM é **trabalho
   Python** que bloquearia a thread da UI, e thread daemon não repinta (quirk 0.85) — daí
   `page.run_task` + `await asyncio.to_thread`, que volta ao loop da UI para o `update()`.
4. O cartão é um **resumo indexável** (schema, estatísticas, descrição) — a tabela entra no corpus
   sem expor linhas. Mesma fronteira de privacidade do `nl2sql`, agora na indexação.
5. O `embed_fn` do RAG (e o `progress_cb` da espinha, o `make_llm`). Injeção na fronteira permite
   testar toda a lógica com dublês, sem Ollama/rede — regra nº 2.

</details>

## Desafios

- **D1 (ache o bug)** Um PR melhora o `nl2sql` enviando à IA, além do schema, "5 linhas de amostra
  para o modelo entender os dados". A qualidade do SQL até melhora. Por que o PR é recusado mesmo
  assim?
- **D2 (e se...?)** E se o `ensure_select` tivesse **só** a lista de proibição (sem a lista de
  permissão de tokens iniciais)? Que categoria de brecha ficaria aberta?
- **D3 (projete)** Nova aba "Exportar" que roda a consulta atual e grava xlsx — a consulta pode levar
  20s. Qual dos três modos de concorrência do projeto você usa, e por que os outros dois estão
  errados aqui?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — Quebra a **fronteira de privacidade**, que é um contrato absoluto, não um "trade-off de
  qualidade": com modelo de nuvem, linhas reais (possivelmente dados pessoais/financeiros) sairiam da
  máquina. O desenho do módulo promete "a IA nunca vê uma linha" — a GUI e a doc afirmam isso ao
  usuário. Melhorias de qualidade têm que vir de schema mais rico (tipos, nomes, estatísticas
  agregadas), nunca de dados.
- **D2** — Comandos **desconhecidos ou futuros** passariam: a lista de proibição só pega o que foi
  previsto. Um token novo do DuckDB (ou um comando exótico) que escreve/toca disco não estaria na
  lista e rodaria. A lista de permissão inverte o default: **tudo é proibido, exceto começos de
  leitura conhecidos** — o default seguro.
- **D3** — `page.run_task(coro)` + `await asyncio.to_thread(exportar, ...)`, o padrão das abas do
  Dados. Thread daemon está errada: o `update()` dela não repinta (quirk 0.85) — e não há contrato de
  eventos de pipeline nesta aba. Bloquear a thread da UI está errado: 20s de tela congelada. Depois
  do `await`, você está de volta ao loop da UI e o `update()` repinta o rodapé com o resultado.

</details>
