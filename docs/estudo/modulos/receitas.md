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
