"""Unit tests for src/gui/modules/image/pipeline_log.py."""

import pytest

pytestmark = pytest.mark.unit

_ALL_OPS = [
    "download",
    "convert",
    "resize",
    "crop",
    "rotate",
    "watermark",
    "border",
    "adjust",
    "filter",
    "favicon",
    "contact_sheet",
    "remove_bg",
    "describe",
]


def _make_event(type_: str, payload: dict):
    """Build a minimal PipelineEvent-like object for testing."""

    class _Ev:
        type = type_
        payload: dict = {}
        module_id = "image"
        stage = "image"

    ev = _Ev()
    ev.payload = payload
    ev.type = type_
    return ev


# ── resolve_stage_label ──────────────────────────────────────────────────────


def test_resolve_stage_label_for_all_operations():
    from src.gui.modules.image.pipeline_log import resolve_stage_label

    for op in _ALL_OPS:
        ev = _make_event("image_op_start", {"operation": op, "item_name": "test.png"})
        label = resolve_stage_label(ev)
        assert label and len(label) > 0, f"Empty label for op={op}"


def test_resolve_stage_label_progress_start():
    from src.gui.modules.image.pipeline_log import resolve_stage_label

    assert resolve_stage_label(_make_event("progress_start", {})) == "Iniciando..."


def test_resolve_stage_label_queue_progress_includes_position_and_name():
    from src.gui.modules.image.pipeline_log import resolve_stage_label

    ev = _make_event(
        "queue_progress",
        {
            "current_item": 3,
            "total_items": 7,
            "item_name": "photo.jpg",
        },
    )
    label = resolve_stage_label(ev)
    assert "3/7" in label
    assert "photo.jpg" in label


def test_resolve_stage_label_op_done_singular_vs_plural():
    from src.gui.modules.image.pipeline_log import resolve_stage_label

    one = _make_event("image_op_done", {"item_idx": 1, "total_items": 1})
    many = _make_event("image_op_done", {"item_idx": 2, "total_items": 5})
    assert resolve_stage_label(one) == "Concluído."
    assert "2/5" in resolve_stage_label(many)


def test_resolve_stage_label_op_error():
    from src.gui.modules.image.pipeline_log import resolve_stage_label

    assert (
        resolve_stage_label(_make_event("image_op_error", {}))
        == "Erro — continuando fila..."
    )


def test_resolve_stage_label_unknown_event_returns_none():
    from src.gui.modules.image.pipeline_log import resolve_stage_label

    assert resolve_stage_label(_make_event("xpto", {})) is None


# ── resolve_messages ─────────────────────────────────────────────────────────


def test_resolve_messages_op_start_uses_verb_and_item_name():
    from src.gui.modules.image.pipeline_log import resolve_messages

    ev = _make_event(
        "image_op_start", {"operation": "resize", "item_name": "photo.jpg"}
    )
    lines = resolve_messages(ev)
    assert len(lines) == 1
    assert "Redimensionando" in lines[0]
    assert "photo.jpg" in lines[0]


def test_resolve_messages_op_done_includes_elapsed_and_path():
    from src.gui.modules.image.pipeline_log import resolve_messages

    ev = _make_event(
        "image_op_done",
        {
            "output_path": "output/image/processed/photo.webp",
            "elapsed": "0.4s",
            "item_idx": 1,
            "total_items": 1,
            "src_size_bytes": 200_000,
            "out_size_bytes": 100_000,
        },
    )
    lines = resolve_messages(ev)
    combined = " ".join(lines)
    assert "0.4s" in combined
    assert "photo.webp" in combined


def test_resolve_messages_op_done_omits_size_when_zero():
    from src.gui.modules.image.pipeline_log import resolve_messages

    ev = _make_event(
        "image_op_done",
        {
            "output_path": "output/image/processed/photo.png",
            "elapsed": "0.1s",
            "item_idx": 1,
            "total_items": 1,
            "src_size_bytes": 0,
            "out_size_bytes": 0,
        },
    )
    lines = resolve_messages(ev)
    combined = " ".join(lines)
    assert "→" not in combined


def test_resolve_messages_op_error_includes_item_and_message():
    from src.gui.modules.image.pipeline_log import resolve_messages

    ev = _make_event(
        "image_op_error", {"item_name": "bad.png", "message": "cannot decode"}
    )
    lines = resolve_messages(ev)
    assert "bad.png" in lines[0]
    assert "cannot decode" in lines[0]


def test_resolve_messages_task_done_with_failed_count():
    from src.gui.modules.image.pipeline_log import resolve_messages

    ev = _make_event(
        "task_done", {"output_paths": ["a.jpg", "b.jpg"], "failed_count": 1}
    )
    lines = resolve_messages(ev)
    assert any("2 arquivo" in line for line in lines)
    assert any("1" in line and "erro" in line for line in lines)


def test_resolve_messages_log_passthrough():
    from src.gui.modules.image.pipeline_log import resolve_messages

    ev = _make_event("log", {"message": "[i] info"})
    assert resolve_messages(ev) == ["[i] info"]


# ── fmt_* builders ───────────────────────────────────────────────────────────


def test_fmt_image_info_with_full_metadata():
    from src.gui.modules.image.pipeline_log import fmt_image_info

    out = fmt_image_info("photo.jpg", 1920, 1080, "RGB", 1_048_576)
    assert "photo.jpg" in out
    assert "1920×1080" in out
    assert "RGB" in out
    assert "1.0 MB" in out


def test_fmt_convert_detail_uppercases_formats():
    from src.gui.modules.image.pipeline_log import fmt_convert_detail

    out = fmt_convert_detail("jpg", "webp")
    assert "JPG" in out
    assert "WEBP" in out
    assert "→" in out


def test_fmt_convert_detail_unknown_source():
    from src.gui.modules.image.pipeline_log import fmt_convert_detail

    out = fmt_convert_detail(None, "png")
    assert "?" in out
    assert "PNG" in out


def test_fmt_resize_detail_scale_pct_mode():
    from src.gui.modules.image.pipeline_log import fmt_resize_detail

    out = fmt_resize_detail(
        "scale_pct",
        w_in=1920,
        h_in=1080,
        w_out=None,
        h_out=None,
        scale_pct=50.0,
    )
    assert "Escala %" in out
    assert "50%" in out


def test_fmt_resize_detail_contain_mode():
    from src.gui.modules.image.pipeline_log import fmt_resize_detail

    out = fmt_resize_detail(
        "contain",
        w_in=1920,
        h_in=1080,
        w_out=800,
        h_out=600,
        scale_pct=100.0,
    )
    assert "Caber" in out
    assert "L=800" in out
    assert "A=600" in out


def test_fmt_crop_detail_modes():
    from src.gui.modules.image.pipeline_log import fmt_crop_detail

    manual = fmt_crop_detail("manual", left=10, top=20, width=100, height=200)
    assert "(10,20)" in manual
    assert "100×200" in manual

    ratio = fmt_crop_detail("ratio", ratio="16:9")
    assert "16:9" in ratio

    autotrim = fmt_crop_detail("autotrim", trim_color="#ffffff")
    assert "Auto-trim" in autotrim
    assert "#ffffff" in autotrim


def test_fmt_rotate_detail_lists_all_active_transforms():
    from src.gui.modules.image.pipeline_log import fmt_rotate_detail

    out = fmt_rotate_detail(angle=90, flip_h=True, flip_v=False, exif_auto=True)
    assert "90°" in out
    assert "espelhar H" in out
    assert "espelhar V" not in out
    assert "EXIF" in out


def test_fmt_rotate_detail_nothing_active_says_nenhuma():
    from src.gui.modules.image.pipeline_log import fmt_rotate_detail

    out = fmt_rotate_detail(angle=0, flip_h=False, flip_v=False, exif_auto=False)
    assert "nenhuma" in out


def test_fmt_watermark_detail_translates_position():
    from src.gui.modules.image.pipeline_log import fmt_watermark_detail

    out = fmt_watermark_detail(mode="texto", position="bottom-right", opacity=0.5)
    assert "↘" in out
    assert "50%" in out


def test_fmt_adjust_detail_omits_neutral_values():
    from src.gui.modules.image.pipeline_log import fmt_adjust_detail

    neutral = fmt_adjust_detail(1.0, 1.0, 1.0, 1.0)
    assert "sem alteração" in neutral

    changed = fmt_adjust_detail(brightness=1.3, contrast=1.0, color=1.0, sharpness=1.0)
    assert "Brilho: 1.3" in changed
    assert "Contraste" not in changed


def test_fmt_filter_detail_translates_known_filters():
    from src.gui.modules.image.pipeline_log import fmt_filter_detail

    assert "Blur" in fmt_filter_detail("blur")
    assert "Sharpen" in fmt_filter_detail("sharpen")
    assert "cinza" in fmt_filter_detail("grayscale")
    # Unknown filter — falls back to raw name
    assert "exotico" in fmt_filter_detail("exotico")


def test_fmt_favicon_detail_sorts_sizes():
    from src.gui.modules.image.pipeline_log import fmt_favicon_detail

    out = fmt_favicon_detail([64, 16, 32])
    assert out.index("16") < out.index("32") < out.index("64")


def test_fmt_cs_detail_computes_rows():
    from src.gui.modules.image.pipeline_log import fmt_cs_detail

    # 7 items in 3 cols → 3 rows (ceil)
    out = fmt_cs_detail(n_items=7, cols=3, thumb_size=200, gap=10, bg_color="white")
    assert "3×3" in out
    assert "200px" in out
    assert "10px" in out
    assert "white" in out


def test_fmt_describe_header_with_and_without_prompt():
    from src.gui.modules.image.pipeline_log import fmt_describe_header

    default = fmt_describe_header(model="moondream", prompt="")
    custom = fmt_describe_header(model="moondream", prompt="What is here?")
    assert "padrão PT-BR" in default
    assert "What is here?" in custom


def test_fmt_rembg_loading_includes_model():
    from src.gui.modules.image.pipeline_log import fmt_rembg_loading, fmt_rembg_loaded

    assert "u2netp" in fmt_rembg_loading("u2netp")
    assert "u2netp" in fmt_rembg_loaded("u2netp")
