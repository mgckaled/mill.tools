# mill.tools — Plano: Splash Screen + Moinho Giratório

> Plano de implementação para (1) uma **tela de abertura (splash)** com o logo e uma
> animação de entrada, e (2) substituir a engrenagem do header do Pipeline por um
> **cata-vento que gira enquanto trabalha e para ao terminar**.
>
> APIs do Flet 0.85 verificadas na documentação oficial (a doc "current" do Flet bate
> com esta versão: `ft.run`, `LayoutControl`, `ft.Rotate(angle=, alignment=)`,
> `ft.Animation`/`ft.AnimationCurve`, `on_animation_end`, `page.run_task`).

## Premissas

- Não quebrar nada do que já funciona (PR2 concluído);
- Assets já existem em `branding/`: `mill-symbol.png` (cata-vento isolado) e
  `mill-logo-wordmark.png`. Recolor = find/replace do hex `#F4A63C` no SVG de origem.
- O `build_app(page)` já termina com `page.controls.clear(); page.add(layout); page.update()`
  — então a troca splash→app é "de graça": basta o splash aparecer **antes** de chamá-lo.
- Tudo roda na UI thread via `page.run_task` (corrotina no event loop), evitando o
  problema documentado de `page.update()` vindo de worker thread.

---

## Parte 0 — Helper de asset compartilhado (evita duplicação)

Tanto o splash quanto o spinner carregam `mill-symbol.png` em base64. Centralizar num
único lugar.

**Novo arquivo: `src/gui/assets.py`**

```python
"""Carregamento de assets de branding (base64) para uso em ft.Image."""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

# src/gui/assets.py -> parents[2] = raiz do projeto
_BRANDING = Path(__file__).resolve().parents[2] / "branding"


@lru_cache(maxsize=None)
def b64(name: str) -> str:
    """Lê branding/<name> e devolve string base64 (cacheado)."""
    return base64.b64encode((_BRANDING / name).read_bytes()).decode()
```

> `lru_cache` evita reler o arquivo a cada uso (o spinner pode recriar o ícone, o splash
> roda uma vez). Se preferir não depender do caminho relativo, configure `assets_dir` no
> `ft.run(main, assets_dir="branding")` e use `src="mill-symbol.png"`.

---

## Parte 1 — Splash Screen

### 1.1 Comportamento

Ao abrir o app, uma tela cheia no azul-escuro do GUI mostra o cata-vento + "mill.tools".
Linha do tempo (~2,05 s):

| t (s) | Ação |
|---|---|
| 0.00 | splash montado (símbolo invisível, escala 0.85, ângulo 0) |
| 0.05 | símbolo: fade-in + scale→1 + **uma volta** (1,4 s, EASE_OUT) |
| 0.30 | wordmark "mill.tools" faz fade-in |
| 1.70 | container do splash inicia fade-out |
| 2.05 | `on_complete()` → `build_app(page)` monta a UI real |

> Aproveitar o tempo do splash para **init real** (carregar settings, `check_dependencies`)
> em vez de só `asyncio.sleep`, quando houver o que inicializar.

### 1.2 Novo arquivo: `src/gui/splash.py`

```python
"""Tela de abertura (splash) do mill.tools — cata-vento + fade de entrada."""
from __future__ import annotations

import asyncio
import math
from typing import Callable

import flet as ft

from src.gui.assets import b64

BG, GOLD, LIGHT = "#0E1B2C", "#F4A63C", "#EAF0F6"


def show_splash(page: ft.Page, on_complete: Callable[[], None]) -> None:
    """Exibe o splash full-screen; ao terminar, chama on_complete()."""
    page.padding = 0
    page.bgcolor = BG

    symbol = ft.Image(
        src_base64=b64("mill-symbol.png"),
        width=150, height=150,
        opacity=0, scale=0.85,
        rotate=ft.Rotate(angle=0, alignment=ft.Alignment.CENTER),
        animate_opacity=ft.Animation(500, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(600, ft.AnimationCurve.EASE_OUT),
        animate_rotation=ft.Animation(1400, ft.AnimationCurve.EASE_OUT),
    )
    title = ft.Text(
        spans=[
            ft.TextSpan("mill", ft.TextStyle(color=LIGHT, weight=ft.FontWeight.W_600)),
            ft.TextSpan(".tools", ft.TextStyle(color=GOLD, weight=ft.FontWeight.W_400)),
        ],
        size=34, opacity=0,
        animate_opacity=ft.Animation(500, ft.AnimationCurve.EASE_OUT),
    )
    root = ft.Container(
        expand=True, bgcolor=BG, alignment=ft.Alignment.CENTER,
        opacity=1, animate_opacity=ft.Animation(350, ft.AnimationCurve.EASE_IN),
        content=ft.Column(
            [symbol, ft.Container(height=18), title],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    page.controls.clear()
    page.add(root)
    page.update()

    async def _run() -> None:
        await asyncio.sleep(0.05)            # deixa o estado inicial pintar
        symbol.opacity = 1
        symbol.scale = 1
        symbol.rotate.angle = 2 * math.pi    # uma volta completa (radianos)
        page.update()
        await asyncio.sleep(0.25)
        title.opacity = 1
        page.update()
        # (opcional) init real aqui: settings, check_dependencies, etc.
        await asyncio.sleep(1.4)             # segura a marca
        root.opacity = 0                     # fade-out
        page.update()
        await asyncio.sleep(0.35)
        on_complete()                        # build_app limpa e monta a UI real

    page.run_task(_run)
```

### 1.3 Wiring em `gui.py`

Só o final do `main` muda:

```python
from src.gui.splash import show_splash

def main(page: ft.Page) -> None:
    page.title = "mill.tools"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 1200
    page.window.height = 800
    page.window.min_width = 1000
    page.window.min_height = 600
    show_splash(page, on_complete=lambda: build_app(page))   # era: build_app(page)
```

### Checklist Parte 1
- [ ] `src/gui/assets.py` com `b64()`
- [ ] `src/gui/splash.py` com `show_splash()`
- [ ] `gui.py`: trocar `build_app(page)` por `show_splash(page, on_complete=lambda: build_app(page))`
- [ ] Verificar `ft.TextSpan`/`ft.TextStyle`/`ft.FontWeight.W_600` (ver "API a confirmar"); se faltar, usar fallback (imagem do wordmark ou dois `ft.Text`)
- [ ] Smoke test: abrir `uv run gui.py` → splash com giro+fade → transição limpa para a UI
- [ ] Smoke test: pipeline completo funciona normalmente após o splash

---

## Parte 2 — Moinho giratório no header do Pipeline

### 2.1 Comportamento

A engrenagem (`ft.Icon(ft.Icons.SETTINGS_SUGGEST_ROUNDED, ...)`, hoje na **linha 376** de
`src/gui/views/progress_view.py`) vira um `ft.Image` do cata-vento que **gira
continuamente enquanto o pipeline trabalha** e **para ao terminar** (descansa na vertical,
pois cada ciclo fecha num múltiplo de 360°).

Mecânica: giro contínuo encadeado via `on_animation_end` — cada volta dispara a próxima
enquanto `_spinning` for `True`. Curva **LINEAR** (essencial: com `EASE_*` o giro pulsaria).

### 2.2 Edição em `progress_view.py`

**(a) Defina ícone + helpers** perto dos outros widgets, antes do `pipeline_panel` (~linha 345):

```python
import math
from src.gui.assets import b64

_SPIN_PERIOD = 900            # ms por volta (menor = mais rápido)
_spinning: list[bool] = [False]

status_icon = ft.Image(
    src_base64=b64("mill-symbol.png"),
    width=22, height=22,
    rotate=ft.Rotate(angle=0, alignment=ft.Alignment.CENTER),
    animate_rotation=ft.Animation(_SPIN_PERIOD, ft.AnimationCurve.LINEAR),
)

def _spin_step(e=None) -> None:
    # chamado ao fim de cada volta; se ainda rodando, agenda a próxima
    if _spinning[0]:
        status_icon.rotate.angle += 2 * math.pi
        status_icon.update()

status_icon.on_animation_end = _spin_step

def start_spin() -> None:
    if not _spinning[0]:
        _spinning[0] = True
        _spin_step()          # primeira volta inicia o ciclo

def stop_spin() -> None:
    _spinning[0] = False      # a volta atual fecha em múltiplo de 2π (vertical) e para
```

**(b) Use `status_icon` no header** (linha 376), no lugar do `ft.Icon(...)`:

```python
ft.Row(
    controls=[
        status_icon,        # era: ft.Icon(ft.Icons.SETTINGS_SUGGEST_ROUNDED, color=ft.Colors.BLUE_300)
        stage_label,
    ],
    spacing=8,
    vertical_alignment=ft.CrossAxisAlignment.CENTER,
),
```

**(c) Ligue/desligue nos eventos** dentro de `_handle_event`:

- **Iniciar** — no ramo que torna a barra indeterminada (~linhas 458-464):

```python
elif event.type in (
    "metadata_start", "download_start", "whisper_loading",
    "transcribe_started", "format_started", "analyze_started",
    "analyze_merge_start", "translation_start", "prompt_started",
):
    progress_bar.visible = True
    progress_bar.value = None
    start_spin()           # <-- adiciona
```

- **Parar** — adicionar `stop_spin()` (antes do `return`) em cada ramo de término:
  `task_done` (~l.487), `task_error` (~l.493), `pipeline_done` (~l.501),
  `pipeline_error` (~l.508), `pipeline_cancelled` (~l.515).

### 2.3 Notas de robustez
- **Não resetar o ângulo** no `stop_spin` — só `_spinning=False`. Forçar `angle=0`
  faria a moinho "rebobinar" de volta (giro reverso feio). Deixar parar sozinho fecha na
  vertical.
- O ângulo cresce indefinidamente (≈330 voltas num pipeline de 5 min), mas é `float` — ok.
- `on_animation_end` dispara para cada animação; aqui só `rotate` anima, então não precisa
  filtrar `e.data`. Se quiser blindar: `if e is not None and e.data != "rotation": return`.
- (Opcional UX) em `pipeline_done`, trocar por um check verde: `status_icon.visible=False`
  e exibir `ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_400)`.

### Checklist Parte 2
- [ ] Importar `math` e `b64` em `progress_view.py`
- [ ] Definir `status_icon` + `_spinning` + `_spin_step`/`start_spin`/`stop_spin`
- [ ] Substituir o `ft.Icon` da linha 376 por `status_icon`
- [ ] `start_spin()` no ramo de barra indeterminada
- [ ] `stop_spin()` nos 5 ramos de término
- [ ] Smoke test: rodar pipeline → moinho gira liso (LINEAR) → para na vertical ao concluir
- [ ] Smoke test: cancelar (Esc) no meio → moinho para; erro (URL inválida) → moinho para

---

## API do Flet 0.85 — confirmado x a confirmar

**Confirmado na doc oficial:**
- `page.run_task(handler)` roda corrotina no event loop da página.
- `animate_opacity/scale/rotation` aceitam `ft.Animation(duration, curve)`, `int` (ms,
  LINEAR) ou `bool`.
- `rotate=ft.Rotate(angle=, alignment=ft.Alignment.CENTER)`; anima-se mutando `.angle`.
- `on_animation_end` existe em `LayoutControl`; `e.data` ∈ {`"opacity"`,`"rotation"`,
  `"scale"`,`"offset"`,`"position"`,`"container"`}.
- Alinhamento é `ft.Alignment.CENTER` (classe), **não** `ft.alignment.center`.

**A confirmar com `inspect` antes de rodar** (não apareceu explícito na doc consultada):
- `ft.TextSpan(text, style=ft.TextStyle(color=, weight=))` e `ft.FontWeight.W_600`.
  Fallback se divergir: usar a imagem `mill-logo-wordmark.png` no splash, ou dois
  `ft.Text` simples coloridos.

---

## Arquivos tocados

| Parte | Arquivo | Mudança |
|---|---|---|
| 0 | `src/gui/assets.py` (novo) | helper `b64()` de branding |
| 1 | `src/gui/splash.py` (novo) | `show_splash()` |
| 1 | `gui.py` | chamar `show_splash` em vez de `build_app` direto |
| 2 | `src/gui/views/progress_view.py` | `status_icon` + helpers de giro; troca da linha 376; `start_spin`/`stop_spin` nos eventos |

## Sources
- [Flet — Animations (cookbook): rotation, on_animation_end, AnimationCurve](https://flet.dev/docs/cookbook/animations)
- [Flet — Page: run_task](https://docs.flet.dev/controls/page/)
