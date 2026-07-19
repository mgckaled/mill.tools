# Hub Receitas — cadeias lineares cross-módulo (Sessão 5)

Delta doc. As Receitas são cadeias **nomeadas** onde a saída de um passo alimenta o próximo,
atravessando módulos — `URL → baixar áudio → transcrever → analisar`. É a **generalização** do
`run_pipeline` que você viu na Sessão 2: em vez de uma operação, uma sequência composta.

> **Base:** [`../arquivos/sessao2-vertical-video.md`](../arquivos/sessao2-vertical-video.md) (o
> `run_pipeline` que isto generaliza), [`../conceitos/EVENTOS.md`](../conceitos/EVENTOS.md) (o `ctx.emit`),
> [`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) (`registry/`),
> [`ia.md`](ia.md)/[`observatorio.md`](observatorio.md) (os outros hubs).

## A ideia — encadear o core puro dos módulos

Uma receita é uma lista **linear** de passos, cada um sendo uma operação de algum módulo (`audio.download`,
`transcription.transcribe`, `ai.answer`...). A saída de um vira a entrada do próximo. 🔑 O truque: as
Receitas **reusam o core puro** de cada módulo (o mesmo `convert_audio`, `transcribe`, `ai.answer` que
as ferramentas usam) — nada é reimplementado. É a prova máxima de que o core é puro e reutilizável: dá
para recombiná-lo em qualquer ordem.

## `registry/<módulo>.py` — os adaptadores

O coração é o `core/recipes/registry/`, decomposto por módulo
([`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) §6): cada arquivo (`registry/audio.py`,
`registry/video.py`...) define `STEP_REGISTRY: "module.op" → StepSpec`, e um `__init__` monta o registro
completo. Cada passo é um **adaptador fino**:

```
adapter(inputs, params, ctx) → list[Path]
```

🔑 O adaptador é a "cola" entre a receita e o core: ele (1) chama a função pura do módulo, (2) grava no
dir canônico daquele módulo, e (3) **normaliza os callbacks** para `ctx.emit` — ou seja, traduz o
`progress_cb`/eventos do core para o contrato de eventos da receita. É o mesmo padrão de tradução que a
CLI e a GUI fazem, agora numa terceira borda: a receita. `runner.execute_recipe(_batch)` roda a cadeia.

## Casos sutis (onde a generalização "range")

Três exceções que o CLAUDE.md registra, e que ensinam os limites do padrão:

- **`transcription.format` reescreve in-place** → seu output é `[input_path]` (não gera arquivo novo; edita
  o texto no lugar). O runner precisa saber disso para encadear certo.
- **`video.subtitle` é o único multi-input** — precisa de dois arquivos (vídeo + legenda), quebrando a
  suposição "um passo, uma entrada".
- **`ai.answer` exige `is_available()`** — o passo de RAG só roda se o embedder estiver de pé (gate,
  como no hub IA).

🔑 Estes casos mostram que uma abstração linear ("saída→entrada") tem bordas: reescrita in-place,
multi-input, gates. O projeto os trata explicitamente em vez de forçar todos no mesmo molde.

## GUI — Rodar | Construir + Histórico

O hub tem um toggle **Rodar | Construir** (executar uma receita salva vs. montar uma nova encadeando
passos) e uma aba **Histórico** (`recipe_runs.json`). A persistência das receitas é `recipes.json`. Como
os passos podem ter progresso (uma transcrição demora), a execução usa o mesmo contrato de eventos com
`module_id` da receita, e o runner checa cancelamento entre passos (o mesmo *seam* do
`run_queue_pipeline` da Sessão 2/3).

## CLI

`recipe list` / `recipe run "<nome>" <URL_OR_FILE>` — e, diferente dos outros hubs read-only, Receitas
tem **runner real** com `CLIEventBus` ([`../conceitos/CLI.md`](../conceitos/CLI.md) §taxonomia): é
pipeline, não read-only. `--model` sobrescreve só o Whisper dos passos `transcription.transcribe`.

---

# Perguntas de fixação

1. Uma receita reusa o core puro de vários módulos. Por que isso só é possível graças à regra "core é
   puro"? (ligue à regra nº 1)
2. O que um adaptador (`adapter(inputs, params, ctx) → list[Path]`) faz nos seus três passos? Como ele
   se liga ao contrato de eventos?
3. `transcription.format`, `video.subtitle` e `ai.answer` são casos sutis. Qual é a exceção de cada um,
   e o que ela ensina sobre os limites de uma abstração linear?
4. Na taxonomia da CLI, por que `recipe` usa `CLIEventBus` enquanto `library`/`ai` não? (ligue ao
   [`../conceitos/CLI.md`](../conceitos/CLI.md))
5. Em que sentido as Receitas são a "generalização do `run_pipeline`" da Sessão 2? O que mudou de "uma
   operação" para "uma cadeia"?

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. Se o core dependesse de Flet, de estado de UI ou de um bus específico, não poderia ser chamado de
   um contexto novo. Puro + injeção = chamável de qualquer borda, em qualquer ordem — a receita é a
   prova.
2. (1) Chama a função **pura** do módulo; (2) grava no **dir canônico** daquele módulo; (3)
   **normaliza os callbacks** para `ctx.emit` — traduzindo o `progress_cb`/eventos do core para o
   contrato de eventos da receita.
3. `transcription.format` **reescreve in-place** (output = `[input_path]`, não gera arquivo novo);
   `video.subtitle` é **multi-input** (vídeo + legenda); `ai.answer` exige **`is_available()`**
   (gate). Lição: abstrações lineares têm bordas — melhor tratá-las explicitamente que forçar tudo
   no molde.
4. Porque `recipe` **roda pipeline** (passos longos, progresso, cancelamento) → `CLIEventBus`;
   `library`/`ai` são read-only core-direto → chamam o core e imprimem.
5. De "uma operação por item" para "uma **cadeia nomeada** de passos cross-módulo, onde a saída de um
   alimenta o próximo" — o mesmo contrato de eventos e o mesmo core puro, recombinados.

</details>

## Desafios

- **D1 (projete)** Novo passo de receita: `image.describe` (descrição de imagem por IA). Escreva o
  "contrato" do adaptador: o que ele checa antes, o que chama, onde grava, e o que devolve.
- **D2 (ache o bug)** Um adaptador novo de áudio importa e chama
  `gui.modules.audio.worker.run_audio_pipeline` "para reaproveitar a cadeia inteira de estágios".
  Funciona — por que está errado mesmo assim?
- **D3 (e se...?)** Monte mentalmente a receita `URL → audio.download → transcription.transcribe →
  transcription.format → ai.answer`. Aponte os **dois** casos sutis desta cadeia e o que o runner
  precisa saber sobre cada um.

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — Checa o **gate** antes (`describe.is_available()` — modelo de visão local/nuvem
  configurado), como `ai.answer` faz. Chama a função **pura** `core/image/describe.py` (nunca o
  worker da GUI). Grava a descrição no dir canônico do módulo Imagem. Devolve `list[Path]` com o
  arquivo de texto gerado — que o passo seguinte pode consumir. Callbacks → normalizados para
  `ctx.emit`.
- **D2** — O adaptador deve chamar o **core puro**, não o worker de um módulo: o worker embute a
  semântica de fila/eventos do módulo (module_id "audio", `run_queue_pipeline`, log scope) — dentro
  de uma receita isso duplicaria maquinaria de pipeline dentro de pipeline, emitiria eventos com
  escopo errado e acoplaria as Receitas à camada `gui/`. Adaptador fino = core + dir canônico +
  `ctx.emit`.
- **D3** — (1) `transcription.format` **reescreve in-place**: o output do passo é `[input_path]` — o
  runner precisa saber que o "arquivo novo" é o mesmo caminho, senão a cadeia perderia o fio. (2)
  `ai.answer` exige **`is_available()`**: sem o embedder de pé, a receita deve falhar cedo no gate
  (mensagem clara), não estourar no meio. (`video.subtitle` seria o terceiro caso, mas não aparece
  nesta cadeia.)

</details>
