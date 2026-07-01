# Novas features de ML — mill.tools — plano de implementação

**Documento de execução — plano de implementação (teor técnico elevado)**
Data: 1 de julho de 2026 · Escopo: capacidades **novas** de ML (não refinamento — ver
`docs/plan/PLANO_REFINAMENTO_ML_TEXTO_RAG.md` para isso) · Restrição: torch-free, preferência
forte por zero dependência nova; quando uma dependência nova for genuinamente necessária, ela
deve ser pequena, pura (sem binário C a compilar) e gateada por extra opcional.

> **Origem.** Nasce de um relatório exploratório ("quais outras features de ML com ganhos reais
> e práticos poderiam ser incluídas?") produzido **antes** do plano de refinamento já implementado.
> Este documento reavalia aquele relatório à luz do estado atual do código (Tiers 1–3 do
> refinamento já shippados) e o formaliza com o mesmo rigor: arquivo por arquivo, com o encaixe
> arquitetural verificado contra o código real, não apenas hipotético.

---

## Sumário

1. Objetivo e escopo
2. Herança do que já está pronto (reaproveitado por este plano)
3. Tier A — ganho alto, custo baixo/quase-zero
4. Tier B — ondas maiores do roadmap (Planos 5/6/7, revisados)
5. Tier C — registrado, **não implementado nesta rodada**
6. Passos de implementação
7. Testes
8. Critérios de aceitação
9. Riscos e o que **não** fazer
10. Tabela-resumo
11. Fontes

---

## 1. Objetivo e escopo

Diferente do plano de refinamento (que só melhorou lógica já existente), este plano traz
**capacidades novas**: busca híbrida no RAG, detecção de anomalias tabulares, deduplicação de
imagens, reuso do classificador em novos domínios, visibilidade dos processos de ML na GUI, e a
conclusão revisada dos Planos 5/6/7 que o `docs/ROADMAP_ML_DADOS.md` original nomeou mas nunca
detalhou (e cujas escolhas de dependência ficaram desatualizadas — ver seção 4).

**No escopo:** Tier A (seção 3, prioridade imediata) e Tier B (seção 4, ondas seguintes). **Fora
do escopo:** Tier C (seção 5) — registrado para referência futura, não agendado.

---

## 2. Herança do que já está pronto (reaproveitado por este plano)

Nada aqui parte do zero — cada item se apoia em uma fundação que os Planos 0–4B e o refinamento
recente já pagaram:

- **`VectorStore.search(mask=...)` + cache de normalização** (Tier 1 do refinamento) — a busca
  híbrida (3.1) se conecta exatamente aqui: o pré-filtro por escopo já acontece antes do rank;
  o BM25 se torna um segundo estágio de scoring sobre o mesmo conjunto já filtrado.
- **`core/data/frames.py`/`charts.py`** (Planos 0/1) — outliers tabulares (3.2) e o resto do
  Plano 5 (4.1) consomem `to_pandas(QueryResult)` diretamente, sem nova fronteira de dados.
- **`core/ml/dedup.py::_connected_components`** (Plano 3) — o dedup de imagens (3.3) reaproveita
  o mesmo algoritmo de componentes conexas por limiar, só trocando cosseno por distância de
  Hamming. Duplicado, não importado (mesma decisão já tomada para o MMR no Tier 2 do refinamento
  — `core/image`/`core/library` seguem independentes de `core/ml`, mesmo racional de `core/text`).
- **`core/ml/classify.py`** (Plano 4B) — o reuso em Dados/Documentos (3.4) é a mesma
  infraestrutura de protótipo+cosseno+upgrade supervisionado, só parametrizada por domínio.
- **`core/recipes/history.py`** (Plano 2) — a previsão de tempo/próxima etapa/falhas do Plano 7
  (4.2) é só análise sobre o `RunRecord` já gravado; nenhuma coleta nova.
- **Convenção de "painéis" por hub** (Plano 2 — `ai/analytics_tab.py`, `library/analytics_panel.py`,
  `recipes/history_tab.py`) — a visibilidade de ML (3.5) reaproveita o **padrão visual** dessas
  abas (toggle manual + cartões/tabela), mas não nesta ou naquela aba: dado o escopo cross-módulo,
  vira um **hub próprio** (ver 3.5) — o padrão arquitetural de "hub = opera sobre as saídas de
  todos" (§ Sistema de módulos, `CLAUDE.md`) é reaproveitado, não inventado.
- **Registro de hubs no AppBar** (`app.py::MODULES`/`_HUB_IDS`, já usado por Biblioteca/IA/
  Receitas) — o 4º hub (3.5) entra pela mesma fonte única, sem novo mecanismo de navegação.

---

## 3. Tier A — ganho alto, custo baixo/quase-zero

### 3.1 Busca híbrida (BM25 + denso) no RAG

**Problema.** Busca por embeddings é ótima para "sentido", mas falha em nomes próprios, siglas,
números e termos exatos — fraqueza conhecida e documentada de RAG puramente denso. Uma pergunta
como "o que disse sobre o artigo 5º?" pode perder o trecho certo se "artigo 5º" não estiver bem
representado no espaço de embedding, mas um índice léxico (BM25) acha na hora.

**Arquivo novo:** `src/core/rag/bm25.py` (puro, função única):

```python
def bm25_scores(query: str, texts: list[str]) -> np.ndarray:
    """BM25 relevance of `query` against each of `texts`, same order, via rank_bm25."""
```

Tokenização simples (`.lower().split()`) — suficiente para o propósito, sem puxar nenhuma
dependência de NLP nova (`yake`/`spacy` já resolvem tokenização mais rica onde importa).

**`VectorStore` ganha um segundo cache lazy**, no mesmo padrão do `_normalized` (Tier 1):

```python
self._bm25: BM25Okapi | None = None  # invalidated by add()/drop_source(), same as _normalized

def _bm25_index(self) -> BM25Okapi:
    if self._bm25 is None:
        from rank_bm25 import BM25Okapi
        self._bm25 = BM25Okapi([m.text.lower().split() for m in self.meta])
    return self._bm25
```

**Combinação — Reciprocal Rank Fusion (RRF), não soma normalizada.** A hipótese original
("somar/normalizar os dois scores") esbarra num problema real: cosseno vive em `[-1, 1]` e BM25
é ilimitado — somar exige normalização ad-hoc e calibrar um peso. RRF evita isso: usa só a
**posição no ranking** de cada método, não o valor do score.

```
RRF(i) = 1/(k + rank_denso(i)) + 1/(k + rank_bm25(i))     # k = 60 (Cormack et al., 2009)
```

`retriever.retrieve()` passa a computar os dois rankings sobre o mesmo conjunto mascarado
(reaproveitando a máscara de escopo do Tier 1), combinar por RRF, e cortar top-`k`. Nenhuma
mudança na assinatura pública de `retrieve()`.

**Dependência — decidido: base, não atrás de extra.** `rank-bm25` é puro Python, ~200 linhas, zero
dependência transitiva, sem binário para compilar — pequeno o bastante para não haver diferença
prática de peso entre "base" e "atrás de um extra". Como a busca densa do RAG hoje já é
incondicional (só o `[ml]` gateia os algoritmos de Plano 4A/4B, não o RAG em si), `rank-bm25` entra
em `[project.dependencies]`: a busca híbrida vira o comportamento padrão para todo mundo, sem
opt-in — consistente com o RAG já não ter nenhum extra hoje.

**CLI/GUI.** Nenhuma superfície nova — `ai "pergunta"` e o chat da GUI já passam por
`retriever.retrieve()`; o ganho é transparente.

### 3.2 Detecção de outliers tabulares no módulo Dados

**Problema.** Ninguém audita manualmente uma planilha de 5 mil linhas, e `assess.py` (parecer de
qualidade pela IA) não pega isso — ele recebe só esquema + `SUMMARIZE` + amostra, nunca as linhas
inteiras (decisão de privacidade deliberada do módulo Dados).

**Arquivo novo:** `src/core/data/ml.py` (paralelo a `charts.py` — mesma fronteira de consumo do
`frames.py`):

```python
def detect_outliers(df: pd.DataFrame, *, contamination: float = 0.05) -> pd.DataFrame:
    """Flag anomalous rows via IsolationForest over the numeric columns of `df`.

    Returns `df` with an added `_anomaly_score` column (lower = more anomalous); non-numeric
    columns are ignored in this first cut (categorical encoding is a known limitation, not a bug).
    """
```

`sklearn.ensemble.IsolationForest` já está dentro do `[ml]` — zero dependência nova. Consome
`frames.to_pandas(engine.run_query_arrow(...))` (Plano 0), fechando o mesmo ciclo que `charts.py`
já fecha para gráficos.

**Engenharia genuinamente nova (única peça):** decisão de que colunas não-numéricas ficam de fora
nesta primeira versão — codificação categórica (one-hot/ordinal) fica registrada como próximo
passo natural, não implementada agora (evita a complexidade de decidir cardinalidade/encoding sem
um caso de uso real para calibrar).

**CLI:** `data outliers <arquivo> [--contamination 0.05]` — imprime contagem de linhas sinalizadas
+ prévia das mais anômalas. **GUI:** ação "Detectar anomalias" na aba Consulta, após uma consulta
rodar — linhas sinalizadas destacadas na `DataTable` paginada já existente (reusa `table_view.py`).
**Receitas:** novo passo `data.outliers` (mesmo padrão de `data.query`/`data.profile`).

### 3.3 Deduplicação de imagens (hash perceptual)

**Problema.** A Biblioteca já deduplica texto por embedding (Plano 3), mas imagens (a mesma foto
reencodada, recortada, ou salva duas vezes) não têm nenhuma defesa — hash criptográfico (MD5/SHA)
não tolera nem 1 pixel de diferença.

**Arquivo novo:** `src/core/image/phash.py` (puro, gate `is_available()` no padrão de
`ocr.is_available()`):

```python
def phash(path: Path, hash_size: int = 8) -> imagehash.ImageHash:
    """Perceptual hash of an image, tolerant to light recompression/resize."""
```

**Arquivo novo:** `src/core/library/image_dedup.py`, reaproveitando o **mesmo algoritmo** de
`core/ml/dedup.py` (componentes conexas por limiar) — duplicado, não importado, mesma decisão já
tomada para o MMR no Tier 2 do refinamento:

```python
def near_duplicate_images(paths: list[Path], *, max_distance: int = 8) -> list[ImageDuplicateGroup]:
    """Group perceptually-identical images by Hamming distance between phashes."""
```

`max_distance = 8` (de 64 bits, `hash_size=8`) é o limiar convencional da comunidade
`imagehash` para "mesma imagem, reencodada/recortada levemente". `ImageDuplicateGroup` como novo
tipo local em `core/library/types.py` — não reaproveita `DuplicateGroup` de `core/ml/types.py`
(mesmo racional de independência de pacote).

**Dependência.** `imagehash` (puro Python + numpy, sem binário) entra como novo extra
**`[ml-image]`** — nome já reservado pelo `docs/ROADMAP_ML_DADOS.md` original para a onda de mídia,
usado aqui adiantado só para este item leve.

**CLI:** `library dedup-images [--max-distance 8]` (mesmo padrão read-only de `library list`).
**GUI:** deferida como fast-follow — mesmo padrão já aceito no Plano 3 ("acessor pronto, GUI
deferida"); o CLI sozinho já entrega o valor prático.

### 3.4 Reuso do classificador zero-shot em Dados e Documentos

**Problema/oportunidade.** `core/ml/classify.py` resolve "qual categoria esse texto pertence, com
poucos exemplos e sem treino" — hoje hardcoded para o domínio "perfil de transcrição". A mesma
infraestrutura (protótipos por categoria, nearest-prototype por cosseno, upgrade transparente
para `LinearSVC`+`CalibratedClassifierCV` conforme rótulos chegam) resolve qualquer domínio de
classificação de texto curto.

**Mudança necessária (única peça de engenharia nova):** `classify.py` precisa parametrizar por
**domínio/namespace** em vez de assumir "perfil de transcrição" implicitamente — os protótipos,
o cache de embeddings de protótipo, e o modelo supervisionado persistido (`store.py`) passam a
ser chaveados por `domain` (ex.: `"transcription_profile"` — default, preserva o comportamento
atual — `"data_domain"`, `"document_type"`), não por um singleton implícito. **Antes de
implementar, ler a assinatura atual de `classify.py`/`store.py` para desenhar o parâmetro sem
quebrar o caminho já em produção** (rótulo de ouro gravado pelo worker via `record_label`).

Definir os protótipos novos é o único trabalho de conteúdo:
- **Dados** (`data_domain`): financeiro, pesquisa/científico, log/operacional, cadastro/pessoas,
  catálogo/produto — alimenta uma etiqueta extra no `datacard.py` (PR9.3).
- **Documentos** (`document_type`): nota fiscal, ata de reunião, artigo/relatório, contrato,
  correspondência — exposto na aba de resultado do módulo Documentos.

Zero código de ML novo — é o item mais barato do lote inteiro.

### 3.5 Visibilidade dos processos de ML — novo hub "Observatório"

**Origem.** Pesquisa dedicada (Context7 + web) sobre viabilidade no Flet 0.85 e inspiração em
dashboards de observabilidade de ML (Airflow DAG, Prefect Radar, ComfyUI/n8n, stepper de
"raciocínio" de apps LLM consumer tipo ChatGPT/Perplexity).

**Restrição real descoberta na pesquisa.** A maioria das chamadas de ML do mill.tools termina em
bem menos de um segundo (YAKE, TextRank, HDBSCAN/k-means, classify, MMR) — um "pipeline acendendo
ao vivo" só tem valor visível nas operações **genuinamente lentas**: indexação do RAG (chamadas de
rede ao Ollama por chunk) e projeção TSNE/UMAP em acervos maiores. As rápidas apenas piscariam;
desacelerar a animação artificialmente para compensar mentiria sobre o comportamento real do
sistema — rejeitado.

**Primitivas do Flet 0.85 confirmadas (Context7, `flet-dev/flet`):** `ft.Canvas`/`flet.canvas`
existe (shapes `Line`/`Circle`/`Arc`/`BezierCurve`), mas é **immediate-mode** — sem scene graph,
sem hit-testing/drag/zoom nativo (qualquer interação exigiria engenharia própria pesada).
`ft.LineChart`/`BarChart`/`PieChart` existem e são estáveis. `ft.ProgressRing` aceita `value=`
dinâmico. `Container(animate_position=True)`/`animate_opacity`/`animate_scale` — já comprovados em
produção (`home.py`, cards que crescem no hover) — são a primitiva certa para destacar um estágio
ativo. **Não existe** widget de grafo/DAG pronto; construir um canvas de nós livre (estilo
ComfyUI) seria inédito e desproporcional — os "pipelines" do mill.tools são pequenos e fixos
(4–6 estágios nomeados), não grafos grandes/dinâmicos autorados pelo usuário. **Rejeitado.**

**Decisão de escopo e de encaixe arquitetural (após discussão com o usuário, revisada 2×):**

1. Primeiro passo: virar a central de comando de toda a maquinaria de ML do app — não só a saúde
   do índice do RAG. A intenção explícita é ter o **máximo de informação possível** num único
   lugar sobre o que cada motor de ML está fazendo/já fez e em que estado está, cobrindo os 5
   módulos que produzem ML (RAG, Biblioteca, Transcrição, Dados, Receitas).
2. Segundo passo, corrigindo a recomendação inicial da pesquisa: dado esse escopo cross-módulo,
   **não cabe como aba de outro hub** — nesting isso dentro do hub IA (RAG/chat) cria um
   descasamento semântico real: quem quer entender "por que o Dados marcou essa linha como
   atípica" não pensaria em abrir "IA → Painel" para achar. O próprio `CLAUDE.md` já define hub
   como algo que **"opera sobre as saídas de todos [os módulos]"** — é exatamente o que esta
   superfície faz, então ela se qualifica como hub por definição própria do projeto, não como
   aba emprestada. **Decisão final: novo hub dedicado, nome "Observatório"** (4º botão dourado no
   AppBar, ao lado de Biblioteca/IA/Receitas) — custo de mais um botão no AppBar, mas semântica
   correta e espaço próprio para crescer (não fica espremido na 3ª sub-aba de outro hub).

Isso muda o peso relativo das três peças: (b) e (c) deixam de ser "complementos baratos" e passam
a ser o **produto principal** do novo hub; (a) continua local/efêmero, embutido nas telas onde a
operação já acontece, mas alimenta (b) como uma das fontes de evento.

**Desenho recomendado — três peças, todas reaproveitando eventos reais (nenhum tempo fabricado),
sem dependência nova:**

**(a) Stepper contextual** — um `Row` de "chips" fixos (nomes dos estágios) que destacam o
estágio ativo via `animate_opacity`/`animate_scale`, embutido **localmente** onde a operação já
mostra progresso, não num painel à parte:
- RAG: "Buscar → Contexto → Responder", ao lado do cronômetro que `ai/timing.py` já mostra.
- Biblioteca → Mapa: "Agrupar → Rotular → Projetar", durante a geração do mapa semântico.
- Transcrição → Insights: "Palavras-chave → Resumo → Entidades", na 1ª abertura da aba.

**Achado de arquitetura que barateia a implementação**: a sequência de cada um desses fluxos **já
é orquestrada na camada de worker/CLI**, não dentro de uma função pura de `core/ml`/`core/text`
(ex.: o worker já chama `keywords()` → `extractive_summary()` → `entities()` em sequência; a
função `build_semantic_map()` já chama cluster→label→project internamente). Isso significa que
**nenhuma função pura de `core/` precisa aprender a emitir eventos** — o stepper só exige que o
worker/CLI emita um evento de "estágio iniciado" nos pontos onde ele já orquestra a sequência,
exatamente o mesmo princípio de injeção de callback na fronteira (§2 da skill `architecture`) já
usado pelos adaptadores de Receitas. `mapviz.build_semantic_map` é a única exceção — internamente
encadeia os 3 estágios sozinha, então ganha um parâmetro opcional `on_stage: Callable[[str], None]
| None = None`, chamado entre as etapas (não muda o contrato para quem não passa o callback).

**Encaixe arquitetural do hub novo:**

- **`src/gui/modules/observatory/`** — novo hub, mesmo esqueleto de `ai`/`recipes` (auto-contido,
  `module_id="observatory"`, split em abas manuais `visible=` num `Stack`): `activity_tab.py`
  (peça b) · `status_tab.py` (peça c) · `view.py` monta o toggle entre as duas. Registrado em
  `app.py::MODULES` (mais uma entrada) + `_HUB_IDS` (exclui da `NavigationRail`, entra como botão
  dourado no AppBar, mesmo padrão de Biblioteca/IA/Receitas).
- **`src/core/observatory/`** (puro, novo pacote, mesmo molde de `core/rag`/`core/recipes`):
  `activity.py` (append/leitura do `ml_activity.json`, mesma forma de `core/recipes/history.py`)
  + `status.py` (agrega, sem recalcular nada: `core/ml/deps.is_available()`, `core/text/*
  .is_available()`, `core/rag/embedder.is_available()`, `core/rag/stats.index_stats()`,
  `core/ml/classify` contagem de rótulos por domínio, `core/rag/analytics.model_timings`).
- **CLI:** `src/cli/observatory.py` — `observatory status` / `observatory activity` (read-only,
  sem `CLIEventBus`, mesmo padrão de `library`/`ai stats` — reusa o core puro direto).

**(b) Feed de atividade ML — cobertura completa, não uma amostra.** Lista cronológica na aba
**Atividade** do novo hub Observatório, registrando **toda** operação de ML de **todo** módulo,
não só os 4 exemplos ilustrativos do primeiro rascunho:

| Módulo | Eventos registrados |
|---|---|
| RAG/IA | resposta gerada (modelo, `k`, `low_confidence`?), reindexação, dedup de texto rodado (N grupos) |
| Biblioteca | mapa semântico (re)gerado (método, N docs, N clusters), duplicatas de imagem encontradas (3.3) |
| Transcrição | perfil sugerido/confirmado (3.4 supervisionado grava aqui também), keywords/resumo/entidades computados |
| Dados | outliers detectados (3.2), domínio classificado (3.4), agrupamento/previsão/importância (4.1, quando implementado) |
| Receitas | previsão de tempo usada, sugestão de próxima etapa aceita/ignorada, config de risco detectada (4.2, quando implementado) |

Persistência **append-only capada**, mesmo padrão de `core/recipes/history.py`
(`~/.mill-tools/ml_activity.json`), escrita pelos workers/CLI runners no ponto natural de
conclusão de cada operação (não exige quebrar a convenção de escopo por `module_id` dos painéis —
o feed lê o log, não assina pubsub de outros módulos). Cada linha guarda `module`/`event`/
`detail`/`timestamp`, o suficiente para filtrar por módulo depois se a lista crescer demais.

**(c) Quadro de status — inventário completo dos motores, não 3 badges.** Também expandido para
"máximo de informação": aba **Status** do novo hub Observatório, organizado em cartões por
assunto:

- **Gates/extras**: `[ml]`, `[ml-viz]`, `[nlp]` (+ modelo spaCy baixado ou não), `[ml-image]`
  (3.3), embedder Ollama — cada um com ✓/✗ e o `SETUP_HINT` já existente quando ausente.
- **Índice RAG**: tudo que `stats.index_stats()` já calcula (docs, chunks, dim, modelo de
  embedding, tamanho em disco, atualizado em) — hoje só na aba Índice, passa a aparecer resumido
  aqui também.
- **Classificador (`classify.py`, 3.4)**: contagem de rótulos treinados por domínio
  (`transcription_profile`/`data_domain`/`document_type`), zero-shot vs. supervisionado ativo em
  cada um.
- **Configuração em vigor**: os parâmetros que hoje só existem como constante no código —
  limiar de dedup de texto (`0.95`) e de imagem (`max_distance=8`, 3.3), piso de auto-k
  (`_MIN_FOR_AUTO_K=20`), λ do MMR (`0.6`), método de projeção do último mapa gerado
  (`pca`/`tsne`/`umap`). Só leitura — não é um formulário de configuração, é transparência.
  Torna visível "por que o mapa saiu assim" sem precisar abrir o código.
- **Timings por modelo** (já existe, `core/rag/analytics.py::model_timings`) — mean/median/p90,
  reaproveitado sem mudança.

**Selo de novidades no botão do hub.** Como (b)/(c) só aparecem se o usuário abrir o Observatório
de propósito, o **botão dourado do hub no AppBar** ganha um contador discreto de itens novos desde
a última visita (ex.: `Observatório ⬤3`, badge sobreposto ao botão, mesmo espírito visual de
contador de não-lidos), zerado ao abrir o hub — persistido como `last_ml_activity_seen` (timestamp)
em `config.json`, ao lado de `last_ai_tab`/`last_data_tab` que já existem ali.

**Nota de UX — organização por revelação progressiva.** "Máximo de informação" sem estrutura vira
ruído. Os cartões de status (c) nascem **recolhidos por assunto** (Gates · Índice · Classificador
· Configuração · Timings), cada um expansível (`ExpansionTile`-like, mesmo espírito dos drill-downs
já usados no inspetor de índice); o feed (b) mostra as últimas ~15 entradas com um "ver tudo" que
abre o histórico completo num diálogo (mesmo padrão do drill-down de chunks da aba Índice).

**Veredito:** viabilidade alta para as três peças + o hub novo, esforço médio-alto (b, c e o
registro do hub) / baixo-médio (a, selo de novidades), zero dependência nova. O canvas de nós
livre fica no Tier C (seção 5) — desproporcional.

---

## 4. Tier B — ondas maiores do roadmap (Planos 5/6/7, revisados)

O `docs/ROADMAP_ML_DADOS.md` original nomeou os Planos 5 (tabular), 6 (mídia) e 7 (operacional)
mas errou a escolha de dependência em dois pontos — corrigido aqui:

- **XGBoost/LightGBM → `HistGradientBoostingClassifier`/`Regressor`** (dentro do `[ml]` desde o
  scikit-learn 0.21): mesma família de boosting por histograma, performance comparável nos
  volumes de um acervo pessoal (milhares, não milhões de linhas), tratamento nativo de valores
  ausentes, **zero dependência nova** — XGBoost/LightGBM trariam mais uma biblioteca C++ compilada
  para manter, por um ganho que ninguém notaria nesse volume.
- **OpenCV/PySceneDetect/librosa → alternativas mais leves** (detalhado em 4.3).

### 4.1 Plano 5 completo — ML tabular no módulo Dados

Além dos outliers (3.2, já Tier A), fecha com:

| Funcionalidade | Dependência | Onde |
|---|---|---|
| Agrupamento de linhas | `core/ml/cluster.py`, mas sobre embeddings/features numéricas da linha | já em `[ml]` |
| Previsão (classificação/regressão) | `HistGradientBoostingClassifier`/`Regressor` | já em `[ml]` |
| Importância de variáveis | `sklearn.inspection.permutation_importance` (model-agnostic) | já em `[ml]` |

Mesma fronteira `core/data/ml.py` do item 3.2. Cuidado real: codificação categórica antes de
entrar nos modelos (one-hot/ordinal) — só peça de engenharia genuinamente nova, mesma ressalva
do item 3.2. Integra com **PR9.2** (encadeamento em estágios, já no roadmap) — quando o
resultado de uma análise puder virar nova fonte, as saídas tabulares de ML encadeiam-se
naturalmente.

### 4.2 Plano 7 — ML operacional em Receitas

O histórico (`core/recipes/history.py`, Plano 2) já é a matéria-prima — nenhuma coleta nova:

- **Previsão de tempo de execução** — `HistGradientBoostingRegressor` sobre `RunRecord`
  (tamanho do arquivo de entrada, receita, etapa) ou, se o volume de histórico for pequeno, média
  ponderada simples — mesmo padrão de "tempo típico" que `ai/timing.py` já faz para respostas RAG.
- **Sugestão de próxima etapa** no modo Construir — cadeia de Markov de 1ª ordem sobre o
  histórico: qual operação historicamente sucede a etapa atual. **`collections.Counter` puro,
  stdlib — nem pede o extra `[ml]`.**
- **Detecção de configurações problemáticas** — tabela de taxa de falha por combinação de
  parâmetros (stdlib) já entrega a maior parte do valor; `IsolationForest` (já em `[ml]`) como
  refinamento opcional.
- **Agregação de lote** — só pandas (Plano 0/`[analysis]`), nenhum ML envolvido.

Depende só de fundações já prontas (Plano 0 + Plano 2 + Plano 3) — nenhuma dependência nova em
nenhum item.

### 4.3 Plano 6 revisado — ML de mídia, leveza máxima

O roadmap original cogitava `librosa`, `PySceneDetect`/OpenCV, `imagehash` (este já adiantado
como 3.3). Revisão:

- **Blur/baixa qualidade em Imagens** — variância do Laplaciano sobre a imagem em escala de
  cinza, convolução manual em numpy puro (kernel `[[0,1,0],[1,-4,1],[0,1,0]]` via slicing
  vetorizado, sem scipy/OpenCV):
  ```python
  lap = im[:-2,1:-1] + im[2:,1:-1] + im[1:-1,:-2] + im[1:-1,2:] - 4*im[1:-1,1:-1]
  blur_score = lap.var()  # menor = mais borrada
  ```
  Sinaliza fotos borradas na Biblioteca antes de gastar tempo processando-as. Zero dependência.
- **Paleta de cores dominante em Imagens** — histograma quantizado em numpy puro sobre a imagem
  redimensionada a 100×100 (resolve ~80% do valor sem sklearn) ou k-means sobre os pixels em
  RGB/Lab (já em `[ml]`) para maior fidelidade. Alimenta busca por cor na Biblioteca.
- **Cena de vídeo (capítulos automáticos)** — filtro nativo `select` do próprio ffmpeg (diferença
  de histograma entre frames), **não** OpenCV/PySceneDetect — zero dependência nova, já que ffmpeg
  é binário externo que o projeto já exige. Não é ML propriamente dito, mas entrega o mesmo
  resultado prático (marcadores de capítulo) a custo zero. Se um dia quiser detecção por conteúdo
  semântico (não só corte visual), aí sim entraria ML de verdade — não uma necessidade agora.
- **VAD leve em Áudio** — condicional a implementar primeiro o item #11 do
  `docs/PLANO_AUDIO_TIER3_RESUMO.md` (split por silêncio via `silencedetect`); só se esse recurso
  mostrar problemas em gravações ruidosas, trocar por `webrtcvad-wheels` (fork com wheels
  pré-compiladas p/ Windows, sem exigir compilador C) — wrapper de ~1 arquivo sobre o WebRTC VAD
  do Google, sem modelo para baixar, tempo real em CPU. Prioridade condicional, não uma entrega
  independente.

---

## 5. Tier C — registrado, **não implementado nesta rodada**

| Item | Motivo |
|---|---|
| XGBoost/LightGBM | `HistGradientBoosting*` do sklearn já cobre o mesmo terreno, sem dependência nova, nos volumes processados (ver 4.1) |
| CLIP/busca visual por conteúdo | Mesmo em ONNX, exige baixar um modelo de ~300MB+ e manter pipeline de inferência — desproporcional ao uso pessoal atual |
| BPM/key detection, vocal isolation por phase-cancellation | Já avaliado e rejeitado no Áudio Tier 3 (`docs/PLANO_AUDIO_TIER3_RESUMO.md`) — decisão original mantida |
| Diarização, upscale, denoise neural | Exigem torch (modelos grandes); já coberto em `docs/RELATORIO_CENARIO_TORCH.md` — a MX150 de 2GB não tem folga; veredito "opcional, não base" continua válido |
| Canvas de nós livre (estilo ComfyUI) para visualizar ML | Desproporcional ao tamanho real dos pipelines do projeto (4–6 estágios fixos, não grafos grandes/dinâmicos) e ao immediate-mode do Flet (sem hit-test/zoom/drag nativo) — ver 3.5 |

---

## 6. Passos de implementação

**Tier A (um item por commit, ordem sugerida = a da seção 3):**
1. `rag/bm25.py` + `rag/store.py` (`_bm25_index`) + `rag/retriever.py` (RRF) + `rank-bm25` em
   `[project.dependencies]` (decisão já confirmada — base, não extra).
2. `data/ml.py` (`detect_outliers`) + CLI `data outliers` + integração na aba Consulta.
3. `image/phash.py` + `library/image_dedup.py` + `library/types.py` (`ImageDuplicateGroup`) +
   extra `[ml-image]` + CLI `library dedup-images`.
4. `classify.py` parametrizado por `domain` (ler assinatura atual antes) + protótipos de Dados e
   Documentos + integração no `datacard.py`/aba de resultado de Documentos.
5. Visibilidade de ML — **novo hub Observatório**, em sub-passos:
   1. `core/observatory/activity.py` (log append-only) + `activity.py` sendo chamado pelos
      workers/CLI runners dos itens 3.1–3.4 já implementados (feed nasce parcial, de propósito).
   2. `core/observatory/status.py` (agregador read-only sobre `deps`/`stats`/`classify`/
      `analytics` já existentes).
   3. `gui/modules/observatory/` (hub novo) + registro em `app.py::MODULES`/`_HUB_IDS` + botão no
      AppBar + selo de novidades no botão.
   4. Stepper contextual embutido nas 3 telas (RAG, Mapa, Insights) — depende de `on_stage` em
      `mapviz.build_semantic_map` + eventos de estágio no worker de RAG/Insights.
   5. `cli/observatory.py` (`status`/`activity`).
   `uv run pytest -m unit` verde entre cada sub-passo. **Nota de sequenciamento:** o feed/status
   ganham novas linhas automaticamente conforme o Tier B (4.1/4.2/4.3) for implementado depois —
   nenhum retrabalho, só mais fontes escrevendo no mesmo `ml_activity.json`.

**Tier B (uma onda por commit ou por sub-item, conforme apetite):** 4.1 (tabular completo) →
4.2 (Receitas) → 4.3 (mídia leve, priorizando blur/paleta antes de cena de vídeo/VAD).

Ordem entre tiers: A → B, cada item validado antes do próximo.

---

## 7. Testes

Cada item ganha teste(s) `@pytest.mark.unit`, espelhando `tests/core/`:

- **3.1**: `test_bm25.py` (`importorskip("rank_bm25")`) — scores maiores para termo exato presente;
  `test_retriever.py` ganha caso onde RRF recupera um chunk com match lexical exato que o cosseno
  sozinho rankeava baixo.
- **3.2**: `test_data_ml.py` — linha sintética fora da distribuição é sinalizada; `contamination`
  respeitado; colunas não-numéricas ignoradas sem erro.
- **3.3**: `test_phash.py`/`test_image_dedup.py` (`importorskip("imagehash")`) — imagem idêntica
  reencodada → mesmo grupo; imagens distintas → não agrupam; `is_available()` False sem o extra.
- **3.4**: `test_classify.py` estendido — dois domínios com protótipos diferentes não vazam
  categoria um para o outro; domínio default preserva comportamento atual (regressão).
- **3.5**: `tests/core/observatory/test_activity.py` — round-trip do `ml_activity.json` em
  `tmp_path` (append, cap, corrompido → vazio, mesmo padrão de `tests/core/recipes/test_store.py`);
  cada worker que passa a gravar no feed (RAG, Biblioteca, Transcrição, Dados, Receitas) ganha 1
  teste confirmando que sua conclusão grava a linha certa (`module`/`event`/`detail`).
  `tests/core/observatory/test_status.py` — cada seção (gates/índice/classificador/config/timings)
  testada isoladamente com dados sintéticos/mockados. `mapviz.build_semantic_map` com `on_stage`
  capturando a sequência `["cluster","label","project"]`; worker de RAG/Insights emitindo eventos
  de estágio verificáveis por um bus falso (mesmo padrão de `tests/gui/modules/ai/test_worker.py`).
  **Hub novo**: `tests/gui/modules/observatory/` por construct-smoke (`build_*` com `MagicMock`,
  mesmo padrão do Plano 4A para `semantic_map_panel`) + registro em `MODULES`/`_HUB_IDS` coberto
  por um teste de `app.py` (import-smoke já existente estendido). Selo de novidades: contagem
  cresce com eventos novos, zera ao abrir o hub (`last_ml_activity_seen` atualizado), persiste em
  `config.json` no mesmo padrão de `test_settings.py`.
- **4.1–4.3**: espelhar os padrões já estabelecidos (`test_cluster.py`/`test_charts.py` para
  tabular; `test_history.py` para Receitas; `test_transform.py`-like para blur/paleta).

---

## 8. Critérios de aceitação

- Nenhuma dependência nova sem extra opcional, exceto `rank-bm25` (decisão confirmada: base) +
  import preguiçoso + gate `is_available()` nas demais.
- `uv run pytest -m unit` verde e `ruff` limpo após cada item.
- Tier A: busca híbrida não piora recall em nenhum caso coberto pelo Tier 1 do refinamento;
  outliers/dedup/classify não regridem nenhum teste existente; visibilidade de ML não introduz
  nenhuma animação com tempo fabricado (só eventos reais); o hub Observatório segue o mesmo
  contrato de `Module` dos demais hubs (auto-contido, escopado por `module_id`).
- Tier C permanece **não implementado** nesta rodada.

---

## 9. Riscos e o que **não** fazer

Não implementar busca híbrida por soma normalizada ad-hoc — RRF evita o problema de escala sem
precisar calibrar peso. Não construir um canvas de nós livre — desproporcional ao tamanho real
dos pipelines e ao immediate-mode do Flet. Não desacelerar artificialmente animações de ML rápido
para fingir "trabalho acontecendo" — mentiria sobre o comportamento real do sistema. Não
compartilhar `_connected_components`/tipos de duplicata entre `core/image`/`core/library` e
`core/ml` via import cruzado — duplicar respeita a independência já decidida entre pacotes. Não
perseguir XGBoost/LightGBM/CLIP/diarização sem decidir, à parte, abrir mão da restrição de
zero/baixa dependência nova.

---

## 10. Tabela-resumo

| # | Item | Módulo | Dependência nova | Esforço | Prioridade |
|---|---|---|---|---|---|
| 3.1 | Busca híbrida (BM25 + RRF) | RAG/IA | `rank-bm25` (base, confirmado) | Baixo | Alta |
| 3.2 | Outliers tabulares | Dados | Nenhuma (`[ml]` já tem) | Baixo | Alta |
| 3.3 | Dedup de imagens | Biblioteca | `imagehash` (novo `[ml-image]`) | Baixo | Alta |
| 3.4 | Reuso do classify.py | Dados, Documentos | Nenhuma | Baixo | Alta |
| 3.5 | Visibilidade de ML — **novo hub Observatório** (stepper+feed+status+selo) | Novo hub, cross-módulo (RAG/Biblioteca/Transcrição/Dados/Receitas) | Nenhuma | Médio-Alto | Alta |
| 4.1 | Plano 5 completo (clustering/previsão/importância) | Dados | Nenhuma (`[ml]` já tem) | Médio | Média |
| 4.2 | Plano 7 (previsão de tempo, próxima etapa, falhas) | Receitas | Nenhuma | Médio | Média |
| 4.3 | Plano 6 leve (blur/paleta/cena/VAD) | Imagens/Vídeo/Áudio | Nenhuma (VAD condicional: `webrtcvad-wheels`) | Baixo-Médio | Média-Baixa |
| — | XGBoost/LightGBM | — | Rejeitado | — | — |
| — | CLIP/busca visual | — | Fora de escopo | — | — |
| — | BPM/key, vocal isolation | — | Já rejeitado (Áudio Tier 3) | — | — |
| — | Diarização/upscale/denoise neural | — | Fora de escopo (torch) | — | — |
| — | Canvas de nós livre p/ visualizar ML | — | Desproporcional | — | — |

---

## 11. Fontes

- [Reciprocal Rank Fusion — Cormack, Clarke & Buettcher, SIGIR 2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [rank-bm25 — dorianbrown/rank_bm25](https://github.com/dorianbrown/rank_bm25)
- [sklearn.ensemble.IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html)
- [sklearn.ensemble.HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html) · [HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html)
- [sklearn.inspection.permutation_importance](https://scikit-learn.org/stable/modules/generated/sklearn.inspection.permutation_importance.html)
- [imagehash — JohannesBuchner/imagehash](https://github.com/JohannesBuchner/imagehash)
- [ffmpeg — filtro `select` (detecção de mudança de cena via `scene`)](https://ffmpeg.org/ffmpeg-filters.html#select_002c-aselect)
- [Flet — `flet.canvas` (Context7, `flet-dev/flet`)](https://flet.dev/docs/controls/canvas/)
- [Variância do Laplaciano para detecção de blur — Pech-Pacheco et al., 2000 (referência clássica do método)](https://www.researchgate.net/publication/3945312)
