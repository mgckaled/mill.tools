# Flet e a GUI — guia completo do mill.tools

Documento de referência para entender a interface gráfica do projeto: o que é o Flet, seu modelo
mental (do básico ao avançado), **todos os recursos usados no seu código** com exemplos ponto a
ponto, a arquitetura da sua `gui/`, e a longa lista de *quirks* da versão exata que você usa. Todo
exemplo é código real de `src/gui/`. Glossário no fim.

> **Versão:** o projeto fixa **Flet 0.85.2** (`flet-desktop>=0.85.2`, resolvido para 0.85.2 no
> `uv.lock`). Isso importa muito: o Flet muda rápido entre versões, e vários recursos que a
> documentação atual mostra **não existem** ou têm outro nome na 0.85.2. A seção de quirks (Parte 6)
> é a sua rede de segurança.
>
> Como ler: Partes 1–3 são conceito de Flet (valem para qualquer app Flet). Partes 4–7 são a sua
> arquitetura e os quirks. As caixas 🔑 marcam o que mais pega quem está aprendendo.

---

# PARTE 1 — O que é o Flet (conceitos gerais)

## 1.1 A ideia central

**Flet** é um framework para construir interfaces gráficas **escrevendo só Python**. Por baixo, ele
roda sobre o **Flutter** (o motor de UI do Google, usado em apps mobile/desktop). Você nunca escreve
Dart nem toca no Flutter direto: você monta a tela com objetos Python, e o Flet cuida de desenhar
tudo numa janela nativa (no seu caso, um app desktop no Windows via `flet-desktop`).

Por que Flet e não, digamos, Tkinter ou PyQt? Porque ele dá uma aparência **moderna** (Material
Design do Flutter) com **pouco código** e sem sair do Python — encaixa num projeto que já é 100%
Python e quer uma GUI bonita sem virar um projeto de front-end.

🔑 **O trade-off que você já sentiu:** o Flet é jovem e muda rápido. A 0.85.2 tem particularidades
(a Parte 6) e divide a GPU fraca com o Whisper (o aviso de BSOD no CLAUDE.md). Em troca, você
escreve uma GUI inteira em Python puro reusando o mesmo `core/`.

## 1.2 O modelo mental: Página + Árvore de Controles

Três conceitos sustentam tudo:

1. **Page (página)** — a janela. É a raiz de tudo. Você recebe um objeto `page: ft.Page` e é nele
   que você adiciona conteúdo (`page.add(...)`), configura tema, barra superior, atalhos de teclado.
2. **Controls (controles)** — os elementos de UI. Um botão, um texto, uma linha, um container. São o
   equivalente Python dos *widgets* do Flutter. Você os cria como objetos: `ft.Text("Olá")`,
   `ft.FilledButton("Executar")`.
3. **Árvore de controles** — controles contêm outros controles. Um `ft.Column` (coluna) contém
   vários controles empilhados; um `ft.Container` embrulha um; a `Page` contém a raiz. Montar uma UI
   = montar essa árvore.

Exemplo mínimo mental:

```python
page.add(
    ft.Column(controls=[            # uma coluna que empilha...
        ft.Text("Título"),         # ...um texto
        ft.FilledButton("OK"),     # ...e um botão
    ])
)
```

## 1.3 O ciclo de atualização: mutar + `update()`

Este é **o** conceito que diferencia Flet de páginas web e o ponto que mais confunde. O Flet é
**imperativo e com estado retido** (*retained mode*): você cria os controles uma vez e, depois,
**muda propriedades deles** e chama `update()` para a tela repintar. Você **não** reconstrói a tela
a cada mudança.

```python
texto = ft.Text("Antes")
page.add(texto)
# ... mais tarde, em resposta a um clique:
texto.value = "Depois"     # 1) muta a propriedade do objeto que JÁ está na tela
page.update()              # 2) manda o Flet repintar a diferença
```

🔑 **Mutar sem `update()` não faz nada visível;** a mudança fica só no objeto Python até você chamar
`update()`. E há duas granularidades: `page.update()` (repinta tudo) e `controle.update()` (repinta
só aquele controle — mais barato). Escolher entre os dois é central na Parte 3 e nos quirks.

---

# PARTE 2 — Os blocos de construção usados no seu projeto

Aqui estão os controles e recursos concretos que aparecem no seu código, com o exemplo real.

## 2.1 A `Page` e seus poderes

No `app.py`, a `page` é usada de várias formas — cada uma vale conhecer:

```python
page.theme_mode = ft.ThemeMode.DARK          # tema claro/escuro
page.appbar = ft.AppBar(...)                 # barra superior
page.pubsub.send_all(evento)                 # publica evento para toda a UI (Parte 4.5)
page.pubsub.subscribe(callback)              # assina eventos
page.on_keyboard_event = _on_keyboard        # atalhos globais de teclado
page.run_task(_fade_in)                      # roda uma corrotina async no loop da UI
page.controls.clear(); page.add(layout); page.update()   # troca o conteúdo raiz
```

- **`page.add(controle)`** insere na raiz; **`page.controls.clear()`** esvazia antes de remontar.
- **`page.on_keyboard_event`** recebe um `ft.KeyboardEvent` com `e.key`, `e.ctrl`, etc. No seu
  `app.py`, `Ctrl+Enter` dispara o botão do formulário e `Esc` cancela o pipeline:

```python
def _on_keyboard(e: ft.KeyboardEvent) -> None:
    if e.ctrl and e.key == "Enter" and not pipeline_running[0]:
        btn = get_form_start_button(active_module.control)
        if btn and not btn.disabled and btn.on_click:
            btn.on_click(e)
    if e.key == "Escape" and pipeline_running[0]:
        cancel_event.set()
```

## 2.2 Texto e tipografia

`ft.Text` mostra texto. Para texto com **partes de estilos diferentes** na mesma linha, usa-se
`spans` com `ft.TextSpan` + `ft.TextStyle`. É como seu wordmark "mill.tools" fica com "mill" branco e
".tools" dourado:

```python
wordmark = ft.Text(spans=[
    ft.TextSpan("mill",   ft.TextStyle(color=ft.Colors.ON_SURFACE, size=Type.title.size,
                                       weight=ft.FontWeight.W_600)),
    ft.TextSpan(".tools", ft.TextStyle(color=ft.Colors.PRIMARY,   size=Type.title.size,
                                       weight=ft.FontWeight.W_400)),
])
```

- **`ft.FontWeight.W_600`** é o peso da fonte (600 = semibold). Os tamanhos vêm dos seus tokens
  (`Type.title.size`) — nunca hardcode px (Parte 4.1).

## 2.3 Contêineres e layout: Container, Row, Column, Stack

Estes quatro montam quase todo layout:

- **`ft.Container`** — embrulha **um** controle e adiciona visual: cor de fundo, borda, padding,
  raio, sombra, e reage a clique/hover. Ex. (do `segmented_selector`):

```python
ft.Container(
    content=t,                                   # o controle interno (um Text)
    border=_border(active),                      # borda
    bgcolor=_bgcolor(active),                    # cor de fundo
    border_radius=Radius.sm,                     # cantos arredondados
    padding=ft.Padding(left=2, right=2, top=7, bottom=7),
    alignment=ft.Alignment.CENTER,               # centraliza o conteúdo
    shadow=ft.BoxShadow(blur_radius=4, offset=ft.Offset(0, 2),
                        color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK)),
    on_click=lambda e, _o=opt: _on_click(e, _o),
    animate=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN_OUT),
)
```

- **`ft.Row`** empilha controles na **horizontal**; **`ft.Column`** na **vertical**. Propriedades
  centrais: `controls=[...]` (a lista de filhos), `spacing` (espaço entre eles), `expand=True` (ocupa
  o espaço disponível), e o alinhamento nos dois eixos:

```python
layout = ft.Row(
    controls=[rail_gd, ft.VerticalDivider(...), ft.Container(content=module_stack, expand=True)],
    expand=True, spacing=0,
    vertical_alignment=ft.CrossAxisAlignment.STRETCH,   # estica os filhos na vertical
)
```

🔑 **`expand=True` é a cola do layout responsivo.** Um controle com `expand=True` "estica" para ocupar
o espaço livre do pai. É como o painel de conteúdo cresce enquanto a `NavigationRail` mantém largura
fixa.

- **`ft.Stack`** — **empilha controles em profundidade** (um sobre o outro, no eixo Z). É a peça-chave
  da sua navegação: todos os módulos são montados num `Stack`, mas só um fica `visible=True`:

```python
module_stack = ft.Stack(
    controls=[m.control for m in MODULES],   # todos os módulos, empilhados
    expand=True, fit=StackFit.EXPAND,
)
```

## 2.4 Botões e eventos de clique

O Flet tem vários botões; seu projeto usa quatro, embrulhados em fábricas (Parte 4.2):

- **`ft.FilledButton`** — botão preenchido (ação primária, dourado).
- **`ft.OutlinedButton`** — só contorno (ação secundária).
- **`ft.TextButton`** — texto/link (ações leves e os botões de hub do AppBar).
- **`ft.IconButton`** — só um ícone (tema, configurações).

Todos recebem **`on_click`** — a função chamada no clique. Ela recebe um *evento*:

```python
theme_btn = ft.IconButton(icon=ft.Icons.LIGHT_MODE, tooltip="Alternar tema", on_click=_toggle_theme)

def _toggle_theme(_e) -> None:      # _e é o ControlEvent; ignorado aqui
    is_dark = page.theme_mode == ft.ThemeMode.DARK
    page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
    page.update()
```

🔑 **`on_click` é um callback** — o mesmo conceito da espinha (`progress_cb`) e da CLI. Você entrega
"o que fazer no clique"; o Flet chama quando o clique acontece. Handlers geralmente recebem um
argumento de evento (`e`), que você ignora (`_e`) quando não precisa dele.

## 2.5 Estilo: `ButtonStyle`, `ControlState`, cores e formas

O visual de um botão vem de um **`ft.ButtonStyle`**. O detalhe poderoso: várias propriedades aceitam
um **dicionário por estado** (`ft.ControlState`), para o botão mudar conforme a interação:

```python
ft.ButtonStyle(
    shape=ft.RoundedRectangleBorder(radius=Radius.md),     # cantos arredondados
    animation_duration=Motion.fast,                         # transição suave
    mouse_cursor=Cursor.btn,                                # cursor por estado (dict)
    color={
        ft.ControlState.DEFAULT: c,                         # cor normal
        ft.ControlState.HOVERED: c,                         # ao passar o mouse
        ft.ControlState.PRESSED: c,                         # ao pressionar
    },
    overlay_color=ft.Colors.with_opacity(0.1, c),           # brilho do clique
)
```

- **`ft.ControlState`** enumera os estados: `DEFAULT`, `HOVERED`, `PRESSED`, `DISABLED`. Dar cores
  diferentes por estado é o que faz o hover dourado do projeto.
- **`ft.Colors.with_opacity(0.1, cor)`** cria uma versão translúcida (10%) da cor — usada em brilhos
  e fundos suaves.
- **`ft.RoundedRectangleBorder(radius=...)`**, **`ft.Border`/`ft.BorderSide`**, **`ft.BoxShadow`**,
  **`ft.Offset`** compõem o visual de caixa (cantos, bordas, sombra e seu deslocamento).

## 2.6 Cores do tema vs. cores fixas

Há **dois** jeitos de referir cor, e o projeto usa ambos com critério:

- **`ft.Colors.PRIMARY`, `ft.Colors.ON_SURFACE`, `ft.Colors.SURFACE`...** — cores **do tema**, que se
  adaptam sozinhas a claro/escuro. Prefira estas para o que deve seguir o tema.
- **`Color.dark.surface_variant` (dos seus tokens)** — um valor **fixo** (hex), usado quando você
  precisa de uma cor específica fora do tema (fundo de tooltip, decoração pontual).

## 2.7 Controles interativos: Slider, Switch, Dropdown, GestureDetector

- **`ft.NavigationRail`** — a barra lateral de navegação (as 5 ferramentas). Recebe `destinations`
  (uma lista de `ft.NavigationRailDestination` com ícone e rótulo) e **`on_change`** (chamado quando
  o usuário troca de item):

```python
rail = ft.NavigationRail(
    selected_index=_rail_index(_DEFAULT_ID),
    destinations=[ft.NavigationRailDestination(icon=m.icon, selected_icon=m.selected_icon,
                                               label=m.label) for m in _RAIL_MODULES],
    on_change=_on_rail_change,
)
```

- **`ft.GestureDetector`** — embrulha um controle para capturar **gestos** (clique, hover, entrada/
  saída do mouse) e definir o **cursor**. No `app.py`, ele embrulha a rail só para dar o cursor certo
  (a `NavigationRail` não aceita cursor direto — um quirk):

```python
rail_gd = ft.GestureDetector(content=rail, mouse_cursor=Cursor.interactive)
```

- **`ft.Slider`, `ft.Switch`, `ft.Dropdown`, `ft.Image`, `ft.SnackBar`** aparecem pelos módulos —
  cada um tem quirks próprios da 0.85 (Parte 6): o Slider programático não dispara `on_change`, o
  Dropdown usa `on_select` (não `on_change`), a Image exige `src` no construtor, o SnackBar vai por
  `page.show_dialog`.

---

# PARTE 3 — O modelo de atualização e threading (o coração)

Esta parte é o que separa "consigo montar uma tela" de "entendo por que a tela trava/pisca". Leia
com calma.

## 3.1 `page.update()` vs. `controle.update()`

Depois de mutar uma propriedade, você precisa repintar. Duas opções:

- **`page.update()`** — repinta a página inteira. Simples, mas caro; e (quirk crítico) **não pode
  rodar durante uma animação** (interrompe o giro do spinner).
- **`controle.update()`** — repinta **só** aquele controle e seus filhos. Mais barato e **escopado**
  — é o preferido em atualizações frequentes (tickers, progresso), para não perturbar o resto da
  tela.

🔑 **Regra prática do projeto:** durante trabalho contínuo (spinner girando, cronômetro), use
`controle.update()` escopado; um `page.update()` global no meio pode quebrar a animação. Fora disso,
`page.update()` está ok.

## 3.2 O problema do trabalho pesado: threads

Um pipeline (baixar, transcrever, converter) demora segundos ou minutos. Se você rodasse isso na
**thread da UI**, a interface **congelaria** — nada de clicar, nada de progresso — até terminar. A
solução é rodar o trabalho pesado numa **thread separada** (daemon), deixando a UI livre.

No `worker.py` de áudio, o pipeline roda numa thread de fundo:

```python
def start_audio_pipeline(args, bus, cancel_event, on_finish=None) -> threading.Thread:
    """Launch the audio pipeline in a daemon thread."""
    return start_pipeline(run_audio_pipeline, args, bus, cancel_event, on_finish)
```

🔑 **Mas aqui mora uma armadilha (quirk da 0.85):** um `controle.update()` chamado **de dentro de uma
thread daemon não repinta** de imediato — a UI só atualiza no próximo `page.update()` da thread da
UI. Então a thread **não** pode tocar a UI diretamente. Como ela avisa a tela, então? Pela ponte de
eventos (o `EventBus`, Parte 4.5): a thread **emite eventos**, e a UI (na thread dela, via `pubsub`)
os recebe e repinta. É por isso que o worker só chama `emit(...)`, nunca mexe num controle.

## 3.3 `page.run_task`: async no loop da UI

Para trabalho que precisa rodar **no** loop da UI mas de forma assíncrona (uma animação temporizada,
um cronômetro vivo), o Flet oferece **`page.run_task(corrotina)`**. No fim do `build_app`, é assim
que o fade-in de entrada acontece:

```python
async def _fade_in() -> None:
    await asyncio.sleep(0.05)     # espera um tiquinho
    layout.opacity = 1           # muta a opacidade
    page.update()                # repinta

page.run_task(_fade_in)
```

🔑 A regra de ouro para trabalho pesado numa aba (DuckDB, LLM): **não** rode em thread daemon (o
`update` não repinta) **nem** bloqueie a thread da UI (congela). Rode via
`page.run_task(coro)` + `await asyncio.to_thread(funcao_bloqueante, ...)` — depois do `await`, você
volta ao loop da UI e o `update()` repinta. (Padrão nas abas Pré-visualização/Análise do módulo
Dados.)

## 3.4 `control.page` antes de montar

🔑 Acessar `controle.page` (a referência à página) **antes** do controle estar montado na árvore
lança `RuntimeError`. Por isso você vê guardas como `if grid.page:` antes de chamar `grid.update()`
no `segmented_selector` — evita repintar um controle que ainda não está na tela.

---

# PARTE 4 — A arquitetura da GUI do projeto

Sobre os blocos do Flet, o projeto construiu um **design system** e um **sistema de módulos**. Entender
esses padrões faz qualquer arquivo de `gui/` ficar legível.

## 4.1 Tokens de design (`theme/tokens.py`) — sem Flet

🔑 O arquivo de tokens é **Python puro, sem importar Flet**. Ele centraliza todos os valores de design
(cores, tipografia, espaçamento, raios, durações) para que nada seja hardcoded espalhado pela UI:

```python
class Color:
    class dark:
        primary = "#F4A63C"      # o dourado, acento único
        surface = "#262629"
        ...
    class log:                   # cores semânticas do log, estáveis nos dois temas
        info = "#5B9BD5"; ok = "#5FCF80"; error = "#E5736B"; ...

class Type:                      # tipografia com escala nomeada
    title = _TypeSpec(22.0, 600)
    body  = _TypeSpec(16.0, 400)

class Space:  xs = 6; sm = 12; md = 16; ...     # grade de espaçamento (múltiplos de ~4)
class Radius: sm = 6; md = 10; lg = 14; ...      # raios de borda
class Motion: fast = 200; base = 300; spin = 900 # durações (ms)
```

Por que puro (sem Flet)? Assim os valores podem ser lidos em qualquer lugar (até em testes) sem
arrastar a dependência de UI, e o tema (`theme.py`) os injeta no Flutter. É a mesma filosofia de
**fonte única** do resto do projeto, aplicada ao visual: mudar o dourado é editar uma linha.

## 4.2 Fábricas de componentes (`theme/components/buttons.py`)

Em vez de recriar um `ft.FilledButton` estilizado em cada tela, o projeto tem **fábricas**: funções
que devolvem um controle já vestido com os tokens. `primary_button`, `secondary_button`,
`action_button`, `danger_button`:

```python
def primary_button(text, icon=None, on_click=None, loading=False) -> ft.FilledButton:
    return ft.FilledButton(
        "Executando..." if loading else text,
        icon=ft.Icons.HOURGLASS_EMPTY if loading else icon,
        disabled=loading,
        on_click=on_click,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=Radius.md),
                             animation_duration=Motion.fast, mouse_cursor=Cursor.btn),
    )
```

🔑 **Note o `loading=True`:** a mesma fábrica cobre o estado "executando" (troca texto, ícone e
desabilita). Consistência de graça — todos os botões primários do app se comportam igual.

E o **`Cursor`** é um ponto único para os cursores do mouse (o quirk é que você nunca escreve
`ft.MouseCursor.*` fora deste arquivo):

```python
class Cursor:
    interactive = ft.MouseCursor.CLICK
    forbidden   = ft.MouseCursor.FORBIDDEN     # rail quando o pipeline roda
    btn: dict = {ft.ControlState.DEFAULT: ft.MouseCursor.CLICK,
                 ft.ControlState.DISABLED: ft.MouseCursor.BASIC}
```

### O padrão de *closures* do `segmented_selector`

O `segmented_selector` (a grade de chips do tipo "Converter | Visualizar") mostra um padrão avançado e
recorrente na sua GUI: uma fábrica que devolve **o controle E funções acessórias**, guardando estado
em listas de um elemento:

```python
def segmented_selector(options, value, page, on_change=None, ...) -> tuple:
    _selected: list[str] = [value]        # estado numa lista de 1 elemento (mutável por closure)
    ...
    def _get_value() -> str: return _selected[0]
    def _set_disabled(disabled: bool) -> None: ...
    return grid, _get_value, _set_disabled     # devolve o controle + seus acessores
```

🔑 **Por que `_selected = [value]` e não `_selected = value`?** Uma *closure* (função interna) pode
**ler** variáveis do escopo externo, mas reatribuir uma variável simples criaria uma nova variável
local. Usar uma **lista de um elemento** e mutar `_selected[0]` contorna isso: a lista é a mesma, só o
conteúdo muda. É um truque de Python que você verá em todo o projeto (inclusive `pipeline_running =
[False]` e `current_idx = [...]` no `app.py`). O padrão "devolve o controle e seus acessores/handlers"
é a espinha da decomposição em `blocks/`/`tabs/` (skill `architecture`).

## 4.3 O contrato de módulo (`modules/base.py`)

Todo módulo da GUI é descrito por um **`dataclass Module`** — a interface única que o `app.py` conhece:

```python
@dataclass
class Module:
    id: str
    label: str
    icon: ft.IconData
    selected_icon: ft.IconData
    control: ft.Control                                  # a árvore de UI do módulo
    on_mount: Callable[[dict], None] = ...              # ao navegar PARA o módulo
    on_unmount: Callable[[], None] = ...                # ao SAIR do módulo
```

🔑 **O `control` é construído UMA vez e reusado.** Trocar de módulo **não** destrói a árvore — o log, a
barra e o resultado ficam preservados quando você volta. `on_mount(payload)` recebe dados injetados
pela navegação (ex.: a bridge Áudio→Transcrição passa `{"file": path}`); `on_unmount()` só solta
recursos externos (parar um preview de áudio), nunca descarta o painel.

## 4.4 A navegação por visibilidade (`navigate_to`) — o grande quirk da 0.85

Aqui está a decisão arquitetural mais importante da sua GUI, e ela nasce de um quirk. No Flet 0.85,
**trocar o `content` de um Container em runtime quebra o "patcher"** (o mecanismo que aplica
diferenças na tela) — o mesmo problema que forçou o abandono do `ft.Tabs`. A solução: montar **todos**
os módulos de uma vez num `ft.Stack` e apenas **alternar `visible=`**:

```python
def navigate_to(module_id: str, payload: dict | None = None) -> None:
    if pipeline_running[0]:
        # bloqueia troca durante um pipeline (mostra SnackBar de aviso)
        ...
        return
    idx = next(i for i, m in enumerate(MODULES) if m.id == module_id)
    MODULES[current_idx[0]].on_unmount()      # avisa o módulo que sai
    current_idx[0] = idx
    for i, m in enumerate(MODULES):
        m.control.visible = i == idx          # só o alvo fica visível
    MODULES[idx].on_mount(payload or {})      # avisa o módulo que entra
    page.update()
```

🔑 Três lições nesse trecho: (1) **visibilidade, não reatribuição** — a regra de ouro da navegação na
0.85; (2) a troca é **bloqueada enquanto um pipeline roda** (`pipeline_running[0]`), com um `SnackBar`
de aviso; (3) `on_unmount`/`on_mount` são os ganchos de ciclo de vida, e o `payload` é como um módulo
manda dados para outro (as *bridges*). `MODULES` (em `app.py`) é a **fonte única** — adicionar um
módulo é uma entrada na lista.

## 4.5 A ponte worker → UI: `EventBus`, `PipelineEvent`, `pubsub`

Como a thread de fundo (que não pode tocar a UI, Parte 3.2) atualiza a tela? Pela ponte de eventos, em
`gui/events.py`. Três peças:

```python
@dataclass
class PipelineEvent:                          # o "envelope" de um evento
    type: str                                 # "progress_update" | "log" | "task_done" | ...
    stage: str
    payload: dict = field(default_factory=dict)
    module_id: str = ""                        # de qual módulo veio (para escopo)

class EventBus:
    def __init__(self, page): self._page = page
    def emit(self, type, stage, payload=None, module_id=""):
        self._page.pubsub.send_all(PipelineEvent(type, stage, payload or {}, module_id))
        ...
```

- **`page.pubsub`** é o sistema publicar/assinar do Flet: `send_all(evento)` entrega o evento a
  **todos** os assinantes; `subscribe(callback)` registra um ouvinte. 🔑 É **thread-safe** — por isso a
  thread de fundo pode chamar `bus.emit(...)` com segurança, e a UI (assinante, na thread dela) recebe
  e repinta. Essa é a solução para a armadilha da Parte 3.2.
- **`module_id`** permite o **escopo**: cada painel de progresso ignora eventos de outro módulo
  (`if event.module_id != owner_id: return`), então o log do Áudio não polui a tela do Vídeo.
- **`LogEventHandler`** (também em `events.py`) é uma ponte extra: captura mensagens do `logging` do
  Python e as reemite como eventos `"log"` — assim os logs do core aparecem no painel da GUI. Ele
  **suprime** prefixos já cobertos por eventos estruturais (`_SUPPRESSED_PREFIXES`) para não duplicar.

### Como o worker realmente emite

No `worker.py` de áudio, veja a ponte em ação — o core recebe um `progress_cb` que **traduz** o
progresso do ffmpeg em eventos para a UI:

```python
def _progress_cb(ratio: float) -> None:          # este callback é passado ao core (ffmpeg)
    emit("progress_update", payload={"current": ratio})          # move a barra
    if ratio > 0:
        emit("log", payload={"message": pipeline_log.fmt_ffmpeg_progress(ratio),
                             "mutable": True})                    # linha de log que se sobrescreve

out_path = convert_audio(src=src, out_dir=..., progress_cb=_progress_cb)   # core puro chama de volta
```

🔑 **Feche o círculo com a espinha.** Lá no `ffmpeg.py`, `run_ffmpeg` chamava `progress_cb(ratio)` sem
saber quem era. **Aqui** você vê quem é: um callback que emite eventos no `EventBus`. O core puro
empurra números; o worker os transforma em eventos; o `pubsub` os leva à UI; a UI repinta. Injeção de
dependência ligando as quatro camadas — é o mesmo padrão que você já viu na CLI (onde o `CLIEventBus`
fazia o papel da UI). **Um core, duas bordas.**

---

# PARTE 5 — O spinner (a "regra de ouro", um quirk que merece seção própria)

O cata-vento animado (`spinner()`) tem uma sutileza que já custou depuração e vale entender a fundo,
porque ilustra o modelo de animação do Flet.

O giro funciona assim: a cada passo, o código incrementa o ângulo de rotação da imagem e chama
`img.update()`; o fim de uma animação dispara a próxima (`on_animation_end`), encadeando o giro.

🔑 **A regra de ouro:** se o spinner vive num container `visible=False` que você **acabou** de exibir,
chame **`page.update()` ANTES de `start()`**. Motivo: a animação só dispara se aquele primeiro
`img.update()` chegar a um controle **já montado e visível** no cliente. Se você chamar `start()`
antes do `page.update()`, a 1ª rotação vai para um controle ainda oculto → nada anima →
`on_animation_end` nunca dispara → a cadeia morre (moinho parado). E, depois de iniciado, **nenhum
`page.update()` global** pode rodar durante o giro (interrompe a animação) — use `controle.update()`
escopado. Isso conecta de volta à Parte 3.1: a escolha entre `page.update()` e `controle.update()`
não é estética, é o que mantém a animação viva.

---

# PARTE 6 — Quirks críticos do Flet 0.85.2 (a tabela de sobrevivência)

A skill `design-system` é a fonte única desta tabela; aqui vai a versão comentada. **Guarde esta
seção** — cada linha é uma dor que já aconteceu.

| Armadilha | O certo / por quê |
|---|---|
| **`ft.Tabs` / `ft.Tab` não existem** | Abas manuais: `TextButton` + `visible=` num `ft.Stack` (a mesma técnica do `navigate_to`). |
| **`ft.Audio` não existe** | Áudio via `sounddevice` + ffmpeg (`audio_player.py`), não pelo Flet. |
| **`ft.ImageFit` não existe** | Use `ft.BoxFit`. |
| **Trocar `Container.content` em runtime** | Quebra o *patcher* → alterne `visible` num `ft.Stack` (razão do `navigate_to`). |
| **`page.update()` em cascata** | Causa `IndexError` no `object_patch` — faça **um** update por evento. |
| **`ink=True` em Container clicável** | Absorve o evento de ponteiro e anula o cursor do `GestureDetector` externo — nunca use; trate o clique no `GestureDetector.on_tap`. |
| **`ft.Slider` programático** | Setar `.value` + `update()` **não** dispara `on_change`; para "seek", use `on_change_end`. |
| **`ft.Dropdown`** | Não aceita `on_change` no construtor (0.85.2) — use `on_select`. `ft.dropdown.Option(key=, text=)`: `key` é o valor lido em `dd.value`. |
| **`control.page` antes do mount** | Lança `RuntimeError` — proteja com `if control.page:` ou `try/except RuntimeError`. |
| **`ft.Image()` exige `src` no construtor** | Comece com um placeholder (PNG 1×1) e troque `img.src` depois. Aceita `bytes` direto (sem base64). |
| **`page.open(...)` não existe** | Diálogos **e** SnackBars vão por `page.show_dialog(...)`; fechar = `page.pop_dialog()`. Nunca `page.snack_bar=`/`page.dialog=`. |
| **Clipboard** | `await ft.Clipboard().set(txt)` / `.get()` (assíncrono); o handler precisa ser `async def`. |
| **`NavigationRailDestination` sem cursor** | Envolva a `NavigationRail` num `GestureDetector(mouse_cursor=...)` (o que o `app.py` faz com `rail_gd`). |
| **`control.update()` de thread daemon não repinta** | Rode atualização periódica no loop da UI via `page.run_task` (corrotina async). |
| **Trabalho pesado (DuckDB/LLM) numa aba** | `page.run_task(coro)` + `await asyncio.to_thread(fn, ...)` — nem thread daemon, nem bloquear a UI. |
| **`Container.on_hover` coberto** | Não dispara se o Container é totalmente coberto por outra região de mouse. Para hover **e** tap no mesmo card, use **um único** `GestureDetector` com `on_enter`/`on_exit` (+ `on_tap`) — ver `home.py`. |
| **`Container(box_shadow=...)`** | Use `Container(shadow=ft.BoxShadow(...))` — sem o prefixo `box_`. |
| **Cores `SURFACE_VARIANT`/`SURFACE_CONTAINER`** | Não existem na 0.85 — use `ft.Colors.SURFACE` ou o hex dos tokens. |

🔑 O fio comum de quase todos: o Flet 0.85 é **imperativo com um patcher sensível**. Reatribuir
árvores (content, cascatas de update) confunde o patcher; mutar propriedades + um update escopado é o
caminho seguro. Quando algo "não repinta" ou "some", a causa quase sempre está nesta tabela.

---

# PARTE 7 — Como adicionar um módulo de GUI (checklist)

1. **Pasta `gui/modules/<novo>/`** com o padrão: `form_view.py` (o formulário), `worker.py` (a thread +
   emit), `view.py` (monta o `Module` e o layout), `pipeline_log.py` (formata as mensagens). Se o
   formulário for grande, quebre em `blocks/`; se for multi-aba, em `tabs/` (skill `architecture`).
2. **Construa um `Module`** (o dataclass de `base.py`): `id/label/icon/selected_icon/control/on_mount/
   on_unmount`. O `control` é montado **uma vez**.
3. **Registre em `MODULES`** (em `app.py`) — fonte única. Ferramenta entra na `NavigationRail`; hub
   entra no `AppBar` (via `_HUB_IDS`).
4. **Worker emite eventos** com o `module_id` correto; o painel ignora eventos de outros módulos.
   Trabalho pesado → thread daemon + `bus.emit`, **nunca** toque a UI direto da thread.
5. **Use os tokens e as fábricas** — nada de px/cor hardcoded nem `ft.MouseCursor.*` fora de
   `buttons.py`. Respeite os quirks da Parte 6.
6. **Lógica pura vai para `core/`**, não para a `view` — a GUI só amarra. (Regra nº 1; a `view` não é
   testável headless, então extraia a lógica para testá-la.)

---

# Glossário

**Flet** — framework para construir GUIs escrevendo só Python, renderizadas pelo Flutter. O projeto
usa a versão **0.85.2** (desktop).

**Flutter** — o motor de UI (do Google) sobre o qual o Flet roda. Você não o toca diretamente.

**Page (`ft.Page`)** — a janela/raiz do app. Onde você adiciona conteúdo, define tema, AppBar,
atalhos, e chama `update()`.

**Control (controle)** — um elemento de UI (texto, botão, container, linha). Equivalente Python do
*widget* do Flutter.

**Árvore de controles** — a hierarquia de controles aninhados que forma a UI.

**Widget** — o termo do Flutter para o que o Flet chama de *control*.

**Retained mode (modo retido) / imperativo** — o modelo do Flet: você cria os controles uma vez e
depois **muta propriedades** + chama `update()`; não reconstrói a tela a cada mudança.

**`update()`** — repinta a UI após uma mutação. `page.update()` repinta tudo (caro); `controle.
update()` repinta só aquele controle (escopado, barato).

**`page.add()` / `page.controls`** — inserir controles na raiz / a lista de controles da raiz.

**`Container`** — controle que embrulha um filho e adiciona visual (fundo, borda, padding, raio,
sombra) e interação (clique/hover).

**`Row` / `Column`** — empilham filhos na horizontal / vertical. `controls`, `spacing`, `expand`,
`alignment` são as propriedades centrais.

**`Stack`** — empilha controles em profundidade (eixo Z). Base da navegação por `visible=`.

**`expand=True`** — faz um controle esticar para ocupar o espaço livre do pai.

**`CrossAxisAlignment` / alignment** — como os filhos se alinham no eixo transversal (ex.: `STRETCH`,
`CENTER`).

**Botões (`FilledButton`/`OutlinedButton`/`TextButton`/`IconButton`)** — variações de botão:
preenchido, contornado, texto/link, só ícone.

**`on_click` / handler / `ControlEvent`** — o callback chamado num clique e o objeto de evento que ele
recebe (frequentemente ignorado como `_e`).

**`ButtonStyle`** — o estilo de um botão (forma, cores, cursor, animação).

**`ControlState`** — os estados de interação (`DEFAULT`, `HOVERED`, `PRESSED`, `DISABLED`); várias
propriedades aceitam um dicionário por estado.

**`ft.Colors.*` (cores do tema)** — cores que se adaptam a claro/escuro (`PRIMARY`, `ON_SURFACE`...).
Preferíveis às cores fixas quando devem seguir o tema.

**`with_opacity(a, cor)`** — cria uma versão translúcida de uma cor.

**`RoundedRectangleBorder` / `Border` / `BorderSide` / `BoxShadow` / `Offset`** — peças de visual de
caixa: cantos arredondados, bordas, sombra e seu deslocamento.

**`NavigationRail` / `NavigationRailDestination`** — a barra lateral de navegação e cada item dela.

**`GestureDetector`** — embrulha um controle para capturar gestos (clique, hover, enter/exit) e definir
o cursor do mouse.

**`Animation` / `AnimationCurve` / `Motion`** — configuração de transição (duração + curva). `Motion`
são os tokens de duração do projeto.

**Thread (daemon)** — linha de execução paralela onde o trabalho pesado roda para não congelar a UI.
`daemon=True` = encerrada com o app.

**`pubsub` (`send_all` / `subscribe`)** — o sistema publicar/assinar **thread-safe** do Flet; a ponte
pela qual a thread de fundo avisa a UI.

**`EventBus` / `PipelineEvent` / `emit`** — a camada do projeto sobre o `pubsub`: o worker `emit`-e um
`PipelineEvent` (com `type`, `payload`, `module_id`); a UI o recebe e repinta.

**`module_id` (escopo de evento)** — marca de qual módulo veio um evento, para cada painel ignorar os
alheios.

**`LogEventHandler`** — ponte que captura logs do `logging` e os reemite como eventos `"log"` para o
painel da GUI, suprimindo os já cobertos por eventos estruturais.

**`page.run_task(coro)`** — roda uma corrotina assíncrona **no loop da UI** (para animações/tickers).
Combina com `asyncio.to_thread` para trabalho pesado sem congelar.

**`control.page`** — referência à página a partir de um controle; lança `RuntimeError` se acessada
antes do controle estar montado.

**Design token** — um valor de design nomeado e centralizado (cor, tamanho, espaçamento, raio,
duração). Vivem em `tokens.py`, puro (sem Flet).

**Fábrica de componente** — função que devolve um controle já estilizado com os tokens
(`primary_button`, `segmented_selector`), garantindo consistência.

**Closure + lista de 1 elemento (`[valor]`)** — truque para uma função interna **mutar** um estado do
escopo externo (muta `x[0]` em vez de reatribuir `x`). Onipresente no projeto (`pipeline_running`,
`current_idx`, `_selected`).

**`Module` (dataclass) / `MODULES`** — o contrato de um módulo de GUI e a lista única que os registra.
O `control` é montado uma vez e reusado.

**`navigate_to`** — a função de navegação: alterna `visible=` no `Stack` (nunca reatribui `content`),
bloqueia troca durante pipeline, dispara `on_unmount`/`on_mount`.

**`on_mount` / `on_unmount`** — ganchos de ciclo de vida de um módulo (ao entrar / sair); `on_mount`
recebe um `payload` (as *bridges* entre módulos).

**Patcher / `object_patch`** — o mecanismo interno do Flet que aplica só as diferenças na tela.
Sensível na 0.85: reatribuir árvores ou cascatear `update()` o confunde (fonte de vários quirks).

**Spinner (regra de ouro)** — a animação do cata-vento só inicia se o primeiro `update()` chegar a um
controle já visível; `page.update()` global durante o giro o interrompe.

**Quirk** — uma peculiaridade/armadilha específica da versão (aqui, Flet 0.85.2) que diverge do
esperado ou da documentação atual.

---

## Fontes

Refinado com a documentação e os anúncios da versão:

- [flet · PyPI](https://pypi.org/project/flet/)
- [Flet 0.85.0: Declarative apps grow up — Router, dialogs, and more (Flet blog)](https://flet.dev/blog/flet-v-0-85-release-announcement/)
- [Page — Flet docs](https://flet.dev/docs/controls/page/)
- [Build cross-platform apps in Python — Flet](https://flet.dev/)
- [Flet Python GUI Tutorial — PythonGUIs](https://www.pythonguis.com/tutorials/getting-started-flet/)
