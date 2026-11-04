"""Passport Photo Maker - desktop GUI (Tkinter + Sun Valley Windows-11 theme).

All heavy work happens in worker.py on a background thread; this file only draws
widgets and reacts to queue messages, so the window never freezes.
"""
import json
import logging
import os
import queue
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk

import imaging
import layout
import model
import presets
import printing
import worker
from imaging import Photo
from units import mm_to_px

log = logging.getLogger("ppm")
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
BG_PRESETS = {"white": (255, 255, 255), "blue": (185, 214, 242)}

DEFAULTS = dict(remove_bg=True, bg_choice="white", bg_custom="#FFFFFF", guides=True,
                photo_preset="Indian Passport", pw=35.0, ph=45.0, head=74,
                paper="A4", paper_w=210.0, paper_h=297.0, orient="Auto",
                margin=5.0, hgap=4.0, vgap=3.0, border=True, border_px=3, new_row=True,
                fmt="PNG", default_copies=5)


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class App:
    def __init__(self, root):
        self.root = root
        root.title("Passport Photo Maker")
        self.S = max(1.0, root.winfo_fpixels("1i") / 96.0)
        root.geometry(f"{self.sc(1180)}x{self.sc(780)}")
        root.minsize(self.sc(1000), self.sc(660))

        self.photos, self.sel = [], None
        self.rows = {}
        self.q = queue.Queue()
        self.jobs, self.active = deque(), None
        self.job_t0 = self.last_prog = 0.0
        self.pages, self.pages_ok, self.page_idx = [], False, 0
        self.lock_traces = False
        self.loading_editor = False
        self.presets = presets.load_photo_presets()
        self.preset_by_name = {p["name"]: p for p in self.presets}
        self.cfg_path = model.app_data_dir() / "settings.json"
        self.cfg = self.load_cfg()

        self.make_vars()
        self.build_ui()
        self.apply_photo_preset(initial=True)
        self.apply_paper_preset(initial=True)
        self.bind_traces()
        self.update_info()
        self.idle_status()

        if os.environ.get("PPM_NO_DND") != "1":
            try:
                from tkinterdnd2 import DND_FILES
                root.drop_target_register(DND_FILES)
                root.dnd_bind("<<Drop>>", self.on_drop)
            except Exception:
                log.info("drag & drop unavailable")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(60, self.poll)
        # load the AI model in the background right away so the first photo is instant
        self.enqueue(worker.Job("warmup", [], self.params()))

    # ------------------------------------------------------------------ helpers
    def sc(self, v):
        return int(v * getattr(self, "S", 1.0))

    def load_cfg(self):
        c = dict(DEFAULTS)
        try:
            c.update(json.loads(self.cfg_path.read_text(encoding="utf-8")))
        except Exception:
            pass
        return c

    def save_cfg(self):
        try:
            c = dict(remove_bg=self.v_remove.get(), bg_choice=self.v_bg.get(), bg_custom=self.bg_custom,
                     guides=self.v_guides.get(), photo_preset=self.v_preset.get(), pw=self.num(self.v_pw, 35),
                     ph=self.num(self.v_ph, 45), head=self.num(self.v_head, 74), paper=self.v_paper.get(),
                     paper_w=self.num(self.v_paper_w, 210), paper_h=self.num(self.v_paper_h, 297),
                     orient=self.v_orient.get(), margin=self.num(self.v_margin, 5), hgap=self.num(self.v_hgap, 4),
                     vgap=self.num(self.v_vgap, 3), border=self.v_border.get(), border_px=int(self.num(self.v_bpx, 3)),
                     new_row=self.v_newrow.get(), fmt=self.v_fmt.get(), default_copies=int(self.num(self.v_defcopies, 5)))
            self.cfg_path.write_text(json.dumps(c, indent=1), encoding="utf-8")
        except Exception:
            log.exception("could not save settings")

    @staticmethod
    def num(var, default):
        try:
            return float(var.get())
        except (tk.TclError, ValueError):
            return default

    def make_vars(self):
        c = self.cfg
        self.bg_custom = c["bg_custom"]
        self.v_remove = tk.BooleanVar(value=c["remove_bg"])
        self.v_bg = tk.StringVar(value=c["bg_choice"])
        self.v_guides = tk.BooleanVar(value=c["guides"])
        self.v_preset = tk.StringVar(value=c["photo_preset"] if c["photo_preset"] in self.preset_by_name else "Indian Passport")
        self.v_pw, self.v_ph = tk.DoubleVar(value=c["pw"]), tk.DoubleVar(value=c["ph"])
        self.v_head = tk.IntVar(value=c["head"])
        self.v_paper = tk.StringVar(value=c["paper"])
        self.v_paper_w, self.v_paper_h = tk.DoubleVar(value=c["paper_w"]), tk.DoubleVar(value=c["paper_h"])
        self.v_orient = tk.StringVar(value=c["orient"])
        self.v_margin, self.v_hgap, self.v_vgap = (tk.DoubleVar(value=c[k]) for k in ("margin", "hgap", "vgap"))
        self.v_border, self.v_bpx = tk.BooleanVar(value=c["border"]), tk.IntVar(value=c["border_px"])
        self.v_newrow = tk.BooleanVar(value=c["new_row"])
        self.v_fmt = tk.StringVar(value=c["fmt"])
        self.v_defcopies = tk.IntVar(value=c["default_copies"])
        self.edit_vars = {k: tk.DoubleVar(value=v) for k, v in imaging.default_edit().items() if k != "rot90"}

    # ------------------------------------------------------------------ UI
    def build_ui(self):
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(0, weight=1)
        main = ttk.Frame(r, padding=8)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        self.build_photos(main)
        self.nb = ttk.Notebook(main)
        self.nb.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.build_editing()
        self.build_layout()
        self.build_preview()
        self.build_status(r)

    def build_photos(self, parent):
        f = ttk.LabelFrame(parent, text=" 1  Photos ", padding=8, width=self.sc(440))
        f.grid(row=0, column=0, sticky="ns")
        f.grid_propagate(False)
        f.rowconfigure(3, weight=1)
        f.columnconfigure(0, weight=1)
        bar = ttk.Frame(f)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(bar, text="Add photos...", style="Accent.TButton", command=self.add_files).pack(side="left")
        ttk.Button(bar, text="Import folder...", command=self.add_folder).pack(side="left", padx=4)
        ttk.Button(bar, text="Clear all", command=self.clear_all).pack(side="left")
        dc = ttk.Frame(f)
        dc.grid(row=1, column=0, sticky="w", pady=(6, 2))
        ttk.Label(dc, text="Copies for newly added photos:").pack(side="left")
        ttk.Spinbox(dc, from_=1, to=99, width=4, textvariable=self.v_defcopies).pack(side="left", padx=6)
        self.lbl_hint = ttk.Label(f, text="Tip: drag & drop photos anywhere on this window.", foreground="#666")
        self.lbl_hint.grid(row=2, column=0, sticky="w", pady=(0, 4))
        box = ttk.Frame(f)
        box.grid(row=3, column=0, sticky="nsew")
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        self.list_canvas = tk.Canvas(box, highlightthickness=0, bg="#fafafa")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.list_canvas.yview)
        self.list_canvas.configure(yscrollcommand=sb.set)
        self.list_canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.list_inner = tk.Frame(self.list_canvas, bg="#fafafa")
        self.list_win = self.list_canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        self.list_inner.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfigure(self.list_win, width=e.width))
        self.list_canvas.bind("<Enter>", lambda e: self.list_canvas.bind_all("<MouseWheel>", self.on_list_wheel))
        self.list_canvas.bind("<Leave>", lambda e: self.list_canvas.unbind_all("<MouseWheel>"))
        self.lbl_total = ttk.Label(f, text="No photos yet")
        self.lbl_total.grid(row=4, column=0, sticky="w", pady=(6, 0))

    def on_list_wheel(self, e):
        self.list_canvas.yview_scroll(int(-e.delta / 120), "units")

    def build_editing(self):
        f = ttk.Frame(self.nb, padding=10)
        self.nb.add(f, text="  2  Editing  ")
        f.columnconfigure(1, weight=1)
        f.rowconfigure(0, weight=1)
        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))

        bgf = ttk.LabelFrame(left, text=" Background ", padding=8)
        bgf.pack(fill="x")
        ttk.Checkbutton(bgf, text="Remove background (AI, runs on this PC)", variable=self.v_remove,
                        command=self.on_remove_toggle).pack(anchor="w")
        row = ttk.Frame(bgf)
        row.pack(anchor="w", pady=(6, 0))
        ttk.Radiobutton(row, text="White", value="white", variable=self.v_bg, command=self.on_bg_change).pack(side="left")
        ttk.Radiobutton(row, text="Light blue", value="blue", variable=self.v_bg, command=self.on_bg_change).pack(side="left", padx=8)
        ttk.Radiobutton(row, text="Custom", value="custom", variable=self.v_bg, command=self.on_bg_change).pack(side="left")
        self.swatch = tk.Button(row, width=3, relief="solid", bd=1, command=self.pick_color, bg=self.bg_custom)
        self.swatch.pack(side="left", padx=6)

        self.edit_frame = ttk.LabelFrame(left, text=" Selected photo ", padding=8)
        self.edit_frame.pack(fill="x", pady=(10, 0))
        self.lbl_sel = ttk.Label(self.edit_frame, text="Select a photo from the list", font=("Segoe UI", 10, "bold"))
        self.lbl_sel.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        specs = [("zoom", "Zoom", 0.5, 2.5), ("dx", "Move left / right", -0.5, 0.5), ("dy", "Move up / down", -0.5, 0.5),
                 ("tilt", "Rotate (fine)", -20, 20), ("bright", "Brightness", -50, 50), ("contrast", "Contrast", -50, 50)]
        self.sliders = {}
        for i, (key, label, lo, hi) in enumerate(specs, start=1):
            ttk.Label(self.edit_frame, text=label).grid(row=i, column=0, sticky="w", pady=2)
            s = ttk.Scale(self.edit_frame, from_=lo, to=hi, variable=self.edit_vars[key], length=self.sc(190),
                          command=lambda v, k=key: self.on_slider(k))
            s.grid(row=i, column=1, padx=6)
            val = ttk.Label(self.edit_frame, width=6, text="")
            val.grid(row=i, column=2)
            self.sliders[key] = (s, val)
        bt = ttk.Frame(self.edit_frame)
        bt.grid(row=8, column=0, columnspan=3, pady=(8, 0), sticky="w")
        ttk.Button(bt, text="Rotate 90° left", command=lambda: self.rot90(-1)).pack(side="left")
        ttk.Button(bt, text="Rotate 90° right", command=lambda: self.rot90(1)).pack(side="left", padx=4)
        ttk.Button(bt, text="Reset / auto-fit", command=self.reset_edit).pack(side="left")
        ttk.Checkbutton(self.edit_frame, text="Show alignment guides", variable=self.v_guides,
                        command=self.draw_editor).grid(row=9, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(left, text="Tip: drag the photo to position it, mouse wheel to zoom.",
                  foreground="#666").pack(anchor="w", pady=(8, 0))

        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.ed_canvas = tk.Canvas(right, bg="#e9e9e9", highlightthickness=0)
        self.ed_canvas.grid(row=0, column=0, sticky="nsew")
        self.ed_canvas.bind("<Configure>", lambda e: self.draw_editor())
        self.ed_canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.ed_canvas.bind("<B1-Motion>", self.on_drag)
        self.ed_canvas.bind("<MouseWheel>", self.on_wheel)
        self.ed_img_size = (1, 1)

    def build_layout(self):
        f = ttk.Frame(self.nb, padding=14)
        self.nb.add(f, text="  3  Layout  ")
        g = ttk.LabelFrame(f, text=" Photo size ", padding=10)
        g.pack(fill="x")
        ttk.Label(g, text="Preset").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(g, textvariable=self.v_preset, values=[p["name"] for p in self.presets],
                          state="readonly", width=30)
        cb.grid(row=0, column=1, columnspan=3, sticky="w", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.apply_photo_preset())
        ttk.Label(g, text="Width (mm)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(g, from_=10, to=200, increment=0.5, width=7, textvariable=self.v_pw,
                    command=self.mark_custom_photo).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(g, text="Height (mm)").grid(row=1, column=2, sticky="w")
        ttk.Spinbox(g, from_=10, to=300, increment=0.5, width=7, textvariable=self.v_ph,
                    command=self.mark_custom_photo).grid(row=1, column=3, sticky="w", padx=6)
        ttk.Label(g, text="Head size (% of height)").grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Spinbox(g, from_=30, to=90, width=7, textvariable=self.v_head,
                    command=self.mark_custom_photo).grid(row=2, column=2, sticky="w", padx=6)
        self.lbl_notes = ttk.Label(g, text="", wraplength=self.sc(560), foreground="#555", justify="left")
        self.lbl_notes.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))

        p = ttk.LabelFrame(f, text=" Paper ", padding=10)
        p.pack(fill="x", pady=10)
        ttk.Label(p, text="Paper size").grid(row=0, column=0, sticky="w")
        pc = ttk.Combobox(p, textvariable=self.v_paper, values=[x[0] for x in presets.PAPERS], state="readonly", width=12)
        pc.grid(row=0, column=1, sticky="w", padx=6)
        pc.bind("<<ComboboxSelected>>", lambda e: self.apply_paper_preset())
        ttk.Label(p, text="W (mm)").grid(row=0, column=2, padx=(12, 0))
        ttk.Spinbox(p, from_=40, to=1000, increment=1, width=7, textvariable=self.v_paper_w,
                    command=self.mark_custom_paper).grid(row=0, column=3, padx=4)
        ttk.Label(p, text="H (mm)").grid(row=0, column=4)
        ttk.Spinbox(p, from_=40, to=1500, increment=1, width=7, textvariable=self.v_paper_h,
                    command=self.mark_custom_paper).grid(row=0, column=5, padx=4)
        ttk.Label(p, text="Orientation").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(p, textvariable=self.v_orient, values=["Auto", "Portrait", "Landscape"],
                     state="readonly", width=12).grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Label(p, text="Auto picks whichever uses the fewest sheets", foreground="#666").grid(
            row=1, column=2, columnspan=4, sticky="w", pady=(8, 0))

        s = ttk.LabelFrame(f, text=" Spacing & border ", padding=10)
        s.pack(fill="x")
        for i, (lbl, var, hi) in enumerate([("Margin (mm)", self.v_margin, 50), ("Horizontal gap (mm)", self.v_hgap, 30),
                                            ("Vertical gap (mm)", self.v_vgap, 30)]):
            ttk.Label(s, text=lbl).grid(row=0, column=i * 2, sticky="w", padx=(0 if i == 0 else 14, 0))
            ttk.Spinbox(s, from_=0, to=hi, increment=0.5, width=6, textvariable=var).grid(row=0, column=i * 2 + 1, padx=6)
        ttk.Checkbutton(s, text="Black border", variable=self.v_border).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(s, text="Thickness (px @300 DPI)").grid(row=1, column=2, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Spinbox(s, from_=1, to=12, width=5, textvariable=self.v_bpx).grid(row=1, column=4, pady=(10, 0))
        ttk.Checkbutton(s, text="Start each person on a new row (easier to cut and hand out)",
                        variable=self.v_newrow).grid(row=2, column=0, columnspan=6, sticky="w", pady=(10, 0))
        self.lbl_info = ttk.Label(f, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_info.pack(anchor="w", pady=(12, 0))

    def build_preview(self):
        f = ttk.Frame(self.nb, padding=10)
        self.nb.add(f, text="  4  Preview & Export  ")
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)
        top = ttk.Frame(f)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Button(top, text="Generate sheet", style="Accent.TButton", command=self.generate).pack(side="left")
        ttk.Button(top, text="<", width=3, command=lambda: self.flip(-1)).pack(side="left", padx=(16, 2))
        self.lbl_page = ttk.Label(top, text="No sheet yet", width=14, anchor="center")
        self.lbl_page.pack(side="left")
        ttk.Button(top, text=">", width=3, command=lambda: self.flip(1)).pack(side="left", padx=2)
        self.lbl_stale = ttk.Label(top, text="", foreground="#b45309")
        self.lbl_stale.pack(side="left", padx=12)
        self.pv_canvas = tk.Canvas(f, bg="#e9e9e9", highlightthickness=0)
        self.pv_canvas.grid(row=1, column=0, sticky="nsew", pady=8)
        self.pv_canvas.bind("<Configure>", lambda e: self.draw_preview())
        bot = ttk.Frame(f)
        bot.grid(row=2, column=0, sticky="ew")
        ttk.Label(bot, text="Save as").pack(side="left")
        ttk.Combobox(bot, textvariable=self.v_fmt, values=["PNG", "JPG", "PDF"], state="readonly", width=6).pack(side="left", padx=6)
        ttk.Button(bot, text="Save...", command=self.save_sheet).pack(side="left")
        ttk.Button(bot, text="Print...", command=self.print_sheet).pack(side="left", padx=6)
        ttk.Label(bot, text="300 DPI - print at 100% / actual size",
                  foreground="#666").pack(side="left", padx=10)

    def build_status(self, parent):
        sb = ttk.Frame(parent, padding=(10, 6))
        sb.grid(row=1, column=0, sticky="ew")
        sb.columnconfigure(1, weight=1)
        self.lbl_stage = ttk.Label(sb, text="", font=("Segoe UI", 10, "bold"), width=34, anchor="w")
        self.lbl_stage.grid(row=0, column=0, sticky="w")
        self.pb = ttk.Progressbar(sb, maximum=100, mode="determinate")
        self.pb.grid(row=0, column=1, sticky="ew", padx=8)
        self.lbl_pct = ttk.Label(sb, text="", width=5, anchor="e")
        self.lbl_pct.grid(row=0, column=2)
        self.btn_cancel = ttk.Button(sb, text="Cancel processing", command=self.cancel_job, state="disabled")
        self.btn_cancel.grid(row=0, column=3, padx=(10, 0))
        self.lbl_detail = ttk.Label(sb, text="", foreground="#555")
        self.lbl_detail.grid(row=1, column=0, columnspan=4, sticky="w")

    # ------------------------------------------------------------------ settings -> specs
    def bg_rgb(self):
        c = self.v_bg.get()
        return BG_PRESETS.get(c) or hex_to_rgb(self.bg_custom)

    def spec(self):
        pap = self.v_paper.get()
        orient = {"Auto": "auto", "Portrait": "portrait", "Landscape": "landscape"}[self.v_orient.get()]
        return layout.LayoutSpec(
            photo_w=max(5, self.num(self.v_pw, 35)), photo_h=max(5, self.num(self.v_ph, 45)),
            head=min(0.95, max(0.2, self.num(self.v_head, 74) / 100.0)),
            paper_name=pap, paper_w=max(20, self.num(self.v_paper_w, 210)), paper_h=max(20, self.num(self.v_paper_h, 297)),
            orientation=orient, margin=max(0, self.num(self.v_margin, 5)), hgap=max(0, self.num(self.v_hgap, 4)),
            vgap=max(0, self.num(self.v_vgap, 3)), border=self.v_border.get(),
            border_px=int(self.num(self.v_bpx, 3)), new_row=self.v_newrow.get())

    def params(self, **extra):
        d = dict(mode="ai" if self.v_remove.get() else "none", spec=self.spec(), bg=self.bg_rgb())
        d.update(extra)
        return d

    def apply_photo_preset(self, initial=False):
        pr = self.preset_by_name.get(self.v_preset.get())
        if pr and (pr["name"] != "Custom" or not initial):
            self.lock_traces = True
            if pr["name"] != "Custom":
                self.v_pw.set(pr["w_mm"])
                self.v_ph.set(pr["h_mm"])
                self.v_head.set(int(round(pr["head_ratio"] * 100)))
            self.lock_traces = False
        self.lbl_notes.config(text=(f"{pr['country']}: " if pr and pr["country"] else "") + (pr["notes"] if pr else ""))
        if not initial:
            self.on_layout_change()

    def mark_custom_photo(self):
        if not self.lock_traces and self.v_preset.get() != "Custom":
            self.v_preset.set("Custom")
            self.lbl_notes.config(text=self.preset_by_name["Custom"]["notes"])
        self.on_layout_change()

    def apply_paper_preset(self, initial=False):
        for name, w, h in presets.PAPERS:
            if name == self.v_paper.get() and w:
                self.lock_traces = True
                self.v_paper_w.set(w)
                self.v_paper_h.set(h)
                self.lock_traces = False
        if not initial:
            self.on_layout_change()

    def mark_custom_paper(self):
        if not self.lock_traces and self.v_paper.get() != "Custom":
            self.v_paper.set("Custom")
        self.on_layout_change()

    def bind_traces(self):
        for v in (self.v_pw, self.v_ph, self.v_head, self.v_margin, self.v_hgap, self.v_vgap, self.v_border,
                  self.v_bpx, self.v_newrow, self.v_orient, self.v_paper_w, self.v_paper_h):
            v.trace_add("write", lambda *a: self.on_layout_change())

    def on_layout_change(self):
        if self.lock_traces:
            return
        for p in self.photos:
            p.thumb_key = None
        self.touch()
        self.update_info()
        self.refresh_thumbs()
        self.draw_editor()

    def update_info(self):
        spec = self.spec()
        counts = [p.copies for p in self.photos] or [1]
        try:
            n, land, g = layout.choose(spec, counts)
            t = (f"{g['cols']} x {g['rows']} = {g['cols'] * g['rows']} photos per sheet "
                 f"({'landscape' if land else 'portrait'}, {spec.paper_name})")
            if self.photos:
                t += f"  -  {sum(counts)} photos need {n} sheet{'s' if n != 1 else ''}"
        except layout.LayoutError as e:
            t = str(e)
        self.lbl_info.config(text=t)

    def touch(self):
        self.pages_ok = False
        if self.pages:
            self.lbl_stale.config(text="Settings changed - click Generate sheet to refresh")

    # ------------------------------------------------------------------ photo list
    def on_drop(self, event):
        self.add_paths(list(self.root.tk.splitlist(event.data)))

    def add_files(self):
        fs = filedialog.askopenfilenames(title="Choose photos", filetypes=[("Photos", "*.jpg *.jpeg *.png *.webp *.bmp")])
        if fs:
            self.add_paths(list(fs))

    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder of photos")
        if d:
            self.add_paths([d])

    def add_paths(self, paths):
        found = []
        for p in paths:
            if os.path.isdir(p):
                found += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith(EXTS)]
            elif p.lower().endswith(EXTS):
                found.append(p)
        have = {p.path for p in self.photos}
        new = [Photo(p, int(self.num(self.v_defcopies, 5))) for p in found if p not in have]
        if not new:
            messagebox.showinfo("No new photos", "No new JPG / PNG photos were found.")
            return
        self.photos += new
        self.refresh_list()
        self.select(new[0])
        self.touch()
        self.update_info()
        self.queue_prepare()

    def queue_prepare(self):
        todo = [p for p in self.photos if p.state == "new"]
        if todo:
            for p in todo:
                p.state = "queued"
                self.update_row(p)
            self.enqueue(worker.Job("prepare", todo, self.params()))

    def clear_all(self):
        if self.photos and messagebox.askyesno("Clear all", "Remove all photos from the list?"):
            self.cancel_job(silent=True)
            self.photos, self.sel = [], None
            self.refresh_list()
            self.pages, self.pages_ok = [], False
            self.draw_preview()
            self.draw_editor()
            self.update_info()

    def remove(self, p):
        self.photos.remove(p)
        if self.sel is p:
            self.sel = self.photos[0] if self.photos else None
        self.refresh_list()
        self.load_editor()
        self.touch()
        self.update_info()

    def move(self, p, d):
        i = self.photos.index(p)
        j = i + d
        if 0 <= j < len(self.photos):
            self.photos[i], self.photos[j] = self.photos[j], self.photos[i]
            self.refresh_list()
            self.touch()

    def status_text(self, p):
        if p.state == "ready":
            return ("Ready", "#15803d") if p.face and p.face["found"] else ("Ready - face not found, adjust crop", "#b45309")
        return {"new": ("Not processed yet", "#666"), "queued": ("Waiting...", "#666"),
                "processing": ("Processing...", "#1d4ed8"), "error": ("Error: " + p.error[:60], "#b91c1c")}[p.state]

    def thumb(self, p):
        box = (self.sc(44), self.sc(56))
        spec = self.spec()
        aspect = spec.photo_w / spec.photo_h
        w = min(box[0], int(box[1] * aspect))
        h = int(w / aspect)
        key = (w, h, p.state, tuple(sorted(p.edit.items())), self.bg_rgb(), round(spec.head, 2))
        if p.thumb_key != key or p.thumb_tk is None:
            if p.cutout is not None:
                im = imaging.render(p.cutout, p.face, p.edit, spec.head, self.bg_rgb(), w, h, ss=1)
            else:
                im = Image.new("RGB", (w, h), (214, 214, 214))
            p.thumb_tk, p.thumb_key = ImageTk.PhotoImage(im), key
        return p.thumb_tk

    def refresh_list(self):
        for w in self.list_inner.winfo_children():
            w.destroy()
        self.rows = {}
        for p in self.photos:
            self.build_row(p)
        self.lbl_hint.config(text="" if self.photos else "Tip: drag & drop photos anywhere on this window.")
        self.update_total()

    def build_row(self, p):
        bgc = "#dbe9fb" if p is self.sel else "#fafafa"
        row = tk.Frame(self.list_inner, bg=bgc, padx=6, pady=4)
        row.pack(fill="x", pady=1)
        th = tk.Label(row, image=self.thumb(p), bg=bgc, width=self.sc(46), height=self.sc(58))
        th.grid(row=0, column=0, rowspan=2, padx=(0, 8))
        nm = p.name if len(p.name) <= 18 else p.name[:15] + "..."
        name = tk.Label(row, text=nm, anchor="w", bg=bgc, font=("Segoe UI", 10, "bold"))
        name.grid(row=0, column=1, sticky="w")
        txt, col = self.status_text(p)
        st = tk.Label(row, text=txt, anchor="w", bg=bgc, fg=col, font=("Segoe UI", 8))
        st.grid(row=1, column=1, sticky="w")
        row.columnconfigure(1, weight=1)
        var = tk.IntVar(value=p.copies)

        def changed(*_):
            try:
                p.copies = max(0, min(999, int(var.get())))
            except (tk.TclError, ValueError):
                return
            self.touch()
            self.update_info()
            self.update_total()

        var.trace_add("write", changed)
        c = ttk.Frame(row)
        c.grid(row=0, column=2, rowspan=2, padx=4)
        ttk.Label(c, text="Copies").grid(row=0, column=0, columnspan=3)
        ttk.Spinbox(c, from_=1, to=99, width=4, textvariable=var).grid(row=1, column=0, columnspan=3)
        bt = ttk.Frame(row)
        bt.grid(row=0, column=3, rowspan=2)
        ttk.Button(bt, text="▲", width=2, command=lambda: self.move(p, -1)).grid(row=0, column=0)
        ttk.Button(bt, text="▼", width=2, command=lambda: self.move(p, 1)).grid(row=1, column=0)
        ttk.Button(bt, text="✕", width=2, command=lambda: self.remove(p)).grid(row=0, column=1, rowspan=2, padx=2)
        for w in (row, th, name, st):
            w.bind("<Button-1>", lambda e, p=p: self.select(p))
        self.rows[p] = (row, th, st, name)

    def update_row(self, p):
        if p in self.rows:
            row, th, st, _ = self.rows[p]
            txt, col = self.status_text(p)
            st.config(text=txt, fg=col)
            th.config(image=self.thumb(p))

    def refresh_thumbs(self):
        for p in self.photos:
            self.update_row(p)

    def update_total(self):
        n, m = len(self.photos), sum(p.copies for p in self.photos)
        self.lbl_total.config(text=f"{n} photo{'s' if n != 1 else ''}  -  {m} prints in total" if n else "No photos yet")

    def select(self, p):
        self.sel = p
        for q, (row, th, st, name) in self.rows.items():
            c = "#dbe9fb" if q is p else "#fafafa"
            for w in (row, th, st, name):
                w.config(bg=c)
        self.load_editor()

    # ------------------------------------------------------------------ editor
    def load_editor(self):
        p = self.sel
        self.loading_editor = True
        e = p.edit if p else imaging.default_edit()
        for k, v in self.edit_vars.items():
            v.set(e[k])
        self.loading_editor = False
        self.lbl_sel.config(text=p.name if p else "Select a photo from the list")
        self.update_slider_labels()
        self.draw_editor()

    def update_slider_labels(self):
        fm = {"zoom": "{:.2f}x", "dx": "{:+.2f}", "dy": "{:+.2f}", "tilt": "{:+.1f}°", "bright": "{:+.0f}", "contrast": "{:+.0f}"}
        for k, (s, lab) in self.sliders.items():
            lab.config(text=fm[k].format(self.edit_vars[k].get()))

    def on_slider(self, key):
        if self.loading_editor or not self.sel:
            return
        self.sel.edit[key] = float(self.edit_vars[key].get())
        self.after_edit()

    def after_edit(self):
        self.update_slider_labels()
        self.touch()
        self.draw_editor()
        self.update_row(self.sel)

    def rot90(self, d):
        if self.sel:
            self.sel.edit["rot90"] = (self.sel.edit["rot90"] + d) % 4
            self.after_edit()

    def reset_edit(self):
        if self.sel:
            self.sel.edit = imaging.default_edit()
            self.load_editor()
            self.touch()
            self.update_row(self.sel)

    def draw_editor(self):
        c = self.ed_canvas
        c.delete("all")
        W, H = max(50, c.winfo_width()), max(50, c.winfo_height())
        p = self.sel
        if not p:
            c.create_text(W // 2, H // 2, text="Add photos, then select one to edit", fill="#777", font=("Segoe UI", 12))
            return
        if p.cutout is None:
            msg = {"error": "Could not process this photo:\n" + p.error}.get(p.state, "Processing this photo...")
            c.create_text(W // 2, H // 2, text=msg, fill="#777", font=("Segoe UI", 12), justify="center")
            return
        spec = self.spec()
        aspect = spec.photo_w / spec.photo_h
        iw = int(min(W - 20, (H - 20) * aspect))
        ih = int(iw / aspect)
        im = imaging.render(p.cutout, p.face, p.edit, spec.head, self.bg_rgb(), iw, ih, ss=1)
        self.ed_tk = ImageTk.PhotoImage(im)
        x0, y0 = (W - iw) // 2, (H - ih) // 2
        c.create_image(x0, y0, anchor="nw", image=self.ed_tk)
        c.create_rectangle(x0, y0, x0 + iw, y0 + ih, outline="#444")
        self.ed_img_size = (iw, ih)
        if self.v_guides.get():
            m = 0.28 * (1 - spec.head)
            for fy in (m, m + spec.head):
                c.create_line(x0, y0 + fy * ih, x0 + iw, y0 + fy * ih, fill="#ef4444", dash=(4, 3))
            c.create_line(x0 + iw / 2, y0, x0 + iw / 2, y0 + ih, fill="#ef4444", dash=(4, 3))
            c.create_text(x0 + 6, y0 + m * ih - 8, text="top of head", anchor="w", fill="#ef4444", font=("Segoe UI", 8))
            c.create_text(x0 + 6, y0 + (m + spec.head) * ih + 8, text="chin", anchor="w", fill="#ef4444", font=("Segoe UI", 8))

    def on_drag_start(self, e):
        self.drag = (e.x, e.y)

    def on_drag(self, e):
        p = self.sel
        if not p or p.cutout is None or not hasattr(self, "drag"):
            return
        iw, ih = self.ed_img_size
        p.edit["dx"] = max(-0.5, min(0.5, p.edit["dx"] - (e.x - self.drag[0]) / iw))
        p.edit["dy"] = max(-0.5, min(0.5, p.edit["dy"] - (e.y - self.drag[1]) / ih))
        self.drag = (e.x, e.y)
        self.loading_editor = True
        self.edit_vars["dx"].set(p.edit["dx"])
        self.edit_vars["dy"].set(p.edit["dy"])
        self.loading_editor = False
        self.after_edit()

    def on_wheel(self, e):
        p = self.sel
        if p and p.cutout is not None:
            p.edit["zoom"] = max(0.5, min(2.5, p.edit["zoom"] * (1.05 if e.delta > 0 else 1 / 1.05)))
            self.loading_editor = True
            self.edit_vars["zoom"].set(p.edit["zoom"])
            self.loading_editor = False
            self.after_edit()

    def on_bg_change(self):
        for p in self.photos:
            p.thumb_key = None
        self.touch()
        self.refresh_thumbs()
        self.draw_editor()

    def pick_color(self):
        c = colorchooser.askcolor(color=self.bg_custom, title="Background colour")
        if c and c[1]:
            self.bg_custom = c[1]
            self.swatch.config(bg=self.bg_custom)
            self.v_bg.set("custom")
            self.on_bg_change()

    def on_remove_toggle(self):
        mode = "ai" if self.v_remove.get() else "none"
        for p in self.photos:
            if p.mode != mode:
                p.cutout, p.state = None, "new"
        self.refresh_list()
        self.touch()
        self.queue_prepare()
        self.draw_editor()

    # ------------------------------------------------------------------ jobs
    def enqueue(self, job):
        self.jobs.append(job)
        self.start_next()

    def start_next(self):
        if self.active or not self.jobs:
            return
        job = self.jobs.popleft()
        self.active = job
        self.job_t0 = self.last_prog = time.time()
        self.pb["value"] = 0
        self.lbl_pct.config(text="0%")
        self.lbl_stage.config(text="Starting...")
        self.lbl_detail.config(text="")
        self.btn_cancel.config(state="normal")
        threading.Thread(target=worker.run_job, args=(job, self.q), daemon=True).start()

    def idle_status(self):
        self.btn_cancel.config(state="disabled")
        ready = model.session_ready()
        self.lbl_stage.config(text="Ready" if ready or not self.v_remove.get() else "AI model not loaded yet")
        self.lbl_detail.config(text="Everything runs on this PC - photos are never uploaded.")
        self.pb["value"] = 0
        self.lbl_pct.config(text="")

    def cancel_job(self, silent=False):
        if self.active:
            self.active.cancel.set()
        for j in list(self.jobs) + ([self.active] if self.active else []):
            for p in j.photos:
                if p.state in ("queued", "processing"):
                    p.state = "new"
        self.jobs.clear()
        self.active = None
        self.refresh_thumbs()
        self.idle_status()
        if not silent:
            self.lbl_stage.config(text="Cancelled")
            self.lbl_detail.config(text="Press Generate sheet to process the photos again.")

    def poll(self):
        try:
            while True:
                self.handle(self.q.get_nowait())
        except queue.Empty:
            pass
        if self.active:
            el = time.time() - self.job_t0
            extra = "   (taking longer than usual - you can Cancel)" if time.time() - self.last_prog > 45 else ""
            base = self.lbl_detail.cget("text").split("   [")[0].replace("   (taking longer than usual - you can Cancel)", "")
            self.lbl_detail.config(text=f"{base}   [{el:.0f}s]{extra}")
        self.root.after(100, self.poll)

    def handle(self, m):
        kind, jid = m[0], m[1]
        job = self.active
        if job is None or job.id != jid:
            return  # message from a cancelled job
        if kind == "progress":
            _, _, pct, stage, detail = m
            self.last_prog = time.time()
            self.pb["value"] = pct
            self.lbl_pct.config(text=f"{pct:.0f}%")
            self.lbl_stage.config(text=stage)
            self.lbl_detail.config(text=detail)
        elif kind == "photo":
            p = m[2]
            self.update_row(p)
            if p is self.sel:
                self.load_editor()
        elif kind == "done":
            self.finish(job)
        elif kind == "cancelled":
            self.active = None
            self.idle_status()
            self.start_next()
        elif kind == "error":
            self.fail(job, m[2], m[3])

    def finish(self, job):
        self.active = None
        self.refresh_thumbs()
        if job.kind == "sheet" and job.result:
            self.pages, self.pages_ok, self.page_idx = job.result, True, 0
            self.lbl_stale.config(text="")
            self.draw_preview()
            self.nb.select(2)
            if job.saved:
                messagebox.showinfo("Saved", "Saved:\n" + "\n".join(job.saved))
            elif job.printed:
                messagebox.showinfo("Printing", "The sheet was sent to the printer.\nPrint at 100% / actual size.")
            bad = [p.name for p in job.photos if p.state == "error"]
            if bad:
                messagebox.showwarning("Some photos were skipped", "These photos could not be processed:\n" + "\n".join(bad))
        self.idle_status()
        if job.kind == "warmup":
            self.lbl_stage.config(text="AI model ready")
        self.start_next()

    def fail(self, job, kind, text):
        self.active = None
        for p in job.photos:
            if p.state in ("queued", "processing"):
                p.state = "new"
        self.refresh_thumbs()
        self.idle_status()
        self.lbl_stage.config(text="Problem - see message")
        if kind == "model":
            if messagebox.askretrycancel("AI model problem", text):
                self.enqueue(job.clone())
                return
        else:
            messagebox.showerror("Something went wrong" if kind == "other" else "Layout problem",
                                 text + ("\n\nDetails were saved to the log file." if kind == "other" else ""))
        self.jobs.clear()
        self.start_next()

    # ------------------------------------------------------------------ actions
    def ready_check(self):
        if not self.photos:
            messagebox.showinfo("No photos", "Add at least one photo first.")
            return False
        if self.active and self.active.kind == "sheet":
            return False
        return True

    def generate(self):
        if self.ready_check():
            self.enqueue(worker.Job("sheet", list(self.photos), self.params()))

    def save_sheet(self):
        if not self.ready_check():
            return
        fmt = self.v_fmt.get()
        ext = {"PNG": ".png", "JPG": ".jpg", "PDF": ".pdf"}[fmt]
        path = filedialog.asksaveasfilename(defaultextension=ext, initialfile="passport_photos" + ext,
                                            filetypes=[(fmt, "*" + ext)])
        if path:
            self.enqueue(worker.Job("sheet", list(self.photos), self.params(save=(path, fmt))))

    def print_sheet(self):
        if not self.ready_check():
            return
        try:
            names, default = printing.list_printers()
        except Exception as e:
            messagebox.showerror("Printing", f"Could not list printers: {e}")
            return
        if not names:
            messagebox.showinfo("Printing", "No printer found (printing works on Windows with an installed printer).\n"
                                            "Tip: Save as PDF and print that.")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Print")
        dlg.transient(self.root)
        dlg.grab_set()
        f = ttk.Frame(dlg, padding=16)
        f.pack()
        ttk.Label(f, text="Printer").grid(row=0, column=0, sticky="w")
        v = tk.StringVar(value=default or names[0])
        ttk.Combobox(f, textvariable=v, values=names, state="readonly", width=38).grid(row=1, column=0, pady=6)
        ttk.Label(f, text="Load the right paper. Photos print at their exact size.", foreground="#666").grid(row=2, column=0)

        def go():
            dlg.destroy()
            self.enqueue(worker.Job("sheet", list(self.photos), self.params(printer=v.get())))

        b = ttk.Frame(f)
        b.grid(row=3, column=0, pady=(12, 0))
        ttk.Button(b, text="Print", style="Accent.TButton", command=go).pack(side="left")
        ttk.Button(b, text="Cancel", command=dlg.destroy).pack(side="left", padx=6)

    def flip(self, d):
        if self.pages:
            self.page_idx = (self.page_idx + d) % len(self.pages)
            self.draw_preview()

    def draw_preview(self):
        c = self.pv_canvas
        c.delete("all")
        W, H = max(50, c.winfo_width()), max(50, c.winfo_height())
        if not self.pages:
            self.lbl_page.config(text="No sheet yet")
            c.create_text(W // 2, H // 2, text="Click  Generate sheet  to preview the print layout",
                          fill="#777", font=("Segoe UI", 12))
            return
        pg = self.pages[self.page_idx]
        s = min((W - 20) / pg.width, (H - 20) / pg.height)
        im = pg.resize((max(1, int(pg.width * s)), max(1, int(pg.height * s))), Image.LANCZOS)
        self.pv_tk = ImageTk.PhotoImage(im)
        c.create_image(W // 2, H // 2, image=self.pv_tk)
        self.lbl_page.config(text=f"Sheet {self.page_idx + 1} of {len(self.pages)}")

    def on_close(self):
        self.save_cfg()
        if self.active:
            self.active.cancel.set()
        try:
            self.root.destroy()
        finally:
            logging.shutdown()
            os._exit(0)   # never hang or crash on exit because a worker thread is mid-inference
