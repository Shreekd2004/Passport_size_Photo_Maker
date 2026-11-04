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
log = logging.getLogger("ppm")


def selftest(img_path, out_path):
    """Headless end-to-end check used by the build pipeline: AI + face + sheet + save."""
    import queue
    import imaging
    import worker
    from layout import LayoutSpec

    photos = [imaging.Photo(img_path, 8), imaging.Photo(img_path, 12)]
    job = worker.Job("sheet", photos, dict(mode="ai", spec=LayoutSpec(), bg=(255, 255, 255), save=(out_path, "PNG")))
    q = queue.Queue()
    worker.run_job(job, q)
    last = None
    while not q.empty():
        last = q.get()
    ok = last is not None and last[0] == "done" and os.path.exists(out_path)
    log.info("SELFTEST %s", "PASS" if ok else f"FAIL {last}")
    return 0 if ok else 1


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2], sys.argv[3]))
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    import tkinter as tk
    from tkinter import messagebox
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    try:
        import sv_ttk
        sv_ttk.set_theme("light")
    except Exception:
        pass
    from app import App

    def on_err(exc, val, tb):
        log.error("UI error", exc_info=(exc, val, tb))
        messagebox.showerror("Unexpected error", f"{exc.__name__}: {val}\n\nDetails: {LOG}")

    root.report_callback_exception = on_err
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
