"""Sheet layout: grid maths, orientation optimiser, page builder, file export."""
import math
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw

from units import DPI, mm_to_px


class LayoutError(Exception):
    pass


@dataclass
class LayoutSpec:
    photo_w: float = 35.0
    photo_h: float = 45.0
    head: float = 0.74
    paper_name: str = "A4"
    paper_w: float = 210.0
    paper_h: float = 297.0
    orientation: str = "auto"      # auto | portrait | landscape
    margin: float = 5.0
    hgap: float = 4.0
    vgap: float = 3.0
    border: bool = True
    border_px: int = 3
    new_row: bool = True           # each person starts on a fresh row (easier to cut / hand out)


def grid(spec, landscape):
    pw, ph = (spec.paper_h, spec.paper_w) if landscape else (spec.paper_w, spec.paper_h)
    PW, PH = mm_to_px(pw), mm_to_px(ph)
    m, hg, vg = mm_to_px(spec.margin), mm_to_px(spec.hgap), mm_to_px(spec.vgap)
    w, h = mm_to_px(spec.photo_w), mm_to_px(spec.photo_h)
    cols = (PW - 2 * m + hg) // (w + hg) if w > 0 else 0
    rows = (PH - 2 * m + vg) // (h + vg) if h > 0 else 0
    return dict(PW=PW, PH=PH, m=m, hg=hg, vg=vg, w=w, h=h, cols=int(cols), rows=int(rows))


def pages_needed(g, counts, new_row):
    if g["cols"] < 1 or g["rows"] < 1:
        return None
    counts = [c for c in counts if c > 0]
    if not counts:
        return 1
    total_rows = sum(math.ceil(c / g["cols"]) for c in counts) if new_row else math.ceil(sum(counts) / g["cols"])
    return max(1, math.ceil(total_rows / g["rows"]))


def choose(spec, counts):
    """Pick the orientation that needs the fewest sheets (portrait wins ties)."""
    lands = [False, True] if spec.orientation == "auto" else [spec.orientation == "landscape"]
    opts = []
    for land in lands:
        g = grid(spec, land)
        n = pages_needed(g, counts, spec.new_row)
        if n is not None:
            opts.append((n, land, g))
    if not opts:
        raise LayoutError(
            f"A {spec.photo_w:g} x {spec.photo_h:g} mm photo does not fit on {spec.paper_name} "
            f"paper with a {spec.margin:g} mm margin. Reduce the margin / spacing or choose bigger paper.")
    opts.sort(key=lambda o: (o[0], o[1]))
    return opts[0]


def build_pages(spec, items):
    """items = [(photo_image_at_print_size, copies), ...] -> list of page images (300 DPI)."""
    counts = [c for _, c in items]
    if not any(c > 0 for c in counts):
        raise LayoutError("All copy counts are 0 - nothing to print.")
    _, land, g = choose(spec, counts)
    PW, PH, m, hg, vg, w, h, cols, rows = (g[k] for k in ("PW", "PH", "m", "hg", "vg", "w", "h", "cols", "rows"))
    grid_w = cols * w + (cols - 1) * hg
    x0 = m + max(0, (PW - 2 * m - grid_w) // 2)
    pages = []

    def new_page():
        im = Image.new("RGB", (PW, PH), (255, 255, 255))
        pages.append(im)
        return im, ImageDraw.Draw(im)

    im, d = new_page()
    row = col = 0
    for img, copies in items:
        if copies <= 0:
            continue
        if spec.new_row and col != 0:
            row, col = row + 1, 0
        for _ in range(copies):
            if col >= cols:
                row, col = row + 1, 0
            if row >= rows:
                im, d = new_page()
                row = 0
            x, y = x0 + col * (w + hg), m + row * (h + vg)
            im.paste(img, (x, y))
            if spec.border and spec.border_px > 0:
                d.rectangle([x, y, x + w - 1, y + h - 1], outline=(0, 0, 0), width=int(spec.border_px))
            col += 1
    return pages


def save_pages(pages, path, fmt):
    base, _ = os.path.splitext(path)
    fmt = fmt.upper()
    if fmt == "PDF":
        out = base + ".pdf"
        pages[0].save(out, "PDF", resolution=float(DPI), save_all=True, append_images=pages[1:], quality=95)
        return [out]
    ext = ".png" if fmt == "PNG" else ".jpg"
    outs = []
    for i, pg in enumerate(pages, 1):
        f = base + ext if len(pages) == 1 else f"{base}_{i}{ext}"
        if fmt == "PNG":
            pg.save(f, "PNG", dpi=(DPI, DPI))
        else:
            pg.save(f, "JPEG", quality=95, subsampling=0, dpi=(DPI, DPI))
        outs.append(f)
    return outs
