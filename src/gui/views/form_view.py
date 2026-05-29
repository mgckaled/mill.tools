"""View de formulário do yt-transcriber GUI.

Coleta os parâmetros do pipeline e dispara o worker ao clicar em Iniciar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import flet as ft

from src.gui import settings
from src.gui.workers import PipelineArgs

# ---------------------------------------------------------------------------
# Helpers para .env
# ---------------------------------------------------------------------------

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _read_api_key() -> str:
    """Lê GOOGLE_API_KEY do arquivo .env da raiz do projeto."""
    if not _ENV_FILE.exists():
        return ""
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def _write_api_key(value: str) -> None:
    """Escreve ou atualiza GOOGLE_API_KEY no arquivo .env."""
    if not value:
        return
    lines = _ENV_FILE.read_text(encoding="utf-8").splitlines() if _ENV_FILE.exists() else []
    key_line = f"GOOGLE_API_KEY={value}"
    updated = [key_line if line.startswith("GOOGLE_API_KEY=") else line for line in lines]
    if not any(line.startswith("GOOGLE_API_KEY=") for line in lines):
        updated.append(key_line)
    _ENV_FILE.write_text("\n".join(updated) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------


def build_form_view(page: ft.Page, on_start: Callable[[PipelineArgs], None]) -> ft.Control:
    """Retorna o controle raiz da view de formulário.

    Args:
        page: Página Flet.
        on_start: Callable recebendo PipelineArgs, chamado ao clicar Iniciar.
    """
    cfg = settings.load()

    # ------------------------------------------------------------------
    # URL
    # ------------------------------------------------------------------
    url_error = ft.Text("", color=ft.Colors.RED_400, size=12, visible=False)

    url_field = ft.TextField(
        label="URL do YouTube",
        hint_text="https://www.youtube.com/watch?v=...",
        expand=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def _validate_url(value: str) -> bool:
        return "youtube.com" in value or "youtu.be" in value

    def _on_url_change(e: ft.ControlEvent) -> None:
        value = url_field.value or ""
        is_valid = _validate_url(value) if value else False
        url_error.visible = bool(value) and not is_valid
        url_error.value = "URL inválida — deve conter youtube.com ou youtu.be" if url_error.visible else ""
        start_btn.disabled = not (value and is_valid)
        page.update()

    url_field.on_change = _on_url_change

    # ------------------------------------------------------------------
    # Whisper model
    # ------------------------------------------------------------------
    whisper_dropdown = ft.Dropdown(
        label="Modelo Whisper",
        value=cfg.get("last_whisper_model", "small"),
        options=[
            ft.dropdown.Option("tiny", "tiny"),
            ft.dropdown.Option("base", "base"),
            ft.dropdown.Option("small", "small"),
            ft.dropdown.Option("medium", "medium"),
            ft.dropdown.Option("large-v3-turbo", "large-v3-turbo"),
            ft.dropdown.Option("large-v3", "large-v3"),
        ],
        expand=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------
    language_dropdown = ft.Dropdown(
        label="Idioma",
        value=cfg.get("last_language", "auto"),
        options=[
            ft.dropdown.Option("auto", "auto (detectar)"),
            ft.dropdown.Option("pt", "pt — Português"),
            ft.dropdown.Option("en", "en — English"),
            ft.dropdown.Option("es", "es — Español"),
            ft.dropdown.Option("fr", "fr — Français"),
            ft.dropdown.Option("de", "de — Deutsch"),
            ft.dropdown.Option("ja", "ja — 日本語"),
            ft.dropdown.Option("zh", "zh — 中文"),
        ],
        expand=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    # ------------------------------------------------------------------
    # Beam size
    # ------------------------------------------------------------------
    beam_label = ft.Text(
        f"Beam size: {int(cfg.get('last_beam_size', 1))}",
        size=13,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )

    beam_slider = ft.Slider(
        min=1,
        max=5,
        divisions=4,
        value=float(cfg.get("last_beam_size", 1)),
        label="{value}",
        expand=True,
    )

    def _on_beam_change(e: ft.ControlEvent) -> None:
        beam_label.value = f"Beam size: {int(beam_slider.value)}"
        page.update()

    beam_slider.on_change = _on_beam_change

    # ------------------------------------------------------------------
    # Format section
    # ------------------------------------------------------------------
    format_model_field = ft.TextField(
        label="Modelo de formatação",
        hint_text="phi4mini-custom",
        value=cfg.get("last_format_model", "phi4mini-custom"),
        expand=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    use_format_switch = ft.Switch(
        label="Formatar parágrafos",
        value=cfg.get("last_use_format", False),
    )

    def _on_format_toggle(e: ft.ControlEvent) -> None:
        format_model_field.disabled = not use_format_switch.value
        page.update()

    use_format_switch.on_change = _on_format_toggle
    format_model_field.disabled = not use_format_switch.value

    # ------------------------------------------------------------------
    # Analyze section
    # ------------------------------------------------------------------
    analyzer_model_field = ft.TextField(
        label="Modelo de análise",
        hint_text="gemini-2.5-flash",
        value=cfg.get("last_analyzer_model", "gemini-2.5-flash"),
        expand=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    use_analyze_switch = ft.Switch(
        label="Analisar",
        value=cfg.get("last_use_analyze", False),
    )

    def _on_analyze_toggle(e: ft.ControlEvent) -> None:
        analyzer_model_field.disabled = not use_analyze_switch.value
        page.update()

    use_analyze_switch.on_change = _on_analyze_toggle
    analyzer_model_field.disabled = not use_analyze_switch.value

    # ------------------------------------------------------------------
    # Prompt-ready section
    # ------------------------------------------------------------------
    prompt_model_field = ft.TextField(
        label="Modelo prompt-ready",
        hint_text="qwen7b-custom",
        value=cfg.get("last_prompt_model", "gemini-2.5-flash"),
        expand=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    use_prompt_switch = ft.Switch(
        label="Gerar prompt-ready",
        value=cfg.get("last_use_prompt", False),
    )

    def _on_prompt_toggle(e: ft.ControlEvent) -> None:
        prompt_model_field.disabled = not use_prompt_switch.value
        page.update()

    use_prompt_switch.on_change = _on_prompt_toggle
    prompt_model_field.disabled = not use_prompt_switch.value

    # ------------------------------------------------------------------
    # Google API Key
    # ------------------------------------------------------------------
    api_key_field = ft.TextField(
        label="Google API Key",
        hint_text="AIza...",
        value=_read_api_key(),
        password=True,
        can_reveal_password=True,
        expand=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def _on_api_key_blur(e: ft.ControlEvent) -> None:
        _write_api_key(api_key_field.value or "")

    api_key_field.on_blur = _on_api_key_blur

    # ------------------------------------------------------------------
    # Start button
    # ------------------------------------------------------------------
    start_btn = ft.FilledButton(
        "Iniciar",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        disabled=True,
    )

    def _on_start_click(e: ft.ControlEvent) -> None:
        url = (url_field.value or "").strip()
        if not url or not _validate_url(url):
            return

        args = PipelineArgs(
            url=url,
            whisper_model=whisper_dropdown.value or "small",
            language=language_dropdown.value or "auto",
            beam_size=int(beam_slider.value),
            use_format=use_format_switch.value,
            format_model=(format_model_field.value or "phi4mini-custom").strip(),
            use_analyze=use_analyze_switch.value,
            analyzer_model=(analyzer_model_field.value or "gemini-2.5-flash").strip(),
            use_prompt=use_prompt_switch.value,
            prompt_model=(prompt_model_field.value or "qwen7b-custom").strip(),
        )

        settings.save({
            "last_whisper_model": args.whisper_model,
            "last_language": args.language,
            "last_beam_size": args.beam_size,
            "last_format_model": args.format_model,
            "last_analyzer_model": args.analyzer_model,
            "last_prompt_model": args.prompt_model,
            "last_use_format": args.use_format,
            "last_use_analyze": args.use_analyze,
            "last_use_prompt": args.use_prompt,
            "theme_mode": cfg.get("theme_mode", "dark"),
        })

        on_start(args)

    start_btn.on_click = _on_start_click

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _section_label(text: str) -> ft.Text:
        return ft.Text(
            text,
            size=13,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

    def _divider() -> ft.Divider:
        return ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT)

    # ------------------------------------------------------------------
    # Root control
    # ------------------------------------------------------------------
    return ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=0,
        controls=[
            ft.Container(
                padding=20,
                content=ft.Column(
                    spacing=16,
                    controls=[
                        # --- URL ---
                        _section_label("Vídeo"),
                        ft.Row(
                            controls=[url_field],
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        url_error,

                        _divider(),

                        # --- Transcrição ---
                        _section_label("Transcrição"),
                        ft.Row(
                            controls=[whisper_dropdown, language_dropdown],
                            spacing=12,
                        ),
                        ft.Column(
                            spacing=4,
                            controls=[
                                beam_label,
                                ft.Row(controls=[beam_slider]),
                            ],
                        ),

                        _divider(),

                        # --- Formatação ---
                        _section_label("Formatação de parágrafos"),
                        use_format_switch,
                        ft.Row(controls=[format_model_field]),

                        _divider(),

                        # --- Análise ---
                        _section_label("Análise estruturada"),
                        use_analyze_switch,
                        ft.Row(controls=[analyzer_model_field]),

                        _divider(),

                        # --- Prompt-ready ---
                        _section_label("Condensação prompt-ready"),
                        use_prompt_switch,
                        ft.Row(controls=[prompt_model_field]),

                        _divider(),

                        # --- API Key ---
                        _section_label("Credenciais"),
                        ft.Row(controls=[api_key_field]),
                        ft.Text(
                            "Necessária apenas para modelos Gemini. Salva automaticamente no .env.",
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            italic=True,
                        ),

                        _divider(),

                        # --- Botão ---
                        ft.Row(
                            controls=[start_btn],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                ),
            ),
        ],
    )
