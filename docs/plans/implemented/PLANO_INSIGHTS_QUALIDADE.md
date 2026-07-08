# Plano — Qualidade da aba Insights (limpeza de texto + gates por idioma)

> **Origem**: avaliação profunda ML/RAG (sessão Cowork, jul/2026 —
> [`docs/reference/AVALIACAO_ML_RAG_FABLE5.md`](../../reference/AVALIACAO_ML_RAG_FABLE5.md)) + caso real
> reportado com screenshot: PDF em inglês (constituição do Claude) produziu resumo dominado por front
> matter e marcadores `--- Página N ---`, keyphrases poluídas ("Página", "January") e a seção Entidades
> pedindo para "instalar o extra de NLP" **com todos os extras instalados** (faltava só o modelo EN).
> Itens dizem *o quê* e *onde*; o *como* é da sessão de implementação (agentes + context7 quando indicado).
>
> **Fronteira com o plano da reindexação**: o `core/text/clean.py` criado aqui será reusado pelo indexer
> do RAG (os marcadores de página hoje também são embeddados nos chunks) — mas essa adoção fica para o
> `PLANO_RAG_ESPACO_EMBEDDING` (exige reindexação). Aqui só se registra o ponteiro no ROADMAP.

## Checklist ativo de salvaguardas (padrões recorrentes — auditar neste escopo)

| Salvaguarda | Situação esperada neste escopo |
|---|---|
| Escritas não-atômicas / `io_atomic` | N/A — este plano não cria persistência nova |
| Timeouts herdados/ausentes | N/A — engines locais, sem rede/subprocesso |
| Duplicação de esqueleto intra-pacote | **Ponto central**: a limpeza nasce em `clean.py` como fonte única — `reader.py`, `summarize.py`, `keywords.py` e (futuro) `rag/indexer` consomem dela; o marcador de página vem de constante compartilhada com `core/document/converter`, nunca regex duplicada |
| Docstring de pacote desatualizado | `text/__init__.py` ganha o módulo novo — atualizar |
| Strings PT no core | Mensagens de gate user-facing (hints de instalação) podem ser PT (exceção formalizada); docstrings/logs em EN |

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline + corpus de reprodução |
| 1 | Verificações guiadas (spaCy EN, YAKE) |
| 2 | `core/text/clean.py` — camada de limpeza compartilhada |
| 3 | `summarize` — split, filtro de candidatas, prior pós-filtro |
| 4 | Gates por idioma (entities + painel) |
| 5 | `keywords` + integração do painel |
| 6 | Verificação + docs |

---

## Fase 0 — Baseline + corpus de reprodução

Suíte `unit` verde. Criar fixture(s) de teste reproduzindo o caso do screenshot: texto extraído de PDF com
`--- Página N ---`, front matter sem pontuação terminal (autores/data/agradecimentos), itens de lista com
travessão, e abreviações (`e.g.`, `i.e.`, `et al.`, `Dr.`, `p. ex.`). Essa fixture é o critério de aceite
das Fases 2–3 — o resumo dela **não** pode conter marcador de página nem o bloco de front matter.

---

## Fase 1 — Verificações guiadas (context7)

1. **spaCy `en_core_web_sm`**: confirmar comando de download e como `spacy.util.is_package` o enxerga
   (o gate `entities.is_available("en")` já resolve o nome via `_MODELS`) — o fix da Fase 4 é de
   *mensagem*, não de mecânica; garantir que a mecânica está mesmo OK.
2. **YAKE**: confirmar se o `KeywordExtractor` instalado aceita stopwords adicionais por parâmetro ou se a
   filtragem de artefatos ("página", meses soltos) deve ser pós-processo nosso — o resultado decide onde o
   item 5.1 mora.

---

## Fase 2 — `core/text/clean.py` (novo, fonte única de limpeza)

Módulo puro com uma API pequena (ex.: `clean_document_text(text) -> str` + helpers testáveis). Escopo:

1. **Marcadores de página**: remover as linhas `--- Página N ---`. A string é gerada em
   `core/document/converter.py` — extrair o formato para constante compartilhada (o converter importa de
   `clean.py` ou ambos de um lugar comum; decidir na implementação) para nunca haver duas fontes.
2. **Fronteiras de lista**: tratar quebra de linha de item de lista (`-`/`–`/`•`) como fronteira de
   sentença — hoje itens sem pontuação se fundem com o parágrafo seguinte.
3. **Filtro de não-prosa**: descartar (ou isolar) linhas que não parecem prosa — curtas demais, sem
   pontuação terminal, metadata em title-case (autores, datas soltas). Conservador: na dúvida, manter.
4. **Máscara de abreviações**: proteger `e.g.`, `i.e.`, `et al.`, `Dr.`, `Sr.`, `Sra.`, `p. ex.` (lista
   pequena e documentada) antes do split de sentenças, restaurando depois.

Consumidores nesta passagem: `summarize`, `keywords` e o `insights_panel` (via `reader` ou chamada
explícita — decidir na implementação mantendo `reader.py` fino). O `rag/indexer` **não** adota aqui (ver
fronteira no topo).

---

## Fase 3 — `summarize`: o resumo não pode premiar boilerplate

1. **Split com abreviações**: `_SENT_BOUNDARY` passa a operar sobre o texto mascarado da Fase 2 — some o
   corte em `(e.g.` visto no screenshot.
2. **Filtro de candidatas**: antes do grafo, descartar sentenças fora de uma faixa de comprimento
   (mín/máx documentados) e as que a Fase 2 marcou como não-prosa.
3. **Prior de posição pós-filtro**: o lead-prior (0.15) hoje premia o front matter porque ele é a
   "primeira sentença". Aplicar o prior **depois** da filtragem de boilerplate; avaliar reduzi-lo quando o
   texto vier de `kind="document"` (front matter é a norma em PDF; em transcrição o prior segue valendo).
   Se a redução por kind exigir passar o kind até aqui, avaliar custo — o filtro pós-boilerplate sozinho
   já pode bastar (a fixture da Fase 0 decide).
4. Critério de aceite: na fixture, nenhuma sentença do resumo contém marcador de página, lista de autores
   ou fragmento terminado em abreviação.

---

## Fase 4 — Gates por idioma (o bug de mensagem do screenshot)

1. **`entities.is_available` → razão, não só booleano** (`core/text/entities.py`): o chamador precisa
   distinguir "extra `[nlp]` ausente" de "modelo do idioma X ausente". Menor mudança possível (ex.: função
   irmã `availability(lang) -> hint | None`) — sem quebrar os call sites existentes do booleano.
2. **`insights_panel`** (`gui/views/insights_panel.py`): mensagem da seção Entidades passa a ser específica
   — para o caso do screenshot: "Modelo de inglês ausente: `uv run python -m spacy download
   en_core_web_sm`" em vez do genérico "Instale o extra de NLP e o modelo spaCy".
3. **Setup documentado**: onde o download do `pt_core_news_sm` está registrado (CLAUDE.md §Testes/deps +
   skill `ml-rag`), acrescentar o `en_core_web_sm` como opcional-recomendado para corpus com material EN.

---

## Fase 5 — `keywords` + integração do painel

1. **Poluição do YAKE**: com a Fase 2, "Página" some na fonte; para artefatos restantes (meses soltos,
   números de página que sobrarem), aplicar o mecanismo decidido na Fase 1.2 (stopwords extras ou
   pós-filtro). Não sobre-engenheirar: o objetivo é o top-10 sem lixo estrutural, não keyphrases perfeitas.
2. **`insights_panel._compute`**: passar a operar sobre o texto limpo (uma chamada de limpeza, três
   engines). Conferir que `detect_lang` roda sobre o texto limpo também (front matter EN num doc PT podia
   enviesar a detecção).

---

## Fase 6 — Verificação + docs

1. Suíte `unit` verde; `ruff` limpo; cobertura de `core/text/` sem regressão; a fixture da Fase 0 passa.
2. Re-auditar o checklist de salvaguardas do topo (em especial a fonte única do marcador de página).
3. **Skill `ml-rag`** (obrigatório): seção `core/text/` ganha o `clean.py` (responsabilidade + quem
   consome); registrar a decisão do prior pós-filtro no `summarize` e o gate por idioma do `entities`.
4. **ROADMAP.md**: registrar o ponteiro "adotar `clean.py` no `rag/indexer` → PLANO_RAG_ESPACO_EMBEDDING
   (exige reindexação)".
5. **CLAUDE.md**: conferir §Módulo Transcrição (aba Insights) e a linha de stack — nada afirmado deve
   mudar, mas validar.
6. Entrada no `HISTORY.md` (decisão: limpeza como camada única em `core/text/clean.py`; prior de posição
   pós-filtro; gates de NLP por idioma). Plano → `docs/plans/implemented/`.

---

## Não-achados dignos de nota (não "consertar")

- O TextRank em si (grafo TF-IDF + PageRank + MMR + amostragem estratificada) está **correto** — o
  problema do screenshot é 100% de *entrada suja* e prior mal posicionado, não do ranking. Não trocar de
  motor nem adicionar dependência (sumy/nltk seguem vetados pelo princípio offline).
- A Insights continuar **100% ML local e instantânea** é decisão de produto — resumo abstrativo via LLM já
  tem casa (aba Análise / hub de IA). Um botão "Refinar com IA" fica fora deste plano; se desejado,
  registrar como ideia no ROADMAP.
- `_MAX_SENTENCES = 400` e a amostragem estratificada não são tocados.
- A heurística `detect_lang` (stopwords) é suficiente — não adotar lib de detecção de idioma.
