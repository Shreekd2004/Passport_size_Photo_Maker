"""SECTION 2 - EDITING: background, crop / zoom / rotate / brightness / contrast / sharpness, text overlay."""
import tkinter as tk
from tkinter import colorchooser, ttk

from PIL import ImageTk

import branding
import imaging
import textoverlay
from ui_widgets import ScrollFrame, chip, tip

BG_CHOICES = [("white", "White", "#FFFFFF"), ("lightblue", "Light blue", "#B9D6F2"),
              ("blue", "Blue", "#2470D6"), ("red", "Red", "#C8232D")]
SLIDERS = [("zoom", "Zoom", 0.5, 2.5, "{:.2f}x"), ("dx", "Move left / right", -0.5, 0.5, "{:+.2f}"),
           ("dy", "Move up / down", -0.5, 0.5, "{:+.2f}"), ("tilt", "Rotate (fine)", -20, 20, "{:+.1f}\u00B0"),
           ("bright", "Brightness", -50, 50, "{:+.0f}"), ("contrast", "Contrast", -50, 50, "{:+.0f}"),
           ("sharp", "Sharpness", -50, 100, "{:+.0f}")]


class EditingMixin:
    def build_editing(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="   2   Editing   ")
        f.columnconfigure(1, weight=1)
        f.rowconfigure(0, weight=1)
        sf = ScrollFrame(f)
        sf.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        sf.canvas.configure(width=self.sc(420))
        body = sf.body

        # -- background --
        bg = ttk.LabelFrame(body, text="  Background  ", padding=8)
        bg.pack(fill="x", pady=(0, 8), padx=(0, 6))
        c = ttk.Checkbutton(bg, text="Remove background (AI, runs on this PC)", variable=self.V["remove_bg"])
        c.pack(anchor="w")
        tip(c, "Switch OFF to keep the original background of the photograph.")
        ttk.Label(bg, text="Background colour", foreground=branding.MUTED).pack(anchor="w", pady=(6, 2))
        grid = ttk.Frame(bg)
        grid.pack(anchor="w")
        for i, (val, label, hexc) in enumerate(BG_CHOICES):
            chip(grid, hexc, size=2).grid(row=i // 2, column=(i % 2) * 2, padx=(0, 4), pady=2)
            ttk.Radiobutton(grid, text=label, value=val, variable=self.V["bg_choice"]).grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(0, 14))
        cr = ttk.Frame(bg)
        cr.pack(anchor="w", pady=(2, 0))
        self.chip_bg = chip(cr, self.g("bg_custom"), lambda: self.pick_color("bg_custom", self.chip_bg, "Background colour", "bg_choice"), 2)
        self.chip_bg.pack(side="left", padx=(0, 4))
        ttk.Radiobutton(cr, text="Custom colour...", value="custom", variable=self.V["bg_choice"]).pack(side="left")

        # -- adjustments --
        adj = ttk.LabelFrame(body, text="  Adjust photo  ", padding=8)
        adj.pack(fill="x", pady=(0, 8), padx=(0, 6))
        self.lbl_sel = ttk.Label(adj, text="Select a photo from the list", font=(branding.FONT, 10, "bold"))
        self.lbl_sel.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.edit_vars, self.sliders = {}, {}
        for i, (key, label, lo, hi, fmt) in enumerate(SLIDERS, start=1):
            ttk.Label(adj, text=label).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.DoubleVar(value=imaging.default_edit()[key])
            self.edit_vars[key] = var
            s = ttk.Scale(adj, from_=lo, to=hi, variable=var, length=self.sc(170), command=lambda v, k=key: self.on_slider(k))
            s.grid(row=i, column=1, padx=6)
            lab = ttk.Label(adj, width=6)
            lab.grid(row=i, column=2)
            self.sliders[key] = (lab, fmt)
        bt = ttk.Frame(adj)
        bt.grid(row=len(SLIDERS) + 1, column=0, columnspan=3, pady=(8, 0), sticky="w")
        ttk.Button(bt, text="\u21B6 90\u00B0", width=6, command=lambda: self.rot90(-1)).pack(side="left")
        ttk.Button(bt, text="90\u00B0 \u21B7", width=6, command=lambda: self.rot90(1)).pack(side="left", padx=4)
        tip(ttk.Button(bt, text="Reset / auto-fit", command=self.reset_edit), "Undo manual zoom / move / rotate for this photo").pack(side="left")
        ttk.Checkbutton(adj, text="Show alignment guides", variable=self.V["head_guides"]).grid(
            row=len(SLIDERS) + 2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(adj, text="Tip: drag the photo to position it, mouse wheel to zoom.", foreground=branding.MUTED).grid(
            row=len(SLIDERS) + 3, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # -- text overlay --
        t = ttk.LabelFrame(body, text="  Text overlay  ", padding=8)
        t.pack(fill="x", pady=(0, 8), padx=(0, 6))
        ttk.Checkbutton(t, text="Add text to every photo", variable=self.V["t_enabled"]).pack(anchor="w")
        r1 = ttk.Frame(t)
        r1.pack(fill="x", pady=(6, 0))
        ttk.Radiobutton(r1, text="Custom text", value="custom", variable=self.V["t_source"]).grid(row=0, column=0, sticky="w")
        ttk.Entry(r1, textvariable=self.V["t_custom"], width=26).grid(row=0, column=1, padx=6, pady=2)
        ttk.Radiobutton(r1, text="Customer name", value="name", variable=self.V["t_source"]).grid(row=1, column=0, sticky="w")
        e = ttk.Entry(r1, textvariable=self.v_label, width=26)
        e.grid(row=1, column=1, padx=6, pady=2)
        tip(e, "Name printed for the SELECTED photo. It starts as the file name - edit it per customer.")
        self.v_label.trace_add("write", lambda *a: self.on_label_changed())
        r2 = ttk.Frame(t)
        r2.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(r2, text="Add date", variable=self.V["t_date"]).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(r2, text="Today", value="today", variable=self.V["t_date_mode"]).grid(row=0, column=1, padx=6)
        ttk.Radiobutton(r2, text="Type date:", value="manual", variable=self.V["t_date_mode"]).grid(row=0, column=2)
        ttk.Entry(r2, textvariable=self.V["t_date_text"], width=12).grid(row=0, column=3, padx=4)
        ttk.Checkbutton(t, text="Put the date on a second line", variable=self.V["t_two"]).pack(anchor="w", pady=(4, 0))
        ttk.Separator(t).pack(fill="x", pady=8)
        r3 = ttk.Frame(t)
        r3.pack(fill="x")
        ttk.Label(r3, text="Font").grid(row=0, column=0, sticky="w")
        ttk.Combobox(r3, textvariable=self.V["t_font"], values=textoverlay.FONT_CHOICES, state="readonly", width=20).grid(row=0, column=1, padx=6, pady=2, sticky="w")
        ttk.Checkbutton(r3, text="Bold", variable=self.V["t_bold"]).grid(row=0, column=2)
        ttk.Label(r3, text="Size (pt)").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(r3, from_=4, to=40, increment=0.5, width=6, textvariable=self.V["t_size"]).grid(row=1, column=1, padx=6, pady=2, sticky="w")
        ttk.Label(r3, text="Text colour").grid(row=2, column=0, sticky="w")
        self.chip_t = chip(r3, self.g("t_color"), lambda: self.pick_color("t_color", self.chip_t, "Text colour"), 3)
        self.chip_t.grid(row=2, column=1, padx=6, pady=2, sticky="w")
        ttk.Label(r3, text="Alignment").grid(row=3, column=0, sticky="w")
        al = ttk.Frame(r3)
        al.grid(row=3, column=1, columnspan=2, sticky="w", padx=6)
        for v, lab in (("left", "Left"), ("center", "Centre"), ("right", "Right")):
            ttk.Radiobutton(al, text=lab, value=v, variable=self.V["t_align"]).pack(side="left", padx=(0, 8))
        ttk.Label(t, text="Position").pack(anchor="w", pady=(8, 0))
        ttk.Radiobutton(t, text="Inside photo (bottom centre)", value="inside", variable=self.V["t_pos"]).pack(anchor="w")
        ttk.Radiobutton(t, text="Below photo (does not cover the picture)", value="below", variable=self.V["t_pos"]).pack(anchor="w")
        r4 = ttk.Frame(t)
        r4.pack(fill="x", pady=(6, 0))
        ttk.Label(r4, text="Vertical position").grid(row=0, column=0, sticky="w")
        ttk.Scale(r4, from_=-6, to=20, variable=self.V["t_voff"], length=self.sc(150)).grid(row=0, column=1, padx=6)
        ttk.Label(r4, text="(mm, up +)", foreground=branding.MUTED).grid(row=0, column=2)
        r5 = ttk.Frame(t)
        r5.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(r5, text="Text background", variable=self.V["t_bg_on"]).pack(side="left")
        self.chip_tb = chip(r5, self.g("t_bg_color"), lambda: self.pick_color("t_bg_color", self.chip_tb, "Text background colour"), 3)
        self.chip_tb.pack(side="left", padx=8)
        ttk.Label(t, text="The text is added to the processed photo before copies are made, so every copy matches. "
                          "Your original files are never changed.", wraplength=self.sc(360), foreground=branding.MUTED).pack(anchor="w", pady=(8, 0))

        # -- live preview --
        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self.lbl_face = ttk.Label(right, text="", foreground="#b45309", font=(branding.FONT, 10, "bold"))
        self.lbl_face.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.ed_canvas = tk.Canvas(right, bg="#E8EEF6", highlightthickness=0)
        self.ed_canvas.grid(row=1, column=0, sticky="nsew")
        self.ed_canvas.bind("<Configure>", lambda e: self.redraw_editor())
        self.ed_canvas.bind("<ButtonPress-1>", lambda e: setattr(self, "drag", (e.x, e.y)))
        self.ed_canvas.bind("<B1-Motion>", self.on_drag)
        self.ed_canvas.bind("<MouseWheel>", self.on_wheel)
        self.ed_photo_size = (1, 1)
        return f

    # ---- colour pickers ---------------------------------------------------------------------
    def pick_color(self, key, chip_btn, title, select_key=None):
        c = colorchooser.askcolor(color=self.g(key), title=title)
        if c and c[1]:
            self.V[key].set(c[1])
            chip_btn.config(bg=c[1], activebackground=c[1])
            if select_key:
                self.V[select_key].set("custom")

    def sync_chips(self):
        for btn, key in ((self.chip_bg, "bg_custom"), (self.chip_t, "t_color"), (self.chip_tb, "t_bg_color")):
            btn.config(bg=self.g(key), activebackground=self.g(key))

    # ---- selected photo -------------------------------------------------------------------------
    def load_editor(self):
        p = self.sel
        self.loading_editor = True
        e = p.edit if p else imaging.default_edit()
        for k, v in self.edit_vars.items():
            v.set(e[k])
        self.v_label.set(p.label if p else "")
        self.loading_editor = False
        self.lbl_sel.config(text=p.name if p else "Select a photo from the list")
        self.update_slider_labels()
        self.draw_editor()

    def update_slider_labels(self):
        for k, (lab, fmt) in self.sliders.items():
            lab.config(text=fmt.format(self.edit_vars[k].get()))

    def on_label_changed(self):
        p = self.sel
        if self.loading_editor or p is None:
            return
        new = self.v_label.get()
        if new != p.label:
            self.push_history(("label", id(p)))
            p.label = new
            self.touch()
            self.mark_dirty()
            self.redraw_editor()

    def on_slider(self, key):
        p = self.sel
        if self.loading_editor or p is None:
            return
        self.push_history(("edit", id(p)))
        p.edit[key] = float(self.edit_vars[key].get())
        self.after_edit()

    def after_edit(self):
        self.update_slider_labels()
        self.touch()
        self.redraw_editor()
        self.update_row(self.sel)
        self.mark_dirty()

    def rot90(self, d):
        if self.sel:
            self.push_history()
            self.sel.edit["rot90"] = (self.sel.edit["rot90"] + d) % 4
            self.after_edit()

    def reset_edit(self):
        if self.sel:
            self.push_history()
            self.sel.edit = imaging.default_edit()
            self.load_editor()
            self.touch()
            self.update_row(self.sel)
            self.mark_dirty()

    # ---- live preview ---------------------------------------------------------------------------
    def draw_editor(self):
        c = self.ed_canvas
        c.delete("all")
        W, H = max(80, c.winfo_width()), max(80, c.winfo_height())
        p = self.sel
        self.lbl_face.config(text="")
        if p is None:
            c.create_text(W // 2, H // 2, text="Add photos, then select one to edit", fill="#6B7C93", font=(branding.FONT, 12))
            return
        if p.src is None or p.state != "ready":
            msg = ("Could not process this photo:\n" + p.error) if p.state == "error" else "Processing this photo..."
            c.create_text(W // 2, H // 2, text=msg, fill="#6B7C93", font=(branding.FONT, 12), justify="center")
            return
        spec, style = self.spec(), self.img_style()
        ratio = spec.photo_w / (spec.photo_h + spec.caption_mm)
        iw = max(60, int(min(W - 24, (H - 24) * ratio)))
        cell, ph = imaging.render_cell(p, spec, style, iw, ss=1)
        self.ed_tk = ImageTk.PhotoImage(cell)
        x0, y0 = (W - cell.width) // 2, (H - cell.height) // 2
        c.create_image(x0, y0, anchor="nw", image=self.ed_tk)
        c.create_rectangle(x0, y0, x0 + iw, y0 + ph, outline="#2B3A55")
        self.ed_photo_size = (iw, ph)
        if self.g("head_guides"):
            m = 0.28 * (1 - spec.head)
            for fy in (m, m + spec.head):
                c.create_line(x0, y0 + fy * ph, x0 + iw, y0 + fy * ph, fill="#ef4444", dash=(4, 3))
            c.create_line(x0 + iw / 2, y0, x0 + iw / 2, y0 + ph, fill="#ef4444", dash=(4, 3))
        if not p.face_found:
            self.lbl_face.config(text="Face not found - position the photo by hand: drag it, or use Zoom / Move.")

    def on_drag(self, e):
        p = self.sel
        if p is None or p.src is None or p.state != "ready" or not hasattr(self, "drag"):
            return
        iw, ih = self.ed_photo_size
        self.push_history(("edit", id(p)))
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
        if p is not None and p.src is not None and p.state == "ready":
            self.push_history(("edit", id(p)))
            p.edit["zoom"] = max(0.5, min(2.5, p.edit["zoom"] * (1.05 if e.delta > 0 else 1 / 1.05)))
            self.loading_editor = True
            self.edit_vars["zoom"].set(p.edit["zoom"])
            self.loading_editor = False
            self.after_edit()
