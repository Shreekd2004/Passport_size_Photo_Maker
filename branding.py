"""SnapMitra branding: colours (taken from the logo), names and asset helpers."""
import functools

from PIL import Image, ImageTk

import model

APP_NAME = "SnapMitra"
TAGLINE = "Your Smart Photo & Print Studio"
WINDOW_TITLE = "SnapMitra \u2013 Your Smart Photo & Print Studio"
VERSION = "3.0"

# palette sampled from the supplied logo
NAVY = "#032A56"
BLUE = "#0067C5"
ORANGE = "#FC6801"
CYAN = "#12E8FE"
WHITE = "#FFFFFF"
BG = "#F4F7FB"         # light surface used on the dashboard / previews
MUTED = "#5B6B82"
FONT = "Segoe UI"


def asset(name):
    return model.resource_dir() / "assets" / name


@functools.lru_cache(maxsize=16)
def logo_pil(size, transparent=True):
    """Original artwork, only resized (never redrawn)."""
    f = asset("snapmitra_logo_transparent.png" if transparent else "snapmitra_logo.png")
    return Image.open(f).convert("RGBA").resize((size, size), Image.LANCZOS)


def logo_tk(size, transparent=True):
    return ImageTk.PhotoImage(logo_pil(size, transparent))


def set_window_icon(root):
    """Window / taskbar icon (the EXE icon itself is embedded by PyInstaller)."""
    try:
        ico = asset("snapmitra.ico")
        if ico.is_file() and root.tk.call("tk", "windowingsystem") == "win32":
            root.iconbitmap(default=str(ico))
        root._icon_ref = ImageTk.PhotoImage(logo_pil(64))
        root.iconphoto(True, root._icon_ref)
    except Exception:
        pass
