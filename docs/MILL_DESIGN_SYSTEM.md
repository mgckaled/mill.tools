# mill.tools — Design System (proposta)

> Fonte única de verdade para a aparência do app. Objetivo: **acabar com decisões de
> estilo improvisadas** — todo token e componente é definido aqui, isolado em arquivos
> próprios, de forma que **uma mudança propague pro app inteiro**.
>
> Esta é uma **proposta detalhada** para o Claude Code derivar a implementação. Faseamento:
> **(1)** criar o pacote `src/gui/theme/`; **(2)** depois, retrofit de Transcrição e Áudio
> para consumi-lo. Vídeo/Imagens já nascem no sistema.

## Decisões travadas (não improvisar)

1. **Acento primário = dourado `#F4A63C`.** Tudo interativo (ação primária, seleção, foco,
   aba/rail ativos, slider, switch, barra de progresso) usa o dourado. O azul **sai da UI**
   e fica só como cor *info* (`[i]`) no log.
2. **"Cancelar"/destrutivo NÃO é dourado.** Dourado é reservado à ação **primária**
   (Iniciar) e à seleção. Cancelar usa tratamento *danger* (texto/ghost vermelho).
3. **Log/CLI em monoespaçada de sistema** (sem bundling): `Consolas, "Cascadia Mono",
   "DejaVu Sans Mono", Menlo, monospace`.
4. **UI em fonte de sistema** (sem bundling): `"Segoe UI", Roboto, "Helvetica Neue", Arial,
   sans-serif`. (Poppins, do wordmark, só no logo; usar Poppins na UI exigiria bundling —
   fica como upgrade opcional via `ft.app(fonts=...)`.)
5. **Cores de log são semânticas e estáveis** — separadas do acento de marca (tabela §2.3).
6. **Tema escuro é o padrão**; o claro é derivado (já existe toggle).

> ⚠️ Verificar nomes de campos do Flet 0.85 (`ft.Theme`, `ColorScheme`, `TextStyle`,
> `ScrollbarTheme`, etc.) com `inspect` antes de implementar — mesma cautela já adotada no
> projeto. Esta proposta define **intenção e valores**; o mapeamento exato de campos é do
> Claude Code.

---

## 1. Estrutura de arquivos (design system isolado)

Pacote novo `src/gui/theme/`, pequeno e por responsabilidade — nada acima de ~150 linhas:

```
src/gui/theme/
├── __init__.py        — API pública do DS (reexporta tokens + apply_theme + fábricas)
├── tokens.py          — valores crus: Color, Type, Space, Radius, Motion, Log (dataclasses/constantes)
├── theme.py           — build_theme() → ft.Theme (ColorScheme + TextTheme); apply(page, mode)
└── components/        — fábricas de componente (um arquivo por grupo)
    ├── __init__.py
    ├── buttons.py     — primary_button, secondary_button, danger_button, segmented_selector
    ├── inputs.py      — labeled_field, dropdown, switch_row, slider_row
    ├── feedback.py    — log_line, progress_header, summary_card, section_title, helper_text
    └── layout.py      — module_scaffold (form | divider | painel), section, hairline
```

**Regra de ouro:** módulos e views **não constroem controles crus nem usam hex literais** —
importam de `src.gui.theme`. Isso padroniza E enxuga os arquivos grandes (form_view,
progress_view, modules/*) movendo a montagem de UI pras fábricas.

`__init__.py` expõe a API:
```python
from src.gui.theme import tokens as T          # T.Color.PRIMARY, T.Space.MD, ...
from src.gui.theme import apply_theme
from src.gui.theme.components import primary_button, segmented_selector, log_line, ...
```

---

## 2. Tokens

### 2.1 Cores — tema escuro (padrão)

| Token | Hex | Uso |
|---|---|---|
| `bg` | `#0E1B2C` | fundo da janela |
| `surface` | `#14233A` | painéis, cartões |
| `surface_variant` | `#1B2A3A` | campos, inputs, chips não-selecionados |
| `surface_hover` | `#1F3047` | hover de itens |
| `outline` | `#2A3B52` | bordas de input/cartão, divisores |
| `outline_variant` | `#1F2E44` | divisores sutis |
| `text` | `#EAF0F6` | texto primário |
| `text_secondary` | `#9FB0C3` | rótulos, helper, texto on-surface-variant |
| `text_disabled` | `#5C6B7E` | desabilitado |
| **`primary`** | **`#F4A63C`** | **acento: ação/seleção/foco/ativo** |
| `primary_hover` | `#F7B65C` | hover da ação primária |
| `primary_pressed` | `#D88E2A` | pressed |
| `primary_tint` | `#F4A63C` @ 14% | fundo de item selecionado (segmented/chips) |
| `on_primary` | `#0E1B2C` | texto/ícone sobre dourado (escuro p/ contraste) |
| `focus_ring` | `#F4A63C` @ 50% | anel de foco |

### 2.2 Cores — tema claro (derivado)

| Token | Hex |
|---|---|
| `bg` | `#F6F8FB` · `surface` `#FFFFFF` · `surface_variant` `#EEF2F7` · `outline` `#D6DEE8` |
| `text` `#1B2A3A` · `text_secondary` `#5A6B7E` · `text_disabled` `#A6B2C0` |
| `primary` `#E0982F` (dourado levemente mais escuro p/ contraste no branco) · `on_primary` `#1B2A3A` |

### 2.3 Cores de log (semânticas, estáveis em ambos os temas)

| Prefixo | Token | Hex | Sentido |
|---|---|---|---|
| `[i]` | `log_info` | `#5B9BD5` (azul) | informação |
| `[*]` | `log_step` | `#4FD0E0` (ciano) | etapa/carregando |
| `[~]` | `log_work` | `#F4A63C` (dourado) | **trabalhando** (amarra com o moinho girando) |
| `[✓]` | `log_ok` | `#5FCF80` (verde) | concluído |
| `[!]` | `log_error` | `#E5736B` (vermelho) | erro |
| `[»]` `[d]` | `log_muted` | `#6B7C90` (slate) | secundário/debug |
| (texto) | `log_text` | `text` | conteúdo (ex.: transcrição) |

### 2.4 Tipografia

| Estilo | Família | Tamanho | Peso | Uso |
|---|---|---|---|---|
| `display` | UI | 34 | 600 | título do splash |
| `title` | UI | 22 | 600 | título de seção/resultado ("Resumo") |
| `heading` | UI | 18 | 600 | header do painel ("Pipeline concluído!") |
| `label` | UI | 13 | 600 | rótulos de grupo ("Vídeo", "Transcrição") |
| `body` | UI | 14 | 400 | texto geral |
| `body_strong` | UI | 14 | 600 | ênfase inline |
| `button` | UI | 14 | 600 | botões |
| `caption` | UI | 12 | 400 | helper/legenda (texto cinza sob controles) |
| `mono` | **monoespaçada** | 12.5 | 400 | **log/CLI** |

- UI stack: `"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- Mono stack: `Consolas, "Cascadia Mono", "DejaVu Sans Mono", Menlo, monospace`

### 2.5 Espaçamento, forma e movimento

| Grupo | Tokens |
|---|---|
| Espaço (grade 4px) | `xs`=4 · `sm`=8 · `md`=12 · `lg`=16 · `xl`=24 · `2xl`=32 · `3xl`=48 |
| Raio | `sm`=6 · `md`=10 · `lg`=14 · `pill`=999 |
| Borda | normal 1px (`outline`) · selecionado/foco 1.5px (`primary`) |
| Motion (ms) | `fast`=200 · `base`=300 · `slow`=500 · `spin`=900 |
| Curvas | padrão `EASE_OUT` · spin `LINEAR` (já usado no splash/spinner) |

### 2.6 Layout

| Token | Valor |
|---|---|
| `form_width` | 380 |
| `content_padding` | 16 (interno) / 24 (lateral do painel) |
| `nav_rail_min_width` | 80 |
| `section_gap` | `xl` (24) entre grupos do formulário |

---

## 3. Mapeamento para o Flet

- **`tokens.py`**: dataclasses/constantes puras (sem Flet) — `Color`, `Type` (com `font_family` + `size` + `weight`), `Space`, `Radius`, `Motion`, `Log`. Cores como string hex; helper p/ alpha (`with_opacity`).
- **`theme.py`**: `build_theme(mode) -> ft.Theme` montando `ColorScheme` (primary=dourado, surface, outline, etc.) + `TextTheme` (estilos nomeados a partir de `Type`). `apply_theme(page, mode)` seta `page.theme`/`page.dark_theme` e cores base. **Substitui** os hex espalhados hoje.
- **`components/`**: o que o tema **não** cobre sozinho (estado selecionado de segmented, chips, linha de log monoespaçada, cartão de resumo) vem das fábricas. É aqui que mora a padronização real entre módulos.

> Cobertura do tema vs fábricas: cor/tipografia/raio globais → tema; **estados de seleção,
> segmented buttons, chips e composições** → fábricas (no Flet esses não saem 100% do
> `ColorScheme`).

---

## 4. Componentes (anatomia + estados)

Para cada um: o que é, tokens que usa, e estados. Estados padrão: **default / hover /
selected / focus / disabled**.

### 4.1 Botões (`buttons.py`)

| Fábrica | Aparência | Estados |
|---|---|---|
| `primary_button(text, icon, on_click)` | preenchido `primary`, texto `on_primary`, raio `md` | hover `primary_hover`; pressed `primary_pressed`; disabled `surface_variant`/`text_disabled` (ex.: "Iniciar") |
| `secondary_button(...)` | outline `outline`, texto `text`, fundo transparente | hover `surface_hover`; foco anel `primary` (ex.: "Selecionar arquivos") |
| `danger_button(...)` | ghost, texto/ícone `log_error` | hover tint vermelho (ex.: **"Cancelar"** — sai do dourado) |

> Estado "executando" da ação primária: `primary_button` aceita `loading=True` →
> desabilita + ícone ampulheta/spinner (reusar o motivo do cata-vento se fizer sentido).

### 4.2 Seleção segmentada (`segmented_selector`)

Usado em **Formato de saída** e **Bitrate** (módulo Áudio).
- Item **default**: fundo `surface_variant`, borda `outline`, texto `text_secondary`, raio `md`.
- Item **selected**: borda 1.5px `primary`, fundo `primary_tint`, texto `text`/`primary`.
- Item **disabled** (ex.: bitrate quando formato=best/wav): opacidade reduzida, sem hover.
- Assinatura: `segmented_selector(options, value, on_change, columns=3)`.

### 4.3 Inputs (`inputs.py`)

| Fábrica | Notas |
|---|---|
| `labeled_field(label, control)` | rótulo `label` acima + `helper_text` opcional abaixo (`caption`/`text_secondary`) |
| `dropdown(...)` | borda `outline`; foco/aberto borda `primary`; raio `md` |
| `switch_row(label, value, on_change)` | switch **dourado quando on** (`primary`); off `outline` |
| `slider_row(label, value, ...)` | trilho ativo + thumb `primary` (Beam size) |

### 4.4 Feedback (`feedback.py`)

| Fábrica | Notas |
|---|---|
| `log_line(prefix, text)` | **monoespaçada** (`mono`); cor pelo prefixo (tabela §2.3); seleção de texto habilitada |
| `progress_header(title, spinner)` | ícone cata-vento (gira via `on_animation_end`, ver `MILL_SPLASH_SPINNER_PLAN.md`) + título `heading` |
| `summary_card(fields)` | fundo `surface`, borda `outline`, raio `lg`; cartão de resumo da transcrição |
| `section_title(text)` | `title`; usado nas seções de Resultados ("Resumo", "Pontos-chave") |
| `helper_text(text)` | `caption` em `text_secondary` (as explicações cinza sob controles) |
| barra de progresso | preenchimento `primary` (era azul); indeterminada `primary` |

### 4.5 Navegação / abas (`layout.py` + tema)

- **NavigationRail**: item ativo com indicador/ícone `primary`; inativo `text_secondary`. (Hoje azul → dourado.)
- **Abas Pipeline | Resultados** (e Transcrição/Análise/Prompt-ready): ativa = texto `primary` + sublinhado `primary`; inativa = `text_secondary`. (Hoje azul → dourado.)
- `module_scaffold(form, panel)`: `Row([Container(form, width=form_width), hairline, Container(panel, expand=True)])` — padrão único de layout dos módulos.

---

## 5. Correções específicas (do que está nos prints)

- Trocar **todo acento azul** de UI por `primary` (dourado): aba ativa, rail, slider, switch,
  borda de selecionado (formato/bitrate), foco de dropdown, barra de progresso, links.
- **"Cancelar"** deixa de ser dourado → `danger_button` (vermelho ghost). Dourado vai pra
  **"Iniciar"** (`primary_button`).
- **Log** passa a `log_line` monoespaçada com as cores semânticas da §2.3.
- Unificar **formato** e **bitrate** sob `segmented_selector` (mesmos estados/raio/borda).
- Padronizar **rótulos de grupo** ("Vídeo", "Transcrição"…) no estilo `label` e o espaçamento
  entre grupos em `section_gap`.
- Título do app/janela: confirmar "mill.tools" em todas as telas (um print antigo ainda
  mostra "yt-transcriber").

---

## 6. Faseamento

**Fase DS-1 — Sistema (agora):**
- Criar `src/gui/theme/` (tokens, theme, components) conforme §1–§4.
- `apply_theme(page, mode)` chamado no `gui.py`/`build_app`; toggle de tema passa a usar o DS.
- Sem retrofit ainda — só introduzir o pacote e aplicar o `ft.Theme` global.

**Fase DS-2 — Retrofit (depois):**
- Transcrição e Áudio passam a importar fábricas de `theme.components` e tokens; remover hex
  literais e construção crua. Isso **encolhe** `form_view.py`, `progress_view.py` e os
  `modules/*/view.py`.
- Mapa de migração (consumidores → fábricas):

| Arquivo atual | Passa a usar |
|---|---|
| `views/form_view.py` | `labeled_field`, `dropdown`, `switch_row`, `slider_row`, `section_title` |
| `views/progress_view.py` | `progress_header`, `log_line`, `summary_card`, barra `primary` |
| `views/result_view.py` | `section_title`, `summary_card`, abas com acento `primary` |
| `modules/audio/form_view.py` | `segmented_selector`, `labeled_field`, `primary/secondary_button` |
| `modules/*/view.py`, `app.py` | `module_scaffold`, rail/abas com `primary` |

## 7. Checklist DS-1
- [ ] `src/gui/theme/tokens.py` — Color (dark+light), Type, Space, Radius, Motion, Log
- [ ] `src/gui/theme/theme.py` — `build_theme(mode)` + `apply_theme(page, mode)` (verificar campos do `ColorScheme`/`TextTheme` no Flet 0.85)
- [ ] `src/gui/theme/components/{buttons,inputs,feedback,layout}.py` com as fábricas de §4
- [ ] `__init__.py` expondo a API pública
- [ ] `gui.py`/`app.py`: aplicar o tema global; toggle dark/light via DS
- [ ] Nenhum arquivo do DS acima de ~150 linhas
- [ ] Smoke test: app abre com o tema aplicado, sem regressão funcional

## 8. Em aberto
- Confirmar **acento**: dourado primário (assumido) vs split dourado+azul.
- Poppins na UI (bundled) como upgrade opcional, ou manter fonte de sistema?
