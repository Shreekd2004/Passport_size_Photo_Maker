"""Create a simple synthetic portrait for the post-build self-test (no personal photos in the repo)."""
import sys
from PIL import Image, ImageDraw

im = Image.new("RGB", (900, 1100), (200, 190, 170))
d = ImageDraw.Draw(im)
d.rectangle([150, 800, 750, 1100], fill=(40, 60, 120))              # shoulders
d.rectangle([380, 640, 520, 820], fill=(205, 160, 130))             # neck
d.ellipse([280, 250, 620, 700], fill=(215, 170, 140))               # face
d.pieslice([270, 220, 630, 520], 180, 360, fill=(30, 20, 15))       # hair
for x in (385, 515):
    d.ellipse([x - 22, 440, x + 22, 470], fill="white")
    d.ellipse([x - 9, 447, x + 9, 465], fill=(40, 25, 15))
d.rectangle([410, 590, 490, 604], fill=(150, 70, 70))
im.save(sys.argv[1])
