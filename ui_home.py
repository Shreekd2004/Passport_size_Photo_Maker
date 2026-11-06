"""Start screen (dashboard), About dialog and splash screen."""
import os
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

import branding
import settings

SHORTCUTS = [("Ctrl+O", "Add photos"), ("Ctrl+Shift+F", "Import folder"), ("Ctrl+G", "Generate sheet"),
             ("Ctrl+S", "Save sheet (output folder)"), ("Ctrl+P", "Print"), ("Ctrl+Z / Ctrl+Y", "Undo / Redo"),
             ("Ctrl+D", "Duplicate photo"), ("Delete", "Remove selected photo"), ("Ctrl+N", "Clear all"),
             ("Ctrl+Shift+S", "Save project"), ("Ctrl+Shift+O", "Open project"), ("Ctrl+1 / 2 / 3", "Editing / Layout / Preview"),
             ("Esc", "Cancel processing"), ("F1", "About & shortcuts")]


def make_splash(root):
    """Borderless splash with the logo, shown while the app loads."""
    sp = tk.Toplevel(root)
    sp.overrideredirect(True)
    sp.configure(bg=branding.BLUE)
    inner = tk.Frame(sp, bg="white")
    inner.pack(padx=2, pady=2)
    img = Image.open(branding.asset("splash.png")).convert("RGB").resize((400, 429), Image.LANCZOS)
    sp._img = ImageTk.PhotoImage(img)
    tk.Label(inner, image=sp._img, bg="white", bd=0).pack()
    sp.status = tk.Label(inner, text="Starting SnapMitra...", bg="white", fg=branding.MUTED, font=(branding.FONT, 10))
    sp.status.pack(pady=(0, 12))
    sp.update_idletasks()
    w, h = sp.winfo_reqwidth(), sp.winfo_reqheight()
    sp.geometry(f"+{(sp.winfo_screenwidth() - w) // 2}+{(sp.winfo_screenheight() - h) // 2}")
    sp.update()
    return sp


class HomeMixin:
    def build_home(self, parent):
        self.home = tk.Frame(parent, bg="white")
        self.home.grid(row=0, column=0, sticky="nsew")
        c = tk.Frame(self.home, bg="white")
        c.place(relx=0.5, rely=0.5, anchor="center")
        self._home_logo = branding.logo_tk(self.sc(210), transparent=False)
        tk.Label(c, image=self._home_logo, bg="white").pack(pady=(0, 4))
        tk.Label(c, text="What would you like to do?", bg="white", fg=branding.NAVY, font=(branding.FONT, 14, "bold")).pack(pady=(4, 10))
        row = tk.Frame(c, bg="white")
        row.pack()
        ttk.Button(row, text="  Add photos  ", style="Accent.TButton", command=self.add_files).pack(side="left", padx=5)
        ttk.Button(row, text="  Import folder  ", command=self.add_folder).pack(side="left", padx=5)
        ttk.Button(row, text="  Open project  ", command=self.open_project).pack(side="left", padx=5)
        self.btn_continue = ttk.Button(row, text="", command=self.continue_last_session)
        tk.Label(c, text="Photo size", bg="white", fg=branding.MUTED, font=(branding.FONT, 10)).pack(pady=(18, 4))
        self.quick_row = tk.Frame(c, bg="white")
        self.quick_row.pack()
        tk.Label(c, text="Recent projects", bg="white", fg=branding.MUTED, font=(branding.FONT, 10)).pack(pady=(16, 4))
        self.recent_list = tk.Listbox(c, height=4, width=62, bd=0, highlightthickness=1, highlightbackground="#D5DDE8",
                                      activestyle="none", font=(branding.FONT, 10), selectbackground="#D6E8FA", selectforeground="black")
        self.recent_list.pack()
        self.recent_list.bind("<Double-Button-1>", self.open_selected_recent)
        tk.Label(c, text="100% offline  \u2022  your customers' photos never leave this PC  \u2022  drag & drop photos anywhere",
                 bg="white", fg=branding.MUTED, font=(branding.FONT, 9)).pack(pady=(18, 0))

    def refresh_home(self):
        for w in self.quick_row.winfo_children():
            w.destroy()
        names = []
        for n in ["Indian Passport", "Stamp Size", "US Passport"] + self.store.top_presets(3):
            if n in self.preset_by_name and n not in names:
                names.append(n)
        names = names[:5] + ["Custom"]
        for n in names:
            ttk.Button(self.quick_row, text=n, command=lambda n=n: self.quick_size(n)).pack(side="left", padx=4)
        self.recent_list.delete(0, "end")
        self._recent_paths = list(self.store.recent)
        for p in self._recent_paths:
            self.recent_list.insert("end", f"{os.path.basename(p)}    \u2013    {os.path.dirname(p)}")
        if not self._recent_paths:
            self.recent_list.insert("end", "(no projects yet - use Save project in the header)")
        d = settings.read_autosave()
        self.btn_continue.pack_forget()
        if d:
            self.btn_continue.config(text=f"  Continue last session ({len(d['photos'])} photos)  ")
            self.btn_continue.pack(side="left", padx=5)

    def open_selected_recent(self, _=None):
        sel = self.recent_list.curselection()
        if sel and sel[0] < len(self._recent_paths):
            self.open_project(self._recent_paths[sel[0]])

    def quick_size(self, name):
        self.set_preset(name)
        self.show_workspace()
        self.nb.select(self.tab_layout if name == "Custom" else self.tab_edit)

    def show_home(self):
        self.refresh_home()
        self.home.tkraise()

    def show_workspace(self):
        self.workspace.tkraise()

    def show_about(self):
        d = tk.Toplevel(self.root)
        d.title("About SnapMitra")
        d.transient(self.root)
        d.configure(bg="white")
        d.resizable(False, False)
        f = tk.Frame(d, bg="white", padx=24, pady=18)
        f.pack()
        d._logo = branding.logo_tk(self.sc(170), transparent=False)
        tk.Label(f, image=d._logo, bg="white").grid(row=0, column=0, rowspan=3, padx=(0, 22), sticky="n")
        tk.Label(f, text=f"{branding.APP_NAME}  {branding.VERSION}", bg="white", fg=branding.NAVY, font=(branding.FONT, 16, "bold")).grid(row=0, column=1, sticky="w")
        tk.Label(f, text=branding.TAGLINE, bg="white", fg=branding.ORANGE, font=(branding.FONT, 11, "italic")).grid(row=1, column=1, sticky="w")
        tk.Label(f, bg="white", fg=branding.MUTED, justify="left", font=(branding.FONT, 9), text=(
            "Passport, stamp, visa and ID photo sheets - made fast.\n\n"
            "PRIVACY: all processing happens on this computer. Photos are never uploaded; no account is needed.\n"
            "The AI models are bundled with the app, so it works fully offline.\n\n"
            "Open-source components: U2-Net background model (Apache-2.0), Ultra-Light-Fast-Generic-Face-Detector (MIT), "
            "ONNX Runtime (MIT), Pillow, NumPy, DejaVu fonts.")).grid(row=2, column=1, sticky="nw", pady=(8, 0))
        sc = tk.Frame(f, bg="white")
        sc.grid(row=3, column=0, columnspan=2, sticky="w", pady=(14, 0))
        tk.Label(sc, text="Keyboard shortcuts", bg="white", fg=branding.NAVY, font=(branding.FONT, 10, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")
        for i, (k, v) in enumerate(SHORTCUTS):
            r, cc = divmod(i, 2)
            tk.Label(sc, text=k, bg="white", fg=branding.BLUE, font=(branding.FONT, 9, "bold"), width=15, anchor="w").grid(row=r + 1, column=cc * 2, sticky="w")
            tk.Label(sc, text=v, bg="white", fg=branding.MUTED, font=(branding.FONT, 9), width=26, anchor="w").grid(row=r + 1, column=cc * 2 + 1, sticky="w")
        tk.Label(f, text=f"Log file: {os.path.join(os.environ.get('LOCALAPPDATA', '~'), 'SnapMitra', 'log.txt')}", bg="white",
                 fg=branding.MUTED, font=(branding.FONT, 8)).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(f, text="Close", style="Accent.TButton", command=d.destroy).grid(row=5, column=1, sticky="e", pady=(10, 0))
        d.update_idletasks()
        d.geometry(f"+{self.root.winfo_rootx() + 120}+{self.root.winfo_rooty() + 60}")
