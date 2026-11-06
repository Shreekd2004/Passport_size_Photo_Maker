"""Small reusable Tk widgets: scrollable frame, tooltips, colour chip."""
import tkinter as tk
from tkinter import ttk

import branding


class ScrollFrame(ttk.Frame):
    """Vertical scrolling container. Put children in `.body`."""

    def __init__(self, parent, bg="#fafafa"):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=bg)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.body = ttk.Frame(self.canvas)
        self.win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")


class Tooltip:
    def __init__(self, widget, text):
        self.w, self.text, self.tw, self.job = widget, text, None, None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _):
        self.job = self.w.after(550, self._show)

    def _show(self):
        if self.tw:
            return
        x, y = self.w.winfo_rootx() + 12, self.w.winfo_rooty() + self.w.winfo_height() + 6
        self.tw = tk.Toplevel(self.w)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=self.text, bg=branding.NAVY, fg="white", padx=8, pady=4,
                 font=(branding.FONT, 9), justify="left", wraplength=320).pack()

    def _leave(self, _=None):
        if self.job:
            self.w.after_cancel(self.job)
            self.job = None
        if self.tw:
            self.tw.destroy()
            self.tw = None


def tip(widget, text):
    Tooltip(widget, text)
    return widget


def chip(parent, color, command=None, size=3):
    """Small coloured square (a colour swatch / picker button)."""
    b = tk.Button(parent, width=size, relief="solid", bd=1, bg=color, activebackground=color,
                  command=command, cursor="hand2" if command else "arrow")
    return b
