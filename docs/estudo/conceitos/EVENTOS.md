# Sessão 3 — O contrato de eventos: como o worker fala com a tela

Na Sessão 2 vimos o worker chamar `emit(...)` várias vezes e dissemos "isto avisa a UI". Esta sessão
abre essa caixa preta: **como** um trabalho rodando numa thread de fundo atualiza a tela sem tocá-la
diretamente. É o **contrato de eventos** — a cola entre o `core`/`worker` e a `view`, e a peça que
torna "um core, duas bordas" possível. Todo exemplo é código real de `src/gui/events.py`,
`_pipeline_runner.py` e do módulo Vídeo.

> **Pré-requisitos:** [`FLET_GUI.md`](FLET_GUI.md) (Parte 3 — threading e `pubsub`) e a fatia da
> Sessão 2 ([`arquivos/sessao2-vertical-video.md`](../arquivos/sessao2-vertical-video.md)), onde os
> `emit(...)` apareceram. Aqui explicamos o que cada um faz.

---

# PARTE 1 — O problema que o contrato resolve

Recapitulando o dilema (do [`FLET_GUI.md`](FLET_GUI.md) §3.2): o pipeline roda numa **thread daemon**
para não congelar a UI. Mas uma thread de fundo **não pode** tocar a tela — no Flet 0.85, um
`controle.update()` chamado de fora da thread da UI não repinta. Então como a barra de progresso se
move, se quem calcula o progresso está na thread errada?

A resposta é o padrão **publicar/assinar (pub/sub)**: a thread de fundo **publica eventos** num canal
thread-safe; a UI, na thread dela, **assina** esse canal, recebe os eventos e repinta. Ninguém
atravessa a fronteira de thread com uma chamada de UI — só **dados** (eventos) cruzam.

```
  thread de fundo (worker)              canal thread-safe            thread da UI (view)
  ──────────────────────────           ─────────────────           ────────────────────────
  emit("progress_update", {0.4})  ──►   page.pubsub    ──►  ProgressPanel move a barra e repinta
```

---

# PARTE 2 — As três peças (em `events.py`)

## 2.1 `PipelineEvent` — o envelope

```python
@dataclass
class PipelineEvent:
    type: str        # "progress_update" | "log" | "task_done" | "video_op_start" | ...
    stage: str       # "download" | "transcribe" | "audio" | ... (contexto textual)
    payload: dict = field(default_factory=dict)   # os dados do evento
    module_id: str = ""                            # de qual módulo veio (escopo)
```

🔑 É só um **dataclass** (como o `InputItem` e o `VideoArgs` que você já conhece) — um "envelope" com
quatro campos. O `type` diz **o que** aconteceu; o `payload` carrega **os dados** (ex.: `{"current":
0.4}`); o `module_id` diz **de quem** veio, para o escopo (Parte 5). Nenhuma lógica — só transporte.

## 2.2 `EventBus` — o carteiro

```python
class EventBus:
    def __init__(self, page): self._page = page
    def emit(self, type, stage, payload=None, module_id=""):
        payload = payload or {}
        self._page.pubsub.send_all(PipelineEvent(type, stage, payload, module_id))
        if type == "task_error":
            ... # (registra a falha no log do Observatório, exceto cancelamentos)
```

- **`emit(...)`** embrulha os argumentos num `PipelineEvent` e o entrega ao **`page.pubsub.send_all`**
  — o sistema pub/sub do Flet, que envia o evento a **todos** os assinantes. 🔑 É **thread-safe**: a
  thread de fundo pode chamar `emit` sem medo; é por isso que o worker faz só isso e nunca toca um
  controle.
- **O gancho de `task_error`** — quando um pipeline falha, o `EventBus` também registra a falha no log
  de erros do Observatório (`log_error`), **exceto** cancelamentos (`_is_cancellation` — apertar Esc
  não é falha do sistema). É um **hook central**: um lugar só captura todo erro de pipeline, sem tocar
  em nenhum `worker.py`.

## 2.3 `make_emitter` — o atalho ligado ao módulo

O worker não chama `bus.emit(type, stage, payload, module_id)` toda vez com os quatro argumentos. O
runner cria um **`emit` já ligado** ao bus, módulo e stage (em `_pipeline_runner.py`):

```python
def make_emitter(bus, module_id, default_stage) -> Callable:
    def emit(type, stage=None, payload=None):
        bus.emit(type, stage or default_stage, payload or {}, module_id=module_id)
    return emit
```

🔑 É uma **closure** ([`FLET_GUI.md`](FLET_GUI.md) §4.2): ela "lembra" do `bus`, `module_id="video"` e
`default_stage="video"`, então dentro do worker você escreve só `emit("progress_update",
payload={...})`. Menos repetição, e o `module_id` correto vai **automaticamente** em todo evento — o
que é essencial para o escopo (Parte 5).

---

# PARTE 3 — O ciclo de vida de um pipeline (a sequência de eventos)

Aqui está o valor prático: **quais** eventos um pipeline emite, **em que ordem**. Seguindo o
`run_queue_pipeline` (`_pipeline_runner.py`) e o `_process_item` do Vídeo da Sessão 2, converter um
`filme.mkv` dispara esta sequência:

```
1. progress_start                     ← o runner, ao começar a fila (barra aparece, zerada)
2. queue_progress   {current_item:1, total_items:1, item_name:"filme.mkv"}   ← "Item 1/1"
3. video_op_start   {operation:"convert", item_name:"filme.mkv", ...}        ← "→ convert: filme.mkv"
4. log              {message:"[i] codec h264 → mp4"}                          ← linha de detalhe
5. progress_update  {current:0.0}  ...  {current:1.0}   (repetido)            ← barra sobe (do ffmpeg!)
6. log              {message:"[d] ...", mutable:True}   (opcional)           ← linha que se sobrescreve
7. video_op_done    {output_path:"...", elapsed:"3.2s", out_size_bytes:...}  ← "✓ done in 3.2s"
8. task_done        {output_paths:["..."]}                                    ← fim, mostra os cards
```

🔑 Repare **quem** emite cada um. Os **genéricos** (`progress_start`, `queue_progress`, `task_done`,
`task_error`) vêm do **runner compartilhado** (`run_queue_pipeline`) — todo módulo os tem de graça. Os
**específicos** (`video_op_start`, `video_op_done`) vêm do **`_process_item` do módulo**. E o
`progress_update` do passo 5 é aquele que nasce lá no fundo, no `run_ffmpeg` lendo o stdout →
`_progress_cb` → `emit` (a cadeia da Sessão 2 §3.2). O evento é o mesmo objeto que atravessa as quatro
camadas.

## O runner, por dentro (a fonte dos eventos genéricos)

```python
def run_queue_pipeline(*, items, bus, module_id, ..., process_item, install_log_handler=True):
    emit = make_emitter(bus, module_id, default_stage)
    with _scope:                                   # _LogScope (Parte 6) ou nullcontext
        emit("progress_start")
        for idx, item in enumerate(items, start=1):
            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado pelo usuário."}); return False
            emit("queue_progress", payload={"current_item": idx, "total_items": total, ...})
            out = process_item(emit, item, idx, total, cancel_event)   # ← o worker do módulo
            output_paths.append(out)
        emit("task_done", payload={"output_paths": output_paths})
        return True
```

🔑 O runner **injeta o `emit`** no `process_item`. É por isso que o worker do módulo recebe `emit` como
primeiro argumento (Sessão 2 §3.2): quem cria o emitter ligado é o runner, e o passa adiante. E o
cancelamento é checado **entre itens** — apertar Esc seta o `cancel_event`, e o runner emite
`task_error("Cancelado")` na próxima volta.

---

# PARTE 4 — Os payloads por tipo de evento (a tabela de referência)

Cada `type` carrega um `payload` com chaves específicas. Esta é a "referência de contrato" — o que a
UI espera encontrar em cada um:

| `type` | Payload (chaves) | Quem emite | Efeito na UI |
|---|---|---|---|
| `progress_start` | — | runner | cria a barra, zerada |
| `progress_update` | `current` (0.0–1.0) | worker / `progress_cb` | move a barra |
| `queue_progress` | `current_item`, `total_items`, `item_name` | runner | rótulo "Item N/M" |
| `log` | `message`, `mutable?`, `level?` | worker / logging | escreve linha (mutável = sobrescreve) |
| `<mod>_op_start` | `operation`, `item_name`, `item_idx`, `total` | worker | cabeçalho da operação |
| `<mod>_op_done` | `output_path`, `elapsed`, `src_size_bytes`, `out_size_bytes` | worker | resumo "✓ done" |
| `task_done` | `output_paths` (lista) | runner | fecha a barra, renderiza os cards |
| `task_error` | `message`, `item_name?` | runner / worker | fecha a barra, mostra erro |

🔑 Este é o **contrato**: se um dia você adicionar um módulo, emitir esses eventos com essas chaves faz
a UI (o `ProgressPanel`) funcionar sem uma linha de código novo — o painel já sabe reagir. É a mesma
lógica de "fonte única" aplicada à comunicação: um vocabulário fixo que worker e view compartilham.
(A skill `design-system/events.md` é a referência canônica e completa desta tabela.)

---

# PARTE 5 — O lado que escuta: escopo por `module_id`

Todos os módulos estão montados ao mesmo tempo num `ft.Stack` ([`FLET_GUI.md`](FLET_GUI.md) §4.4), e o
`pubsub.send_all` entrega cada evento a **todos**. Então como o painel do Vídeo não reage a um evento
do Áudio? Pelo **escopo**.

Na view (Sessão 2 §4.2), o painel é criado com `owner_id="video"`:

```python
progress_panel = build_progress_view(page, ..., owner_id="video", ...)
```

E o painel, ao receber um evento, **ignora** o que não é dele:

```python
# dentro do ProgressPanel (padrão):
def _on_event(event):
    if not isinstance(event, PipelineEvent): return
    if event.module_id != owner_id: return          # ← o escopo
    ... # reage ao evento
```

🔑 É por isso que o `make_emitter` carimba o `module_id` em **todo** evento automaticamente: sem ele, o
painel não saberia filtrar, e o log do Áudio poluiria a tela do Vídeo. O `module_id` é o "endereço" no
envelope; o `owner_id` é "para quem esta caixa de correio aceita cartas". Hubs (IA/Receitas/Dados) são
auto-contidos e usam o mesmo mecanismo.

---

# PARTE 6 — Logs viram eventos: `LogEventHandler` + `_LogScope`

Há um segundo fluxo. O `core` puro não emite eventos (ele nem conhece o bus) — mas ele **loga** via o
`logging` do Python (regra nº 4). Como esses logs aparecem no painel da GUI? Uma **ponte**.

## 6.1 O handler que converte log → evento

```python
class LogEventHandler(logging.Handler):
    _SUPPRESSED_PREFIXES = ("[~] Transcribing", "[i] Detected language", ...)
    def emit(self, record):
        msg = self.format(record)
        if any(msg.startswith(p) for p in self._SUPPRESSED_PREFIXES):
            return                                    # já coberto por evento estrutural
        self._bus.emit("log", "system", {"message": msg, "level": record.levelname},
                       module_id=self._module_id)
```

🔑 É um **handler de logging** (como o `TqdmLoggingHandler` do [`utils.md`](../arquivos/utils.md), mas do
outro lado): cada mensagem que o core loga vira um evento `"log"` no bus. A lista
`_SUPPRESSED_PREFIXES` **evita duplicação** — mensagens que já têm um evento estrutural próprio
(`video_op_start` etc.) são filtradas, para não aparecerem duas vezes.

## 6.2 O escopo que instala/remove o handler

```python
class _LogScope:                                      # context manager
    def __enter__(self):
        self._root.addHandler(self._handler)          # liga a ponte
        for noisy in _NOISY_LOGGERS:
            logging.getLogger(noisy).setLevel(logging.WARNING)   # cala httpx/yt_dlp/...
    def __exit__(self, *_exc):
        self._root.removeHandler(self._handler)       # SEMPRE remove (mesmo com erro)
```

🔑 Um **context manager** (`with _scope:`) garante que o handler é **sempre removido** ao fim do
pipeline — mesmo se der exceção — evitando acúmulo de handlers a cada execução. E é aqui que entra o
`install_log_handler=False` da CLI (Sessão 2 §2): a CLI já recebe logs pelo `CLIEventBus`, então pede
para **pular** essa ponte (`contextlib.nullcontext()` no lugar do `_LogScope`), evitando log duplicado.

---

# PARTE 7 — O mesmo contrato, duas bordas (o fecho)

Volte ao [`CLI.md`](CLI.md) §5: o **`CLIEventBus`** tem um `emit` com **a mesma assinatura** do
`EventBus` da GUI. O worker chama `emit(...)` sem saber qual bus está do outro lado:

- Na **GUI**, `emit` → `pubsub` → `ProgressPanel` move a barra e escreve linhas coloridas.
- Na **CLI**, `emit` → `CLIEventBus` traduz o mesmo evento em barra `tqdm` e `tqdm.write` no terminal.

🔑 **Este é o clímax conceitual de todo o estudo até aqui.** O contrato de eventos é o que permite o
`run_video_pipeline` servir GUI e CLI sem um único `if borda == "gui"`. O worker fala uma língua
(eventos); cada borda tem seu "tradutor" (bus). Injeção de dependência de novo: o bus é passado pronto.
É o mesmo princípio do `progress_cb` da espinha, agora num nível acima — não um número, mas um
vocabulário inteiro de eventos.

## Recap: a regra de ouro do spinner

Como o `ProgressPanel` anima o cata-vento durante o pipeline, vale relembrar a regra de ouro
([`FLET_GUI.md`](FLET_GUI.md) §5): a animação só inicia se o primeiro `update()` chegar a um controle
já visível, e **nenhum `page.update()` global** pode rodar durante o giro (usa-se `controle.update()`
escopado). É por isso que o painel repinta de forma **escopada** ao receber cada evento, em vez de
chamar `page.update()` — o que mataria o spinner. O contrato de eventos e o modelo de repintura da GUI
se encaixam aqui.

---

# Glossário

**Evento (event)** — uma mensagem que descreve algo que aconteceu no pipeline (progresso, log, fim,
erro). Transportado como `PipelineEvent`.

**`PipelineEvent`** — o dataclass-envelope com `type`, `stage`, `payload`, `module_id`.

**`type`** — o que aconteceu (`progress_update`, `log`, `task_done`, `video_op_start`...).

**`payload`** — o dicionário de dados do evento (ex.: `{"current": 0.4}`).

**`module_id` / `owner_id`** — o "remetente" do evento e o "destinatário" que um painel aceita; juntos
implementam o **escopo** (cada painel ignora eventos de outros módulos).

**`EventBus`** — o objeto que publica `PipelineEvent`s via `page.pubsub` (thread-safe). Tem um gancho
que registra falhas no Observatório.

**pub/sub (publicar/assinar)** — padrão em que produtores publicam mensagens num canal e consumidores
as recebem, sem se conhecerem. `page.pubsub.send_all`/`subscribe`.

**Thread-safe** — seguro para ser chamado de várias threads ao mesmo tempo; a razão de a thread de
fundo poder emitir eventos.

**`make_emitter` / `emit`** — a closure que liga o bus a um módulo/stage, para o worker chamar `emit`
com poucos argumentos e o `module_id` ir automaticamente.

**`run_queue_pipeline`** — o runner genérico (compartilhado) que processa a fila de itens e emite os
eventos genéricos (`progress_start`, `queue_progress`, `task_done`, `task_error`).

**`process_item`** — a função que o módulo fornece: o que fazer com **um** item; recebe o `emit`
injetado.

**`<mod>_op_start` / `<mod>_op_done`** — eventos específicos do módulo (ex.: `video_op_start`) para o
cabeçalho e o resumo de uma operação.

**`ProgressPanel`** — o painel da GUI que assina os eventos, move a barra, escreve o log e mostra os
cards de resultado; filtra por `owner_id`.

**`LogEventHandler`** — o handler de logging que converte mensagens do `logging` do core em eventos
`"log"`, suprimindo as já cobertas por eventos estruturais.

**`_LogScope`** — o context manager que instala/remove o `LogEventHandler` durante o pipeline (sempre
remove, mesmo com erro).

**`install_log_handler=False`** — pedido da CLI para pular o `_LogScope` (ela já loga via
`CLIEventBus`), evitando duplicação.

**`CLIEventBus`** — o bus da CLI: mesma assinatura de `emit`, mas traduz os eventos em `tqdm`/terminal.

**Context manager (`with`)** — um objeto com `__enter__`/`__exit__` que garante setup e limpeza,
mesmo em caso de exceção.

---

## Perguntas de fixação

1. Uma thread de fundo não pode tocar a UI no Flet 0.85. Como, então, o worker consegue mover a barra
   de progresso? Descreva o caminho do dado.
2. Por que `make_emitter` é uma closure? O que ela "lembra", e por que isso importa para o escopo?
3. Liste, em ordem, os eventos que uma conversão de vídeo emite. Quais vêm do runner genérico e quais
   do `_process_item` do módulo?
4. O `pubsub.send_all` entrega o evento a **todos** os painéis. Por que o painel do Áudio não reage a
   um evento do Vídeo?
5. O `core` puro não conhece o `EventBus`. Como, então, um `logging.info(...)` dentro do core aparece
   no painel da GUI?
6. Por que a CLI passa `install_log_handler=False`? O que aconteceria sem isso?
7. Ligue este doc ao `progress_cb` da espinha: em que sentido o contrato de eventos é "o mesmo
   princípio, um nível acima"?

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. O worker chama `emit(...)` → o `EventBus` embrulha num `PipelineEvent` e o entrega ao
   `page.pubsub.send_all` (**thread-safe**) → o `ProgressPanel`, assinante na **thread da UI**,
   recebe o evento e repinta. Só dados cruzam a fronteira de thread, nunca uma chamada de UI.
2. Porque "lembra" o `bus`, o `module_id` e o `default_stage`. O worker escreve só
   `emit("progress_update", ...)` e o `module_id` correto vai carimbado **automaticamente** em todo
   evento — sem ele, o escopo por painel não funcionaria.
3. `progress_start` → `queue_progress` (runner) → `video_op_start` → `log` → `progress_update`
   (repetido) → `video_op_done` (worker/`_process_item`) → `task_done` (runner). Genéricos vêm do
   runner compartilhado; os `video_op_*` são do módulo.
4. Porque o painel filtra: `if event.module_id != owner_id: return`. O `send_all` entrega a todos,
   mas cada painel só aceita eventos do seu módulo.
5. Pela ponte `LogEventHandler` (instalado pelo `_LogScope` durante o pipeline): cada mensagem do
   `logging` vira um evento `"log"` no bus — o core continua sem conhecer o bus.
6. Porque a CLI já recebe os logs pelo `CLIEventBus`; com o handler instalado também, cada mensagem
   sairia **duas vezes** no terminal.
7. O `progress_cb` injeta uma função que empurra **um número**; o bus injeta um **vocabulário
   inteiro** de eventos. Nos dois casos, o núcleo não conhece a borda — recebe a dependência pronta e
   a chama.

</details>

## Desafios

- **D1 (e se...?)** E se o worker, em vez de `emit`, fizesse
  `progress_panel.bar.value = ratio; progress_panel.bar.update()` direto da thread daemon? Liste os
  **três** problemas que isso cria.
- **D2 (e se...?)** E se o `make_emitter` não carimbasse o `module_id`? Qual seria o **sintoma
  visível** na GUI ao rodar um pipeline de Áudio com o módulo Vídeo já usado antes?
- **D3 (ache o bug)** Um módulo novo instala o `LogEventHandler` com
  `logging.root.addHandler(handler)` solto no início do worker, sem `_LogScope`. Funciona na primeira
  execução. O que o usuário nota a partir da segunda?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — (1) Quirk da 0.85: `update()` de thread daemon **não repinta** — a barra fica congelada.
  (2) O worker acopla-se à UI: deixa de ser reusável pela CLI (que não tem `progress_panel`). (3)
  Quebra o contrato: qualquer mudança no painel exige mexer no worker. O `emit` resolve os três — só
  dados cruzam a fronteira.
- **D2** — Todo painel receberia todos os eventos sem conseguir filtrar (`module_id` vazio ≠
  `owner_id`, ou pior: se o filtro fosse permissivo, todos reagiriam). Na prática: o log e a barra do
  Áudio apareceriam **também** no painel do Vídeo — poluição cruzada entre módulos montados no mesmo
  `Stack`.
- **D3** — Handlers **acumulam**: cada execução adiciona mais um ao root logger sem nunca remover. Na
  2ª execução, cada mensagem aparece 2× no painel; na 3ª, 3×... O `_LogScope` (context manager)
  garante `removeHandler` no `__exit__`, **mesmo com exceção**.

</details>

*Próximo: Sessão 4 — os demais módulos como variações desta fatia (Áudio, Imagem, Documentos, Dados,
Transcrição, Biblioteca).*
