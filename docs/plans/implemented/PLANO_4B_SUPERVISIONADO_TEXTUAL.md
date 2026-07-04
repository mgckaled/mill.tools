# Plano 4B — Classificação supervisionada + inteligência textual — plano de implementação

**Documento de execução — plano de implementação detalhado (teor técnico elevado)**
Data: 23 de junho de 2026 · Roadmap de origem: `docs/ROADMAP.md` (Plano 4, parte B) · Fundações: Planos 0/1/2/3/4A (✅) · Padrão de referência: skill `architecture`

> **Invocação da skill.** Ao executar, **invoque a skill `architecture`**: núcleo puro (§1), camadas (§2), limites/coesão e "divide-se ao tocar" (§3), `tabs/`/sub-builders (§4), fluxo core → extra/gate → CLI → GUI → testes (§5), `TYPE_CHECKING` (§7), checklist (§8).

> **Relação com 4A e 4C.** O 4A entregou a **geometria** (cluster/mapa/relacionados) sem rótulos. O 4B traz o que precisa de **rótulo ou de NLP textual**: classificação de perfil, palavras-chave, resumo extractivo e entidades. **Importante:** o 4B constrói os *motores* textuais (`core/text/`); o futuro **Plano 4C ("ficha de leitura")** apenas **compõe** esses motores numa apresentação por arquivo — então os motores nascem aqui, reutilizáveis, sem duplicação.

---

## Sumário

1. Objetivo e escopo
2. Achados da varredura web (decisões técnicas)
3. A decisão central: de onde vêm os rótulos
4. Decisões de arquitetura
5. Desenho técnico — classificação (`core/ml/classify.py`)
6. Desenho técnico — textual (`core/text/`)
7. Dependências (extra `[nlp]`, gate, modelo spaCy)
8. GUI e CLI
9. Cache, complexidade, numerics
10. Passos de implementação (commits)
11. Testes
12. Critérios de aceitação
13. Riscos e o que **não** fazer
14. O que destrava

---

## 1. Objetivo e escopo

Entregar a camada **supervisionada e textual**: (a) **classificar o perfil** de uma transcrição/documento (Aula, Entrevista, Tutorial, Científico, Administrativo, Notas…) para auto-sugerir o perfil de análise; (b) **palavras-chave** (YAKE), **resumo extractivo** (TextRank) e **entidades** (spaCy NER) sobre o documento inteiro. Tudo torch-free.

**No escopo:** `core/ml/classify.py` (zero-shot + upgrade supervisionado), pacote novo `core/text/{keywords,summarize,entities}.py`, extra `[nlp]`, gate, cache por `(path, mtime)`, superfície na Transcrição/Documentos (auto-sugestão de perfil + campos textuais) e Biblioteca (auto-tags), CLI (`ai classify`/`ai keywords`/`ai summary`/`ai entities`), testes. **Fora do escopo:** a composição "ficha de leitura" (Plano 4C), que reusa estes motores.

---

## 2. Achados da varredura web (decisões técnicas)

**Classificação sem rótulos → zero-shot por protótipo de embedding.** A varredura confirma o padrão: como os rótulos (perfis) são **textuais**, projetam-se no mesmo espaço dos documentos; classifica-se um doc pela **menor distância ao protótipo** de cada classe. Com encoder pré-treinado + **L2-normalização + nearest-centroid**, obtém-se resultado forte **sem nenhum meta-treino**. *Influência:* a classificação parte **zero-shot** (sem rótulos), reusando os embeddings do Plano 3 — só os perfis precisam ser embeddados uma vez (cacheado).

**spaCy `pt_core_news_sm` é CNN (thinc), torch-free.** O modelo pequeno é um pipeline CNN otimizado para CPU (tok2vec/parser/ner); **apenas** as variantes `_trf` (transformer) puxam torch. *Influência:* fixar o modelo `sm` (ou `md`) mantém o NER torch-free; o `_trf` fica proibido.

**Resumo extractivo sem download surpresa.** O `sumy` é simples mas costuma exigir dados do `nltk` (punkt) baixados em runtime — atrito num app local-first/offline. *Influência:* implementar um **TextRank self-contained** (divisor de sentenças simples + `TfidfVectorizer` do sklearn para o grafo de similaridade + power-iteration) evita o download e mantém tudo sob `[ml]`/`[nlp]` já controlados.

Fontes na seção final.

---

## 3. A decisão central: de onde vêm os rótulos

Esta é a pergunta que o 4B precisa resolver. Resposta em três camadas:

**Conjunto de classes = os perfis de análise que já existem** (`src/analysis/profiles/`): `default`, `lecture`, `interview`, `tutorial`, `scientific`, `administrative`, `literary`, `review`, `storytelling`, `notes`, `tldr`, `flashcards`. Não se inventa taxonomia nova — reusa-se a que o app já usa no `--profile`.

**Cold-start = zero-shot, sem rótulos.** Cada perfil vira um **protótipo**: um texto canônico curto (o `label` + uma descrição de uma linha do que aquele perfil cobre) é embeddado uma vez (uma chamada ao embedder por perfil, cacheada). Classifica-se um documento pelo **cosseno ao protótipo mais próximo** sobre `features.document_matrix` (Plano 3). **Zero rótulo, zero treino** — funciona desde o primeiro uso.

**Upgrade = supervisão a partir das correções do usuário.** Quando o usuário **confirma ou corrige** a sugestão (ele já escolhe `--profile` hoje — isso é um rótulo de ouro), o par `(document_vector, profile)` é gravado. Acumulados rótulos suficientes (≥ k por classe), treina-se um classificador linear (LogReg/LinearSVC do sklearn sobre `dm.X`) que **supera** o protótipo, persistido pelo **store versionado do Plano 3**. Até lá, vale o zero-shot. É *human-in-the-loop* sem nenhuma etapa de rotulagem dedicada — o rótulo nasce do fluxo normal de uso.

Essa escalada (zero-shot → supervisionado conforme correções chegam) é o coração do 4B e resolve a objeção "de onde vêm os rótulos" sem pedir trabalho extra ao usuário.

---

## 4. Decisões de arquitetura

**Dois mundos, dois lugares.** Classificação é geometria de embeddings + sklearn → `core/ml/classify.py` (reusa `features`/`store`). NLP textual (string in → estrutura out) é outro domínio → pacote novo **`core/text/`** (`keywords`, `summarize`, `entities`), puro e independente do `core/ml`. Um arquivo, uma responsabilidade (skill §3).

**Reuso, não recálculo.** A classificação usa `dm.X` (vetores já no índice). Só os **protótipos** dos perfis são embeddados (uma vez, cacheados em `~/.mill-tools/ml/`). Os motores textuais leem o **arquivo completo** (não chunks) — é a leitura de documento, distinta da recuperação do RAG.

**Gate granular.** Classificação zero-shot = numpy + embedder (já existe); supervisionada = `[ml]` (já existe). Textual = extra novo `[nlp]`; cada motor degrada sozinho (keywords/summary podem rodar sem spaCy; NER desabilita se o modelo faltar, como o Tesseract).

**Motores aqui, composição depois.** `core/text/*` expõem funções puras; o Plano 4C só as orquestra numa ficha. Sem duplicação.

---

## 5. Desenho técnico — classificação (`core/ml/classify.py`)

```python
@dataclass(frozen=True, slots=True)
class Classification:
    profile_id: str          # nearest profile (or trained prediction)
    confidence: float        # top-1 cosine (zero-shot) or calibrated proba (supervised)
    margin: float            # top1 - top2 (uncertainty signal)
    method: str              # "zeroshot" | "supervised"

def profile_prototypes(embed_fn, *, cache_dir=None) -> tuple["np.ndarray", list[str]]:
    """Embed one canonical text per analysis profile (label + 1-line description).
    Cached by profile-set hash; one embedder call per profile, once."""

def classify_zeroshot(doc_vec, P, ids) -> Classification:
    """Nearest-prototype over L2-normalized vectors: argmax cos(doc_vec, P)."""

def train_supervised(dm, labels, *, signature) -> "Pipeline":
    """LinearSVC/LogReg over dm.X (already L2-normed). class_weight='balanced',
    CalibratedClassifierCV for probabilities. Persisted via ml.store (versioned)."""

def classify(doc_vec, *, embed_fn, dm=None) -> Classification:
    """Use the trained model if available & valid (ml.store), else zero-shot."""
```

**Detalhes.** Vetores já L2-normalizados (acessor do 4A/Plano 3) → modelos lineares operam na geometria do cosseno. `margin = top1 − top2` vira o sinal de incerteza ("classificação duvidosa" na GUI). O supervisionado só entra quando o `store` tem um modelo válido para a `signature` atual (conjunto de rótulos + `sklearn.__version__`); senão, zero-shot. Protótipos: o texto-semente por perfil é autorado (curto) ou derivado do `label` + objetivo do perfil; embeddado uma vez.

---

## 6. Desenho técnico — textual (`core/text/`)

### 6.1 `keywords.py` — YAKE

```python
def keyphrases(text: str, *, lang="pt", top_n=10, ngram=3) -> list[tuple[str, float]]:
    """Unsupervised keyphrase extraction (YAKE). Lower score = more relevant."""
```
O(N) em tokens; YAKE é estatístico (sem modelo neural), com deduplicação de candidatos. `lang` por detecção/heurística simples. Pequeno, torch-free.

### 6.2 `summarize.py` — TextRank self-contained

```python
def extractive_summary(text: str, *, sentences=5, lang="pt") -> list[str]:
    """In-house TextRank: split into sentences, build a TF-IDF cosine sentence
    graph (sklearn TfidfVectorizer), rank by power-iteration PageRank, return the
    top sentences in original order. No nltk download."""
```
Divisor de sentenças por regex robusto (sem `nltk.punkt`); grafo `S×S` de cosseno; PageRank por iteração de potência (numpy). O(S²) em sentenças — capar `sentences`/amostrar acima de um teto. Auto-contido sob deps já presentes.

### 6.3 `entities.py` — spaCy NER

```python
def entities(text: str, *, lang="pt") -> list[tuple[str, str]]:
    """Named entities (PER/ORG/LOC/MISC/DATE) via spaCy pt_core_news_sm (CNN, CPU)."""

def is_available() -> bool:
    """True if spacy AND the language model are importable/loaded."""
```
Modelo CNN (torch-free); **carga única** (singleton lazy) reusada entre chamadas. Gate verifica o pacote **e** o modelo (o modelo não é um extra pip limpo — instala-se via `python -m spacy download pt_core_news_sm` ou wheel fixada; o gate trata ausência como o Tesseract). `_trf` proibido (puxaria torch).

---

## 7. Dependências (extra `[nlp]`, gate, modelo spaCy)

```toml
[project.optional-dependencies]
nlp = ["yake>=0.4", "spacy>=3.7"]   # summary é self-contained (sklearn já em [ml])
```

- **YAKE** e **spaCy** sob `[nlp]`; o resumo não precisa de dep nova (usa o `TfidfVectorizer` do `[ml]`). O **modelo** `pt_core_news_sm` é passo à parte (download), documentado no README como o Tesseract.
- Gate: `text.keywords.is_available()` (yake), `text.entities.is_available()` (spacy + modelo). Imports preguiçosos; tipagem sob `TYPE_CHECKING`. Quem não usa não paga; NER ausente desabilita só o campo de entidades.

---

## 8. GUI e CLI

**Transcrição/Documentos — auto-sugestão de perfil (integração de baixo atrito).** Ao produzir/abrir uma transcrição, `classify` sugere o perfil e **pré-seleciona** o dropdown de `--profile` no `form_view` (com um chip "sugerido: Aula · 0,82"). O usuário confirma ou troca — e essa escolha vira rótulo (seção 3). Margem baixa → chip "incerto". Campos textuais (keywords/resumo/entidades) aparecem no painel de resultado, gated por `[nlp]`. "Divide-se ao tocar": se o `form_view`/`view` da Transcrição/Documentos passar do teto, fatiar antes de adicionar.

**Biblioteca — auto-tags.** Palavras-chave por item viram etiquetas pesquisáveis (reusa `keywords`), cacheadas.

**CLI (paridade, `cli/ai.py`):** `ai classify <path>` (perfil + confiança/margem), `ai keywords <path>`, `ai summary <path> [--sentences]`, `ai entities <path>`. Read-only, reusam o core, UTF-8. (Os quatro são também os blocos que o Plano 4C vai compor.)

---

## 9. Cache, complexidade, numerics

**Cache.** Classificação, keywords, resumo e entidades são **determinísticos** → cacheados por `(path, mtime)` em `~/.mill-tools/` (convenção `assess`/`datacard`/Plano 3). Segunda leitura instantânea; recomputa só quando o arquivo muda. Protótipos de perfil cacheados por hash do conjunto de perfis.

**Complexidade (máquina-alvo).** keywords O(N); resumo O(S²) em sentenças (capar); NER O(N) a milhares–dezenas de milhares de palavras/s na CPU + carga única do modelo (~0,5–1 s, amortizada); classificação O(C·D) (C≈12 perfis) — desprezível. Tudo off-thread (`page.run_task`+`asyncio.to_thread`).

**Numerics/determinismo.** Vetores float32 L2-normalizados; zero-shot e PageRank determinísticos; o supervisionado com `random_state` fixo e `CalibratedClassifierCV` para probabilidades comparáveis à confiança do zero-shot.

---

## 10. Passos de implementação (commits)

**Commit 1 — classificação zero-shot.** `core/ml/classify.py` (protótipos + `classify_zeroshot` + `classify` com fallback) + testes. Reusa embedder/features; sem dep nova além do que já existe.

**Commit 2 — textual: keywords + resumo.** `core/text/{keywords,summarize}.py` + extra `[nlp]` (yake) + testes (`importorskip("yake")`; resumo sem skip — usa sklearn).

**Commit 3 — textual: NER.** `core/text/entities.py` (spaCy, singleton, gate de modelo) + testes (`importorskip("spacy")` + skip se modelo ausente, padrão do Tesseract).

**Commit 4 — upgrade supervisionado.** `train_supervised` + persistência no `store` + captura de rótulos das confirmações do usuário + testes.

**Commit 5 — CLI** (`classify`/`keywords`/`summary`/`entities`) + testes de dispatch.

**Commit 6 — GUI** (auto-sugestão de perfil na Transcrição/Documentos + campos textuais + auto-tags na Biblioteca) + construct-smoke + smoke manual.

**Commit 7 — docs.** CLAUDE.md/README/skills.

Ordem core → CLI → GUI; risco crescente; suíte verde entre commits.

---

## 11. Testes

**`tests/core/ml/test_classify.py`** (`importorskip("sklearn")` só no supervisionado): protótipos — `embed_fn` falso retorna vetores conhecidos por perfil → `classify_zeroshot` escolhe o esperado; `margin` correto; doc ambíguo → margem baixa. `train_supervised` — rótulos sintéticos → modelo prediz; persistência/validação por signature (reusa `store`); cold-start (poucos rótulos) → cai no zero-shot.

**`tests/core/text/`** (espelha `src/`): `test_keywords.py` (`importorskip("yake")`) — texto com termos óbvios → no top-n; `test_summarize.py` (sem skip) — documento com frases redundantes vs centrais → as centrais no resumo; ordem original preservada; `sentences` respeitado; texto vazio/1 frase (bordas). `test_entities.py` (`importorskip("spacy")` + skip se modelo ausente) — texto com nomes/lugares → entidades certas; `is_available` False sem modelo.

**CLI** — `tests/cli/test_ai_cli.py`: os quatro subcomandos no parser + dispatch (mock dos cores); arquivo inexistente → `sys.exit`.

**GUI** — construct-smoke + manual. Cobertura dos núcleos novos ≥ 90%.

---

## 12. Critérios de aceitação

- Classificação **zero-shot** funciona sem rótulos (protótipos de perfil cacheados); **upgrade supervisionado** entra automaticamente quando há rótulos+modelo válidos (store versionado), com fallback transparente.
- `core/text/{keywords,summarize,entities}` puros, torch-free; resumo **self-contained** (sem download nltk); NER em CNN `sm` (sem `_trf`/torch); gate por motor.
- Extra `[nlp]`; base intacta; modelo spaCy documentado como passo à parte; degradação graciosa.
- GUI auto-sugere o perfil (pré-seleção + confiança/margem) e a escolha do usuário vira rótulo; campos textuais e auto-tags gated.
- CLI `classify`/`keywords`/`summary`/`entities` em paridade; os motores ficam prontos para o Plano 4C compor.
- Cache por `(path, mtime)`; contrato de GUI/eventos preservado; `view`/`form_view` tocados não inflados (divide-se ao tocar).
- `uv run pytest -m unit` verde; `ruff` limpo; cobertura ≥ 90%; checklist da skill `architecture` satisfeito.

---

## 13. Riscos e o que **não** fazer

**Rótulos:** não montar etapa de rotulagem dedicada — os rótulos nascem das confirmações de perfil (seção 3). **spaCy:** não usar `_trf` (puxa torch); fixar `sm`/`md`. **Resumo:** não depender de download nltk em runtime — TextRank self-contained. **Quadrático:** capar o resumo por nº de sentenças. **Zero-shot:** ser honesto na GUI sobre a confiança (mostrar margem; baixa → "sugestão incerta"). **Duplicação:** não reimplementar keywords/resumo no Plano 4C — ele compõe os motores daqui. **Divide-se ao tocar:** fatiar `form_view`/`view` de Transcrição/Documentos se passarem do teto ao receber os novos campos.

---

## 14. O que destrava

O 4B fecha a onda semântica/textual e entrega os **motores** (`classify`, `keywords`, `extractive_summary`, `entities`) que o **Plano 4C ("ficha de leitura")** vai compor num "raio-X por arquivo" — somando os campos baratos (stats/legibilidade, score de qualidade, ritmo de fala) sobre a mesma leitura. A auto-sugestão de perfil também alimenta, no futuro, o roteamento automático do Analyzer.

---

## Fontes

- [Unsupervised text classification with word embeddings — Max Halford (protótipos/centroides)](https://maxhalford.github.io/blog/unsupervised-text-classification/)
- [Getting Started with Zero-Shot Text Classification — MachineLearningMastery](https://machinelearningmastery.com/getting-started-with-zero-shot-text-classification/)
- [spacy/pt_core_news_sm — Hugging Face (CNN, CPU)](https://huggingface.co/spacy/pt_core_news_sm)
- [Install spaCy — modelos e pipelines](https://spacy.io/usage)
