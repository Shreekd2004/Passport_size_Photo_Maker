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

log = logging.getLogger("snapmitra")
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
    remove, spec, style = P["remove"], P["spec"], P["style"]

    if job.kind == "warmup":
        prog(0, "Loading AI model", "")

        def dl(d, t):
            prog(100.0 * d / max(1, t) * 0.9, "Downloading AI model (one time only)", f"{d / 1e6:.0f} / {t / 1e6:.0f} MB")

        model.get_session(dl, job.cancel)
        model.get_face()
        prog(100, "AI model ready", "")
        return

    todo = [p for p in job.photos if imaging.needs_processing(p, remove)]
    n = len(todo)
    need_ai = remove and any(p.mask is None for p in todo)
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
            if p.src is None:
                at(0, "Reading photo", det)
                p.src = imaging.load_image(p.path)
                p.mask, p.face_checked, p.face_rect = None, False, None
            check()
            if remove and p.mask is None:
                at(5, "Removing background", det)
                p.mask = session.predict(p.src)
            check()
            if not p.face_checked:
                at(55, "Detecting face", det)
                p.face_rect = imaging.detect_face(p.src)
                p.face_checked = True
            check()
            p.reset_derived()
            imaging.final_cell(p, spec, style, lambda stage: at(
                {"Cropping photograph": 63, "Applying text overlay": 70, "Preparing final image": 75}[stage], stage, det))
            p.state, p.error = "ready", ""
            log.info("processed %s in %.2fs (face=%s)", p.name, time.time() - t0, p.face_found)
        except (Cancelled, ModelError):
            p.state = "new"
            raise
        except Exception as e:  # noqa - one bad file must not stop the others
            log.exception("photo failed: %s", p.path)
            p.state, p.error, p.src, p.mask = "error", f"{type(e).__name__}: {e}", None, None
        put("photo", job.id, p)
        base[0] += W_PHOTO

    if job.kind != "sheet":
        prog(100, "Done", "")
        return

    ready = [p for p in job.photos if p.state == "ready" and p.src is not None]
    if not ready:
        raise layout.LayoutError("No photo is ready. Check the error shown next to each photo.")
    check()
    at(0, "Generating sheet", f"{sum(p.copies for p in ready)} photos")
    items = [(*imaging.final_cell(p, spec, style), p.copies) for p in ready]
    check()
    at(8, "Generating sheet", "placing photos")
    job.result = layout.build_pages(spec, items)
    check()
    at(14, "Finalising output", "")
    if P.get("save"):
        path, fmt = P["save"]
        job.saved = layout.save_pages(job.result, path, fmt)
    if P.get("printer"):
        at(17, "Sending to printer", P["printer"])
        printing.print_pages(job.result, P["printer"], copies=int(P.get("sheet_copies", 1)))
        job.printed = True
    prog(100, "Done", "")
