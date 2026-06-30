"""Reprodutor de áudio — play/pause/seek/skip/loop/volume via sounddevice + ffmpeg."""

from __future__ import annotations

import io
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft
import numpy as np

from src.gui.theme.tokens import Color, Radius, Space, Type

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_SAMPLERATE = 44100
_CHANNELS = 2
_DTYPE = "float32"
_UI_INTERVAL = 0.2  # segundos entre atualizações de UI durante reprodução
_WF_W = 600  # largura do waveform em pixels (resolução interna da imagem PNG)
_WF_H = 120  # altura do waveform em pixels
_WF_SR_FAST = 500  # Hz do decode rápido (mono) — suficiente para 600px (≥50 amostras/pixel em 1 min)

# Color.dark.primary = #F4A63C convertido para RGBA
_WF_PLAYED = (244, 166, 60, 210)
_WF_UNPLAYED = (80, 80, 95, 150)
_WF_CURSOR = (255, 255, 255, 200)

# 1×1 px PNG transparente — src aceita bytes diretamente em Flet 0.85
_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_s(seconds: float) -> str:
    """Formata segundos em mm:ss."""
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _decode_via_ffmpeg(path: str) -> np.ndarray:
    """Decodifica qualquer formato de áudio para float32 PCM via ffmpeg.

    Retorna array (n_samples, 2) a 44100 Hz estéreo — usado para playback.
    """
    cmd = [
        "ffmpeg",
        "-i",
        path,
        "-f",
        "f32le",
        "-ar",
        str(_SAMPLERATE),
        "-ac",
        str(_CHANNELS),
        "pipe:1",
        "-loglevel",
        "quiet",
    ]
    result = subprocess.run(cmd, capture_output=True)
    raw = result.stdout
    if not raw:
        raise RuntimeError(f"ffmpeg returned no output for: {path}")
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, _CHANNELS)


def _decode_waveform_fast(path: str) -> np.ndarray:
    """Decodifica a 8 kHz mono para geração rápida do waveform.

    Aproximadamente 10x mais rápido que o decode completo.
    Retorna array (n_samples, 1) — não usado para playback.
    """
    cmd = [
        "ffmpeg",
        "-i",
        path,
        "-f",
        "f32le",
        "-ar",
        str(_WF_SR_FAST),
        "-ac",
        "1",
        "pipe:1",
        "-loglevel",
        "quiet",
    ]
    result = subprocess.run(cmd, capture_output=True)
    raw = result.stdout
    if not raw:
        raise RuntimeError(f"ffmpeg returned no waveform output for: {path}")
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 1)


def _compute_waveform(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pré-computa os arrays RGBA played/unplayed para o waveform.

    Retorna (played_arr, unplayed_arr) com shape (_WF_H, _WF_W, 4).
    Aceita dados mono (n, 1) ou estéreo (n, 2) — usa mean(axis=1).
    Ambos são calculados uma vez no carregamento e reutilizados em cada tick.
    """
    W, H = _WF_W, _WF_H
    played = np.zeros((H, W, 4), dtype=np.uint8)
    unplayed = np.zeros((H, W, 4), dtype=np.uint8)

    n = len(data)
    if n == 0:
        return played, unplayed

    mono = np.abs(data.mean(axis=1))
    chunk = max(1, n // W)
    n_chunks = min(W, n // chunk)
    if n_chunks == 0:
        return played, unplayed

    sliced = mono[: n_chunks * chunk].reshape(n_chunks, chunk)
    amps = sliced.max(axis=1)
    peak = amps.max()
    if peak > 0:
        amps = amps / peak

    cy = H // 2
    for x in range(n_chunks):
        h = max(2, int(amps[x] * (cy - 2)))
        y0, y1 = cy - h, cy + h
        played[y0:y1, x] = _WF_PLAYED
        unplayed[y0:y1, x] = _WF_UNPLAYED

    return played, unplayed


def _encode_png(arr: np.ndarray) -> bytes:
    """Codifica array RGBA como PNG sem compressão (rápido — ~1ms para _WF_W×_WF_H)."""
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, "PNG", compress_level=0)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Motor de reprodução
# ---------------------------------------------------------------------------


class _AudioEngine:
    """Motor de playback baseado em sounddevice.

    Volume e mute são aplicados no callback do PortAudio (escala o buffer PCM).
    Thread-safe para as operações essenciais via GIL do CPython.
    """

    def __init__(self) -> None:
        self._data: np.ndarray | None = None
        self._sr: int = _SAMPLERATE
        self._frame: int = 0
        self._stream = None
        self._volume: float = 1.0
        self._muted: bool = False
        self.loop: bool = False
        self.state: str = "stopped"  # stopped | loading | playing | paused
        self.on_complete: Callable | None = None

    # ------------------------------------------------------------------
    # Propriedades de consulta
    # ------------------------------------------------------------------

    @property
    def duration_s(self) -> float:
        """Duração total em segundos."""
        return len(self._data) / self._sr if self._data is not None else 0.0

    @property
    def position_s(self) -> float:
        """Posição atual em segundos."""
        return self._frame / self._sr if self._data is not None else 0.0

    @property
    def effective_volume(self) -> float:
        """Volume efetivo considerando mute."""
        return 0.0 if self._muted else self._volume

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load(self, path: str, on_loaded: Callable | None = None) -> None:
        """Carrega arquivo em thread de background; chama on_loaded() ao terminar."""
        self.stop()
        self.state = "loading"

        def _worker() -> None:
            try:
                data = _decode_via_ffmpeg(path)
                self._data = data
                self._sr = _SAMPLERATE
                self._frame = 0
                self.state = "stopped"
            except Exception:
                self.state = "stopped"
            finally:
                if on_loaded:
                    on_loaded()

        threading.Thread(target=_worker, daemon=True).start()

    def toggle(self) -> None:
        """Alterna play/pause."""
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
        """Pausa a reprodução."""
        if self._stream:
            self._stream.stop()
        self.state = "paused"

    def resume(self) -> None:
        """Retoma a reprodução de onde parou."""
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
        self._frame = int(max(0, min(seconds * self._sr, len(self._data) - 1)))
        if was_playing:
            self._open_stream()

    def skip(self, delta_s: float) -> None:
        """Avança/retrocede delta_s segundos a partir da posição atual."""
        self.seek(self.position_s + delta_s)

    def stop(self) -> None:
        """Para e reseta a reprodução."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._frame = 0
        self.state = "stopped"

    def set_volume(self, vol: float) -> None:
        """Define volume 0.0–1.0."""
        self._volume = max(0.0, min(1.0, vol))

    def toggle_mute(self) -> None:
        """Alterna mudo."""
        self._muted = not self._muted

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _open_stream(self) -> None:
        import sounddevice as sd  # importação lazy — dep declarada mas não carregada no import

        if self._stream:
            self._stream.stop()
            self._stream.close()

        engine = self

        def _callback(outdata: np.ndarray, frames: int, _t, _s) -> None:
            start = engine._frame
            end = min(start + frames, len(engine._data))
            actual = end - start

            if actual <= 0:
                outdata[:] = 0
                engine.state = "stopped"
                if engine.on_complete:
                    engine.on_complete()
                raise sd.CallbackStop()

            chunk = engine._data[start:end]
            vol = engine.effective_volume
            outdata[:actual] = chunk * vol if vol != 1.0 else chunk
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
    """Reprodutor de áudio com controle visual play/pause/seek/skip/loop/volume.

    Atributos:
        control: Widget Flet a inserir no layout. Sempre visível — exibe
                 placeholder até o primeiro load().
        load: Função que recebe caminho de arquivo e inicia o carregamento.
    """

    control: ft.Control
    load: Callable[[str], None]


def build_audio_player(page: ft.Page) -> AudioPlayer:
    """Constrói o reprodutor de áudio.

    Features:
        - Waveform estático com cursor de posição (PIL + numpy, 1 redesenho/tick)
        - Play/pause, skip ±10s, loop, volume + mute
        - Seek por clique no waveform (GestureDetector.on_tap_down → local_x)
        - Decode rápido (8 kHz mono) para waveform em paralelo com decode completo para playback
          — waveform aparece antes dos controles serem habilitados
        - gapless_playback=True no ft.Image elimina flickering durante atualizações do cursor

    Args:
        page: Página Flet (usada em page.update() nos callbacks de UI).
    """
    engine = _AudioEngine()
    _timer_running: list[bool] = [False]
    _wf_played: list[np.ndarray | None] = [None]
    _wf_unplayed: list[np.ndarray | None] = [None]
    _load_generation: list[int] = [0]  # descarta waveform de carga anterior

    # ------------------------------------------------------------------
    # Widgets de informação
    # ------------------------------------------------------------------

    file_label = ft.Text(
        "",
        size=Type.label.size,
        weight=ft.FontWeight.W_500,
        color=ft.Colors.ON_SURFACE,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        expand=True,
    )

    info_label = ft.Text(
        "",
        size=12,
        color=ft.Colors.ON_SURFACE_VARIANT,
        font_family=Type.FONT_MONO,
        no_wrap=True,
    )

    time_label = ft.Text(
        "0:00 / 0:00",
        size=Type.mono.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        font_family=Type.FONT_MONO,
    )

    loading_ring = ft.ProgressRing(
        width=14,
        height=14,
        stroke_width=2,
        color=ft.Colors.PRIMARY,
        visible=False,
    )

    # ------------------------------------------------------------------
    # Waveform
    # ------------------------------------------------------------------

    # src aceita Union[str, bytes] em Flet 0.85 — bytes PNG diretos sem conversão
    # gapless_playback=True mantém o frame anterior visível durante a troca — sem flickering
    waveform_img = ft.Image(
        src=_BLANK_PNG,
        fit=ft.BoxFit.FILL,
        expand=True,
        gapless_playback=True,
    )

    waveform_gd = ft.GestureDetector(
        content=waveform_img,
        on_tap_down=None,  # atribuído abaixo após definir o handler
        expand=True,
    )

    waveform_ctr = ft.Container(
        content=waveform_gd,
        height=_WF_H,
        border_radius=4,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    # ------------------------------------------------------------------
    # Botões de transporte
    # ------------------------------------------------------------------

    play_btn = ft.IconButton(
        icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
        selected_icon=ft.Icons.PAUSE_CIRCLE_OUTLINE,
        selected=False,
        icon_size=38,
        icon_color=ft.Colors.PRIMARY,
        tooltip="Reproduzir",
        padding=ft.Padding(left=0, right=6, top=0, bottom=0),
        disabled=True,
    )

    skip_back_btn = ft.IconButton(
        icon=ft.Icons.REPLAY_10,
        icon_size=26,
        icon_color=ft.Colors.ON_SURFACE_VARIANT,
        tooltip="Voltar 10s",
        disabled=True,
    )

    skip_fwd_btn = ft.IconButton(
        icon=ft.Icons.FORWARD_10,
        icon_size=26,
        icon_color=ft.Colors.ON_SURFACE_VARIANT,
        tooltip="Avançar 10s",
        disabled=True,
    )

    loop_btn = ft.IconButton(
        icon=ft.Icons.REPEAT,
        selected_icon=ft.Icons.REPEAT,
        selected=False,
        icon_size=22,
        style=ft.ButtonStyle(
            color={"selected": ft.Colors.PRIMARY, "": ft.Colors.ON_SURFACE_VARIANT},
        ),
        tooltip="Repetir",
    )

    # ------------------------------------------------------------------
    # Controle de volume
    # ------------------------------------------------------------------

    mute_btn = ft.IconButton(
        icon=ft.Icons.VOLUME_UP,
        selected_icon=ft.Icons.VOLUME_OFF,
        selected=False,
        icon_size=22,
        style=ft.ButtonStyle(
            color={
                "selected": ft.Colors.ON_SURFACE_VARIANT,
                "": ft.Colors.ON_SURFACE_VARIANT,
            },
        ),
        tooltip="Mudo",
    )

    vol_slider = ft.Slider(
        min=0.0,
        max=1.0,
        value=1.0,
        width=110,
        height=24,
        active_color=ft.Colors.PRIMARY,
        inactive_color=ft.Colors.OUTLINE_VARIANT,
        thumb_color=ft.Colors.PRIMARY,
    )

    # ------------------------------------------------------------------
    # Placeholder (visível antes do primeiro load)
    # ------------------------------------------------------------------

    # Altura espelhando o conteúdo do player: header(30) + wf(120) + time(22) + controls(52) + spacing(18) + padding(24) ≈ 266
    _PLAYER_H = 270

    placeholder_ctr = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.AUDIO_FILE_OUTLINED,
                    size=36,
                    color=ft.Colors.OUTLINE_VARIANT,
                ),
                ft.Text(
                    "Aguardando arquivo de áudio...",
                    size=Type.input.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        ),
        height=_PLAYER_H,
        alignment=ft.Alignment.CENTER,
        visible=True,
    )

    # ------------------------------------------------------------------
    # Painel do player (oculto até load)
    # ------------------------------------------------------------------

    player_inner = ft.Container(
        content=ft.Column(
            controls=[
                # Linha 1: ícone + nome do arquivo + loading ring + info
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.AUDIO_FILE_OUTLINED,
                            size=14,
                            color=ft.Colors.PRIMARY,
                        ),
                        file_label,
                        loading_ring,
                        info_label,
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                # Waveform clicável
                waveform_ctr,
                # Posição
                ft.Row(
                    controls=[time_label],
                    alignment=ft.MainAxisAlignment.END,
                ),
                # Controles: transport à esquerda, volume à direita
                ft.Row(
                    controls=[
                        skip_back_btn,
                        play_btn,
                        skip_fwd_btn,
                        loop_btn,
                        ft.Container(expand=True),
                        mute_btn,
                        vol_slider,
                    ],
                    spacing=Space.xxs,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=6,
        ),
        visible=False,
    )

    # ------------------------------------------------------------------
    # Container raiz — sempre visível
    # ------------------------------------------------------------------

    root = ft.Container(
        content=ft.Column(
            controls=[placeholder_ctr, player_inner],
            spacing=0,
        ),
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        ),
        border_radius=Radius.sm,
        bgcolor=Color.dark.surface_variant,
        padding=ft.Padding(left=10, right=14, top=8, bottom=8),
    )

    # ------------------------------------------------------------------
    # Waveform render (chamado no polling thread — ~1ms por frame)
    # ------------------------------------------------------------------

    def _render_wf(pos_s: float) -> bytes:
        """Gera PNG do waveform com cursor na posição pos_s."""
        if _wf_played[0] is None:
            return _BLANK_PNG
        W = _WF_W
        dur = engine.duration_s
        cx = min(int(pos_s / dur * W), W - 1) if dur > 0 else 0

        img = _wf_unplayed[0].copy()
        if cx > 0:
            img[:, :cx] = _wf_played[0][:, :cx]
        if 0 <= cx < W:
            img[:, cx] = _WF_CURSOR

        return _encode_png(img)

    # ------------------------------------------------------------------
    # Atualização periódica de posição
    # ------------------------------------------------------------------

    def _update_display() -> None:
        """Atualiza ícone play/pause, label de tempo e waveform."""
        pos = engine.position_s
        dur = engine.duration_s
        state = engine.state

        play_btn.selected = state == "playing"
        play_btn.tooltip = "Pausar" if state == "playing" else "Reproduzir"
        time_label.value = f"{_fmt_s(pos)} / {_fmt_s(dur)}"

        # Waveform isolado em try/except — exceção aqui não mata o polling
        if _wf_played[0] is not None:
            try:
                waveform_img.src = _render_wf(pos)
            except Exception:
                pass

        try:
            page.update()
        except Exception:
            pass

    def _start_polling() -> None:
        if _timer_running[0]:
            return
        _timer_running[0] = True

        def _poll() -> None:
            # try/finally garante reset de _timer_running mesmo com exceção inesperada,
            # evitando que o guard impeça novos pollings após falha
            try:
                while _timer_running[0]:
                    state = engine.state
                    _update_display()
                    if state not in ("playing", "loading"):
                        break
                    time.sleep(_UI_INTERVAL)
            finally:
                _timer_running[0] = False

        threading.Thread(target=_poll, daemon=True).start()

    def _stop_polling() -> None:
        _timer_running[0] = False

    # ------------------------------------------------------------------
    # Handlers de interação
    # ------------------------------------------------------------------

    def _on_play_click(_e) -> None:
        if engine.state == "loading":
            return
        engine.toggle()
        if engine.state == "playing":
            _start_polling()
        _update_display()

    def _on_skip_back(_e) -> None:
        engine.skip(-10.0)
        if engine.state == "playing":
            _start_polling()
        _update_display()

    def _on_skip_fwd(_e) -> None:
        engine.skip(10.0)
        if engine.state == "playing":
            _start_polling()
        _update_display()

    def _on_loop_click(_e) -> None:
        engine.loop = not engine.loop
        loop_btn.selected = engine.loop
        page.update()

    def _on_mute_click(_e) -> None:
        engine.toggle_mute()
        mute_btn.selected = engine._muted
        page.update()

    def _on_vol_change(_e) -> None:
        engine.set_volume(vol_slider.value)
        if engine._muted:
            engine._muted = False
            mute_btn.selected = False
            page.update()

    def _on_waveform_tap(e) -> None:
        """Seek por clique no waveform; local_x fornecido pelo GestureDetector."""
        if engine.state == "loading" or engine._data is None:
            return
        w = waveform_gd.width
        if not (w and w > 0 and engine.duration_s > 0):
            return
        frac = max(0.0, min(1.0, e.local_x / w))
        engine.seek(frac * engine.duration_s)
        if engine.state == "playing":
            _start_polling()
        _update_display()

    def _on_complete() -> None:
        """Chamado pelo engine ao fim da reprodução — trata loop e reset de UI."""
        if engine.loop and engine._data is not None:
            # Reinicia em nova thread para não bloquear o callback do PortAudio
            def _restart() -> None:
                engine.play()
                _start_polling()

            threading.Thread(target=_restart, daemon=True).start()
        else:
            _stop_polling()
            try:
                waveform_img.src = _render_wf(0.0)
            except Exception:
                pass
            time_label.value = f"0:00 / {_fmt_s(engine.duration_s)}"
            play_btn.selected = False
            play_btn.tooltip = "Reproduzir"
            try:
                page.update()
            except Exception:
                pass

    play_btn.on_click = _on_play_click
    skip_back_btn.on_click = _on_skip_back
    skip_fwd_btn.on_click = _on_skip_fwd
    loop_btn.on_click = _on_loop_click
    mute_btn.on_click = _on_mute_click
    vol_slider.on_change = _on_vol_change
    waveform_gd.on_tap_down = _on_waveform_tap
    engine.on_complete = _on_complete

    # ------------------------------------------------------------------
    # Função pública de carga
    # ------------------------------------------------------------------

    def _load(path: str) -> None:
        """Carrega arquivo de áudio, calcula waveform e exibe o player.

        Lança duas threads paralelas:
          - waveform: decode rápido 8 kHz mono → waveform aparece logo (ring ainda visível)
          - playback: decode completo 44100 Hz estéreo → habilita controles ao terminar
        """
        _stop_polling()
        _load_generation[0] += 1
        gen = _load_generation[0]
        p = Path(path)

        # Reset de UI para estado loading
        file_label.value = p.name
        info_label.value = ""
        time_label.value = "0:00 / 0:00"
        play_btn.selected = False
        play_btn.disabled = True
        skip_back_btn.disabled = True
        skip_fwd_btn.disabled = True
        loading_ring.visible = True
        waveform_img.src = _BLANK_PNG
        _wf_played[0] = None
        _wf_unplayed[0] = None

        # Transição placeholder → player
        placeholder_ctr.visible = False
        player_inner.visible = True

        try:
            page.update()
        except Exception:
            pass

        def _load_waveform() -> None:
            """Decode rápido 8 kHz mono → waveform visível antes do decode completo."""
            try:
                wf_data = _decode_waveform_fast(str(p))
                if _load_generation[0] != gen:
                    return
                played, unplayed = _compute_waveform(wf_data)
                if _load_generation[0] != gen:
                    return
                _wf_played[0] = played
                _wf_unplayed[0] = unplayed
                waveform_img.src = _render_wf(0.0)
                try:
                    page.update()
                except Exception:
                    pass
            except Exception:
                pass

        def _on_loaded() -> None:
            """Chamado quando o decode completo (44100 Hz estéreo) termina."""
            if _load_generation[0] != gen:
                return
            dur = engine.duration_s
            sr_str = f"{_SAMPLERATE // 1000}.{(_SAMPLERATE % 1000) // 100}kHz"
            info_label.value = f"{_fmt_s(dur)} · {sr_str} · Stereo"
            play_btn.disabled = False
            skip_back_btn.disabled = False
            skip_fwd_btn.disabled = False
            loading_ring.visible = False
            try:
                page.update()
            except Exception:
                pass

        # Waveform rápido em paralelo com o decode completo para playback
        threading.Thread(target=_load_waveform, daemon=True).start()
        engine.load(str(p), on_loaded=_on_loaded)

    return AudioPlayer(control=root, load=_load)
