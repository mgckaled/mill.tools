"""Unit tests for src/gui/modules/document/pipeline_log.py — 10 tests."""
import pytest

pytestmark = pytest.mark.unit

_ALL_OPS = [
    "merge", "split", "compress", "rotate", "watermark", "stamp",
    "encrypt", "extract", "pdf_to_images", "images_to_pdf", "analyze", "qr",
]


def _make_event(type_: str, payload: dict):
    """Build a minimal PipelineEvent-like object for testing."""
    class _Ev:
        type = type_
        payload = {}
        module_id = "document"
        stage = "document"
    ev = _Ev()
    ev.payload = payload
    ev.type = type_
    return ev


def test_resolve_stage_label_for_all_operations():
    from src.gui.modules.document.pipeline_log import resolve_stage_label
    for op in _ALL_OPS:
        ev = _make_event("document_op_start", {"operation": op, "item_name": "test.pdf"})
        label = resolve_stage_label(ev)
        assert label and len(label) > 0, f"Empty label for op={op}"


def test_fmt_op_start_includes_item_name():
    from src.gui.modules.document.pipeline_log import fmt_op_start
    result = fmt_op_start("merge", "meu_doc.pdf", 1, 1, page_count=5)
    assert "meu_doc.pdf" in result


def test_fmt_op_start_includes_page_count():
    from src.gui.modules.document.pipeline_log import fmt_op_start
    result = fmt_op_start("split", "doc.pdf", 1, 1, page_count=10)
    assert "10" in result


def test_fmt_op_done_shows_size_reduction_for_compress():
    from src.gui.modules.document.pipeline_log import fmt_op_done
    lines = fmt_op_done(
        "compress",
        "output/doc_compressed.pdf",
        "1.2s",
        extra_stats={"size_reduction_pct": 75.0},
    )
    combined = " ".join(lines)
    assert "75" in combined
    assert "−" in combined


def test_fmt_op_done_shows_elapsed():
    from src.gui.modules.document.pipeline_log import fmt_op_done
    lines = fmt_op_done("rotate", "output/doc_rotated90.pdf", "0.8s")
    combined = " ".join(lines)
    assert "0.8s" in combined


def test_fmt_op_done_merge_shows_page_total():
    from src.gui.modules.document.pipeline_log import fmt_op_done
    lines = fmt_op_done(
        "merge",
        "output/merged.pdf",
        "0.5s",
        extra_stats={"page_total": 67, "file_count": 3},
    )
    combined = " ".join(lines)
    assert "67" in combined


def test_fmt_op_done_split_shows_file_count():
    from src.gui.modules.document.pipeline_log import fmt_op_done
    lines = fmt_op_done(
        "split",
        "output/doc_p1-3.pdf",
        "0.3s",
        extra_stats={"output_files": ["p1-3.pdf", "p5.pdf"], "page_counts": [3, 1]},
    )
    combined = " ".join(lines)
    assert "2" in combined  # len(output_files)


def test_resolve_messages_op_start():
    from src.gui.modules.document.pipeline_log import resolve_messages
    ev = _make_event("document_op_start", {"operation": "compress", "item_name": "doc.pdf"})
    lines = resolve_messages(ev)
    assert len(lines) == 1
    assert "Comprimindo" in lines[0]


def test_resolve_messages_op_done():
    from src.gui.modules.document.pipeline_log import resolve_messages
    ev = _make_event("document_op_done", {
        "operation": "rotate",
        "output_path": "output/document/processed/doc_rotated90.pdf",
        "elapsed": "0.5s",
        "item_idx": 1,
        "total": 1,
        "extra_stats": {},
    })
    lines = resolve_messages(ev)
    assert any("0.5s" in l for l in lines)


def test_resolve_messages_op_error():
    from src.gui.modules.document.pipeline_log import resolve_messages
    ev = _make_event("document_op_error", {"item_name": "bad.pdf", "message": "file not found"})
    lines = resolve_messages(ev)
    assert len(lines) == 1
    assert "[!]" in lines[0]
    assert "bad.pdf" in lines[0]
