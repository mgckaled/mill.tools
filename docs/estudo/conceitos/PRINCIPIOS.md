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

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. Exemplos válidos em três camadas: `progress_cb` (espinha — um número), `emit`/bus (eventos — um
   vocabulário), `embed_fn`/`make_llm`/motor DuckDB (rede/modelo/banco). Em todos, quem chama passa a
   dependência pronta.
2. **CLI** (traduz eventos em tqdm/terminal), **GUI** (traduz em barra/painéis via pubsub) e
   **Receitas** (normaliza callbacks para `ctx.emit` numa cadeia). Cada uma traduz o mesmo core para
   seu contexto.
3. O import lazy garante que a lib pesada só carrega se o recurso for acionado (o extra pode nem
   estar instalado); o `is_available()` permite ao gate **desabilitar com dica** em vez de estourar
   um `ImportError` — exatamente a definição de degradação graciosa.
4. Uma closure pode ler variáveis do escopo externo, mas **reatribuir** criaria uma variável local
   nova. Mutar `x[0]` numa lista de 1 elemento contorna isso. Visto no `segmented_selector`, em
   `pipeline_running`, `current_idx` e nos `blocks/`.
5. "...este arquivo é **core puro**, **borda**, ou **contrato** entre eles?" — a resposta posiciona o
   arquivo na arquitetura e explica quase tudo sobre o que ele pode ou não fazer.

</details>

## Desafios

- **D1 (Feynman)** Explique "um core, N bordas" em **3 frases**, sem nenhum termo técnico, para
  alguém que nunca programou. Se precisar de jargão, a camada de baixo ainda não consolidou.
- **D2 (projete)** O projeto vai ganhar uma **quarta borda**: uma API HTTP local (`POST /transcribe`
  dispara um pipeline). Usando os idiomas deste doc, liste o que precisa ser **criado** — e o que
  **não** precisa ser tocado.
- **D3 (ache o bug)** Sintoma real: um usuário reporta que um nome de arquivo com "ç" quebra uma
  operação nova com `UnicodeDecodeError`. Sem ver o código: qual regra provavelmente foi violada, em
  que camada o bug mora, e onde você procuraria primeiro?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — Exemplo de resposta: "A receita do bolo fica escrita **uma vez só** num caderno. Tanto a
  confeitaria de balcão quanto o serviço de entrega usam o **mesmo** caderno — cada uma só muda a
  embalagem e o jeito de servir. Se a receita melhora, os dois lados melhoram juntos, sem ninguém
  reescrever nada."
- **D2** — Criar: a borda em si (`api/`), que traduz o request nos `Args` do módulo (como a CLI traduz
  o `Namespace`) e um **bus adapter** com o mesmo `emit` (traduzindo eventos em, digamos, respostas de
  status/streaming — o papel do `CLIEventBus`). **Não tocar**: `core/` (puro, já serve), os workers
  (Flet-free, já reusáveis), o contrato de eventos (vocabulário pronto). É o teste-ácido do idioma:
  borda nova = tradutores novos, zero mudança no núcleo.
- **D3** — Regra nº 5 (subprocess em modo binário). O bug mora na fronteira com um processo externo —
  provavelmente alguém usou `text=True` (ou `check_output` sem decode manual) num `subprocess` novo.
  Procuraria primeiro por `text=True` / `universal_newlines` no diff da operação nova. O "ç" fora do
  cp1252 do console Windows é a assinatura clássica.

</details>
