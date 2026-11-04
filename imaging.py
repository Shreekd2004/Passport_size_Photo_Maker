"""Image pipeline: load -> remove background -> detect face -> render passport photo.

The expensive AI step runs ONCE per photo and the transparent cut-out is cached.
Everything else (background colour, zoom, move, rotate, brightness, contrast)
is a cheap re-render from that cache, so editing never re-runs the AI.
"""
import math
import os

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

import model
import units

MAX_SIDE = 1600  # working resolution: plenty for a 413 x 531 px print photo, and much faster


def default_edit():
    return dict(zoom=1.0, dx=0.0, dy=0.0, tilt=0.0, rot90=0, bright=0.0, contrast=0.0)


class Photo:
    def __init__(self, path, copies=5):
        self.path = path
        self.name = os.path.basename(path)
        self.copies = copies
        self.state = "new"      # new | queued | processing | ready | error
        self.error = ""
        self.cutout = None      # RGBA working image (background removed or original)
        self.mode = None        # "ai" | "none" that produced cutout
        self.face = None        # dict(cx, top, chin, found)
        self.edit = default_edit()
        self.cache_key = None
        self.cache_img = None
        self.thumb_key = None
        self.thumb_tk = None


def needs_processing(p, mode):
    return p.cutout is None or p.mode != mode


def load_image(path):
    im = Image.open(path)
    try:
        im.draft("RGB", (MAX_SIDE // 2, MAX_SIDE // 2))  # fast down-scaled JPEG decode
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


def remove_background(img, session):
    mask = session.predict(img)
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def detect_face(rgb):
    """Largest face as (x, y, w, h) in image pixels, or None (caller falls back to a mask-based crop)."""
    fm = model.get_face()
    if fm is None:
        return None
    try:
        return fm.detect(rgb)
    except Exception:  # noqa
        return None


def analyse(cutout, face, has_alpha):
    """Head geometry in working-image pixels: horizontal centre, crown (top) and chin."""
    arr = np.asarray(cutout)
    H, W = arr.shape[:2]
    top_mask, bottom = 0, H - 1
    if has_alpha:
        rows = np.where((arr[..., 3] > 128).sum(axis=1) >= max(5, int(0.01 * W)))[0]
        if len(rows):
            top_mask, bottom = int(rows[0]), int(rows[-1])
    if face is not None:
        x, y, w, h = face
        cx = x + w / 2.0
        chin = y + h * 0.99          # detector box bottom sits on the chin
        top = top_mask if has_alpha else y - 0.25 * h
        if top >= y - 0.02 * h or top < y - 0.7 * h:    # mask miss or stray blob above the head
            top = y - 0.25 * h
        return dict(cx=cx, top=top, chin=chin, found=True)
    # fallback: assume head & shoulders framing
    top = top_mask
    chin = top + 0.55 * max(1, bottom - top)
    if has_alpha:
        band = arr[top: top + max(2, int(0.25 * (bottom - top))), :, 3] > 128
        xs = np.where(band.any(axis=0))[0]
        cx = float(xs.mean()) if len(xs) else W / 2.0
    else:
        cx = W / 2.0
    return dict(cx=cx, top=float(top), chin=float(chin), found=False)


def default_crop(face, head_ratio, aspect):
    hh = max(1.0, face["chin"] - face["top"])
    ch = hh / head_ratio
    top_margin = 0.28 * (1.0 - head_ratio) * ch
    cy = face["top"] - top_margin + ch / 2.0
    return face["cx"], cy, ch * aspect, ch


def render(cutout, face, edit, head_ratio, bg, out_w, out_h, ss=2):
    """Crop/rotate/zoom the cut-out into an out_w x out_h RGB image on a solid background."""
    aspect = out_w / float(out_h)
    cx, cy, cw, ch = default_crop(face, head_ratio, aspect)
    z = max(0.2, float(edit["zoom"]))
    cw /= z
    ch /= z
    cx += edit["dx"] * cw
    cy += edit["dy"] * ch
    th = math.radians(edit["rot90"] * 90 + edit["tilt"])
    cs, sn = math.cos(th), math.sin(th)
    W, H = int(out_w * ss), int(out_h * ss)
    coeffs = (
        cw / W * cs, -ch / H * sn, cx - 0.5 * cw * cs + 0.5 * ch * sn,
        cw / W * sn, ch / H * cs, cy - 0.5 * cw * sn - 0.5 * ch * cs,
    )
    tile = cutout.transform((W, H), Image.AFFINE, coeffs, resample=Image.BICUBIC)
    canvas = Image.new("RGB", (W, H), tuple(bg))
    canvas.paste(tile, mask=tile.getchannel("A"))
    if ss != 1:
        canvas = canvas.resize((out_w, out_h), Image.LANCZOS)
    if abs(edit["bright"]) > 0.5:
        canvas = ImageEnhance.Brightness(canvas).enhance(1 + edit["bright"] / 100.0)
    if abs(edit["contrast"]) > 0.5:
        canvas = ImageEnhance.Contrast(canvas).enhance(1 + edit["contrast"] / 100.0)
    return canvas


def final_image(p, spec, bg):
    """Print-resolution passport photo (cached until an edit / setting changes)."""
    w, h = units.mm_to_px(spec.photo_w), units.mm_to_px(spec.photo_h)
    key = (w, h, round(spec.head, 3), tuple(bg), tuple(sorted(p.edit.items())), p.mode)
    if p.cache_key == key and p.cache_img is not None:
        return p.cache_img
    img = render(p.cutout, p.face, p.edit, spec.head, bg, w, h, ss=2)
    p.cache_key, p.cache_img = key, img
    return img
