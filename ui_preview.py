"""SECTION 4 - PREVIEW & EXPORT: sheet preview, page navigation, PNG / JPG / PDF, print, output folder."""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

import branding
import layout
import printing
import worker
from ui_widgets import tip


class PreviewMixin:
    def build_preview(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="   4   Preview & Export   ")
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)
        top = ttk.Frame(f)
        top.grid(row=0, column=0, sticky="ew")
        gb = tk.Button(top, text="  Generate sheet  ", command=self.generate, bg=branding.ORANGE, fg="white",
                       activebackground="#D95900", activeforeground="white", relief="flat", bd=0, padx=10, pady=7,
                       font=(branding.FONT, 11, "bold"), cursor="hand2")
        gb.pack(side="left")
        tip(gb, "Process the photos (if needed) and build the print sheet (Ctrl+G)")
        ttk.Button(top, text="<", width=3, command=lambda: self.flip(-1)).pack(side="left", padx=(16, 2))
        self.lbl_page = ttk.Label(top, text="No sheet yet", width=16, anchor="center")
        self.lbl_page.pack(side="left")
        ttk.Button(top, text=">", width=3, command=lambda: self.flip(1)).pack(side="left", padx=2)
        self.lbl_stale = ttk.Label(top, text="", foreground="#b45309")
        self.lbl_stale.pack(side="left", padx=12)
        self.pv_canvas = tk.Canvas(f, bg="#E8EEF6", highlightthickness=0)
        self.pv_canvas.grid(row=1, column=0, sticky="nsew", pady=8)
        self.pv_canvas.bind("<Configure>", lambda e: self.draw_preview())
        out = ttk.Frame(f)
        out.grid(row=2, column=0, sticky="ew")
        ttk.Label(out, text="Output folder").pack(side="left")
        ttk.Entry(out, textvariable=self.V["output_dir"], width=42).pack(side="left", padx=6)
        ttk.Button(out, text="Browse...", command=self.choose_output_dir).pack(side="left")
        ttk.Button(out, text="Open folder", command=lambda: self.open_folder(self.g("output_dir"))).pack(side="left", padx=6)
        bot = ttk.Frame(f)
        bot.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(bot, text="Format").pack(side="left")
        ttk.Combobox(bot, textvariable=self.V["fmt"], values=["PDF", "PNG", "JPG"], state="readonly", width=6).pack(side="left", padx=6)
        tip(ttk.Button(bot, text="Save", style="Accent.TButton", command=self.save_sheet),
            "Save into the output folder with an automatic name (Ctrl+S). PDF keeps the exact paper size.").pack(side="left")
        tip(ttk.Button(bot, text="Save as...", command=self.save_sheet_as), "Choose the file name and folder").pack(side="left", padx=6)
        tip(ttk.Button(bot, text="Print...", command=self.print_sheet), "Print on an installed printer at actual size (Ctrl+P)").pack(side="left")
        ttk.Label(bot, text="300 DPI - print at 100% / actual size", foreground=branding.MUTED).pack(side="left", padx=14)
        return f

    def choose_output_dir(self):
        d = filedialog.askdirectory(title="Choose the output folder", initialdir=self.g("output_dir") or None)
        if d:
            self.V["output_dir"].set(d)

    def open_folder(self, d):
        try:
            os.makedirs(d, exist_ok=True)
            if hasattr(os, "startfile"):
                os.startfile(d)
            else:
                subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", d])
        except Exception:
            pass

    # ---- preview ---------------------------------------------------------------------------------
    def flip(self, d):
        if self.pages:
            self.page_idx = (self.page_idx + d) % len(self.pages)
            self.draw_preview()

    def draw_preview(self):
        c = self.pv_canvas
        c.delete("all")
        W, H = max(80, c.winfo_width()), max(80, c.winfo_height())
        if not self.pages:
            self.lbl_page.config(text="No sheet yet")
            c.create_text(W // 2, H // 2, text="Click  Generate sheet  to preview the print layout",
                          fill="#6B7C93", font=(branding.FONT, 12))
            return
        pg = self.pages[self.page_idx]
        s = min((W - 24) / pg.width, (H - 24) / pg.height)
        im = pg.resize((max(1, int(pg.width * s)), max(1, int(pg.height * s))), Image.LANCZOS)
        self.pv_tk = ImageTk.PhotoImage(im)
        x, y = W // 2, H // 2
        c.create_rectangle(x - im.width // 2 + 4, y - im.height // 2 + 4, x + im.width // 2 + 4, y + im.height // 2 + 4,
                           fill="#C9D3E0", outline="")                                    # soft paper shadow
        c.create_image(x, y, image=self.pv_tk)
        self.lbl_page.config(text=f"Sheet {self.page_idx + 1} of {len(self.pages)}")

    # ---- actions ---------------------------------------------------------------------------------
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
        """Quick save: into the output folder with a clear automatic file name."""
        if not self.ready_check():
            return
        d = self.g("output_dir")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Save", f"Cannot use the output folder:\n{d}\n\n{e}")
            return
        path = os.path.join(d, layout.default_basename(self.spec()))
        self.enqueue(worker.Job("sheet", list(self.photos), self.params(save=(path, self.g("fmt")))))

    def save_sheet_as(self):
        if not self.ready_check():
            return
        fmt = self.g("fmt")
        ext = {"PNG": ".png", "JPG": ".jpg", "PDF": ".pdf"}[fmt]
        d = self.g("output_dir")
        path = filedialog.asksaveasfilename(
            defaultextension=ext, initialdir=d if os.path.isdir(d) else None,
            initialfile=layout.default_basename(self.spec()) + ext, filetypes=[(fmt, "*" + ext)])
        if path:
            self.enqueue(worker.Job("sheet", list(self.photos), self.params(save=(path, fmt))))

    def after_saved(self, files):
        folder = os.path.dirname(files[0])
        names = "\n".join(os.path.basename(f) for f in files)
        if messagebox.askyesno("Saved", f"Saved {len(files)} file(s) to:\n{folder}\n\n{names}\n\nOpen the folder?"):
            self.open_folder(folder)

    def print_sheet(self):
        if not self.ready_check():
            return
        try:
            names, default = printing.list_printers()
        except Exception as e:
            messagebox.showerror("Printing", f"Could not list printers: {e}")
            return
        if not names:
            messagebox.showinfo("Printing", "No printer found (direct printing works on Windows with an installed printer).\n"
                                            "Tip: save as PDF and print that.")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Print")
        dlg.transient(self.root)
        dlg.grab_set()
        f = ttk.Frame(dlg, padding=16)
        f.pack()
        ttk.Label(f, text="Printer").grid(row=0, column=0, sticky="w")
        v = tk.StringVar(value=default or names[0])
        ttk.Combobox(f, textvariable=v, values=names, state="readonly", width=40).grid(row=1, column=0, columnspan=2, pady=6)
        ttk.Label(f, text="Copies of the whole sheet").grid(row=2, column=0, sticky="w")
        nc = tk.IntVar(value=1)
        ttk.Spinbox(f, from_=1, to=50, width=5, textvariable=nc).grid(row=2, column=1, sticky="e")
        ttk.Label(f, text="Prints at 100% (actual size) - load the paper size you chose in Layout.",
                  foreground=branding.MUTED).grid(row=3, column=0, columnspan=2, pady=(8, 0))

        def go():
            dlg.destroy()
            try:
                copies = max(1, int(nc.get()))
            except (tk.TclError, ValueError):
                copies = 1
            self.enqueue(worker.Job("sheet", list(self.photos), self.params(printer=v.get(), sheet_copies=copies)))

        b = ttk.Frame(f)
        b.grid(row=4, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(b, text="Print", style="Accent.TButton", command=go).pack(side="left")
        ttk.Button(b, text="Cancel", command=dlg.destroy).pack(side="left", padx=6)
