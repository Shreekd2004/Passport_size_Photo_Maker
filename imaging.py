"""Image pipeline: load -> mask (AI) -> face -> crop/adjust -> text overlay -> print-size cell.

The expensive AI step runs ONCE per photo. The original image, the mask and the face box are all kept, so changing
the background colour, switching background removal on/off, zoom, move, rotate, brightness, contrast, sharpness or
text re-renders instantly - the photo never has to be re-uploaded or re-processed.
"""
import math
import os

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

import model
import textoverlay
import units

MAX_SIDE = 1600  # working resolution: plenty for a print photo and far faster than full-size phone images


def default_edit():
    return dict(zoom=1.0, dx=0.0, dy=0.0, tilt=0.0, rot90=0, bright=0.0, contrast=0.0, sharp=0.0)


class Style:
    """Everything (besides size/layout) that changes how a photo looks."""
    def __init__(self, bg=(255, 255, 255), remove=True, text=None):
        self.bg = tuple(bg)
        self.remove = bool(remove)
        self.text = text or textoverlay.TextStyle()


def nice_label(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.replace("_", " ").replace("-", " ").strip()


class Photo:
    def __init__(self, path, copies=5, label=None):
        self.path = path
        self.name = os.path.basename(path)
        self.label = label if label is not None else nice_label(path)   # customer name for the text overlay
        self.copies = copies
        self.state = "new"          # new | queued | processing | ready | error
        self.error = ""
        self.src = None             # original image (RGB, working size) - kept for instant re-edits
        self.mask = None            # AI foreground mask (L) or None until needed
        self.face_rect = None
        self.face_checked = False
        self.edit = default_edit()
        self._layer = None
        self._geom = None
        self.cache_key = None
        self.cache_img = None
        self.thumb_key = None
        self.thumb_tk = None

    def duplicate(self):
        d = Photo(self.path, self.copies, self.label)
        d.src, d.mask, d.face_rect, d.face_checked = self.src, self.mask, self.face_rect, self.face_checked
        d.edit = dict(self.edit)
        d.state = self.state if self.state in ("ready", "error") else "new"
        d.error = self.error
        return d

    def reset_derived(self):
        self._layer = self._geom = self.cache_key = self.cache_img = self.thumb_key = None

    @property
    def face_found(self):
        return self.face_rect is not None

    def layer(self, remove):
        """RGBA image to crop from: original + AI mask (background removed) or the untouched original."""
        use_mask = bool(remove and self.mask is not None)
        if self._layer is None or self._layer[0] != use_mask:
            rgba = self.src.convert("RGBA")
            if use_mask:
                rgba.putalpha(self.mask)
            self._layer = (use_mask, rgba)
        return self._layer[1]

    def geom(self, remove):
        use_mask = bool(remove and self.mask is not None)
        if self._geom is None or self._geom[0] != use_mask:
            self._geom = (use_mask, analyse(self.src.size, self.mask if use_mask else None, self.face_rect))
        return self._geom[1]


def needs_processing(p, remove):
    return p.src is None or not p.face_checked or (remove and p.mask is None)


def load_image(path):
    im = Image.open(path)
    try:
        im.draft("RGB", (MAX_SIDE, MAX_SIDE))  # fast JPEG decode of huge phone photos, never below working size
    except Exception:
        pass
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        im = im.convert("RGBA")
        flat = Image.new("RGBA", im.size, (255, 255, 255, 255))
        flat.alpha_composite(im)
        im = flat
    im = im.convert("RGB")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return im


def detect_face(rgb):
    """Largest face as (x, y, w, h), or None. Never raises - the caller falls back to manual framing."""
    fm = model.get_face()
    if fm is None:
        return None
    try:
        return fm.detect(rgb)
    except Exception:  # noqa
        return None


def analyse(size, mask, face):
    """Head geometry in working-image pixels: horizontal centre, crown (top) and chin."""
    W, H = size
    top_mask, bottom = 0, H - 1
    m = None
    if mask is not None:
        m = np.asarray(mask) > 128
        rows = np.where(m.sum(axis=1) >= max(5, int(0.01 * W)))[0]
        if len(rows):
            top_mask, bottom = int(rows[0]), int(rows[-1])
    if face is not None:
        x, y, w, h = face
        cx = x + w / 2.0
        chin = y + h * 0.99                          # detector box bottom sits on the chin
        top = top_mask if m is not None else y - 0.25 * h
        if top >= y - 0.02 * h or top < y - 0.7 * h:   # mask miss or stray blob above the head
            top = y - 0.25 * h
        return dict(cx=cx, top=float(top), chin=float(chin), found=True)
    # no face: assume head & shoulders framing - the user can fine-tune with zoom / move (manual crop)
    top = float(top_mask if m is not None else H * 0.08)
    chin = top + 0.55 * max(1, (bottom - top) if m is not None else H * 0.9)
    cx = W / 2.0
    if m is not None:
        band = m[int(top): int(top) + max(2, int(0.25 * (bottom - top))), :]
        xs = np.where(band.any(axis=0))[0]
        if len(xs):
            cx = float(xs.mean())
    return dict(cx=cx, top=top, chin=chin, found=False)


def default_crop(g, head_ratio, aspect):
    hh = max(1.0, g["chin"] - g["top"])
    ch = hh / head_ratio
    top_margin = 0.28 * (1.0 - head_ratio) * ch
    return g["cx"], g["top"] - top_margin + ch / 2.0, ch * aspect, ch


def render(layer, g, edit, head_ratio, bg, out_w, out_h, ss=2):
    """Crop / rotate / zoom / adjust into an out_w x out_h RGB image on a solid background colour."""
    cx, cy, cw, ch = default_crop(g, head_ratio, out_w / float(out_h))
    z = max(0.2, float(edit["zoom"]))
    cw, ch = cw / z, ch / z
    cx += edit["dx"] * cw
    cy += edit["dy"] * ch
    th = math.radians(edit["rot90"] * 90 + edit["tilt"])
    cs, sn = math.cos(th), math.sin(th)
    W, H = int(out_w * ss), int(out_h * ss)
    coeffs = (cw / W * cs, -ch / H * sn, cx - 0.5 * cw * cs + 0.5 * ch * sn,
              cw / W * sn, ch / H * cs, cy - 0.5 * cw * sn - 0.5 * ch * cs)
    tile = layer.transform((W, H), Image.AFFINE, coeffs, resample=Image.BICUBIC)
    canvas = Image.new("RGB", (W, H), tuple(bg))
    canvas.paste(tile, mask=tile.getchannel("A"))
    if ss != 1:
        canvas = canvas.resize((out_w, out_h), Image.LANCZOS)
    if abs(edit["bright"]) > 0.5:
        canvas = ImageEnhance.Brightness(canvas).enhance(1 + edit["bright"] / 100.0)
    if abs(edit["contrast"]) > 0.5:
        canvas = ImageEnhance.Contrast(canvas).enhance(1 + edit["contrast"] / 100.0)
    if abs(edit.get("sharp", 0)) > 0.5:
        canvas = ImageEnhance.Sharpness(canvas).enhance(1 + edit["sharp"] / 100.0)
    return canvas


def render_cell(p, spec, style, out_w, ss=1):
    """Photo + text overlay at an arbitrary width (live preview). -> (cell, photo_height_px)"""
    ppm = out_w / spec.photo_w
    out_h = max(1, int(round(spec.photo_h * ppm)))
    photo = render(p.layer(style.remove), p.geom(style.remove), p.edit, spec.head, style.bg, out_w, out_h, ss)
    text = textoverlay.resolve_text(style.text, p.label)
    strip = int(round(spec.caption_mm * ppm)) if spec.caption_mm > 0 else 0
    return textoverlay.apply(photo, style.text, text, ppm, strip), out_h


def final_cell(p, spec, style, prog=None):
    """Print-resolution cell (cached until an edit / setting changes). -> (cell, photo_height_px)"""
    w, h = units.mm_to_px(spec.photo_w), units.mm_to_px(spec.photo_h)
    strip = units.mm_to_px(spec.caption_mm) if spec.caption_mm > 0 else 0
    text = textoverlay.resolve_text(style.text, p.label)
    key = (w, h, strip, round(spec.head, 3), style.bg, style.remove, tuple(sorted(p.edit.items())),
           style.text.sig(), text, p.mask is not None)
    if p.cache_key == key and p.cache_img is not None:
        return p.cache_img
    if prog:
        prog("Cropping photograph")
    photo = render(p.layer(style.remove), p.geom(style.remove), p.edit, spec.head, style.bg, w, h, ss=2)
    if prog:
        prog("Applying text overlay")
    cell = textoverlay.apply(photo, style.text, text, w / spec.photo_w, strip)
    if prog:
        prog("Preparing final image")
    p.cache_key, p.cache_img = key, (cell, h)
    return p.cache_img
