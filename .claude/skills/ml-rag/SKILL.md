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
- **`VectorStore`** (`store.py`): matriz numpy `(N,D)` + persistência `.npz`/`.json` em `~/.mill-tools/rag/`.
  Caches lazy de `_normalized` **e `_bm25`**, ambos invalidados por `add()`/`drop_source()`. `persist()` grava
  sidecar `index_info.json` (`embed_model`, `dim`); índices antigos → `embed_model="?"`.
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
- **`batch.run_batch`** aceita `cancel_is_set: Callable[[], bool] | None`, checado entre itens (mesmo padrão
  do runner de Receitas) — hoje é só o *seam* no core: não há worker de GUI que chame `run_batch` (o hub IA só
  tem a Conversa single-answer) nem mecanismo de cancelamento no `cli/ai.py --batch` (Ctrl+C já cobre o caso
  síncrono); pronto para quando um chamador cancelável de verdade existir.
- **`chat.answer()`** monta contexto numerado `[n]` sob prompt estrito; o **`[n]` é chaveado pelo documento
  distinto** (chunks do mesmo arquivo compartilham número) — as citações nunca passam do total de fontes.
- **`stats.py`** (puro): `index_stats(directory) → IndexStats` (docs, chunks, dim, modelo, tamanho, `per_doc`);
  `fmt_status_line()`, `fmt_disk_size`/`fmt_thousands`/`fmt_datetime`/`chunks_for` (mês PT-BR manual, sem
  `locale`). `analytics.py` (Plano 2): `index_health` + timing por modelo (p90 via `statistics`).
- **Gate**: `embedder.is_available()` bloqueia os fluxos com `SETUP_HINT`; usa um timeout curto próprio
  (`AVAILABILITY_TIMEOUT=10s`) para o ping, distinto do `EMBED_TIMEOUT=300s` do embedding real (senão o status
  board do Observatório pendura por até 5 min quando o Ollama está fora do ar).

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
  arquivo; o domínio default preserva os nomes pré-existentes (zero invalidação de cache).
- **Cegueira ao embed model (corrigida)**: as assinaturas de cache de protótipos **e** do modelo
  supervisionado dobram o `embed_space_id` (`"{modelo}:{dim}"`, de `rag.stats.embed_space_id`) — trocar o
  embed model e reindexar costumava deixar protótipos/SVM do espaço antigo válidos e prevendo lixo em
  silêncio, já que a assinatura não mudava. Índice sem sidecar → `"?"`. Threading: `classify()` /
  `has_supervised_model()` / `profile_prototypes()` / `train_supervised()` / `maybe_train()` recebem
  `embed_space_id: str = "?"`; os call sites de produção (`cli/ai.py`, `gui/views/profile_section.py`,
  `observatory/status.py::domain_statuses`) leem o valor real via `rag.stats.embed_space_id(index_dir())`.
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
- **Modelo spaCy** é download à parte (como o Tesseract): `uv sync --extra nlp && uv run python -m spacy
  download pt_core_news_sm`. `entities.is_available()` checa **pacote e modelo**.
- **Glossário opcional de domínio**: `~/.mill-tools/entity_glossary.json` (`[{"label":…, "pattern":…}]`),
  lido 1× no 1º carregamento por idioma (singleton em cache — não trocável por chamada), adicionado antes do
  `ner` estatístico. Sem o arquivo, comportamento idêntico; não há CLI/GUI para editá-lo.

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
   deriva `low_confidence` do `hits[0].score` sem re-embeddar, compara com `recommend.DEFAULT_IN_CORPUS_THRESHOLD`).
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
| `nomic-embed-custom` | **embeddings do RAG** — 768-dim, CPU, torch-free. Alternativas multilíngues (exigem reindexação): `bge-m3`, `mxbai-embed-large` |
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
| `rag/` (`.npz`/`.json` + `index_info.json`) | `rag/store.persist` | índice do RAG (matriz + metadados + modelo/dim) |
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

- **CLI** `ai` (index/stats/dups/topics/map/related/classify/keywords/summary/entities/pergunta) e
  `observatory` (status/activity/logs/disk-usage) → skill **`cli`** (read-only, sem `CLIEventBus`; `ai` usa um
  positional despachado por valor literal).
- **GUI** hub IA (só a Conversa) e hub Observatório (5 abas: Índice/RAG · Status · Atividade · Logs · Tempo de
  resposta) → skill **`design-system`** (abas manuais `visible=`, spinner, thread-safety).
- **Reindexação mora no Observatório** (Fase 0b, `PLANO_NL2CLI_HUB_IA.md`, jul/2026): a sub-aba Índice do
  Índice/RAG roda o próprio pipeline (`gui/modules/observatory/index_worker.py`, `module_id="observatory"`,
  worker+view no mesmo padrão de um módulo-ferramenta — botão Reindexar + progresso + Cancelar) em vez de
  bridgear pro hub de IA. O hub de IA mantém só a linha de status do índice (read-only) + um botão "Indexar
  no Observatório" (`nav[0]("observatory", {"tab": "index"})`). `core/observatory/` (o pacote puro) continua
  100% read-only — o pipeline vive só na camada `gui/`.
