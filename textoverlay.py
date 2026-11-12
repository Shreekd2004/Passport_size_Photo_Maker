"""Text overlay (customer name / dates / custom text) drawn onto the processed photograph.

Three positions:
  inside - bottom centre of the photograph
  below  - OUTSIDE image: a text strip is ADDED under the photograph (total height grows)
  fixed  - FIXED CANVAS: the text area is carved out of the selected size, so photo + text together are
           EXACTLY the selected width x height (e.g. 40 mm photo + 5 mm text = 45 mm)

The text is applied BEFORE copies are made (every duplicate is identical), the uploaded file is never touched, and
the text is baked into the pixels - so PNG, JPG and PDF exports match. Changing any text setting re-renders from the
cached cut-out; the AI background removal is never repeated.
"""
import datetime
import functools
import os
from dataclasses import asdict, dataclass, fields
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
POSITIONS = ("inside", "below", "fixed")
MIN_FIXED_MM, MAX_FIXED_FRACTION = 2.0, 0.45     # fixed text area is kept between 2 mm and 45 % of the height


@dataclass
class TextStyle:
    enabled: bool = False
    # ---- content (each ticked item becomes a line / part of the text) ----
    use_name: bool = False
    name: str = ""                  # "" -> the photo's customer-name label (usually from the file name)
    use_custom: bool = False
    custom: str = ""
    use_dob: bool = False
    dob: str = ""                   # date of birth, e.g. 15/08/2002
    use_date: bool = False          # photograph date
    date_mode: str = "today"        # today | manual
    date_text: str = ""
    use_cdate: bool = False
    cdate: str = ""                 # any other date
    multiline: bool = False         # one item per line (otherwise joined on one line with  |  )
    # ---- look ----
    font: str = FONT_CHOICES[0]
    bold: bool = False
    size_pt: float = 9.0
    color: tuple = (0, 0, 0)
    align: str = "center"           # left | center | right
    position: str = "inside"        # inside | below | fixed
    area_mm: float = 5.0            # height of the text area for position == "fixed"
    voff_mm: float = 0.0            # vertical position: + moves up, - moves down
    bg_on: bool = True              # inside: band behind the text; below / fixed: colour of the text area
    bg_color: tuple = (255, 255, 255)

    def sig(self):
        return tuple(sorted(asdict(self).items()))

    def to_dict(self):
        d = asdict(self)
        d["color"], d["bg_color"] = list(d["color"]), list(d["bg_color"])
        return d

    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in fields(cls)}
        out = {k: v for k, v in (d or {}).items() if k in known}
        for k in ("color", "bg_color"):
            if k in out:
                out[k] = tuple(int(x) for x in out[k])
        return cls(**out)


def resolve_text(ts, label, today=None):
    """The final string for one photograph ('' when nothing to print). Items keep a fixed order."""
    if not ts.enabled:
        return ""
    parts = []
    if ts.use_name:
        n = (ts.name or label or "").strip()
        if n:
            parts.append(n)
    if ts.use_custom and ts.custom.strip():
        parts.append(ts.custom.strip())
    if ts.use_dob and ts.dob.strip():
        parts.append(ts.dob.strip())
    if ts.use_date:
        d = ts.date_text.strip() if ts.date_mode == "manual" else (today or datetime.date.today()).strftime("%d/%m/%Y")
        if d:
            parts.append(d)
    if ts.use_cdate and ts.cdate.strip():
        parts.append(ts.cdate.strip())
    return ("\n" if ts.multiline else "  |  ").join(parts)


def n_lines(ts):
    """How many lines the text will normally need (used to size an outside strip consistently)."""
    if not ts.multiline:
        return 1
    n = (1 if ts.use_name else 0) + (1 if ts.use_custom and ts.custom.strip() else 0) \
        + (1 if ts.use_dob and ts.dob.strip() else 0) + (1 if ts.use_date and (ts.date_mode == "today" or ts.date_text.strip()) else 0) \
        + (1 if ts.use_cdate and ts.cdate.strip() else 0)
    return max(1, n)


def caption_mm(ts):
    """OUTSIDE mode: height of the strip ADDED below each photo (same for every photo -> tidy grid)."""
    if not (ts.enabled and ts.position == "below"):
        return 0.0
    return round(ts.size_pt * 0.3528 * 1.3 * n_lines(ts) + 2.0, 1)


def fixed_mm(ts, photo_h_mm):
    """FIXED CANVAS mode: height of the text area carved out of the photo size (0 when not in this mode)."""
    if not (ts.enabled and ts.position == "fixed"):
        return 0.0
    return round(min(max(float(ts.area_mm), MIN_FIXED_MM), MAX_FIXED_FRACTION * photo_h_mm), 2)


def _font_path(family, bold):
    if family in _WIN_FILES:
        win = os.environ.get("WINDIR") or r"C:\Windows"
        p = Path(win) / "Fonts" / _WIN_FILES[family][1 if bold else 0]
        if p.is_file():
            return str(p)
    p = model.resource_dir() / "assets" / "fonts" / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return str(p) if p.is_file() else None


@functools.lru_cache(maxsize=96)
def get_font(family, bold, px):
    path = _font_path(family, bold)
    try:
        if path:
            return ImageFont.truetype(path, px)
    except OSError:
        pass
    return ImageFont.load_default(size=px)


def _px(pt, ppm):
    return max(5, int(round(pt * 25.4 / 72.0 * ppm)))


def _fit(ts, lines, ppm, max_w, max_h):
    """Largest font (<= the chosen size) whose text fits the width AND height - so nothing is ever clipped.
    If even the smallest legible font does not fit, long lines are shortened with '...'."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    px = _px(ts.size_pt, ppm)
    while True:
        font = get_font(ts.font, ts.bold, px)
        asc, desc = font.getmetrics()
        widths = [probe.textlength(l, font=font) for l in lines]
        if (max(widths, default=0) <= max_w and (asc + desc) * len(lines) <= max_h) or px <= 5:
            break
        px -= 1
    out = []
    for l in lines:
        while len(l) > 1 and probe.textlength(l, font=font) > max_w:
            l = l[:-2].rstrip() + "..." if not l.endswith("...") else l[:-4].rstrip() + "..."
        out.append(l)
    return font, out, [probe.textlength(l, font=font) for l in out]


def _draw_block(img, ts, text, ppm, area, anchor):
    lines = text.split("\n")
    x0, y0, x1, y1 = area
    hm = max(1, int(round(1.2 * ppm)))                    # side margin
    vm = max(1, int(round(0.3 * ppm)))                    # top/bottom margin
    max_h = (y1 - y0) * 0.5 if anchor == "bottom" else (y1 - y0) - 2 * vm
    font, lines, widths = _fit(ts, lines, ppm, (x1 - x0) - 2 * hm, max_h)
    asc, desc = font.getmetrics()
    lh = asc + desc
    block_h = lh * len(lines)
    voff = int(round(ts.voff_mm * ppm))
    if anchor == "bottom":
        top = y1 - hm - block_h - voff
    else:
        top = y0 + ((y1 - y0) - block_h) // 2 - voff
    top = min(max(top, y0), max(y0, y1 - block_h))       # always inside the area

    def line_x(w):
        if ts.align == "left":
            return x0 + hm
        if ts.align == "right":
            return x1 - hm - w
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
    """photo (RGB) -> cell image.
    inside: text on the photo.  below / fixed: the photo with a text strip of strip_px stacked under it.
    (For 'fixed' the caller already made the photo shorter by strip_px, so the total stays the selected size.)"""
    if not ts.enabled:
        return photo
    W, H = photo.size
    if ts.position in ("below", "fixed"):
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
