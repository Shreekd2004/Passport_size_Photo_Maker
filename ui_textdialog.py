"""'Edit text' dialog: independent text settings for ONE photograph, with a live preview.

Photo text mode:  global (use the global text settings)  |  custom (this photo's own text)  |  none (no text).
Nothing is applied until OK / Apply; the AI background removal is never repeated - only the cheap text render.
"""
import tkinter as tk
from dataclasses import replace
from tkinter import colorchooser, ttk

from PIL import ImageTk

import branding
import imaging
import settings
import textoverlay
from textoverlay import TextStyle
from ui_widgets import ScrollFrame, chip, tip


class TextDialog:
    def __init__(self, app, photo):
        self.app, self.p = app, photo
        w = self.win = tk.Toplevel(app.root)
        w.title(f"Edit text - {photo.name}")
        w.transient(app.root)
        w.geometry(f"{app.sc(1100)}x{app.sc(720)}+{app.root.winfo_rootx() + 60}+{app.root.winfo_rooty() + 40}")
        w.minsize(app.sc(980), app.sc(580))
        w.columnconfigure(1, weight=1)
        w.rowconfigure(0, weight=1)
        base = photo.ptext or app.default_individual_ts(photo)
        self.v = {}
        self._job = None
        self._init = True

        def sv(key, val):
            cls = tk.BooleanVar if isinstance(val, bool) else tk.DoubleVar if isinstance(val, float) else tk.StringVar
            self.v[key] = cls(value=val)
            return self.v[key]

        self.v_mode = tk.StringVar(value=photo.text_mode)
        sf = ScrollFrame(w)
        sf.grid(row=0, column=0, sticky="ns", padx=(10, 6), pady=10)
        sf.canvas.configure(width=app.sc(520))
        b = sf.body

        m = ttk.LabelFrame(b, text="  Text for this photograph  ", padding=8)
        m.pack(fill="x", padx=(0, 8), pady=(0, 8))
        ttk.Radiobutton(m, text="Use the global text settings", value="global", variable=self.v_mode).pack(anchor="w")
        ttk.Radiobutton(m, text="Individual text for this photo (set below)", value="custom", variable=self.v_mode).pack(anchor="w")
        ttk.Radiobutton(m, text="No text on this photo", value="none", variable=self.v_mode).pack(anchor="w")

        c = ttk.LabelFrame(b, text="  What to print  ", padding=8)
        c.pack(fill="x", padx=(0, 8), pady=(0, 8))
        rows = [("use_name", "Customer name", "name", base.use_name, base.name or photo.label),
                ("use_custom", "Custom text", "custom", base.use_custom, base.custom),
                ("use_dob", "Date of birth", "dob", base.use_dob, base.dob),
                ("use_cdate", "Custom date", "cdate", base.use_cdate, base.cdate)]
        for i, (ck, label, ek, on, txt) in enumerate(rows):
            ttk.Checkbutton(c, text=label, variable=sv(ck, bool(on))).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(c, textvariable=sv(ek, txt or ""), width=26).grid(row=i, column=1, padx=8, pady=2)
        r = len(rows)
        ttk.Checkbutton(c, text="Photograph date", variable=sv("use_date", bool(base.use_date))).grid(row=r, column=0, sticky="w", pady=2)
        d = ttk.Frame(c)
        d.grid(row=r, column=1, sticky="w", padx=8)
        sv("date_mode", base.date_mode)
        ttk.Radiobutton(d, text="Today", value="today", variable=self.v["date_mode"]).pack(side="left")
        ttk.Radiobutton(d, text="Type:", value="manual", variable=self.v["date_mode"]).pack(side="left", padx=(8, 2))
        ttk.Entry(d, textvariable=sv("date_text", base.date_text or ""), width=12).pack(side="left")
        ttk.Checkbutton(c, text="One item per line (otherwise all on one line)", variable=sv("multiline", bool(base.multiline))).grid(
            row=r + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        s = ttk.LabelFrame(b, text="  Look  ", padding=8)
        s.pack(fill="x", padx=(0, 8), pady=(0, 8))
        ttk.Label(s, text="Font").grid(row=0, column=0, sticky="w")
        ttk.Combobox(s, textvariable=sv("font", base.font), values=textoverlay.FONT_CHOICES, state="readonly", width=20).grid(row=0, column=1, sticky="w", padx=6, pady=2)
        ttk.Checkbutton(s, text="Bold", variable=sv("bold", bool(base.bold))).grid(row=0, column=2)
        ttk.Label(s, text="Size (pt)").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(s, from_=4, to=40, increment=0.5, width=6, textvariable=sv("size_pt", float(base.size_pt))).grid(row=1, column=1, sticky="w", padx=6, pady=2)
        ttk.Label(s, text="Text colour").grid(row=2, column=0, sticky="w")
        sv("color", "#%02X%02X%02X" % tuple(base.color))
        self.chip_c = chip(s, self.v["color"].get(), lambda: self.pick("color", self.chip_c, "Text colour"), 3)
        self.chip_c.grid(row=2, column=1, sticky="w", padx=6, pady=2)
        ttk.Label(s, text="Alignment").grid(row=3, column=0, sticky="w")
        al = ttk.Frame(s)
        al.grid(row=3, column=1, columnspan=2, sticky="w", padx=6)
        sv("align", base.align)
        for val, lab in (("left", "Left"), ("center", "Centre"), ("right", "Right")):
            ttk.Radiobutton(al, text=lab, value=val, variable=self.v["align"]).pack(side="left", padx=(0, 8))
        ttk.Label(s, text="Position").grid(row=4, column=0, sticky="nw", pady=(8, 0))
        pf = ttk.Frame(s)
        pf.grid(row=4, column=1, columnspan=2, sticky="w", padx=6, pady=(8, 0))
        sv("position", base.position)
        for val, lab in (("inside", "Inside photo (bottom centre)"), ("below", "Below photo - outside image (adds height)"),
                         ("fixed", "Below photo - fixed canvas (exact size)")):
            ttk.Radiobutton(pf, text=lab, value=val, variable=self.v["position"]).pack(anchor="w")
        ttk.Label(s, text="Text area height (mm)").grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Spinbox(s, from_=2, to=20, increment=0.5, width=6, textvariable=sv("area_mm", float(base.area_mm))).grid(row=5, column=2, sticky="w", pady=(4, 0))
        ttk.Label(s, text="Vertical position").grid(row=6, column=0, sticky="w", pady=(4, 0))
        ttk.Scale(s, from_=-6, to=20, variable=sv("voff_mm", float(base.voff_mm)), length=app.sc(150)).grid(row=6, column=1, sticky="w", padx=6, pady=(4, 0))
        bgr = ttk.Frame(s)
        bgr.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Checkbutton(bgr, text="Text background / text area colour", variable=sv("bg_on", bool(base.bg_on))).pack(side="left")
        sv("bg_color", "#%02X%02X%02X" % tuple(base.bg_color))
        self.chip_b = chip(bgr, self.v["bg_color"].get(), lambda: self.pick("bg_color", self.chip_b, "Text background colour"), 3)
        self.chip_b.pack(side="left", padx=8)

        btn = ttk.Frame(b)
        btn.pack(fill="x", padx=(0, 8), pady=(0, 10))
        ttk.Button(btn, text="OK", style="Accent.TButton", command=self.apply).pack(side="left")
        ttk.Button(btn, text="Cancel", command=self.win.destroy).pack(side="left", padx=6)
        tip(ttk.Button(btn, text="Apply this look to all photos", command=self.apply_look_to_all),
            "Copies font, size, colour, alignment, position and text area to every photo's own text (names/dates stay different).").pack(side="left")

        pv = ttk.Frame(w)
        pv.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        pv.rowconfigure(1, weight=1)
        pv.columnconfigure(0, weight=1)
        ttk.Label(pv, text="Live preview", font=(branding.FONT, 11, "bold")).grid(row=0, column=0, sticky="w")
        self.canvas = tk.Canvas(pv, bg="#E8EEF6", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=6)
        self.lbl_info = ttk.Label(pv, text="", foreground=branding.MUTED, wraplength=app.sc(480), justify="left")
        self.lbl_info.grid(row=2, column=0, sticky="w")
        self.canvas.bind("<Configure>", lambda e: self.schedule())

        for k, var in self.v.items():                       # any edit refreshes the preview (and selects 'individual')
            var.trace_add("write", lambda *a, k=k: self.changed(k))
        self.v_mode.trace_add("write", lambda *a: self.schedule())
        self._init = False
        self.schedule()

    # ------------------------------------------------------------------
    def pick(self, key, chip_btn, title):
        c = colorchooser.askcolor(color=self.v[key].get(), title=title, parent=self.win)
        if c and c[1]:
            self.v[key].set(c[1])
            chip_btn.config(bg=c[1], activebackground=c[1])

    def changed(self, key):
        if self._init:
            return
        if self.v_mode.get() != "custom":
            self.v_mode.set("custom")                       # touching an individual setting = use individual text
        self.schedule()

    def schedule(self):
        if self._job is None:
            self._job = self.win.after(40, self.draw)

    def val(self, key, default):
        try:
            return self.v[key].get()
        except (tk.TclError, ValueError):
            return default

    def to_ts(self):
        g = self.val
        return TextStyle(
            enabled=True, use_name=g("use_name", False), name=g("name", ""), use_custom=g("use_custom", False),
            custom=g("custom", ""), use_dob=g("use_dob", False), dob=g("dob", ""), use_date=g("use_date", False),
            date_mode=g("date_mode", "today"), date_text=g("date_text", ""), use_cdate=g("use_cdate", False),
            cdate=g("cdate", ""), multiline=g("multiline", False), font=g("font", textoverlay.FONT_CHOICES[0]),
            bold=g("bold", False), size_pt=max(4.0, float(g("size_pt", 9.0))), color=settings.hex_to_rgb(g("color", "#000000")),
            align=g("align", "center"), position=g("position", "inside"), area_mm=float(g("area_mm", 5.0)),
            voff_mm=float(g("voff_mm", 0.0)), bg_on=g("bg_on", True), bg_color=settings.hex_to_rgb(g("bg_color", "#FFFFFF")))

    def preview_ts(self):
        mode = self.v_mode.get()
        if mode == "none":
            return TextStyle(enabled=False)
        if mode == "global":
            return self.app.text_style()
        return self.to_ts()

    def draw(self):
        self._job = None
        c = self.canvas
        c.delete("all")
        W, H = max(80, c.winfo_width()), max(80, c.winfo_height())
        p, app = self.p, self.app
        if p.src is None or p.state != "ready":
            c.create_text(W // 2, H // 2, text="This photo is still processing...", fill="#6B7C93", font=(branding.FONT, 12))
            return
        spec, style = app.spec(), app.img_style()
        ts = self.preview_ts()
        cap = textoverlay.caption_mm(ts)
        extra = cap if (ts.enabled and ts.position == "below") else 0
        iw = max(60, int(min(W - 24, (H - 24) * spec.photo_w / (spec.photo_h + extra))))
        cell, bh = imaging.render_cell(p, spec, style, iw, ss=1, ts=ts, caption_mm=cap)
        self.tk_img = ImageTk.PhotoImage(cell)
        x0, y0 = (W - cell.width) // 2, (H - cell.height) // 2
        c.create_image(x0, y0, anchor="nw", image=self.tk_img)
        c.create_rectangle(x0, y0, x0 + cell.width - 1, y0 + bh, outline="#2B3A55")
        ppm = cell.width / spec.photo_w
        total_mm = cell.height / ppm
        text = textoverlay.resolve_text(ts, p.label).replace("\n", "  /  ")
        mode_txt = {"global": "Using the global text settings", "none": "No text on this photograph",
                    "custom": "Individual text"}[self.v_mode.get()]
        fixed = ts.enabled and ts.position == "fixed"
        self.lbl_info.config(text=f"{mode_txt}. Printed text: {text!r}\nFinal size of one photo: {spec.photo_w:g} x {total_mm:.1f} mm"
                                  + ("  (fixed canvas - stays exactly the selected size)" if fixed else
                                     "  (outside image - taller than the selected size)" if (ts.enabled and ts.position == 'below') else ""))

    # ------------------------------------------------------------------
    def apply(self):
        a, p = self.app, self.p
        a.push_history()
        p.text_mode = self.v_mode.get()
        if p.text_mode == "custom":
            p.ptext = self.to_ts()
        if p.text_mode != "global" and a.g("t_mode") != "individual":
            a.V["t_mode"].set("individual")                  # individual settings only count in Individual mode
            a.lbl_detail.config(text="Text mode switched to 'Individual' so this photo's own text is used.")
        a.after_text_change()
        self.win.destroy()

    def apply_look_to_all(self):
        a = self.app
        a.push_history()
        t = self.to_ts()
        keys = ("font", "bold", "size_pt", "color", "align", "position", "area_mm", "voff_mm", "bg_on", "bg_color")
        for q in a.photos:
            base = q.ptext or a.default_individual_ts(q)
            q.ptext = replace(base, **{k: getattr(t, k) for k in keys})
        a.after_text_change()
        self.lbl_info.config(text="Look copied to every photo's individual text.")
