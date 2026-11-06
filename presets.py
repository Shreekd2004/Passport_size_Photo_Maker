"""Photo-size and paper presets. Nothing is hard-coded elsewhere in the app.

Shops can add their own sizes without touching code (or with the "Save as preset" button):
%LOCALAPPDATA%\\SnapMitra\\presets.json
[{"name": "My ID", "country": "India", "w_mm": 30, "h_mm": 40, "head_ratio": 0.7, "notes": "..."}]
head_ratio = chin-to-crown height as a fraction of the photo height.
"""
import json
import logging

from model import app_data_dir

log = logging.getLogger("snapmitra")

_VERIFY = " Rules change - verify with the issuing authority before printing."

PHOTO_PRESETS = [
    dict(name="Indian Passport", country="India", w_mm=35.0, h_mm=45.0, head_ratio=0.74,
         notes="35 x 45 mm. Plain white background, face about 70-80% of the photo, no shadows." + _VERIFY),
    dict(name="Stamp Size", country="", w_mm=25.0, h_mm=25.0, head_ratio=0.62,
         notes="25 x 25 mm square. Common for forms, applications and ID cards."),
    dict(name="US Passport", country="USA", w_mm=50.8, h_mm=50.8, head_ratio=0.60,
         notes="2 x 2 in, white background, head 1 to 1-3/8 in (50-69%)." + _VERIFY),
    dict(name="India e-Visa (2 x 2 in)", country="India", w_mm=50.8, h_mm=50.8, head_ratio=0.60,
         notes="Square 2 x 2 in, plain light background, face centred." + _VERIFY),
    dict(name="US Visa (2 x 2 in)", country="USA", w_mm=50.8, h_mm=50.8, head_ratio=0.60,
         notes="2 x 2 in, white background, head 1 to 1-3/8 in (50-69%)." + _VERIFY),
    dict(name="Schengen Visa (35 x 45)", country="Schengen area", w_mm=35.0, h_mm=45.0, head_ratio=0.75,
         notes="35 x 45 mm, light grey/white background, face 32-36 mm tall." + _VERIFY),
    dict(name="UK Passport (35 x 45)", country="United Kingdom", w_mm=35.0, h_mm=45.0, head_ratio=0.72,
         notes="35 x 45 mm, plain cream/light grey background, head 29-34 mm." + _VERIFY),
    dict(name="China Visa (33 x 48)", country="China", w_mm=33.0, h_mm=48.0, head_ratio=0.64,
         notes="33 x 48 mm, white background, head 28-33 mm." + _VERIFY),
    dict(name="Canada Passport (50 x 70)", country="Canada", w_mm=50.0, h_mm=70.0, head_ratio=0.48,
         notes="50 x 70 mm, plain white background, face 31-36 mm." + _VERIFY),
    dict(name="Custom", country="", w_mm=35.0, h_mm=45.0, head_ratio=0.72,
         notes="Type any width / height in millimetres or inches."),
]

PAPERS = [
    ("A4", 210.0, 297.0),
    ("A5", 148.0, 210.0),
    ("4 x 6 in", 101.6, 152.4),
    ("5 x 7 in", 127.0, 177.8),
    ("Custom", None, None),
]


def _presets_file():
    return app_data_dir() / "presets.json"


def load_photo_presets():
    out = [dict(p) for p in PHOTO_PRESETS]
    f = _presets_file()
    if f.is_file():
        try:
            extra = json.loads(f.read_text(encoding="utf-8"))
            at = len(out) - 1                      # keep "Custom" last
            for e in extra:
                out.insert(at, dict(
                    name=str(e["name"]), country=str(e.get("country", "")),
                    w_mm=float(e["w_mm"]), h_mm=float(e["h_mm"]),
                    head_ratio=float(e.get("head_ratio", 0.72)), notes=str(e.get("notes", "")), user=True))
                at += 1
        except Exception:
            log.exception("could not read presets.json")
    return out


def save_user_preset(name, w_mm, h_mm, head_ratio, notes=""):
    """Add / replace a shop-specific preset (persisted in presets.json)."""
    f = _presets_file()
    items = []
    if f.is_file():
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            items = []
    items = [i for i in items if i.get("name") != name]
    items.append(dict(name=name, country="", w_mm=round(w_mm, 2), h_mm=round(h_mm, 2),
                      head_ratio=round(head_ratio, 3), notes=notes or "Saved by you."))
    f.write_text(json.dumps(items, indent=1), encoding="utf-8")
