"""Unit tests for the recipe step registry — every StepSpec is well-formed."""

from pathlib import Path

import pytest


@pytest.mark.unit
def test_registry_is_not_empty():
    from src.core.recipes.registry import STEP_REGISTRY

    assert STEP_REGISTRY


@pytest.mark.unit
def test_every_spec_is_well_formed():
    from src.core.recipes.registry import STEP_REGISTRY
    from src.core.recipes.types import ALL_KINDS

    for key, spec in STEP_REGISTRY.items():
        assert "." in key, f"{key!r} must follow 'module.op'"
        module, _, op = key.partition(".")
        assert module and op, f"{key!r} has empty module/op"
        assert callable(spec.adapter), f"{key} adapter is not callable"
        assert spec.accepts, f"{key} has empty accepts"
        assert spec.accepts <= ALL_KINDS, f"{key} accepts unknown kind(s)"
        assert spec.produces in ALL_KINDS, f"{key} produces unknown kind"
        assert spec.label.strip(), f"{key} has empty label"


@pytest.mark.unit
def test_core_operations_are_registered():
    from src.core.recipes.registry import STEP_REGISTRY

    for key in (
        "audio.download",
        "audio.normalize",
        "transcription.transcribe",
        "transcription.format",
        "transcription.analyze",
        "document.ocr",
        "video.subtitle",
        "ai.answer",
    ):
        assert key in STEP_REGISTRY


@pytest.mark.unit
def test_transcribe_accepts_audio_and_video():
    from src.core.recipes.registry import STEP_REGISTRY
    from src.core.recipes.types import KIND_AUDIO, KIND_VIDEO

    spec = STEP_REGISTRY["transcription.transcribe"]
    assert {KIND_AUDIO, KIND_VIDEO} <= spec.accepts


@pytest.mark.unit
def test_format_adapter_returns_input_path(mocker, tmp_path):
    """transcription.format rewrites in place and returns str → adapter yields [input_path]."""
    import src.core.recipes.registry.transcription as reg
    from src.core.recipes.types import StepContext

    mock_fmt = mocker.patch(
        "src.formatter.format_transcription", return_value="formatted body"
    )
    src = tmp_path / "t.txt"
    src.write_text("hello", encoding="utf-8")
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[src],
        outputs_by_op={},
    )

    out = reg._format([src], {"model": "phi4mini-custom"}, ctx)

    assert out == [src]
    assert mock_fmt.call_args.kwargs["model_name"] == "phi4mini-custom"


@pytest.mark.unit
def test_transcribe_adapter_builds_meta_and_reconstructs_subtitles(
    mocker, tmp_path, monkeypatch
):
    """transcribe() only returns elapsed time → adapter reconstructs [txt, *subs]."""
    import src.core.recipes.registry.transcription as reg
    import src.utils as utils
    from src.core.recipes.types import StepContext

    monkeypatch.setattr(utils, "TRANSCRIPTIONS_TEXT_DIR", tmp_path / "text")
    monkeypatch.setattr(utils, "TRANSCRIPTIONS_SUBTITLES_DIR", tmp_path / "subs")
    mock_tr = mocker.patch("src.transcriber.transcribe", return_value=1.0)

    media = tmp_path / "a.mp3"
    media.write_bytes(b"")
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[media],
        outputs_by_op={},
    )

    out = reg._transcribe([media], {"subtitles": ["srt", "vtt"], "model": "small"}, ctx)

    kwargs = mock_tr.call_args.kwargs
    assert kwargs["subtitle_formats"] == ("srt", "vtt")
    assert kwargs["output_path"] == tmp_path / "text" / "transcription_a.txt"
    assert kwargs["meta"]["title"] == "a"
    assert kwargs["model_size"] == "small"
    assert out == [
        tmp_path / "text" / "transcription_a.txt",
        tmp_path / "subs" / "transcription_a.srt",
        tmp_path / "subs" / "transcription_a.vtt",
    ]


@pytest.mark.unit
def test_transcribe_adapter_maps_auto_language_to_none(mocker, tmp_path, monkeypatch):
    import src.core.recipes.registry.transcription as reg
    import src.utils as utils
    from src.core.recipes.types import StepContext

    monkeypatch.setattr(utils, "TRANSCRIPTIONS_TEXT_DIR", tmp_path / "text")
    monkeypatch.setattr(utils, "TRANSCRIPTIONS_SUBTITLES_DIR", tmp_path / "subs")
    mock_tr = mocker.patch("src.transcriber.transcribe", return_value=1.0)

    media = tmp_path / "a.mp3"
    media.write_bytes(b"")
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[media],
        outputs_by_op={},
    )

    reg._transcribe([media], {}, ctx)  # language defaults to "auto"

    assert mock_tr.call_args.kwargs["language"] is None


# (registry key, core function to mock at its source, return value the mock yields)
# Patching at the source module works because each adapter does a function-local
# ``from X import Y`` at call time. A renamed core function makes mocker.patch
# raise at patch time, so this also pins the adapters against signature drift.
_ADAPTER_CASES = [
    ("audio.download", "src.core.audio.downloader.download_audio", Path("o.mp3")),
    ("audio.convert", "src.core.audio.converter.convert_audio", Path("o.mp3")),
    ("audio.extract", "src.core.audio.converter.extract_audio", Path("o.mp3")),
    ("audio.denoise", "src.core.audio.denoiser.denoise", Path("o.wav")),
    (
        "audio.normalize",
        "src.core.audio.normalizer.normalize_lufs",
        (Path("o.mp3"), {}),
    ),
    ("video.download", "src.core.video.downloader.download_video", Path("o.mp4")),
    ("video.convert", "src.core.video.converter.convert_video", Path("o.mp4")),
    ("video.trim", "src.core.video.converter.trim_video", Path("o.mp4")),
    ("video.compress", "src.core.video.converter.compress_video", Path("o.mp4")),
    ("video.resize", "src.core.video.converter.resize_video", Path("o.mp4")),
    ("video.thumbnail", "src.core.video.converter.make_thumbnail", Path("o.jpg")),
    ("transcription.analyze", "src.analyzer.analyze", Path("o.md")),
    ("transcription.prompt", "src.prompter.build_prompt_ready", Path("o.txt")),
    ("document.merge", "src.core.document.processor.merge_pdfs", Path("o.pdf")),
    ("document.split", "src.core.document.processor.split_pdf", [Path("o.pdf")]),
    ("document.compress", "src.core.document.processor.compress_pdf", Path("o.pdf")),
    ("document.rotate", "src.core.document.processor.rotate_pdf", Path("o.pdf")),
    ("document.watermark", "src.core.document.processor.watermark_pdf", Path("o.pdf")),
    ("document.stamp", "src.core.document.processor.stamp_pdf", Path("o.pdf")),
    ("document.encrypt", "src.core.document.processor.encrypt_pdf", Path("o.pdf")),
    (
        "document.extract",
        "src.core.document.converter.extract_text",
        (Path("o.txt"), 0),
    ),
    ("document.ocr", "src.core.document.ocr.ocr_pdf", (Path("o.txt"), 0)),
    (
        "document.pdf_to_images",
        "src.core.document.converter.pdf_to_images",
        [Path("o.jpg")],
    ),
    (
        "document.images_to_pdf",
        "src.core.document.converter.images_to_pdf",
        Path("o.pdf"),
    ),
    ("image.convert", "src.core.image.converter.convert_image", Path("o.webp")),
    ("image.resize", "src.core.image.transform.resize_image", Path("o.webp")),
    ("data.convert", "src.core.data.convert.convert_file", Path("o.csv")),
    ("data.profile", "src.core.data.profile.profile_file", Path("o_profile.txt")),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    "key,target,retval", _ADAPTER_CASES, ids=[c[0] for c in _ADAPTER_CASES]
)
def test_adapter_calls_core_and_returns_path_list(
    key, target, retval, mocker, tmp_path
):
    from src.core.recipes.registry import STEP_REGISTRY
    from src.core.recipes.types import StepContext

    mock = mocker.patch(target, return_value=retval)
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[tmp_path / "in"],
        outputs_by_op={},
    )

    out = STEP_REGISTRY[key].adapter([tmp_path / "in"], {}, ctx)

    assert mock.called
    assert isinstance(out, list)
    assert out and all(isinstance(p, Path) for p in out)


@pytest.mark.unit
def test_data_query_accepts_data_and_produces_text():
    from src.core.recipes.registry import STEP_REGISTRY
    from src.core.recipes.types import KIND_DATA, KIND_TEXT

    spec = STEP_REGISTRY["data.query"]
    assert spec.accepts == frozenset({KIND_DATA})
    assert spec.produces == KIND_TEXT


@pytest.mark.unit
def test_data_query_adapter_with_sql_skips_translation(mocker, tmp_path):
    from src.core.recipes.registry import STEP_REGISTRY
    from src.core.recipes.types import StepContext

    scan = mocker.patch(
        "src.core.data.scanner.scan_files", return_value=["fake_datafile"]
    )
    save = mocker.patch(
        "src.core.data.convert.save_query", return_value=tmp_path / "consulta.csv"
    )
    to_sql = mocker.patch("src.core.data.nl2sql.to_sql")  # must NOT be called

    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[tmp_path / "a.csv", tmp_path / "b.csv"],
        outputs_by_op={},
    )
    out = STEP_REGISTRY["data.query"].adapter(
        [tmp_path / "a.csv", tmp_path / "b.csv"], {"sql": "SELECT 1"}, ctx
    )

    assert scan.called  # multi-input: scans the whole list
    to_sql.assert_not_called()
    assert save.call_args.args[1] == "SELECT 1"
    assert out == [tmp_path / "consulta.csv"]


@pytest.mark.unit
def test_data_query_adapter_translates_question(mocker, tmp_path):
    from src.core.recipes.registry import STEP_REGISTRY
    from src.core.recipes.types import StepContext

    mocker.patch("src.core.data.scanner.scan_files", return_value=["fake"])
    mocker.patch("src.core.data.scanner.schema_text", return_value="t: a INT")
    to_sql = mocker.patch(
        "src.core.data.nl2sql.to_sql", return_value=("SELECT a FROM t", "ok")
    )
    save = mocker.patch(
        "src.core.data.convert.save_query", return_value=tmp_path / "consulta.csv"
    )

    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[tmp_path / "a.csv"],
        outputs_by_op={},
    )
    STEP_REGISTRY["data.query"].adapter(
        [tmp_path / "a.csv"], {"question": "quanto?"}, ctx
    )

    assert to_sql.called
    assert save.call_args.args[1] == "SELECT a FROM t"


@pytest.mark.unit
def test_data_query_adapter_requires_sql_or_question(mocker, tmp_path):
    from src.core.recipes.registry import STEP_REGISTRY
    from src.core.recipes.types import StepContext

    mocker.patch("src.core.data.scanner.scan_files", return_value=["fake"])
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[tmp_path / "a.csv"],
        outputs_by_op={},
    )
    with pytest.raises(ValueError):
        STEP_REGISTRY["data.query"].adapter([tmp_path / "a.csv"], {}, ctx)


@pytest.mark.unit
def test_subtitle_adapter_recovers_video_and_srt_from_context(mocker, tmp_path):
    import src.core.recipes.registry.video as reg
    from src.core.recipes.types import StepContext

    mock = mocker.patch(
        "src.core.video.converter.add_subtitles", return_value=tmp_path / "out.mp4"
    )
    video = tmp_path / "movie.mp4"
    srt = tmp_path / "t.srt"
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[video],
        outputs_by_op={"transcription.transcribe": [tmp_path / "t.txt", srt]},
    )

    out = reg._video_subtitle([tmp_path / "t.txt"], {"mode": "soft"}, ctx)

    assert mock.call_args.args[0] == video  # original video, not the chain's text
    assert mock.call_args.args[1] == srt  # subtitle recovered from history
    assert out == [tmp_path / "out.mp4"]


@pytest.mark.unit
def test_analyze_adapter_forwards_profile_param(mocker, tmp_path):
    import src.core.recipes.registry.transcription as reg
    from src.core.recipes.types import StepContext

    mock = mocker.patch("src.analyzer.analyze", return_value=tmp_path / "o.md")
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[tmp_path / "in.txt"],
        outputs_by_op={},
    )

    reg._analyze([tmp_path / "in.txt"], {"profile": "scientific"}, ctx)
    assert mock.call_args.kwargs["profile"] == "scientific"


@pytest.mark.unit
def test_analyze_adapter_defaults_profile_to_default(mocker, tmp_path):
    import src.core.recipes.registry.transcription as reg
    from src.core.recipes.types import StepContext

    mock = mocker.patch("src.analyzer.analyze", return_value=tmp_path / "o.md")
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[tmp_path / "in.txt"],
        outputs_by_op={},
    )

    reg._analyze([tmp_path / "in.txt"], {}, ctx)
    assert mock.call_args.kwargs["profile"] == "default"


@pytest.mark.unit
def test_ai_answer_adapter_writes_markdown_with_sources(mocker, tmp_path, monkeypatch):
    import src.core.recipes.registry.ai as reg
    import src.utils as utils
    from src.core.rag.types import AnswerResult
    from src.core.recipes.types import StepContext

    monkeypatch.setattr(utils, "TRANSCRIPTIONS_ANALYSIS_DIR", tmp_path / "analysis")
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.library.scanner.scan_library", return_value=[])
    mocker.patch("src.core.rag.indexer.build_index", return_value=None)
    mocker.patch("src.core.rag.store.VectorStore.load", return_value=mocker.MagicMock())
    mocker.patch("src.core.rag.retriever.retrieve", return_value=[])
    mocker.patch(
        "src.core.rag.chat.answer",
        return_value=AnswerResult(text="resposta gerada", sources=[Path("foo.txt")]),
    )

    src = tmp_path / "doc.txt"
    src.write_text("conteúdo", encoding="utf-8")
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[src],
        outputs_by_op={},
    )

    out = reg._ai_answer([src], {"query": "resuma"}, ctx)

    assert out == [tmp_path / "analysis" / "doc_ia.md"]
    text = out[0].read_text(encoding="utf-8")
    assert "resposta gerada" in text
    assert "foo.txt" in text


@pytest.mark.unit
def test_ai_answer_adapter_raises_when_embedder_unavailable(mocker, tmp_path):
    import src.core.recipes.registry.ai as reg
    from src.core.recipes.types import StepContext

    mocker.patch("src.core.rag.embedder.is_available", return_value=False)
    src = tmp_path / "doc.txt"
    src.write_text("x", encoding="utf-8")
    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[src],
        outputs_by_op={},
    )

    with pytest.raises(RuntimeError, match="indisponível"):
        reg._ai_answer([src], {}, ctx)


@pytest.mark.unit
def test_subtitle_adapter_errors_without_subtitle(tmp_path):
    import src.core.recipes.registry.video as reg
    from src.core.recipes.types import StepContext

    ctx = StepContext(
        emit=lambda *a: None,
        cancel_is_set=lambda: False,
        initial_inputs=[tmp_path / "movie.mp4"],
        outputs_by_op={"transcription.transcribe": [tmp_path / "t.txt"]},  # no .srt
    )

    with pytest.raises(ValueError, match="subtitle"):
        reg._video_subtitle([tmp_path / "t.txt"], {}, ctx)
