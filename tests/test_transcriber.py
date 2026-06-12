import pytest


# ── format_elapsed ───────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("seconds, expected", [
    (0,      "0s"),
    (5,      "5s"),
    (59,     "59s"),
    (60,     "1m 00s"),
    (90,     "1m 30s"),
    (3600,   "1h 00m 00s"),
    (3661,   "1h 01m 01s"),
    (7384,   "2h 03m 04s"),
])
def test_format_elapsed(seconds, expected):
    from src.transcriber import format_elapsed
    assert format_elapsed(seconds) == expected


# ── _resolve_device ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_resolve_device_cuda_fallback(mocker):
    """Se ctranslate2 lança RuntimeError, deve retornar CPU."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        side_effect=RuntimeError("no CUDA"),
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cpu"
    assert compute == "int8"


@pytest.mark.unit
def test_resolve_device_cuda_int8_float32(mocker):
    """Se int8_float32 disponível em CUDA, deve preferir CUDA."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        return_value=["int8_float32", "float32"],
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cuda"
    assert compute == "int8_float32"


@pytest.mark.unit
def test_resolve_device_cuda_float32_fallback(mocker):
    """Se apenas float32 disponível em CUDA, usa float32."""
    mocker.patch(
        "ctranslate2.get_supported_compute_types",
        return_value=["float32"],
    )
    from src.transcriber import _resolve_device
    device, compute = _resolve_device(4)
    assert device == "cuda"
    assert compute == "float32"


# ── transcribe (via WhisperModel mock) ───────────────────────────────────────

class _Seg:
    """Minimal Segment stand-in matching the faster-whisper API surface used."""
    def __init__(self, start, end, text, avg_logprob=-0.2, no_speech_prob=0.1):
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


class _Info:
    """Minimal TranscriptionInfo stand-in."""
    def __init__(self, language="pt", language_probability=0.99, duration=6.0):
        self.language = language
        self.language_probability = language_probability
        self.duration = duration


_DEFAULT_META = {"title": "Test Video", "duration": 6}


def _patch_whisper(mocker, segments, info=None):
    """Patch WhisperModel + _resolve_device to skip GPU lookup; return the fake_model."""
    fake_model = mocker.MagicMock()
    fake_model.transcribe.return_value = (iter(segments), info or _Info())
    mocker.patch("src.transcriber.WhisperModel", return_value=fake_model)
    mocker.patch("src.transcriber._resolve_device", return_value=("cpu", "int8"))
    return fake_model


def _call_transcribe(tmp_path, **kwargs):
    """Helper that fills required positional args with sensible defaults."""
    from src.transcriber import transcribe
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    output = tmp_path / "out.txt"
    defaults = dict(
        audio_path=audio,
        output_path=output,
        meta=_DEFAULT_META,
        url="https://youtu.be/abc",
        model_size="small",
        language="pt",
        threads=2,
        beam_size=1,
        force_overwrite=True,
    )
    defaults.update(kwargs)
    return transcribe(**defaults)


@pytest.mark.unit
def test_transcribe_writes_header_and_body(tmp_path, mocker):
    _patch_whisper(mocker, [
        _Seg(0.0, 3.0, "olá"),
        _Seg(3.0, 6.0, "mundo"),
    ])
    elapsed = _call_transcribe(tmp_path)
    assert elapsed is not None
    body = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "olá" in body
    assert "mundo" in body
    # Header from format_metadata includes the title
    assert "Test Video" in body


@pytest.mark.unit
def test_transcribe_flags_low_logprob(tmp_path, mocker):
    """avg_logprob < -1.0 dispara o marcador [?]."""
    _patch_whisper(mocker, [
        _Seg(0.0, 3.0, "claro"),
        _Seg(3.0, 6.0, "ruído", avg_logprob=-2.0),
    ])
    _call_transcribe(tmp_path)
    body = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "ruído [?]" in body
    # The clear segment must NOT be flagged
    assert "claro [?]" not in body


@pytest.mark.unit
def test_transcribe_flags_high_no_speech(tmp_path, mocker):
    """no_speech_prob > 0.6 também dispara [?] (segundo ramo)."""
    _patch_whisper(mocker, [
        _Seg(0.0, 3.0, "silêncio", no_speech_prob=0.8),
    ])
    _call_transcribe(tmp_path)
    body = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "silêncio [?]" in body


@pytest.mark.unit
def test_transcribe_emits_lifecycle_events(tmp_path, mocker):
    _patch_whisper(mocker, [_Seg(0.0, 3.0, "a"), _Seg(3.0, 6.0, "b")])
    events: list[tuple[str, str, dict]] = []
    _call_transcribe(tmp_path, on_event=lambda t, s, p: events.append((t, s, p)))
    types = [e[0] for e in events]
    assert "whisper_loading" in types
    assert "whisper_loaded" in types
    assert "transcribe_started" in types
    assert "language_detected" in types
    # Two segments → two transcribe_segment events
    assert types.count("transcribe_segment") == 2
    assert "transcribe_done" in types
    # Stage sempre "transcribe"
    assert all(stage == "transcribe" for _, stage, _ in events)


@pytest.mark.unit
def test_transcribe_done_payload_includes_flagged_count(tmp_path, mocker):
    _patch_whisper(mocker, [
        _Seg(0.0, 3.0, "ok"),
        _Seg(3.0, 6.0, "ruim", avg_logprob=-3.0),
    ])
    events: list[tuple[str, str, dict]] = []
    _call_transcribe(tmp_path, on_event=lambda t, s, p: events.append((t, s, p)))
    done = next(p for t, _, p in events if t == "transcribe_done")
    assert done["flagged_count"] == 1
    assert done["output_path"].endswith("out.txt")


@pytest.mark.unit
def test_transcribe_language_detected_payload(tmp_path, mocker):
    _patch_whisper(
        mocker,
        [_Seg(0.0, 3.0, "hello")],
        info=_Info(language="en", language_probability=0.92, duration=10.5),
    )
    events: list[tuple[str, str, dict]] = []
    _call_transcribe(tmp_path, on_event=lambda t, s, p: events.append((t, s, p)))
    payload = next(p for t, _, p in events if t == "language_detected")
    assert payload["language"] == "en"
    assert payload["confidence"] == pytest.approx(0.92)
    assert payload["audio_duration"] == pytest.approx(10.5)


# ── subtitle_formats integration ─────────────────────────────────────────────

@pytest.mark.unit
def test_transcribe_subtitle_formats_writes_srt_and_vtt(tmp_path, mocker, monkeypatch):
    import src.transcriber as tr
    import src.utils as utils
    sub_dir = tmp_path / "subtitles"
    monkeypatch.setattr(utils, "TRANSCRIPTIONS_SUBTITLES_DIR", sub_dir)

    _patch_whisper(mocker, [
        _Seg(0.0, 3.0, "olá"),
        _Seg(3.0, 6.0, "mundo"),
    ])
    _call_transcribe(tmp_path, subtitle_formats=("srt", "vtt"))

    srt_path = sub_dir / "out.srt"
    vtt_path = sub_dir / "out.vtt"
    assert srt_path.exists() and vtt_path.exists()
    srt = srt_path.read_text(encoding="utf-8")
    assert "1\n00:00:00,000 --> 00:00:03,000\nolá\n" in srt
    vtt = vtt_path.read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:03.000" in vtt


@pytest.mark.unit
def test_transcribe_subtitles_done_event_emitted(tmp_path, mocker, monkeypatch):
    import src.utils as utils
    monkeypatch.setattr(utils, "TRANSCRIPTIONS_SUBTITLES_DIR", tmp_path / "subs")
    _patch_whisper(mocker, [_Seg(0.0, 3.0, "hi")])

    events: list[tuple[str, str, dict]] = []
    _call_transcribe(
        tmp_path,
        subtitle_formats=("srt",),
        on_event=lambda t, s, p: events.append((t, s, p)),
    )
    payload = next(p for t, _, p in events if t == "subtitles_done")
    assert len(payload["paths"]) == 1
    assert payload["paths"][0].endswith(".srt")


@pytest.mark.unit
def test_transcribe_no_subtitle_formats_skips_writes(tmp_path, mocker, monkeypatch):
    import src.utils as utils
    sub_dir = tmp_path / "subs"
    monkeypatch.setattr(utils, "TRANSCRIPTIONS_SUBTITLES_DIR", sub_dir)
    _patch_whisper(mocker, [_Seg(0.0, 3.0, "hi")])

    events: list[tuple[str, str, dict]] = []
    _call_transcribe(
        tmp_path,
        on_event=lambda t, s, p: events.append((t, s, p)),
    )  # subtitle_formats default is ()
    assert not sub_dir.exists()
    assert "subtitles_done" not in [e[0] for e in events]


@pytest.mark.unit
def test_transcribe_subtitle_formats_with_zero_segments_skips_write(tmp_path, mocker, monkeypatch):
    """Quando subtitle_formats != () mas a transcrição não produz segmentos,
    nenhum arquivo é gravado e nenhum evento subtitles_done é emitido."""
    import src.utils as utils
    sub_dir = tmp_path / "subs"
    monkeypatch.setattr(utils, "TRANSCRIPTIONS_SUBTITLES_DIR", sub_dir)
    _patch_whisper(mocker, [])  # zero segments

    events: list[tuple[str, str, dict]] = []
    _call_transcribe(
        tmp_path,
        subtitle_formats=("srt", "vtt"),
        on_event=lambda t, s, p: events.append((t, s, p)),
    )
    assert "subtitles_done" not in [e[0] for e in events]
    assert not sub_dir.exists()


# ── force_overwrite e KeyboardInterrupt ──────────────────────────────────────

@pytest.mark.unit
def test_transcribe_existing_output_skips_when_user_says_no(tmp_path, mocker):
    """force_overwrite=False + arquivo existente + input='n' → retorna None sem chamar Whisper."""
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    out = tmp_path / "out.txt"
    out.write_text("existing", encoding="utf-8")

    mock_whisper = mocker.patch("src.transcriber.WhisperModel")
    mocker.patch("builtins.input", return_value="n")
    from src.transcriber import transcribe
    result = transcribe(
        audio_path=audio, output_path=out, meta=_DEFAULT_META,
        url="https://x", model_size="small", language="pt",
        threads=2, beam_size=1, force_overwrite=False,
    )
    assert result is None
    mock_whisper.assert_not_called()
    # Conteúdo original preservado
    assert out.read_text(encoding="utf-8") == "existing"


@pytest.mark.unit
def test_transcribe_existing_output_overwrites_when_user_says_yes(tmp_path, mocker):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    out = tmp_path / "out.txt"
    out.write_text("old content", encoding="utf-8")

    _patch_whisper(mocker, [_Seg(0.0, 3.0, "novo")])
    mocker.patch("builtins.input", return_value="y")
    from src.transcriber import transcribe
    result = transcribe(
        audio_path=audio, output_path=out, meta=_DEFAULT_META,
        url="https://x", model_size="small", language="pt",
        threads=2, beam_size=1, force_overwrite=False,
    )
    assert result is not None
    assert "novo" in out.read_text(encoding="utf-8")
    assert "old content" not in out.read_text(encoding="utf-8")


@pytest.mark.unit
def test_transcribe_keyboard_interrupt_removes_partial_file(tmp_path, mocker):
    """KeyboardInterrupt no meio do loop → remove arquivo incompleto e sys.exit(0)."""
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    out = tmp_path / "out.txt"

    def _raise_after_first():
        yield _Seg(0.0, 3.0, "primeiro")
        raise KeyboardInterrupt

    fake_model = mocker.MagicMock()
    fake_model.transcribe.return_value = (_raise_after_first(), _Info())
    mocker.patch("src.transcriber.WhisperModel", return_value=fake_model)
    mocker.patch("src.transcriber._resolve_device", return_value=("cpu", "int8"))

    from src.transcriber import transcribe
    with pytest.raises(SystemExit) as exc:
        transcribe(
            audio_path=audio, output_path=out, meta=_DEFAULT_META,
            url="https://x", model_size="small", language="pt",
            threads=2, beam_size=1, force_overwrite=True,
        )
    assert exc.value.code == 0
    # Arquivo incompleto removido
    assert not out.exists()


# ── print_summary ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_print_summary_outputs_key_fields(capsys, tmp_path):
    from src.transcriber import print_summary
    out_path = tmp_path / "result.txt"
    out_path.write_text("dummy", encoding="utf-8")
    print_summary({"title": "Meu Vídeo", "duration": 125}, out_path, elapsed=63)
    captured = capsys.readouterr().out
    assert "Meu Vídeo" in captured
    assert "00:02:05" in captured
    assert "result.txt" in captured
    assert "1m 03s" in captured
