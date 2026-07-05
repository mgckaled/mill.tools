"""Pillow-based image manipulation ops (pure, no Flet).

Split into _shared.py (IO/format helpers), watermark.py and ops.py (everything
else) — this file re-exports the flat public API so every existing call site
(``from src.core.image.transform import X``) keeps working unchanged.
"""

from __future__ import annotations

from src.core.image.transform._shared import _hex_rgb as _hex_rgb
from src.core.image.transform._shared import _out_path as _out_path
from src.core.image.transform._shared import _save as _save
from src.core.image.transform.ops import add_border as add_border
from src.core.image.transform.ops import adjust_image as adjust_image
from src.core.image.transform.ops import apply_filter as apply_filter
from src.core.image.transform.ops import apply_filter_im as apply_filter_im
from src.core.image.transform.ops import crop_image as crop_image
from src.core.image.transform.ops import _ensure_rgb as _ensure_rgb
from src.core.image.transform.ops import make_contact_sheet as make_contact_sheet
from src.core.image.transform.ops import make_favicon as make_favicon
from src.core.image.transform.ops import resize_image as resize_image
from src.core.image.transform.ops import rotate_image as rotate_image
from src.core.image.transform.watermark import _build_wm_stamp as _build_wm_stamp
from src.core.image.transform.watermark import _qr_rgba as _qr_rgba
from src.core.image.transform.watermark import _tile_watermark as _tile_watermark
from src.core.image.transform.watermark import _wm_coords as _wm_coords
from src.core.image.transform.watermark import watermark_image as watermark_image
