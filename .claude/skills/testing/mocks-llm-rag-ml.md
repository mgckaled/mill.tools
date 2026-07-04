# Testing — mocks de LLM, RAG, ML e Dados

Receitas de mock para as camadas de IA: LangChain (`GenericFakeChatModel`), core RAG (`src/core/rag/`),
core ML (`src/core/ml/`, Planos 3/4A/4B), core Dados (`src/core/data/`, incl. `assess`/`datacard`) e core
Receitas (`src/core/recipes/`). Todas essas camadas são unit-testáveis **sem rede** graças à injeção de
dependências (`embed_fn`, `make_llm_fn`, `STEP_REGISTRY`). Abra este arquivo ao testar qualquer uma delas.

---

## Mock de LangChain (`GenericFakeChatModel`) — analyzer/formatter/prompter

Os módulos `src/analyzer.py`, `src/formatter.py` e `src/prompter.py` usam o padrão `chain = ANY_PROMPT | llm`
seguido de `chain.invoke({"text": ...})`. **Não** use `MagicMock` direto — `RunnableSequence` valida que o
operando direito do `|` seja um `Runnable`, e MagicMock falha nessa checagem.

Use `GenericFakeChatModel` de `langchain_core.language_models.fake_chat_models`: é um `Runnable` real que
retorna respostas determinísticas a partir de um iterador de `AIMessage`.

```python
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


def _fake_llm(*responses: str):
    return GenericFakeChatModel(messages=iter([AIMessage(content=r) for r in responses]))


def test_format_transcription(tmp_path, mocker):
    from src import formatter
    src = tmp_path / "t.txt"
    src.write_text(_HEADER + "\n\nhello.", encoding="utf-8")
    mocker.patch.object(
        formatter, "make_llm",
        return_value=_fake_llm("formatted content"),
    )
    out = formatter.format_transcription(src)
    assert "formatted content" in out
```

Para o analyzer, que chama `make_llm` **duas vezes** (uma para análise em T=0.4, outra para detecção de
idioma em T=0), use `side_effect=[fake1, fake2]`:

```python
mocker.patch.object(
    analyzer, "make_llm",
    side_effect=[
        _fake_llm(json.dumps(analysis_dict, ensure_ascii=False)),   # análise (1ª chamada)
        _fake_llm("pt"),                                            # detecção (2ª chamada)
    ],
)
```

Quando o fluxo precisa de N respostas em sequência (multi-chunk + merge), empilhe-as na mesma fake e o
iterador interno avança a cada `.invoke()`:

```python
_fake_llm(*([partial_json] * n_chunks), merged_json)
```

**Gotcha**: a `GenericFakeChatModel` levanta `StopIteration` se a chain chamar `.invoke()` mais vezes que o
número de mensagens fornecidas. Isso é útil — falha imediata se você previu errado quantas chamadas o
código faz (ex.: esquecer que single-chunk **não** invoca o merge).

**Isolation de output dirs**: redirecione `TRANSCRIPTIONS_DIGEST_DIR` ou `TRANSCRIPTIONS_ANALYSIS_DIR` via
`monkeypatch.setattr(mod, "ATTR", tmp_path)` no nível do módulo — esses atributos são lidos só dentro de
`analyze()` / `build_prompt_ready()`, então um fixture autouse não é necessário.

---

## Core RAG (`src/core/rag/`) — `embed_fn` injetado, sem Ollama

O core do RAG é unit-testável **sem rede**: indexer/retriever/batch recebem `embed_fn`/`embed_query_fn`
injetados, e `chat.answer` usa `make_llm` (mocável via `GenericFakeChatModel`). Padrões:

- **`embedder.is_available`/`embed_texts`**: o `langchain_ollama` é importado **lazy** dentro das funções →
  substitua o módulo inteiro via `mocker.patch.dict(sys.modules, {"langchain_ollama": _fake_module})` (um
  `MagicMock` com `.OllamaEmbeddings`). Cubra o ramo "pacote ausente" com
  `mocker.patch.dict(sys.modules, {"langchain_ollama": None})`.
- **`store`**: use vetores estreitos (dim 3–8) e `np.eye`/vetores ortogonais — vetor idêntico → score ≈ 1.0,
  ortogonal → ≈ 0. `persist`/`load` round-trip em `tmp_path`. Serialização usa `dataclasses.asdict` (slots
  não têm `__dict__`).
- **`indexer.build_index`**: crie `LibraryItem`s sintéticos apontando p/ `.txt` reais em `tmp_path`; controle
  o `mtime` pelo **campo `modified`** do item (não pelo mtime do arquivo). `embed_fn` falso retorna
  `np.ones((n, W))` e conta chamadas — assim você verifica skip incremental (mesmo `(path, mtime)` → 0
  chamadas novas), reembedding (mtime muda) e reconciliação (item sai da lista). `split_text` roda de
  verdade (barato).
- **`index_dir()`**: `monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))` ou patch direto
  do atributo do módulo nos callers.
- **`bm25`/busca híbrida (Tier A)**: `build_bm25_index`/`bm25_score` são puros (`rank_bm25` já é dependência
  base, sem `importorskip`) — mas cuidado com IDF degenerado em corpus ≤2 docs (`log((N-n+0.5)/(n+0.5))`
  bate 0/negativo quando o termo não é minoria; use ≥3 documentos nos testes de ranking). `VectorStore._bm25`
  é um 2º cache lazy ao lado de `_normalized`, invalidado pelos mesmos `add()`/`drop_source()` — teste os
  dois juntos (mesmo padrão: comparar identidade do objeto, não só o valor). `retriever._reciprocal_rank_fusion`
  usa `np.lexsort((idx, -scores))`, não `argsort(...)[::-1]`, deliberadamente: a reversão de um argsort
  ascendente inverte a ordem de desempate em empates, o que pode fazer um sinal totalmente neutro (BM25 sem
  nenhum match) **cancelar** uma preferência clara do outro sinal quando há poucos candidatos — achado real
  ao escrever os testes, não uma hipótese.

---

## Core Receitas (`src/core/recipes/`) — `STEP_REGISTRY` mockado, sem core real

O runner é testável sem tocar ffmpeg/Whisper: substitua os adaptadores reais por fakes via `patch.dict` e
injete um `emit`/`cancel_is_set` simples.

- **`runner` (encadeamento/cancel/erro/lote)**: `mocker.patch.dict(STEP_REGISTRY, {"t.s1": StepSpec(adapter,
  frozenset({"url"}), "audio", "S1"), ...})` com adapters que retornam `[tmp_path/"x"]`.
  `emit=lambda t, p: eventos.append(...)`, `cancel_is_set` com contador p/ disparar no N-ésimo passo. Asserir
  a ordem dos tipos (`recipe_start → progress_start → step_start/done×N → task_done`), encadeamento (output de
  um vira input do próximo), `emit_terminal=False` (sem `progress_start`/`task_done`; falha vira `log`), e
  `execute_recipe_batch` (um `queue_progress` por entrada, `failed_count`, cancel entre entradas).
- **adaptadores reais (`registry`)**: mocke a função de **core no seu módulo de origem**
  (`mocker.patch("src.core.audio.normalizer.normalize_lufs", return_value=...)`) — como cada adaptador faz
  `from X import Y` function-local, patchar a origem funciona **e** um rename de core faz o `patch` falhar
  (pega drift de assinatura). Para dirs canônicos, `monkeypatch.setattr(src.utils, "TRANSCRIPTIONS_TEXT_DIR",
  tmp_path)`. `ai.answer`: mocke `embedder.is_available`/`scan_library`/`build_index`/`VectorStore.load`/
  `retrieve`/`chat.answer` e redirecione `TRANSCRIPTIONS_ANALYSIS_DIR`.
- **`store`**: round-trip em `tmp_path` (passe `path=` explícito — não toque `~/.mill-tools`); `presets`:
  valide cada um contra todo kind do `accepts` do 1º passo.

> O teste do **worker GUI** de Receitas (bus falso) fica em [`mocks-gui-cli.md`](mocks-gui-cli.md).

---

## Core ML (`src/core/ml/`) — numpy-puro; sklearn só no `store` (Plano 3)

Fundação de ML, testável sem rede e (na maior parte) sem o extra `[ml]`:

- **`features`/`dedup` (sem `importorskip`)**: numpy-puros. Construa um `VectorStore` sintético com vetores
  estreitos (dim 3–8) e `source_path` conhecido; `document_matrix` deve fazer mean-pool por documento (ex.:
  2 chunks → média), L2-normalizar quando pedido, preservar **ordem first-seen** e `float32`, e devolver
  `(0, D)` no store vazio. `load_document_matrix` faz round-trip de um `VectorStore` persistido em `tmp_path`
  (reusa `store.persist`). `dedup.near_duplicates`: plante linhas idênticas/ortogonais (idêntico → grupo no
  limiar; ortogonal → não agrupa), cadeia transitiva A≈B≈C → um componente, `score` = menor cosseno
  par-a-par, `max_docs` excedido → `[]` + warning (`caplog`).
- **`deps`**: `is_available()` True com sklearn; False via `mocker.patch.dict(sys.modules, {"sklearn": None})`
  (padrão do `embedder`).
- **`store` (`importorskip("sklearn")`)**: round-trip `save_model`/`load_model` com um estimador pequeno
  (`StandardScaler().fit(...)`) em `tmp_path` (`directory=` injetável — não toque `~/.mill-tools`);
  **mismatch de versão** → `None` (`monkeypatch.setattr(store, "_sklearn_version", lambda: "0.0.0")`);
  **mismatch de signature** → `None`; sidecar ausente/corrompido e artefato `.joblib` corrompido → `None`.

### Plano 4A — semântico (`cluster`/`project`/`labeling`/`recommend`/`cache`/`mapviz`)

- **`recommend` (sem `importorskip`)**: numpy-puro. `related` — vizinhos plantados no topo, exclui o próprio,
  respeita `k`, esgota corpus, doc inexistente → `ValueError`; reranking por **MMR** (vetores ortogonais com
  relevância bem separada → reduz a top-k puro; par quase-duplicado + candidato diverso → MMR prefere o
  diverso ao invés do duplicado); `in_corpus` — acima/abaixo do limiar, store vazio → `(False, 0.0)`.
- **`cluster`/`labeling`/`project` (`importorskip("sklearn")`)**: blobs sintéticos ortogonais em dim estreita
  (jitter pequeno) → `n_clusters` esperado; outlier isolado → `-1`/`n_noise`; k-means com `k`; **k-means com
  `k=None`**: corpus grande (≥ `_MIN_FOR_AUTO_K`, blobs de k conhecido) → auto-seleção acha o k certo via
  `silhouette_score`; corpus pequeno → `ValueError` preservado (mesma mensagem de antes); `_auto_k` chamada
  direta cobre o guarda defensivo do range de candidatos. `M<min_cluster_size` → tudo ruído; método inválido
  / k-means sem `k` / gate off (`mocker.patch(...is_available, return_value=False)`) → erro. c-TF-IDF
  (`ngram_range=(1,3)`, `reduce_frequent_words`): vocabulário distinto → termos discriminativos no topo
  (inclui frases de até 3 palavras), `-1` ignorado, stopwords removidas, só-stopwords → vazio. PCA: shape
  `(M,2)`, **determinismo** (duas execuções idênticas via convenção de sinal), pad degenerado (D=1); **TSNE**:
  shape `(M,2)`, `_tsne_perplexity` parametrizada (piso 1.0, teto 30.0, sempre `< n_samples`), corpus de 2
  documentos não lança, pré-redução PCA exercida com D>50; UMAP → `importorskip("umap")` (pulado sem o extra;
  `_umap_2d` tem `# pragma: no cover`).
- **`cache`**: `corpus_signature` estável a reordenação/multiplicidade, muda com mtime; `save_map`/`load_map`
  round-trip em `tmp_path`; mismatch de signature/versão e arquivos corrompidos (sidecar/npz) → `None`.
- **`mapviz` (`importorskip("sklearn")`)**: `build_semantic_map` clusteriza+rotula+cacheia (**spy** em
  `cluster_documents`: 1× com cache, 2× com `use_cache=False`); `cluster_display_name`;
  `render_semantic_map_png` → PNG válido (Pillow), mapa vazio / charts ausente → erro. **`on_stage` (Tier A)**:
  callback chamado em `["cluster","project","label"]` nessa ordem exata (a ordem real do código — a prosa do
  plano original tinha `project`/`label` trocados); **pulado inteiramente** em cache hit (nenhum estágio de
  fato roda).
- **`classify` (Tier A — `domain` parametrizado)**: domínio default preserva os nomes de arquivo pré-existentes
  (`_proto_filenames`/`_model_name`/`_labels_json_name` do domínio `DOMAIN_TRANSCRIPTION_PROFILE` == as
  constantes antigas — teste de regressão explícito); domínios novos (`DOMAIN_DATA`/`DOMAIN_DOCUMENT`) não
  vazam ids de protótipo um pro outro; rótulos gravados num domínio não aparecem em `load_labels` de outro
  (isolamento por arquivo, não por processo).
- **`charts.render_category_scatter`** (`tests/core/data/test_charts.py`): scatter categórico → PNG válido,
  vazio/coluna inexistente → erro, >12 categorias sem legenda, thread-safe (dois renders concorrentes).
- **GUI (Plano 4A)**: `semantic_map_panel` por **construct-smoke** (`build_*` com `MagicMock` pega erro de
  construtor que o import-smoke não pega) + gates (ml/índice vazio); worker da IA marca `low_confidence`
  quando o query é ortogonal ao acervo (e não quando coberto), via `hits[0].score` sem re-embeddar.

---

## Core Dados (`src/core/data/`) — DuckDB in-process (qualifica como `unit`)

DuckDB roda in-process (sem ffmpeg/rede/GPU), então os testes de dados são `unit` como os do RAG. Fixtures
locais em `tests/core/data/conftest.py` (`csv_sales`, `csv_people_cp1252`, `json_file`). Arquivos:
`test_validate`/`test_engine`/`test_scanner`/`test_convert`/`test_profile`/`test_nl2sql`/`test_store` +
(PR9.3) `test_assess`/`test_datacard`.

- **`engine.preview`/`reader_expr`/`xlsx_sheet_names`** (`test_engine.py`): use `csv_sales` real;
  `preview(limit/offset)` janela linhas; `reader_expr(.xlsx, sheet=)` deve emitir `sheet = '...'` (aspas
  escapadas) e **ignorar** `sheet` em CSV; para `xlsx_sheet_names`, monte um XLSX mínimo com `zipfile` + um
  `xl/workbook.xml` (declare o ns `r:`!) — zip corrompido / não-XLSX → `[]`.
- **`profile.summarize_sql`** (puro): abaixo do threshold → `SUMMARIZE "view"`; acima → `SUMMARIZE SELECT *
  FROM "view" USING SAMPLE n ROWS`. `profile_text` retorna o relatório sem gravar.
- **`assess`** (`test_assess.py`): LLM via `GenericFakeChatModel` (injete `make_llm_fn=lambda *a, **k:
  _fake_llm(...)`); o prompt não tem chaves literais (valores com `{` são seguros). Cache: passe
  `cache_file=tmp_path/...` em `load/save_assessment`; mudar o mtime do arquivo invalida; cache malformado →
  miss; salvar p/ arquivo inexistente é no-op.
- **`datacard.build_data_card`** (puro): asserir seções ARQUIVO/SCHEMA/PERFIL/AMOSTRA e que `AVALIAÇÃO DA IA`
  só aparece com `assessment=`; `card_for_path` lê arquivo real e dobra a avaliação cacheada (mocke
  `assess._cache_file`).
- **indexer `kind="data"`** (`tests/core/rag/test_indexer.py`): `build_index(..., card_fn=...)` embeda o
  cartão (não o arquivo); sem `card_fn`, itens de dados são pulados; `card_fn` que levanta pula só aquele
  item; `indexable_items` inclui `kind="data"` por kind (qualquer sufixo). **`index_files`** (aditivo, sem
  reconciliação, usado pelo botão Indexar da aba Pré-visualização): indexar só o arquivo B **não** derruba A
  já indexado; reembeda a cada chamada (ação explícita, sem skip por mtime); `card_fn` que falha pula só aquele.
- **`ml.detect_outliers`** (`test_ml.py`, Tier A — `pd = pytest.importorskip("pandas")` +
  `pytest.importorskip("sklearn")`, sem fixture de arquivo — DataFrame sintético direto): linha bem fora da
  distribuição → menor `ANOMALY_COLUMN` (mais anômala); ordem de linhas e colunas não-numéricas preservadas;
  NaN numérico não lança (mean-imputado antes de `IsolationForest`, que rejeita NaN); sem coluna numérica →
  `ValueError`.
