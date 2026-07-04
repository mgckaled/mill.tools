# Plano de Implementação — Home Screen "crescer-no-hover"

> Alvo: `src/gui/home.py` (arquivo único). Sem dependência nova. Flet 0.85.2.
> Este plano prescreve **estrutura e comportamento**, não o texto dos cards.
> O **copy** (descrições e features) fica a cargo do Claude Code — ver seção "Conteúdo".

---

## 1. Objetivo

A home está saturada: os 8 cards (5 ferramentas + 3 hubs) exibem **título + descrição + 3 bullets ao mesmo tempo**, virando uma parede de texto.

Meta:

- **Repouso limpo** — só ícone + título + **uma** linha de descrição (sem bullets).
- **Detalhe rico revelado ao passar o mouse**, de forma **fluida** (não-modal).
- Manter a divisão atual: **5 ferramentas** (grade 3+2) + **3 hubs** (Biblioteca/IA/Receitas), com os rótulos de seção `FERRAMENTAS` e `ACERVO & INTELIGÊNCIA`.

---

## 2. Abordagem: grow-to-reveal (crescer-no-hover)

- **Repouso:** o `Container` do card fica numa **altura compacta**; o bloco de detalhe já existe na árvore mas é **clipado** pela altura (`clip_behavior=ANTI_ALIAS`).
- **Hover:** a altura do `Container` cresce (animada) e revela o detalhe; acrescenta borda de acento, leve `scale` e fade-in do detalhe (`opacity`).
- **Anti-reflow (ponto crítico):** a `Row` que segura os cards recebe **altura fixa = altura expandida** + `vertical_alignment=START`. Assim o card cresce **por dentro** da fileira, sem empurrar as fileiras de baixo nem estourar a janela.

### Por que essa técnica (restrições do Flet 0.85.2)

Primitivas **já comprovadas no próprio projeto**: `Container.animate` (anima `height`/`bgcolor`/`border`), `animate_opacity`, `scale` + `animate_scale` (`splash.py`), `on_hover` (`e.data == "true"`), `clip_behavior`, `GestureDetector` + `Cursor.interactive`.

Descartado (e por quê):

- **Tooltip rico** — layout/estilo pobres no 0.85.2.
- **Modal/dialog** — não desejado.
- **Overlay flutuante ancorado por pixel** — o 0.85.2 não expõe geometria pós-layout confiável; posicionar um painel sobre o card vizinho fica frágil.

**Fallback de menor risco** (se o crescer-no-hover ficar instável na máquina alvo): cross-fade de conteúdo num card de **tamanho fixo** (dois layers alternando `opacity` ou `AnimatedSwitcher`) — zero reflow, mas perde a sensação de "crescer".

---

## 3. Passos de implementação

### Passo 1 — Constantes

Substituir `_TOOL_CARD_H` e `_HUB_CARD_H` por pares compacto/expandido:

```python
_TOOL_COMPACT_H = 100      # repouso: ícone + título + 1 linha de descrição
_TOOL_EXPANDED_H = 200     # hover: revela o detalhe
_HUB_COMPACT_H = 88
_HUB_EXPANDED_H = 150
```

> Os números são ponto de partida — ajustar ao copy final (ver Passo 5 / Validação).

### Passo 2 — `_make_card` (ferramentas)

Reescrever para: detalhe em `Column` com `opacity=0`; `Container` compacto + `clip_behavior` + `animate` + `animate_scale`; handler de hover local que cresce/encolhe.

```python
def _make_card(data, on_tap, page):
    accent = data["accent"]
    pal = _palette(page)

    detail = ft.Column(
        controls=[_feature_row(f) for f in data["features"]],
        spacing=4,
        opacity=0,                                              # escondido no repouso (o clip já corta)
        animate_opacity=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN),
    )

    ctr = ft.Container(
        height=_TOOL_COMPACT_H,
        expand=True,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,              # corta o detalhe quando compacto
        border_radius=Radius.lg,
        border=_border(ft.BorderSide(1.5, pal.outline_variant)),
        bgcolor=ft.Colors.with_opacity(0.75, pal.surface),
        padding=ft.Padding(left=Space.lg, right=Space.lg, top=Space.lg, bottom=Space.lg),
        shadow=ft.BoxShadow(blur_radius=12, spread_radius=0, offset=ft.Offset(0, 4),
                            color=ft.Colors.with_opacity(0.20, ft.Colors.BLACK)),
        animate=ft.Animation(Motion.base, ft.AnimationCurve.EASE_OUT),         # anima a altura
        animate_scale=ft.Animation(Motion.base, ft.AnimationCurve.EASE_OUT),
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(data["icon"], size=_CARD_ICON_SIZE, color=accent),
                        ft.Column(
                            controls=[
                                ft.Text(data["title"], size=Type.heading.size,
                                        weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE),
                                ft.Text(data["desc"], size=Type.caption.size,
                                        color=ft.Colors.ON_SURFACE_VARIANT, no_wrap=False),
                            ],
                            spacing=Space.xxs, expand=True,
                        ),
                    ],
                    spacing=Space.md,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=Space.sm),
                detail,
            ],
            spacing=0,
        ),
    )

    def _hover(e):
        on = e.data == "true"
        ctr.height = _TOOL_EXPANDED_H if on else _TOOL_COMPACT_H
        ctr.scale = 1.015 if on else 1.0
        ctr.bgcolor = ft.Colors.with_opacity(0.88 if on else 0.75,
                                             pal.surface_hover if on else pal.surface)
        ctr.border = _border(
            ft.BorderSide(1.5, ft.Colors.with_opacity(0.6, accent)) if on
            else ft.BorderSide(1.5, pal.outline_variant))
        detail.opacity = 1 if on else 0
        ctr.update()

    ctr.on_hover = _hover
    return ft.GestureDetector(
        mouse_cursor=Cursor.interactive, content=ctr,
        on_tap=lambda _: on_tap(data["id"]), expand=True,
    )
```

### Passo 3 — `_make_hub_card` (hubs, horizontais)

Mesma lógica, mantendo o layout horizontal (chip de ícone + info) e a **borda de repouso dourada** + selo "HUB". Marcar a `Column` de features como `detail` (opacity 0 + `animate_opacity`).

```python
def _make_hub_card(data, on_tap, page):
    accent = data["accent"]
    pal = _palette(page)

    icon_chip = ft.Container(
        width=_HUB_ICON_CHIP, height=_HUB_ICON_CHIP, border_radius=Radius.md,
        bgcolor=ft.Colors.with_opacity(0.14, accent), alignment=ft.Alignment.CENTER,
        content=ft.Icon(data["icon"], size=IconSize.xl, color=accent),
    )
    hub_badge = ft.Container(
        bgcolor=ft.Colors.with_opacity(0.16, ft.Colors.PRIMARY), border_radius=Radius.pill,
        padding=ft.Padding(left=Space.xs, right=Space.xs, top=Space.xxs, bottom=Space.xxs),
        content=ft.Text("HUB", size=Type.tiny.size, weight=ft.FontWeight.W_600,
                        color=ft.Colors.PRIMARY),
    )

    detail = ft.Column(
        controls=[_feature_row(f) for f in data["features"]],
        spacing=4,
        opacity=0,
        animate_opacity=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN),
    )

    info = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Text(data["title"], size=Type.heading.size, weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE),
                    ft.Container(expand=True),
                    hub_badge,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(data["desc"], size=Type.caption.size,
                    color=ft.Colors.ON_SURFACE_VARIANT, no_wrap=False),
            ft.Container(height=Space.xxs),
            detail,
        ],
        spacing=Space.xxs, expand=True,
    )

    ctr = ft.Container(
        height=_HUB_COMPACT_H,
        expand=True,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        border_radius=Radius.lg,
        border=_border(ft.BorderSide(1.5, ft.Colors.with_opacity(0.45, ft.Colors.PRIMARY))),
        bgcolor=ft.Colors.with_opacity(0.80, pal.surface),
        padding=ft.Padding(left=Space.lg, right=Space.lg, top=Space.lg, bottom=Space.lg),
        shadow=ft.BoxShadow(blur_radius=14, spread_radius=0, offset=ft.Offset(0, 5),
                            color=ft.Colors.with_opacity(0.24, ft.Colors.BLACK)),
        animate=ft.Animation(Motion.base, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(Motion.base, ft.AnimationCurve.EASE_OUT),
        content=ft.Row(controls=[icon_chip, info], spacing=Space.md,
                       vertical_alignment=ft.CrossAxisAlignment.START),
    )

    def _hover(e):
        on = e.data == "true"
        ctr.height = _HUB_EXPANDED_H if on else _HUB_COMPACT_H
        ctr.scale = 1.012 if on else 1.0
        ctr.bgcolor = ft.Colors.with_opacity(0.90 if on else 0.80,
                                             pal.surface_hover if on else pal.surface)
        ctr.border = _border(
            ft.BorderSide(1.5, ft.Colors.with_opacity(0.6, accent)) if on
            else ft.BorderSide(1.5, ft.Colors.with_opacity(0.45, ft.Colors.PRIMARY)))
        detail.opacity = 1 if on else 0
        ctr.update()

    ctr.on_hover = _hover
    return ft.GestureDetector(
        mouse_cursor=Cursor.interactive, content=ctr,
        on_tap=lambda _: on_tap(data["id"]), expand=True,
    )
```

### Passo 4 — Alturas fixas nas fileiras (`show_home`)

É o que impede o reflow. Adicionar `height` + `vertical_alignment=START` nas três `Row` de cards:

```python
# tools_grid — nas DUAS Rows internas
ft.Row(controls=[tool_cards[0], tool_cards[1], tool_cards[2]],
       spacing=Space.xl, height=_TOOL_EXPANDED_H,
       vertical_alignment=ft.CrossAxisAlignment.START),
ft.Row(controls=[ft.Container(expand=1), _flex(tool_cards[3], 2),
                 _flex(tool_cards[4], 2), ft.Container(expand=1)],
       spacing=Space.xl, height=_TOOL_EXPANDED_H,
       vertical_alignment=ft.CrossAxisAlignment.START),

# hubs_grid
hubs_grid = ft.Row(controls=hub_cards, spacing=Space.xl,
                   height=_HUB_EXPANDED_H,
                   vertical_alignment=ft.CrossAxisAlignment.START)
```

### Passo 5 — Limpeza e o que NÃO mexer

- Remover `_on_card_hover` (fica sem uso — o hover agora é local a cada card).
- **Não** alterar: `_on_tap` / navegação com fade-out, fundo animado (`bg_symbol`), `header`, `hint`, rótulos de seção, montagem do `Stack`/página.

---

## 4. Conteúdo (copy) dos cards — decidir no Claude Code

Este plano **não prescreve o texto**. O Claude Code deve decidir — com base no `CLAUDE.md`, no `README.md` e no que já existe em `_TOOL_CARDS`/`_HUB_CARDS` — se mantém, enxuga ou reescreve `desc` e `features` de cada card, garantindo que reflitam com precisão as funcionalidades reais de cada módulo.

Regras **de estrutura** (não de texto) que o copy deve respeitar:

- **Repouso** mostra apenas **uma** linha de `desc`, **sem bullets**.
- O **detalhe revelado** no hover pode ser as `features` (com ou sem marcador) ou um parágrafo curto — preferir **2–3 itens enxutos**.
- Manter ícones e acentos (`accent`) atuais, salvo decisão explícita em contrário.

---

## 5. Validação

1. `uv run gui.py` → passar o mouse em **cada um dos 8 cards**: o detalhe revela suave, **sem "pulo"** das fileiras de baixo, e **tudo cabe** na janela (sem scroll).
2. Conferir nos **dois temas** (claro/escuro) — o código usa `_palette(page)`.
3. Conferir que o **clique navega** (`on_tap`) e que o **fade-out de navegação** segue funcionando.
4. `uv run pytest -m unit` — garantir que nenhum import quebrou (a GUI não tem teste headless; aqui é só sanidade).

---

## 6. Riscos / armadilhas

- **`vertical_alignment=START` é obrigatório** nas Rows de card: sem ele, o `CrossAxisAlignment` default estica o card à altura cheia da fileira e ele **nunca** fica compacto.
- **`clip_behavior=ANTI_ALIAS`** é o que esconde o detalhe no repouso; o `opacity` é só polimento.
- Ajustar `_TOOL_EXPANDED_H` / `_HUB_EXPANDED_H` ao **copy final**: se faltar/sobrar espaço, é só esse número.
- **Nunca usar `ink=True`** em container clicável — absorve o ponteiro e anula o cursor; manter o `GestureDetector` externo com `Cursor.interactive`.
- Hubs: manter a **borda de repouso dourada** (`with_opacity(0.45, ft.Colors.PRIMARY)`) e o selo "HUB".
- Se a soma das alturas estourar a janela (sem scroll na home), reduzir `_TOOL_EXPANDED_H` ou as margens do `fg_layer` antes de mudar a abordagem.
