# Guia de Estudo — mill.tools

Roteiro para entender o projeto a fundo, arquivo por arquivo. Este guia é o **índice e o
professor**: ele organiza o percurso, aponta para os documentos de detalhe e faz as perguntas de
fixação. O detalhamento linha a linha de cada arquivo mora em `arquivos/<nome>.md`. Termos técnicos
transversais moram em `GLOSSARIO.md` (cada doc de arquivo também tem seu próprio glossário no fim).

## Como usar

1. Leia a seção da sessão aqui **primeiro** (o "porquê" e o lugar da peça no todo).
2. Abra o doc de detalhe referenciado e leia o código junto.
3. Volte aqui e responda as **perguntas de fixação** sem consultar. Confira depois.
4. Todo termo novo que travar → confira no glossário (ou peça para adicioná-lo).

## Mapa do percurso

| # | Sessão | Estado | Detalhe |
|---|---|---|---|
| 1 | Espinha reutilizável | ✅ documentada | `arquivos/ffmpeg.md`, `arquivos/utils.md`, `arquivos/llm_factory.md` |
| 2 | Fatia vertical de um módulo simples (core → cli → gui → testes) | ✅ documentada | `arquivos/sessao2-vertical-video.md` |
| 3 | Contrato de eventos (PipelineEvent, worker, EventBus, spinner) | ✅ documentada | `conceitos/EVENTOS.md` |
| 4 | Demais módulos como variações do padrão | ✅ documentada | `conceitos/decomposicao.md` + `modulos/{audio,imagem,documentos,dados,transcricao,biblioteca}.md` |
| 5 | Diferencial: RAG / ML / NLP / Observatório | ✅ documentada | conceitos: `EMBEDDINGS`·`RAG`·`MACHINE_LEARNING`; hubs: `modulos/{ia,observatorio,receitas}.md` |

## Mapa da Sessão 4 — cada módulo como variação

Depois de traçar o Vídeo (Sessão 2), os demais são **deltas**. O que cada um adiciona de novo:

| Módulo | Core (biblioteca) | Externo/em-processo | Novidade-chave | Testes |
|---|---|---|---|---|
| [Áudio](modulos/audio.md) | ffmpeg | externo | cadeia de estágios · gate de extra · player fora do Flet | ffmpeg mockado |
| [Imagem](modulos/imagem.md) | Pillow | em-processo | **sem `run_ffmpeg`** · `transform/` pacote · imagem→texto | Pillow real |
| [Documentos](modulos/documentos.md) | pymupdf | em-processo | OCR híbrido · reúso cross-módulo | pymupdf real |
| [Dados](modulos/dados.md) | DuckDB | em-processo | fronteira de privacidade · `ensure_select` · async-na-UI | DuckDB real |
| [Transcrição](modulos/transcricao.md) | faster-whisper + LLM | GPU + externo | form adaptativo · cadeia de IA · amarra espinha/ML/RAG | — |
| [Biblioteca](modulos/biblioteca.md) | (nenhum) | read-only | **sem worker/pipeline** · scanner · 4 modos | core-direto |

Padrões de decomposição (`blocks/`/`tabs/`/`_state`/`registry/`) → [`conceitos/decomposicao.md`](conceitos/decomposicao.md).

## Materiais transversais

- **[`TESTES.md`](conceitos/TESTES.md)** — guia completo de testes de software e `pytest` (fundamentos →
  fixtures/mocks/markers → plugins → cobertura → a regra anti-OOM do projeto), com exemplos reais de
  `tests/`. Leia antes/junto da parte de testes da Sessão 2.
- **[`CLI.md`](conceitos/CLI.md)** — guia completo de interfaces de linha de comando e `argparse` (fundamentos
  de CLI → parser/posicionais/opções/`Namespace` → subcomandos e despacho → arquitetura da `cli/` do
  projeto → `CLIEventBus`), com exemplos reais de `main.py` e `src/cli/`. Leia antes/junto da camada
  CLI da Sessão 2.
- **[`FLET_GUI.md`](conceitos/FLET_GUI.md)** — guia completo do Flet 0.85.2 e da GUI (conceitos gerais →
  controles/layout/estilo → modelo de atualização e threading → design system e sistema de módulos do
  projeto → a ponte worker→UI → tabela de quirks da 0.85), com exemplos reais de `src/gui/`. Leia
  antes/junto da camada GUI da Sessão 2 e da Sessão 3 (contrato de eventos).

Conceitos para a Sessão 5 (RAG/ML) — ler nesta ordem:

- **[`EMBEDDINGS.md`](conceitos/EMBEDDINGS.md)** — a fundação: vetor, dimensão, embedding, similaridade de
  cosseno, normalização L2, mean-pooling. Base comum de RAG e ML. Exemplos de `core/rag/` e `core/ml/`.
- **[`RAG.md`](conceitos/RAG.md)** — o RAG completo: chunking, busca híbrida (densa + BM25), fusão RRF, MMR, piso
  de relevância, citações, gate de cobertura. Requer `EMBEDDINGS.md`.
- **[`MACHINE_LEARNING.md`](conceitos/MACHINE_LEARNING.md)** — ML clássico torch-free (clustering, PCA/t-SNE/UMAP,
  outliers, classificação zero-shot→supervisionada) + NLP (YAKE, TextRank, spaCy NER). Requer
  `EMBEDDINGS.md`.
- **[`decomposicao.md`](conceitos/decomposicao.md)** — os padrões `blocks/`/`tabs/`/`_state`/`registry/`.
- **[`PRINCIPIOS.md`](conceitos/PRINCIPIOS.md)** — capstone: os idiomas recorrentes + as 6 regras (leia por último).
- **[`PERSISTENCIA.md`](conceitos/PERSISTENCIA.md)** — onde as coisas ficam entre sessões (`output/`, `~/.mill-tools/`).
- **[`APENDICE_WINDOWS_HARDWARE.md`](conceitos/APENDICE_WINDOWS_HARDWARE.md)** — quirks de Windows, GPU/BSOD, anti-bot.
- **[`GLOSSARIO.md`](GLOSSARIO.md)** — termos técnicos transversais.

> Índice navegável completo: **[`README.md`](README.md)**.

## As 6 regras invioláveis (a bússola)

Tudo no código serve a estas 6 regras (skill `architecture`). Elas se repetem em toda sessão:

1. **`src/core/` é PURO** — sem `import flet`, sem estado de UI, sem `print`. Para avisar progresso,
   recebe um *callback* por parâmetro; nunca conhece a GUI.
2. **Injeção de dependência na fronteira de rede/modelo** — a única função que toca rede/modelo é
   injetável (ex.: `progress_cb`, `embed_fn`). O resto é testável sem Ollama/DuckDB/ffmpeg.
3. **Código em inglês** — PT só em labels da GUI e mensagens de exceção *user-facing* do core.
4. **Logging por handler dedicado — nunca `print()`.**
5. **`subprocess` sempre em modo binário** (sem `text=True`); decodificar com
   `.decode("utf-8", errors="replace")`.
6. **Degradação graciosa** — extra opcional ausente desabilita o recurso com dica, nunca quebra.

---

# Sessão 1 — A espinha reutilizável

Quatro arquivos que quase todo módulo reusa. Entender estes destrava metade do resto. Ordem de
leitura sugerida: `io_types` (aqui embaixo) → `ffmpeg.md` → `utils.md` → `llm_factory.md`.

## 1.1 `src/core/io_types.py` — o tipo mais básico (15 linhas, sem doc próprio)

```python
@dataclass
class InputItem:
    kind: str   # "url" | "local"
    value: str  # URL completa ou caminho absoluto
```

Representa **uma** entrada — URL remota ou arquivo local — num objeto com campos nomeados. CLI e GUI
classificam o que o usuário digitou e produzem um `InputItem`; do meio do pipeline em diante, tudo
fala essa língua em vez de strings soltas. Mora em `core/` porque é *puro* (não importa Flet nem
argparse) → CLI **e** GUI reusam o mesmo tipo. É a regra 1 em miniatura. `dataclass` em vez de tupla
`(kind, value)` porque campos nomeados são auto-documentados e imunes a erro de ordem.

## 1.2 `ffmpeg.py` → **detalhe em [`arquivos/ffmpeg.md`](arquivos/ffmpeg.md)**

A única porta para o programa externo `ffmpeg`. Ensina: processos e canais (stdout/stderr), o
deadlock de buffer e a thread que o evita, o callback de progresso (`progress_cb`), validação dupla
(returncode + existência do arquivo) e o quirk do `cwd` no Windows.

## 1.3 `utils.py` → **detalhe em [`arquivos/utils.md`](arquivos/utils.md)**

Constantes de diretório (fonte única de caminhos), `sanitize_filename` (defensividade de Windows em
regex), `TqdmLoggingHandler` + `setup_logging` (logging que não quebra a barra de progresso) e
`check_dependencies` (falha cedo com mensagem útil).

## 1.4 `llm_factory.py` → **detalhe em [`arquivos/llm_factory.md`](arquivos/llm_factory.md)**

A fábrica de modelos de linguagem. Ensina: o padrão *Factory*, roteamento por prefixo de nome
(Ollama/Gemini/GLM), import preguiçoso, o funil único que permite cronometrar toda chamada
(`_TimingCallback`), segredos no `.env` e `temperature=0.0` (determinismo).

---

## Perguntas de fixação — Sessão 1

Responda sem consultar; depois confira nos docs de detalhe.

### `io_types.py`
1. Por que `InputItem` mora em `core/` e não dentro da pasta da CLI ou da GUI?
2. Que vantagem um `dataclass` tem sobre uma tupla `(kind, value)`?

### `ffmpeg.py`
3. Numa conversão longa, por que o ffmpeg travaria se lêssemos só o stdout? (use a palavra "buffer")
4. Se a GUI e a CLI usam o **mesmo** `run_ffmpeg`, como cada uma mostra o progresso de um jeito
   diferente (barrinha vs. texto no terminal)?
5. Por que a função faz **duas** checagens de falha no fim, e não só a do `returncode`?
6. Sem `text=True` no `Popen`, o código lê bytes e decodifica à mão. Que problema de Windows isso
   evita?

### `utils.py`
7. Por que centralizar todas as constantes de diretório num arquivo só? Quem se beneficia disso?
8. `sanitize_filename` troca `:` por hífen em vez de simplesmente removê-lo. Por quê? (pense no NTFS)
9. Qual o problema que o `TqdmLoggingHandler` resolve? O que aconteceria com um `logging` comum
   durante uma barra de progresso?
10. O que `shutil.which` faz, e por que `check_dependencies` roda no **início** do app?

### `llm_factory.py`
11. Explique o padrão *Factory* com suas palavras: o que `make_llm` esconde do chamador?
12. Por que os imports das bibliotecas de nuvem (Gemini/GLM) ficam **dentro** das funções `_make_*`
    e não no topo do arquivo?
13. Como o projeto consegue cronometrar **toda** chamada de LLM sem colocar código de cronômetro em
    cada arquivo que usa um modelo?
14. Por que `temperature=0.0` é o padrão para as tarefas deste projeto?
15. Onde ficam as chaves de API, e o que acontece se faltar a chave quando você pede um modelo de
    nuvem?

---

*Próxima sessão (2): uma fatia vertical de um módulo simples, de ponta a ponta
(core → cli → gui → testes), para aprender o padrão que se repete em todos os módulos.*
