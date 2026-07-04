# Plano de Implementação — Home Screen (mill.tools)

> **Scope:** tela intermediária entre splash e NavigationRail; logo girando ao fundo + 4 cards de módulo clicáveis.
> **Arquivos afetados:** 1 novo (`home.py`) · 2 modificados (`gui.py`, `app.py`)

---

## 1. Contexto

Fluxo atual:
```
gui.py → show_splash(on_complete=λ: build_app)
```

Fluxo desejado:
```
gui.py → show_splash(on_complete=λ: show_home(on_complete=λ(mid): build_app(initial_module=mid)))
```

`show_home` segue o mesmo contrato do `show_splash`: recebe `page` e um callback `on_complete`, controla o ciclo de vida via `page.run_task`, limpa os controles com `page.controls.clear()` e chama o callback ao sair.

---

## 2. Resumo das Alterações

| Arquivo | Tipo | O que muda |
|---|---|---|
| `src/gui/home.py` | **NOVO** | Tela completa: fundo animado + 4 cards |
| `gui.py` | modificado | Inserir `show_home` no meio da cadeia de callbacks |
| `src/gui/app.py` | modificado | Adicionar parâmetro `initial_module: str = "transcription"` |

---

## 3. Assinaturas Públicas

```python
# src/gui/home.py
def show_home(page: ft.Page, on_complete: Callable[[str], None]) -> None:
    """Exibe a home screen; ao clicar em um card chama on_complete(module_id)."""

# src/gui/app.py  (linha 21 — só adiciona o parâmetro)
def build_app(page: ft.Page, initial_module: str = "transcription") -> None:
    ...
    _DEFAULT_ID = initial_module   # era hardcoded "transcription"

# gui.py  (linha 25 — substitui lambda por cadeia)
show_splash(page, on_complete=lambda: show_home(
    page,
    on_complete=lambda mid: build_app(page, initial_module=mid),
))
```

---

## 4. Design Spec

### 4.1 Estrutura de camadas (ft.Stack)

```
page (bgcolor = Color.dark.bg)
└── home_root  (ft.Container expand, opacity animado)
    └── ft.Stack(expand, clip_behavior=ANTI_ALIAS)
        ├── [0] bg_layer   — ft.Container(expand, alignment=CENTER)
        │       └── mill-symbol.png  500×500px  opacity=0.06  rotate lento
        └── [1] fg_layer   — ft.Column(alignment=CENTER, h_align=CENTER)
                ├── header_row  (logo wordmark + versão)
                ├── ft.Container(height=48)   ← espaçamento
                └── cards_grid  (ft.Column de 2 ft.Row)
```

**Por que Stack?** Permite sobrepor o bg rotativo sem interferir no layout do fg. `clip_behavior=ft.ClipBehavior.ANTI_ALIAS` evita overflow do símbolo 500px nas bordas.

### 4.2 Background — mill-symbol animado

| Parâmetro | Valor | Razão |
|---|---|---|
| `src` | `b64("mill-symbol.png")` | mesmo asset do splash |
| `width / height` | `500` | grande o suficiente para preencher visualmente |
| `opacity` | `0.06` | "quase imperceptível, porém visível" |
| `rotate` | `ft.Rotate(angle=0, alignment=ft.Alignment.CENTER)` | centro de rotação |
| `animate_rotation` | `ft.Animation(20000, ft.AnimationCurve.LINEAR)` | 1 volta a cada 20 s |
| `on_animation_end` | `_next_turn` | encadeia indefinidamente |

**Lógica de encadeamento (igual ao spinner do DS):**

```python
_bg_turns: list[int] = [0]

def _next_turn(_e=None) -> None:
    _bg_turns[0] += 1
    bg_symbol.rotate.angle = _bg_turns[0] * 2 * math.pi
    try:
        bg_symbol.update()
    except RuntimeError:
        pass   # controle desmontado, silenciar

bg_symbol.on_animation_end = _next_turn
```

A primeira chamada é disparada no `_run()` assíncrono após `await asyncio.sleep(0.05)` (dá tempo de montar o widget).

### 4.3 Header

```python
ft.Row(
    controls=[
        ft.Image(src=b64("mill-symbol.png"), width=32, height=32),
        ft.Text(
            spans=[
                ft.TextSpan("mill", ft.TextStyle(color=ft.Colors.ON_SURFACE,
                                                  size=Type.heading.size,
                                                  weight=ft.FontWeight.W_600)),
                ft.TextSpan(".tools", ft.TextStyle(color=Color.dark.primary,
                                                    size=Type.heading.size,
                                                    weight=ft.FontWeight.W_400)),
            ]
        ),
    ],
    alignment=ft.MainAxisAlignment.CENTER,
    vertical_alignment=ft.CrossAxisAlignment.CENTER,
    spacing=Space.sm,
)
```

Não usa AppBar (ela é configurada apenas em `build_app`). Header inline, centralizado.

### 4.4 Cards Grid

**Grid:** `ft.Column` de duas `ft.Row`; cada `ft.Row` tem 2 cards com `expand=True`. Total: 4 cards idênticos em dimensão.

**Container externo do grid:**
```python
ft.Container(
    content=cards_column,
    width=960,           # limita em janelas muito largas
    padding=ft.Padding(left=Space.xl, right=Space.xl, top=0, bottom=0),
)
```

**Espaçamento entre rows:** `Space.xl` (24px).  
**Espaçamento entre cards na row:** `Space.xl` (24px).  
**Altura dos cards:** `220` px (fixo, igual para todos).

### 4.5 Anatomia de cada card

```
┌──────────────────────────────────────────────┐  h=220
│  padding: Space.xl (24px)                    │
│                                              │
│  ft.Row [                                    │
│    ft.Icon(icon, size=40, color=accent)      │
│    ft.Column [                               │
│      ft.Text(title)   — Type.heading (18/600)│
│      ft.Text(desc)    — Type.caption (14/400)│  text_secondary
│    ]                                         │
│  ]                                           │
│                                              │
│  ft.Container(height=12)                     │
│                                              │
│  ft.Column [                           ← features
│    ft.Row [ft.Icon(CIRCLE, 6px), ft.Text]  × 3
│  ]                                           │
│                                              │
│  ft.Container(expand=True)  ← push footer   │
│                                              │
│  ft.Row [                              ← footer
│    ft.Text("Abrir módulo", color=accent, caption)
│    ft.Icon(ARROW_FORWARD, size=14, color=accent)
│  ]                                           │
└──────────────────────────────────────────────┘
```

**Cores base do card (dark/light via `ft.Colors.SURFACE` / `ft.Colors.ON_SURFACE`):**

| Estado | `bgcolor` | `border` |
|---|---|---|
| default | `ft.Colors.SURFACE` | `ft.BorderSide(1.5, outline_variant)` |
| hover | `Color.dark.surface_hover` | `ft.BorderSide(1.5, accent_with_opacity_0.6)` |

> **Nota:** cores dinâmicas por tema (dark/light) — usar função helper `_palette(page)` idêntica à do `segmented_selector`.

**Shadow:**
```python
shadow=ft.BoxShadow(
    blur_radius=12, spread_radius=0,
    offset=ft.Offset(0, 4),
    color=ft.Colors.with_opacity(0.20, ft.Colors.BLACK),
)
```

### 4.6 Hover state

Padrão **sem `ink=True`**, sem `Container.on_click` (ver CLAUDE.md quirk):

```python
card_ctr = ft.Container(
    ...
    animate=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN_OUT),
    on_hover=lambda e, c=card_ctr: _on_card_hover(e, c, accent),
    # SEM on_click aqui
)
gd = ft.GestureDetector(
    mouse_cursor=Cursor.interactive,
    content=card_ctr,
    on_tap=lambda _, mid=module_id: _navigate(mid),
    expand=True,
)
```

`_on_card_hover`:
```python
def _on_card_hover(e: ft.HoverEvent, ctr: ft.Container, accent: str) -> None:
    is_hover = e.data == "true"
    pal = Color.dark if page.theme_mode != ft.ThemeMode.LIGHT else Color.light
    ctr.bgcolor = pal.surface_hover if is_hover else ft.Colors.SURFACE
    side = ft.BorderSide(1.5, ft.Colors.with_opacity(0.6 if is_hover else 0.0, accent))
    outline = ft.BorderSide(1.5, pal.outline_variant)
    ctr.border = ft.Border(
        left=side if is_hover else outline,
        right=side if is_hover else outline,
        top=side if is_hover else outline,
        bottom=side if is_hover else outline,
    )
    ctr.update()
```

> `ft.Border(all=...)` não existe no 0.85 — usar os 4 lados explicitamente.

### 4.7 Dados dos módulos

```python
_MODULE_CARDS = [
    {
        "id": "audio",
        "title": "Áudio",
        "icon": ft.Icons.MUSIC_NOTE_OUTLINED,
        "accent": Color.log.ok,        # verde #5FCF80
        "desc": "Download, conversão e pós-processamento",
        "features": [
            "Download de URL (yt-dlp) · MP3, M4A, WAV, OGG",
            "Redução de ruído — spectral gating (CPU)",
            "Normalização de volume EBU R128",
        ],
    },
    {
        "id": "video",
        "title": "Vídeo",
        "icon": ft.Icons.VIDEO_FILE_OUTLINED,
        "accent": Color.log.info,      # azul #5B9BD5
        "desc": "7 operações — download, corte, compressão e mais",
        "features": [
            "Download · Converter · Cortar (trim)",
            "Compressão H.264 CRF · Redimensionar",
            "Extrair áudio · Gerar thumbnail",
        ],
    },
    {
        "id": "image",
        "title": "Imagens",
        "icon": ft.Icons.IMAGE_OUTLINED,
        "accent": Color.log.step,      # ciano #4FD0E0
        "desc": "12 operações de conversão, manipulação e IA",
        "features": [
            "Converter · Redimensionar · Recortar · Girar",
            "Remover fundo (rembg · ONNX · CPU)",
            "Descrever imagem com IA (Ollama vision)",
        ],
    },
    {
        "id": "transcription",
        "title": "Transcrição",
        "icon": ft.Icons.SUBTITLES_OUTLINED,
        "accent": Color.dark.primary,  # dourado #F4A63C
        "desc": "YouTube → texto com Whisper, 100 % local",
        "features": [
            "faster-whisper + GPU (CUDA / int8_float32)",
            "Formatação e análise com LLM (Ollama / Gemini)",
            "Exporta TXT · Markdown · Prompt-ready",
        ],
    },
]
```

### 4.8 Animações de entrada e saída

| Evento | Animação | Duração |
|---|---|---|
| Home monta | `home_root.opacity` 0 → 1 | `Motion.slow` (500 ms) EASE_OUT |
| Card clicado | `home_root.opacity` 1 → 0 | `350 ms` EASE_IN |
| Após fade-out | `on_complete(module_id)` | `asyncio.sleep(0.35)` |
| Bg rotation start | `_next_turn()` dispara | após `asyncio.sleep(0.05)` |

---

## 5. Implementação Detalhada — `src/gui/home.py`

### Estrutura do arquivo

```python
"""Home screen do mill.tools — fundo animado + 4 cards de módulo."""
from __future__ import annotations

import asyncio
import math
from typing import Callable

import flet as ft

from src.gui.assets import b64
from src.gui.theme.components.buttons import Cursor
from src.gui.theme.tokens import Color, Motion, Radius, Space, Type

# ── Dados dos módulos ────────────────────────────────────────────────────────
_MODULE_CARDS: list[dict] = [...]   # ver seção 4.7

# ── Helpers ──────────────────────────────────────────────────────────────────
def _palette(page: ft.Page):
    """Retorna Color.dark ou Color.light conforme o tema ativo."""
    return Color.dark if page.theme_mode != ft.ThemeMode.LIGHT else Color.light

def _on_card_hover(e, ctr, accent, page): ...  # ver seção 4.6

def _make_card(data: dict, on_tap: Callable, page: ft.Page) -> ft.GestureDetector:
    """Constrói o GestureDetector wrapping o card Container."""
    ...

# ── Ponto de entrada ─────────────────────────────────────────────────────────
def show_home(page: ft.Page, on_complete: Callable[[str], None]) -> None:
    """Exibe a home screen; chama on_complete(module_id) ao navegar."""
    ...
```

### `_make_card` — detalhes

```python
def _make_card(data: dict, on_tap: Callable[[str], None], page: ft.Page) -> ft.GestureDetector:
    accent = data["accent"]
    pal    = _palette(page)

    # ── feature list ──────────────────────────────────────────
    feature_rows = [
        ft.Row(
            controls=[
                ft.Icon(ft.Icons.CIRCLE, size=5, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(f, size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT,
                        expand=True, no_wrap=False),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        for f in data["features"]
    ]

    # ── card container ────────────────────────────────────────
    ctr = ft.Container(
        height=220,
        expand=True,
        border_radius=Radius.lg,
        border=ft.Border(
            left=ft.BorderSide(1.5, pal.outline_variant),
            right=ft.BorderSide(1.5, pal.outline_variant),
            top=ft.BorderSide(1.5, pal.outline_variant),
            bottom=ft.BorderSide(1.5, pal.outline_variant),
        ),
        bgcolor=ft.Colors.SURFACE,
        padding=ft.Padding(left=Space.xl, right=Space.xl, top=Space.xl, bottom=Space.xl),
        shadow=ft.BoxShadow(
            blur_radius=12, spread_radius=0,
            offset=ft.Offset(0, 4),
            color=ft.Colors.with_opacity(0.20, ft.Colors.BLACK),
        ),
        animate=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN_OUT),
        # SEM on_click — handler fica no GestureDetector
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(data["icon"], size=40, color=accent),
                        ft.Column(
                            controls=[
                                ft.Text(data["title"],
                                        size=Type.heading.size,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.ON_SURFACE),
                                ft.Text(data["desc"],
                                        size=Type.caption.size,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                        no_wrap=False),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=Space.md,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=Space.sm),
                ft.Column(controls=feature_rows, spacing=4),
                ft.Container(expand=True),   # empurra footer para baixo
                ft.Row(
                    controls=[
                        ft.Text("Abrir módulo",
                                size=Type.caption.size,
                                color=accent,
                                weight=ft.FontWeight.W_600),
                        ft.Icon(ft.Icons.ARROW_FORWARD, size=14, color=accent),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=0,
            expand=True,
        ),
    )
    ctr.on_hover = lambda e: _on_card_hover(e, ctr, accent, page)

    return ft.GestureDetector(
        mouse_cursor=Cursor.interactive,
        content=ctr,
        on_tap=lambda _: on_tap(data["id"]),
        expand=True,
    )
```

### `show_home` — corpo principal

```python
def show_home(page: ft.Page, on_complete: Callable[[str], None]) -> None:
    page.padding = 0

    # ── background: mill-symbol girando ────────────────────────
    _bg_turns: list[int] = [0]

    bg_symbol = ft.Image(
        src=b64("mill-symbol.png"),
        width=500,
        height=500,
        opacity=0.06,
        rotate=ft.Rotate(angle=0, alignment=ft.Alignment.CENTER),
        animate_rotation=ft.Animation(20_000, ft.AnimationCurve.LINEAR),
    )

    def _next_turn(_e=None) -> None:
        _bg_turns[0] += 1
        bg_symbol.rotate.angle = _bg_turns[0] * 2 * math.pi
        try:
            bg_symbol.update()
        except RuntimeError:
            pass

    bg_symbol.on_animation_end = _next_turn

    bg_layer = ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=bg_symbol,
    )

    # ── navegação com fade-out ──────────────────────────────────
    home_root: list[ft.Container] = [None]   # forward ref

    async def _navigate(module_id: str) -> None:
        home_root[0].opacity = 0
        page.update()
        await asyncio.sleep(0.35)
        on_complete(module_id)

    def _on_tap(module_id: str) -> None:
        page.run_task(_navigate, module_id)

    # ── header ──────────────────────────────────────────────────
    header = ft.Row(
        controls=[
            ft.Image(src=b64("mill-symbol.png"), width=30, height=30),
            ft.Text(
                spans=[
                    ft.TextSpan("mill", ft.TextStyle(
                        color=ft.Colors.ON_SURFACE,
                        size=Type.heading.size,
                        weight=ft.FontWeight.W_600,
                    )),
                    ft.TextSpan(".tools", ft.TextStyle(
                        color=Color.dark.primary,
                        size=Type.heading.size,
                        weight=ft.FontWeight.W_400,
                    )),
                ]
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=Space.sm,
    )

    # ── cards ───────────────────────────────────────────────────
    cards = [_make_card(data, _on_tap, page) for data in _MODULE_CARDS]

    cards_grid = ft.Column(
        controls=[
            ft.Row(controls=[cards[0], cards[1]], spacing=Space.xl, expand=False),
            ft.Row(controls=[cards[2], cards[3]], spacing=Space.xl, expand=False),
        ],
        spacing=Space.xl,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    cards_wrapper = ft.Container(
        content=cards_grid,
        width=960,
    )

    # ── foreground ──────────────────────────────────────────────
    fg_layer = ft.Column(
        controls=[
            header,
            ft.Container(height=48),
            cards_wrapper,
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
    )

    # ── root com Stack ──────────────────────────────────────────
    root = ft.Container(
        expand=True,
        opacity=0,
        animate_opacity=ft.Animation(Motion.slow, ft.AnimationCurve.EASE_OUT),
        content=ft.Stack(
            controls=[bg_layer, fg_layer],
            expand=True,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ),
    )
    home_root[0] = root

    # ── montar página ───────────────────────────────────────────
    page.controls.clear()
    page.add(root)
    page.update()

    async def _run() -> None:
        await asyncio.sleep(0.05)
        root.opacity = 1
        page.update()
        _next_turn()   # inicia rotação do bg

    page.run_task(_run)
```

---

## 6. Implementação — `src/gui/app.py`

**Apenas 2 linhas mudam:**

```python
# Linha 21 — assinatura
def build_app(page: ft.Page, initial_module: str = "transcription") -> None:

# Linha 77 (aprox.) — substituir hardcode
_DEFAULT_ID = initial_module          # era: _DEFAULT_ID = "transcription"
```

Nenhuma outra mudança. Retrocompatível com qualquer chamada existente que omita `initial_module`.

---

## 7. Implementação — `gui.py`

**Apenas a linha 25 muda:**

```python
# antes
show_splash(page, on_complete=lambda: build_app(page))

# depois
show_splash(page, on_complete=lambda: show_home(
    page,
    on_complete=lambda mid: build_app(page, initial_module=mid),
))
```

**Import adicionado (linha ~7):**
```python
from src.gui.home import show_home
```

---

## 8. Checklist de Implementação

- [ ] Criar `src/gui/home.py` com estrutura completa
  - [ ] `_MODULE_CARDS` com dados dos 4 módulos
  - [ ] `_palette(page)` helper
  - [ ] `_on_card_hover(e, ctr, accent, page)` — hover state
  - [ ] `_make_card(data, on_tap, page)` — factory do card
  - [ ] `show_home(page, on_complete)` — função principal
- [ ] Modificar `src/gui/app.py`
  - [ ] Adicionar parâmetro `initial_module: str = "transcription"`
  - [ ] Substituir `_DEFAULT_ID = "transcription"` por `_DEFAULT_ID = initial_module`
- [ ] Modificar `gui.py`
  - [ ] Adicionar import de `show_home`
  - [ ] Encadear `show_home` na chamada de `show_splash`
- [ ] Testar fluxo splash → home → módulo X (todos os 4 cards)
- [ ] Verificar comportamento no tema light (cards com `Color.light.*`)
- [ ] Verificar que a rotação do bg para de gerar erros ao navegar (try/except RuntimeError)
- [ ] Verificar redimensionamento da janela (min 1000px — cards 960px de width cabem)

---

## 9. Armadilhas Flet 0.85

| Armadilha | Solução aplicada |
|---|---|
| `ft.Border(all=...)` não existe | `ft.Border(left=, right=, top=, bottom=)` explícito |
| `ink=True` absorve eventos de cursor | Nunca usar; `GestureDetector` wrap + `on_tap` |
| `Container.on_click` + `GestureDetector` competem | `Container` sem `on_click`; handler só em `GestureDetector.on_tap` |
| `control.update()` em controle desmontado | `try/except RuntimeError` em `_next_turn` |
| `ft.Colors.SURFACE_VARIANT` / `SURFACE_CONTAINER` não existem | Usar `ft.Colors.SURFACE` e `Color.dark.surface_variant` diretamente |
| `page.update()` em cascata causa `IndexError` | Um único `page.update()` por evento assíncrono |
| `ft.Column(expand=True)` dentro de `ft.Stack` | Stack propaga o expand; `fg_layer` precisa de `expand=True` para ocupar toda a área |
| `home_root` referenciado antes de ser atribuído em `_navigate` | Usar lista `home_root: list[ft.Container] = [None]` como forward ref mutável |

---

## 10. Notas Adicionais

**Tema:** O header usa `Color.dark.primary` hardcoded para o ".tools" dourado. Se o usuário estiver em tema light, o dourado correto é `Color.light.primary` (`#E0982F`). Para corrigir dinamicamente, usar `_palette(page).primary` no lugar de `Color.dark.primary` — ou manter hardcoded se a home for sempre mostrada antes de `build_app` (onde o tema é lido do settings).

**Solução limpa:** ler o tema salvo antes de montar a home:

```python
# no início de show_home:
from src.gui import settings as _settings
from src.gui.theme import sync_page_bgcolor
cfg = _settings.load()
page.theme_mode = (
    ft.ThemeMode.DARK if cfg.get("theme_mode", "dark") == "dark"
    else ft.ThemeMode.LIGHT
)
sync_page_bgcolor(page)
```

Isso garante que o tema correto já esteja ativo quando os cards renderizam, sem duplicar a lógica que `build_app` já faz.

**Opção futura — skip home:** Adicionar `show_home_on_startup: bool = True` ao `settings.py` e um checkbox na home ou em alguma tela de preferências. Por ora, sempre exibida.
