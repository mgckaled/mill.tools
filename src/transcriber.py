"""
transcriber.py: Audio transcription, progress display and result summary.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from time import time

import ctranslate2
from faster_whisper import WhisperModel
from tqdm import tqdm

from src.core.metadata import format_duration, format_metadata

LOW_CONF_LOGPROB = -1.0  # avg_logprob abaixo disso indica baixa confiança
HIGH_NO_SPEECH_PROB = 0.6  # no_speech_prob acima disso indica provável silêncio/ruído


def format_elapsed(seconds: float) -> str:
    """Format elapsed processing time into a human-readable string.

    Args:
        seconds: Elapsed time in seconds.

    Returns:
        Human-readable string such as '2h 14m 03s' or '03m 22s'.
    """
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02}m {s:02}s"
    if m:
        return f"{m}m {s:02}s"
    return f"{s}s"


def _resolve_device(threads: int) -> tuple[str, str]:
    """Detect available compute device and select the best compute type.

    Prefers CUDA with int8_float32 if available, falls back to CPU with int8.

    Args:
        threads: CPU thread count (used only on CPU fallback path).

    Returns:
        Tuple of (device, compute_type).
    """
    try:
        cuda_types = ctranslate2.get_supported_compute_types("cuda")
        if "int8_float32" in cuda_types:
            return "cuda", "int8_float32"
        if "float32" in cuda_types:
            return "cuda", "float32"
    except RuntimeError:
        pass
    return "cpu", "int8"


def transcribe(
    audio_path: Path,
    output_path: Path,
    meta: dict,
    url: str,
    model_size: str,
    language: str | None,
    threads: int,
    beam_size: int,
    on_event: Callable[[str, str, dict], None] | None = None,
    force_overwrite: bool = False,
    subtitle_formats: tuple[str, ...] = (),
) -> float | None:
    """Transcribe an audio file using faster-whisper and save plain text output.

    Writes a metadata header (including detected language) at the top of the
    output file, followed by the full transcription as continuous text.
    Displays a tqdm progress bar during transcription. Uses VAD filter to
    skip silence and beam_size to balance speed vs accuracy. Handles
    KeyboardInterrupt gracefully by removing the incomplete output file.

    Args:
        audio_path: Path to the MP3 audio file.
        output_path: Path to write the plain text transcription.
        meta: Raw metadata dictionary from yt-dlp.
        url: Original YouTube URL.
        model_size: Whisper model size (e.g. 'small', 'medium', 'large-v3').
        language: Language code or None for auto-detection.
        threads: Number of CPU threads (used only when GPU is unavailable).
        beam_size: Beam size for decoding (lower = faster, higher = more accurate).
        subtitle_formats: Optional tuple of formats to export ("srt", "vtt").
            Empty (default) preserves the original .txt-only behavior. When
            non-empty, each segment is also collected as a SubtitleCue and the
            files are written to TRANSCRIPTIONS_SUBTITLES_DIR after the loop.

    Returns:
        Elapsed transcription time in seconds.
    """

    def _emit(type: str, payload: dict = {}) -> None:
        if on_event:
            on_event(type, "transcribe", payload)

    if output_path.exists():
        if force_overwrite:
            logging.info("[»] Overwriting existing transcription: %s", output_path.name)
        else:
            try:
                answer = input(
                    f"[!] Transcription already exists: '{output_path}'. Overwrite? [y/N] "
                )
            except EOFError:
                # No stdin (scheduled/piped run) — default to not overwriting
                # rather than crashing on the prompt.
                answer = "n"
            if answer.strip().lower() != "y":
                logging.info("Skipping transcription.")
                return None

    device, compute_type = _resolve_device(threads)
    logging.debug(
        "[d] Device: %s | compute_type: %s | threads: %d | beam_size: %d",
        device.upper(),
        compute_type,
        threads,
        beam_size,
    )
    logging.info(
        "[*] Loading model '%s' on %s (%s)...", model_size, device.upper(), compute_type
    )
    model_load_start = time()
    _emit(
        "whisper_loading",
        {"model_size": model_size, "device": device, "compute_type": compute_type},
    )
    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        cpu_threads=threads if device == "cpu" else 0,
        num_workers=1,
    )
    elapsed_load = time() - model_load_start
    logging.debug("[d] Model loaded in %.1fs", elapsed_load)
    _emit("whisper_loaded", {"elapsed": elapsed_load})

    logging.info("[~] Transcribing... (this may take a while for long videos)")
    _emit("transcribe_started")

    try:
        start = time()
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        logging.info(
            "[i] Detected language: %s (%.0f%% confidence)",
            info.language,
            info.language_probability * 100,
        )
        logging.debug(
            "[d] Audio duration: %.1fs | language_prob: %.2f | vad_filter: on | min_silence: 500ms",
            info.duration,
            info.language_probability,
        )
        _emit(
            "language_detected",
            {
                "language": info.language,
                "confidence": info.language_probability,
                "audio_duration": info.duration,
            },
        )

        # VAD optimization: report how much silence was skipped.
        duration_after_vad = getattr(info, "duration_after_vad", None)
        if duration_after_vad is not None:
            removed = info.duration - duration_after_vad
            if removed >= 1:
                pct = (removed / info.duration * 100) if info.duration else 0
                logging.info(
                    "[i] VAD removed %s of silence (%.0f%%)",
                    format_elapsed(removed),
                    pct,
                )
                _emit(
                    "vad_filtered",
                    {
                        "duration": info.duration,
                        "duration_after_vad": duration_after_vad,
                        "removed": removed,
                    },
                )

        header = format_metadata(meta, url, detected_language=info.language)
        # meta["duration"] is 0 for local files (no metadata source) — info.duration
        # (from Whisper, known before the segment loop starts) gives the progress
        # bar a real total instead of staying stuck at 0%.
        duration = int(meta.get("duration", 0)) or int(info.duration)

        segment_count = 0
        flagged_count = 0
        cues: list = []  # populated only when subtitle_formats is non-empty
        with output_path.open("w", encoding="utf-8") as f:
            f.write(header)
            current = 0.0
            shown = 0  # whole seconds already reported to the bar
            with tqdm(
                total=duration, unit="s", desc="Transcribing", ncols=72
            ) as progress_bar:
                for segment in segments:
                    text = segment.text.strip()
                    low_conf = (
                        segment.avg_logprob < LOW_CONF_LOGPROB
                        or segment.no_speech_prob > HIGH_NO_SPEECH_PROB
                    )
                    if low_conf:
                        f.write(f"{text} [?] ")
                        flagged_count += 1
                    else:
                        f.write(f"{text} ")
                    current = segment.end
                    # Update by the integer difference of the float-accumulated
                    # cumulative position, not int(elapsed_seg) per segment —
                    # truncating each segment's fractional part independently
                    # loses time across many segments and the bar never reaches 100%.
                    total_shown = int(current)
                    progress_bar.update(total_shown - shown)
                    shown = total_shown
                    segment_count += 1
                    if subtitle_formats:
                        from src.core.subtitles import SubtitleCue

                        cues.append(
                            SubtitleCue(
                                index=segment_count,
                                start=segment.start,
                                end=segment.end,
                                text=text,
                            )
                        )
                    _emit(
                        "transcribe_segment",
                        {
                            "text": segment.text,
                            "start": segment.start,
                            "end": segment.end,
                            "is_low_confidence": low_conf,
                        },
                    )

        elapsed = time() - start
        txt_size_kb = output_path.stat().st_size / 1024
        logging.debug(
            "[d] Segments transcribed: %d | flagged low-confidence: %d | output size: %.1f KB",
            segment_count,
            flagged_count,
            txt_size_kb,
        )
        if flagged_count:
            logging.info(
                "[!] %d segment(s) flagged as low-confidence [?] — review recommended",
                flagged_count,
            )

        if subtitle_formats and cues:
            from src.core.subtitles import write_subtitles
            from src.utils import TRANSCRIPTIONS_SUBTITLES_DIR

            TRANSCRIPTIONS_SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
            sub_stem = TRANSCRIPTIONS_SUBTITLES_DIR / output_path.stem
            sub_paths = write_subtitles(cues, sub_stem, subtitle_formats)
            logging.info(
                "[✓] Subtitles written: %s", ", ".join(p.name for p in sub_paths)
            )
            _emit("subtitles_done", {"paths": [str(p) for p in sub_paths]})

        _emit(
            "transcribe_done",
            {
                "elapsed": elapsed,
                "flagged_count": flagged_count,
                "output_path": str(output_path),
            },
        )
        return elapsed

    except BaseException as exc:
        # Any exception mid-loop — not just Ctrl-C — leaves an incomplete .txt
        # that the Library/RAG would later index as if it were a full
        # transcription. Clean it up regardless of cause, then re-raise:
        # deciding the process exit code is main.py's call, not this library
        # function's.
        if isinstance(exc, KeyboardInterrupt):
            logging.warning("[!] Transcription interrupted by user.")
        else:
            logging.error("[x] Transcription failed: %s", exc)
        if output_path.exists():
            output_path.unlink()
            logging.warning("[-] Incomplete file removed: %s", output_path)
        raise


def print_summary(meta: dict, output_path: Path, elapsed: float) -> None:
    """Print a formatted summary block after a successful transcription.

    Args:
        meta: Raw metadata dictionary from yt-dlp.
        output_path: Path where the transcription was saved.
        elapsed: Total processing time in seconds.
    """
    duration = format_duration(int(meta.get("duration", 0)))
    print("\n" + "=" * 64)
    print(f"  title    : {meta.get('title', 'n/a')}")
    print(f"  duration : {duration}")
    print(f"  output   : {output_path}")
    print(f"  elapsed  : {format_elapsed(elapsed)}")
    print("=" * 64 + "\n")
