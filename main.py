import logging
import os
import sys

# windowed (no-console) builds have no stdout/stderr; libraries that print would crash
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import model

LOG = model.app_data_dir() / "log.txt"
logging.basicConfig(filename=str(LOG), level=logging.INFO, filemode="a",
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("snapmitra")


def selftest(img_path, out_dir):
    """Headless end-to-end check used by the build pipeline: AI + face + text + guides + stamp size + PNG/JPG/PDF."""
    import queue
    import imaging
    import layout
    import textoverlay
    import worker

    os.makedirs(out_dir, exist_ok=True)
    photos = [imaging.Photo(img_path, 4, "Customer One"), imaging.Photo(img_path, 1, "Customer Two"),
              imaging.Photo(img_path, 8, "Customer Three")]
    ts = textoverlay.TextStyle(enabled=True, source="name", use_date=True, two_lines=True, position="below", size_pt=7)
    spec = layout.LayoutSpec(photo_w=25, photo_h=25, head=0.62, guides="dotted", caption_mm=textoverlay.caption_mm(ts))
    ok = True
    for fmt in ("PNG", "JPG", "PDF"):
        job = worker.Job("sheet", photos, dict(remove=True, spec=spec, style=imaging.Style((255, 255, 255), True, ts),
                                               save=(os.path.join(out_dir, "selftest"), fmt)))
        q = queue.Queue()
        worker.run_job(job, q)
        last = None
        while not q.empty():
            last = q.get()
        good = last is not None and last[0] == "done" and job.saved and all(os.path.exists(f) for f in job.saved)
        log.info("SELFTEST %s %s", fmt, "PASS" if good else f"FAIL {last}")
        ok = ok and bool(good)
    log.info("SELFTEST %s", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2], sys.argv[3]))
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SnapMitra.PhotoStudio")  # taskbar icon
        except Exception:
            pass
    import tkinter as tk
    from tkinter import messagebox
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    root.withdraw()
    try:
        import sv_ttk
        sv_ttk.set_theme("light")
    except Exception:
        pass
    import branding
    branding.set_window_icon(root)
    from ui_home import make_splash
    splash = make_splash(root)                       # logo splash while the rest loads
    import time
    t0 = time.time()
    from app import App

    def on_err(exc, val, tb):
        log.error("UI error", exc_info=(exc, val, tb))
        messagebox.showerror("Unexpected error", f"{exc.__name__}: {val}\n\nDetails: {LOG}")

    root.report_callback_exception = on_err
    app = App(root)
    while time.time() - t0 < 1.2:                    # show the splash for at least a moment
        root.update()
        time.sleep(0.02)
    splash.destroy()
    root.deiconify()
    root.lift()
    root.mainloop()


if __name__ == "__main__":
    main()
