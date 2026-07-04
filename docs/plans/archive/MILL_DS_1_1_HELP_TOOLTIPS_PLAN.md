# mill.tools — DS-1.1: Tooltips de ajuda por controle (ⓘ)

> Extensão do Design System. Adiciona um ícone **ⓘ (info)** ao lado dos controles, com
> **tooltip ao passar o mouse** (texto curto) e, opcionalmente, **modal ao clicar** (texto
> longo). Mecanismo único e replicável: todo módulo (Transcrição, Áudio, e futuros
> Vídeo/Imagens) ganha ajuda só passando uma chave.
>
> Implementar direto (sem plan mode). Pré-requisito: DS-1 (`src/gui/theme/`) já existe.

## Decisões travadas

- **Interação:** hover → `ft.Tooltip` (texto curto). **Modal só quando houver texto longo.**
- **Conteúdo:** dict Python central em `src/gui/help_content.py`, chaveado por
  `"<módulo>.<campo>"`. Separado da UI.
- **Posição:** ⓘ **inline à direita do rótulo** do controle (ex.: "Bitrate ⓘ").
- **Cor:** ⓘ em `on_surface_variant`; hover → `primary` (dourado). Sem texto longo, não é clicável.
- **Convenção vs `helper_text`:** dica curta sempre visível = `helper_text` (já existe);
  explicação "o que é/faz" sob demanda = ⓘ. Preferir ⓘ para desafogar o formulário.

> ⚠️ Verificar no Flet 0.85 (com `inspect`, como de praxe): `ft.Tooltip(message=, bgcolor=,
> text_style=, padding=, border=, wait_duration=)`; API de diálogo `page.open(dlg)` /
> `page.close(dlg)`; `ft.Icons.INFO_OUTLINED`; `Container.on_hover` (evento com `e.data`
> `"true"`/`"false"`).

---

## Arquivos

**Novos:**
- `src/gui/help_content.py` — registro central (`HELP_SHORT`, `HELP_LONG`) + `help_for`, `help_long_for`.
- `src/gui/theme/components/help.py` — `help_icon(short, long, page)` (puro) + `help_icon_for(key, page)` (faz o lookup no registro; **único arquivo do DS que importa `help_content`**).

**Modificados:**
- `src/gui/theme/components/inputs.py` — `labeled_field` ganha `help_key` + `page`.
- `src/gui/theme/components/layout.py` — `section` ganha `help_key` + `page`.
- `src/gui/theme/components/__init__.py` — exportar `help_icon`, `help_icon_for`.
- `src/gui/modules/audio/form_view.py` e `src/gui/views/form_view.py` — adotar (passar `help_key`/`page`).

> Acoplamento: `theme/components/help.py` → `src/gui/help_content.py` (uma aresta, isolada
> nesse arquivo). Aceitável para este app. Alternativa mais pura (não obrigatória): injetar
> o provedor de conteúdo via `set_help_provider(fn)` no startup.

---

## 1. `src/gui/help_content.py` (novo)

```python
"""Conteúdo de ajuda por controle — texto curto (tooltip) e longo (modal opcional).

Chave: "<módulo>.<campo>". Editar aqui é o único lugar para ajustar a cópia.
"""
from __future__ import annotations

#: Texto curto exibido no tooltip (hover). 1–2 frases.
HELP_SHORT: dict[str, str] = {
    # --- Transcrição ---
    "transcription.whisper_model": "Modelo do Whisper. Maiores = mais precisos e mais lentos. 'small' equilibra bem; use 'medium'/'large' em áudio difícil.",
    "transcription.language": "Idioma do áudio. 'auto' detecta sozinho; fixar o idioma evita erros de detecção em áudios curtos ou ruidosos.",
    "transcription.beam_size": "Largura da busca do decodificador. 1 = mais rápido; 3–5 = um pouco mais preciso e mais lento.",
    "transcription.format": "Reinsere quebras de parágrafo na transcrição via LLM, sem alterar o texto.",
    "transcription.analyze": "Gera uma análise estruturada (resumo, pontos-chave, citações…) a partir da transcrição.",
    "transcription.prompt": "Cria uma versão condensada (~40%) da transcrição, pronta para colar como contexto em prompts.",
    "transcription.model_stage": "Modelo desta etapa. Nomes começando com 'gemini' usam a nuvem (requer GOOGLE_API_KEY); os demais rodam local no Ollama.",
    # --- Áudio ---
    "audio.input": "Cole URLs (YouTube, SoundCloud…) ou selecione arquivos locais. URLs são baixadas; arquivos locais são convertidos/extraídos.",
    "audio.format": "Formato de saída. 'best' mantém o codec original sem reconverter (sem perda); os demais convertem via ffmpeg.",
    "audio.bitrate": "Taxa de bits para formatos com perda. Não melhora a fonte — acima de ~192 kbps pode só inflar o arquivo. Ignorado em 'best' e 'wav'.",
    "audio.embed_meta": "Embute título, autor e capa no arquivo. Em ogg/opus a capa pode ser omitida automaticamente.",
}

#: Texto longo (opcional) — quando presente, a ⓘ vira clicável e abre um modal.
HELP_LONG: dict[str, str] = {
    "audio.bitrate": (
        "O bitrate define quantos kbps o codec usa em formatos com perda (mp3, m4a, "
        "ogg, opus).\n\n"
        "Pontos importantes:\n"
        "• Não recupera qualidade que não existe na fonte — converter um áudio de 128 "
        "kbps para 320 kbps não melhora nada, só aumenta o arquivo.\n"
        "• 128–192 kbps costuma ser transparente para fala; música pede mais.\n"
        "• É ignorado quando o formato é 'best' (sem reencode) ou 'wav' (sem perda)."
    ),
}


def help_for(key: str) -> str | None:
    """Texto curto (tooltip) ou None se não houver entrada."""
    return HELP_SHORT.get(key)


def help_long_for(key: str) -> str | None:
    """Texto longo (modal) ou None."""
    return HELP_LONG.get(key)
```

> Se o dict crescer muito, dá para quebrar por módulo (`HELP_SHORT` montado a partir de
> sub-dicts) sem mudar a API. Por ora, um arquivo só.

## 2. `src/gui/theme/components/help.py` (novo)

```python
"""Ícone de ajuda (ⓘ): tooltip no hover, modal opcional no clique."""
from __future__ import annotations

import flet as ft

from src.gui.help_content import help_for, help_long_for
from src.gui.theme.tokens import Radius, Space


def help_icon(
    short: str,
    long: str | None = None,
    page: ft.Page | None = None,
    size: int = 16,
) -> ft.Container:
    """ⓘ com tooltip (short). Se `long` e `page`, clique abre modal."""
    icon = ft.Icon(ft.Icons.INFO_OUTLINED, size=size, color=ft.Colors.ON_SURFACE_VARIANT)
    box = ft.Container(
        content=icon,
        tooltip=ft.Tooltip(message=short, wait_duration=300),
        border_radius=Radius.pill,
        padding=2,
        ink=long is not None,
    )

    # hover → dourado
    def _hover(e: ft.HoverEvent) -> None:
        icon.color = ft.Colors.PRIMARY if e.data == "true" else ft.Colors.ON_SURFACE_VARIANT
        icon.update()

    box.on_hover = _hover

    if long is not None and page is not None:
        def _open(_e) -> None:
            dlg = ft.AlertDialog(
                title=ft.Text(short, size=16, weight=ft.FontWeight.W_600),
                content=ft.Container(content=ft.Text(long, selectable=True), width=420),
                actions=[ft.TextButton("Fechar", on_click=lambda _: page.close(dlg))],
            )
            page.open(dlg)

        box.on_click = _open

    return box


def help_icon_for(key: str, page: ft.Page | None = None) -> ft.Container | None:
    """Monta a ⓘ a partir do registro. None se a chave não tiver texto curto."""
    short = help_for(key)
    if not short:
        return None
    return help_icon(short, help_long_for(key), page)
```

## 3. Integração em `inputs.py` — `labeled_field`

Estender a assinatura (mantendo compatibilidade) e transformar o rótulo num `Row` com a ⓘ
quando houver `help_key`:

```python
from src.gui.theme.components.help import help_icon_for  # topo do arquivo

def labeled_field(
    label: str,
    control: ft.Control,
    helper: str | None = None,
    help_key: str | None = None,
    page: ft.Page | None = None,
) -> ft.Column:
    icon = help_icon_for(help_key, page) if help_key else None
    label_text = ft.Text(
        label, size=Type.label.size, weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    label_row = (
        ft.Row([label_text, icon], spacing=Space.xs, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        if icon else label_text
    )
    items: list[ft.Control] = [label_row, control]
    if helper:
        items.append(ft.Text(helper, size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT))
    return ft.Column(controls=items, spacing=Space.sm)
```

## 4. Integração em `layout.py` — `section`

Mesmo padrão (cobre os grupos do form de Áudio, ex.: "Formato de saída", "Bitrate (kbps)"):

```python
from src.gui.theme.components.help import help_icon_for  # topo do arquivo

def section(
    label: str,
    *controls: ft.Control,
    help_key: str | None = None,
    page: ft.Page | None = None,
) -> ft.Column:
    icon = help_icon_for(help_key, page) if help_key else None
    label_text = ft.Text(
        label, size=Type.label.size, weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    header = (
        ft.Row([label_text, icon], spacing=Space.xs, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        if icon else label_text
    )
    return ft.Column(controls=[header, *controls], spacing=Space.sm)
```

## 5. `components/__init__.py`

Adicionar aos imports/`__all__`:
```python
from src.gui.theme.components.help import help_icon, help_icon_for
# ... e em __all__: "help_icon", "help_icon_for"
```

## 6. Adoção nos módulos (call sites)

Passar `help_key` + `page` onde os controles são montados. Exemplos:

**`modules/audio/form_view.py`:**
```python
section("Formato de saída", fmt_grid, help_key="audio.format", page=page)
section("Bitrate (kbps)", bitrate_grid, help_key="audio.bitrate", page=page)
labeled_field("Entrada", input_source.control, help_key="audio.input", page=page)
switch_row("Embutir capa e metadados", value=True, on_change=...)  # ⓘ ao lado: ver nota
```

**`views/form_view.py` (Transcrição):**
```python
labeled_field("Modelo Whisper", whisper_dd, help_key="transcription.whisper_model", page=page)
labeled_field("Idioma", lang_dd, help_key="transcription.language", page=page)
slider_row("Beam size", value=1, ...)            # ⓘ ao lado: ver nota
labeled_field("Modelo de análise", am_dd, help_key="transcription.model_stage", page=page)
```

**Nota sobre `switch_row`/`slider_row`:** esses montam o próprio rótulo internamente. Duas
opções (escolher uma e manter consistente):
- (a) Adicionar `help_key`/`page` a `switch_row` e `slider_row` também (mesma lógica do §3); ou
- (b) No módulo, envolver: `ft.Row([switch, help_icon_for("transcription.format", page)])`.
Recomendo **(a)** para uniformidade — replica o mesmo padrão de todos os controles.

## Mapa de chaves (cobertura alvo)

| Módulo | Chaves |
|---|---|
| Transcrição | `whisper_model`, `language`, `beam_size`, `format`, `analyze`, `prompt`, `model_stage` (reusável p/ fm/am/pm) |
| Áudio | `input`, `format`, `bitrate` (com modal), `embed_meta` |
| Vídeo/Imagens (futuro) | criar `video.*` / `image.*` no mesmo dict |

## Estilo (DS)
- ⓘ: `ft.Icons.INFO_OUTLINED`, 16px, `on_surface_variant`; hover → `primary`.
- Tooltip: usar `ft.Tooltip` (verificar suporte a `bgcolor`/`text_style`/`border` na versão;
  se suportar, alinhar a `surface`/`outline`/`body`). `wait_duration=300`.
- Modal: `AlertDialog` com título = texto curto, corpo = texto longo (largura ~420), botão "Fechar".

## Checklist
- [ ] `src/gui/help_content.py` (HELP_SHORT, HELP_LONG, help_for, help_long_for)
- [ ] `src/gui/theme/components/help.py` (help_icon, help_icon_for)
- [ ] `inputs.py`: `labeled_field` com `help_key`/`page`
- [ ] `layout.py`: `section` com `help_key`/`page`
- [ ] (opção a) `inputs.py`: `switch_row` e `slider_row` com `help_key`/`page`
- [ ] `components/__init__.py`: exportar help_icon/help_icon_for
- [ ] Adoção: `modules/audio/form_view.py` + `views/form_view.py` passam `help_key`/`page`
- [ ] Verificar APIs Flet 0.85 (Tooltip, page.open/close, INFO_OUTLINED, on_hover)
- [ ] `help.py` ≤ ~60 linhas

## Smoke tests
- [ ] Hover na ⓘ do "Bitrate" → tooltip curto aparece.
- [ ] Clique na ⓘ do "Bitrate" → abre modal com o texto longo; "Fechar" funciona.
- [ ] ⓘ sem `HELP_LONG` (ex.: "Idioma") → só tooltip, não é clicável (sem ripple).
- [ ] Chave inexistente → nenhuma ⓘ é renderizada (sem erro).
- [ ] Hover muda a cor da ⓘ para dourado e volta ao sair.
- [ ] Tema claro/escuro: ⓘ e tooltip legíveis nos dois.
