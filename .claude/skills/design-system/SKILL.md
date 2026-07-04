---
name: design-system
description: Referência completa do design system da GUI mill.tools (Flet 0.85) — imports, factories de botões/cards/spinners, tokens (Color/Space/Radius/Type/Motion/Layout), Cursor, tema, help system e a tabela única de quirks do Flet 0.85. Use ao criar/editar/revisar componentes da GUI, importar de `src.gui.theme.components`/`tokens`, aplicar tokens, configurar cursores ou o help/tooltip (`help_icon_for`), adicionar módulo/view ou montar o tema (`apply_theme`). O contrato de eventos (`PipelineEvent`, payloads por módulo, barra de progresso, thread-safety, abas aninhadas) fica em events.md — abra-o ao emitir/consumir eventos num worker/view.
---

# mill.tools — Design System Reference

> **Fonte única de quirks do Flet 0.85 e do contrato de eventos.** Quirks/tokens/factories ficam aqui;
> payloads de evento em [`events.md`](events.md). O CLAUDE.md e as outras skills apenas apontam para cá.

## Imports

Componentes (factories + Cursor) — via `src.gui.theme.components`:
```python
from src.gui.theme.components import (
    Cursor,
    primary_button, secondary_button, action_button, danger_button,
    segmented_selector, output_card,
    spinner, log_line, helper_text, section_title, summary_card,
    labeled_field, slider_row, switch_row,
    labeled_slider,
    hairline, module_scaffold, section, section_label,
    help_icon, help_icon_for,
)
```

Tokens de valor (sem Flet) — via `src.gui.theme.tokens`:
```python
from src.gui.theme.tokens import Color, Type, Space, Radius, IconSize, Motion, Layout
```

Tema da página — via `src.gui.theme.theme`:
```python
from src.gui.theme.theme import apply_theme, sync_page_bgcolor
```

> `tokens.py` é puro Python — sem dependência de Flet. `Cursor` fica em `components/buttons.py` porque importa `ft.MouseCursor`.

---

## Component Factories

| Símbolo | Retorno / Assinatura | Descrição |
|---|---|---|
| `primary_button(text, icon, on_click, loading)` | `ft.FilledButton` | Ação primária dourada; `loading=True` desabilita e troca ícone |
| `secondary_button(text, icon, on_click)` | `ft.OutlinedButton` | Ação secundária sem preenchimento |
| `action_button(text, icon, on_click, accent)` | `ft.TextButton` | Link/ação; `accent` padrão = `Color.log.info` (azul) |
| `danger_button(text, icon, on_click)` | `ft.TextButton` | Ação destrutiva em vermelho; nunca usa o dourado |
| `segmented_selector(options, value, page, on_change, columns, labels)` | `(grid, get_value, set_disabled)` | Grade N×columns de chips clicáveis; `get_value()→str`, `set_disabled(bool)`. `with_setter=True` → 4º elemento `set_value(opt)` (retrocompatível) |
| `output_card(path, accent, icon, extra_actions)` | `ft.Container` | Card de arquivo de saída com "Abrir pasta"; `accent` padrão = `Color.log.info` |
| `spinner()` | `(img, start, stop)` | Cata-vento animado; `start()` inicia giro contínuo, `stop()` para. **Ver "Regra de ouro do spinner" abaixo.** |
| `log_line(text)` | `ft.Text` | Linha mono com cor semântica por prefixo (`[i]` `[*]` `[~]` `[✓]` `[!]` `[»]`) |
| `helper_text(text)` | `ft.Text` | Texto de apoio caption em `ON_SURFACE_VARIANT` |
| `section_title(text)` | `ft.Text` | Título 22px W600 para seções de resultado |
| `summary_card(content)` | `ft.Container` | Card com fundo `surface_variant`, borda e raio `lg` |
| `labeled_field(label, control, helper, help_key, page)` | `ft.Column` | Rótulo + controle + helper opcional; `help_key` adiciona ⓘ automático |
| `slider_row(label, value, min_val, max_val, divisions, on_change, help_key, page)` | `ft.Column` | Rótulo + slider dourado com `on_change` externo; `help_key` adiciona ⓘ — definido em `inputs.py` |
| `labeled_slider(*, label, value, min, max, divisions, fmt, on_commit)` | `(ft.Column, ft.Slider)` | Slider com label ao vivo (atualiza a cada tick via `on_change`) e `on_commit` no `on_change_end`; retorna `(coluna, slider)`. Definido em `sliders.py`. Usado nos blocos de imagem |
| `switch_row(label, value, on_change, label_size)` | `ft.Switch` | Switch com cor `PRIMARY` e rótulo inline |
| `hairline(vertical)` | `ft.Divider` \| `ft.VerticalDivider` | Divisor 1.5px em `OUTLINE_VARIANT` |
| `module_scaffold(form, panel)` | `ft.Row` | Layout padrão: form 380px fixo \| divisor \| painel expand |
| `section(label, *controls, help_key, page)` | `ft.Column` | Grupo com rótulo W600 + ⓘ opcional no topo |
| `section_label(text)` | `ft.Text` | Rótulo 14px W600 `ON_SURFACE_VARIANT` simples (sem ⓘ) |
| `help_icon(short, long, page, size)` | `ft.Container` | ⓘ construído diretamente; clique abre modal se `long+page` |
| `help_icon_for(key, page)` | `ft.Container \| None` | ⓘ via registro `help_content.py`; retorna `None` se chave inexistente |

### Regra de ouro do spinner

Se o spinner vive num container `visible=False` que você acabou de exibir, chame **`page.update()` ANTES de
`start()`**. O giro é `_step → img.rotate.angle += 2π → img.update()` encadeado por `on_animation_end`; a
animação só dispara se esse `img.update()` chegar a um controle **já montado e visível** no cliente.
`start()` antes do `page.update()` manda a 1ª rotação para um controle oculto → nada anima,
`on_animation_end` nunca dispara, a cadeia morre (moinho parado). O `progress_view` "funciona" com
start-then-update só porque o spinner dele é permanentemente visível. Depois de iniciado, **nenhum
`page.update()` global** pode rodar durante o giro (interrompe a animação) — use `control.update()` escopado
em tickers/progresso. Ver `modules/data/view.py::_begin`/`_on_index`/`_on_assess`.

---

## Cursor — Convenções de UX

`Cursor` vive em `components/buttons.py`; **`tokens.py` permanece livre de Flet**.

| Token | Quando usar |
|---|---|
| `Cursor.interactive` | GestureDetector, IconButton, qualquer área clicável |
| `Cursor.disabled` | estado desabilitado (embutido em `Cursor.btn`) |
| `Cursor.forbidden` | NavigationRail quando pipeline está rodando |
| `Cursor.help` | ⓘ sem modal (só tooltip) |
| `Cursor.btn` | `ButtonStyle.mouse_cursor` em botões que podem ser desabilitados |

**Regra:** todo elemento clicável usa `Cursor.*` — nunca escrever `ft.MouseCursor.*` fora de `buttons.py`.
`ink=True` e `NavigationRailDestination` têm quirks próprios — ver a tabela de quirks abaixo.

---

## Tokens de Cor (`tokens.py` → classe `Color`)

### `Color.dark` e `Color.light`

| Token | dark | Uso |
|---|---|---|
| `bg` | `#1E1E20` | `page.bgcolor` (via `sync_page_bgcolor`) |
| `surface` | `#262629` | painéis, cards |
| `surface_variant` | `#2F2F34` | card interno, tooltip bg, log bg |
| `surface_hover` | `#3A3A40` | hover de container |
| `outline` | `#52525B` | bordas primárias |
| `outline_variant` | `#484850` | bordas secundárias, divisores |
| `text` | `#FFFFFF` | texto principal |
| `text_secondary` | `#A1A1AA` | texto ON_SURFACE_VARIANT |
| `text_disabled` | `#6B6B75` | texto desabilitado |
| `primary` | `#F4A63C` | dourado — acento único |
| `primary_hover` | `#F7B65C` | hover do dourado |
| `primary_pressed` | `#D88E2A` | pressed do dourado |
| `on_primary` | `#1E1E20` | texto sobre botão primário |
| `error` | `#E05A51` | erros |
| `on_error` | `#1E1E20` | texto sobre fundo de erro |

Use `Color.dark.*` / `Color.light.*` apenas quando precisar de hardcode fora do tema (ex: tooltip decoration, bg fixo). Para cores dinâmicas use `ft.Colors.PRIMARY`, `ft.Colors.ON_SURFACE`, etc.

### `Color.log` — prefixos de log

| Token | Cor | Prefixo |
|---|---|---|
| `Color.log.info` | azul `#5B9BD5` | `[i]` — informação; também acento padrão de `action_button` e `output_card` |
| `Color.log.step` | ciano `#4FD0E0` | `[*]` — etapa/carregando |
| `Color.log.work` | dourado `#F4A63C` | `[~]` — trabalhando |
| `Color.log.ok` | verde `#5FCF80` | `[✓]` — concluído |
| `Color.log.error` | vermelho `#E5736B` | `[!]` — erro |
| `Color.log.muted` | slate `#6B7C90` | `[»]` `[d]` — secundário |
| `Color.log.text` | `#C0C8D0` | sem prefixo — conteúdo transcrito |

---

## Tokens de Espaçamento (`Space`), Raio (`Radius`), Animação (`Motion`), Layout

```python
# Space — grade em px
Space.xxs = 2  Space.xs = 6   Space.sm = 12   Space.md = 16
Space.lg = 18  Space.xl = 24  Space.xxl = 32  Space.xxxl = 48

# Radius
Radius.sm = 6   Radius.md = 10   Radius.lg = 14   Radius.pill = 999

# IconSize — tamanhos de ícone (px) para ft.Icon(size=) / IconButton(icon_size=)
IconSize.sm = 14   IconSize.md = 16   IconSize.lg = 18   IconSize.xl = 24   IconSize.hero = 48

# Motion — durações em ms
Motion.fast = 200   Motion.base = 300   Motion.slow = 500   Motion.spin = 900

# Layout — constantes globais
Layout.form_width = 380          # largura do painel de formulário (px)
Layout.field_height = 38         # altura padrão de TextField em formulários
Layout.content_padding = 16
Layout.content_lateral = 24
Layout.nav_rail_width = 80
Layout.section_gap = Space.xl    # 24px
```

---

## Tipografia (`tokens.py` → classe `Type`)

`theme.py → _text_theme()` lê **todos** os tamanhos de `Type.*` — nunca hardcodar px em componentes DS.

| Token | Tamanho / Peso | Uso |
|---|---|---|
| `Type.hero` | 68 / 600 | branding da splash screen |
| `Type.wordmark` | 44 / 600 | wordmark da home screen |
| `Type.display` | 34 / 600 | títulos grandes |
| `Type.title` | 22 / 600 | títulos de seção de resultado |
| `Type.heading` | 18 / 600 | sub-títulos |
| `Type.label` | 14 / 600 | rótulos de campo |
| `Type.body` | 16 / 400 | texto corrido |
| `Type.body_strong` | 16 / 600 | texto em destaque |
| `Type.button` | 16 / 600 | texto de botão |
| `Type.caption` | 14 / 400 | texto secundário, tooltips |
| `Type.input` | 13 / 400 | rótulo de TextField, Switch, Dropdown |
| `Type.small` | 11 / 400 | labels de ícone, badges, caminhos compactos |
| `Type.tiny` | 10 / 400 | rótulos micro ("Antes"/"Depois") |
| `Type.mono` | 13 / 300 | caminhos, código — `font_family=Type.FONT_MONO` |
| `Type.FONT_UI` | `"Verdana"` | fonte padrão da UI |
| `Type.FONT_MONO` | `"JetBrains Mono"` | fonte mono |

---

## Tema da Página

```python
from src.gui.theme.theme import apply_theme, sync_page_bgcolor

apply_theme(page)          # aplica theme + dark_theme + sincroniza page.bgcolor
sync_page_bgcolor(page)    # chamar sempre que theme_mode mudar
```

`build_theme(dark=True)` retorna `ft.Theme` isolado — útil para testes.

---

## Help System

- **Registro central:** `help_content.py` — dicionários `HELP_SHORT` (tooltip) e `HELP_LONG` (modal). Adicionar nova chave lá antes de usar `help_icon_for`.
- **Uso padrão:** `help_icon_for(key, page)` → `ft.Container | None`. Retorna `None` se chave inexistente — seguro omitir sem `if`.
- **Padrão de linha com ⓘ:** `ft.Row([section_label("Label"), ft.Container(expand=True), help_icon_for("key", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER)`
- Tooltip: `BoxConstraints(max_width=280)`, decoração com borda + sombra, cursor `interactive` (com modal) ou `help` (sem modal).
- Hint de clique (`↗ Clique para mais detalhes`) é anexado automaticamente quando `HELP_LONG` existe.

---

## Quirks críticos do Flet 0.85.2

Tabela única de referência (o CLAUDE.md aponta para cá). Avisos de hardware/GPU (BSOD MX150) **não** são
design system — ficam no CLAUDE.md.

| Armadilha | Correto |
|---|---|
| `ft.Audio` | **não existe** — usar `sounddevice` + ffmpeg (`audio_player.py`) |
| `ft.ImageFit` | usar `ft.BoxFit` |
| `ft.Tabs` / `ft.Tab` | não existem — abas manuais: `TextButton` + `visible=` num `ft.Stack` |
| `ft.Colors.SURFACE_VARIANT` / `SURFACE_CONTAINER` | não existem no 0.85 — usar `ft.Colors.SURFACE` ou `Color.dark.surface_variant` |
| `surface_container_*` no `ColorScheme(...)` | kwarg inválido → `TypeError`; suportados: `surface`, `on_surface`, `on_surface_variant`, `outline`, `outline_variant` |
| trocar `Container.content` em runtime | reatribuir a árvore quebra o patcher → toggle `visible` num `ft.Stack` |
| `page.update()` em cascata | causa `IndexError` no `object_patch` — um update por evento |
| `ink=True` em Container clicável | absorve eventos de ponteiro, anula o cursor do `GestureDetector` externo — nunca usar; handler em `GestureDetector.on_tap` |
| `ft.Slider` programático | setar `.value` + `update()` **não** dispara `on_change`; usar `on_change_end` para seek |
| `ft.Dropdown` evento de seleção | **não** aceita `on_change` no construtor (0.85.2) — usar `on_select` (campos válidos: `on_select`, `on_text_change`). `ft.dropdown.Option(key=, text=)`: `key` é o valor lido em `dd.value` |
| `control.page` antes do mount | lança `RuntimeError` — proteger com `try/except RuntimeError` |
| `FilePicker` | `page.services.append(picker)` + `await picker.pick_files(...)` |
| `Container(box_shadow=...)` | usar `Container(shadow=ft.BoxShadow(...))` — sem prefixo `box_` |
| `ft.NavigationRailDestination` cursor | sem `mouse_cursor` — envolver o `NavigationRail` num `GestureDetector(mouse_cursor=Cursor.interactive)` e alternar p/ `Cursor.forbidden` via `page.pubsub` quando pipeline rodando |
| `ft.Image.src` tipo | aceita `Union[str, bytes]` no 0.85 — bytes PNG direto, sem base64 |
| `ft.Image()` **exige `src` no construtor** | `missing 1 required positional argument: 'src'` se omitido. Comece com placeholder (`_charts.BLANK_PNG`, 1×1) e troque `img.src = png` depois |
| `ft.Image` updates frequentes | `gapless_playback=True` mantém o frame anterior visível — evita flicker (cursor de waveform) |
| `Container.on_hover` coberto | **não dispara** quando o Container é totalmente coberto por outra região de mouse. Para hover **e** tap no mesmo card, usar **um único** `ft.GestureDetector` com `on_enter`/`on_exit` (+ `on_tap`) — ver `home.py` |
| `control.update()` de thread daemon | **não repinta** até o próximo `page.update()` da UI thread — cronômetro/ticker em `threading.Thread` parece travado. Para atualização periódica viva, rodar no event loop da UI via `page.run_task` (corotina async com `await asyncio.sleep`) — ver `ai/view.py`, `home.py`, `library.py` |
| Trabalho pesado numa aba/painel (DuckDB, LLM) | **Não** rodar em thread daemon (o `control.update()` não repinta) nem bloquear na UI thread. Rode via `page.run_task(coro)` + `await asyncio.to_thread(blocking_fn, ...)` — após o `await` você volta ao loop e `page.update()`/`control.update()` repinta. Ver abas Pré-visualização/Análise do `modules/data/view.py` |
| `page.open(...)` | **não existe** no 0.85.2 (`AttributeError` em runtime). Diálogos **e** SnackBars (SnackBar é `DialogControl`) vão por `page.show_dialog(...)`; fechar = `page.pop_dialog()`. Nunca `page.snack_bar=`/`page.dialog=` |
| `page.set_clipboard(...)` / `page.get_clipboard()` | **não existem** no 0.85.2 — API assíncrona: `await ft.Clipboard().set(texto)` / `await ft.Clipboard().get()`. Handler precisa ser `async def` (o Flet 0.85 dá `await` automático). `page.clipboard` (propriedade) está deprecated (remoção 0.90.0) |
| `ft.ReorderableListView` | **existe** (`on_reorder` → `e.old_index`/`e.new_index`), mas **não** aceita `shrink_wrap` e é um **scrollable** (precisa de `height` fixo). Aninhá-lo num `ft.Column(scroll=...)` é frágil — para listas curtas num formulário rolável, prefira o fallback **↑/↓** (dois `IconButton` por linha). Ver `modules/recipes/form_view.py` |

---

## Eventos do pipeline

O contrato de eventos (`PipelineEvent`, payloads por módulo, barra de progresso, thread-safety, abas
aninhadas, hook do Observatório) é a fonte única em **[`events.md`](events.md)** — abra ao emitir/consumir
eventos num `worker.py`/`view.py`/`pipeline_log.py`.
