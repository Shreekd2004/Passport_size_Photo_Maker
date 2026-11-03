import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from rembg import new_session, remove

DPI = 300
def mm(v): return int(round(v / 25.4 * DPI))

SHEET_W, SHEET_H = mm(210), mm(297)   # A4
PHOTO_W, PHOTO_H = mm(35), mm(45)     # 35x45 mm
MARGIN, GAP = mm(5), mm(5)
COLS = (SHEET_W - 2 * MARGIN + GAP) // (PHOTO_W + GAP)  # 5

_session = None
_cascade = None

def _get_session():
    global _session
    if _session is None:
        _session = new_session("u2net")
    return _session

def _get_cascade():
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return _cascade

def remove_bg(img):
    return remove(img.convert("RGB"), session=_get_session()).convert("RGBA")

def crop_passport(rgba, bg=(255, 255, 255)):
    arr = np.array(rgba)
    ys, xs = np.where(arr[..., 3] > 128)
    if len(ys) == 0:
        ys, xs = np.array([0, rgba.height - 1]), np.array([0, rgba.width - 1])
    top, bottom = ys.min(), ys.max()
    gray = cv2.cvtColor(arr[..., :3], cv2.COLOR_RGB2GRAY)
    faces = _get_cascade().detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
    if len(faces):
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        cx = x + w / 2
        ch = ((y + h * 1.05) - top) / 0.72
        t = top - 0.08 * ch
    else:
        cx = xs[ys < top + (bottom - top) * 0.25].mean()
        ch = (bottom - top) * 1.1
        t = top - 0.05 * ch
    cw = ch * PHOTO_W / PHOTO_H
    l = cx - cw / 2
    canvas = Image.new("RGB", (int(cw), int(ch)), bg)
    canvas.paste(rgba, (-int(l), -int(t)), rgba)
    return canvas.resize((PHOTO_W, PHOTO_H), Image.LANCZOS)

def build_sheets(photos, copies, border=True):
    pages = []
    def new_page():
        im = Image.new("RGB", (SHEET_W, SHEET_H), (255, 255, 255))
        pages.append(im)
        return im, ImageDraw.Draw(im)
    page, draw = new_page()
    y = MARGIN
    for photo in photos:
        placed = 0
        for _ in range(math.ceil(copies / COLS)):
            if y + PHOTO_H > SHEET_H - MARGIN:
                page, draw = new_page()
                y = MARGIN
            for c in range(COLS):
                if placed >= copies:
                    break
                x = MARGIN + c * (PHOTO_W + GAP)
                page.paste(photo, (x, y))
                if border:
                    draw.rectangle([x, y, x + PHOTO_W - 1, y + PHOTO_H - 1],
                                   outline=(0, 0, 0), width=3)
                placed += 1
            y += PHOTO_H + GAP
    return pages
