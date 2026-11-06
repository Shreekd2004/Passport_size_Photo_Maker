"""Sheet layout: continuous sequential packing, orientation optimiser, cutting guides, page builder, export."""
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw

from units import DPI, mm_to_px

GUIDE_MIN_GAP_MM = 2.0     # gaps are widened to this when cutting guides are on, so guides never touch a photo


class LayoutError(Exception):
    pass


@dataclass
class LayoutSpec:
    photo_w: float = 35.0          # mm
    photo_h: float = 45.0          # mm
    head: float = 0.74
    caption_mm: float = 0.0        # text strip BELOW each photo (0 = none)
    paper_name: str = "A4"
    paper_w: float = 210.0         # mm
    paper_h: float = 297.0         # mm
    orientation: str = "auto"      # auto | portrait | landscape
    margin: float = 5.0
    hgap: float = 4.0
    vgap: float = 4.0
    border: bool = True
    border_px: int = 3
    guides: str = "none"           # none | thin | dotted
    mode: str = "continuous"       # continuous | group


def grid(spec, landscape):
    """Real printable grid: how many cells fit across / down for this orientation (all sizes in px @300 DPI)."""
    pw, ph = (spec.paper_h, spec.paper_w) if landscape else (spec.paper_w, spec.paper_h)
    PW, PH = mm_to_px(pw), mm_to_px(ph)
    m = mm_to_px(spec.margin)
    hg, vg = mm_to_px(spec.hgap), mm_to_px(spec.vgap)
    if spec.guides != "none":
        gmin = mm_to_px(GUIDE_MIN_GAP_MM)
        hg, vg = max(hg, gmin), max(vg, gmin)
    w, h = mm_to_px(spec.photo_w), mm_to_px(spec.photo_h)
    cap = mm_to_px(spec.caption_mm) if spec.caption_mm > 0 else 0
    ch = h + cap
    cols = (PW - 2 * m + hg) // (w + hg) if w > 0 else 0
    rows = (PH - 2 * m + vg) // (ch + vg) if ch > 0 else 0
    return dict(PW=PW, PH=PH, m=m, hg=hg, vg=vg, w=w, h=h, cap=cap, ch=ch,
                cols=int(max(0, cols)), rows=int(max(0, rows)), landscape=landscape)


def fill(cols, rows, counts, group):
    """Place copies in upload order. Continuous: every free slot is used before moving on.
    Group: each photograph starts on a fresh row. Returns pages = [[(row, col, photo_index), ...], ...]."""
    pages = [[]]
    r = c = 0
    for idx, n in enumerate(counts):
        if n <= 0:
            continue
        if group and c != 0:
            r, c = r + 1, 0
        for _ in range(n):
            if c >= cols:
                r, c = r + 1, 0
            if r >= rows:
                pages.append([])
                r = 0
            pages[-1].append((r, c, idx))
            c += 1
    if len(pages) > 1 and not pages[-1]:
        pages.pop()
    return pages


def choose(spec, counts):
    """Pick the orientation that needs the fewest sheets (portrait wins ties). -> (pages, grid, positions)."""
    lands = [False, True] if spec.orientation == "auto" else [spec.orientation == "landscape"]
    opts = []
    for land in lands:
        g = grid(spec, land)
        if g["cols"] < 1 or g["rows"] < 1:
            continue
        pages = fill(g["cols"], g["rows"], counts, spec.mode == "group")
        opts.append((len(pages), land, g, pages))
    if not opts:
        raise LayoutError(
            f"A {spec.photo_w:g} x {spec.photo_h:g} mm photo does not fit on {spec.paper_name} paper "
            f"with a {spec.margin:g} mm margin. Reduce the margin / spacing or choose bigger paper.")
    opts.sort(key=lambda o: (o[0], o[1]))
    n, land, g, pages = opts[0]
    return n, g, pages


def _line(d, p1, p2, width, dotted):
    (x1, y1), (x2, y2) = p1, p2
    if not dotted:
        d.line([p1, p2], fill=(0, 0, 0), width=width)
        return
    dash, gap = 9, 9
    if y1 == y2:
        x = x1
        while x < x2:
            d.line([(x, y1), (min(x + dash, x2), y1)], fill=(0, 0, 0), width=width)
            x += dash + gap
    else:
        y = y1
        while y < y2:
            d.line([(x1, y), (x1, min(y + dash, y2))], fill=(0, 0, 0), width=width)
            y += dash + gap


def _draw_guides(d, g, cells, x0, dotted):
    """Cutting guides run through the CENTRE of the gaps, so they can never overlap a photograph."""
    if not cells:
        return
    rs, cs = [r for r, _ in cells], [c for _, c in cells]
    r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
    w, ch, hg, vg, m = g["w"], g["ch"], g["hg"], g["vg"], g["m"]
    left = max(0, x0 + c0 * (w + hg) - hg // 2)
    right = x0 + (c1 + 1) * (w + hg) - hg // 2
    top = max(0, m + r0 * (ch + vg) - vg // 2)
    bottom = m + (r1 + 1) * (ch + vg) - vg // 2
    for c in range(c0, c1 + 2):
        x = max(0, x0 + c * (w + hg) - hg // 2)
        _line(d, (x, top), (x, bottom), 2, dotted)
    for r in range(r0, r1 + 2):
        y = max(0, m + r * (ch + vg) - vg // 2)
        _line(d, (left, y), (right, y), 2, dotted)


def build_pages(spec, items):
    """items = [(cell_image, photo_height_px, copies), ...] in upload order -> list of 300-DPI page images."""
    counts = [c for _, _, c in items]
    if not any(c > 0 for c in counts):
        raise LayoutError("All copy counts are 0 - nothing to print.")
    _, g, positions = choose(spec, counts)
    PW, PH, m, hg, vg, w, ch, cols = (g[k] for k in ("PW", "PH", "m", "hg", "vg", "w", "ch", "cols"))
    grid_w = cols * w + (cols - 1) * hg
    x0 = m + max(0, (PW - 2 * m - grid_w) // 2)
    pages = []
    for cells in positions:
        im = Image.new("RGB", (PW, PH), (255, 255, 255))
        d = ImageDraw.Draw(im)
        for r, c, idx in cells:
            cell, ph, _ = items[idx]
            x, y = x0 + c * (w + hg), m + r * (ch + vg)
            im.paste(cell, (x, y))
            if spec.border and spec.border_px > 0:
                d.rectangle([x, y, x + w - 1, y + ph - 1], outline=(0, 0, 0), width=int(spec.border_px))
        if spec.guides != "none":
            _draw_guides(d, g, [(r, c) for r, c, _ in cells], x0, spec.guides == "dotted")
        pages.append(im)
    return pages


def summary(spec, counts=None):
    """Human-readable capacity line for the Layout tab."""
    n, g, pos = choose(spec, counts if counts and any(counts) else [1])
    per = g["cols"] * g["rows"]
    t = (f"{g['cols']} x {g['rows']} = {per} photos per sheet "
         f"({'landscape' if g['landscape'] else 'portrait'}, {spec.paper_name})")
    if counts and any(counts):
        t += f"  -  {sum(counts)} photos need {n} sheet{'s' if n != 1 else ''}"
    return t


def default_basename(spec):
    import datetime
    return f"SnapMitra_{spec.paper_name.replace(' ', '')}_{datetime.datetime.now():%Y%m%d_%H%M%S}"


def save_pages(pages, path, fmt):
    """Save at 300 DPI. PDF = one multi-page file with exact physical page size. Returns the file list."""
    base, _ = os.path.splitext(path)
    fmt = fmt.upper()
    if fmt == "PDF":
        out = base + ".pdf"
        pages[0].save(out, "PDF", resolution=float(DPI), save_all=True, append_images=pages[1:], quality=95)
        return [out]
    ext = ".png" if fmt == "PNG" else ".jpg"
    outs = []
    n = len(pages)
    for i, pg in enumerate(pages, 1):
        f = base + ext if n == 1 else f"{base}_page{i}of{n}{ext}"
        if fmt == "PNG":
            pg.save(f, "PNG", dpi=(DPI, DPI))
        else:
            pg.save(f, "JPEG", quality=95, subsampling=0, dpi=(DPI, DPI))
        outs.append(f)
    return outs
