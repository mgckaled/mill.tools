# Princípios e idiomas recorrentes — a síntese

Documento **capstone**: leia por último. Depois de percorrer a espinha, as bordas e os módulos, os
mesmos padrões apareceram dezenas de vezes. Este doc os reúne num lugar só — é o que transforma "vi 30
arquivos" em "entendo o sistema". Cada princípio remete a onde você já o viu.

---

# PARTE 1 — As 6 regras invioláveis (a bússola)

Tudo no código serve a estas 6 regras (skill `architecture`):

1. **`src/core/` é PURO** — sem `import flet`, sem estado de UI, sem `print`. Para avisar progresso,
   recebe um *callback*; nunca conhece a GUI.
2. **Injeção de dependência na fronteira de rede/modelo** — a única função que toca rede/modelo é
   injetável. O resto é testável sem Ollama/DuckDB/ffmpeg.
3. **Código em inglês** — PT só em labels da GUI e mensagens de exceção *user-facing* do core.
4. **Logging por handler dedicado — nunca `print()`.**
5. **`subprocess` sempre em modo binário** (sem `text=True`); decodificar com `errors="replace"`.
6. **Degradação graciosa** — extra opcional ausente desabilita o recurso com dica, nunca quebra.

---

# PARTE 2 — Os idiomas que se repetem

## 2.1 "Um core, N bordas"

O idioma-mestre. A lógica mora **uma vez** no `core/` puro; cada **borda** (CLI, GUI, Receitas) só a
**traduz** para seu contexto. Você viu isso três vezes:
- **CLI e GUI** chamam o mesmo `run_video_pipeline` (fatia da Sessão 2).
- **CLIEventBus e EventBus** têm o mesmo `emit` (Sessão 3) — o worker fala uma língua, cada borda
  traduz.
- **Receitas** recombinam o mesmo core puro numa cadeia (Sessão 5).

🔑 É o que torna o projeto testável e extensível: adicionar uma borda não toca o core.

## 2.2 Injeção de dependência (o callback que sobe de nível)

A dependência externa é **recebida**, não criada. Você a rastreou subindo de abstração:
- **`progress_cb`** — um número (espinha `ffmpeg.md`).
- **`emit`/`EventBus`** — um vocabulário de eventos (Sessão 3).
- **`embed_fn`, motor DuckDB, `make_llm`** — a rede/modelo/banco (conceitos de RAG/ML/Dados).

🔑 Todos são a **mesma ideia**: a função pura não conhece a coisa pesada; quem chama a passa pronta.
Nos testes, você passa um dublê (`TESTES.md`).

## 2.3 Fonte única (single source of truth)

Cada assunto tem **um** dono. Você viu: `run_ffmpeg` (todo acesso ao ffmpeg), as constantes de
diretório (`utils.md`), `make_llm` (toda chamada de LLM), `cited_source_numbers` (todo parse de `[n]`),
`MODULES` (todo módulo de GUI), `embed_space_id` (todo cache de ML). Consequência: um bug se conserta
num lugar; uma mudança é uma edição.

## 2.4 Import preguiçoso (lazy) + gate

Bibliotecas pesadas/opcionais só carregam **dentro** da função que as usa, e um `is_available()` guarda
o recurso. Você viu no `llm_factory` (nuvem/Ollama), no denoise (Áudio), no `[ml]`/`[nlp]` (ML/NLP), no
embedder (RAG). É o que mantém a **partida rápida** e as dependências **de fato opcionais** (regra nº 6).

## 2.5 O truque de closure `[valor]`

Uma lista de um elemento para uma função interna **mutar** estado do escopo externo (`pipeline_running
= [False]`, `_selected = [value]`, `current_idx = [...]`). Você viu no `segmented_selector`, nos
`blocks/` (`XRefs`), no `app.py`. É Python idiomático que aparece em toda a GUI (`FLET_GUI.md` §4.2,
`decomposicao.md`).

## 2.6 Determinismo

"Mesma entrada → mesmo resultado", uma obsessão saudável: `temperature=0.0` (LLM), `random_state=42`
(k-means/UMAP/t-SNE), `_fix_signs` (PCA), `time.monotonic()` (medir duração). O usuário não deve ver
resultados "pularem" sem motivo (`llm_factory.md`, `MACHINE_LEARNING.md`).

## 2.7 Robustez em duas frentes + defensividade seletiva

Validar mais de uma condição (returncode **e** existência do arquivo — `ffmpeg.md`); tolerar corrupção
(store vazio + aviso — `EMBEDDINGS.md`); engolir erro de uma linha mas gritar na falha do processo;
parse defensivo de `[n]` (nunca inventar citação — `RAG.md`). O padrão: falhar **cedo e claro** onde
importa, **tolerar** o ruído onde não importa.

## 2.8 Privacidade por desenho

O que sai da máquina é minimizado: embeddings **sempre locais**; a IA de Dados vê **só o schema**,
nunca as linhas; a condensação multiturno roda **sempre local**; chaves de nuvem só têm sua **presença**
reportada, nunca o valor. (`RAG.md`, `dados.md`, `ia.md`.)

---

# PARTE 3 — O mapa mental final

Se você tiver que guardar **uma** frase de todo o estudo, é esta:

> **A lógica pura vive no `core/`, desacoplada por injeção de dependência; as bordas (CLI, GUI,
> Receitas) só a traduzem; e um vocabulário compartilhado (Args, eventos, `is_available`) as liga sem
> que nenhuma conheça as outras.**

Tudo o mais — os quirks do Flet, a busca híbrida do RAG, o clustering, os `blocks/` — são detalhes que
servem a essa estrutura. Quando abrir um arquivo novo do projeto, pergunte: *é core puro, borda, ou
contrato entre eles?* A resposta explica quase tudo.

---

# Perguntas de fixação (síntese)

1. Dê **três** exemplos, de camadas diferentes, do idioma "a dependência é recebida, não criada".
2. "Um core, N bordas" — cite as três bordas e o que cada uma traduz.
3. Por que import preguiçoso + `is_available()` são a implementação da regra nº 6 (degradação
   graciosa)?
4. O truque `[valor]` resolve qual limitação de closures em Python? Onde você o viu mais vezes?
5. Complete com suas palavras: "quando abro um arquivo novo do projeto, a primeira pergunta que faço
   é..."
