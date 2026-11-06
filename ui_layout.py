"""SECTION 3 - LAYOUT: photo-size presets, custom size (mm / inches), paper, spacing, border, cutting guides, mode."""
from tkinter import messagebox, simpledialog, ttk

import branding
import layout
import presets
import units
from ui_widgets import ScrollFrame, tip


class LayoutMixin:
    def build_layout(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="   3   Layout   ")
        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)
        sf = ScrollFrame(f)
        sf.grid(row=0, column=0, sticky="nsew")
        body = sf.body
        pad = dict(fill="x", pady=(0, 8), padx=(0, 8))
        self.lbl_info = ttk.Label(body, text="", font=(branding.FONT, 11, "bold"), foreground=branding.NAVY, wraplength=self.sc(700))
        self.lbl_info.pack(anchor="w", pady=(0, 8))

        g = ttk.LabelFrame(body, text="  Photo size  ", padding=10)
        g.pack(**pad)
        ttk.Label(g, text="Size").grid(row=0, column=0, sticky="w")
        self.cb_preset = ttk.Combobox(g, textvariable=self.V["photo_preset"], values=[p["name"] for p in self.presets],
                                      state="readonly", width=30)
        self.cb_preset.grid(row=0, column=1, columnspan=3, sticky="w", padx=6)
        self.cb_preset.bind("<<ComboboxSelected>>", lambda e: self.set_preset(self.g("photo_preset")))
        tip(ttk.Button(g, text="Save as preset...", command=self.save_preset), "Remember this size for next time").grid(row=0, column=4, padx=6)
        ttk.Label(g, text="Units").grid(row=1, column=0, sticky="w", pady=4)
        u = ttk.Frame(g)
        u.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Radiobutton(u, text="Millimetres (mm)", value="mm", variable=self.V["unit"], command=self.on_unit_change).pack(side="left")
        ttk.Radiobutton(u, text="Inches (in)", value="in", variable=self.V["unit"], command=self.on_unit_change).pack(side="left", padx=10)
        ttk.Label(g, text="Width").grid(row=2, column=0, sticky="w")
        self.sp_w = ttk.Spinbox(g, from_=0.2, to=400, increment=0.5, width=8, textvariable=self.V["pw"])
        self.sp_w.grid(row=2, column=1, sticky="w", padx=6, pady=2)
        ttk.Label(g, text="Height").grid(row=2, column=2, sticky="e")
        self.sp_h = ttk.Spinbox(g, from_=0.2, to=400, increment=0.5, width=8, textvariable=self.V["ph"])
        self.sp_h.grid(row=2, column=3, sticky="w", padx=6)
        ttk.Label(g, text="Head size (% of height)").grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Spinbox(g, from_=30, to=90, width=8, textvariable=self.V["head"]).grid(row=3, column=2, sticky="w", padx=6, pady=2)
        self.lbl_notes = ttk.Label(g, text="", wraplength=self.sc(640), foreground=branding.MUTED, justify="left")
        self.lbl_notes.grid(row=4, column=0, columnspan=5, sticky="w", pady=(8, 0))

        p = ttk.LabelFrame(body, text="  Paper  ", padding=10)
        p.pack(**pad)
        ttk.Label(p, text="Paper size").grid(row=0, column=0, sticky="w")
        pc = ttk.Combobox(p, textvariable=self.V["paper"], values=[x[0] for x in presets.PAPERS], state="readonly", width=12)
        pc.grid(row=0, column=1, sticky="w", padx=6)
        pc.bind("<<ComboboxSelected>>", lambda e: self.set_paper(self.g("paper")))
        ttk.Label(p, text="W (mm)").grid(row=0, column=2, padx=(12, 0))
        ttk.Spinbox(p, from_=40, to=1000, increment=1, width=7, textvariable=self.V["paper_w"]).grid(row=0, column=3, padx=4)
        ttk.Label(p, text="H (mm)").grid(row=0, column=4)
        ttk.Spinbox(p, from_=40, to=1500, increment=1, width=7, textvariable=self.V["paper_h"]).grid(row=0, column=5, padx=4)
        ttk.Label(p, text="Orientation").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(p, textvariable=self.V["orient"], values=["Auto", "Portrait", "Landscape"], state="readonly",
                     width=12).grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Label(p, text="Auto picks whichever fits the most photos / needs the fewest sheets", foreground=branding.MUTED).grid(
            row=1, column=2, columnspan=4, sticky="w", pady=(8, 0))

        s = ttk.LabelFrame(body, text="  Spacing & border  ", padding=10)
        s.pack(**pad)
        for i, (lbl, key, hi) in enumerate([("Margin (mm)", "margin", 50), ("Horizontal gap (mm)", "hgap", 30), ("Vertical gap (mm)", "vgap", 30)]):
            ttk.Label(s, text=lbl).grid(row=0, column=i * 2, sticky="w", padx=(0 if i == 0 else 14, 0))
            ttk.Spinbox(s, from_=0, to=hi, increment=0.5, width=6, textvariable=self.V[key]).grid(row=0, column=i * 2 + 1, padx=6)
        ttk.Checkbutton(s, text="Black border around each photo", variable=self.V["border"]).grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(s, text="Thickness (px @300 DPI)").grid(row=1, column=3, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Spinbox(s, from_=1, to=12, width=5, textvariable=self.V["border_px"]).grid(row=1, column=5, pady=(10, 0))

        cg = ttk.LabelFrame(body, text="  Cutting guides  ", padding=10)
        cg.pack(**pad)
        for val, lab in (("none", "No cutting guides"), ("thin", "Thin black cutting guides"), ("dotted", "Dotted cutting guides")):
            ttk.Radiobutton(cg, text=lab, value=val, variable=self.V["cut_guides"]).pack(anchor="w")
        ttk.Label(cg, text="Guides run through the middle of the gaps so they never touch a photo. With guides on, gaps are "
                           "kept at least 2 mm wide.", wraplength=self.sc(640), foreground=branding.MUTED).pack(anchor="w", pady=(6, 0))

        lm = ttk.LabelFrame(body, text="  Layout mode  ", padding=10)
        lm.pack(**pad)
        ttk.Radiobutton(lm, text="Continuous packing (recommended) - photos flow one after another, no empty spots",
                        value="continuous", variable=self.V["layout_mode"]).pack(anchor="w")
        ttk.Radiobutton(lm, text="Group by photo - every photo starts on a new row (uses more paper)",
                        value="group", variable=self.V["layout_mode"]).pack(anchor="w", pady=(4, 0))

        self.update_unit_widgets()
        return f

    # ---- photo size / units ---------------------------------------------------------------------
    def update_unit_widgets(self):
        inch = self.g("unit") == "in"
        for sp in (self.sp_w, self.sp_h):
            sp.config(increment=0.05 if inch else 0.5, from_=0.1 if inch else 5, to=16 if inch else 400)

    def sync_preset_notes(self):
        pr = self.preset_by_name.get(self.g("photo_preset"))
        self.lbl_notes.config(text=((pr["country"] + ": ") if pr and pr["country"] else "") + (pr["notes"] if pr else ""))
        self.update_unit_widgets()
        self.sync_chips()

    def set_preset(self, name):
        pr = self.preset_by_name.get(name)
        if not pr:
            return
        self.lock_traces = True
        self.V["photo_preset"].set(name)
        if name != "Custom":
            unit = self.g("unit")
            nd = 3 if unit == "in" else 2
            self.V["pw"].set(round(units.from_mm(pr["w_mm"], unit), nd))
            self.V["ph"].set(round(units.from_mm(pr["h_mm"], unit), nd))
            self.V["head"].set(int(round(pr["head_ratio"] * 100)))
        self.lock_traces = False
        self.sync_preset_notes()
        self.on_setting("photo_preset")

    def on_unit_change(self):
        new, old = self.g("unit"), self._unit_prev
        if new != old:
            self.lock_traces = True
            nd = 3 if new == "in" else 2
            for k in ("pw", "ph"):
                self.V[k].set(round(units.from_mm(units.to_mm(self.g(k), old), new), nd))
            self.lock_traces = False
            self._unit_prev = new
            self.update_unit_widgets()
        self.on_setting("pw")

    def mark_custom_photo(self):
        """User typed a size: switch the preset box to 'Custom' unless it still matches the chosen preset."""
        pr = self.preset_by_name.get(self.g("photo_preset"))
        if not pr or pr["name"] == "Custom":
            return
        unit = self.g("unit")
        same = (abs(units.to_mm(self.g("pw"), unit) - pr["w_mm"]) < 0.06 and abs(units.to_mm(self.g("ph"), unit) - pr["h_mm"]) < 0.06
                and abs(self.g("head") - pr["head_ratio"] * 100) < 0.6)
        if not same:
            self.lock_traces = True
            self.V["photo_preset"].set("Custom")
            self.lock_traces = False
            self.sync_preset_notes()

    def save_preset(self):
        name = simpledialog.askstring("Save size", "Name for this photo size (e.g. 'College ID'):", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in {p["name"] for p in presets.PHOTO_PRESETS}:
            messagebox.showinfo("Save size", "That name is used by a built-in size. Please choose another name.")
            return
        spec = self.spec()
        presets.save_user_preset(name, spec.photo_w, spec.photo_h, spec.head)
        self.presets = presets.load_photo_presets()
        self.preset_by_name = {p["name"]: p for p in self.presets}
        self.cb_preset.config(values=[p["name"] for p in self.presets])
        self.set_preset(name)
        self.refresh_home()

    # ---- paper ----------------------------------------------------------------------------------
    def set_paper(self, name):
        for n, w, h in presets.PAPERS:
            if n == name and w:
                self.lock_traces = True
                self.V["paper"].set(name)
                self.V["paper_w"].set(w)
                self.V["paper_h"].set(h)
                self.lock_traces = False
        self.on_setting("paper")

    def mark_custom_paper(self):
        cur = self.g("paper")
        for n, w, h in presets.PAPERS:
            if n == cur and w and (abs(self.g("paper_w") - w) > 0.2 or abs(self.g("paper_h") - h) > 0.2):
                self.lock_traces = True
                self.V["paper"].set("Custom")
                self.lock_traces = False

    def update_info(self):
        spec = self.spec()
        counts = [p.copies for p in self.photos]
        try:
            t = layout.summary(spec, counts)
            if spec.guides != "none" and (spec.hgap < layout.GUIDE_MIN_GAP_MM or spec.vgap < layout.GUIDE_MIN_GAP_MM):
                t += "\n(gaps widened to 2 mm so the cutting guides do not touch the photos)"
        except layout.LayoutError as e:
            t = str(e)
        self.lbl_info.config(text=t)
