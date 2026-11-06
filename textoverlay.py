"""Text overlay (customer name / date / custom text) drawn onto the processed photograph.

Applied BEFORE copies are made, so every duplicate carries the same overlay, the uploaded file is never touched,
and the text is baked into the pixels - so PNG, JPG and PDF exports are identical.
"""
import datetime
import functools
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import model

BUILTIN_FONT = "Built-in (DejaVu Sans)"
FONT_CHOICES = ["Segoe UI", "Arial", "Calibri", "Times New Roman", "Verdana", "Tahoma", "Courier New", BUILTIN_FONT]
_WIN_FILES = {
    "Segoe UI": ("segoeui.ttf", "segoeuib.ttf"), "Arial": ("arial.ttf", "arialbd.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf"), "Times New Roman": ("times.ttf", "timesbd.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf"), "Tahoma": ("tahoma.ttf", "tahomabd.ttf"),
    "Courier New": ("cour.ttf", "courbd.ttf"),
}


@dataclass
class TextStyle:
    enabled: bool = False
    source: str = "custom"          # custom | name (per-photo customer name)
    custom: str = ""
    use_date: bool = False
    date_mode: str = "today"        # today | manual
    date_text: str = ""
    two_lines: bool = False         # put the date on its own line
    font: str = FONT_CHOICES[0]
    bold: bool = False
    size_pt: float = 9.0
    color: tuple = (0, 0, 0)
    align: str = "center"           # left | center | right
    position: str = "inside"        # inside (bottom centre of the photo) | below (strip under the photo)
    voff_mm: float = 0.0            # vertical position: + moves up, - moves down
    bg_on: bool = True
    bg_color: tuple = (255, 255, 255)

    def sig(self):
        return tuple(sorted(asdict(self).items()))


def resolve_text(ts, label, today=None):
    """The final string for one photograph ('' when nothing to print)."""
    if not ts.enabled:
        return ""
    parts = []
    base = (label if ts.source == "name" else ts.custom).strip()
    if base:
        parts.append(base)
    if ts.use_date:
        d = ts.date_text.strip() if ts.date_mode == "manual" else (today or datetime.date.today()).strftime("%d/%m/%Y")
        if d:
            parts.append(d)
    return ("\n" if ts.two_lines else "  |  ").join(parts)


def caption_mm(ts):
    """Height of the strip reserved under each photo in 'below' mode (same for every photo -> tidy grid)."""
    if not (ts.enabled and ts.position == "below"):
        return 0.0
    lines = 2 if (ts.two_lines and ts.use_date) else 1
    return round(ts.size_pt * 0.3528 * 1.3 * lines + 2.0, 1)


def _font_path(family, bold):
    if family in _WIN_FILES:
        win = os.environ.get("WINDIR") or r"C:\Windows"
        p = Path(win) / "Fonts" / _WIN_FILES[family][1 if bold else 0]
        if p.is_file():
            return str(p)
    p = model.resource_dir() / "assets" / "fonts" / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return str(p) if p.is_file() else None


@functools.lru_cache(maxsize=64)
def get_font(family, bold, px):
    path = _font_path(family, bold)
    try:
        if path:
            return ImageFont.truetype(path, px)
    except OSError:
        pass
    return ImageFont.load_default(size=px)


def _px(pt, ppm):
    return max(6, int(round(pt * 25.4 / 72.0 * ppm)))


def _fit(ts, lines, ppm, max_w):
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    px = _px(ts.size_pt, ppm)
    while True:
        font = get_font(ts.font, ts.bold, px)
        widths = [probe.textlength(l, font=font) for l in lines]
        if max(widths, default=0) <= max_w or px <= 6:
            return font, widths
        px -= 1                                  # shrink long names so they always fit the photo width


def _draw_block(img, ts, text, ppm, area, anchor):
    lines = text.split("\n")
    x0, y0, x1, y1 = area
    margin = int(round(1.5 * ppm))
    font, widths = _fit(ts, lines, ppm, (x1 - x0) - 2 * margin)
    asc, desc = font.getmetrics()
    lh = asc + desc
    block_h = lh * len(lines)
    voff = int(round(ts.voff_mm * ppm))
    if anchor == "bottom":
        top = y1 - margin - block_h - voff
    else:
        top = y0 + ((y1 - y0) - block_h) // 2 - voff
    top = max(y0, min(top, y1 - block_h))

    def line_x(w):
        if ts.align == "left":
            return x0 + margin
        if ts.align == "right":
            return x1 - margin - w
        return x0 + ((x1 - x0) - w) / 2.0

    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    if ts.bg_on and anchor == "bottom":
        bw = max(widths)
        bx = line_x(bw)
        pad = int(round(0.8 * ppm))
        d.rectangle([bx - pad, top - pad // 2, bx + bw + pad, top + block_h + pad // 2], fill=(*ts.bg_color, 215))
    for i, line in enumerate(lines):
        d.text((line_x(widths[i]), top + i * lh), line, font=font, fill=(*ts.color, 255))
    base = img.convert("RGBA")
    base.alpha_composite(ov)
    return base.convert("RGB")


def apply(photo, ts, text, ppm, strip_px=0):
    """photo (RGB) -> cell image. 'inside': text on the photo. 'below': photo + a text strip under it."""
    if not ts.enabled:
        return photo
    W, H = photo.size
    if ts.position == "below":
        if strip_px <= 0:
            return photo
        strip = Image.new("RGB", (W, strip_px), ts.bg_color if ts.bg_on else (255, 255, 255))
        if text:
            strip = _draw_block(strip, ts, text, ppm, (0, 0, W, strip_px), "center")
        cell = Image.new("RGB", (W, H + strip_px), (255, 255, 255))
        cell.paste(photo, (0, 0))
        cell.paste(strip, (0, H))
        return cell
    if not text:
        return photo
    return _draw_block(photo, ts, text, ppm, (0, 0, W, H), "bottom")
