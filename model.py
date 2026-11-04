"""AI model management (offline-first).

Search order for u2net.onnx:
  1. bundled next to the app (installed builds ship the model -> no download ever)
  2. %LOCALAPPDATA%\\PassportPhotoMaker\\models (cached from an earlier download)
  3. one-time download with progress, timeout, MD5 check, and retry support.
The ONNX session is created ONCE and reused for every photo.
"""
import hashlib
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("ppm")

MODEL_FILE = "u2net.onnx"
MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
MODEL_MD5 = "60024c5c889badc19c04ad937298a77b"
MODEL_SIZE = 175997641


class Cancelled(Exception):
    pass


class ModelError(Exception):
    pass


def app_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    p = Path(base) / "PassportPhotoMaker"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_dir():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _candidate_dirs():
    yield resource_dir() / "models"
    if getattr(sys, "frozen", False):
        yield Path(sys.executable).parent / "models"
    yield app_data_dir() / "models"


def find_model():
    for d in _candidate_dirs():
        f = d / MODEL_FILE
        try:
            if f.is_file() and f.stat().st_size == MODEL_SIZE:
                return d
        except OSError:
            pass
    return None


def _friendly(e):
    reason = getattr(e, "reason", e)
    return (
        "The AI model (about 170 MB) could not be downloaded.\n\n"
        f"Reason: {reason}\n\n"
        "This is needed only ONCE. Please check that the internet works "
        "(github.com must be reachable), then press Retry. "
        "Nothing is uploaded - only the model is downloaded."
    )


def download_model(progress=None, cancel=None):
    dest_dir = app_data_dir() / "models"
    dest_dir.mkdir(parents=True, exist_ok=True)
    part = dest_dir / (MODEL_FILE + ".part")
    final = dest_dir / MODEL_FILE
    req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "PassportPhotoMaker/2.0"})
    md5 = hashlib.md5()
    done = 0
    last = 0.0
    try:
        with urllib.request.urlopen(req, timeout=20) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or MODEL_SIZE)
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                md5.update(chunk)
                done += len(chunk)
                now = time.time()
                if progress and now - last > 0.1:
                    progress(done, total)
                    last = now
    except Cancelled:
        _rm(part)
        raise
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as e:
        _rm(part)
        log.warning("model download failed: %s", e)
        raise ModelError(_friendly(e))
    if md5.hexdigest() != MODEL_MD5 or done != MODEL_SIZE:
        _rm(part)
        raise ModelError("The downloaded AI model file is incomplete or corrupt.\n\nPlease press Retry.")
    os.replace(part, final)
    if progress:
        progress(done, done)
    return dest_dir


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def ensure_model(progress=None, cancel=None):
    d = find_model()
    if d is not None:
        return d
    return download_model(progress, cancel)


_lock = threading.Lock()
_session = None


class MaskModel:
    """U2-Net salient-object model run directly through onnxruntime (no rembg / numba / scipy needed)."""
    SIZE = (320, 320)
    MEAN = (0.485, 0.456, 0.406)
    STD = (0.229, 0.224, 0.225)

    def __init__(self, onnx_path):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.log_severity_level = 3
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(str(onnx_path), sess_options=so, providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name

    def predict(self, img):
        """PIL RGB image -> PIL 'L' mask (255 = person/foreground) at the image's own size."""
        import numpy as np
        from PIL import Image

        im = img.convert("RGB").resize(self.SIZE, Image.LANCZOS)
        a = np.asarray(im, dtype=np.float32)
        a = a / max(float(a.max()), 1e-6)
        a = (a - np.array(self.MEAN, dtype=np.float32)) / np.array(self.STD, dtype=np.float32)
        x = a.transpose(2, 0, 1)[None].astype(np.float32)
        pred = self.sess.run(None, {self.input_name: x})[0][:, 0, :, :]
        ma, mi = float(pred.max()), float(pred.min())
        pred = np.squeeze((pred - mi) / max(ma - mi, 1e-6))
        mask = Image.fromarray((pred * 255).astype("uint8"), mode="L")
        return mask.resize(img.size, Image.LANCZOS)


FACE_FILE = "face_detector.onnx"
FACE_URL = "https://github.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB/raw/master/models/onnx/version-RFB-320.onnx"
FACE_SIZE = 1270727
_face_lock = threading.Lock()
_face = None
_face_failed = False


class FaceModel:
    """Tiny (1.3 MB) face detector run through onnxruntime - replaces OpenCV, so nothing else is needed."""

    def __init__(self, path):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.log_severity_level = 3
        self.sess = ort.InferenceSession(str(path), sess_options=so, providers=["CPUExecutionProvider"])

    def detect(self, img):
        """PIL image -> (x, y, w, h) of the largest face in image pixels, or None."""
        import numpy as np
        from PIL import Image

        W, H = img.size
        a = np.asarray(img.convert("RGB").resize((320, 240), Image.BILINEAR), dtype=np.float32)
        a = ((a - 127.0) / 128.0).transpose(2, 0, 1)[None].astype(np.float32)
        scores, boxes = self.sess.run(None, {"input": a})
        sc, bx = scores[0, :, 1], boxes[0]
        k = np.where(sc > 0.6)[0]
        if not len(k):
            return None
        best = bx[k[np.argmax(sc[k] * (bx[k, 2] - bx[k, 0]))]]

        def iou(p, q):
            ix = max(0.0, min(p[2], q[2]) - max(p[0], q[0]))
            iy = max(0.0, min(p[3], q[3]) - max(p[1], q[1]))
            inter = ix * iy
            return inter / max(1e-9, (p[2] - p[0]) * (p[3] - p[1]) + (q[2] - q[0]) * (q[3] - q[1]) - inter)

        sel = [i for i in k if iou(best, bx[i]) > 0.5]
        w = sc[sel][:, None]
        b = (bx[sel] * w).sum(0) / w.sum()
        return (float(b[0] * W), float(b[1] * H), float((b[2] - b[0]) * W), float((b[3] - b[1]) * H))


def get_face():
    """Face detector, or None if unavailable (the app then falls back to a mask-based crop)."""
    global _face, _face_failed
    with _face_lock:
        if _face is not None or _face_failed:
            return _face
        try:
            path = None
            for d in _candidate_dirs():
                f = d / FACE_FILE
                if f.is_file() and f.stat().st_size == FACE_SIZE:
                    path = f
                    break
            if path is None:  # tiny one-time download, only when running from source
                dest = app_data_dir() / "models"
                dest.mkdir(parents=True, exist_ok=True)
                path = dest / FACE_FILE
                req = urllib.request.Request(FACE_URL, headers={"User-Agent": "PassportPhotoMaker/2.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = r.read()
                if len(data) != FACE_SIZE:
                    raise RuntimeError("face model download incomplete")
                path.write_bytes(data)
            _face = FaceModel(path)
        except Exception:  # noqa
            log.exception("face detector unavailable - using fallback crop")
            _face_failed = True
        return _face


def session_ready():
    return _session is not None


def get_session(progress=None, cancel=None):
    """Create the ONNX session once; every later call returns the cached one."""
    global _session
    with _lock:
        if _session is not None:
            return _session
        d = ensure_model(progress, cancel)
        t = time.time()
        try:
            from PIL import Image

            s = MaskModel(d / MODEL_FILE)
            s.predict(Image.new("RGB", (320, 320), "white"))   # warm-up so the first real photo is fast
        except Exception as e:  # noqa
            log.exception("model start failed")
            raise ModelError(f"The AI model could not be started: {e}")
        log.info("AI session ready in %.2fs", time.time() - t)
        _session = s
        return _session
