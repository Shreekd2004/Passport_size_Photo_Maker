"""SnapMitra main window - composition root.

All heavy work runs in worker.py on a background thread; the UI only draws widgets and reacts to queue messages,
so the window never freezes. The four sections live in mixins: ui_photos / ui_editing / ui_layout / ui_preview,
plus ui_home (dashboard, about, splash).
"""
import copy
import logging
import os
import queue
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

import branding
import imaging
import layout
import model
import presets
import settings
import textoverlay
import units
import worker
from imaging import Photo
from ui_editing import EditingMixin
from ui_home import HomeMixin
from ui_layout import LayoutMixin
from ui_photos import PhotosMixin
from ui_preview import PreviewMixin
from ui_widgets import tip

log = logging.getLogger("snapmitra")
ORIENT = {"Auto": "auto", "Portrait": "portrait", "Landscape": "landscape"}
TEXT_ENTRY_CLASSES = ("Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox", "Text")


class App(HomeMixin, PhotosMixin, EditingMixin, LayoutMixin, PreviewMixin):
    def __init__(self, root):
        self.root = root
        root.title(branding.WINDOW_TITLE)
        branding.set_window_icon(root)
        self.S = max(1.0, root.winfo_fpixels("1i") / 96.0)
        root.geometry(f"{self.sc(1400)}x{self.sc(860)}")
        root.minsize(self.sc(1120), self.sc(720))

        self.store = settings.Store()
        self.presets = presets.load_photo_presets()
        self.preset_by_name = {p["name"]: p for p in self.presets}
        self.photos, self.sel, self.rows = [], None, {}
        self.q, self.jobs, self.active = queue.Queue(), deque(), None
        self.job_t0 = self.last_prog = 0.0
        self.pages, self.pages_ok, self.page_idx = [], False, 0
        self.lock_traces = self.loading_editor = False
        self.undo_stack, self.redo_stack = [], []
        self._hk, self._ht = None, 0.0
        self._as_job = self._redraw_job = None
        self.project_path = None
        self.make_vars()
        self.build_ui()
        self.finish_init()

    # ------------------------------------------------------------------ settings <-> variables
    def sc(self, v):
        return int(v * getattr(self, "S", 1.0))

    def make_vars(self):
        self.V = {}
        for k, d in settings.DEFAULTS.items():
            cls = (tk.BooleanVar if isinstance(d, bool) else tk.IntVar if isinstance(d, int)
                   else tk.DoubleVar if isinstance(d, float) else tk.StringVar)
            self.V[k] = cls(value=self.store.cfg.get(k, d))
        if self.V["photo_preset"].get() not in self.preset_by_name:
            self.V["photo_preset"].set("Indian Passport")
        self._unit_prev = self.V["unit"].get()
        self.v_label = tk.StringVar()          # customer name of the selected photo (text overlay)

    def g(self, key):
        try:
            return self.V[key].get()
        except (tk.TclError, ValueError):
            return settings.DEFAULTS[key]

    def collect_cfg(self):
        return {k: self.g(k) for k in settings.DEFAULTS}

    def bg_rgb(self):
        c = self.g("bg_choice")
        return settings.BG_COLORS.get(c) or settings.hex_to_rgb(self.g("bg_custom"))

    def text_style(self):
        """GLOBAL text settings (the ones in Editing > Text overlay)."""
        g = self.g
        src = g("t_source")
        return textoverlay.TextStyle(
            enabled=g("t_enabled"), use_name=(src == "name"), use_custom=(src == "custom"), custom=g("t_custom"),
            use_date=g("t_date"), date_mode=g("t_date_mode"), date_text=g("t_date_text"), multiline=g("t_two"),
            font=g("t_font"), bold=g("t_bold"), size_pt=max(4.0, float(g("t_size"))), color=settings.hex_to_rgb(g("t_color")),
            align=g("t_align"), position=g("t_pos"), area_mm=float(g("t_area")), voff_mm=float(g("t_voff")),
            bg_on=g("t_bg_on"), bg_color=settings.hex_to_rgb(g("t_bg_color")))

    def img_style(self):
        return imaging.Style(self.bg_rgb(), self.g("remove_bg"), self.text_style(), self.g("t_mode"))

    def caption_needed(self):
        """OUTSIDE-mode strip height: the tallest one any photo needs, so every cell on the sheet is the same height."""
        style = self.img_style()
        caps = [textoverlay.caption_mm(style.text_for(p)) for p in self.photos] or [textoverlay.caption_mm(style.text)]
        return max(caps)

    def default_individual_ts(self, photo):
        """Starting point for a photo's own text: the global look + this customer's name."""
        return replace(self.text_style(), enabled=True, use_name=True, name=photo.label, use_custom=False, custom="",
                       use_dob=False, use_cdate=False)

    def text_summary(self, p):
        if self.g("t_mode") != "individual":
            return ""
        if p.text_mode == "none":
            return "Text: off"
        if p.text_mode == "custom" and p.ptext is not None:
            t = textoverlay.resolve_text(p.ptext, p.label).replace("\n", " / ")
            return "Text: " + (t if len(t) <= 22 else t[:19] + "...")
        return "Text: global"

    def edit_text(self, p):
        from ui_textdialog import TextDialog
        self.select(p)
        TextDialog(self, p)

    def after_text_change(self):
        for p in self.photos:
            p.thumb_key = None
        self.touch()
        self.update_info()
        self.refresh_thumbs()
        self.redraw_editor()
        self.mark_dirty()

    def spec(self):
        g, unit = self.g, self.g("unit")
        return layout.LayoutSpec(
            photo_w=max(5.0, units.to_mm(g("pw"), unit)), photo_h=max(5.0, units.to_mm(g("ph"), unit)),
            head=min(0.95, max(0.2, g("head") / 100.0)), caption_mm=self.caption_needed(),
            paper_name=g("paper"), paper_w=max(20.0, g("paper_w")), paper_h=max(20.0, g("paper_h")),
            orientation=ORIENT.get(g("orient"), "auto"), margin=max(0.0, g("margin")),
            hgap=max(0.0, g("hgap")), vgap=max(0.0, g("vgap")), border=g("border"), border_px=int(g("border_px")),
            guides=g("cut_guides"), mode=g("layout_mode"))

    def params(self, **extra):
        d = dict(remove=self.g("remove_bg"), spec=self.spec(), style=self.img_style())
        d.update(extra)
        return d

    # ------------------------------------------------------------------ UI skeleton
    def build_ui(self):
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(1, weight=1)
        self.build_header()
        self.content = ttk.Frame(r)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self.workspace = ttk.Frame(self.content, padding=8)
        self.workspace.grid(row=0, column=0, sticky="nsew")
        self.workspace.columnconfigure(1, weight=1)
        self.workspace.rowconfigure(0, weight=1)
        self.build_photos(self.workspace)
        self.nb = ttk.Notebook(self.workspace)
        self.nb.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.tab_edit = self.build_editing()
        self.tab_layout = self.build_layout()
        self.tab_preview = self.build_preview()
        self.build_home(self.content)
        self.build_status(r)

    def build_header(self):
        h = tk.Frame(self.root, bg=branding.NAVY)
        h.grid(row=0, column=0, sticky="ew")
        self._hdr_logo = branding.logo_tk(self.sc(46))
        tk.Label(h, image=self._hdr_logo, bg=branding.NAVY).pack(side="left", padx=(12, 8), pady=6)
        box = tk.Frame(h, bg=branding.NAVY)
        box.pack(side="left")
        row = tk.Frame(box, bg=branding.NAVY)
        row.pack(anchor="w")
        tk.Label(row, text="Snap", bg=branding.NAVY, fg="white", font=(branding.FONT, 17, "bold")).pack(side="left")
        tk.Label(row, text="Mitra", bg=branding.NAVY, fg=branding.ORANGE, font=(branding.FONT, 17, "bold")).pack(side="left")
        tk.Label(box, text=branding.TAGLINE, bg=branding.NAVY, fg="#9DB7DA", font=(branding.FONT, 9)).pack(anchor="w")
        right = tk.Frame(h, bg=branding.NAVY)
        right.pack(side="right", padx=8)

        def hb(text, cmd, tooltip):
            b = tk.Button(right, text=text, command=cmd, bg=branding.NAVY, fg="white", activebackground="#0B4A8F",
                          activeforeground="white", relief="flat", bd=0, highlightthickness=0, padx=11, pady=7, cursor="hand2",
                          font=(branding.FONT, 10))
            b.pack(side="left", padx=1)
            tip(b, tooltip)
            return b

        hb("Home", self.show_home, "Back to the start screen")
        hb("Undo", self.undo, "Undo the last change (Ctrl+Z)")
        hb("Redo", self.redo, "Redo (Ctrl+Y)")
        hb("Open project", self.open_project, "Open a saved SnapMitra project (Ctrl+Shift+O)")
        hb("Save project", self.save_project, "Save photos, copies and all settings (Ctrl+Shift+S)")
        hb("About", self.show_about, "About SnapMitra, shortcuts and privacy (F1)")
        tk.Frame(self.root, bg=branding.ORANGE, height=3).grid(row=0, column=0, sticky="sew")

    def build_status(self, parent):
        sb = ttk.Frame(parent, padding=(10, 6))
        sb.grid(row=2, column=0, sticky="ew")
        sb.columnconfigure(1, weight=1)
        self.lbl_stage = ttk.Label(sb, text="", font=(branding.FONT, 10, "bold"), width=34, anchor="w")
        self.lbl_stage.grid(row=0, column=0, sticky="w")
        self.pb = ttk.Progressbar(sb, maximum=100, mode="determinate")
        self.pb.grid(row=0, column=1, sticky="ew", padx=8)
        self.lbl_pct = ttk.Label(sb, text="", width=5, anchor="e")
        self.lbl_pct.grid(row=0, column=2)
        self.btn_cancel = ttk.Button(sb, text="Cancel processing", command=self.cancel_job, state="disabled")
        self.btn_cancel.grid(row=0, column=3, padx=(10, 0))
        tip(self.btn_cancel, "Stop the current processing (Esc). Nothing is lost.")
        self.lbl_detail = ttk.Label(sb, text="", foreground=branding.MUTED)
        self.lbl_detail.grid(row=1, column=0, columnspan=4, sticky="w")

    def finish_init(self):
        self.apply_cfg_side_effects(initial=True)
        for k in self.V:
            self.V[k].trace_add("write", lambda *a, k=k: self.on_setting(k))
        self.bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if os.environ.get("PPM_NO_DND") != "1":
            try:
                from tkinterdnd2 import DND_FILES
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind("<<Drop>>", self.on_drop)
            except Exception:
                log.info("drag & drop unavailable")
        self.refresh_home()
        self.show_home()
        self.idle_status()
        self.root.after(60, self.poll)
        self.enqueue(worker.Job("warmup", [], self.params()))   # load the AI model in the background right away

    # ------------------------------------------------------------------ keyboard shortcuts
    def bind_keys(self):
        def typing():
            w = self.root.focus_get()
            return w is not None and w.winfo_class() in TEXT_ENTRY_CLASSES

        def bk(seq, fn, guard=False):
            def h(e):
                if guard and typing():
                    return
                fn()
                return "break"
            self.root.bind(seq, h)
            if seq[-2] == "-" and seq[-1].isalpha():
                self.root.bind(seq[:-1] + seq[-1].swapcase(), h)

        bk("<Control-o>", self.add_files)
        bk("<Control-Shift-O>", self.open_project)
        bk("<Control-Shift-F>", self.add_folder)
        bk("<Control-g>", self.generate)
        bk("<Control-s>", self.save_sheet)
        bk("<Control-Shift-S>", self.save_project)
        bk("<Control-p>", self.print_sheet)
        bk("<Control-n>", self.clear_all)
        bk("<Control-z>", self.undo, guard=True)
        bk("<Control-y>", self.redo, guard=True)
        bk("<Control-d>", self.duplicate_selected, guard=True)
        bk("<Delete>", self.remove_selected, guard=True)
        bk("<Escape>", self.cancel_job)
        bk("<F1>", self.show_about)
        for i, sel in enumerate(("edit", "layout", "preview"), 1):
            bk(f"<Control-Key-{i}>", lambda s=sel: self.goto_tab(s))

    def goto_tab(self, which):
        self.show_workspace()
        self.nb.select({"edit": self.tab_edit, "layout": self.tab_layout, "preview": self.tab_preview}[which])

    # ------------------------------------------------------------------ reacting to setting changes
    IMAGE_KEYS = {"bg_choice", "bg_custom", "remove_bg", "head", "pw", "ph", "unit"}

    def on_setting(self, key):
        if self.lock_traces or key == "unit":
            return
        if key in ("pw", "ph", "head"):
            self.mark_custom_photo()
        if key in ("paper_w", "paper_h"):
            self.mark_custom_paper()
        if key in self.IMAGE_KEYS or key.startswith("t_"):
            for p in self.photos:
                p.thumb_key = None
        self.touch()
        self.update_info()
        self.refresh_thumbs()
        self.redraw_editor()
        self.mark_dirty()
        if key == "remove_bg":
            self.on_remove_toggle()
        if key == "photo_preset":
            self.store.bump_usage(self.g("photo_preset"))

    def apply_cfg_side_effects(self, initial=False):
        """Sync dependent widgets after settings were loaded / a project was opened."""
        self._unit_prev = self.g("unit")
        self.sync_preset_notes()
        self.update_info()
        if not initial:
            self.refresh_thumbs()
            self.redraw_editor()

    def touch(self):
        self.pages_ok = False
        if self.pages:
            self.lbl_stale.config(text="Settings changed - click Generate sheet to refresh")

    def redraw_editor(self):
        if self._redraw_job is None:
            self._redraw_job = self.root.after(30, self._do_redraw)

    def _do_redraw(self):
        self._redraw_job = None
        self.draw_editor()

    # ------------------------------------------------------------------ undo / redo
    def state(self):
        return [(p, p.copies, p.label, copy.deepcopy(p.edit), p.text_mode, copy.deepcopy(p.ptext)) for p in self.photos]

    def push_history(self, kind=None):
        """Snapshot BEFORE a change. Rapid repeats of the same kind (slider drags) collapse into one step."""
        now = time.time()
        if kind is not None and kind == self._hk and now - self._ht < 1.2:
            self._ht = now
            return
        self._hk, self._ht = kind, now
        self.undo_stack.append(self.state())
        del self.undo_stack[:-60]
        self.redo_stack.clear()

    def restore(self, st):
        self.photos = [r[0] for r in st]
        for p, c, label, edit, tmode, ptext in st:
            p.copies, p.label, p.edit = c, label, copy.deepcopy(edit)
            p.text_mode, p.ptext = tmode, copy.deepcopy(ptext)
            p.cache_key = p.thumb_key = None
        if self.sel not in self.photos:
            self.sel = self.photos[0] if self.photos else None
        self._hk = None
        self.refresh_list()
        self.load_editor()
        self.touch()
        self.update_info()
        self.mark_dirty()
        self.queue_prepare()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.state())
            self.restore(self.undo_stack.pop())
            self.lbl_detail.config(text="Undone.")

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.state())
            self.restore(self.redo_stack.pop())
            self.lbl_detail.config(text="Redone.")

    # ------------------------------------------------------------------ projects & auto-save
    def mark_dirty(self):
        if self._as_job is None:
            self._as_job = self.root.after(2500, self.autosave)

    def autosave(self):
        self._as_job = None
        try:
            settings.write_autosave(self.collect_cfg(), self.photos)
        except Exception:
            log.exception("autosave failed")

    def save_project(self):
        if not self.photos:
            messagebox.showinfo("Save project", "Add some photos first.")
            return
        path = self.project_path or filedialog.asksaveasfilename(
            title="Save SnapMitra project", defaultextension=".snapmitra", initialdir=self.g("output_dir")
            if os.path.isdir(self.g("output_dir")) else None, initialfile="my_photos.snapmitra",
            filetypes=[("SnapMitra project", "*.snapmitra")])
        if not path:
            return
        try:
            settings.write_project(path, self.collect_cfg(), self.photos)
        except OSError as e:
            messagebox.showerror("Save project", f"Could not save the project:\n{e}")
            return
        self.project_path = path
        self.store.add_recent(path)
        self.refresh_home()
        self.lbl_detail.config(text=f"Project saved: {path}")

    def open_project(self, path=None):
        path = path or filedialog.askopenfilename(title="Open SnapMitra project",
                                                  filetypes=[("SnapMitra project", "*.snapmitra"), ("All files", "*.*")])
        if not path:
            return
        try:
            d = settings.read_project(path)
        except Exception as e:
            messagebox.showerror("Open project", f"Could not open this project:\n{e}")
            return
        self.apply_project(d)
        self.project_path = path
        self.store.add_recent(path)
        self.refresh_home()

    def apply_project(self, d):
        self.cancel_job(silent=True)
        self.push_history()
        self.lock_traces = True
        for k, v in d.get("settings", {}).items():
            if k in self.V:
                try:
                    self.V[k].set(v)
                except tk.TclError:
                    pass
        self.lock_traces = False
        photos, missing = [], 0
        for r in d.get("photos", []):
            if not os.path.isfile(r.get("path", "")):
                missing += 1
                continue
            p = Photo(r["path"], int(r.get("copies", 5)), r.get("label"))
            p.edit.update({k: v for k, v in r.get("edit", {}).items() if k in p.edit})
            p.text_mode = r.get("text_mode", "global") if r.get("text_mode") in ("global", "custom", "none") else "global"
            if r.get("ptext"):
                p.ptext = textoverlay.TextStyle.from_dict(r["ptext"])
            photos.append(p)
        self.photos, self.sel = photos, (photos[0] if photos else None)
        self.pages, self.pages_ok = [], False
        self.apply_cfg_side_effects()
        self.refresh_list()
        self.load_editor()
        self.draw_preview()
        self.update_info()
        if photos:
            self.show_workspace()
        self.queue_prepare()
        if missing:
            messagebox.showwarning("Open project", f"{missing} photo file(s) could not be found and were skipped.")

    def continue_last_session(self):
        d = settings.read_autosave()
        if d:
            self.apply_project(d)

    # ------------------------------------------------------------------ background jobs
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
        self.lbl_stage.config(text="Ready" if ready or not self.g("remove_bg") else "AI model not loaded yet")
        self.lbl_detail.config(text="Everything runs on this PC - customer photos are never uploaded.")
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
            base = self.lbl_detail.cget("text").split("   [")[0]
            extra = "   (taking longer than usual - you can Cancel)" if time.time() - self.last_prog > 45 else ""
            self.lbl_detail.config(text=f"{base}   [{el:.0f}s]{extra}")
        self.root.after(100, self.poll)

    def handle(self, m):
        kind, jid = m[0], m[1]
        job = self.active
        if job is None or job.id != jid:
            return                                   # message from a cancelled job
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
            self.nb.select(self.tab_preview)
            if job.saved:
                self.after_saved(job.saved)
            elif job.printed:
                messagebox.showinfo("Printing", "The sheet was sent to the printer.\nIt prints at 100% (actual size).")
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

    def on_close(self):
        try:
            self.store.save(self.collect_cfg())
            self.autosave()
            if self.active:
                self.active.cancel.set()
            self.root.destroy()
        finally:
            logging.shutdown()
            os._exit(0)      # never hang or crash on exit because a worker thread is mid-inference
