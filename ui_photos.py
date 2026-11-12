"""SECTION 1 - PHOTOS: add / import / drag & drop, thumbnails, per-photo copies, reorder, duplicate, remove."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

import branding
import imaging
import worker
from imaging import Photo
from ui_widgets import tip

EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
ROW_BG, ROW_SEL = "#FAFAFA", "#D6E8FA"


class PhotosMixin:
    def build_photos(self, parent):
        f = ttk.LabelFrame(parent, text="  1   Photos  ", padding=8, width=self.sc(440))
        f.grid(row=0, column=0, sticky="ns")
        f.grid_propagate(False)
        f.rowconfigure(3, weight=1)
        f.columnconfigure(0, weight=1)
        bar = ttk.Frame(f)
        bar.grid(row=0, column=0, sticky="ew")
        b = ttk.Button(bar, text="Add photos...", style="Accent.TButton", command=self.add_files)
        b.pack(side="left")
        tip(b, "Choose one or many photos (Ctrl+O). You can also drag & drop them onto this window.")
        tip(ttk.Button(bar, text="Import folder...", command=self.add_folder), "Add every photo in a folder (Ctrl+Shift+F)").pack(side="left", padx=4)
        tip(ttk.Button(bar, text="Duplicate", command=self.duplicate_selected), "Copy the selected photo with its edits (Ctrl+D)").pack(side="left")
        tip(ttk.Button(bar, text="Clear all", command=self.clear_all), "Remove all photos and start fresh (Ctrl+N)").pack(side="left", padx=4)
        dc = ttk.Frame(f)
        dc.grid(row=1, column=0, sticky="w", pady=(6, 2))
        ttk.Label(dc, text="Copies for newly added photos:").pack(side="left")
        ttk.Spinbox(dc, from_=1, to=99, width=4, textvariable=self.V["default_copies"]).pack(side="left", padx=6)
        self.lbl_hint = ttk.Label(f, text="Tip: drag & drop photos anywhere on this window.", foreground=branding.MUTED)
        self.lbl_hint.grid(row=2, column=0, sticky="w", pady=(0, 4))
        box = ttk.Frame(f)
        box.grid(row=3, column=0, sticky="nsew")
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        self.list_canvas = tk.Canvas(box, highlightthickness=0, bg=ROW_BG)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.list_canvas.yview)
        self.list_canvas.configure(yscrollcommand=sb.set)
        self.list_canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.list_inner = tk.Frame(self.list_canvas, bg=ROW_BG)
        self.list_win = self.list_canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        self.list_inner.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfigure(self.list_win, width=e.width))
        self.list_canvas.bind("<Enter>", lambda e: self.list_canvas.bind_all("<MouseWheel>", self.on_list_wheel))
        self.list_canvas.bind("<Leave>", lambda e: self.list_canvas.unbind_all("<MouseWheel>"))
        self.lbl_total = ttk.Label(f, text="No photos yet", font=(branding.FONT, 10, "bold"))
        self.lbl_total.grid(row=4, column=0, sticky="w", pady=(6, 0))

    def on_list_wheel(self, e):
        self.list_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    # ---- adding ---------------------------------------------------------------------------------
    def on_drop(self, event):
        self.add_paths(list(self.root.tk.splitlist(event.data)))

    def add_files(self):
        fs = filedialog.askopenfilenames(title="Choose photos",
                                         filetypes=[("Photos", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff")])
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
        copies = max(1, int(self.g("default_copies")))
        new = [Photo(p, copies) for p in found if p not in have]
        if not new:
            messagebox.showinfo("No new photos", "No new JPG / PNG photos were found.")
            return
        self.push_history()
        self.photos += new
        self.show_workspace()
        self.refresh_list()
        self.select(new[0])
        self.touch()
        self.update_info()
        self.mark_dirty()
        self.queue_prepare()

    def queue_prepare(self):
        todo = [p for p in self.photos if p.state == "new"]
        if todo:
            for p in todo:
                p.state = "queued"
                self.update_row(p)
            self.enqueue(worker.Job("prepare", todo, self.params()))

    def on_remove_toggle(self):
        """Background removal switched on/off: instant when the mask exists, otherwise process once."""
        remove = self.g("remove_bg")
        for p in self.photos:
            if p.state in ("ready", "error") and imaging.needs_processing(p, remove):
                p.state = "new"
        self.refresh_list()
        self.queue_prepare()

    # ---- editing the list -----------------------------------------------------------------------
    def clear_all(self):
        if self.photos and messagebox.askyesno("Clear all", "Remove all photos from the list?"):
            self.cancel_job(silent=True)
            self.push_history()
            self.photos, self.sel, self.project_path = [], None, None
            self.refresh_list()
            self.pages, self.pages_ok = [], False
            self.draw_preview()
            self.load_editor()
            self.update_info()
            self.mark_dirty()

    def remove(self, p):
        self.push_history()
        self.photos.remove(p)
        if self.sel is p:
            self.sel = self.photos[0] if self.photos else None
        self.refresh_list()
        self.load_editor()
        self.touch()
        self.update_info()
        self.mark_dirty()

    def remove_selected(self):
        if self.sel is not None and self.sel in self.photos:
            self.remove(self.sel)

    def move(self, p, d):
        i = self.photos.index(p)
        j = i + d
        if 0 <= j < len(self.photos):
            self.push_history()
            self.photos[i], self.photos[j] = self.photos[j], self.photos[i]
            self.refresh_list()
            self.touch()
            self.mark_dirty()

    def duplicate_selected(self):
        p = self.sel
        if p is None or p not in self.photos:
            return
        self.push_history()
        d = p.duplicate()
        self.photos.insert(self.photos.index(p) + 1, d)
        self.refresh_list()
        self.select(d)
        self.touch()
        self.update_info()
        self.mark_dirty()
        self.queue_prepare()

    # ---- list drawing ---------------------------------------------------------------------------
    def status_text(self, p):
        if p.state == "ready":
            extra = self.text_summary(p)
            if not p.face_found:
                return ("Ready - face not found: adjust the crop by hand", "#b45309")
            return ("Ready" + ("  |  " + extra if extra else ""), "#15803d")
        return {"new": ("Not processed yet", "#666"), "queued": ("Waiting...", "#666"),
                "processing": ("Processing...", "#0067C5"), "error": ("Error: " + p.error[:70], "#b91c1c")}[p.state]

    def thumb(self, p):
        spec = self.spec()
        aspect = spec.photo_w / spec.photo_h
        box = (self.sc(44), self.sc(56))
        w = max(8, min(box[0], int(box[1] * aspect)))
        h = max(8, int(w / aspect))
        remove = self.g("remove_bg")
        key = (w, h, p.state, tuple(sorted(p.edit.items())), self.bg_rgb(), round(spec.head, 2), remove,
               p.mask is not None)
        if p.thumb_key != key or p.thumb_tk is None:
            if p.src is not None and p.state == "ready":
                im = imaging.render(p.layer(remove), p.geom(remove), p.edit, spec.head, self.bg_rgb(), w, h, ss=1)
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
        bgc = ROW_SEL if p is self.sel else ROW_BG
        row = tk.Frame(self.list_inner, bg=bgc, padx=6, pady=4)
        row.pack(fill="x", pady=1)
        th = tk.Label(row, image=self.thumb(p), bg=bgc, width=self.sc(46), height=self.sc(58))
        th.grid(row=0, column=0, rowspan=2, padx=(0, 8))
        nm = p.name if len(p.name) <= 15 else p.name[:12] + "..."
        name = tk.Label(row, text=nm, anchor="w", bg=bgc, font=(branding.FONT, 10, "bold"))
        name.grid(row=0, column=1, sticky="w")
        txt, col = self.status_text(p)
        st = tk.Label(row, text=txt, anchor="w", bg=bgc, fg=col, font=(branding.FONT, 8), wraplength=self.sc(150), justify="left")
        st.grid(row=1, column=1, sticky="w")
        row.columnconfigure(1, weight=1)
        var = tk.IntVar(value=p.copies)

        def changed(*_):
            try:
                n = max(0, min(999, int(var.get())))
            except (tk.TclError, ValueError):
                return
            if n != p.copies:
                self.push_history(("copies", id(p)))
                p.copies = n
                self.touch()
                self.update_info()
                self.update_total()
                self.mark_dirty()

        var.trace_add("write", changed)
        c = ttk.Frame(row)
        c.grid(row=0, column=2, rowspan=2, padx=4)
        ttk.Label(c, text="Copies").grid(row=0, column=0)
        sp = ttk.Spinbox(c, from_=1, to=99, width=4, textvariable=var)
        sp.grid(row=1, column=0)
        tip(sp, "How many prints of this photograph (use the arrows or type a number)")
        tip(ttk.Button(c, text="Edit text", command=lambda: self.edit_text(p)),
            "Name / date / custom text for THIS photograph only").grid(row=2, column=0, pady=(3, 0))
        bt = ttk.Frame(row)
        bt.grid(row=0, column=3, rowspan=2)
        ttk.Button(bt, text="\u25B2", width=2, command=lambda: self.move(p, -1)).grid(row=0, column=0)
        ttk.Button(bt, text="\u25BC", width=2, command=lambda: self.move(p, 1)).grid(row=1, column=0)
        ttk.Button(bt, text="\u2715", width=2, command=lambda: self.remove(p)).grid(row=0, column=1, rowspan=2, padx=2)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Duplicate", command=lambda: (self.select(p), self.duplicate_selected()))
        menu.add_command(label="Move up", command=lambda: self.move(p, -1))
        menu.add_command(label="Move down", command=lambda: self.move(p, 1))
        menu.add_separator()
        menu.add_command(label="Remove", command=lambda: self.remove(p))
        for w in (row, th, name, st):
            w.bind("<Button-1>", lambda e, p=p: self.select(p))
            w.bind("<Button-3>", lambda e, m=menu, p=p: (self.select(p), m.tk_popup(e.x_root, e.y_root)))
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
            c = ROW_SEL if q is p else ROW_BG
            for w in (row, th, st, name):
                w.config(bg=c)
        self.load_editor()
