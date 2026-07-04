# Plano PR9.3 — Prévia visual, Avaliação da IA e Indexação de Dados no RAG

> Extensão do PR9 (Módulo Dados). Cobre três capacidades interligadas:
> (1) prévia visual da fonte, (2) avaliação de qualidade pela IA, (3) indexação dos 5 formatos no RAG.
> As três compartilham a mesma peça: o **cartão de dados** (descrição textual de um arquivo).

---

## 1. Princípio que sustenta o PR9.3

| Pergunta | Quem responde |
|---|---|
| "O que tem *dentro* dos dados?" (linhas, somas, filtros) | **DuckDB** (consulta) |
| "*Qual* dataset / sobre o que é este arquivo?" (descoberta, entendimento) | **RAG** (catálogo semântico) |
| "Esses dados estão consistentes?" (qualidade, tipos, estrutura) | **IA** (narra o perfil; não toca nas linhas) |

**Decisão central:** o RAG indexa o **cartão de dados** (texto que *descreve* o arquivo), nunca as linhas cruas. Motivos: embeddar linhas incha o índice e vira ruído; embeddings são fracos com números (filtragem numérica fica no DuckDB). O RAG vira um catálogo; o DuckDB, o motor de consulta.

---

## 2. O "cartão de dados" (data card) — artefato indexável

Documento textual gerado por arquivo (ou por aba, no XLSX), **agnóstico de formato** (o `scanner`/`engine` já abstraíram CSV/TSV/JSON/Parquet/XLSX antes deste ponto):

```
ARQUIVO: vendas.csv  ·  formato: CSV  ·  26 linhas × 7 colunas
SCHEMA: id_venda(BIGINT) · data(VARCHAR) · produto(VARCHAR) · valor(VARCHAR) · ...
PERFIL (SUMMARIZE):
  - valor: VARCHAR · 3 nulos · 18 distintos · ex.: "R$ 45,00", "45", "N/A"
  - cidade: VARCHAR · 0 nulos · 6 distintos
  - ...
AMOSTRA (10 linhas em texto)
AVALIAÇÃO DA IA (opcional, cacheada): "coluna valor está como texto porque mistura formatos..."
```

Construtor: novo `core/data/datacard.py` (puro) — `build_data_card(DataFile, profile, sample, assessment=None) → str`. Determinístico (schema + perfil + amostra); a avaliação da IA entra só se já estiver cacheada.

---

## 3. Prévia visual da fonte (modal)

- **Olho clicável dentro do card da fonte** (o "chip"): ao adicionar um arquivo, o card mostra `nome · N linhas × M colunas` + ícone de olho.
- Olho → `AlertDialog` (modal flutuando sobre as duas views, padrão do inspetor de índice do PR7.2).
- Dentro do modal: **componente de tabela reutilizável** (o mesmo do painel de resultado da consulta) mostrando as primeiras ~100 linhas, paginado (`PREVIEW_ROWS`, update escopado, carga em `page.run_task`).
- Cabeçalho da tabela mostra o **tipo inferido por coluna** (vinda do `scanner`) → a prévia vira também lente de qualidade (vê-se `valor: VARCHAR` a olho nu).
- **XLSX multi-aba:** seletor de aba no modal (único formato que exige parâmetro extra).

Core novo: `engine.preview(arquivo, limit, offset[, sheet]) → QueryResult` (`SELECT * ... LIMIT ? OFFSET ?`).

**Custo de memória/processamento:** baixo para CSV/TSV/Parquet (streaming, ~constante); limitado para XLSX (aba carrega, mas ≤1M linhas); um pouco maior só para JSON-array gigante (parse quase total). Disciplina real é na UI: capar linhas + paginar.

---

## 4. Avaliação da IA (prompt de responsabilidade única)

> No app não há "subagente" (processo separado) — é um prompt estrito no estilo dos perfis de `src/analysis/`.

- Core novo: `core/data/assess.py` — `build_assessment_prompt(schema, profile_text, sample) → ChatPromptTemplate` + `assess(...)` via `make_llm`. Escapa chaves literais (`{`→`{{`).
- **A IA recebe só:** nomes/tipos de coluna + `SUMMARIZE` do DuckDB + amostra de ~10 linhas. **Nunca as linhas todas.**
- Saída: markdown sinalizando consistência, tipos suspeitos, colunas mal nomeadas, duplicatas, valores fora de faixa, estrutura (cabeçalho deslocado, schema irregular).
- **Exibição:** segunda seção/aba no modal de prévia ("Avaliação da IA").
- **Cache + reúso:** a avaliação é gravada (junto ao índice ou em `~/.mill-tools/`); a indexação a reaproveita sem novo custo de LLM.
- Privacidade: com Gemini, só nomes de coluna + estatísticas saem da máquina.

> 🔍 **Checkpoint context7:** `query-docs` DuckDB sobre `SUMMARIZE` e `TABLESAMPLE`/`USING SAMPLE` (para perfilar arquivo grande sem varrer tudo).

---

## 5. Indexação dos 5 formatos no RAG — pipeline detalhado

Integra com o `core/rag/` existente (`embedder`/`store`/`indexer`/`retriever`/`chat`), sem mexer no motor de embedding.

1. **Descoberta:** o `library/scanner.py` já mapeia `output/data/ → kind="data"`. O `indexer.build_index()` passa a incluir `"data"` nos kinds indexáveis.
2. **Roteamento:** para `kind="data"`, em vez de ler texto, o indexer chama `build_data_card()` (scanner + `profile`/`SUMMARIZE` + amostra + avaliação cacheada se houver).
3. **Chunking:** `split_text` no cartão — pequeno, normalmente 1–3 chunks por arquivo (vs. dezenas numa transcrição).
4. **Embedding + store:** `embedder` (nomic-embed-custom, 768-dim) → `VectorStore` com metadados `(path, kind="data", mtime, formato, dims)`.
5. **Incremental:** por `(path, mtime)` — reembeda só o que mudou, reconcilia removidos (já existe no indexer).
6. **Recuperação/chat:** cartões de dados aparecem como fontes `[n]` como qualquer documento. A resposta pode citar o dataset e até sugerir a consulta DuckDB.

### Por formato — o que muda

| Formato | Particularidade na indexação |
|---|---|
| CSV / TSV | encoding/delimitador resolvidos no `engine`; cartão uniforme |
| JSON | listar **caminhos aninhados** no schema; NDJSON é mais leve que array para perfilar |
| Parquet | tipos e stats vêm do **metadata** (perfil mais barato dos cinco) |
| XLSX | **um cartão por aba** (cada aba é uma tabela); extensão `excel` |

> Quando o cartão é montado, o formato já foi abstraído — por isso o pipeline (passos 1–6) é idêntico para os cinco.

---

## 6. Bridges e integração

- Resposta do hub IA sobre um dataset → badge `[n]` → bridge **"Consultar nos Dados"** abre o módulo Dados com o arquivo carregado (fecha o ciclo descoberta → consulta).
- `profile`/cartão também viram texto consultável no hub IA.
- Botão **"Indexar no RAG"** no painel de resultado/prévia (reusa o `index_button` do PR7.2).

---

## 7. Esforço e custo

- **Código:** moderado. Novo: `datacard.py`, `assess.py`, `engine.preview`, roteamento de `kind="data"` no indexer, modal de prévia. Reaproveita: componente de tabela (compartilhado com resultado), todo o `core/rag/`, `index_button`.
- **Embedding:** baixíssimo (1–3 chunks por arquivo) — indexar dados é **mais leve** que indexar transcrições.
- **Perfil:** uma passada por arquivo (barata no Parquet via metadata; varredura no CSV), só no momento de indexar e **incremental**; amostrada (`USING SAMPLE`) para arquivos grandes.
- **Avaliação IA:** uma inferência pequena, **sob demanda + cacheada** (não roda por arquivo durante o index).

---

## 8. Riscos e decisões

| Risco / decisão | Tratamento |
|---|---|
| Embeddar linhas cruas | **Não fazer** — indexar só o cartão (evita bloat e ruído) |
| Embeddings fracos com números | RAG só para descoberta semântica; filtragem numérica fica no DuckDB |
| Avaliação IA encarecer a indexação | Determinística por padrão; narrativa IA é opcional/cacheada |
| XLSX multi-aba | Um cartão por aba; seletor de aba na prévia |
| Perfil de arquivo gigante | `USING SAMPLE` no `SUMMARIZE`; prévia sempre com `LIMIT` |
| JSON-array enorme | Sinalizar formato menos "preguiçoso"; preferir NDJSON quando possível |

---

## 9. Skills e checkpoints (execução em Claude Code)

- 🎨 **`design-system`** — modal de prévia, olho no card, componente de tabela compartilhado, seletor de aba.
- 🧪 **`testing`** — units de `datacard` e `assess` (LLM mock `GenericFakeChatModel`), `engine.preview` (DuckDB real), roteamento `kind="data"` no indexer.
- ⌨️ **`cli`** — se expor `data assess <arquivo>` / `ai index` cobrindo `kind="data"`.
- 🔍 **context7** — antes de escrever: DuckDB (`SUMMARIZE`, `USING SAMPLE`, `read_json` aninhado, extensão `excel` multi-aba) e Flet 0.85 (`AlertDialog`, `DataTable`).

---

## 10. Ordenação sugerida

`engine.preview + modal (prévia visual) → profile/SUMMARIZE → assess.py (avaliação IA) → datacard.py → roteamento kind="data" no indexer → bridges`.
Cada etapa entrega valor isolado: a prévia já é útil sozinha; a avaliação reusa o perfil; a indexação reusa a avaliação cacheada.
