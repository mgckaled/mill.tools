# mill.tools — Plano rápido: ícone do app (.ico)

> Configurar o ícone do moinho na janela e no executável. Gerado a partir do símbolo
> atual (`branding/mill-symbol.svg`).

## Arquivos (já gerados)

```
assets/icons/
├── mill.ico        ← multi-resolução (16, 24, 32, 48, 64, 128, 256 px) — janela + flet pack
└── mill-512.png    ← PNG grande — usar no flet build (ver pegadinha abaixo)
```

> Pasta dedicada `assets/icons/` separa o ícone do app dos assets de marca (`branding/`).

## 1. Ícone da janela em runtime (`uv run gui.py`)

No `gui.py`, dentro de `main`, antes do `show_splash`:

```python
from pathlib import Path

_ICON = Path(__file__).resolve().parent / "assets" / "icons" / "mill.ico"

def main(page: ft.Page) -> None:
    page.title = "mill.tools"
    page.window.icon = str(_ICON)   # caminho ABSOLUTO (ver pegadinha 1)
    ...
```

- **Só tem efeito no Windows** (`page.window.icon` é Windows-only).
- Atualiza o ícone da barra de título e da barra de tarefas com o app rodando.

## 2. Empacotamento

**`flet pack` (PyInstaller)** — usa o `.ico` direto:

```bash
flet pack gui.py --name mill.tools --icon assets/icons/mill.ico
```

Isso aplica o ícone ao `.exe`, à janela, à barra de tarefas e ao Gerenciador de Tarefas.

**`flet build windows`** — devido a um bug conhecido (só usa o 16×16 de um `.ico`
multi-tamanho), passe o **PNG grande** em vez do `.ico`:

```bash
flet build windows --icon assets/icons/mill-512.png
```

## Pegadinhas (documentadas no Flet)

1. **`page.window.icon` com caminho relativo falha** (issue #3438) — sempre use caminho
   absoluto, como no exemplo acima.
2. **`flet build` + `.ico` multi-tamanho usa só o 16×16** (issue #6007) — por isso o
   `mill-512.png` existe; use-o no `flet build`. No `flet pack` o `.ico` funciona normal.
3. O ícone da janela em runtime pode não aparecer em alguns cenários sem empacotar; o
   resultado garantido é via `flet pack`/`flet build`.

## Checklist
- [ ] `gui.py`: `page.window.icon = str(_ICON)` (caminho absoluto)
- [ ] Smoke test runtime: `uv run gui.py` → ícone do moinho na barra de título/tarefas (Windows)
- [ ] Empacotar: `flet pack gui.py --name mill.tools --icon assets/icons/mill.ico`
- [ ] Conferir ícone do `.exe` no Explorer e na barra de tarefas (16px nítido, 256px na visão grande)
- [ ] Se usar `flet build windows`, trocar para `--icon assets/icons/mill-512.png`

## Regenerar o `.ico` (se o símbolo mudar)

```bash
for s in 16 24 32 48 64 128 256; do
  magick -background none branding/mill-symbol.svg -resize ${s}x${s} ico_$s.png
done
magick ico_16.png ico_24.png ico_32.png ico_48.png ico_64.png ico_128.png ico_256.png assets/icons/mill.ico
magick -background none branding/mill-symbol.svg -resize 512x512 assets/icons/mill-512.png
```

## Sources
- [Flet — Packaging desktop apps with a custom icon](https://flet.dev/blog/packaging-desktop-apps-with-custom-icon/)
- [Flet — Window type (page.window.icon)](https://docs.flet.dev/types/window/)
- [Issue #3438 — window.icon com caminho relativo](https://github.com/flet-dev/flet/issues/3438) · [Issue #6007 — flet build usa só 16×16](https://github.com/flet-dev/flet/issues/6007)
