"""Background worker. Runs OFF the GUI thread and talks to the UI only through a queue.

Messages put on the queue:
  ("progress", job_id, percent, stage, detail)
  ("photo",    job_id, photo)            a photo finished (or failed)
  ("done",     job_id)
  ("cancelled", job_id)
  ("error",    job_id, kind, text)       kind = model | layout | other
"""
import itertools
import logging
import threading
import time

import imaging
import layout
import model
import printing
from model import Cancelled, ModelError

log = logging.getLogger("ppm")
_ids = itertools.count(1)


class Job:
    def __init__(self, kind, photos=None, params=None):
        self.id = next(_ids)
        self.kind = kind            # warmup | prepare | sheet
        self.photos = photos or []
        self.params = params or {}
        self.cancel = threading.Event()
        self.result = None          # list of page images for kind == "sheet"
        self.saved = []             # files written
        self.printed = False

    def clone(self):
        return Job(self.kind, self.photos, self.params)


def run_job(job, q):
    def put(*a):
        q.put(a)

    def prog(pct, stage, detail=""):
        put("progress", job.id, max(0.0, min(100.0, pct)), stage, detail)

    def check():
        if job.cancel.is_set():
            raise Cancelled()

    try:
        _run(job, prog, check, put)
        put("done", job.id)
    except Cancelled:
        put("cancelled", job.id)
    except ModelError as e:
        put("error", job.id, "model", str(e))
    except layout.LayoutError as e:
        put("error", job.id, "layout", str(e))
    except Exception as e:  # noqa
        log.exception("job failed")
        put("error", job.id, "other", f"{type(e).__name__}: {e}")


def _run(job, prog, check, put):
    P = job.params
    mode, spec, bg = P["mode"], P["spec"], P["bg"]

    if job.kind == "warmup":
        prog(0, "Loading AI model", "")

        def dl(d, t):
            prog(100.0 * d / max(1, t) * 0.9, "Downloading AI model (one time only)", f"{d / 1e6:.0f} / {t / 1e6:.0f} MB")

        model.get_session(dl, job.cancel)
        prog(100, "AI model ready", "")
        return

    todo = [p for p in job.photos if imaging.needs_processing(p, mode)]
    n = len(todo)
    need_ai = mode == "ai" and n > 0
    W_LOAD = 10.0 if need_ai else 0.0
    W_PHOTO = 80.0
    W_SHEET = 20.0 if job.kind == "sheet" else 0.0
    total = W_LOAD + n * W_PHOTO + W_SHEET or 1.0
    base = [0.0]

    def at(units_, stage, detail=""):
        prog(100.0 * (base[0] + units_) / total, stage, detail)

    session = None
    if need_ai:
        def dl(d, t):
            frac = d / max(1, t)
            at(W_LOAD * 0.8 * frac, "Downloading AI model (one time only)", f"{d / 1e6:.0f} / {t / 1e6:.0f} MB")

        at(0, "Loading AI model", "")
        session = model.get_session(dl, job.cancel)
        base[0] += W_LOAD

    for i, p in enumerate(todo, 1):
        check()
        det = f"Photo {i} of {n}  -  {p.name}"
        p.state = "processing"
        t0 = time.time()
        try:
            at(0, "Reading photo", det)
            img = imaging.load_image(p.path)
            check()
            at(5, "Removing background" if mode == "ai" else "Preparing photo", det)
            rgba = imaging.remove_background(img, session) if mode == "ai" else img.convert("RGBA")
            check()
            at(55, "Detecting face", det)
            face = imaging.detect_face(img)
            check()
            at(63, "Cropping photograph", det)
            p.face = imaging.analyse(rgba, face, mode == "ai")
            p.cutout, p.mode = rgba, mode
            at(68, "Preparing passport-size image", det)
            imaging.final_image(p, spec, bg)
            p.state, p.error = "ready", ""
            log.info("processed %s in %.2fs (face=%s)", p.name, time.time() - t0, p.face["found"])
        except Cancelled:
            p.state = "new"
            raise
        except ModelError:
            p.state = "new"
            raise
        except Exception as e:  # noqa - one bad file must not stop the others
            log.exception("photo failed: %s", p.path)
            p.state, p.error, p.cutout = "error", f"{type(e).__name__}: {e}", None
        put("photo", job.id, p)
        base[0] += W_PHOTO

    if job.kind != "sheet":
        prog(100, "Done", "")
        return

    ready = [p for p in job.photos if p.state == "ready" and p.cutout is not None]
    if not ready:
        raise layout.LayoutError("No photo is ready. Check the error shown next to each photo.")
    check()
    at(0, f"Generating {spec.paper_name} sheet", f"{sum(p.copies for p in ready)} photos")
    items = [(imaging.final_image(p, spec, bg), p.copies) for p in ready]
    check()
    at(8, f"Generating {spec.paper_name} sheet", "placing photos")
    job.result = layout.build_pages(spec, items)
    check()
    at(14, "Finalising output", "")
    if P.get("save"):
        path, fmt = P["save"]
        job.saved = layout.save_pages(job.result, path, fmt)
    if P.get("printer"):
        at(17, "Sending to printer", P["printer"])
        printing.print_pages(job.result, P["printer"])
        job.printed = True
    prog(100, "Done", "")
