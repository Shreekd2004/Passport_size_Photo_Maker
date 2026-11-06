"""Generate every branding asset from the ORIGINAL logo (assets/snapmitra_logo.png).
The artwork is only resized / placed on a canvas - never redrawn or distorted.
Run:  python tools/make_assets.py
"""
import os
from collections import deque
from PIL import Image, ImageFilter

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
src = Image.open(os.path.join(A, "snapmitra_logo.png")).convert("RGB")


def cut_outside(im, tol=14):
    """Make the near-white area OUTSIDE the rounded card transparent (flood fill from the corners)."""
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    q = deque([(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)])
    lim = 255 - tol * 2
    mask = Image.new("L", (w, h), 255)
    mp = mask.load()
    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or seen[y * w + x]:
            continue
        seen[y * w + x] = 1
        p = px[x, y]
        if not (p[0] >= lim and p[1] >= lim and p[2] >= lim):
            continue
        mp[x, y] = 0
        q.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


card = cut_outside(src)
card.save(os.path.join(A, "snapmitra_logo_transparent.png"))
for s in (512, 256, 96, 48):
    card.resize((s, s), Image.LANCZOS).save(os.path.join(A, f"logo_{s}.png"))
card.save(os.path.join(A, "snapmitra.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

sp = Image.new("RGB", (560, 600), "white")                      # splash: logo on white
sp.paste(src.resize((520, 520), Image.LANCZOS), (20, 10))
sp.save(os.path.join(A, "splash.png"))

big = Image.new("RGB", (164, 314), "white")                     # Inno Setup wizard images
big.paste(src.resize((150, 150), Image.LANCZOS), (7, 80))
big.save(os.path.join(A, "wizard_large.bmp"))
src.resize((55, 55), Image.LANCZOS).save(os.path.join(A, "wizard_small.bmp"))
print("assets written:", sorted(os.listdir(A)))
