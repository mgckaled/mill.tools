"""Uniform step adapters wrapping existing pure core functions.

Each adapter gives a heterogeneous core function a uniform signature
``adapter(inputs, params, ctx) -> list[Path]`` and writes to the *canonical*
output dir of its module (``src/utils`` constants), never to a shared dir —
that is what keeps PR6's Library classifying each artifact by kind.

The core never changes: adding an operation to automation is a thin wrapper plus
one ``STEP_REGISTRY`` entry. The adapter is also the single layer that knows the
exact callback shape of each core function. The project has no single callback
style — ``transcribe``/``analyze`` use ``on_event(type, stage, payload)``,
``download_*`` use ``progress_hook(dict)`` and ``normalize_lufs`` uses
``progress_cb(float)`` — so the adapter is where those converge onto
``ctx.emit(...)``; without it, download/normalize steps would have no progress.
"""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import (
    KIND_AUDIO,
    KIND_IMAGE,
    KIND_MARKDOWN,
    KIND_PDF,
    KIND_TEXT,
    KIND_URL,
    KIND_VIDEO,
    StepContext,
    StepSpec,
)

# ---------------------------------------------------------------------------
# Audio adapters
# ---------------------------------------------------------------------------


def _audio_download(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """URL → audio file in the canonical audio/source dir. Wraps download_audio.

    download_audio reports progress via ``progress_hook(dict)`` (yt-dlp); the
    adapter normalizes it to ``ctx.emit`` so the step shows progress like the rest.
    """
    from src.core.audio.downloader import download_audio
    from src.utils import AUDIO_SOURCE_DIR

    out = download_audio(
        str(inputs[0]),
        AUDIO_SOURCE_DIR,
        fmt=params.get("fmt", "mp3"),
        quality=params.get("quality", "best"),
        embed_meta=params.get("embed_meta", False),
        progress_hook=lambda d: ctx.emit("progress_update", d),
    )
    return [out]


def _audio_convert(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """audio → re-encoded audio. Wraps convert_audio."""
    from src.core.audio.converter import convert_audio
    from src.utils import AUDIO_PROCESSED_DIR

    out = convert_audio(
        Path(inputs[0]),
        AUDIO_PROCESSED_DIR,
        fmt=params.get("fmt", "mp3"),
        bitrate=params.get("bitrate"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _audio_extract(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → extracted audio track. Wraps extract_audio."""
    from src.core.audio.converter import extract_audio
    from src.utils import AUDIO_PROCESSED_DIR

    out = extract_audio(
        Path(inputs[0]),
        AUDIO_PROCESSED_DIR,
        fmt=params.get("fmt", "mp3"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _audio_denoise(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """audio → spectral-gated denoised WAV. Wraps denoise (CPU, no progress cb)."""
    from src.core.audio.denoiser import denoise
    from src.utils import AUDIO_PROCESSED_DIR

    out = denoise(
        Path(inputs[0]), AUDIO_PROCESSED_DIR, stationary=params.get("stationary", True)
    )
    return [out]


def _audio_normalize(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """audio → loudness-normalized audio. Wraps normalize_lufs.

    normalize_lufs reports progress via ``progress_cb(float 0..1)`` and returns
    ``(path, stats)``; the adapter keeps only the path and normalizes progress.
    """
    from src.core.audio.normalizer import normalize_lufs
    from src.utils import AUDIO_PROCESSED_DIR

    out, _stats = normalize_lufs(
        Path(inputs[0]),
        AUDIO_PROCESSED_DIR,
        target_lufs=params.get("target_lufs", -14.0),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


# ---------------------------------------------------------------------------
# Video adapters
# ---------------------------------------------------------------------------


def _video_download(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """URL → video file in the canonical video/source dir. Wraps download_video."""
    from src.core.video.downloader import download_video
    from src.utils import VIDEO_SOURCE_DIR

    out = download_video(
        str(inputs[0]),
        VIDEO_SOURCE_DIR,
        resolution=params.get("resolution", "1080"),
        container=params.get("container", "mp4"),
        embed_meta=params.get("embed_meta", True),
        progress_hook=lambda d: ctx.emit("progress_update", d),
    )
    return [out]


def _video_convert(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → converted container/codec. Wraps convert_video."""
    from src.core.video.converter import convert_video
    from src.utils import VIDEO_PROCESSED_DIR

    out = convert_video(
        Path(inputs[0]),
        VIDEO_PROCESSED_DIR,
        container=params.get("container", "mp4"),
        vcodec=params.get("vcodec", "copy"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _video_trim(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → trimmed clip. Wraps trim_video."""
    from src.core.video.converter import trim_video
    from src.utils import VIDEO_PROCESSED_DIR

    out = trim_video(
        Path(inputs[0]),
        VIDEO_PROCESSED_DIR,
        start=params.get("start", ""),
        end=params.get("end", ""),
        reenc=params.get("reenc", False),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _video_compress(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → H.264/CRF compressed video. Wraps compress_video."""
    from src.core.video.converter import compress_video
    from src.utils import VIDEO_PROCESSED_DIR

    out = compress_video(
        Path(inputs[0]),
        VIDEO_PROCESSED_DIR,
        crf=params.get("crf", 23),
        preset=params.get("preset", "medium"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _video_resize(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → resized video (aspect preserved). Wraps resize_video."""
    from src.core.video.converter import resize_video
    from src.utils import VIDEO_PROCESSED_DIR

    out = resize_video(
        Path(inputs[0]),
        VIDEO_PROCESSED_DIR,
        width=params.get("width", 0),
        height=params.get("height", 0),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _video_thumbnail(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → single frame as image. Wraps make_thumbnail (no progress cb).

    The frame is an image, so it is written to the image/processed dir to keep
    the Library kind classification correct.
    """
    from src.core.video.converter import make_thumbnail
    from src.utils import IMAGE_PROCESSED_DIR

    out = make_thumbnail(
        Path(inputs[0]),
        IMAGE_PROCESSED_DIR,
        time=params.get("time", "00:00:01"),
        fmt=params.get("fmt", "jpg"),
    )
    return [out]


def _video_subtitle(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video + subtitle → subtitled video (mux/burn-in). Wraps add_subtitles.

    The only multi-input step of v1: the chain carries text after transcribing,
    but burning a subtitle needs the *original video* and the *.srt*. Both are
    recovered from ``ctx`` — the video from ``initial_inputs[0]`` and the subtitle
    from the transcribe step's outputs (any .srt/.vtt among them).
    """
    from src.core.video.converter import add_subtitles
    from src.utils import VIDEO_PROCESSED_DIR

    video = Path(ctx.initial_inputs[0])
    produced = ctx.outputs_by_op.get("transcription.transcribe", [])
    subs = [Path(p) for p in produced if Path(p).suffix.lower() in (".srt", ".vtt")]
    if not subs:
        raise ValueError(
            "video.subtitle requires a subtitle produced by transcription.transcribe "
            "(add subtitles=['srt'] to the transcribe step)"
        )
    out = add_subtitles(
        video,
        subs[0],
        VIDEO_PROCESSED_DIR,
        mode=params.get("mode", "soft"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


# ---------------------------------------------------------------------------
# Transcription / LLM adapters
# ---------------------------------------------------------------------------


def _transcribe(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """audio/video → transcription .txt (+ optional .srt/.vtt). Wraps transcribe.

    transcribe() returns only elapsed time, so the adapter reconstructs the
    subtitle paths deterministically (the core writes them to
    ``TRANSCRIPTIONS_SUBTITLES_DIR / f"{stem}.{fmt}"``). Returning ``[txt, *subs]``
    lets a later video.subtitle step reach the .srt via ``ctx.outputs_by_op``.
    """
    from src import transcriber
    from src.utils import TRANSCRIPTIONS_SUBTITLES_DIR, TRANSCRIPTIONS_TEXT_DIR

    media = Path(inputs[0])  # audio OR video (faster-whisper decodes video via PyAV)
    out = TRANSCRIPTIONS_TEXT_DIR / f"transcription_{media.stem}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    subs = tuple(params.get("subtitles", ()))
    language = params.get("language", "auto")
    transcriber.transcribe(
        audio_path=media,
        output_path=out,
        meta={"title": media.stem, "duration": 0},
        url=str(media),
        model_size=params.get("model", "small"),
        language=None if language == "auto" else language,
        threads=params.get("threads", 2),
        beam_size=params.get("beam_size", 1),
        force_overwrite=True,
        subtitle_formats=subs,
        on_event=lambda t, s, p: ctx.emit(t, p),
    )
    sub_paths = [TRANSCRIPTIONS_SUBTITLES_DIR / f"{out.stem}.{fmt}" for fmt in subs]
    return [out, *sub_paths]


def _format(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """transcription .txt → same .txt with paragraph breaks. Wraps format_transcription.

    format_transcription rewrites the file IN-PLACE and returns ``str | None``
    (the body), so the adapter returns ``[input_path]`` — the same, now-formatted
    .txt — discarding the string.
    """
    from src import formatter

    input_path = Path(inputs[0])
    formatter.format_transcription(
        input_path,
        model_name=params.get("model", formatter.DEFAULT_FORMAT_MODEL),
        on_event=lambda t, s, p: ctx.emit(t, p),
    )
    return [input_path]


def _analyze(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """transcription/text → structured analysis .md. Wraps analyzer.analyze."""
    from src import analyzer

    out = analyzer.analyze(
        input_path=Path(inputs[0]),
        model_name=params.get("model", analyzer.DEFAULT_MODEL),
        on_event=lambda t, s, p: ctx.emit(t, p),
        profile=params.get("profile", analyzer.DEFAULT_PROFILE),
    )
    return [out]


def _prompt(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """transcription/text → condensed prompt-ready .txt. Wraps build_prompt_ready."""
    from src import prompter

    out = prompter.build_prompt_ready(
        Path(inputs[0]),
        model_name=params.get("model", prompter.DEFAULT_PROMPT_MODEL),
        on_event=lambda t, s, p: ctx.emit(t, p),
    )
    return [out]


def _ai_answer(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """text/markdown → cited RAG answer .md (PR7). Wraps the local RAG core.

    chat.answer() returns an AnswerResult (text + sources), not a Path, so the
    adapter serializes the answer (plus a Fontes list) to a .md. The just-produced
    document is reindexed first and the retrieval is scoped to it, so a chain like
    ``transcribe → ai.answer`` actually grounds the answer on the new file. Needs
    the local embedder available (PR7 gate); otherwise the step fails and
    stop_on_error reports it.
    """
    from src.core.library.scanner import scan_library
    from src.core.rag import embedder
    from src.core.rag.chat import DEFAULT_MODEL
    from src.core.rag.chat import answer as _answer
    from src.core.rag.indexer import build_index, index_dir
    from src.core.rag.retriever import retrieve
    from src.core.rag.store import VectorStore
    from src.utils import TRANSCRIPTIONS_ANALYSIS_DIR

    embed_model = params.get("embed_model", "nomic-embed-custom")
    if not embedder.is_available(embed_model):
        raise RuntimeError(f"Embedder indisponível. {embedder.SETUP_HINT}")

    query = params.get("query") or "Resuma o conteúdo e liste os pontos principais."
    src = Path(inputs[0])

    # Reindex so the freshly produced document is embedded, then scope to it.
    store = VectorStore.load(index_dir(), dim=embedder.EMBED_DIM)
    build_index(
        scan_library(),
        store,
        lambda texts: embedder.embed_texts(texts, model=embed_model),
    )
    store.persist(index_dir())

    hits = retrieve(
        query,
        store,
        lambda q: embedder.embed_query(q, model=embed_model),
        k=params.get("k", 6),
        scope=str(src),
    )
    result = _answer(query, hits, model_name=params.get("model", DEFAULT_MODEL))

    TRANSCRIPTIONS_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out = TRANSCRIPTIONS_ANALYSIS_DIR / f"{src.stem}_ia.md"
    body = result.text
    if result.sources:
        body += "\n\n## Fontes\n" + "\n".join(f"- {s.name}" for s in result.sources)
    out.write_text(body + "\n", encoding="utf-8")
    return [out]


# ---------------------------------------------------------------------------
# Document adapters
# ---------------------------------------------------------------------------


def _doc_merge(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """N PDFs → one merged PDF. Wraps merge_pdfs (consumes the whole input list)."""
    from src.core.document.processor import merge_pdfs
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = merge_pdfs([Path(p) for p in inputs], DOCUMENT_PROCESSED_DIR)
    return [out]


def _doc_split(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → one PDF per page range. Wraps split_pdf."""
    from src.core.document.processor import split_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    return split_pdf(
        Path(inputs[0]), params.get("pages", "all"), DOCUMENT_PROCESSED_DIR
    )


def _doc_compress(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → image-recompressed PDF. Wraps compress_pdf."""
    from src.core.document.processor import compress_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = compress_pdf(
        Path(inputs[0]),
        DOCUMENT_PROCESSED_DIR,
        image_quality=params.get("image_quality", 75),
    )
    return [out]


def _doc_rotate(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → rotated PDF. Wraps rotate_pdf."""
    from src.core.document.processor import rotate_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = rotate_pdf(
        Path(inputs[0]),
        DOCUMENT_PROCESSED_DIR,
        angle=params.get("angle", 90),
        pages=params.get("pages", "all"),
    )
    return [out]


def _doc_watermark(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → watermarked PDF. Wraps watermark_pdf."""
    from src.core.document.processor import watermark_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = watermark_pdf(
        Path(inputs[0]),
        DOCUMENT_PROCESSED_DIR,
        text=params.get("text", "CONFIDENCIAL"),
        opacity=params.get("opacity", 0.3),
        position=params.get("position", "center"),
    )
    return [out]


def _doc_stamp(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → stamped PDF. Wraps stamp_pdf."""
    from src.core.document.processor import stamp_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = stamp_pdf(
        Path(inputs[0]), DOCUMENT_PROCESSED_DIR, text=params.get("text", "RASCUNHO")
    )
    return [out]


def _doc_encrypt(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → AES-256 encrypted PDF. Wraps encrypt_pdf."""
    from src.core.document.processor import encrypt_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = encrypt_pdf(
        Path(inputs[0]), DOCUMENT_PROCESSED_DIR, password=params.get("password", "")
    )
    return [out]


def _doc_extract(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → extracted text .txt. Wraps extract_text (keeps only the path)."""
    from src.core.document.converter import extract_text
    from src.utils import DOCUMENT_PROCESSED_DIR

    out, _wc = extract_text(Path(inputs[0]), DOCUMENT_PROCESSED_DIR)
    return [out]


def _doc_ocr(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """scanned PDF → OCR text .txt. Wraps ocr_pdf (hybrid native + Tesseract)."""
    from src.core.document.ocr import ocr_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out, _wc = ocr_pdf(
        Path(inputs[0]),
        DOCUMENT_PROCESSED_DIR,
        lang=params.get("lang", "por"),
        dpi=params.get("dpi", 300),
        progress_cb=lambda c, t: ctx.emit(
            "progress_update", {"current": c, "total": t}
        ),
    )
    return [out]


def _doc_pdf_to_images(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → one image per page. Wraps pdf_to_images (writes to image/processed)."""
    from src.core.document.converter import pdf_to_images
    from src.utils import IMAGE_PROCESSED_DIR

    return pdf_to_images(
        Path(inputs[0]),
        IMAGE_PROCESSED_DIR,
        fmt=params.get("fmt", "jpg"),
        dpi=params.get("dpi", 150),
        progress_cb=lambda c, t: ctx.emit(
            "progress_update", {"current": c, "total": t}
        ),
    )


def _doc_images_to_pdf(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """N images → one PDF. Wraps images_to_pdf (consumes the whole input list)."""
    from src.core.document.converter import images_to_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = images_to_pdf(
        [Path(p) for p in inputs],
        DOCUMENT_PROCESSED_DIR,
        output_name=params.get("output_name", ""),
    )
    return [out]


# ---------------------------------------------------------------------------
# Image adapters
# ---------------------------------------------------------------------------


def _image_convert(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """image → re-encoded image. Wraps convert_image."""
    from src.core.image.converter import convert_image
    from src.utils import IMAGE_PROCESSED_DIR

    out = convert_image(
        Path(inputs[0]),
        IMAGE_PROCESSED_DIR,
        fmt=params.get("fmt", "webp"),
        quality=params.get("quality", 90),
    )
    return [out]


def _image_resize(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """image → resized image. Wraps resize_image."""
    from src.core.image.transform import resize_image
    from src.utils import IMAGE_PROCESSED_DIR

    out = resize_image(
        Path(inputs[0]),
        IMAGE_PROCESSED_DIR,
        resize_mode=params.get("resize_mode", "contain"),
        width=params.get("width"),
        height=params.get("height"),
        scale_pct=params.get("scale_pct", 100.0),
        out_fmt=params.get("out_fmt"),
        quality=params.get("quality", 90),
    )
    return [out]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

STEP_REGISTRY: dict[str, StepSpec] = {
    # audio
    "audio.download": StepSpec(
        _audio_download, frozenset({KIND_URL}), KIND_AUDIO, "Baixar áudio"
    ),
    "audio.convert": StepSpec(
        _audio_convert, frozenset({KIND_AUDIO}), KIND_AUDIO, "Converter áudio"
    ),
    "audio.extract": StepSpec(
        _audio_extract, frozenset({KIND_VIDEO}), KIND_AUDIO, "Extrair áudio"
    ),
    "audio.denoise": StepSpec(
        _audio_denoise, frozenset({KIND_AUDIO}), KIND_AUDIO, "Reduzir ruído"
    ),
    "audio.normalize": StepSpec(
        _audio_normalize, frozenset({KIND_AUDIO}), KIND_AUDIO, "Normalizar volume"
    ),
    # video
    "video.download": StepSpec(
        _video_download, frozenset({KIND_URL}), KIND_VIDEO, "Baixar vídeo"
    ),
    "video.convert": StepSpec(
        _video_convert, frozenset({KIND_VIDEO}), KIND_VIDEO, "Converter vídeo"
    ),
    "video.trim": StepSpec(
        _video_trim, frozenset({KIND_VIDEO}), KIND_VIDEO, "Cortar vídeo"
    ),
    "video.compress": StepSpec(
        _video_compress, frozenset({KIND_VIDEO}), KIND_VIDEO, "Comprimir vídeo"
    ),
    "video.resize": StepSpec(
        _video_resize, frozenset({KIND_VIDEO}), KIND_VIDEO, "Redimensionar vídeo"
    ),
    "video.thumbnail": StepSpec(
        _video_thumbnail, frozenset({KIND_VIDEO}), KIND_IMAGE, "Gerar thumbnail"
    ),
    # video.subtitle consumes the text the chain carries after transcribing; the
    # adapter recovers the real video + .srt from ctx (the only multi-input step).
    "video.subtitle": StepSpec(
        _video_subtitle, frozenset({KIND_TEXT}), KIND_VIDEO, "Embutir legenda"
    ),
    # transcription / LLM
    "transcription.transcribe": StepSpec(
        _transcribe, frozenset({KIND_AUDIO, KIND_VIDEO}), KIND_TEXT, "Transcrever"
    ),
    "transcription.format": StepSpec(
        _format, frozenset({KIND_TEXT}), KIND_TEXT, "Formatar"
    ),
    "transcription.analyze": StepSpec(
        _analyze, frozenset({KIND_TEXT, KIND_MARKDOWN}), KIND_MARKDOWN, "Analisar"
    ),
    "transcription.prompt": StepSpec(
        _prompt, frozenset({KIND_TEXT}), KIND_TEXT, "Gerar prompt-ready"
    ),
    "ai.answer": StepSpec(
        _ai_answer,
        frozenset({KIND_TEXT, KIND_MARKDOWN}),
        KIND_MARKDOWN,
        "Perguntar à IA",
    ),
    # document
    "document.merge": StepSpec(
        _doc_merge, frozenset({KIND_PDF}), KIND_PDF, "Mesclar PDFs"
    ),
    "document.split": StepSpec(
        _doc_split, frozenset({KIND_PDF}), KIND_PDF, "Dividir PDF"
    ),
    "document.compress": StepSpec(
        _doc_compress, frozenset({KIND_PDF}), KIND_PDF, "Comprimir PDF"
    ),
    "document.rotate": StepSpec(
        _doc_rotate, frozenset({KIND_PDF}), KIND_PDF, "Girar PDF"
    ),
    "document.watermark": StepSpec(
        _doc_watermark, frozenset({KIND_PDF}), KIND_PDF, "Marca d'água"
    ),
    "document.stamp": StepSpec(
        _doc_stamp, frozenset({KIND_PDF}), KIND_PDF, "Carimbar PDF"
    ),
    "document.encrypt": StepSpec(
        _doc_encrypt, frozenset({KIND_PDF}), KIND_PDF, "Criptografar PDF"
    ),
    "document.extract": StepSpec(
        _doc_extract, frozenset({KIND_PDF}), KIND_TEXT, "Extrair texto"
    ),
    "document.ocr": StepSpec(_doc_ocr, frozenset({KIND_PDF}), KIND_TEXT, "OCR"),
    "document.pdf_to_images": StepSpec(
        _doc_pdf_to_images, frozenset({KIND_PDF}), KIND_IMAGE, "PDF → imagens"
    ),
    "document.images_to_pdf": StepSpec(
        _doc_images_to_pdf, frozenset({KIND_IMAGE}), KIND_PDF, "Imagens → PDF"
    ),
    # image
    "image.convert": StepSpec(
        _image_convert, frozenset({KIND_IMAGE}), KIND_IMAGE, "Converter imagem"
    ),
    "image.resize": StepSpec(
        _image_resize, frozenset({KIND_IMAGE}), KIND_IMAGE, "Redimensionar imagem"
    ),
}
