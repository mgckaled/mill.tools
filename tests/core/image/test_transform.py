import pytest
from pathlib import Path
from PIL import Image


# ── resize_image ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_resize_contain_respects_aspect_ratio(jpg_image, out_dir):
    from src.core.image.transform import resize_image
    out = resize_image(
        jpg_image, out_dir,
        resize_mode="contain", width=100, height=100,
        scale_pct=100.0, out_fmt=None, quality=85,
    )
    assert out.exists()
    with Image.open(out) as im:
        assert im.width <= 100
        assert im.height <= 100


@pytest.mark.unit
def test_resize_exact_ignores_aspect_ratio(jpg_image, out_dir):
    from src.core.image.transform import resize_image
    out = resize_image(
        jpg_image, out_dir,
        resize_mode="exact", width=50, height=80,
        scale_pct=100.0, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (50, 80)


@pytest.mark.unit
def test_resize_scale_pct(jpg_image, out_dir):
    from src.core.image.transform import resize_image
    with Image.open(jpg_image) as src:
        orig_w, orig_h = src.size
    out = resize_image(
        jpg_image, out_dir,
        resize_mode="scale_pct", width=None, height=None,
        scale_pct=50.0, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.width == orig_w // 2
        assert im.height == orig_h // 2


@pytest.mark.unit
def test_resize_converts_format(jpg_image, out_dir):
    """Conversão de formato junto com resize."""
    from src.core.image.transform import resize_image
    out = resize_image(
        jpg_image, out_dir,
        resize_mode="contain", width=100, height=100,
        scale_pct=100.0, out_fmt="png", quality=85,
    )
    assert out.suffix.lower() == ".png"


# ── crop_image ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_crop_manual(jpg_image, out_dir):
    from src.core.image.transform import crop_image
    out = crop_image(
        jpg_image, out_dir,
        crop_mode="manual", left=10, top=10,
        crop_width=50, crop_height=50,
        ratio="4:3", trim_color="#ffffff",
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (50, 50)


@pytest.mark.unit
def test_crop_ratio_16_9(jpg_image, out_dir):
    from src.core.image.transform import crop_image
    out = crop_image(
        jpg_image, out_dir,
        crop_mode="ratio", left=0, top=0,
        crop_width=0, crop_height=0,
        ratio="16:9", trim_color="#ffffff",
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        w, h = im.size
        ratio = w / h
        assert abs(ratio - 16 / 9) < 0.1


@pytest.mark.unit
def test_crop_autotrim_white_bg(tmp_path, out_dir):
    """Auto-trim remove bordas brancas (PNG lossless evita artefatos JPEG)."""
    from src.core.image.transform import crop_image
    from PIL import ImageDraw
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 79, 79], fill=(0, 0, 200))
    # PNG garante que a área branca seja exatamente (255,255,255) sem artefatos
    src = tmp_path / "white_border.png"
    img.save(src)
    out = crop_image(
        src, out_dir,
        crop_mode="autotrim", left=0, top=0,
        crop_width=0, crop_height=0,
        ratio="1:1", trim_color="#ffffff",
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.width < 100
        assert im.height < 100


# ── rotate_image ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("angle, expected_size", [
    (0,   (200, 150)),
    (90,  (150, 200)),
    (180, (200, 150)),
    (270, (150, 200)),
])
def test_rotate_angle_swaps_dimensions(jpg_image, out_dir, angle, expected_size):
    from src.core.image.transform import rotate_image
    out = rotate_image(
        jpg_image, out_dir,
        angle=angle, flip_h=False, flip_v=False,
        exif_auto=False, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == expected_size


@pytest.mark.unit
def test_rotate_flip_horizontal(jpg_image, out_dir):
    from src.core.image.transform import rotate_image
    out = rotate_image(
        jpg_image, out_dir,
        angle=0, flip_h=True, flip_v=False,
        exif_auto=False, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (200, 150)


# ── add_border ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_add_border_increases_size(jpg_image, out_dir):
    from src.core.image.transform import add_border
    out = add_border(
        jpg_image, out_dir,
        padding=10, color="#000000",
        fill_alpha=False, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.width == 220   # 200 + 10*2
        assert im.height == 170  # 150 + 10*2


@pytest.mark.unit
def test_add_border_to_png_rgba(png_image, out_dir):
    """PNG RGBA com fill_alpha=True deve converter para RGB antes da borda."""
    from src.core.image.transform import add_border
    out = add_border(
        png_image, out_dir,
        padding=5, color="#ffffff",
        fill_alpha=True, out_fmt="png", quality=85,
    )
    assert out.exists()


# ── adjust_image ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_adjust_identity_does_not_crash(jpg_image, out_dir):
    """Todos os valores em 1.0 (identidade) não deve alterar dimensões."""
    from src.core.image.transform import adjust_image
    out = adjust_image(
        jpg_image, out_dir,
        brightness=1.0, contrast=1.0, color=1.0, sharpness=1.0,
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (200, 150)


@pytest.mark.unit
@pytest.mark.parametrize("brightness", [0.5, 1.5, 2.0])
def test_adjust_brightness_variants(jpg_image, out_dir, brightness):
    from src.core.image.transform import adjust_image
    out = adjust_image(
        jpg_image, out_dir,
        brightness=brightness, contrast=1.0, color=1.0, sharpness=1.0,
        out_fmt=None, quality=85,
    )
    assert out.exists()


# ── apply_filter ──────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("filter_type", [
    "blur", "sharpen", "autocontrast", "equalize", "grayscale",
])
def test_apply_filter_all_types(jpg_image, out_dir, filter_type):
    from src.core.image.transform import apply_filter
    out = apply_filter(
        jpg_image, out_dir,
        filter_type=filter_type, out_fmt=None, quality=85,
    )
    assert out.exists()


@pytest.mark.unit
def test_apply_filter_grayscale_mode(jpg_image, out_dir):
    """PNG preserva mode L; JPEG converteria para RGB em _save."""
    from src.core.image.transform import apply_filter
    out = apply_filter(
        jpg_image, out_dir,
        filter_type="grayscale", out_fmt="png", quality=85,
    )
    with Image.open(out) as im:
        assert im.mode == "L"


# ── make_favicon ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_make_favicon_creates_ico(jpg_image, out_dir):
    from src.core.image.transform import make_favicon
    out = make_favicon(jpg_image, out_dir, sizes=[16, 32, 48])
    assert out.exists()
    assert out.suffix.lower() == ".ico"


# ── make_contact_sheet ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_make_contact_sheet_single_image(jpg_image, out_dir):
    from src.core.image.transform import make_contact_sheet
    out = make_contact_sheet(
        [jpg_image], out_dir,
        cols=3, thumb_size=100, gap=5,
        bg_color="#cccccc", out_fmt="jpg", quality=85,
    )
    assert out.exists()


@pytest.mark.unit
def test_make_contact_sheet_empty_list_raises(out_dir):
    from src.core.image.transform import make_contact_sheet
    with pytest.raises(ValueError, match="Nenhum arquivo válido"):
        make_contact_sheet(
            [], out_dir,
            cols=3, thumb_size=100, gap=5,
            bg_color="#ffffff", out_fmt="jpg", quality=85,
        )


@pytest.mark.unit
def test_make_contact_sheet_invalid_files_ignored(jpg_image, tmp_path, out_dir):
    """Arquivos inválidos são ignorados; válidos são processados."""
    invalid = tmp_path / "not_an_image.txt"
    invalid.write_text("not an image")
    from src.core.image.transform import make_contact_sheet
    out = make_contact_sheet(
        [invalid, jpg_image], out_dir,
        cols=2, thumb_size=80, gap=4,
        bg_color="#ffffff", out_fmt="png", quality=85,
    )
    assert out.exists()


# ── _out_path (anti-colisão) ──────────────────────────────────────────────────

@pytest.mark.unit
def test_out_path_no_collision(jpg_image, out_dir):
    """Segunda chamada com mesmo src deve gerar nome diferente."""
    from src.core.image.transform import _out_path
    p1 = _out_path(jpg_image, out_dir, None)
    p1.touch()
    p2 = _out_path(jpg_image, out_dir, None)
    assert p1 != p2


# ── crop_image — branches adicionais ─────────────────────────────────────────

@pytest.mark.unit
def test_crop_ratio_height_clamp(jpg_image, out_dir):
    """Branch if target_h > ih: imagem 200×150 + ratio 1:1 → target_h=200>150."""
    from src.core.image.transform import crop_image
    out = crop_image(
        jpg_image, out_dir,
        crop_mode="ratio", left=0, top=0,
        crop_width=0, crop_height=0,
        ratio="1:1", trim_color="#ffffff",
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (150, 150)


@pytest.mark.unit
def test_crop_autotrim_uniform_image_unchanged(tmp_path, out_dir):
    """Imagem uniforme == trim_color: diff todo zero, getbbox()=None, sem recorte."""
    from src.core.image.transform import crop_image
    img = Image.new("RGB", (100, 100), (255, 0, 0))
    src = tmp_path / "solid_red.png"
    img.save(src)
    out = crop_image(
        src, out_dir,
        crop_mode="autotrim", left=0, top=0,
        crop_width=0, crop_height=0,
        ratio="1:1", trim_color="#ff0000",
        out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (100, 100)


# ── rotate_image — branches adicionais ───────────────────────────────────────

@pytest.mark.unit
def test_rotate_exif_auto_true(jpg_image, out_dir):
    """exif_auto=True em imagem sem dados EXIF deve preservar dimensões."""
    from src.core.image.transform import rotate_image
    out = rotate_image(
        jpg_image, out_dir,
        angle=0, flip_h=False, flip_v=False,
        exif_auto=True, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (200, 150)


@pytest.mark.unit
def test_rotate_flip_vertical(jpg_image, out_dir):
    """flip_v=True deve preservar dimensões."""
    from src.core.image.transform import rotate_image
    out = rotate_image(
        jpg_image, out_dir,
        angle=0, flip_h=False, flip_v=True,
        exif_auto=False, out_fmt=None, quality=85,
    )
    with Image.open(out) as im:
        assert im.size == (200, 150)


# ── watermark_image — modo image ──────────────────────────────────────────────

@pytest.mark.unit
def test_watermark_image_mode(jpg_image, tmp_path, out_dir):
    """wm_mode='image' aplica marca d'água PNG RGBA sem alterar tamanho da base."""
    from src.core.image.transform import watermark_image
    wm_img = Image.new("RGBA", (30, 30), (0, 255, 0, 200))
    wm_path = tmp_path / "watermark.png"
    wm_img.save(wm_path)
    out = watermark_image(
        jpg_image, out_dir,
        wm_mode="image", text="", text_color="#000000", text_size=20,
        wm_path=wm_path, position="bottom-right", opacity=0.8,
        out_fmt="png", quality=85,
    )
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (200, 150)


# ── watermark_image — modo texto ─────────────────────────────────────────────

@pytest.mark.unit
def test_watermark_text_mode(jpg_image, out_dir):
    """wm_mode='text' renderiza texto sobre a imagem sem alterar dimensões."""
    from src.core.image.transform import watermark_image
    out = watermark_image(
        jpg_image, out_dir,
        wm_mode="text", text="TESTE", text_color="#ffffff", text_size=16,
        wm_path=None, position="top-left", opacity=0.9,
        out_fmt="png", quality=85,
    )
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (200, 150)


# ── make_favicon — fallback de tamanho ───────────────────────────────────────

@pytest.mark.unit
def test_make_favicon_size_fallback(tmp_path, out_dir):
    """Quando todos os sizes > imagem, fallback usa (min_dim, min_dim)."""
    from src.core.image.transform import make_favicon
    small = Image.new("RGB", (10, 10), (255, 0, 0))
    src = tmp_path / "tiny.png"
    small.save(src)
    out = make_favicon(src, out_dir, sizes=[32, 48, 64])
    assert out.exists()
    assert out.suffix.lower() == ".ico"


# ── make_contact_sheet — except no loop de paste ──────────────────────────────

@pytest.mark.unit
def test_make_contact_sheet_paste_failure_is_ignored(jpg_image, out_dir, mocker):
    """Arquivo válido no verify que falha no paste é silenciosamente ignorado."""
    from PIL import Image as PILImage
    original_open = PILImage.open
    call_count = {"n": 0}

    def selective_open(path, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("mocked paste failure")
        return original_open(path, *args, **kwargs)

    mocker.patch("PIL.Image.open", side_effect=selective_open)
    from src.core.image.transform import make_contact_sheet
    out = make_contact_sheet(
        [jpg_image], out_dir,
        cols=1, thumb_size=50, gap=2,
        bg_color="#eeeeee", out_fmt="png", quality=85,
    )
    assert out.exists()


# ── _wm_coords (helper watermark) ─────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("position, expected", [
    ("top-left",     (10, 10)),
    ("top-right",    (170, 10)),    # 200 - 20 - 10 = 170
    ("bottom-left",  (10, 120)),    # 150 - 20 - 10 = 120
    ("center",       (90, 65)),     # (200-20)//2=90, (150-20)//2=65
    ("bottom-right", (170, 120)),
])
def test_wm_coords(position, expected):
    from src.core.image.transform import _wm_coords
    result = _wm_coords(iw=200, ih=150, ww=20, wh=20, position=position, margin=10)
    assert result == expected
