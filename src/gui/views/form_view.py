"""View de formulário do yt-transcriber GUI.

Coleta os parâmetros do pipeline e dispara o worker ao clicar em Iniciar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.audio.converter import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from src.core.io_types import InputItem
from src.gui import settings
from src.gui.components.input_source import build_input_source
from src.gui.theme.components import Cursor, hairline, section, section_label
from src.gui.theme.tokens import Space, Type
from src.gui.workers import PipelineArgs

# Local file types the Transcription module accepts (without leading dot).
# Audio/video are transcribed; .txt/.md skip Whisper and run only the LLM steps.
_TRANSCRIBE_EXTS = sorted(
    {e.lstrip(".") for e in (AUDIO_EXTENSIONS | VIDEO_EXTENSIONS)} | {"txt", "md"}
)
_TEXT_SUFFIXES = {".txt", ".md"}


@dataclass
class FormPanel:
    """Controle do formulário com método de controle de estado de execução."""

    control: ft.Control
    set_running: Callable[[bool], None]
    fill_from_path: Callable[[str], None]


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
    lines = (
        _ENV_FILE.read_text(encoding="utf-8").splitlines() if _ENV_FILE.exists() else []
    )
    key_line = f"GOOGLE_API_KEY={value}"
    updated = [
        key_line if line.startswith("GOOGLE_API_KEY=") else line for line in lines
    ]
    if not any(line.startswith("GOOGLE_API_KEY=") for line in lines):
        updated.append(key_line)
    _ENV_FILE.write_text("\n".join(updated) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------


def build_form_view(
    page: ft.Page, on_start: Callable[[PipelineArgs], None]
) -> FormPanel:
    """Retorna um FormPanel com o controle raiz e método set_running.

    Args:
        page: Página Flet.
        on_start: Callable recebendo PipelineArgs, chamado ao clicar Iniciar.
    """
    cfg = settings.load()

    # ------------------------------------------------------------------
    # Entrada (URL ou arquivo local: áudio / vídeo / texto)
    # ------------------------------------------------------------------

    def _is_text_input(its: list[InputItem]) -> bool:
        """True when the (single) input is a local .txt/.md — skips Whisper."""
        if not its:
            return False
        it = its[0]
        return it.kind == "local" and Path(it.value).suffix.lower() in _TEXT_SUFFIXES

    def _on_items_change(its: list[InputItem]) -> None:
        # Enable Start when there is an input; adapt the form to the input kind:
        # a text file hides the transcription controls (Whisper/beam/subtitles).
        start_btn.disabled = len(its) == 0
        is_text = _is_text_input(its)
        transcribe_section.visible = not is_text
        text_notice.visible = is_text
        page.update()

    input_source = build_input_source(
        page,
        allowed_extensions=_TRANSCRIBE_EXTS,
        on_change=_on_items_change,
        url_hint="URL (YouTube, SoundCloud…) ou selecione um arquivo",
        allow_multiple=False,
    )

    text_notice = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.PRIMARY),
                ft.Text(
                    "Arquivo de texto detectado — a transcrição será pulada; "
                    "escolha as análises abaixo.",
                    size=Type.input.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                    expand=True,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        visible=False,
    )

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
        size=Type.input.size,
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

    reprocess_switch = ft.Switch(
        label="Reprocessar se já existir",
        value=cfg.get("last_reprocess", False),
    )

    # ------------------------------------------------------------------
    # Format section
    # ------------------------------------------------------------------
    format_model_field = ft.Dropdown(
        label="Modelo de formatação",
        value=cfg.get("last_format_model", "phi4mini-custom"),
        options=[
            ft.dropdown.Option("phi4mini-custom", "phi4mini-custom"),
            ft.dropdown.Option("qwen7b-custom", "qwen7b-custom"),
        ],
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
    analyzer_model_field = ft.Dropdown(
        label="Modelo de análise",
        value=cfg.get("last_analyzer_model", "gemini-2.5-flash"),
        options=[
            ft.dropdown.Option("gemini-2.5-flash", "gemini-2.5-flash"),
            ft.dropdown.Option("qwen7b-custom", "qwen7b-custom"),
        ],
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
    prompt_model_field = ft.Dropdown(
        label="Modelo prompt-ready",
        value=cfg.get("last_prompt_model", "gemini-2.5-flash"),
        options=[
            ft.dropdown.Option("gemini-2.5-flash", "gemini-2.5-flash"),
            ft.dropdown.Option("qwen7b-custom", "qwen7b-custom"),
        ],
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
    # Subtitle export (.srt + .vtt)
    # ------------------------------------------------------------------
    export_subtitles_switch = ft.Switch(
        label="Exportar legendas (.srt + .vtt)",
        value=cfg.get("last_export_subtitles", False),
    )

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
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )

    def _on_start_click(e: ft.ControlEvent) -> None:
        items = input_source.get_items()
        if not items:
            return
        # url carries either a remote URL or a local file path; the worker
        # decides what to do by inspecting the path (file vs URL, extension).
        source_value = items[0].value

        args = PipelineArgs(
            url=source_value,
            whisper_model=whisper_dropdown.value or "small",
            language=language_dropdown.value or "auto",
            beam_size=int(beam_slider.value),
            use_format=use_format_switch.value,
            format_model=format_model_field.value or "phi4mini-custom",
            use_analyze=use_analyze_switch.value,
            analyzer_model=analyzer_model_field.value or "gemini-2.5-flash",
            use_prompt=use_prompt_switch.value,
            prompt_model=prompt_model_field.value or "gemini-2.5-flash",
            reprocess=reprocess_switch.value,
            export_subtitles=export_subtitles_switch.value,
        )

        settings.save(
            {
                "last_whisper_model": args.whisper_model,
                "last_language": args.language,
                "last_beam_size": args.beam_size,
                "last_format_model": args.format_model,
                "last_analyzer_model": args.analyzer_model,
                "last_prompt_model": args.prompt_model,
                "last_use_format": args.use_format,
                "last_use_analyze": args.use_analyze,
                "last_use_prompt": args.use_prompt,
                "last_reprocess": args.reprocess,
                "last_export_subtitles": args.export_subtitles,
                "theme_mode": cfg.get("theme_mode", "dark"),
            }
        )

        on_start(args)

    start_btn.on_click = _on_start_click

    def _set_running(running: bool) -> None:
        start_btn.disabled = running
        start_btn.text = "Executando..." if running else "Iniciar"
        start_btn.icon = (
            ft.Icons.HOURGLASS_EMPTY if running else ft.Icons.PLAY_ARROW_ROUNDED
        )
        page.update()

    # ------------------------------------------------------------------
    # Transcription-only controls — hidden when the input is a text file
    # ------------------------------------------------------------------
    transcribe_section = ft.Column(
        spacing=16,
        controls=[
            section(
                "Transcrição",
                help_key="transcription.whisper_model",
                page=page,
            ),
            ft.Row(controls=[whisper_dropdown, language_dropdown], spacing=12),
            ft.Column(
                spacing=4,
                controls=[beam_label, ft.Row(controls=[beam_slider])],
            ),
            reprocess_switch,
            hairline(),
            section("Legendas", help_key="transcription.subtitles", page=page),
            export_subtitles_switch,
            hairline(),
        ],
    )

    # ------------------------------------------------------------------
    # Root control
    # ------------------------------------------------------------------
    root = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
        controls=[
            ft.Container(
                padding=20,
                content=ft.Column(
                    spacing=16,
                    controls=[
                        # --- Entrada ---
                        section_label("Entrada"),
                        input_source.control,
                        text_notice,
                        hairline(),
                        # --- Transcrição + Legendas (ocultas para texto) ---
                        transcribe_section,
                        # --- Formatação ---
                        section(
                            "Formatação de parágrafos",
                            help_key="transcription.format",
                            page=page,
                        ),
                        use_format_switch,
                        ft.Row(controls=[format_model_field]),
                        hairline(),
                        # --- Análise ---
                        section(
                            "Análise estruturada",
                            help_key="transcription.analyze",
                            page=page,
                        ),
                        use_analyze_switch,
                        ft.Row(controls=[analyzer_model_field]),
                        hairline(),
                        # --- Prompt-ready ---
                        section(
                            "Condensação prompt-ready",
                            help_key="transcription.prompt",
                            page=page,
                        ),
                        use_prompt_switch,
                        ft.Row(controls=[prompt_model_field]),
                        hairline(),
                        # --- API Key ---
                        section_label("Credenciais"),
                        ft.Row(controls=[api_key_field]),
                        ft.Text(
                            "Necessária apenas para modelos Gemini. Salva automaticamente no .env.",
                            size=Type.small.size,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            italic=True,
                        ),
                        hairline(),
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

    def _fill_from_path(path: str) -> None:
        """Bridge entry point — add a local file as the (single) input item."""
        input_source.clear()
        input_source.add_item(InputItem(kind="local", value=path))

    return FormPanel(
        control=root,
        set_running=_set_running,
        fill_from_path=_fill_from_path,
    )
