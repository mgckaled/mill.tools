"""Reprodutor de áudio simples — play/pause/seek via sounddevice + ffmpeg."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft
import numpy as np

from src.gui.theme.tokens import Color, Type

# ---------------------------------------------------------------------------
# Constantes de decodificação
# ---------------------------------------------------------------------------

_SAMPLERATE = 44100
_CHANNELS = 2
_DTYPE = "float32"
_UI_INTERVAL = 0.2  # segundos entre atualizações de posição na UI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_s(seconds: float) -> str:
    """Formata segundos em mm:ss."""
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _decode_via_ffmpeg(path: str) -> np.ndarray:
    """Decodifica qualquer formato de áudio para float32 PCM via ffmpeg.

    Retorna array (n_samples, 2) a 44100 Hz estéreo.
    Usa ffmpeg que já é dependência do projeto.
    """
    cmd = [
        "ffmpeg",
        "-i", path,
        "-f", "f32le",
        "-ar", str(_SAMPLERATE),
        "-ac", str(_CHANNELS),
        "pipe:1",
        "-loglevel", "quiet",
    ]
    result = subprocess.run(cmd, capture_output=True)
    raw = result.stdout
    if not raw:
        raise RuntimeError(f"ffmpeg não produziu saída para: {path}")
    data = np.frombuffer(raw, dtype=np.float32).reshape(-1, _CHANNELS)
    return data


# ---------------------------------------------------------------------------
# Motor de reprodução
# ---------------------------------------------------------------------------

class _AudioEngine:
    """Motor de playback baseado em sounddevice.

    Thread-safe para as operações essenciais (play/pause/seek).
    A posição (_frame) é lida/escrita atomicamente via GIL do CPython.
    """

    def __init__(self) -> None:
        self._data: np.ndarray | None = None
        self._sr: int = _SAMPLERATE
        self._frame: int = 0
        self._stream = None          # sd.OutputStream
        self.state: str = "stopped"  # stopped | loading | playing | paused
        self.on_complete: Callable | None = None

    # ------------------------------------------------------------------
    # Propriedades de consulta
    # ------------------------------------------------------------------

    @property
    def duration_s(self) -> float:
        if self._data is None:
            return 0.0
        return len(self._data) / self._sr

    @property
    def position_s(self) -> float:
        if self._data is None:
            return 0.0
        return self._frame / self._sr

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load(self, path: str, on_loaded: Callable | None = None) -> None:
        """Carrega arquivo em thread de background. Chama on_loaded() ao terminar."""
        self.stop()
        self.state = "loading"

        def _worker() -> None:
            try:
                data = _decode_via_ffmpeg(path)
                self._data = data
                self._sr = _SAMPLERATE
                self._frame = 0
                self.state = "stopped"
            except Exception as exc:
                self.state = "stopped"
                raise exc
            finally:
                if on_loaded:
                    on_loaded()

        threading.Thread(target=_worker, daemon=True).start()

    def toggle(self) -> None:
        if self.state == "playing":
            self.pause()
        elif self.state == "paused":
            self.resume()
        elif self.state == "stopped" and self._data is not None:
            self.play()

    def play(self) -> None:
        """Inicia reprodução do início."""
        if self._data is None:
            return
        self._frame = 0
        self._open_stream()
        self.state = "playing"

    def pause(self) -> None:
        if self._stream:
            self._stream.stop()
        self.state = "paused"

    def resume(self) -> None:
        if self._data is None:
            return
        self._open_stream()
        self.state = "playing"

    def seek(self, seconds: float) -> None:
        """Salta para posição em segundos."""
        if self._data is None:
            return
        was_playing = self.state == "playing"
        if self._stream:
            self._stream.stop()
        self._frame = int(
            max(0, min(seconds * self._sr, len(self._data) - 1))
        )
        if was_playing:
            self._open_stream()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._frame = 0
        self.state = "stopped"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _open_stream(self) -> None:
        import sounddevice as sd  # importação lazy — dep opcional

        if self._stream:
            self._stream.stop()
            self._stream.close()

        engine = self

        def _callback(
            outdata: np.ndarray,
            frames: int,
            _time_info,
            _status,
        ) -> None:
            start = engine._frame
            end = min(start + frames, len(engine._data))
            actual = end - start

            if actual <= 0:
                outdata[:] = 0
                engine.state = "stopped"
                if engine.on_complete:
                    engine.on_complete()
                raise sd.CallbackStop()

            outdata[:actual] = engine._data[start:end]
            engine._frame = end

            if actual < frames:
                outdata[actual:] = 0
                engine.state = "stopped"
                if engine.on_complete:
                    engine.on_complete()
                raise sd.CallbackStop()

        self._stream = sd.OutputStream(
            samplerate=self._sr,
            channels=_CHANNELS,
            dtype=_DTYPE,
            callback=_callback,
        )
        self._stream.start()


# ---------------------------------------------------------------------------
# Componente de UI
# ---------------------------------------------------------------------------

@dataclass
class AudioPlayer:
    """Reprodutor de áudio com controle visual (play/pause/seek).

    Atributos:
        control: Widget Flet a inserir no layout (inicialmente invisible).
        load: Função que recebe um caminho de arquivo e carrega o áudio.
    """
    control: ft.Control
    load: Callable[[str], None]


def build_audio_player(page: ft.Page) -> AudioPlayer:
    """Constrói o reprodutor de áudio.

    O controle começa com visible=False e torna-se visível após o primeiro load().
    A decodificação ocorre em thread de background via ffmpeg; um indicador de
    carregamento é exibido enquanto decoding está em andamento.

    Args:
        page: Página Flet (usada para page.update() nas atualizações de posição).
    """
    engine = _AudioEngine()
    _timer_running: list[bool] = [False]

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------

    file_label = ft.Text(
        "",
        size=12,
        weight=ft.FontWeight.W_500,
        color=ft.Colors.ON_SURFACE,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        expand=True,
    )

    time_label = ft.Text(
        "0:00 / 0:00",
        size=11,
        color=ft.Colors.ON_SURFACE_VARIANT,
        font_family=Type.FONT_MONO,
    )

    play_btn = ft.IconButton(
        icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
        icon_size=26,
        icon_color=ft.Colors.PRIMARY,
        tooltip="Reproduzir",
        padding=ft.Padding(left=0, right=2, top=0, bottom=0),
    )

    seek_slider = ft.Slider(
        min=0.0,
        max=1.0,
        value=0.0,
        expand=True,
        height=20,
        active_color=ft.Colors.PRIMARY,
        inactive_color=ft.Colors.OUTLINE_VARIANT,
        thumb_color=ft.Colors.PRIMARY,
    )

    loading_ring = ft.ProgressRing(
        width=16,
        height=16,
        stroke_width=2,
        color=ft.Colors.PRIMARY,
        visible=False,
    )

    # ------------------------------------------------------------------
    # Container raiz (invisível até o primeiro load)
    # ------------------------------------------------------------------

    container = ft.Container(
        visible=False,
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        ),
        border_radius=6,
        bgcolor=Color.dark.surface_variant,
        padding=ft.Padding(left=8, right=12, top=6, bottom=4),
        margin=ft.Margin(top=0, bottom=0, left=0, right=0),
        content=ft.Column(
            spacing=0,
            controls=[
                # Linha 1: ícone + nome do arquivo + loading ring + tempo
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.AUDIO_FILE_OUTLINED,
                            size=13,
                            color=ft.Colors.PRIMARY,
                        ),
                        file_label,
                        loading_ring,
                        time_label,
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                # Linha 2: botão play/pause + seek slider
                ft.Row(
                    controls=[
                        play_btn,
                        seek_slider,
                    ],
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
        ),
    )

    # ------------------------------------------------------------------
    # Atualização periódica de posição (thread de polling)
    # ------------------------------------------------------------------

    def _update_display() -> None:
        """Atualiza slider e tempo enquanto reproduzindo."""
        dur = engine.duration_s
        pos = engine.position_s
        state = engine.state

        # Atualiza ícone do botão
        if state == "playing":
            play_btn.icon = ft.Icons.PAUSE_CIRCLE_OUTLINE
            play_btn.tooltip = "Pausar"
        elif state == "loading":
            play_btn.icon = ft.Icons.PLAY_CIRCLE_OUTLINE
            play_btn.tooltip = "Reproduzir"
        else:
            play_btn.icon = ft.Icons.PLAY_CIRCLE_OUTLINE
            play_btn.tooltip = "Reproduzir"

        # Atualiza slider (somente se não estiver no evento on_change)
        if dur > 0:
            seek_slider.value = min(pos / dur, 1.0)

        # Atualiza label de tempo
        time_label.value = f"{_fmt_s(pos)} / {_fmt_s(dur)}"

        try:
            page.update()
        except Exception:
            pass

    def _start_polling() -> None:
        if _timer_running[0]:
            return
        _timer_running[0] = True

        def _poll() -> None:
            while _timer_running[0]:
                state = engine.state
                _update_display()
                if state not in ("playing", "loading"):
                    _timer_running[0] = False
                    break
                time.sleep(_UI_INTERVAL)

        threading.Thread(target=_poll, daemon=True).start()

    def _stop_polling() -> None:
        _timer_running[0] = False

    # ------------------------------------------------------------------
    # Handlers de interação
    # ------------------------------------------------------------------

    def _on_play_click(_e) -> None:
        state = engine.state
        if state == "loading":
            return
        engine.toggle()
        if engine.state == "playing":
            _start_polling()
        _update_display()

    def _on_seek_change_end(e) -> None:
        """Seek ao soltar o slider."""
        dur = engine.duration_s
        if dur > 0:
            engine.seek(seek_slider.value * dur)
        if engine.state == "playing":
            _start_polling()

    def _on_complete() -> None:
        """Chamado pelo engine quando a reprodução termina."""
        _stop_polling()
        seek_slider.value = 0.0
        time_label.value = f"0:00 / {_fmt_s(engine.duration_s)}"
        play_btn.icon = ft.Icons.PLAY_CIRCLE_OUTLINE
        play_btn.tooltip = "Reproduzir"
        try:
            page.update()
        except Exception:
            pass

    play_btn.on_click = _on_play_click
    seek_slider.on_change_end = _on_seek_change_end
    engine.on_complete = _on_complete

    # ------------------------------------------------------------------
    # Função pública de carga
    # ------------------------------------------------------------------

    def _load(path: str) -> None:
        """Carrega um arquivo de áudio e exibe o player."""
        _stop_polling()
        p = Path(path)

        # Resetar UI para estado de carregamento
        file_label.value = p.name
        time_label.value = "0:00 / 0:00"
        seek_slider.value = 0.0
        play_btn.icon = ft.Icons.PLAY_CIRCLE_OUTLINE
        play_btn.tooltip = "Reproduzir"
        play_btn.disabled = True
        loading_ring.visible = True
        container.visible = True

        try:
            page.update()
        except Exception:
            pass

        def _on_loaded() -> None:
            play_btn.disabled = False
            loading_ring.visible = False
            dur = engine.duration_s
            time_label.value = f"0:00 / {_fmt_s(dur)}"
            try:
                page.update()
            except Exception:
                pass

        engine.load(path, on_loaded=_on_loaded)

    return AudioPlayer(control=container, load=_load)
