---
name: design-system
description: Referência completa do design system da GUI mill.tools (Flet 0.85). Use este skill sempre que estiver criando, editando ou revisando componentes da GUI — especialmente ao importar de `src.gui.theme.components` ou `src.gui.theme.tokens`, usar factories de botões/cards/spinners, aplicar tokens de cor (`Color`), espaçamento (`Space`), raio (`Radius`), animação (`Motion`) ou tipografia (`Type`), configurar cursores (`Cursor.*`), ou integrar o sistema de help/tooltip (`help_icon_for`). Invoque também ao adicionar um novo módulo, criar uma nova view, montar o tema (`apply_theme`) ou qualquer trabalho que envolva o design system do projeto.
---

# mill.tools — Design System Reference

## Imports

Componentes (factories + Cursor) — via `src.gui.theme.components`:
```python
from src.gui.theme.components import (
    Cursor,
    primary_button, secondary_button, action_button, danger_button,
    segmented_selector, output_card,
    spinner, log_line, helper_text, section_title, summary_card,
    labeled_field, slider_row, switch_row,
    hairline, module_scaffold, section, section_label,
    help_icon, help_icon_for,
)
```

Tokens de valor (sem Flet) — via `src.gui.theme.tokens`:
```python
from src.gui.theme.tokens import Color, Type, Space, Radius, Motion, Layout
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
| `segmented_selector(options, value, page, on_change, columns, labels)` | `(grid, get_value, set_disabled)` | Grade N×columns de chips clicáveis; `get_value()→str`, `set_disabled(bool)` |
| `output_card(path, accent, icon, extra_actions)` | `ft.Container` | Card de arquivo de saída com "Abrir pasta"; `accent` padrão = `Color.log.info` |
| `spinner()` | `(img, start, stop)` | Cata-vento animado; `start()` inicia giro contínuo, `stop()` para |
| `log_line(text)` | `ft.Text` | Linha mono com cor semântica por prefixo (`[i]` `[*]` `[~]` `[✓]` `[!]` `[»]`) |
| `helper_text(text)` | `ft.Text` | Texto de apoio caption em `ON_SURFACE_VARIANT` |
| `section_title(text)` | `ft.Text` | Título 22px W600 para seções de resultado |
| `summary_card(content)` | `ft.Container` | Card com fundo `surface_variant`, borda e raio `lg` |
| `labeled_field(label, control, helper, help_key, page)` | `ft.Column` | Rótulo + controle + helper opcional; `help_key` adiciona ⓘ automático |
| `slider_row(label, value, min_val, max_val, divisions, on_change, help_key, page)` | `ft.Column` | Rótulo + slider dourado; `help_key` adiciona ⓘ |
| `switch_row(label, value, on_change, label_size)` | `ft.Switch` | Switch com cor `PRIMARY` e rótulo inline |
| `hairline(vertical)` | `ft.Divider` \| `ft.VerticalDivider` | Divisor 1.5px em `OUTLINE_VARIANT` |
| `module_scaffold(form, panel)` | `ft.Row` | Layout padrão: form 380px fixo \| divisor \| painel expand |
| `section(label, *controls, help_key, page)` | `ft.Column` | Grupo com rótulo W600 + ⓘ opcional no topo |
| `section_label(text)` | `ft.Text` | Rótulo 14px W600 `ON_SURFACE_VARIANT` simples (sem ⓘ) |
| `help_icon(short, long, page, size)` | `ft.Container` | ⓘ construído diretamente; clique abre modal se `long+page` |
| `help_icon_for(key, page)` | `ft.Container \| None` | ⓘ via registro `help_content.py`; retorna `None` se chave inexistente |

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

**Atenção — `ink=True`:** absorve eventos de ponteiro e anula o cursor do GestureDetector externo. Nunca usar `ink=True` em containers clicáveis; usar `GestureDetector(mouse_cursor=Cursor.interactive, content=ctr)`.

**NavigationRail:** `ft.NavigationRailDestination` não tem `mouse_cursor`. Envolver o `NavigationRail` num `GestureDetector(mouse_cursor=Cursor.interactive)` e alternar para `Cursor.forbidden` via `page.pubsub` quando pipeline estiver rodando.

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
| `on_primary` | `#1E1E20` | texto sobre botão primário |
| `error` | `#E05A51` | erros |

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
# Space — grade em px (múltiplos de 4)
Space.xs = 6   Space.sm = 12   Space.md = 16
Space.lg = 18  Space.xl = 24   Space.xxl = 32  Space.xxxl = 48

# Radius
Radius.sm = 6   Radius.md = 10   Radius.lg = 14   Radius.pill = 999

# Motion — durações em ms
Motion.fast = 200   Motion.base = 300   Motion.slow = 500   Motion.spin = 900

# Layout — constantes globais
Layout.form_width = 380          # largura do painel de formulário
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
| `Type.display` | 34 / 600 | títulos grandes |
| `Type.title` | 22 / 600 | títulos de seção de resultado |
| `Type.heading` | 18 / 600 | sub-títulos |
| `Type.label` | 14 / 600 | rótulos de campo |
| `Type.body` | 16 / 400 | texto corrido |
| `Type.body_strong` | 16 / 600 | texto em destaque |
| `Type.button` | 16 / 600 | texto de botão |
| `Type.caption` | 14 / 400 | texto secundário, tooltips |
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

> Nunca atribuir `ft.Colors.SURFACE_VARIANT` ou `ft.Colors.SURFACE_CONTAINER` — não existem no Flet 0.85. Usar `ft.Colors.SURFACE` ou `Color.dark.surface_variant`.

---

## Help System

- **Registro central:** `help_content.py` — dicionários `HELP_SHORT` (tooltip) e `HELP_LONG` (modal). Adicionar nova chave lá antes de usar `help_icon_for`.
- **Uso padrão:** `help_icon_for(key, page)` → `ft.Container | None`. Retorna `None` se chave inexistente — seguro omitir sem `if`.
- **Padrão de linha com ⓘ:** `ft.Row([section_label("Label"), ft.Container(expand=True), help_icon_for("key", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER)`
- Tooltip: `BoxConstraints(max_width=280)`, decoração com borda + sombra, cursor `interactive` (com modal) ou `help` (sem modal).
- Hint de clique (`↗ Clique para mais detalhes`) é anexado automaticamente quando `HELP_LONG` existe.
