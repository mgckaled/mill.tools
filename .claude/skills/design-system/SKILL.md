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
| `segmented_selector(options, value, page, on_change, columns, labels)` | `(grid, get_value, set_disabled)` | Grade N×columns de chips clicáveis; `get_value()→str`, `set_disabled(bool)` |
| `output_card(path, accent, icon, extra_actions)` | `ft.Container` | Card de arquivo de saída com "Abrir pasta"; `accent` padrão = `Color.log.info` |
| `spinner()` | `(img, start, stop)` | Cata-vento animado; `start()` inicia giro contínuo, `stop()` para. **REGRA DE OURO**: se o spinner vive num container `visible=False` que você acabou de exibir, chame **`page.update()` ANTES de `start()`**. O giro é `_step → img.rotate.angle += 2π → img.update()` encadeado por `on_animation_end`; a animação só dispara se esse `img.update()` chegar a um controle **já montado e visível** no cliente. `start()` antes do `page.update()` manda a 1ª rotação para um controle oculto → nada anima, `on_animation_end` nunca dispara, a cadeia morre (moinho parado). O `progress_view` "funciona" com start-then-update só porque o spinner dele é permanentemente visível. Depois de iniciado, **nenhum `page.update()` global** pode rodar durante o giro (interrompe a animação) — use `control.update()` escopado em tickers/progresso. Ver `modules/data/view.py::_begin`/`_on_index`/`_on_assess`. |
| `log_line(text)` | `ft.Text` | Linha mono com cor semântica por prefixo (`[i]` `[*]` `[~]` `[✓]` `[!]` `[»]`) |
| `helper_text(text)` | `ft.Text` | Texto de apoio caption em `ON_SURFACE_VARIANT` |
| `section_title(text)` | `ft.Text` | Título 22px W600 para seções de resultado |
| `summary_card(content)` | `ft.Container` | Card com fundo `surface_variant`, borda e raio `lg` |
| `labeled_field(label, control, helper, help_key, page)` | `ft.Column` | Rótulo + controle + helper opcional; `help_key` adiciona ⓘ automático |
| `slider_row(label, value, min_val, max_val, divisions, on_change, help_key, page)` | `ft.Column` | Rótulo + slider dourado com `on_change` externo; `help_key` adiciona ⓘ — definido em `inputs.py` |
| `labeled_slider(*, label, value, min, max, divisions, fmt, on_commit)` | `(ft.Column, ft.Slider)` | Slider com label ao vivo (atualiza a cada tick via `on_change`) e `on_commit` no `on_change_end`; retorna `(coluna, slider)` — ler `slider.value` para o valor atual. Definido em `sliders.py`. Usado nos blocos de imagem (`resize`, `border`, `adjust`, `watermark`, `contact_sheet`, `convert_fmt`). |
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

> Nunca atribuir `ft.Colors.SURFACE_VARIANT` ou `ft.Colors.SURFACE_CONTAINER` — não existem no Flet 0.85. Usar `ft.Colors.SURFACE` ou `Color.dark.surface_variant`.

---

## Controles verificados (Flet 0.85.2)

| Controle | Situação | Nota |
|---|---|---|
| `ft.ReorderableListView` | **existe** (tem `on_reorder` → `e.old_index`/`e.new_index`) | **NÃO** aceita `shrink_wrap`; é um **scrollable** (precisa de `height` fixo). Aninhá-lo num `ft.Column(scroll=...)` é frágil. Para reordenar listas curtas dentro de um formulário rolável, prefira o fallback **↑/↓** (dois `ft.IconButton` por linha trocando posições — determinístico, sem aninhar scroll). Ver `modules/recipes/form_view.py`. |
| `ft.dropdown.Option(key=, text=)` | existe | `key` é o valor lido em `dd.value`; `text` é o rótulo exibido. Para reabilitar o evento de seleção, usar `on_select` (não `on_change`). |
| `ft.GestureDetector` hover | `on_enter`/`on_exit` (+ `on_hover`) confirmados | Para **hover e clique no mesmo controle**, use um único `GestureDetector` com `on_enter`/`on_exit` + `on_tap`. `Container.on_hover` (ou um `GestureDetector` aninhado) **não dispara** quando o controle é totalmente coberto por outra região de mouse de mesma área. Padrão crescer-no-hover dos cards da home: ver `src/gui/home.py`. |
| `ft.AlertDialog` modal | `page.show_dialog(dlg)` abre, `page.pop_dialog()` fecha | Toast: `page.open(ft.SnackBar(content=..., duration=...))`. Ver `views/file_viewer.py` (visor) e `settings_dialog.py` (Configurações). |
| Trabalho pesado numa aba/painel (DuckDB, LLM) | **Não** rodar em thread daemon (o `control.update()` não repinta) nem bloquear na UI thread | Rode no event loop da UI via `page.run_task(coro)` e dentro use `await asyncio.to_thread(blocking_fn, ...)`; após o `await` você está de volta no loop e `page.update()`/`control.update()` repinta. Padrão das abas Pré-visualização/Análise do `modules/data/view.py` (prévia DuckDB + parecer da IA). |

---

## Help System

- **Registro central:** `help_content.py` — dicionários `HELP_SHORT` (tooltip) e `HELP_LONG` (modal). Adicionar nova chave lá antes de usar `help_icon_for`.
- **Uso padrão:** `help_icon_for(key, page)` → `ft.Container | None`. Retorna `None` se chave inexistente — seguro omitir sem `if`.
- **Padrão de linha com ⓘ:** `ft.Row([section_label("Label"), ft.Container(expand=True), help_icon_for("key", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER)`
- Tooltip: `BoxConstraints(max_width=280)`, decoração com borda + sombra, cursor `interactive` (com modal) ou `help` (sem modal).
- Hint de clique (`↗ Clique para mais detalhes`) é anexado automaticamente quando `HELP_LONG` existe.

---

## Eventos do pipeline (`PipelineEvent`)

`PipelineEvent(type, stage, payload, module_id)` é publicado via `page.pubsub.send_all()` (thread-safe; worker thread → callbacks na UI thread). `module_id` ∈ {`"transcription"`, `"audio"`, `"image"`, `"video"`, `"document"`, `"data"`, `"ai"`, `"recipes"`, `""` (legado)}. O `ProgressPanel` ignora eventos cujo `module_id` ≠ `owner_id`; os hubs **IA** e **Receitas** e a ferramenta **Dados** são auto-contidos (assinam os próprios eventos, não usam `ProgressPanel`). Eventos próprios do **Dados**: `data_scanned` (chips de fonte), `data_sql_ready` (`sql`/`explanation`), `data_result` (`columns`/`rows`/`n_rows`/`elapsed`/`truncated`), `data_saved` (`output_path`); **PR9.3** acrescenta `data_index_start`/`data_index_progress` (`current`/`total`)/`data_indexed` (`added`/`total`/`chunks`) p/ a indexação RAG na aba Pré-visualização e `data_assess_start`/`data_assessed` (`name`/`text`) p/ a Análise com IA. **Plano 1 (PR9.1)** acrescenta `data_plot_start`/`data_plot_done` (`png: bytes`) p/ a aba Gráfico — o render matplotlib roda off-thread (`run_data_plot`: `run_query_arrow → frames.to_pandas → charts.render_png`) e a UI só troca o `src` de um `ft.Image`; falha via `task_error` roteado por `ctx.action[0] == "plot"`. O painel tem **4 abas manuais** (Consulta | Pré-visualização | Análise com IA | Gráfico — padrão `Conversa|Índice` do hub de IA, `visible=` num `Stack`, persistidas em `last_data_tab`), cada uma com **rodapé fixo** (ações) e **progress/log no topo**. **Quirk do spinner**: eventos de progresso emitidos *enquanto o moinho gira* (`data_index_*`, `data_assess_start`, `data_plot_start`, `log`) fazem **update escopado** (`control.update()`) + `return` — nunca o `page.update()` global do fim do handler, que interromperia a animação. A tabela paginada reutilizável é `modules/data/table_view.py` (cabeçalho mostra o tipo por coluna).

`pipeline_log.py` (por módulo) separa "o que emitir" de "como exibir": `worker.py` importa `fmt_*` p/ `emit("log", ...)`; `view.py`/`progress_view.py` importa `resolve_messages()`/`resolve_stage_label()`. Os campos exatos de cada payload são derivados do `worker.py`/`pipeline_log.py` do módulo — as tabelas abaixo são o contrato de referência.

**Genéricos (todos os módulos):**

| Evento | Payload | Efeito na UI |
|---|---|---|
| `progress_start` | — | barra indeterminada + inicia spinner |
| `progress_update` | `current`, `total` (0–1) | barra determinada |
| `queue_progress` | `current_item`, `total_items`, `item_name` | label "Item 2/5 — arquivo.mp3" |
| `task_done` | `output_path(s)` | barra 1.0, para spinner, habilita Resultados |
| `task_error` | `message` | log de erro, para spinner |
| `log` | `message`, `level`, `mutable: bool` | passthrough colorido; `mutable=True` atualiza a última linha em vez de criar nova (progresso contínuo, ex.: download yt-dlp) |

**Áudio (stage="audio"):** `audio_op_start` (`operation`, `item_name`, `item_idx`, `total`), `audio_op_done` (`output_path`, `elapsed`, `item_idx`, `total`, `src_size_bytes`, `out_size_bytes`). `operation` ∈ {`download`, `convert`, `extract`, `silence`, `denoise`, `speed`, `normalize`, `encode`}. A cadeia de pós-processamento roda em ordem fixa (silêncio → denoise → velocidade → normalize → **encode** final, que aplica `args.fmt` + mono/sample-rate). O `segmented_selector` aceita `with_setter=True` → retorna um 4º elemento `set_value(opt)` para seleção programática (presets do módulo Áudio); retrocompatível (3-tupla por padrão).

**Vídeo (stage="video"):** `video_op_start` (`operation`, `item_name`, `item_idx`, `total`), `video_op_done` (`output_path`, `elapsed`, `item_idx`, `total`, `src_size_bytes`, `out_size_bytes`), `video_op_error` (`item_name`, `message`). `operation` ∈ {`download`, `convert`, `trim`, `compress`, `resize`, `extract_audio`, `thumbnail`}.

**Imagens (stage="image"):** `image_op_start` (`operation`, `item_name`, `item_idx`, `total_items`, `thumb: bytes|None`), `image_op_done` (`output_path`, `elapsed`, `src_size_bytes`, `out_size_bytes`, `thumb`, `item_idx`, `total_items`), `image_op_error` (`item_name`, `message`).

**Documentos (stage="document"):** `document_op_start` (`operation`, `item_name`, `item_idx`, `total`, `page_count`), `document_op_done` (`output_path`, `elapsed`, `operation`, `item_idx`, `total`, `extra_stats`), `document_op_error` (`item_name`, `message`). `operation` ∈ {`merge`, `split`, `compress`, `rotate`, `watermark`, `stamp`, `encrypt`, `extract`, `ocr`, `pdf_to_images`, `images_to_pdf`, `analyze`, `qr`}.

**Transcrição (stage específico):** `metadata_start/done`, `audio_cached`, `download_start/done`, `whisper_loading/loaded`, `transcribe_started`, `language_detected` (`audio_duration`), `vad_filtered` (`duration`, `duration_after_vad`, `removed` — silêncio pulado pelo VAD; `[i] VAD removed Xs of silence (Y%)`), `transcribe_segment` (`end`, `is_low_confidence`), `transcribe_summary`, `format_*`, `analyze_*`, `translation_*`, `prompt_*`. A resposta da IA emite `answer_done` com `query`/`text`/`sources`/`model_name`/`elapsed` + **`low_confidence`/`best_score`** (Plano 4A — derivado do top-1 do retrieve sem re-embeddar; `True` mostra um banner "o acervo não cobre bem esta pergunta" acima da resposta).

**Receitas (module_id="recipes"):** `recipe_start` (`name`, `total_steps`), `step_start` (`op`, `label`, `idx`, `total`), `step_done` (`op`, `idx`, `total`, `outputs`), `step_error` (`op`, `idx`, `message`); reusa `progress_*`/`task_done`/`task_error` e, no lote, `queue_progress`. Os adaptadores de passo encaminham os eventos das funções de core (ex.: `transcribe_segment`) sob o mesmo `module_id`.

### Barra de progresso (transcrição/genérico)

- **Idle**: oculta, label "Inicie o pipeline pelo formulário →". **Indeterminada**: 1º evento de início (`value=None`).
- **Determinada**: transcrição `transcribe_segment.end / audio_duration`; áudio `progress_update(current/total)`; chunks LLM `i / total`.
- **`extra_header` no `build_progress_view`**: `ft.Control | None` opcional entre a barra e o log (Áudio injeta o `AudioPlayer`).

### Thread safety

- `bus.emit()` roda na worker thread; `page.pubsub.send_all()` é thread-safe; callbacks de `subscribe` rodam na UI thread.
- `pipeline_running[0]` resetado em `finally` (sucesso/erro/cancelamento) — senão a navegação trava.
- Não chamar `page.update()` em cascata no mesmo evento.
