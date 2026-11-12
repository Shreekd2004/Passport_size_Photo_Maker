"""Settings, recent projects, project files and auto-save (all stored locally in %LOCALAPPDATA%\\SnapMitra)."""
import json
import logging
import os
from pathlib import Path

from model import app_data_dir

log = logging.getLogger("snapmitra")

DEFAULTS = dict(
    remove_bg=True, bg_choice="white", bg_custom="#FFFFFF", head_guides=True,
    photo_preset="Indian Passport", unit="mm", pw=35.0, ph=45.0, head=74,
    paper="A4", paper_w=210.0, paper_h=297.0, orient="Auto",
    margin=5.0, hgap=4.0, vgap=4.0, border=True, border_px=3,
    cut_guides="none", layout_mode="continuous",
    fmt="PDF", default_copies=5, output_dir=str(Path.home() / "Pictures" / "SnapMitra"),
    t_enabled=False, t_source="custom", t_custom="", t_date=False, t_date_mode="today", t_date_text="",
    t_two=False, t_font="Segoe UI", t_bold=False, t_size=9.0, t_color="#000000", t_align="center",
    t_pos="inside", t_area=5.0, t_mode="global", t_voff=0.0, t_bg_on=True, t_bg_color="#FFFFFF",
)

BG_COLORS = {"white": (255, 255, 255), "lightblue": (185, 214, 242), "blue": (36, 112, 214), "red": (200, 35, 45)}


def hex_to_rgb(h):
    h = (h or "#000000").lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


class Store:
    """settings.json: UI settings + recent projects + how often each photo size is used."""

    def __init__(self):
        self.path = app_data_dir() / "settings.json"
        raw = _read_json(self.path, {})
        self.cfg = dict(DEFAULTS)
        self.cfg.update({k: v for k, v in raw.get("cfg", {}).items() if k in DEFAULTS})
        self.recent = [p for p in raw.get("recent", []) if os.path.isfile(p)][:8]
        self.usage = raw.get("usage", {})

    def save(self, cfg=None):
        if cfg is not None:
            self.cfg = cfg
        try:
            _write_json(self.path, dict(cfg=self.cfg, recent=self.recent, usage=self.usage))
        except Exception:
            log.exception("could not save settings")

    def add_recent(self, path):
        path = str(path)
        self.recent = [path] + [p for p in self.recent if p != path]
        self.recent = self.recent[:8]
        self.save()

    def bump_usage(self, preset):
        self.usage[preset] = self.usage.get(preset, 0) + 1

    def top_presets(self, n=4):
        return [k for k, _ in sorted(self.usage.items(), key=lambda kv: -kv[1])][:n]


def project_dict(cfg, photos):
    return dict(app="SnapMitra", version=1, settings=cfg,
                photos=[dict(path=p.path, copies=p.copies, label=p.label, edit=p.edit, text_mode=p.text_mode,
                           ptext=(p.ptext.to_dict() if p.ptext is not None else None)) for p in photos])


def write_project(path, cfg, photos):
    _write_json(path, project_dict(cfg, photos))


def read_project(path):
    d = _read_json(path, None)
    if not isinstance(d, dict) or d.get("app") != "SnapMitra":
        raise ValueError("This is not a SnapMitra project file.")
    return d


AUTOSAVE = app_data_dir() / "autosave.json"


def write_autosave(cfg, photos):
    if photos:
        _write_json(AUTOSAVE, project_dict(cfg, photos))
    elif AUTOSAVE.exists():
        AUTOSAVE.unlink()


def read_autosave():
    d = _read_json(AUTOSAVE, None)
    if isinstance(d, dict) and d.get("photos"):
        d["photos"] = [p for p in d["photos"] if os.path.isfile(p.get("path", ""))]
        return d if d["photos"] else None
    return None
