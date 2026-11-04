"""Download the U2-Net model into ./models so it is bundled INSIDE the app (offline-first)."""
import hashlib, os, sys, urllib.request

URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
MD5 = "60024c5c889badc19c04ad937298a77b"
FACE_URL = "https://github.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB/raw/master/models/onnx/version-RFB-320.onnx"
FACE_MD5 = "1456b253b02dcd6a0e02a6d8ad69b136"
dest = os.path.join("models", "u2net.onnx")
os.makedirs("models", exist_ok=True)

for attempt in range(1, 4):
    try:
        print(f"download attempt {attempt}...")
        urllib.request.urlretrieve(URL, dest)
        h = hashlib.md5(open(dest, "rb").read()).hexdigest()
        if h == MD5:
            print("model OK", os.path.getsize(dest), "bytes")
            break
        print("checksum mismatch", h)
    except Exception as e:
        print("failed:", e)
else:
    sys.exit("could not download model")

for attempt in range(1, 4):
    try:
        face = os.path.join("models", "face_detector.onnx")
        urllib.request.urlretrieve(FACE_URL, face)
        if hashlib.md5(open(face, "rb").read()).hexdigest() == FACE_MD5:
            print("face model OK")
            sys.exit(0)
    except Exception as e:
        print("face download failed:", e)
sys.exit("could not download face model")
