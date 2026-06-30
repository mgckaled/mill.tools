"""Tests for CLI image subcommand argument parsing."""

import argparse

import pytest

from src.cli.image import add_image_parser


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_image_parser(sub)
    return parser.parse_args(["image", *argv])


@pytest.mark.unit
def test_image_convert_defaults():
    ns = _parse("convert", "photo.jpg")
    assert ns.image_op == "convert"
    assert ns.file == "photo.jpg"
    assert ns.fmt == "jpg"
    assert ns.quality == 90


@pytest.mark.unit
def test_image_convert_custom_fmt():
    ns = _parse("convert", "photo.jpg", "--fmt", "webp", "--quality", "85")
    assert ns.fmt == "webp"
    assert ns.quality == 85


@pytest.mark.unit
def test_image_resize_mode_and_dims():
    ns = _parse(
        "resize", "photo.jpg", "--mode", "exact", "--width", "1920", "--height", "1080"
    )
    assert ns.mode == "exact"
    assert ns.width == 1920
    assert ns.height == 1080


@pytest.mark.unit
def test_image_resize_scale():
    ns = _parse("resize", "photo.jpg", "--mode", "scale_pct", "--scale", "50")
    assert ns.mode == "scale_pct"
    assert ns.scale_pct == 50.0


@pytest.mark.unit
def test_image_crop_ratio():
    ns = _parse("crop", "photo.jpg", "--mode", "ratio", "--ratio", "16:9")
    assert ns.mode == "ratio"
    assert ns.ratio == "16:9"


@pytest.mark.unit
def test_image_rotate_angle_and_flips():
    ns = _parse("rotate", "photo.jpg", "--angle", "90", "--flip-h", "--flip-v")
    assert ns.angle == 90
    assert ns.flip_h is True
    assert ns.flip_v is True


@pytest.mark.unit
def test_image_watermark_defaults():
    ns = _parse("watermark", "photo.jpg", "--text", "© 2025")
    assert ns.text == "© 2025"
    assert ns.position == "bottom-right"
    assert ns.opacity == 0.5


@pytest.mark.unit
def test_image_border_defaults():
    ns = _parse("border", "photo.jpg")
    assert ns.padding == 20
    assert ns.border_color == "#000000"
    assert ns.fill_alpha is False


@pytest.mark.unit
def test_image_adjust_defaults():
    ns = _parse("adjust", "photo.jpg", "--brightness", "1.2", "--contrast", "0.9")
    assert ns.brightness == 1.2
    assert ns.contrast == 0.9
    assert ns.saturation == 1.0


@pytest.mark.unit
def test_image_filter_type():
    ns = _parse("filter", "photo.jpg", "--type", "grayscale")
    assert ns.filter_type == "grayscale"


@pytest.mark.unit
def test_image_favicon_sizes():
    ns = _parse("favicon", "logo.png", "--sizes", "16,32,64")
    assert ns.sizes == "16,32,64"


@pytest.mark.unit
def test_image_contact_sheet_multiple_files():
    ns = _parse("contact-sheet", "a.jpg", "b.jpg", "c.jpg", "--cols", "3")
    assert ns.image_op == "contact-sheet"
    assert ns.files == ["a.jpg", "b.jpg", "c.jpg"]
    assert ns.cols == 3


@pytest.mark.unit
def test_image_remove_bg_model():
    ns = _parse("remove-bg", "photo.jpg", "--model", "u2netp")
    assert ns.model == "u2netp"


@pytest.mark.unit
def test_image_describe_prompt():
    ns = _parse("describe", "photo.jpg", "--prompt", "What is in this image?")
    assert ns.prompt == "What is in this image?"


@pytest.mark.unit
def test_image_func_is_callable():
    ns = _parse("convert", "photo.jpg")
    assert callable(ns.func)


@pytest.mark.unit
def test_run_image_cli_convert_dispatches_to_pipeline(mocker, tmp_path):
    """image convert FILE → ImageArgs with operation='convert' and single item."""
    mocker.patch("src.utils.check_dependencies")
    mock_pipeline = mocker.patch(
        "src.gui.modules.image.worker.run_image_pipeline",
        return_value=True,
    )
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"")
    ns = _parse("convert", str(f), "--fmt", "webp", "--quality", "82")
    ns.func(ns)
    assert mock_pipeline.called
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "convert"
    assert args.fmt == "webp"
    assert args.quality == 82
    assert len(args.items) == 1


@pytest.mark.unit
def test_run_image_cli_contact_sheet_collects_multiple_items(mocker, tmp_path):
    """image contact-sheet FILES... → multiple items, op normalised to snake_case."""
    mocker.patch("src.utils.check_dependencies")
    mock_pipeline = mocker.patch(
        "src.gui.modules.image.worker.run_image_pipeline",
        return_value=True,
    )
    files = []
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        p = tmp_path / name
        p.write_bytes(b"")
        files.append(str(p))
    ns = _parse("contact-sheet", *files, "--cols", "3")
    ns.func(ns)
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "contact_sheet"
    assert len(args.items) == 3
