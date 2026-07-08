---
name: ml-rag
description: Guia único do RAG local, do ML clássico, do NLP textual e do Observatório do mill.tools — os pacotes core/rag, core/ml, core/text e core/observatory. Invocar ao mexer em RAG (embeddings, índice, busca híbrida BM25+denso, chat com citação), ML (dedup, cluster, labeling, project, recommend/MMR, classify por domínio, outliers), NLP (YAKE keyphrases, TextRank, spaCy NER), ou no hub Observatório (activity/logs/status/model_timing/disk_usage). Cobre também os modelos Ollama (*-custom, num_ctx, quirks), os gates dos extras [ml]/[ml-viz]/[nlp] e as persistências em ~/.mill-tools/. Superfícies de CLI (ai/observatory) → skill cli; de GUI (hubs IA/Observatório) → skill design-system; onde o código mora → skill architecture.
---

# mill.tools — RAG, ML, NLP e Observatório

Dono único do assunto que mais cresceu. Todo o resto (`CLAUDE.md`, outras skills) **aponta** para cá. O que
mora onde e limites de tamanho → skill `architecture`; superfícies → `cli` (subcomandos `ai`/`observatory`) e
`design-system` (hubs IA/Observatório).

## Mapa dos pacotes (todos em `src/core/`, puros)

| Pacote | Responsabilidade |
|---|---|
| `core/rag/` | RAG local: embedder (única rede) · store `.npz` · busca híbrida · indexer incremental · chat com citação · bm25 · templates · batch · stats · analytics |
| `core/ml/` | ML clássico torch-free: features (acessor) · dedup · cluster · labeling · project · recommend · classify/ (pacote) · store (modelos versionados) · deps (gate `[ml]`) · cache · mapviz |
| `core/text/` | NLP textual (Plano 4B, independente de `core/ml`): keywords (YAKE) · summarize (TextRank) · entities (spaCy NER) · reader · lang |
| `core/observatory/` | Cross-módulo read-only: activity · logs · status · model_timing · disk_usage |

---

## `core/rag/` — RAG local

- **`embedder.py` é a única rede** (injetável como `embed_fn`; o resto é unit-testável sem Ollama).
  Embeddings **100% locais** (Ollama, `nomic-embed-custom`, CPU `num_gpu 0`, 768-dim, torch-free).
  **Prefixos de tarefa** (`PLANO_RAG_ESPACO_EMBEDDING`, jul/2026): `embed_texts` prepends
  `"search_document: "` e `embed_query` prepends `"search_query: "` — o `nomic-embed-text` foi treinado
  com esses prefixos (exatos, com espaço; confirmado no card do modelo) e sem eles documento/pergunta caem
  no mesmo espaço "sem tarefa". Chaveado por família (`_prefixes_for`, qualquer tag contendo `"nomic"`); um
  modelo fora dela embedda sem prefixo. Verificado (context7 + `ollama/Modelfile.nomic`) que nada no
  caminho já prefixava sozinho — nem o `TEMPLATE {{ .Prompt }}` do Modelfile (herdado da base, sem
  wrapper) nem `langchain_ollama.OllamaEmbeddings`, que repassa o texto cru ao `/api/embed`.
- **`VectorStore`** (`store.py`): matriz numpy `(N,D)` + persistência `.npz`/`.json` em `~/.mill-tools/rag/`.
  Caches lazy de `_normalized` **e `_bm25`**, ambos invalidados por `add()`/`drop_source()`. `persist()` grava
  sidecar `index_info.json` (`embed_model`, `dim`, **`embed_scheme`**); índices antigos → `embed_model="?"`/
  `embed_scheme="?"`. **`load()` tolera corrupção** (`PLANO_CORRECOES_RAG_ML_2.md`, Fase 2): `vectors.npz`/
  `meta.json` truncados ou inválidos (`zipfile.BadZipFile`/`ValueError`/`OSError`/`KeyError`/`EOFError`)
  viram store vazio + warning, não exceção crua — mesma paridade de `classify.prototypes._load_prototypes`.
- **Busca híbrida** (`retriever.retrieve()`): cosseno denso + **BM25** (`bm25.py`) combinados por **Reciprocal
  Rank Fusion** (`np.lexsort((idx, -scores))`, não `argsort[::-1]` — ver skill `testing` p/ o porquê). BM25
  tokeniza via regex (`re.findall(r"\w+", text.lower())`, sem pontuação) nos **dois** lados (índice e query) —
  não um `.split()` ingênuo. A fusão RRF é **pulada** (fallback pro cosseno denso puro) quando o BM25 não tem
  nenhum match (`lexical.max() <= 0`), evitando que um sinal neutro injete viés de ordem-de-índice. O `.score`
  reportado por chunk continua o **cosseno denso** (não o valor fundido) — preserva o contrato do aviso de
  fora-de-escopo.
- **`indexer.build_index()`** é **incremental** por `(path, mtime)`: pula inalterados, reembeda alterados,
  reconcilia removidos. Indexa kinds textuais (`transcription`/`document` + descrições `.txt`), tira o header
  de transcrição, chunka via `split_text` (1200/150). Aceita **`card_fn` injetável** e inclui `kind="data"` —
  arquivos de dados são indexados pelo **cartão de dados** (`core/data/datacard.card_for_path`), nunca pelas
  linhas cruas. `index_files` é a variante **aditiva** (sem reconciliação, sempre reembeda) usada pelo botão
  "Indexar no RAG" da aba Pré-visualização do módulo Dados.
- **Limpeza + header contextual** (`PLANO_RAG_ESPACO_EMBEDDING`, jul/2026): `_read_indexable_text` passa o
  corpo por `core/text/clean.clean_document_text` antes de chunkar (kinds texto, não `card_fn`) — marcadores
  `--- Página N ---` e boilerplate de PDF param de ser embeddados/citados como conteúdo (resolve o ponteiro
  que estava no ROADMAP). Cada chunk ganha uma linha de contexto (`"{stem} — {kind}:\n"`) prependada **só**
  no texto passado a `embed_fn` — `ChunkMeta.text` continua o chunk cru, então BM25 (construído sobre
  `m.text`) e as citações ficam intactos. `indexer.CURRENT_EMBED_SCHEME` é o marcador de versão desse
  conteúdo (junto com os prefixos do embedder) — bump aqui sempre que uma mudança exigir reindexação;
  **fonte única**, nunca criar um segundo mecanismo de versionamento.
- **`batch.run_batch`** aceita `cancel_is_set: Callable[[], bool] | None`, checado entre itens (mesmo padrão
  do runner de Receitas) — hoje é só o *seam* no core: não há worker de GUI que chame `run_batch` (o hub IA só
  tem a Conversa single-answer) nem mecanismo de cancelamento no `cli/ai.py --batch` (Ctrl+C já cobre o caso
  síncrono); pronto para quando um chamador cancelável de verdade existir. **Isolamento de falha por
  documento** (`PLANO_CORRECOES_RAG_ML_2.md`, Fase 1): um erro de LLM/retrieval num documento é logado
  (`logging.warning`) e **pulado**, no mesmo contrato "log + skip" de `indexer._index_one` — não aborta os
  demais nem devolve um campo de erro no `BatchResult`. `cli/ai.py --batch` reporta quais documentos faltam
  comparando `sources` (entrada) contra os `source_path` dos resultados devolvidos (sem campo novo).
- **`chat.answer()`** monta contexto numerado `[n]` sob prompt estrito; o **`[n]` é chaveado pelo documento
  distinto** (chunks do mesmo arquivo compartilham número) — as citações nunca passam do total de fontes.
- **`stats.py`** (puro): `index_stats(directory) → IndexStats` (docs, chunks, dim, modelo, **esquema**,
  tamanho, `per_doc`); `fmt_status_line()`, `fmt_disk_size`/`fmt_thousands`/`fmt_datetime`/`chunks_for` (mês
  PT-BR manual, sem `locale`). `embed_space_id(directory)` compõe **`"{modelo}:{dim}:{esquema}"`** (esquema
  = `indexer.CURRENT_EMBED_SCHEME` no momento da indexação; `"?"` p/ índice sem o campo). `is_stale_scheme
  (stats, current_scheme)` compara o esquema persistido contra o do código em execução — `stats.py` não
  importa `indexer` (fica puro); quem chama injeta `CURRENT_EMBED_SCHEME`. Usado pela linha de status do
  hub IA e pelo card "Modelo" da aba Índice/RAG do Observatório para sinalizar "esquema antigo — reindexe"
  (a migração continua sendo o botão Reindexar existente). `analytics.py` (Plano 2): `index_health` + timing
  por modelo (p90 via `statistics`).
- **Gate**: `embedder.is_available(model, use_cache=False)` bloqueia os fluxos com `SETUP_HINT`; usa um
  timeout curto próprio (`AVAILABILITY_TIMEOUT=10s`) para o ping, distinto do `EMBED_TIMEOUT=300s` do
  embedding real (senão o status board do Observatório pendura por até 5 min quando o Ollama está fora do
  ar). `use_cache=True` (opt-in, TTL 60s via `AVAILABILITY_CACHE_TTL`, chaveado por modelo) poupa um ping por
  pergunta no **hot path** da Conversa (`run_ai_answer`) — fluxos frios (status board, gate de reindexação,
  CLI) mantêm o default `False` para nunca reportar um veredito velho.

> `rank-bm25` é dependência **base** (puro Python/numpy, sem scipy) — não atrás de extra, porque a busca densa
> do RAG já é incondicional. Racional da escolha (vs. `bm25s`) → `docs/HISTORY.md`.

---

## `core/ml/` — ML clássico (torch-free)

- **`features.py`** (acessor, **numpy-puro, sem gate**): mean-pool dos chunks do `VectorStore` em vetores de
  documento (L2-norm, ordem first-seen, `float32`). A decisão de pooling/normalização é **única** e herdada
  por todos os consumidores dos Planos 4/5. Não recalcula embedding — reusa o `VectorStore` persistido.
- **`dedup.py`** / **`recommend.py`** (numpy-puros, sem gate): duplicatas por cosseno (componentes conexas,
  guard `max_docs`); `related`/`in_corpus` com reranking por **MMR**.
- **`cluster.py`** (`[ml]`): HDBSCAN (auto-k, ruído=-1) / k-means (`k=None` → auto-seleção por
  `silhouette_score` acima de 20 docs). **`labeling.py`**: c-TF-IDF estilo BERTopic (`CountVectorizer`,
  `ngram_range=(1,3)` + `reduce_frequent_words`, stopwords PT/EN próprias). **`project.py`**: PCA
  determinística (default) · TSNE · UMAP (`[ml-viz]`, métrica cosseno + pré-redução PCA→50D).
- **`classify/`** (`[ml]`, pacote — dividido de um `classify.py` de 471 linhas na correção do quarteto ML,
  jul/2026): `prototypes.py` (seeds + cache de protótipos), `labels.py` (rótulos + treino supervisionado +
  `record_label`), `inference.py` (dispatch `classify()`/`has_supervised_model()`), `_naming.py` (nomes de
  arquivo por domínio); `classify/__init__.py` reexporta a API flat pré-existente — zero mudança nos call
  sites. Perfil **zero-shot** por protótipo (`label`+`source_hint`, embeddado 1×, cacheado; nearest-prototype
  por cosseno; `margin`=incerteza) que **escala para supervisionado** (`LinearSVC`+`CalibratedClassifierCV`
  sobre `dm.X`) conforme o usuário confirma o perfil. **Parametrizado por `domain`**
  (`DOMAIN_TRANSCRIPTION_PROFILE`/`DOMAIN_DATA`/`DOMAIN_DOCUMENT`) — mesmas funções, chaveadas por prefixo de
  arquivo; o domínio default preserva os nomes pré-existentes (zero invalidação de cache). **Seeds bilíngues**
  (`PLANO_CORRECOES_RAG_ML_2.md`, Fase 3): `_DATA_DOMAIN_SEEDS`/`_DOCUMENT_TYPE_SEEDS` carregam a frase em
  inglês **e** em português no mesmo texto de protótipo — o corpus desses dois domínios é majoritariamente
  PT-BR e o `nomic-embed` é fraco cross-língua; seeds só-EN deprimiam a margem artificialmente. Os seeds de
  perfil de transcrição (derivados de `label`+`source_hint`, já PT) não precisam disso. `_seeds_signature`
  invalida o cache sozinha ao mudar o texto — zero migração.
- **Cegueira ao embed model (corrigida)**: as assinaturas de cache de protótipos **e** do modelo
  supervisionado dobram o `embed_space_id` (`"{modelo}:{dim}:{esquema}"`, de `rag.stats.embed_space_id` —
  o componente de esquema veio com o `PLANO_RAG_ESPACO_EMBEDDING`) — trocar o embed model **ou** reindexar
  sob um esquema novo costumava deixar protótipos/SVM do espaço antigo válidos e prevendo lixo em silêncio,
  já que a assinatura não mudava. Índice sem sidecar/campo → `"?"`. Threading: `classify()` /
  `has_supervised_model()` / `profile_prototypes()` / `train_supervised()` / `maybe_train()` recebem
  `embed_space_id: str = "?"`; os call sites de produção (`cli/ai.py`, `gui/views/profile_section.py`,
  `observatory/status.py::domain_statuses`) leem o valor real via `rag.stats.embed_space_id(index_dir())`.
  **Mesma cegueira existia no mapa semântico** (`ml/cache.corpus_signature`, assinado só por
  `(source_path, mtime)`): `corpus_signature`/`mapviz.build_semantic_map` agora também aceitam
  `embed_space_id` e o dobram no hash — os dois call sites (`cli ai map`/`topics`, painel semântico da
  Biblioteca) passam o valor real em vez de deixar o mapa cacheado servir vetores do espaço antigo.
- **`store.py`** (`[ml]`): persistência de modelos versionada por `sklearn.__version__`+signature (invalida no
  mismatch; joblib v1). **`mapviz.py`**: orquestra cluster→project→label → `SemanticMap` → PNG;
  `build_semantic_map` aceita `on_stage` (stepper do Observatório; pulado em cache hit). **`cache.py`**: mapa
  versionado por `corpus_signature`. **`deps.py`**: gate `[ml]` (scikit-learn ≥1.4).
- **`core/data/ml.py`** (`[ml]`): `detect_outliers` via `IsolationForest` sobre `frames.to_pandas`
  (`_anomaly_score`, NaN mean-imputado). **`core/image/dhash.py`** (zero-dep): perceptual hash p/ dedup de
  imagens (`core/library/image_dedup.py`) — hand-rolled, não `imagehash` (evita scipy; racional → HISTORY).

---

## `core/text/` — NLP textual (extra `[nlp]`)

- **`keywords.py`** — YAKE (estatístico, torch-free). **`summarize.py`** — TextRank **self-contained** sobre o
  `TfidfVectorizer` do `[ml]` (sem download nltk, sem dep nova). **`entities.py`** — spaCy NER **CNN**
  (`pt_core_news_sm`, singleton lazy; **nunca `_trf`**, que puxaria torch). **`reader.py`**/**`lang.py`** —
  corpo do doc (header-strip) e heurística PT/EN.
- **`clean.py`** (`PLANO_INSIGHTS_QUALIDADE.md`) — fonte única de limpeza de texto extraído de PDF: derruba
  marcadores de página, pontua itens de lista sem fronteira de sentença, filtra linhas curtas sem pontuação
  terminal (front matter tipo título/autor/data) e mascara/desmascara abreviações (`e.g.`, `i.e.`, `et al.`,
  `Dr.`, `Sr.`, `Sra.`, `p. ex.`). `core/document/converter.py::extract_text` gera o marcador via
  `clean.page_marker()` — mesma string, fonte única (antes duplicava o literal). **Consumida internamente**
  por `summarize.extractive_summary`/`keywords.keyphrases` (qualquer chamador — GUI ou CLI — se beneficia sem
  precisar limpar antes) e explicitamente pelo `insights_panel` (uma chamada, três engines — ver abaixo).
  **Nunca consumida por `entities()`**: front matter carrega entidades PER/ORG/DATE legítimas ("Anthropic",
  "January 2024") que o NER se beneficia de ver — só o hub Insights opta por alimentá-lo com o texto limpo
  mesmo assim, por consistência visual entre as três seções do painel, não por precisar da limpeza.
  `reader.py` **não** foi alterado (fica fino, só o header-strip de sempre) — a limpeza é responsabilidade de
  cada engine que a usa, não da leitura em si; isso preserva o acesso do `entities()` ao texto cru via CLI
  (`cli/ai.py entities`), que continua sem tocar `clean.py`.
- **Prior de posição pós-filtro** (`summarize.py`, Fase 3): o filtro de sentenças candidatas
  (`_is_summary_candidate` — `clean.is_prose_line` + teto de palavras) roda **antes** do grafo do TextRank
  ser montado, então o lead-position prior (`_POSITION_BIAS_WEIGHT = 0.15`) já opera só sobre sentenças
  reais — não precisou de ajuste por `kind` (o filtro pós-boilerplate sozinho bastou, confirmado pela fixture
  de reprodução `messy_pdf_text`). `split_sentences` mascara/desmascara abreviações internamente, ao redor do
  `_SENT_BOUNDARY`.
- **Modelo spaCy** é download à parte (como o Tesseract): `uv sync --extra nlp && uv run python -m spacy
  download pt_core_news_sm`. `en_core_web_sm` (`uv run python -m spacy download en_core_web_sm`) é
  **opcional-recomendado** para acervo com material em inglês. `entities.is_available()` checa **pacote e
  modelo**; `entities.availability(lang)` (Fase 4, `PLANO_INSIGHTS_QUALIDADE.md`) devolve `None`/hint
  específico — distingue "falta o extra `[nlp]`" de "falta só o modelo de `lang`", já que um PDF em inglês
  com todos os extras instalados mas sem `en_core_web_sm` mostrava a mesma mensagem genérica dos dois casos.
- **Glossário opcional de domínio**: `~/.mill-tools/entity_glossary.json` (`[{"label":…, "pattern":…}]`),
  lido 1× no 1º carregamento por idioma (singleton em cache — não trocável por chamada), adicionado antes do
  `ner` estatístico. Sem o arquivo, comportamento idêntico; não há CLI/GUI para editá-lo.

### `core/text/nl2cli.py` — NL→CLI (não é NLP clássico; mora aqui por forma, não por família)

`to_command(question, reference, make_llm_fn, *, model, validate_fn)` traduz um pedido em português no
comando `uv run main.py ...` equivalente. Análogo direto a `core/data/nl2sql.py` (mesmo padrão de prompt
estrito → JSON `{"command", "explanation"}` → parsing defensivo), com uma diferença: **retry** — se
`validate_fn(command)` reprovar (ou a resposta não vier em JSON), reprompta 1× anexando o erro; segunda
falha levanta `NL2CLIError`. Comando vazio (`""`) é uma **recusa deliberada** (pergunta fora do escopo do
app) — nunca passa por `validate_fn`.

- **`reference`/`validate_fn` são sempre injetados** — o núcleo nunca importa `cli/`. Quem amarra é o
  chamador: `gui/modules/ai/worker.py::run_ai_command` (hub de IA, modo "Comandos CLI") e
  `cli/ai.py::_nl2cli` (`ai --cmd`) — ambos usam `cli/reference.build_reference()`/`validate_command()`.
  **A exceção de camada `gui/ → cli/reference.py`** (`gui/` normalmente só importa `core/`) está registrada
  e comentada só em `run_ai_command`; ver skill `architecture` e `docs/HISTORY.md`.
- **Gate é só o `make_llm` (Ollama de chat)** — nunca o embedder, porque este modo não faz retrieval
  nenhum. `ollama_inventory().reachable` (de `core/observatory/status.py`) checa o serviço; pulado quando o
  modelo escolhido é de nuvem (`llm_factory.is_cloud_model`), já que aí não há Ollama envolvido.
  `llm_factory.OLLAMA_SETUP_HINT = "ollama serve"` é o hint genérico (distinto do `embedder.SETUP_HINT`,
  que é específico do modelo de embedding).
- **Decisão de arquitetura (`PLANO_NL2CLI_HUB_IA.md`)**: prompt direto com few-shot em PT, **não** RAG — o
  corpus de CLI inteiro (~54 operações, ~8,5k chars via `cli/reference.build_reference()`) cabe no contexto
  de um modelo local (`DEFAULT_OLLAMA_NUM_CTX = 8192`); RAG trocaria "o modelo vê tudo" por "vê top-k", o que
  pioraria a acurácia num corpus desse tamanho. Só reabrir se o corpus de CLI multiplicar de tamanho.
- **`cli/reference.py`** (camada `cli/`, não `core/`) constrói a referência por **introspecção real dos
  parsers argparse** (`_SubParsersAction`/`_choices_actions`) — nunca texto hardcoded, zero drift quando uma
  flag nova é adicionada a qualquer subcomando. `validate_command()` roda o `parse_args()` real do mesmo
  parser descartável (patch temporário de `ArgumentParser.error` captura a mensagem de qualquer parser da
  árvore, incl. sub-subcomandos como `video trim`) — fecha o ciclo sem executar nada.

---

## `core/observatory/` — hub read-only cross-módulo

Zero dependência nova; agrega o que já existe em outros módulos.

- **`activity.py`** — log append-only cross-módulo (`ActivityEntry`, cap 200) em `~/.mill-tools/ml_activity.json`.
  Escrito pelos **workers/CLI runners** no ponto de conclusão (RAG dedup/classify, Dados outliers, Biblioteca
  dedup de imagens, e a GUI da Transcrição: `profile_suggested`/`profile_labelled`) — **nunca** pelas funções
  puras de `core/ml`/`core/text`.
- **`logs.py`** — 2º log append-only, mas de **falhas** (`LogEntry`, cap 100) em `~/.mill-tools/ml_logs.json`;
  alimentado por um **hook central em `gui/events.py::EventBus.emit()`** (todo `task_error` da GUI, exceto
  cancelamentos) — sem tocar em nenhum `worker.py`.
- **`status.py`** — agregador read-only: `gate_statuses()` (9 gates), `entity_glossary_status()`,
  `binary_statuses()` (yt-dlp/ffmpeg/ffprobe/tesseract via `shutil.which`), `ollama_inventory()`
  (`ollama.Client(timeout=5).list()`, degrada sem lançar), `cloud_provider_statuses()` (só **presença** de
  `GOOGLE_API_KEY`/`ZHIPU_API_KEY`, nunca o valor), contagem de rótulos por domínio, `config_snapshot()` (lê
  defaults reais via `inspect.signature`, nunca cópia hardcoded).
- **`model_timing.py`** — log persistente cumulativo de latência por `(domain, model)` (`domain ∈
  {"llm","vlm","embed"}`, cap **500 por par**) em `~/.mill-tools/model_timings.json`. Instrumentado na fonte:
  `llm_factory.make_llm()` anexa um `_TimingCallback` a todo modelo (cobre Formatter/Analyzer/Prompter/RAG
  chat/`data.assess`/`data.nl2sql` sem tocar esses arquivos); `describe_image` passa `domain="vlm"`;
  `embedder.py` mede manualmente (LangChain `Embeddings` não expõe callbacks). **Não confundir** com
  `ai_answer_times` (`config.json`, janela móvel de 5, só a estimativa "tempo típico" da Conversa da IA) — são
  paralelos, sem dual-write.
- **`disk_usage.py`** — scanner genérico de `~/.mill-tools/` (`DiskUsageEntry` recursivo, maior primeiro); não
  lista nomes hardcoded — um store novo aparece sozinho. Reusa `rag/stats.fmt_disk_size`.

> **Por que hub próprio (não aba do hub de IA)**: a superfície de ML cobre RAG/Biblioteca/Transcrição/Dados/
> Receitas — aninhá-la na IA seria descasamento semântico. Ver `docs/HISTORY.md` (decisão) e o plano em
> `docs/plans/implemented/PLANO_ML_NOVAS_FEATURES.md`.

---

## Regras de fronteira (invioláveis)

1. **Embeddings sempre locais** (Ollama, na indexação). Gemini/GLM entram **só** no passo de resposta e
   sempre opt-in.
2. **`.score` = cosseno denso**, não o valor fundido do RRF — contrato do aviso de fora-de-escopo (o worker
   deriva `low_confidence` do **`max(h.score for h in hits)`** sem re-embeddar, compara com
   `recommend.DEFAULT_IN_CORPUS_THRESHOLD`). Não é `hits[0].score`: `hits` vem ordenado pela fusão RRF, cujo
   primeiro lugar não é necessariamente o de maior cosseno denso — um chunk lexicalmente forte porém
   semanticamente mediano podia vencer a fusão e disparar o aviso de fora-de-escopo com o corpus cobrindo bem
   a pergunta (`PLANO_CORRECOES_RAG_ML_2.md`, Fase 1).
3. **A IA de dados recebe só schema/cartão**, nunca as linhas cruas (privacidade: com nuvem, só nomes de
   coluna saem da máquina).
4. **Funções puras de `core/ml`/`core/text` nunca escrevem log** — quem grava `activity`/`logs` é o
   worker/CLI runner no ponto de conclusão.

---

## Gates e extras

| Extra | Cobre | Gate |
|---|---|---|
| (nenhum) | `features`/`dedup`/`recommend` (numpy-puro), `bm25`/`rank-bm25` (base), `dhash` (Pillow+numpy) | — |
| `[ml]` | scikit-learn ≥1.4: cluster/labeling/project(PCA,TSNE)/classify/store/outliers | `deps.is_available()` |
| `[ml-viz]` | UMAP (projeção 2D alternativa; puxa numba) | `importorskip("umap")` |
| `[nlp]` | YAKE + spaCy (keyphrases + NER) | `entities.is_available()` (pacote+modelo) |
| embedder | Ollama `nomic-embed-custom` | `embedder.is_available()` + `SETUP_HINT` |

Recurso opcional ausente **desabilita o card/flag com dica** — nunca quebra (degradação graciosa).

---

## Modelos Ollama (`ollama/Modelfile.*`)

CPU-pinned (`num_gpu 0`); Modelfiles minimalistas (sem `SYSTEM`/`temperature` — `make_llm` define a
temperatura por papel).

| Modelo | Papel |
|---|---|
| `nomic-embed-custom` | **embeddings do RAG** — 768-dim, CPU, torch-free. `bge-m3`/`mxbai-embed-large` (multilíngues) foram **descartados por decisão** (`PLANO_CORRECOES_RAG_ML_2.md`): dimensão >1000 dobraria a memória do índice e quebra a suposição `EMBED_DIM=768` — não são um upgrade drop-in, exigiriam retrabalho além da reindexação |
| `gemma3-4b-custom` | Gemma 3 4B (128K ctx) — **default da resposta de RAG e do Analyzer/Prompter local**; ~3,3 GB; sintetiza e cita `[n]` muito melhor que o 1B |
| `gemma3-1b-custom` | Gemma 3 1B (32K) — fallback rápido/baixa-RAM (~815 MB); fraco em síntese |
| `qwen7b-custom` | Qwen 2.5 7B — análise/RAG de máxima qualidade; lento na CPU |
| `phi4mini-custom` | Phi-4 Mini 3.8B — `--format` (formatter) |
| `moondream-custom` | vision — descrição de imagens |

- **`num_ctx`** (`llm_factory.DEFAULT_OLLAMA_NUM_CTX = 8192`): o Ollama usa 2048 por padrão — pequeno demais p/
  o JSON verboso (truncava → JSON inválido). `make_llm`/`_make_ollama` passam `num_ctx` por requisição (vence o
  slider do app Ollama, que é o nível mais baixo de precedência). **Editar `DEFAULT_OLLAMA_NUM_CTX`, não o
  slider.**
- **Bypass de contexto longo** (`bypass_long_context=True` em analyzer/prompter): nuvem pula chunking sempre
  (`is_cloud_model`); locais conhecidos pulam até um teto — `LONG_CONTEXT_LOCAL_BUDGETS` (`gemma3-4b-custom`:
  12000 chars ≈ 3K tokens). Acima do teto, volta a fatiar.
- **Quirk Ollama #10176**: configs que devolvem 8192 dims em vez de 768 → `embedder._check_dim()` warning.
- **Nuvem opt-in**: Gemini (`gemini-2.5-flash`) e GLM (`glm-4.7-flash`) roteados por `llm_factory.make_llm`/
  `is_glm_model`/`is_gemini_model`. GLM via `langchain-openai` (`ChatOpenAI` com `base_url` da Zhipu — evita o
  `ChatZhipuAI` legado; racional → HISTORY).

---

## Persistências em `~/.mill-tools/` (quem grava o quê)

| Caminho | Dono | Conteúdo |
|---|---|---|
| `rag/` (`.npz`/`.json` + `index_info.json`) | `rag/store.persist` | índice do RAG (matriz + metadados + modelo/dim/esquema) |
| `ml/` | `ml/store` | modelos sklearn versionados (classify supervisionado, etc.) |
| `ml_activity.json` | `observatory/activity` | log de sucesso cross-módulo (cap 200) |
| `ml_logs.json` | `observatory/logs` | log de falhas (`task_error`, cap 100) |
| `model_timings.json` | `observatory/model_timing` | latência por `(domain, model)` (cap 500/par) |
| `data_assessments.json` | `data/assess` | avaliação de qualidade da IA, keyed por `(path, mtime)` |
| `library_tags.json` | `library/tags` | auto-tags YAKE por item, keyed por `(path, mtime)` |
| `entity_glossary.json` | (manual) | padrões opcionais do EntityRuler |
| `prompts.json` | `rag/templates` | biblioteca de prompts do usuário |
| `config.json` (chaves `last_ai_*`, `ai_answer_times`, `last_embed_model`) | `gui/settings` | preferências + janela móvel de tempos da Conversa |

---

## Superfícies (ponteiros)

- **CLI** `ai` (index/stats/dups/topics/map/related/classify/keywords/summary/entities/pergunta/`--cmd`) e
  `observatory` (status/activity/logs/disk-usage) → skill **`cli`** (read-only, sem `CLIEventBus`; `ai` usa um
  positional despachado por valor literal; `--cmd` tem prioridade sobre os demais).
- **GUI** hub IA (toggle Corpus|Comandos CLI — ver `nl2cli.py` acima) e hub Observatório (5 abas: Índice/RAG
  · Status · Atividade · Logs · Tempo de resposta) → skill **`design-system`** (abas manuais `visible=`,
  spinner, thread-safety).
- **Reindexação mora no Observatório** (Fase 0b, `PLANO_NL2CLI_HUB_IA.md`, jul/2026): a sub-aba Índice do
  Índice/RAG roda o próprio pipeline (`gui/modules/observatory/index_worker.py`, `module_id="observatory"`,
  worker+view no mesmo padrão de um módulo-ferramenta — botão Reindexar + progresso + Cancelar) em vez de
  bridgear pro hub de IA. O hub de IA mantém só a linha de status do índice (read-only) + um botão "Indexar
  no Observatório" (`nav[0]("observatory", {"tab": "index"})`). `core/observatory/` (o pacote puro) continua
  100% read-only — o pipeline vive só na camada `gui/`.
