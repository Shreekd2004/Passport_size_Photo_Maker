import os, sys, threading
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageOps, ImageTk
import passport_core as core


class App:
    def __init__(self, root):
        self.root = root
        root.title("Passport Photo Maker")
        root.geometry("520x680")
        self.files = []
        self.pages = []

        top = ttk.Frame(root, padding=10); top.pack(fill="x")
        ttk.Button(top, text="Add photos...", command=self.add).pack(side="left")
        ttk.Button(top, text="Clear", command=self.clear).pack(side="left", padx=6)
        self.lbl = ttk.Label(top, text="No photos selected"); self.lbl.pack(side="left", padx=10)

        opt = ttk.Frame(root, padding=10); opt.pack(fill="x")
        ttk.Label(opt, text="Copies:").pack(side="left")
        self.copies = tk.IntVar(value=5)
        ttk.Spinbox(opt, from_=1, to=50, width=5, textvariable=self.copies).pack(side="left", padx=6)
        self.border = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Border", variable=self.border).pack(side="left", padx=10)
        ttk.Label(opt, text="Format:").pack(side="left")
        self.fmt = tk.StringVar(value="PNG")
        ttk.Combobox(opt, textvariable=self.fmt, values=["PNG", "JPG"], width=6,
                     state="readonly").pack(side="left", padx=6)

        self.go = ttk.Button(root, text="Generate sheet", command=self.generate)
        self.go.pack(pady=6)
        self.status = ttk.Label(root, text=""); self.status.pack()
        self.preview = ttk.Label(root); self.preview.pack(pady=6, expand=True)
        self.save_btn = ttk.Button(root, text="Save...", command=self.save, state="disabled")
        self.save_btn.pack(pady=8)

    def add(self):
        fs = filedialog.askopenfilenames(
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp")])
        self.files += list(fs)
        self.lbl.config(text=f"{len(self.files)} photo(s) selected")

    def clear(self):
        self.files = []
        self.lbl.config(text="No photos selected")

    def generate(self):
        if not self.files:
            messagebox.showwarning("No photos", "Add at least one photo."); return
        self.go.config(state="disabled"); self.save_btn.config(state="disabled")
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            photos = []
            for i, f in enumerate(self.files, 1):
                self.root.after(0, lambda i=i: self.status.config(
                    text=f"Processing photo {i}/{len(self.files)}... (first run downloads model)"))
                img = ImageOps.exif_transpose(Image.open(f))
                photos.append(core.crop_passport(core.remove_bg(img)))
            self.pages = core.build_sheets(photos, int(self.copies.get()), self.border.get())
            self.root.after(0, self.done)
        except Exception as e:
            self.root.after(0, lambda: (messagebox.showerror("Error", str(e)),
                                        self.go.config(state="normal"),
                                        self.status.config(text="")))

    def done(self):
        thumb = self.pages[0].copy(); thumb.thumbnail((380, 500))
        self.tk_img = ImageTk.PhotoImage(thumb)
        self.preview.config(image=self.tk_img)
        n = len(self.pages)
        self.status.config(text=f"Done - {n} page(s)")
        self.go.config(state="normal"); self.save_btn.config(state="normal")

    def save(self):
        ext = ".png" if self.fmt.get() == "PNG" else ".jpg"
        path = filedialog.asksaveasfilename(defaultextension=ext,
                                            initialfile="passport_sheet" + ext,
                                            filetypes=[(self.fmt.get(), "*" + ext)])
        if not path: return
        base, e = os.path.splitext(path)
        for i, p in enumerate(self.pages, 1):
            out = path if len(self.pages) == 1 else f"{base}_{i}{e}"
            if ext == ".png": p.save(out, "PNG", dpi=(300, 300))
            else: p.save(out, "JPEG", quality=95, dpi=(300, 300))
        messagebox.showinfo("Saved", f"Saved {len(self.pages)} file(s).")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
