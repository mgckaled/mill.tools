# Histórico de decisões e entregas — mill.tools

Changelog em ordem cronológica inversa. **Uma entrada curta por marco**, com link para o plano
correspondente em [`plans/implemented/`](plans/implemented/) ou [`plans/archive/`](plans/archive/). O
detalhe completo vive no plano linkado; aqui fica só o "o quê + por quê" de cada entrega. Pendências
ficam em [`ROADMAP.md`](ROADMAP.md) e [`plans/active/`](plans/active/).

> Fonte única de história. CLAUDE.md e as skills apenas **apontam** para cá — não narram planos concluídos.

---

## Entregas (marcos)

### Correções do `core/data/` (jul/2026)
Revisão exploratória arquivo-a-arquivo do pacote (14 arquivos, ~1.450 linhas), mesmo formato do quarteto ML,
implementada fase a fase direto no `main`: **3 bugs reais** (`validate.ensure_select` rejeitava a própria
receita pt-BR recomendada pelo docstring de `engine.reader_expr` — `"replace"` como palavra-chave proibida
colidia com a função pura `replace()`; um `;` dentro de literal de string era confundido com um segundo
statement porque o strip de literais rodava depois do check; `nl2sql._extract_payload` usava o índice errado
no fallback de SQL cru em bloco cercado, nunca funcionando no caso pra que foi escrito); **robustez** (`store`/
`assess` migrados para o `io_atomic` do quarteto ML; `resp.content` como lista de blocos — Gemini/tool-call —
agora tolerado por `nl2sql`/`assess` via `extract_llm_text`, promovido de `core/rag/chat._extract_text` p/
`src/llm_utils.py`; `ml.detect_outliers` dropa coluna numérica 100% NaN antes do `fillna(mean)`); **perf/seams**
(`profile.profile_text` aceita um `DataFile` já escaneado — `datacard.card_for_path` parou de escanear o
arquivo 2×; `engine.describe_file` ganhou `connect_fn` injetável, único ponto do engine sem o seam); **miudezas**
(`view_name_for` prefixa stems que colidem com keyword SQL — `select.csv` → view `t_select`; `charts._line`
coage o eixo X via `_numeric` só quando a coluna é de fato numérica, sem quebrar o eixo temporal). Decisão de
convenção de idioma em entrada própria (abaixo). Pendências de baixo risco registradas no `ROADMAP.md` §8
(sheet de XLSX não propagado em consultas; `charts.py`/`engine.py` acima do alvo de tamanho — dividir ao
tocar). Plano: [`plans/implemented/PLANO_CORRECOES_CORE_DATA.md`](plans/implemented/PLANO_CORRECOES_CORE_DATA.md).

### Decisão — mensagens de exceção user-facing do core podem ser em PT (jul/2026)
Fase 0 da revisão exploratória do `core/data/` (14 arquivos, ~1.450 linhas): o pacote é todo PT em mensagens
de exceção (`DataEngineError`, `ConvertError`, `ValueError` dos charts), enquanto `core/ml` é EN — inconsistência
não resolvida entre pacotes. Decisão: exceções *user-facing* (as que chegam cruas à GUI/CLI, sem
transformação) podem ficar em PT — são texto de interface, não código; docstrings/logs/comentários continuam
em EN sem exceção. Formalizado em CLAUDE.md §Convenções e na skill `architecture` §1.3.
[`plans/implemented/PLANO_CORRECOES_CORE_DATA.md`](plans/implemented/PLANO_CORRECOES_CORE_DATA.md).

### Correções do quarteto ML — rag · ml · text · observatory (jul/2026)
Revisão exploratória arquivo-a-arquivo dos 4 pacotes (37 arquivos, ~4.370 linhas) virou um plano de 6 fases,
implementado sessão a sessão direto no `main`: **infra compartilhada** (escrita atômica em
`core/io_atomic.py`; log JSON genérico em `observatory/_jsonlog.py`, incl. mitigação do hot path de
`record_timing`); **`core/rag/`** (bug real do `index_health` que nunca marcava documento stale; tokenização
BM25 sem pontuação; timeout curto (`10s`) do gate do embedder; persistência em grupo atômica; `store.load`
tolera `meta.json` ausente; `cancel_is_set` no `batch.run_batch`; `_index_one` extraída do duplicado
`index_files`/`build_index`; pula fusão RRF quando o BM25 não tem match); **`core/ml/`** (`classify.py`
dividido em pacote `classify/`; cegueira ao embed model corrigida nas assinaturas de cache de
protótipos/SVM via `embed_space_id`; canonicalização de path simétrica em `record_label`/`ChunkMeta`; gate do
`mapviz` antes do `import pandas`; guarda quadrática em `related()`; miudezas de robustez do `cache`/`store`);
**`core/text/`** (marcadores de idioma ambíguos removidos de `_PT_MARKERS`; amostragem estratificada no
resumo de textos longos — o item de maior impacto de produto do plano; `"transformer"` morto removido de
`_NER_PIPES`; `entities()` não re-checa `is_available` com pipeline em cache; edge case do separador de
header de 64 traços limitado a uma janela de prefixo); **`core/observatory/`** (docstring do `__init__.py`
para os 5 módulos reais; `disk_usage` blindado contra ciclo de symlink; ausência de lock inter-processo nos
logs documentada e aceita). Decisões pontuais de produto/arquitetura ficam em entradas próprias (abaixo).
Plano: [`plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md`](plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md).

### Decisão — `MLConfigSnapshot` reporta os dois `_MMR_LAMBDA` (jul/2026)
Fase 4 do plano do quarteto ML (item T3/O5): `core/observatory/status.py::config_snapshot()` só lia
`recommend._MMR_LAMBDA`, deixando `summarize._MMR_LAMBDA` (`core/text`) invisível no board do Observatório —
mesmo nome, mesmo valor hoje (0.6), mas constantes independentes por design (ver decisão abaixo). Decisão:
reportar as duas (`mmr_lambda` + `mmr_lambda_summary`) em vez de esconder uma; não move nenhuma constante
entre camadas, só lê ambas para exibição. CLI (`observatory status`) e a aba Status do hub Observatório
mostram as duas linhas. [`plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md`](plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md).

### Decisão — duplicação aceita entre `core/text` × `core/ml` (jul/2026)
Revisão arquivo-a-arquivo do quarteto ML (rag·ml·text·observatory) encontrou três pequenas duplicações na
fronteira entre `core/text` e `core/ml`: separador de cabeçalho `"-" * 64` (`core/rag/indexer.py`,
`core/text/reader.py`, `src/analyzer.py`), a função `_mmr` (`core/ml/recommend.py`,
`core/text/summarize.py`) e o gate `is_available()` de scikit-learn (`core/ml/deps.py`,
`core/text/summarize.py`). Decisão: manter — `core/text` é independente de `core/ml` por design (Plano 4B)
e o acoplamento de extrair uma camada comum para ~3 linhas repetidas não compensa. Não "consertar" uma
cópia isolada sem revisitar esta nota. [`plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md`](plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md).

### Reorganização da documentação técnica (jul/2026)
Consolidação dos três locais de plano (`docs/` raiz, `docs/plan/`, `.claude/plans/`) numa árvore única
`docs/plans/{active,implemented,archive}`; roadmap vivo único em `ROADMAP.md`; referência em `reference/`;
CLAUDE.md reduzido a índice + contratos, com skills como fonte única por assunto (esta é a convenção "fonte
única + ponteiro" de [`README.md`](README.md)). Nova skill `ml-rag`; `testing`/`design-system` divididas em
arquivos de referência. Plano: [`plans/implemented/PLANO_REORGANIZACAO_DOCS_SKILLS.md`](plans/implemented/PLANO_REORGANIZACAO_DOCS_SKILLS.md).

### Observatório — fast-follow 2: perf fix + Índice/RAG aninhado ✅
A aba Status travava a UI por 7-12s (cold-import de extras + `ollama.Client().list()` síncronos na UI
thread) → movidos para thread daemon com placeholder + `Client(timeout=5)`. Índice e Painel saíram do hub
de IA (que virou só Conversa) e viraram a aba aninhada **Índice/RAG** no Observatório (Índice · Painel ·
**Uso de disco**, esta nova — `core/observatory/disk_usage.py`). "Reindexar" bridgeia pro hub de IA
(`trigger_reindex`) em vez de rodar pipeline. CLI `observatory disk-usage`.
[`plans/implemented/PLANO_ML_NOVAS_FEATURES.md`](plans/implemented/PLANO_ML_NOVAS_FEATURES.md).

### Observatório — fast-follow 1: GUI write-through + Status ampliado ✅
Fechou o gap em que só a CLI gravava `log_activity`: a GUI da Transcrição passou a gravar auto-sugestão e
confirmação de perfil. Nova aba **Logs** (`core/observatory/logs.py`) captura `task_error` de qualquer
módulo via hook central em `EventBus.emit()` — sem tocar nenhum `worker.py`. Status ganhou inventário
Ollama, gates expandidos, binários externos, provedores de nuvem e glossário de entidades; Status virou a
aba padrão. [`plans/implemented/PLANO_ML_NOVAS_FEATURES.md`](plans/implemented/PLANO_ML_NOVAS_FEATURES.md).

### Novas features de ML — Tier A ✅
Busca **híbrida** no RAG (BM25+RRF, `rank-bm25` base); outliers tabulares (`IsolationForest`); dedup de
imagens (**dHash** hand-rolled, zero dep); `classify.py` parametrizado por domínio; **novo hub Observatório**
(`core/observatory/` + `gui/modules/observatory/` + CLI `observatory`) centralizando atividade/status de ML
cross-módulo; stepper contextual (infra pronta, wiring adiado).
[`plans/implemented/PLANO_ML_NOVAS_FEATURES.md`](plans/implemented/PLANO_ML_NOVAS_FEATURES.md).

### Refinamento ML/texto/RAG (Tiers 1–3) ✅
Correção de recall + cache na busca do RAG (Tier 1); MMR em `recommend`/`summarize`, c-TF-IDF com
`ngram_range`, YAKE afinado, TextRank com viés de posição, glossário opcional do `EntityRuler` (Tier 2);
TSNE como 3º método de projeção, auto-k via `silhouette_score` (Tier 3). Zero dependência nova.
[`plans/implemented/PLANO_REFINAMENTO_ML_TEXTO_RAG.md`](plans/implemented/PLANO_REFINAMENTO_ML_TEXTO_RAG.md).

### Plano 4B — classificação supervisionada + inteligência textual ✅
Camada que precisa de **rótulo** ou **NLP textual**. `core/ml/classify.py`: perfil zero-shot por protótipo
que escala para supervisionado (`LinearSVC`+`CalibratedClassifierCV`) conforme o usuário confirma o perfil
(`record_label` no worker). Novo pacote `core/text/` (YAKE · TextRank self-contained · spaCy NER CNN ·
reader/lang), independente de `core/ml`. Extra `[nlp]`. GUI: auto-sugestão de perfil, aba Insights,
auto-tags na Biblioteca. [`plans/implemented/PLANO_4B_SUPERVISIONADO_TEXTUAL.md`](plans/implemented/PLANO_4B_SUPERVISIONADO_TEXTUAL.md).

### Plano 4A — inteligência semântica não-supervisionada ✅
Só geometria de embeddings (sem rótulos/treino), reusa `features.document_matrix` (Plano 3) e `charts`
(Plano 1). `cluster` (HDBSCAN/k-means), `labeling` (c-TF-IDF), `project` (PCA default / UMAP `[ml-viz]`),
`recommend` (numpy-puro), `mapviz` → PNG. GUI: modo **Mapa** na Biblioteca + aviso de fora-de-escopo na IA.
CLI `ai topics`/`map`/`related`. [`plans/implemented/PLANO_4A_SEMANTICO.md`](plans/implemented/PLANO_4A_SEMANTICO.md).

### Plano 3 — fundação de ML ✅
Pacote puro `core/ml/` espelhando `core/rag/`, **reusando o `VectorStore` persistido** (sem recalcular
embedding). `features.py` (numpy-puro) mean-pool dos chunks; `dedup.py` (prova de vida). Gate `[ml]`
(scikit-learn ≥1.4) só nos algoritmos futuros; acessor/dedup são fundação grátis. `store.py` versiona
modelos por `sklearn.__version__`+signature. CLI `ai dups`.
[`plans/implemented/PLANO_3_FUNDACAO_ML.md`](plans/implemented/PLANO_3_FUNDACAO_ML.md).

### Plano 2 — painéis analíticos dos hubs ✅
Superfície de painel em cada hub sobre dados já coletados, **sem ML** e sem dep nova. Núcleos puros
`core/library/analytics.py` · `core/rag/analytics.py` · `core/recipes/history.py`. Biblioteca ganha modo
Painel, IA ganha aba Painel (depois migrada ao Observatório), Receitas ganha Histórico. Helper
`gui/modules/_charts.py`. CLI `library stats`/`recipe stats`.
[`plans/implemented/PLANO_2_PAINEIS_HUBS.md`](plans/implemented/PLANO_2_PAINEIS_HUBS.md).

### PR9.1 / Plano 1 — gráficos no módulo Dados ✅
`core/data/charts.py` (única fronteira matplotlib, render off-thread `Figure`/`Agg` sem `pyplot` → PNG),
aba **Gráfico** na GUI + CLI `data plot`, extra `[data-plot]`. Reusa o caminho Arrow do Plano 0.
[`plans/implemented/PLANO_1_GRAFICOS.md`](plans/implemented/PLANO_1_GRAFICOS.md).

### Plano 0 — fundação de dados ✅
Camada Polars sobre o DuckDB: `core/data/frames.py` (única fronteira de DataFrame) + `engine.run_query_arrow`
(Arrow zero-copy), extra `[analysis]`. Puramente aditiva; destrava os Planos 1/2/5.
[`plans/implemented/PLANO_0_FUNDACAO_DADOS.md`](plans/implemented/PLANO_0_FUNDACAO_DADOS.md).

### PR9.3 — prévia visual, avaliação de qualidade e indexação de dados ✅
Aba **Pré-visualização** (tabela paginada + tipos por coluna, seletor de aba XLSX), **Análise com IA**
(`assess.py` + cache), e **indexação dos 5 formatos no RAG** via cartão de dados (`datacard.py`, `card_fn`
no indexer). CLI `data assess`. [`plans/archive/PLANO_PR9.3_PREVIA_AVALIACAO_INDEXACAO.md`](plans/archive/PLANO_PR9.3_PREVIA_AVALIACAO_INDEXACAO.md).

### PR9 — módulo Dados (query-first sobre DuckDB) ✅
6ª ferramenta. Motor DuckDB (in-process, torch-free); IA traduz PT→SQL recebendo **só o schema**. CLI
`data`; integração Receitas/Biblioteca. [`plans/archive/PLANO_PR9_DADOS.md`](plans/archive/PLANO_PR9_DADOS.md).

### Áudio Tier 2 — visualização e feedback ✅
Aba **Visualizar** (áudio→imagem via `showwavespic`/`showspectrumpic`, off-thread), toggle
`Converter|Visualizar`, **A/B antes/depois** no player, **card de loudness** medido vs. alvo. CLI
`audio-viz`. Cursor do player migrado para `page.run_task`. Backlog avançado em
[`plans/active/PLANO_AUDIO_TIER3_RESUMO.md`](plans/active/PLANO_AUDIO_TIER3_RESUMO.md).
[`plans/implemented/PLANO_AUDIO_TIER2.md`](plans/implemented/PLANO_AUDIO_TIER2.md).

### Áudio Tier 1 — pós-processamento estendido ✅
Cadeia 100% ffmpeg: remoção de silêncio, velocidade sem pitch (`atempo`), downmix mono + sample-rate no
encode final, toggle de modo de ruído, **presets de uma tecla**. Formulário fatiado em `blocks/`.
[`plans/implemented/PLANO_AUDIO_TIER1.md`](plans/implemented/PLANO_AUDIO_TIER1.md).

### PR7.2 — inspetor de índice + indexação por escolha + ETA ✅
`ai stats`, indexação por escolha (nunca automática), ETA da Transcrição e estimativa de tempo da resposta.
[`plans/archive/ROADMAP_PR7.2_IA_INDICE.md`](plans/archive/ROADMAP_PR7.2_IA_INDICE.md).

### PR8 — módulo Receitas / Automação ✅
Cadeias lineares nomeadas atravessando módulos (core `src/core/recipes/`, GUI Rodar|Construir, CLI
`recipe`). [`plans/archive/ROADMAP_PR8_RECEITAS.md`](plans/archive/ROADMAP_PR8_RECEITAS.md).

### PR7 — módulo IA / RAG local ✅
RAG local sobre o corpus (core `src/core/rag/`, GUI hub, CLI `ai`). Embeddings 100% locais.
[`plans/archive/ROADMAP_PR7_IA.md`](plans/archive/ROADMAP_PR7_IA.md).

### PR6 — módulo Biblioteca ✅
Índice navegável de `output/` (grade+lista, bridges, visor in-app) + entrada flexível de análise.
[`plans/archive/ROADMAP_PR6_BIBLIOTECA.md`](plans/archive/ROADMAP_PR6_BIBLIOTECA.md).

### Tier 0 — legendas + OCR ✅
Legendas SRT/VTT, legenda no vídeo (mux/burn-in), OCR híbrido.
[`plans/archive/ROADMAP_TIER0_LACUNAS.md`](plans/archive/ROADMAP_TIER0_LACUNAS.md) ·
[`plans/archive/STATUS_TIER0.md`](plans/archive/STATUS_TIER0.md).

### PR5 / PR5.1 — módulo Documentos ✅
13 ops GUI / 12 CLI + OCR híbrido via pytesseract.
[`plans/archive/MILL_PR5_DOCUMENTS_PLAN.md`](plans/archive/MILL_PR5_DOCUMENTS_PLAN.md).

### Plano −1 — refatoração prévia ✅
Aplicou a régua de tamanho/coesão da skill `architecture` a `data/view.py` (→ `tabs/`) e
`recipes/registry.py` (→ `registry/<módulo>.py`) e fixou a regra da seção 3 no CLAUDE.md — fundação
estrutural que os planos de dados/ML herdaram. [`plans/archive/REFATORACAO_PREVIA.md`](plans/archive/REFATORACAO_PREVIA.md).

### Anteriores (era pré-mill.tools e migração)
Vídeo (PR4), Áudio (PR3), Imagens (PR-IMG), migração para multiferramenta, design system, home screen,
splash — todos em [`plans/archive/`](plans/archive/) (só leitura histórica).

---

## Decisões arquiteturais (justificativas citáveis)

Estas justificativas se repetiam em vários lugares; cada uma é fonte única aqui, referenciável por link.

### Decisão: sem PyTorch no app base
Pós-processamento de áudio é CPU-only/torch-free (noisereduce/soundfile). IA com torch (Demucs,
DeepFilterNet) ficaria isolada num extra `[ai-audio]` — o app base permanece torch-free. Ver cenário
completo em [`reference/RELATORIO_CENARIO_TORCH.md`](reference/RELATORIO_CENARIO_TORCH.md).

### Decisão: encoding de vídeo 100% CPU — sem NVENC
Definitivo. A MX150 (2GB) disputa a GPU com o Whisper/DirectX; NVENC não compensa o risco de instabilidade.

### Decisão: `rank-bm25` (não `bm25s`) para a busca híbrida
`rank-bm25` é dependência **base** — puro Python/numpy, sem scipy. `bm25s` seria mais rápido, mas puxa
scipy para um ganho que só importa acima de ~1M documentos — fora do perfil do app.

### Decisão: dHash hand-rolled (não `imagehash`) para dedup de imagens
`core/image/dhash.py` usa só Pillow+numpy. O pacote `imagehash` puxaria scipy/PyWavelets (pelo `phash`) —
correção em relação ao plano original do Tier A, que cogitava `imagehash`.

### Decisão: GLM via `langchain-openai` (não `ChatZhipuAI`)
`ChatOpenAI` com `base_url` da Zhipu (API OpenAI-compatible) evita o `ChatZhipuAI` do `langchain_community`
(que puxa `pyjwt`, legado).

### Decisão: Observatório virou hub próprio (não aba do hub de IA)
O CLAUDE.md define hub como algo que "opera sobre as saídas de todos os módulos". A superfície de ML cobre
RAG/Biblioteca/Transcrição/Dados/Receitas — aninhá-la na IA seria descasamento semântico. Ver
[`plans/implemented/PLANO_ML_NOVAS_FEATURES.md`](plans/implemented/PLANO_ML_NOVAS_FEATURES.md) (item 3.5).

### Decisão: `classify.py` parametrizado por domínio
As mesmas funções servem perfil de transcrição / domínio de dados / tipo de documento, chaveadas por prefixo
de arquivo. O domínio default preserva os nomes pré-existentes → zero invalidação de cache.

### Decisão: embeddings sempre locais; nuvem só opt-in na resposta
`core/rag/embedder.py` é a única rede na indexação (Ollama, CPU, torch-free). Gemini/GLM entram só na
geração da resposta e sempre opt-in. Racional de modelos em [`reference/MODELOS_IA.md`](reference/MODELOS_IA.md).
